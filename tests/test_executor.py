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
