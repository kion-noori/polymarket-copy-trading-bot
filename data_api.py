"""Public Data API v2 reads with cursor pagination and a stable internal model."""
from __future__ import annotations

import logging
import math
import time
from typing import Any

import requests
from config import DATA_API_BASE, TARGET_WALLET

logger = logging.getLogger(__name__)
API_RETRIES = 3
API_RETRY_DELAY_SEC = 2


class DataAPIError(RuntimeError):
    """An unavailable/incomplete snapshot must never look like an empty portfolio."""


def _request_with_retry(method: str, url: str, **kwargs) -> requests.Response:
    timeout = kwargs.pop("timeout", 30)
    for attempt in range(API_RETRIES):
        try:
            response = requests.request(method, url, timeout=timeout, **kwargs)
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            response = getattr(exc, "response", None)
            if response is not None and response.status_code not in (429, 500, 502, 503, 504):
                raise DataAPIError(f"Data API rejected read: HTTP {response.status_code}") from exc
            if attempt == API_RETRIES - 1:
                raise DataAPIError("Data API read failed after retries") from exc
            delay = API_RETRY_DELAY_SEC
            if response is not None:
                try:
                    delay = min(60, max(delay, float(response.headers.get("Retry-After", delay))))
                except ValueError:
                    pass
            time.sleep(delay)
    raise DataAPIError("Data API read failed")


def _read(route: str, params: dict) -> dict:
    response = _request_with_retry("GET", f"{DATA_API_BASE.rstrip('/')}/v2/{route}", params=params)
    try:
        payload = response.json()
    except ValueError as exc:
        raise DataAPIError("Invalid Data API JSON") from exc
    if not isinstance(payload, dict) or "data" not in payload:
        raise DataAPIError("Missing Data API v2 envelope")
    return payload


def _pages(route: str, params: dict, *, max_pages: int, bounded: bool = False) -> list[dict]:
    rows: list[dict] = []
    cursors: set[str] = set()
    for _ in range(max_pages):
        payload = _read(route, params)
        data, pagination = payload["data"], payload.get("pagination")
        if not isinstance(data, list) or not all(isinstance(row, dict) for row in data):
            raise DataAPIError(f"Invalid {route} rows")
        if not isinstance(pagination, dict) or "next_cursor" not in pagination:
            raise DataAPIError(f"Missing {route} pagination")
        rows.extend(data)
        cursor = pagination["next_cursor"]
        if cursor is None:
            if pagination.get("has_more") is True:
                raise DataAPIError("Incomplete Data API cursor")
            return rows
        if not isinstance(cursor, str) or not cursor or cursor in cursors:
            raise DataAPIError("Repeated or invalid Data API cursor")
        cursors.add(cursor)
        params = {**params, "cursor": cursor}
    if bounded:
        return rows
    raise DataAPIError(f"{route} snapshot exceeds page limit; refusing partial snapshot")


def trade_key(trade: dict) -> str:
    """One logical fill group per transaction, asset and direction; old tx keys remain valid."""
    tx = trade.get("transactionHash") or trade.get("transaction_hash") or ""
    asset = trade.get("asset") or trade.get("token_id") or ""
    side = str(trade.get("side", "")).upper()
    return f"{tx}:{asset}:{side}" if tx and asset else ""


def _normalize_trade(row: dict) -> dict:
    return {**row, "transactionHash": row.get("transaction_hash"),
            "asset": row.get("token_id"), "conditionId": row.get("condition_id"),
            "outcomeIndex": row.get("outcome_index")}


def get_trades(user: str | None = None, limit: int = 100, *, max_pages: int = 5,
               start: int | None = None, end: int | None = None,
               bounded: bool = True, taker_only: bool = False) -> list[dict[str, Any]]:
    params: dict = {"user": (user or TARGET_WALLET).strip(), "limit": limit, "taker_only": "true" if taker_only else "false"}
    if not params["user"]:
        raise DataAPIError("Missing wallet for trade read")
    if start is not None:
        params["start"] = start
    if end is not None:
        params["end"] = end
    rows = _pages("trades", params, max_pages=max_pages, bounded=bounded)
    # Same transaction can contain several fills. Aggregate them before assigning a key.
    groups: dict[str, dict] = {}
    for row in rows:
        trade = _normalize_trade(row)
        key = trade_key(trade)
        if not key:
            raise DataAPIError("Trade lacks a stable transaction/asset identity")
        try:
            size, price = float(trade["size"]), float(trade["price"])
            if not math.isfinite(size) or not math.isfinite(price) or size <= 0 or not 0 < price <= 1:
                raise ValueError()
        except (KeyError, TypeError, ValueError) as exc:
            raise DataAPIError("Invalid trade size/price") from exc
        if key in groups:
            old = groups[key]
            total = old["size"] + size
            old["price"] = (old["size"] * old["price"] + size * price) / total
            old["size"] = total
        else:
            groups[key] = {**trade, "size": size, "price": price}
    return sorted(groups.values(), key=lambda row: row.get("timestamp", 0))


def get_positions(user: str, size_threshold: float | None = None) -> list[dict[str, Any]]:
    params: dict = {"user": user, "limit": 100, "include_archived": "true"}
    if size_threshold is not None:
        params.update(filter_type="TOKENS", filter_amount=size_threshold)
    rows = _pages("positions", params, max_pages=100)
    return [{**row, "asset": row.get("token_id"), "conditionId": row.get("condition_id"),
             "size": row.get("current_size"), "curPrice": row.get("current_price"),
             "outcomeIndex": row.get("outcome_index")} for row in rows]


def get_portfolio_value(user: str) -> float:
    data = _read("value", {"user": user})["data"]
    try:
        value = float(data["value"])
        if not math.isfinite(value) or value < 0:
            raise ValueError()
        return value
    except (KeyError, TypeError, ValueError) as exc:
        raise DataAPIError("Invalid portfolio value") from exc


def get_combo_positions(user: str) -> list[dict]:
    """Complete held Combo snapshot; entry basis is not an executable sale quote."""
    return _pages('positions/combos', {'user': user, 'limit': 100}, max_pages=100)


def get_activity(user: str, start: int, end: int) -> list[dict]:
    return _pages("activity", {"user": user, "start": start, "end": end, "limit": 100,
                              "exclude_deposits_withdrawals": "false"}, max_pages=1000)


def get_pnl_series(user: str) -> Any:
    return _read("user-pnl", {"user": user, "interval": "max", "fidelity": "1d"})["data"]
