from types import SimpleNamespace
import pytest
import data_api as api


def row(tx="0xtx", asset="token", side="BUY", size=10, price=0.5):
    return {"transaction_hash": tx, "token_id": asset, "condition_id": "condition", "side": side,
            "size": size, "price": price, "timestamp": 100, "outcome_index": 0}


def stub(monkeypatch, pages):
    calls = []
    def request(method, url, **kwargs):
        calls.append((url, dict(kwargs["params"])))
        return SimpleNamespace(json=lambda: pages[len(calls)-1])
    monkeypatch.setattr(api, "_request_with_retry", request)
    return calls


def page(rows, cursor=None):
    return {"data": rows, "pagination": {"next_cursor": cursor, "has_more": cursor is not None}}


def test_cursor_filters_and_both_maker_taker(monkeypatch):
    calls = stub(monkeypatch, [page([row()], "next"), page([row(tx="other")])])
    trades = api.get_trades("wallet", start=10, end=200)
    assert len(trades) == 2
    assert calls[0][0].endswith('/v2/trades')
    assert calls[1][1] == {"user": "wallet", "limit": 100, "taker_only": "false", "start": 10, "end": 200, "cursor": "next"}
    assert all("offset" not in params for _, params in calls)
    assert trades[0]["conditionId"] == "condition"


def test_transaction_legs_are_independent_but_same_leg_is_vwap_aggregated(monkeypatch):
    stub(monkeypatch, [page([row(size=2, price=0.4), row(size=3, price=0.6), row(asset="other"), row(side="SELL")])])
    trades = api.get_trades("wallet")
    assert len(trades) == 3
    assert len({api.trade_key(t) for t in trades}) == 3
    assert trades[0]["size"] == 5
    assert trades[0]["price"] == pytest.approx(0.52)


def test_repeated_cursor_aborts_snapshot(monkeypatch):
    stub(monkeypatch, [page([row()], "again"), page([row()], "again")])
    with pytest.raises(api.DataAPIError, match="Repeated"):
        api.get_trades("wallet")


def test_positions_never_silently_truncate(monkeypatch):
    monkeypatch.setattr(api, "_read", lambda *args: page([], "cursor"))
    with pytest.raises(api.DataAPIError):
        api._pages("positions", {"user": "wallet"}, max_pages=1)


def test_value_envelope_missing_value_is_error_not_zero(monkeypatch):
    stub(monkeypatch, [{"data": {}}])
    with pytest.raises(api.DataAPIError):
        api.get_portfolio_value("wallet")


def test_complete_position_normalization(monkeypatch):
    calls = stub(monkeypatch, [page([{"token_id": "t", "condition_id": "c", "current_size": 3,
                                     "current_price": 0.4, "outcome_index": 1}])])
    position = api.get_positions("wallet")[0]
    assert position["size"] == 3
    assert position["curPrice"] == 0.4
    assert calls[0][1]["include_archived"] == "true"


def test_rate_limit_honors_retry_after(monkeypatch):
    import requests
    sleeps = []
    response = requests.Response()
    response.status_code = 429
    response.headers["Retry-After"] = "7"
    calls = []
    def request(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise requests.HTTPError(response=response)
        return SimpleNamespace(raise_for_status=lambda: None)
    monkeypatch.setattr(api.requests, "request", request)
    monkeypatch.setattr(api.time, "sleep", sleeps.append)
    api._request_with_retry("GET", "https://example.invalid")
    assert sleeps == [7]


def test_combo_positions_follow_all_pages(monkeypatch):
    calls = stub(monkeypatch, [page([{'combo_condition_id': 'a'}], 'next'),
                               page([{'combo_condition_id': 'b'}])])
    assert len(api.get_combo_positions('wallet')) == 2
    assert calls[0][0].endswith('/v2/positions/combos')
    assert calls[1][1]['cursor'] == 'next'
