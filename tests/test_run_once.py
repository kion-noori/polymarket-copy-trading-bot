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
    monkeypatch.setattr(main, "LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setattr(main, "get_current_price", lambda asset: 0.5)
    monkeypatch.setattr(main, "get_bid_ask_prices", lambda asset: (0.49, 0.51))
    monkeypatch.setattr(main, "get_order_execution", lambda *args: ("pending", []))
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

    def fake_get_trades(limit=100, **kwargs):
        return [buy_trade, sell_trade]

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
    assert st.is_already_seen(main.trade_key(buy_trade)) is True
    assert st.is_already_seen(main.trade_key(sell_trade)) is True


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
    monkeypatch.setattr(main, "get_trades", lambda **kwargs: [trade])
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
    assert st.is_already_seen(main.trade_key(trade)) is True


def test_run_once_startup_reconcile_sells_excess_position(main_mod, monkeypatch):
    main, st = main_mod
    monkeypatch.setattr(main, "RECONCILE_ON_START", True)
    monkeypatch.setattr(main, "RECONCILE_SELL_ONLY", True)
    monkeypatch.setattr(main, "RECONCILE_MIN_NOTIONAL", 1.0)
    monkeypatch.setattr(main, "TARGET_WALLET", "target-wallet")
    monkeypatch.setattr(main, "FUNDER_ADDRESS", "my-wallet")

    monkeypatch.setattr(main, "get_trades", lambda **kwargs: [])
    monkeypatch.setattr(
        main,
        "get_portfolio_value",
        lambda user: 100.0,
    )
    monkeypatch.setattr(main, "get_collateral_balance_usdc", lambda: 0.0)
    monkeypatch.setattr(
        main,
        "get_positions",
        lambda user: (
            [
                {
                    "asset": "asset-1",
                    "conditionId": "cond-1",
                    "size": 20.0,
                    "curPrice": 0.5,
                    "title": "Market one",
                    "outcome": "YES",
                }
            ]
            if user == "my-wallet"
            else [
                {
                    "asset": "asset-1",
                    "conditionId": "cond-1",
                    "size": 5.0,
                    "curPrice": 0.5,
                    "title": "Market one",
                    "outcome": "YES",
                }
            ]
        ),
    )
    monkeypatch.setattr(
        main,
        "_skip_sell_insufficient_shares",
        lambda asset, my_notional, worst_price: (False, 20.0, my_notional / worst_price, my_notional),
    )

    placed = []

    def fake_place(asset, condition_id, side, my_notional, worst_price, title, outcome="?", order_type="FOK", **kwargs):
        placed.append((asset, side, round(my_notional, 2), round(worst_price, 3), title, outcome, order_type))
        return True

    monkeypatch.setattr(main, "_place_one", fake_place)

    main.run_once()

    assert placed == [("asset-1", "SELL", 7.5, 0.01, "Market one", "YES", "FAK")]


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
    monkeypatch.setattr(main, "get_trades", lambda **kwargs: [trade])
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
    assert st.is_already_seen(main.trade_key(trade)) is True


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

    monkeypatch.setattr(main, "get_trades", lambda **kwargs: [trade])
    monkeypatch.setattr(
        main,
        "get_portfolio_value",
        lambda user: 1000.0 if user == main.FUNDER_ADDRESS else 2000.0,
    )
    monkeypatch.setattr(main, "get_collateral_balance_usdc", lambda: 100.0)
    calls: list[float] = []

    def fake_place_market_order(**kwargs):
        calls.append(kwargs["notional_usd"])
        if len(calls) < 3:
            return {"success": False, "status": "rejected"}
        return {"orderID": "partial-ok", "status": "matched"}

    monkeypatch.setattr(main, "place_market_order", fake_place_market_order)

    main.run_once()
    assert st.is_already_seen(main.trade_key(trade)) is False

    first = json.loads(open(st.STATE_FILE, encoding="utf-8").read())
    assert first["order_failure_counts"][main.trade_key(trade)] == 1

    main.run_once()
    assert st.is_already_seen(main.trade_key(trade)) is True
    assert calls == [5.5, 5.5, 2.75]

    second = json.loads(open(st.STATE_FILE, encoding="utf-8").read())
    assert main.trade_key(trade) not in (second.get("order_failure_counts") or {})


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

    monkeypatch.setattr(main, "get_trades", lambda **kwargs: [trade])
    monkeypatch.setattr(
        main,
        "get_portfolio_value",
        lambda user: 1000.0 if user == main.FUNDER_ADDRESS else 2000.0,
    )
    monkeypatch.setattr(main, "get_collateral_balance_usdc", lambda: 100.0)
    monkeypatch.setattr(main, "place_market_order", lambda **kwargs: {"success": False, "status": "rejected"})

    main.run_once()
    assert st.is_already_seen(main.trade_key(trade)) is False

    main.run_once()
    assert st.is_already_seen(main.trade_key(trade)) is True


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
    monkeypatch.setattr(main, "get_trades", lambda **kwargs: [trade])
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
    assert st.is_already_seen(main.trade_key(trade)) is True


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
    monkeypatch.setattr(main, "get_trades", lambda **kwargs: [trade])
    monkeypatch.setattr(
        main,
        "get_portfolio_value",
        lambda user: 1000.0 if user == main.FUNDER_ADDRESS else 2000.0,
    )
    monkeypatch.setattr(main, "get_collateral_balance_usdc", lambda: 0.0)
    monkeypatch.setattr(main, "place_market_order", lambda **kwargs: placed.__setitem__("count", placed["count"] + 1))

    main.run_once()

    assert placed["count"] == 0
    assert st.is_already_seen(main.trade_key(trade)) is True


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

    monkeypatch.setattr(main, "get_trades", lambda **kwargs: [sell_trade])
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
    assert st.is_already_seen(main.trade_key(sell_trade)) is True


def test_partial_sell_keeps_reference_share_quantity(main_mod, monkeypatch):
    main, st = main_mod
    trade = {"transactionHash": "0xpartial", "side": "SELL", "size": 20, "price": 0.5,
             "asset": "token", "conditionId": "cond", "timestamp": 100}
    monkeypatch.setattr(main, "get_trades", lambda **kwargs: [trade])
    monkeypatch.setattr(main, "get_portfolio_value", lambda user: 100 if user == main.FUNDER_ADDRESS else 200)
    monkeypatch.setattr(main, "get_collateral_balance_usdc", lambda: 0)
    monkeypatch.setattr(main, "get_conditional_token_balance_shares", lambda token: 100)
    calls = []
    monkeypatch.setattr(main, "place_market_order", lambda **kwargs: calls.append(kwargs) or {"orderID": "order"})
    main.run_once()
    assert calls[0]["shares"] == 10
    assert calls[0]["worst_price"] == 0.01


def test_unknown_submission_does_not_repost_on_next_poll(main_mod, monkeypatch):
    main, st = main_mod
    trade = {"transactionHash": "0xuncertain", "side": "BUY", "size": 20, "price": 0.5,
             "asset": "token", "conditionId": "cond", "timestamp": 100}
    monkeypatch.setattr(main, "get_trades", lambda **kwargs: [trade])
    monkeypatch.setattr(main, "get_portfolio_value", lambda user: 100)
    monkeypatch.setattr(main, "get_collateral_balance_usdc", lambda: 20)
    calls = []
    monkeypatch.setattr(main, "place_market_order", lambda **kwargs: calls.append(kwargs) or {"status": "unknown"})
    main.run_once()
    st.clear_seen_memory_cache()
    main.run_once()
    assert len(calls) == 1
    assert main.journal.active_orders()[0]["status"] == "unknown"


def test_quote_outage_defers_without_consuming_trade(main_mod, monkeypatch):
    main, st = main_mod
    trade = {"transactionHash": "0xquote", "side": "BUY", "size": 20, "price": 0.5,
             "asset": "token", "conditionId": "cond", "timestamp": 100}
    monkeypatch.setattr(main, "get_trades", lambda **kwargs: [trade])
    monkeypatch.setattr(main, "get_portfolio_value", lambda user: 100)
    monkeypatch.setattr(main, "get_collateral_balance_usdc", lambda: 10)
    monkeypatch.setattr(main, "get_current_price", lambda asset: None)
    main.run_once()
    assert not st.is_already_seen(main.trade_key(trade))


def test_journal_repairs_seen_state_before_growing_catchup_group(main_mod, monkeypatch):
    """A crash after a confirmed post but before mark_seen must not replay its leg."""
    main, st = main_mod
    first = {"transactionHash": "first", "side": "BUY", "size": 10, "price": 0.5,
             "asset": "token", "conditionId": "cond", "timestamp": 100}
    second = {**first, "transactionHash": "second", "timestamp": 200}
    request = {"asset": "token", "side": "BUY", "source_ids": [main.trade_key(first)], "reference_price": 0.5}
    key, _ = main.journal.reserve(request)
    main.journal.update(key, "filled", response={"orderID": "old"}, fills=[])
    monkeypatch.setattr(main, "get_trades", lambda **kwargs: [first, second])
    monkeypatch.setattr(main, "get_portfolio_value", lambda user: 100)
    monkeypatch.setattr(main, "get_collateral_balance_usdc", lambda: 10)
    calls = []
    monkeypatch.setattr(main, "place_market_order", lambda **kw: calls.append(kw) or {"orderID": "new"})
    main.run_once()
    assert st.is_already_seen(main.trade_key(first))
    requests = [json.loads(row["request"]) for row in main.journal.all_orders()]
    assert len(calls) == 1
    assert requests[-1]["source_ids"] == [main.trade_key(second)]


def setup_cash_trade(main_mod, monkeypatch, cash=10):
    main, st = main_mod
    trade = {'transactionHash': 'cash', 'asset': 'token', 'conditionId': 'condition',
             'side': 'BUY', 'size': 1, 'price': .5, 'timestamp': 100}
    monkeypatch.setattr(main, 'get_trades', lambda **kwargs: [trade])
    monkeypatch.setattr(main, 'get_portfolio_value', lambda user: 100)
    monkeypatch.setattr(main, 'get_collateral_balance_usdc', lambda: cash)
    calls = []
    monkeypatch.setattr(main, 'place_market_order', lambda **kw: calls.append(kw) or {'orderID': 'order'})
    return main, st, trade, calls


def test_low_cash_defers_without_post_or_failure_counter(main_mod, monkeypatch):
    main, st, trade, calls = setup_cash_trade(main_mod, monkeypatch, cash=2)
    main.run_once()
    main.run_once()
    assert calls == []
    assert not st.is_already_seen(main.trade_key(trade))
    assert st.get_failure_count(main.trade_key(trade)) == 0


def test_cash_restored_within_deadline_can_copy_once(main_mod, monkeypatch):
    main, st, trade, calls = setup_cash_trade(main_mod, monkeypatch, cash=2)
    main.run_once()
    monkeypatch.setattr(main, 'get_collateral_balance_usdc', lambda: 20)
    main.run_once()
    main.run_once()
    assert len(calls) == 1


def test_deposit_does_not_replay_expired_cash_entry(main_mod, monkeypatch):
    main, st, trade, calls = setup_cash_trade(main_mod, monkeypatch, cash=20)
    main.controls.defer([main.trade_key(trade)], now=0)
    main.run_once()
    assert calls == []
    assert st.is_already_seen(main.trade_key(trade))
    assert any(r['reason'] == 'deferral_expired' for r in main.controls.summary()['decisions'])


def test_same_cycle_buys_cannot_each_spend_same_cached_cash(main_mod, monkeypatch):
    main, st, trade, calls = setup_cash_trade(main_mod, monkeypatch, cash=7)
    second = {**trade, 'asset': 'other', 'transactionHash': 'second'}
    monkeypatch.setattr(main, 'get_trades', lambda **kwargs: [trade, second])
    monkeypatch.setattr(main, 'get_order_execution', lambda *args: ('filled', [
        {'trade_id': 'fill', 'shares': 10, 'price': .5, 'notional_usd': 5,
         'timestamp': 100, 'transaction_hash': 'bot'}]))
    main.run_once()
    assert len(calls) == 1
    assert not st.is_already_seen(main.trade_key(second))


def test_pending_buy_budget_blocks_other_asset_even_if_balance_is_stale(main_mod, monkeypatch):
    main, st, trade, calls = setup_cash_trade(main_mod, monkeypatch, cash=7)
    key, _ = main.journal.reserve({'asset': 'other', 'side': 'BUY', 'notional_usd': 5,
                                   'source_ids': ['previous']})
    main.journal.update(key, 'unknown')
    main.run_once()
    assert calls == []


def test_pause_blocks_buys_but_does_not_disable_sell(main_mod, monkeypatch):
    main, st, trade, calls = setup_cash_trade(main_mod, monkeypatch, cash=20)
    main.controls.set_pause('token', True, 'external_sale')
    main.run_once()
    assert calls == []
    assert st.is_already_seen(main.trade_key(trade))
    sell = {**trade, 'side': 'SELL', 'transactionHash': 'sell', 'size': 10}
    monkeypatch.setattr(main, 'get_trades', lambda **kwargs: [sell])
    monkeypatch.setattr(main, 'get_conditional_token_balance_shares', lambda token: 10)
    main.run_once()
    assert len(calls) == 1 and calls[0]['side'] == 'SELL'


def test_external_activity_outage_defers_buy_without_spending_failure_budget(main_mod, monkeypatch):
    main, st, trade, calls = setup_cash_trade(main_mod, monkeypatch, cash=20)
    monkeypatch.setattr(main.manual_guard, 'refresh', lambda **kwargs: False)
    main.run_once()
    assert calls == []
    assert st.get_failure_count(main.trade_key(trade)) == 0
    assert not st.is_already_seen(main.trade_key(trade))


def test_known_combo_is_recorded_and_never_sent_to_ordinary_clob(main_mod, monkeypatch):
    main, st, trade, calls = setup_cash_trade(main_mod, monkeypatch, cash=20)
    main.controls.set_meta('combo_registry', {'conditions': ['condition']})
    main.run_once()
    assert calls == []
    assert st.is_already_seen(main.trade_key(trade))
    assert main.controls.summary()['decisions'][0]['reason'] == 'combo_requires_rfq'


def test_metadata_404_is_terminal_and_does_not_loop_ten_times(main_mod, monkeypatch):
    main, st, trade, calls = setup_cash_trade(main_mod, monkeypatch, cash=20)
    def unavailable(**kwargs):
        calls.append(kwargs)
        raise main.UnsupportedMarket('not available')
    monkeypatch.setattr(main, 'place_market_order', unavailable)
    main.run_once()
    main.run_once()
    assert len(calls) == 1
    assert st.is_already_seen(main.trade_key(trade))
