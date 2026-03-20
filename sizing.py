"""Compute our order notional from target trade and portfolio values."""

from config import MIN_NOTIONAL_MODE, SKIP_COPY_WHEN_TARGET_VALUE_UNKNOWN, get_sizing_params


def compute_my_notional(
    target_notional: float,
    my_portfolio_value: float,
    target_portfolio_value: float,
) -> float:
    """
    Proportional sizing with cap and floor (or skip dust — see MIN_NOTIONAL_MODE).
    - raw = target_notional * (my_value / target_value) * size_multiplier
    - capped = min(raw, my_value * max_pct_per_trade)
    - floor mode: my_notional = max(capped, min_notional)
    - skip mode: if capped < min_notional return 0 (caller should skip mirror)
    If target_portfolio_value <= 0: return 0 when SKIP_COPY_WHEN_TARGET_VALUE_UNKNOWN else min_notional.
    """
    params = get_sizing_params()
    if target_portfolio_value <= 0:
        if SKIP_COPY_WHEN_TARGET_VALUE_UNKNOWN:
            return 0.0
        return params.min_notional
    raw = (
        target_notional
        * (my_portfolio_value / target_portfolio_value)
        * params.size_multiplier
    )
    capped = min(raw, my_portfolio_value * params.max_pct_per_trade)
    if params.max_trade_usd > 0:
        capped = min(capped, params.max_trade_usd)
    if MIN_NOTIONAL_MODE == "skip":
        if capped < params.min_notional:
            return 0.0
        return capped
    return max(capped, params.min_notional)
