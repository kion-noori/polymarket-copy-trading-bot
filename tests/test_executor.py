"""Order quantities, API response parsing and ambiguous submission handling."""
from types import SimpleNamespace
import pytest
import executor


@pytest.fixture
def client(monkeypatch):
    class Client:
        def __init__(self):
            self.posts = []
            self.response = {"orderID": "order", "status": "matched", "tradeIDs": ["fill"]}
            self.error = None
        def create_market_order(self, args, options=None):
            return args
        def post_order(self, args, kind):
            self.posts.append((args, kind))
            if self.error:
                raise self.error
            return self.response
        def get_midpoint(self, token):
            return {"mid": "0.5"}
        def get_price(self, token, side):
            return {"price": "0.49" if side == "BUY" else "0.51"}
    fake = Client()
    monkeypatch.setattr(executor, "get_client", lambda: fake)
    monkeypatch.setattr(executor, "get_market_options", lambda *a: SimpleNamespace(tick_size="0.01"))
    return fake


def test_quotes_unpack_json_and_use_documented_book_sides(client):
    assert executor.get_current_price("token") == 0.5
    assert executor.get_bid_ask_prices("token") == (0.49, 0.51)


def test_sell_quantity_does_not_depend_on_price_floor(client):
    executor.place_market_order("token", "condition", "SELL", 5, 0.01, shares=10)
    args, kind = client.posts[0]
    assert args.amount == 10
    assert args.price == 0.01
    assert kind == "FAK"


def test_sell_requires_shares(client):
    with pytest.raises(ValueError, match="explicit"):
        executor.place_market_order("token", "condition", "SELL", 5, 0.01)
    assert not client.posts


def test_buy_price_is_rounded_inside_cap_and_budget_includes_fees(client):
    executor.place_market_order("token", "condition", "BUY", 5, 0.714)
    args, kind = client.posts[0]
    assert args.price == 0.71
    assert args.amount == 5
    assert args.user_usdc_balance == 5


def test_timeout_is_not_retried(client):
    client.error = TimeoutError()
    result = executor.place_market_order("token", "condition", "BUY", 5, 0.5)
    assert result["status"] == "unknown"
    assert len(client.posts) == 1


def test_definitive_rejection_is_distinct_from_unknown(client):
    class Rejected(Exception):
        status_code = 400
    client.error = Rejected()
    assert executor.place_market_order("token", "condition", "BUY", 5, 0.5)["success"] is False


def test_confirmed_partial_fill_uses_actual_quantities(client):
    client.get_order = lambda order: {"status": "MATCHED", "size_matched": "3", "associate_trades": ["fill"]}
    client.get_trades = lambda params: [{"id": "fill", "status": "CONFIRMED", "taker_order_id": "order",
                                       "size": "3", "price": "0.48", "transaction_hash": "0xtx"}]
    status, fills = executor.get_order_execution("order", {})
    assert status == "filled"
    assert fills[0]["shares"] == 3
    assert fills[0]["notional_usd"] == pytest.approx(1.44)


def test_matched_but_unsettled_is_pending(client):
    client.get_order = lambda order: {"status": "MATCHED", "size_matched": "3", "associate_trades": ["fill"]}
    client.get_trades = lambda params: [{"id": "fill", "status": "MINED"}]
    assert executor.get_order_execution("order", {}) == ("pending", [])


def test_maker_fill_uses_our_order_amount_not_total_trade(client):
    client.get_order = lambda order: {"status": "MATCHED", "size_matched": "2", "associate_trades": ["fill"]}
    client.get_trades = lambda params: [{"id": "fill", "status": "CONFIRMED", "size": "100", "price": "0.5",
        "maker_orders": [{"order_id": "order", "matched_amount": "2", "price": "0.51"}]}]
    status, fills = executor.get_order_execution("order", {})
    assert status == "filled"
    assert fills[0]["shares"] == 2
    assert fills[0]["price"] == 0.51


def test_pinned_sdk_signs_actual_order_with_explicit_sell_shares(monkeypatch):
    """Exercise the real SDK builder/signature and serialized side, without HTTP."""
    import base64
    from py_clob_client_v2 import ApiCreds, ClobClient
    sdk = ClobClient("https://clob.invalid", chain_id=137, key="0x" + "a" * 64,
                     creds=ApiCreds(api_key="test", api_secret=base64.b64encode(b"test").decode(),
                                    api_passphrase="test"), signature_type=0, retry_on_error=False)
    def get(url, **kwargs):
        if "/clob-markets/" in url:
            return {"mts": "0.01", "nr": False, "t": [{"t": "123"}], "fd": {"r": 0, "e": 1}}
        if url.endswith("/version"):
            return {"version": 2}
        raise AssertionError(f"Unexpected SDK read: {url}")
    posts = []
    def post(url, **kwargs):
        import json
        posts.append(json.loads(kwargs["data"]))
        return {"orderID": "order", "status": "delayed", "tradeIDs": []}
    monkeypatch.setattr(sdk, "_get", get)
    monkeypatch.setattr(sdk, "_post", post)
    monkeypatch.setattr(executor, "get_client", lambda: sdk)
    result = executor.place_market_order("123", "condition", "SELL", 5, 0.01, shares=10)
    assert result["orderID"] == "order"
    assert posts[0]["order"]["makerAmount"] == "10000000"
    assert posts[0]["order"]["takerAmount"] == "100000"
    assert posts[0]["orderType"] == "FAK"
