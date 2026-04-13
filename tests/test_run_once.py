"""Integration-style tests for run_once catch-up and retry semantics."""

import importlib
import json

import pytest


@pytest.fixture
def main_mod(tmp_path, monkeypatch):
    monkeypatch.setenv("TARGET_WALLET", "0x" + "1" * 40)
    monkeypatch.setenv("FUNDER_ADDRESS", "0x" + "2" * 40)
    monkeypatch.setenv("PRIVATE_KEY", "0x" + "a" * 64)
    monkeypatch.setenv("POLY_API_KEY", "k")
    monkeypatch.setenv("POLY_API_SECRET", "s")
    monkeypatch.setenv("POLY_API_PASSPHRASE", "p")
    monkeypatch.setenv("PRICE_GUARD_ENABLED", "0")
    monkeypatch.setenv("MAX_TRADE_AGE_SEC", "0")
    monkeypatch.setenv("MAX_LIVE_ORDER_ATTEMPTS", "2")
    monkeypatch.setenv("TEST_MODE", "0")

    import config
    import main
    import state as st

    importlib.reload(config)
    importlib.reload(st)
    monkeypatch.setattr(st, "STATE_FILE", str(tmp_path / "seen.json"))
    st.clear_seen_memory_cache()
    importlib.reload(main)
    yield main, st
    st.clear_seen_memory_cache()


def test_run_once_skips_asset_when_recent_window_contains_buy_then_sell(main_mod, monkeypatch):
    main, st = main_mod
    buy_trade = {
        "transactionHash": "0xbuy",
        "side": "BUY",
        "size": 10,
        "price": 0.5,
        "asset": "asset-1",
        "conditionId": "cond-1",
        "timestamp": 100,
        "title": "Market A",
    }
    sell_trade = {
        "transactionHash": "0xsell",
        "side": "SELL",
        "size": 10,
        "price": 0.48,
        "asset": "asset-1",
        "conditionId": "cond-1",
        "timestamp": 200,
        "title": "Market A",
    }

    def fake_get_trades(limit=100, offset=0):
        if offset == 0:
            return [sell_trade]
        if offset == 100:
            return [buy_trade]
        return []

    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(main, "get_trades", fake_get_trades)
    monkeypatch.setattr(
        main,
        "get_portfolio_value",
        lambda user: 1000.0 if user == main.FUNDER_ADDRESS else 2000.0,
    )
    monkeypatch.setattr(main, "get_collateral_balance_usdc", lambda: 0.0)
    monkeypatch.setattr(
        main,
        "place_market_order",
        lambda **kwargs: calls.append((kwargs["side"], kwargs["token_id"])) or {"orderID": "x"},
    )

    main.run_once()

    assert calls == []
    assert st.is_already_seen("0xbuy") is True
    assert st.is_already_seen("0xsell") is True


def test_run_once_single_sell_without_position_marks_seen_and_skips_order(main_mod, monkeypatch):
    main, st = main_mod
    trade = {
        "transactionHash": "0xsell-only",
        "side": "SELL",
        "size": 20,
        "price": 0.5,
        "asset": "asset-2",
        "conditionId": "cond-2",
        "timestamp": 100,
        "title": "Market B",
    }

    placed = {"called": False}
    monkeypatch.setattr(main, "get_trades", lambda limit=100, offset=0: [trade] if offset == 0 else [])
    monkeypatch.setattr(
        main,
        "get_portfolio_value",
        lambda user: 1000.0 if user == main.FUNDER_ADDRESS else 2000.0,
    )
    monkeypatch.setattr(main, "get_collateral_balance_usdc", lambda: 0.0)
    monkeypatch.setattr(main, "get_conditional_token_balance_shares", lambda token_id: 0.0)
    monkeypatch.setattr(
        main,
        "place_market_order",
        lambda **kwargs: placed.__setitem__("called", True) or {"orderID": "x"},
    )

    main.run_once()

    assert placed["called"] is False
    assert st.is_already_seen("0xsell-only") is True


