"""Compute our order notional from target trade and portfolio values."""

from config import get_sizing_params


def compute_my_notional(
    target_notional: float,
    my_portfolio_value: float,
    target_portfolio_value: float,
) -> float:
    """
    Proportional sizing with cap and floor.
    - raw = target_notional * (my_value / target_value) * size_multiplier
    - capped = min(raw, my_value * max_pct_per_trade)
    - my_notional = max(capped, min_notional)
    """
    params = get_sizing_params()
    if target_portfolio_value <= 0:
        return params.min_notional
    raw = (
        target_notional
        * (my_portfolio_value / target_portfolio_value)
        * params.size_multiplier
    )
    capped = min(raw, my_portfolio_value * params.max_pct_per_trade)
    if params.max_trade_usd > 0:
        capped = min(capped, params.max_trade_usd)
    return max(capped, params.min_notional)
