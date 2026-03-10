"""
Polymarket copy-trading bot: watch a target wallet and mirror their trades with proportional sizing.
"""

import logging
import os
import time
from datetime import datetime

from config import FUNDER_ADDRESS, TARGET_WALLET, POLL_INTERVAL_SEC, TEST_MODE, validate_config
from data_api import get_trades, get_portfolio_value
from executor import get_current_price, place_market_order
from sizing import compute_my_notional
from state import is_already_seen, mark_seen, mark_seen_batch

# Slippage: allow 2% worse than target's price for our market order
SLIPPAGE_FRACTION = 0.02

LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"
TRADES_LOG_HEADER = "timestamp,side,outcome,market_title,notional_usd,price,shares,mode"


def _normalize_outcome(trade: dict) -> str:
    """Return YES, NO, or ? from trade's outcome or outcomeIndex."""
    out = trade.get("outcome") or trade.get("outcomeName") or ""
    if isinstance(out, str):
        u = out.upper().strip()
        if u in ("YES", "Y"): return "YES"
        if u in ("NO", "N"): return "NO"
        if u: return u[:3]  # e.g. "Yes" -> "YES" via slice
    idx = trade.get("outcomeIndex")
    if idx is not None:
        return "YES" if idx == 0 else "NO"
    return "?"


def _append_trade_log(side: str, outcome: str, title: str, notional_usd: float, price: float, mode: str = "live") -> None:
    """Append one line to the daily trades CSV for a clear audit of what was bought/sold."""
    if price <= 0:
        return
    shares = notional_usd / price
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    raw = (title or "").strip()
    safe_title = raw.replace('"', '""')
    if "," in safe_title or "\n" in safe_title or '"' in raw:
        safe_title = f'"{safe_title}"'
    line = f"{ts},{side},{outcome},{safe_title},{notional_usd:.2f},{price:.4f},{shares:.4f},{mode}\n"
    log_path = os.path.join(LOG_DIR, f"trades_{datetime.utcnow().strftime('%Y-%m-%d')}.csv")
    try:
        write_header = not os.path.isfile(log_path)
        with open(log_path, "a", encoding="utf-8") as f:
            if write_header:
                f.write(TRADES_LOG_HEADER + "\n")
            f.write(line)
    except OSError as e:
        logger.warning("Could not write trades log: %s", e)


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


# Minimum net notional to place an order when catching up (avoid dust)
MIN_NET_NOTIONAL = 0.50

# Theoretical portfolio (test mode only): simulate $500 and track PnL of "would have" trades
THEORETICAL_START = 500.0
_theoretical_cash = THEORETICAL_START
_theoretical_positions: dict[str, dict] = {}  # token_id -> {"shares": float, "entry_price": float}

# Throttle balance logging when idle: log every N-th poll if no new trades to mirror
_poll_count = 0
IDLE_LOG_EVERY_N_POLLS = 10


def _apply_theoretical_trade(asset: str, side: str, notional: float, price: float) -> None:
    """Update simulated portfolio when we 'would place' a trade in test mode."""
    global _theoretical_cash, _theoretical_positions
    if price <= 0:
        return
    if side.upper() == "BUY":
        _theoretical_cash -= notional
        shares = notional / price
        if asset not in _theoretical_positions:
            _theoretical_positions[asset] = {"shares": 0.0, "entry_price": price}
        pos = _theoretical_positions[asset]
        total_cost = pos["shares"] * pos["entry_price"] + notional
        pos["shares"] += shares
        if pos["shares"] > 0:
            pos["entry_price"] = total_cost / pos["shares"]
    else:
        shares_sold = notional / price
        if asset not in _theoretical_positions:
            return  # Can't sell what we don't hold in simulated portfolio
        pos = _theoretical_positions[asset]
        pos["shares"] -= shares_sold
        if pos["shares"] <= 0:
            del _theoretical_positions[asset]
        _theoretical_cash += notional


def _log_theoretical_pnl() -> None:
    """Log theoretical equity and PnL (test mode, mark-to-market when possible)."""
    equity = _theoretical_cash
    for token_id, pos in list(_theoretical_positions.items()):
        shares = pos["shares"]
        if shares <= 0:
            continue
        current = get_current_price(token_id)
        price = current if current is not None else pos["entry_price"]
        equity += shares * price
    pnl = equity - THEORETICAL_START
    logger.info(
        "Theoretical PnL (fake $500): equity=$%.2f | PnL=$%.2f (%.1f%%)",
        equity,
        pnl,
        100.0 * pnl / THEORETICAL_START if THEORETICAL_START else 0,
    )


def _place_one(
    asset: str,
    condition_id: str,
    side: str,
    my_notional: float,
    worst_price: float,
    title: str,
    outcome: str = "?",
) -> None:
    """Place a single order (or log in test mode) and mark no state."""
    shares = my_notional / worst_price if worst_price > 0 else 0
    market_short = ((title or "").strip() or "Unknown market")[:50]
    logger.info(
        "Trade: %s %s | %s | $%.2f @ %.3f | ~%.2f shares",
        side,
        outcome,
        market_short,
        my_notional,
        worst_price,
        shares,
    )
    _append_trade_log(side, outcome, title or "", my_notional, worst_price, mode="test" if TEST_MODE else "live")
    if TEST_MODE:
        _apply_theoretical_trade(asset, side, my_notional, worst_price)
        logger.info("[TEST MODE] No order placed (simulation only)")
        return
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