def test_run_once_single_sell_dust_remainder_marks_seen_and_skips_order(main_mod, monkeypatch):
    main, st = main_mod
    trade = {
        "transactionHash": "0xsell-dust",
        "side": "SELL",
        "size": 20,
        "price": 0.5,
        "asset": "asset-dust",
        "conditionId": "cond-dust",
        "timestamp": 100,
        "title": "Dust Market",
    }

    placed = {"called": False}
    monkeypatch.setattr(main, "get_trades", lambda limit=100, offset=0: [trade] if offset == 0 else [])
    monkeypatch.setattr(
        main,
        "get_portfolio_value",
        lambda user: 1000.0 if user == main.FUNDER_ADDRESS else 2000.0,
    )
    monkeypatch.setattr(main, "get_collateral_balance_usdc", lambda: 0.0)
    monkeypatch.setattr(main, "get_conditional_token_balance_shares", lambda token_id: 0.008517)
    monkeypatch.setattr(
        main,
        "place_market_order",
        lambda **kwargs: placed.__setitem__("called", True) or {"orderID": "x"},
    )

    main.run_once()

    assert placed["called"] is False
    assert st.is_already_seen("0xsell-dust") is True


def test_run_once_failed_live_order_retries_then_uses_partial_fallback(main_mod, monkeypatch):
    main, st = main_mod
    trade = {
        "transactionHash": "0xfail-buy",
        "side": "BUY",
        "size": 20,
        "price": 0.5,
        "asset": "asset-3",
        "conditionId": "cond-3",
        "timestamp": 100,
        "title": "Market C",
    }

    monkeypatch.setattr(main, "get_trades", lambda limit=100, offset=0: [trade] if offset == 0 else [])
    monkeypatch.setattr(
        main,
        "get_portfolio_value",
        lambda user: 1000.0 if user == main.FUNDER_ADDRESS else 2000.0,
    )
    monkeypatch.setattr(main, "get_collateral_balance_usdc", lambda: 0.0)
    calls: list[float] = []

    def fake_place_market_order(**kwargs):
        calls.append(kwargs["notional_usd"])
        if len(calls) < 3:
            return None
        return {"orderID": "partial-ok", "status": "matched"}

    monkeypatch.setattr(main, "place_market_order", fake_place_market_order)

    main.run_once()
    assert st.is_already_seen("0xfail-buy") is False

    first = json.loads(open(st.STATE_FILE, encoding="utf-8").read())
    assert first["order_failure_counts"]["0xfail-buy"] == 1

    main.run_once()
    assert st.is_already_seen("0xfail-buy") is True
    assert calls == [5.0, 5.0, 2.5]

    second = json.loads(open(st.STATE_FILE, encoding="utf-8").read())
    assert "0xfail-buy" not in (second.get("order_failure_counts") or {})


def test_run_once_failed_live_order_fallback_failure_still_abandons(main_mod, monkeypatch):
    main, st = main_mod
    trade = {
        "transactionHash": "0xfail-buy-hard",
        "side": "BUY",
        "size": 20,
        "price": 0.5,
        "asset": "asset-hard",
        "conditionId": "cond-hard",
        "timestamp": 100,
        "title": "Market Hard",
    }

    monkeypatch.setattr(main, "get_trades", lambda limit=100, offset=0: [trade] if offset == 0 else [])
    monkeypatch.setattr(
        main,
        "get_portfolio_value",
        lambda user: 1000.0 if user == main.FUNDER_ADDRESS else 2000.0,
    )
    monkeypatch.setattr(main, "get_collateral_balance_usdc", lambda: 0.0)
    monkeypatch.setattr(main, "place_market_order", lambda **kwargs: None)

    main.run_once()
    assert st.is_already_seen("0xfail-buy-hard") is False

    main.run_once()
    assert st.is_already_seen("0xfail-buy-hard") is True


