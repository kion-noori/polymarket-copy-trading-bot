"""Persist seen trade IDs so we don't mirror the same trade twice after restarts."""

from __future__ import annotations

import json
import logging
import os

from config import TARGET_WALLET

logger = logging.getLogger(__name__)

STATE_DIR = os.path.join(os.path.dirname(__file__), "state")
STATE_FILE = os.path.join(STATE_DIR, "seen_trades.json")
MAX_SEEN = 10_000  # Keep last N to avoid unbounded growth

# In-process cache (single bot process). None = not loaded from disk yet.
_seen_cache: set[str] | None = None
_seen_order_cache: list[str] | None = None
_failure_counts_cache: dict[str, int] | None = None


def clear_seen_memory_cache() -> None:
    """Drop in-memory state; next access reloads from disk."""
    global _seen_cache, _seen_order_cache, _failure_counts_cache
    _seen_cache = None
    _seen_order_cache = None
    _failure_counts_cache = None


def _load_full_from_disk() -> tuple[set[str], list[str], dict[str, int]]:
    if not os.path.isfile(STATE_FILE):
        return set(), [], {}
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        raw_seen = data.get("seen_tx_hashes", [])
        seen_order: list[str] = []
        seen: set[str] = set()
        if isinstance(raw_seen, list):
            for item in raw_seen:
                if not item:
                    continue
                h = str(item)
                if h in seen:
                    continue
                seen.add(h)
                seen_order.append(h)
        raw_fc = data.get("order_failure_counts") or {}
        failures: dict[str, int] = {}
        if isinstance(raw_fc, dict):
            for k, v in raw_fc.items():
                if not k:
                    continue
                try:
                    iv = int(v)
                except (TypeError, ValueError):
                    continue
                if iv > 0:
                    failures[str(k)] = iv
        return seen, seen_order, failures
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Could not load state file: %s", e)
        return set(), [], {}


def _ensure_loaded() -> None:
    global _seen_cache, _seen_order_cache, _failure_counts_cache
    if _seen_cache is None:
        seen, seen_order, failures = _load_full_from_disk()
        _seen_cache = seen
        _seen_order_cache = seen_order
        _failure_counts_cache = failures
    if _seen_order_cache is None:
        _seen_order_cache = []
    if _failure_counts_cache is None:
        _failure_counts_cache = {}


def _get_seen() -> set[str]:
    _ensure_loaded()
    assert _seen_cache is not None
    return _seen_cache


def _get_failure_counts() -> dict[str, int]:
    _ensure_loaded()
    assert _failure_counts_cache is not None
    return _failure_counts_cache


def _get_seen_order() -> list[str]:
    _ensure_loaded()
    assert _seen_order_cache is not None
    return _seen_order_cache


def _save_state() -> None:
    _ensure_loaded()
    seen = _get_seen()
    seen_order = _get_seen_order()
    failures = _get_failure_counts()
    os.makedirs(STATE_DIR, exist_ok=True)
    if len(seen_order) > MAX_SEEN:
        seen_order[:] = seen_order[-MAX_SEEN:]
        seen.clear()
        seen.update(seen_order)
    # Drop failure rows for hashes we've already seen (housekeeping)
    for h in list(failures.keys()):
        if h in seen:
            del failures[h]
    fc_out = {k: v for k, v in failures.items() if v > 0}
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "target": TARGET_WALLET,
                    "seen_tx_hashes": seen_order,
                    "order_failure_counts": fc_out,
                },
                f,
                indent=0,
            )
    except OSError as e:
        logger.warning("Could not save state file: %s", e)


def is_already_seen(transaction_hash: str) -> bool:
    if not transaction_hash:
        return False
    return transaction_hash in _get_seen()


def mark_seen(transaction_hash: str) -> None:
    if not transaction_hash:
        return
    seen = _get_seen()
    seen_order = _get_seen_order()
    failures = _get_failure_counts()
    if transaction_hash not in seen:
        seen.add(transaction_hash)
        seen_order.append(transaction_hash)
    failures.pop(transaction_hash, None)
    _save_state()


def mark_seen_batch(transaction_hashes: list[str]) -> None:
    """Mark multiple hashes as seen in one read/write cycle."""
    hashes = [h for h in transaction_hashes if h]
    if not hashes:
        return
    seen = _get_seen()
    seen_order = _get_seen_order()
    failures = _get_failure_counts()
    for h in hashes:
        if h not in seen:
            seen.add(h)
            seen_order.append(h)
        failures.pop(h, None)
    _save_state()


def note_live_order_failure(
    transaction_hashes: list[str], max_attempts: int
) -> bool:
    """
    Record one failed live CLOB post per logical mirror attempt.
    For catch-up, increments each tx hash in the batch by 1 (one failed order = one bump each).

    If max_attempts <= 0, never returns True (unlimited retries).

    Returns True if max_attempts reached for any involved hash — caller should mark_seen
    and stop retrying (or handle manual copy).
    """
    if max_attempts <= 0:
        return False
    hashes = [h for h in transaction_hashes if h]
    if not hashes:
        return False
    failures = _get_failure_counts()
    max_count = 0
    for h in hashes:
        failures[h] = failures.get(h, 0) + 1
        max_count = max(max_count, failures[h])
    _save_state()
    return max_count >= max_attempts