def run_once() -> None:
    """Poll target trades, mirror any new ones with proportional sizing."""
    global _poll_count
    _poll_count += 1

    trades = get_trades(limit=50)
    trades = sorted(trades, key=lambda t: t.get("timestamp") or 0) if trades else []

    my_value = get_portfolio_value(FUNDER_ADDRESS)
    target_value = get_portfolio_value(TARGET_WALLET)
    if my_value <= 0 and TEST_MODE:
        my_value = 500.0  # placeholder for sizing and theoretical PnL
        if _poll_count == 1:
            logger.info("Test mode: using placeholder portfolio value $500 (actual value 0 or unknown)")

    if not trades:
        # No trades at all: log balance only every N-th poll to avoid log spam
        if _poll_count % IDLE_LOG_EVERY_N_POLLS == 1:
            logger.info("Portfolio: me=$%.2f | target=$%.2f (no new trades)", my_value, target_value)
            if TEST_MODE:
                _log_theoretical_pnl()
        return

    if my_value <= 0 and not TEST_MODE:
        logger.warning("My portfolio value is 0 or unknown; skipping execution")
        return

    # Collect unseen trades and group by asset (same market/token)
    unseen_by_asset: dict[str, list[dict]] = {}
    for trade in trades:
        tx_hash = trade.get("transactionHash") or trade.get("transaction_hash")
        if not tx_hash or is_already_seen(tx_hash):
            continue
        side = (trade.get("side") or "").upper()
        if side not in ("BUY", "SELL"):
            continue
        try:
            size = float(trade.get("size", 0))
            price = float(trade.get("price", 0))
        except (TypeError, ValueError):
            continue
        if size <= 0 or price <= 0:
            continue
        asset = trade.get("asset")
        condition_id = trade.get("conditionId") or trade.get("condition_id")
        if not asset or not condition_id:
            continue
        unseen_by_asset.setdefault(asset, []).append(trade)

    # When we have new trades to mirror, always log balance. When idle (all seen), only every N-th poll.
    should_log_balance = len(unseen_by_asset) > 0 or _poll_count % IDLE_LOG_EVERY_N_POLLS == 1
    if should_log_balance:
        logger.info("Portfolio: me=$%.2f | target=$%.2f", my_value, target_value)
        if TEST_MODE:
            _log_theoretical_pnl()
    if len(unseen_by_asset) == 0:
        # All trades already seen; nothing to mirror this poll
        return

    for asset, group in unseen_by_asset.items():
        if len(group) == 1:
            # Single trade: mirror as-is
            trade = group[0]
            tx_hash = trade.get("transactionHash") or trade.get("transaction_hash")
            side = (trade.get("side") or "").upper()
            size = float(trade.get("size", 0))
            price = float(trade.get("price", 0))
            condition_id = trade.get("conditionId") or trade.get("condition_id")
            target_notional = size * price
            my_notional = compute_my_notional(target_notional, my_value, target_value)
            worst_price = min(0.99, price * (1 + SLIPPAGE_FRACTION)) if side == "BUY" else max(0.01, price * (1 - SLIPPAGE_FRACTION))
            _place_one(
                asset,
                condition_id,
                side,
                my_notional,
                worst_price,
                trade.get("title", ""),
                outcome=_normalize_outcome(trade),
            )
            mark_seen(tx_hash)
            continue

        # Multiple trades for same asset (catching up)
        has_buy = any((t.get("side") or "").upper() == "BUY" for t in group)
        has_sell = any((t.get("side") or "").upper() == "SELL" for t in group)

        mark_seen_batch(
            [t.get("transactionHash") or t.get("transaction_hash") for t in group]
        )

        # If target both entered and exited (full or partial), skip: we'd be getting in at bad odds (late).
        if has_buy and has_sell:
            logger.info(
                "Catch-up: skip asset %s... (target entered then sold; not mirroring late entry)",
                asset[:16],
            )
            continue

        # Only BUYs: net them and place one BUY
        if has_buy:
            net_notional = sum(
                float(t.get("size", 0)) * float(t.get("price", 0))
                for t in group
                if (t.get("side") or "").upper() == "BUY"
            )
            if net_notional < MIN_NET_NOTIONAL:
                continue
            last_trade = group[-1]
            condition_id = last_trade.get("conditionId") or last_trade.get("condition_id")
            last_price = float(last_trade.get("price", 0.5))
            my_notional = compute_my_notional(net_notional, my_value, target_value)
            worst_price = min(0.99, last_price * (1 + SLIPPAGE_FRACTION))
            logger.info("Catch-up: net BUY notional=%.2f -> our notional=%.2f (one order)", net_notional, my_notional)
            _place_one(
                asset,
                condition_id,
                "BUY",
                my_notional,
                worst_price,
                last_trade.get("title", ""),
                outcome=_normalize_outcome(last_trade),
            )

        # Only SELLs: skip (we weren't in the position when they sold; mirroring would be wrong)


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