def test_run_once_skips_buy_above_max_buy_price(main_mod, monkeypatch):
    main, st = main_mod
    trade = {
        "transactionHash": "0xhi-price",
        "side": "BUY",
        "size": 10,
        "price": 0.94,
        "asset": "asset-4",
        "conditionId": "cond-4",
        "timestamp": 100,
        "title": "Market D",
    }

    placed = {"called": False}
    monkeypatch.setattr(main, "get_trades", lambda limit=100, offset=0: [trade] if offset == 0 else [])
    monkeypatch.setattr(
        main,
        "get_portfolio_value",
        lambda user: 1000.0 if user == main.FUNDER_ADDRESS else 2000.0,
    )
    monkeypatch.setattr(main, "get_collateral_balance_usdc", lambda: 0.0)
    monkeypatch.setattr(main, "get_current_price", lambda asset: 0.97)
    monkeypatch.setattr(main, "place_market_order", lambda **kwargs: placed.__setitem__("called", True))

    main.run_once()

    assert placed["called"] is False
    assert st.is_already_seen("0xhi-price") is True


def test_run_once_live_safe_startup_marks_visible_trades_seen(tmp_path, monkeypatch):
    monkeypatch.setenv("TARGET_WALLET", "0x" + "1" * 40)
    monkeypatch.setenv("FUNDER_ADDRESS", "0x" + "2" * 40)
    monkeypatch.setenv("PRIVATE_KEY", "0x" + "a" * 64)
    monkeypatch.setenv("POLY_API_KEY", "k")
    monkeypatch.setenv("POLY_API_SECRET", "s")
    monkeypatch.setenv("POLY_API_PASSPHRASE", "p")
    monkeypatch.setenv("PRICE_GUARD_ENABLED", "0")
    monkeypatch.setenv("MAX_TRADE_AGE_SEC", "0")
    monkeypatch.setenv("STARTUP_MODE", "live_safe")
    monkeypatch.setenv("TEST_MODE", "0")

    import config
    import main
    import state as st

    importlib.reload(config)
    importlib.reload(st)
    monkeypatch.setattr(st, "STATE_FILE", str(tmp_path / "seen.json"))
    st.clear_seen_memory_cache()
    importlib.reload(main)

    trade = {
        "transactionHash": "0xstartup",
        "side": "BUY",
        "size": 10,
        "price": 0.5,
        "asset": "asset-5",
        "conditionId": "cond-5",
        "timestamp": 100,
        "title": "Market E",
    }

    placed = {"count": 0}
    monkeypatch.setattr(main, "get_trades", lambda limit=100, offset=0: [trade] if offset == 0 else [])
    monkeypatch.setattr(
        main,
        "get_portfolio_value",
        lambda user: 1000.0 if user == main.FUNDER_ADDRESS else 2000.0,
    )
    monkeypatch.setattr(main, "get_collateral_balance_usdc", lambda: 0.0)
    monkeypatch.setattr(main, "place_market_order", lambda **kwargs: placed.__setitem__("count", placed["count"] + 1))

    main.run_once()

    assert placed["count"] == 0
    assert st.is_already_seen("0xstartup") is True


def test_run_once_catchup_sell_only_places_order_when_shares_exist(main_mod, monkeypatch):
    main, st = main_mod
    sell_trade = {
        "transactionHash": "0xcatchup-sell",
        "side": "SELL",
        "size": 10,
        "price": 0.5,
        "asset": "asset-catchup-sell",
        "conditionId": "cond-catchup-sell",
        "timestamp": 100,
        "title": "Market Sell Catchup",
    }

    placed: list[tuple[str, str]] = []

    monkeypatch.setattr(main, "get_trades", lambda limit=100, offset=0: [sell_trade] if offset == 0 else [])
    monkeypatch.setattr(
        main,
        "get_portfolio_value",
        lambda user: 1000.0 if user == main.FUNDER_ADDRESS else 2000.0,
    )
    monkeypatch.setattr(main, "get_collateral_balance_usdc", lambda: 0.0)
    monkeypatch.setattr(main, "get_conditional_token_balance_shares", lambda token_id: 100.0)
    monkeypatch.setattr(
        main,
        "place_market_order",
        lambda **kwargs: placed.append((kwargs["side"], kwargs["token_id"])) or {"orderID": "x"},
    )

    main.run_once()

    assert placed == [("SELL", "asset-catchup-sell")]
    assert st.is_already_seen("0xcatchup-sell") is True
