"""Defaults: follow target exits (wide sell, no sell price guard)."""


def test_default_sell_worst_price_hits_floor():
    """SELL_SLIPPAGE_FRACTION=0.99 -> worst = max(0.01, ref * 0.01) -> 0.01 for typical refs."""
    ref = 0.50
    sell_slip = 0.99
    worst = max(0.01, ref * (1 - sell_slip))
    assert worst == 0.01


def test_default_buy_limit_tight():
    ref = 0.50
    buy_slip = 0.02
    worst = min(0.99, ref * (1 + buy_slip))
    assert abs(worst - 0.51) < 1e-9
