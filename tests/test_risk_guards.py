"""Tests for risk_guards helpers."""

from risk_guards import (
    is_group_too_old,
    is_trade_too_old,
    price_guard_allows,
    vwap_price_buy_group,
)


def test_price_guard_buy_blocks_if_mid_too_high():
    ok, _ = price_guard_allows("BUY", 0.50, 0.60, 0.08)
    assert ok is False


def test_price_guard_buy_allows_near_mid():
    ok, _ = price_guard_allows("BUY", 0.50, 0.53, 0.08)
    assert ok is True


def test_price_guard_sell_blocks_if_mid_too_low():
    ok, _ = price_guard_allows("SELL", 0.50, 0.40, 0.08)
    assert ok is False


def test_price_guard_none_mid_allows():
    ok, _ = price_guard_allows("BUY", 0.50, None, 0.08)
    assert ok is True


def test_trade_age_ms_timestamp():
    now = 1_700_000_000.0
    trade = {"timestamp": int(now * 1000)}
    assert is_trade_too_old(trade, max_age_sec=3600, now=now + 10) is False
    assert is_trade_too_old(trade, max_age_sec=3600, now=now + 4000) is True


def test_max_age_zero_never_old():
    trade = {"timestamp": 1_700_000_000}
    assert is_trade_too_old(trade, 0) is False


def test_group_too_old_uses_oldest():
    base = 1_700_000_000.0
    g = [
        {"timestamp": base},
        {"timestamp": base + 100},
    ]
    assert is_group_too_old(g, max_age_sec=50, now=base + 60) is True


def test_vwap_buy_group():
    trades = [
        {"side": "BUY", "size": 10, "price": 0.40},
        {"side": "BUY", "size": 10, "price": 0.60},
    ]
    assert abs(vwap_price_buy_group(trades) - 0.50) < 1e-9
