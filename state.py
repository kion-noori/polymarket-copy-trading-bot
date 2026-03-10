"""Persist seen trade IDs so we don't mirror the same trade twice after restarts."""

import json
import logging
import os

from config import TARGET_WALLET

logger = logging.getLogger(__name__)

STATE_DIR = os.path.join(os.path.dirname(__file__), "state")
STATE_FILE = os.path.join(STATE_DIR, "seen_trades.json")
MAX_SEEN = 10_000  # Keep last N to avoid unbounded growth


def _load_seen() -> set[str]:
    if not os.path.isfile(STATE_FILE):
        return set()
    try:
        with open(STATE_FILE) as f:
            data = json.load(f)
        return set(data.get("seen_tx_hashes", []))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Could not load state file: %s", e)
        return set()


def _save_seen(seen: set[str]) -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    lst = list(seen)
    if len(lst) > MAX_SEEN:
        lst = lst[-MAX_SEEN:]
    try:
        with open(STATE_FILE, "w") as f:
            json.dump({"target": TARGET_WALLET, "seen_tx_hashes": lst}, f, indent=0)
    except OSError as e:
        logger.warning("Could not save state file: %s", e)


def is_already_seen(transaction_hash: str) -> bool:
    return transaction_hash in _load_seen()


def mark_seen(transaction_hash: str) -> None:
    seen = _load_seen()
    seen.add(transaction_hash)
    _save_seen(seen)


def mark_seen_batch(transaction_hashes: list[str]) -> None:
    """Mark multiple hashes as seen in one read/write cycle."""
    if not transaction_hashes:
        return
    seen = _load_seen()
    for h in transaction_hashes:
        if h:
            seen.add(h)
    _save_seen(seen)
