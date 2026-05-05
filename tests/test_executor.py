"""Execution-layer tests for retry pricing behavior."""

from types import SimpleNamespace

import executor


class DummyMarketOrderArgs:
    def __init__(self, token_id, amount, side, price, order_type):
        self.token_id = token_id
        self.amount = amount
        self.side = side
        self.price = price
        self.order_type = order_type


class FakeClient:
    def __init__(self, failures_before_success=0):
        self.failures_before_success = failures_before_success
        self.create_prices = []

    def create_market_order(self, order_args, options=None):
        self.create_prices.append(order_args.price)
        return order_args

    def post_order(self, signed, order_type):
        if len(self.create_prices) <= self.failures_before_success:
            raise RuntimeError("order couldn't be fully filled")
        return {"orderID": "abc", "status": "matched"}


class FakeV2Client:
    def __init__(self):
        self.calls = []

    def create_and_post_market_order(self, order_args, options=None, order_type=None):
        self.calls.append(
            {
                "token_id": order_args.token_id,
                "amount": order_args.amount,
                "side": order_args.side,
                "price": order_args.price,
                "order_type": order_args.order_type,
                "post_order_type": order_type,
            }
        )
        return {"orderID": "v2", "status": "matched"}


def test_buy_retries_widen_price(monkeypatch):
    fake_client = FakeClient(failures_before_success=2)
    monkeypatch.setattr(executor, "_require_client_lib", lambda: None)
    monkeypatch.setattr(executor, "get_market_options", lambda condition_id, token_id: None)
    monkeypatch.setattr(executor, "get_client", lambda: fake_client)
    monkeypatch.setattr(executor, "MarketOrderArgs", DummyMarketOrderArgs)
    monkeypatch.setattr(executor, "OrderType", SimpleNamespace(FOK="FOK"))
    monkeypatch.setattr(executor, "BUY", "BUY")
    monkeypatch.setattr(executor, "SELL", "SELL")
    monkeypatch.setattr(executor.time, "sleep", lambda _: None)

    resp = executor.place_market_order("tok", "cond", "BUY", 5.0, 0.714)

    assert resp == {"orderID": "abc", "status": "matched"}
    assert fake_client.create_prices == [0.714, 0.734, 0.754]


def test_sell_retry_keeps_same_price(monkeypatch):
    fake_client = FakeClient(failures_before_success=1)
    monkeypatch.setattr(executor, "_require_client_lib", lambda: None)
    monkeypatch.setattr(executor, "get_market_options", lambda condition_id, token_id: None)
    monkeypatch.setattr(executor, "get_client", lambda: fake_client)
    monkeypatch.setattr(executor, "MarketOrderArgs", DummyMarketOrderArgs)
    monkeypatch.setattr(executor, "OrderType", SimpleNamespace(FOK="FOK"))
    monkeypatch.setattr(executor, "BUY", "BUY")
    monkeypatch.setattr(executor, "SELL", "SELL")
    monkeypatch.setattr(executor.time, "sleep", lambda _: None)

    resp = executor.place_market_order("tok", "cond", "SELL", 5.0, 0.5)

    assert resp == {"orderID": "abc", "status": "matched"}
    assert fake_client.create_prices == [0.5, 0.5]


def test_v2_client_path_uses_create_and_post(monkeypatch):
    fake_client = FakeV2Client()
    monkeypatch.setattr(executor, "_require_client_lib", lambda: None)
    monkeypatch.setattr(executor, "get_market_options", lambda condition_id, token_id: None)
    monkeypatch.setattr(executor, "get_client", lambda: fake_client)
    monkeypatch.setattr(executor, "MarketOrderArgs", DummyMarketOrderArgs)
    monkeypatch.setattr(executor, "OrderType", SimpleNamespace(FOK="FOK"))
    monkeypatch.setattr(executor, "BUY", "BUY")
    monkeypatch.setattr(executor, "SELL", "SELL")
    monkeypatch.setattr(executor, "USING_CLOB_V2", True)

    resp = executor.place_market_order("tok", "cond", "BUY", 5.0, 0.714)

    assert resp == {"orderID": "v2", "status": "matched"}
    assert fake_client.calls == [
        {
            "token_id": "tok",
            "amount": 5.0,
            "side": "BUY",
            "price": 0.714,
            "order_type": "FOK",
            "post_order_type": "FOK",
        }
    ]


def test_v2_client_path_honors_custom_order_type(monkeypatch):
    fake_client = FakeV2Client()
    monkeypatch.setattr(executor, "_require_client_lib", lambda: None)
    monkeypatch.setattr(executor, "get_market_options", lambda condition_id, token_id: None)
    monkeypatch.setattr(executor, "get_client", lambda: fake_client)
    monkeypatch.setattr(executor, "MarketOrderArgs", DummyMarketOrderArgs)
    monkeypatch.setattr(executor, "OrderType", SimpleNamespace(FOK="FOK", FAK="FAK"))
    monkeypatch.setattr(executor, "BUY", "BUY")
    monkeypatch.setattr(executor, "SELL", "SELL")
    monkeypatch.setattr(executor, "USING_CLOB_V2", True)

    resp = executor.place_market_order("tok", "cond", "SELL", 2.5, 0.25, order_type="FAK")

    assert resp == {"orderID": "v2", "status": "matched"}
    assert fake_client.calls == [
        {
            "token_id": "tok",
            "amount": 10.0,
            "side": "SELL",
            "price": 0.25,
            "order_type": "FAK",
            "post_order_type": "FAK",
        }
    ]
