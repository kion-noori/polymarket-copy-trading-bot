"""
Pre-trade checks: stale trades and price vs target's fill (extra CLOB price reads).
"""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


def _parse_trade_timestamp_unix(trade: dict[str, Any]) -> float | None:
    """
    Return trade time as Unix seconds (UTC), or None if missing/unparseable.
    Data API may use seconds or milliseconds.
    """
    ts = trade.get("timestamp")
    if ts is None:
        return None
    try:
        t = float(ts)
    except (TypeError, ValueError):
        return None
    # Heuristic: ms since epoch
    if t > 1e12:
        t /= 1000.0
    elif t > 1e11:  # rare: still ms-ish
        t /= 1000.0
    return t


def trade_age_seconds(trade: dict[str, Any], now: float | None = None) -> float | None:
    """Seconds since trade time, or None if unknown."""
    t = _parse_trade_timestamp_unix(trade)
    if t is None:
        return None
    return max(0.0, (now if now is not None else time.time()) - t)


def is_trade_too_old(
    trade: dict[str, Any], max_age_sec: float, now: float | None = None
) -> bool:
    """If max_age_sec <= 0, never too old. If timestamp missing, not too old (avoid skipping all)."""
    if max_age_sec <= 0:
        return False
    age = trade_age_seconds(trade, now=now)
    if age is None:
        logger.debug("Trade age unknown (no timestamp); not applying max-age skip")
        return False
    return age > max_age_sec


def group_max_age_seconds(
    trades: list[dict[str, Any]], now: float | None = None
) -> float | None:
    """Oldest trade in the group (max age); None if no parseable timestamps."""
    ages: list[float] = []
    for t in trades:
        a = trade_age_seconds(t, now=now)
        if a is not None:
            ages.append(a)
    if not ages:
        return None
    return max(ages)


def is_group_too_old(
    trades: list[dict[str, Any]], max_age_sec: float, now: float | None = None
) -> bool:
    if max_age_sec <= 0 or not trades:
        return False
    oldest_age = group_max_age_seconds(trades, now=now)
    if oldest_age is None:
        return False
    return oldest_age > max_age_sec


def vwap_price_buy_group(trades: list[dict[str, Any]]) -> float | None:
    """Volume-weighted average price for BUY legs only."""
    num = 0.0
    den = 0.0
    for t in trades:
        if (t.get("side") or "").upper() != "BUY":
            continue
        try:
            sz = float(t.get("size", 0))
            px = float(t.get("price", 0))
        except (TypeError, ValueError):
            continue
        if sz <= 0 or px <= 0:
            continue
        num += sz * px
        den += sz
    if den <= 0:
        return None
    return num / den


def price_guard_allows(
    side: str,
    reference_price: float,
    current_mid: float | None,
    max_deviation_fraction: float,
) -> tuple[bool, str]:
    """
    Compare live mid to target's reference fill.
    - BUY: skip if current_mid > reference * (1 + max_deviation) — would pay much worse.
    - SELL: skip if current_mid < reference * (1 - max_deviation) — would get much worse exit.

    If current_mid is None or max_deviation_fraction <= 0, allow (no extra block).
    """
    if max_deviation_fraction <= 0 or current_mid is None or reference_price <= 0:
        return True, ""
    u = side.upper()
    if u == "BUY":
        limit = reference_price * (1.0 + max_deviation_fraction)
        if current_mid > limit:
            return (
                False,
                f"mid {current_mid:.4f} > ref*(1+dev)={limit:.4f} (target ref {reference_price:.4f})",
            )
    elif u == "SELL":
        limit = reference_price * (1.0 - max_deviation_fraction)
        if current_mid < limit:
            return (
                False,
                f"mid {current_mid:.4f} < ref*(1-dev)={limit:.4f} (target ref {reference_price:.4f})",
            )
    return True, ""
