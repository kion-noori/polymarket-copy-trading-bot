"""
Polymarket copy-trading bot: watch a target wallet and mirror their trades with proportional sizing.
"""

import logging
import os
import time
from datetime import datetime

from config import FUNDER_ADDRESS, TARGET_WALLET, POLL_INTERVAL_SEC, TEST_MODE, validate_config
from data_api import get_trades, get_portfolio_value
from executor import place_market_order
from sizing import compute_my_notional
from state import is_already_seen, mark_seen

# Slippage: allow 2% worse than target's price for our market order
SLIPPAGE_FRACTION = 0.02

LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"


def _setup_logging() -> None:
    os.makedirs(LOG_DIR, exist_ok=True)
    log_file = os.path.join(LOG_DIR, f"bot_{datetime.utcnow().strftime('%Y-%m-%d')}.log")
    fmt = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATEFMT)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if not root.handlers:
        console = logging.StreamHandler()
        console.setFormatter(fmt)
        root.addHandler(console)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)


_setup_logging()
logger = logging.getLogger(__name__)


def run_once() -> None:
    """Poll target trades, mirror any new ones with proportional sizing."""
    trades = get_trades(limit=50)
    if not trades:
        return

    my_value = get_portfolio_value(FUNDER_ADDRESS)
    target_value = get_portfolio_value(TARGET_WALLET)
    if my_value <= 0:
        logger.warning("My portfolio value is 0 or unknown; skipping execution")
        return

    # Process newest first; we only mirror each tx once
    for trade in trades:
        tx_hash = trade.get("transactionHash") or trade.get("transaction_hash")
        if not tx_hash:
            continue
        if is_already_seen(tx_hash):
            continue

        side = (trade.get("side") or "").upper()
        if side not in ("BUY", "SELL"):
            continue

        try:
            size = float(trade.get("size", 0))
            price = float(trade.get("price", 0))
        except (TypeError, ValueError):
            logger.warning("Skip trade %s: invalid size/price", tx_hash[:16])
            continue
        if size <= 0 or price <= 0:
            continue

        asset = trade.get("asset")
        condition_id = trade.get("conditionId") or trade.get("condition_id")
        if not asset or not condition_id:
            logger.warning("Skip trade %s: missing asset or conditionId", tx_hash[:16])
            continue

        target_notional = size * price
        my_notional = compute_my_notional(target_notional, my_value, target_value)

        # Slippage: for BUY allow slightly higher price, for SELL allow slightly lower
        if side == "BUY":
            worst_price = min(0.99, price * (1 + SLIPPAGE_FRACTION))
        else:
            worst_price = max(0.01, price * (1 - SLIPPAGE_FRACTION))

        logger.info(
            "Mirroring trade %s: %s %s notional=%.2f -> our notional=%.2f @ worst %.3f",
            tx_hash[:16],
            side,
            trade.get("title", "")[:40],
            target_notional,
            my_notional,
            worst_price,
        )
        if TEST_MODE:
            logger.info(
                "[TEST MODE] Would place %s order: token_id=%s notional=%.2f worst_price=%.3f (no order placed)",
                side,
                asset[:16] + "..." if len(asset) > 16 else asset,
                my_notional,
                worst_price,
            )
            mark_seen(tx_hash)
            continue
        resp = place_market_order(
            token_id=asset,
            condition_id=condition_id,
            side=side,
            notional_usd=my_notional,
            worst_price=worst_price,
        )
        if resp and resp.get("orderID"):
            logger.info("Order placed: orderID=%s status=%s", resp.get("orderID"), resp.get("status"))
        else:
            logger.error("Order failed or no orderID: %s", resp)
            # Still mark seen so we don't retry forever on same trade
        mark_seen(tx_hash)


def main() -> None:
    errors = validate_config()
    if errors:
        for e in errors:
            logger.error("Config: %s", e)
        raise SystemExit(1)

    logger.info(
        "Starting copy-trading: target=%s, poll_interval=%ds%s",
        TARGET_WALLET[:10] + "..." if len(TARGET_WALLET) > 10 else TARGET_WALLET,
        POLL_INTERVAL_SEC,
        " [TEST MODE - no orders placed]" if TEST_MODE else "",
    )
    while True:
        try:
            run_once()
        except Exception as e:
            logger.exception("Poll cycle error: %s", e)
        time.sleep(POLL_INTERVAL_SEC)


if __name__ == "__main__":
    main()
