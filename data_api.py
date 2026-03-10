"""Polymarket Data API client (public, no auth): trades and portfolio value."""

import logging
import time
from typing import Any

import requests

from config import DATA_API_BASE, TARGET_WALLET

logger = logging.getLogger(__name__)

# Retry: attempts and delay in seconds
API_RETRIES = 3
API_RETRY_DELAY_SEC = 2


def _request_with_retry(method: str, url: str, **kwargs) -> requests.Response | None:
    """GET with retries and backoff. Returns None on final failure."""
    timeout = kwargs.pop("timeout", 30)
    last_err = None
    for attempt in range(API_RETRIES):
        try:
            r = requests.request(method, url, timeout=timeout, **kwargs)
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            last_err = e
            if attempt < API_RETRIES - 1:
                time.sleep(API_RETRY_DELAY_SEC)
    logger.warning("Request failed after %s attempts: %s", API_RETRIES, last_err)
    return None


def get_trades(user: str | None = None, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    """Fetch trades for a user. Defaults to TARGET_WALLET. Retries on failure."""
    addr = (user or TARGET_WALLET).strip()
    if not addr:
        return []
    url = f"{DATA_API_BASE}/trades"
    params = {"user": addr, "limit": limit, "offset": offset, "takerOnly": True}
    r = _request_with_retry("GET", url, params=params, timeout=30)
    if r is None:
        return []
    try:
        return r.json()
    except ValueError:
        return []


def get_portfolio_value(user: str) -> float:
    """Get total portfolio value (USDC) for an address. Returns 0 on error. Retries on failure."""
    addr = (user or "").strip()
    if not addr:
        return 0.0
    url = f"{DATA_API_BASE}/value"
    params = {"user": addr}
    r = _request_with_retry("GET", url, params=params, timeout=15)
    if r is None:
        return 0.0
    try:
        data = r.json()
        if isinstance(data, list) and data:
            return float(data[0].get("value", 0))
        if isinstance(data, dict):
            return float(data.get("value", 0))
        return 0.0
    except (KeyError, TypeError, ValueError):
        return 0.0
