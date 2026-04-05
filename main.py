"""
Polymarket copy-trading bot: watch a target wallet and mirror their trades with proportional sizing.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import UTC, datetime

from config import (
    ALERT_WEBHOOK_URL,
    FUNDER_ADDRESS,
    MAX_LIVE_ORDER_ATTEMPTS,
    MAX_BUY_PRICE,
    MAX_PRICE_DEVIATION_VS_TARGET,
    MAX_SPREAD_FRACTION,
    MAX_TRADE_AGE_SEC,
    POLL_INTERVAL_SEC,
    PRICE_GUARD_APPLY_TO_SELL,
    PRICE_GUARD_ENABLED,
    RECENT_TRADES_MAX_PAGES,
    RECENT_TRADES_PAGE_SIZE,
    REQUIRE_CLOB_BALANCE_FOR_SELL,
    SELL_SLIPPAGE_FRACTION,
    SKIP_COPY_WHEN_TARGET_VALUE_UNKNOWN,
    SLIPPAGE_FRACTION,
    STARTUP_MODE,
    TARGET_WALLET,
    TEST_MODE,
    validate_config,
)
from data_api import get_trades, get_portfolio_value
from executor import (
    get_bid_ask_prices,
    get_collateral_balance_usdc,
    get_conditional_token_balance_shares,
    get_current_price,
    place_market_order,
)
from notifier import send_alert
from risk_guards import is_group_too_old, is_trade_too_old, price_guard_allows, vwap_price_buy_group
from sizing import compute_my_notional
from state import is_already_seen, mark_seen, mark_seen_batch, note_live_order_failure

LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"
TRADES_LOG_HEADER = "timestamp,side,outcome,market_title,notional_usd,price,shares,mode"


def _utc_now() -> datetime:
    """Timezone-aware UTC now for logs and filenames."""
    return datetime.now(UTC)


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
    ts = _utc_now().strftime("%Y-%m-%d %H:%M:%S")
    raw = (title or "").strip()
    safe_title = raw.replace('"', '""')
    if "," in safe_title or "\n" in safe_title or '"' in raw:
        safe_title = f'"{safe_title}"'
    line = f"{ts},{side},{outcome},{safe_title},{notional_usd:.2f},{price:.4f},{shares:.4f},{mode}\n"
    log_path = os.path.join(LOG_DIR, f"trades_{_utc_now().strftime('%Y-%m-%d')}.csv")
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
    log_file = os.path.join(LOG_DIR, f"bot_{_utc_now().strftime('%Y-%m-%d')}.log")
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

# Float tolerance when comparing CLOB share balance vs sell size
SELL_SHARES_EPSILON = 1e-6


def _skip_sell_insufficient_shares(
    token_id: str,
    my_notional: float,
    worst_price: float,
) -> tuple[bool, float | None, float]:
    """
    If we can read CLOB balance and it's below shares needed for this SELL, return (True, balance, need).
    If balance unknown (None), return (False, None, need) — caller attempts sell anyway.
    """
    if worst_price <= 0:
        return False, None, 0.0
    need = my_notional / worst_price
    if need <= 0:
        return False, None, need
    bal = get_conditional_token_balance_shares(token_id)
    if bal is None:
        return False, None, need
    if bal + SELL_SHARES_EPSILON < need:
        return True, bal, need
    return False, bal, need

# Theoretical portfolio (test mode only): simulate $500 and track PnL of "would have" trades
THEORETICAL_START = 500.0
_theoretical_cash = THEORETICAL_START
_theoretical_positions: dict[str, dict] = {}  # token_id -> {"shares": float, "entry_price": float}

# Throttle balance logging when idle: log every N-th poll if no new trades to mirror
_poll_count = 0
IDLE_LOG_EVERY_N_POLLS = 10
_startup_window_initialized = False


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


def _get_recent_trades() -> list[dict]:
    """
    Fetch a wider recent window than a single page so we can detect "bought then sold"
    catch-up batches and avoid entering trades that are already closed.
    """
    all_trades: list[dict] = []
    for page in range(RECENT_TRADES_MAX_PAGES):
        batch = get_trades(limit=RECENT_TRADES_PAGE_SIZE, offset=page * RECENT_TRADES_PAGE_SIZE)
        if not batch:
            break
        all_trades.extend(batch)
    return sorted(all_trades, key=lambda t: t.get("timestamp") or 0)


def _place_one(
    asset: str,
    condition_id: str,
    side: str,
    my_notional: float,
    worst_price: float,
    title: str,
    outcome: str = "?",
) -> bool:
    """
    Place a single order (or log in test mode).
    Returns True if the mirror should be treated as done for state purposes:
    test mode always True after simulation; live mode True only when order returns orderID.
    """
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
    if TEST_MODE:
        _append_trade_log(side, outcome, title or "", my_notional, worst_price, mode="test")
        _apply_theoretical_trade(asset, side, my_notional, worst_price)
        logger.info("[TEST MODE] No order placed (simulation only)")
        return True
    resp = place_market_order(
        token_id=asset,
        condition_id=condition_id,
        side=side,
        notional_usd=my_notional,
        worst_price=worst_price,
    )
    if resp and resp.get("orderID"):
        _append_trade_log(side, outcome, title or "", my_notional, worst_price, mode="live")
        logger.info("Order placed: orderID=%s status=%s", resp.get("orderID"), resp.get("status"))
        return True
    logger.error("Order failed or no orderID: %s — will retry same trade on next poll (not marked seen)", resp)
    return False


def _pre_trade_allows(
    asset: str,
    side: str,
    reference_price: float,
    trade_or_group: dict | list,
) -> tuple[bool, str]:
    """
    Max-age and price-vs-target checks. trade_or_group is one trade dict or list for catch-up.
    Extra API: get_current_price when PRICE_GUARD_ENABLED.
    """
    if isinstance(trade_or_group, list):
        if is_group_too_old(trade_or_group, float(MAX_TRADE_AGE_SEC)):
            return False, f"group older than MAX_TRADE_AGE_SEC ({MAX_TRADE_AGE_SEC}s)"
    else:
        if is_trade_too_old(trade_or_group, float(MAX_TRADE_AGE_SEC)):
            return False, f"trade older than MAX_TRADE_AGE_SEC ({MAX_TRADE_AGE_SEC}s)"
    current: float | None = None
    need_current_price = side.upper() == "BUY" or (
        PRICE_GUARD_ENABLED
        and MAX_PRICE_DEVIATION_VS_TARGET > 0
        and (side.upper() != "SELL" or PRICE_GUARD_APPLY_TO_SELL)
    )
    if need_current_price:
        current = get_current_price(asset)
    if side.upper() == "BUY":
        effective_price = current if current is not None else reference_price
        if effective_price >= MAX_BUY_PRICE:
            return False, f"buy price {effective_price:.4f} >= MAX_BUY_PRICE ({MAX_BUY_PRICE:.4f})"
        if MAX_SPREAD_FRACTION > 0:
            best_bid, best_ask = get_bid_ask_prices(asset)
            if (
                best_bid is not None
                and best_ask is not None
                and best_bid > 0
                and best_ask >= best_bid
            ):
                mid = (best_bid + best_ask) / 2.0
                if mid > 0:
                    spread_frac = (best_ask - best_bid) / mid
                    if spread_frac > MAX_SPREAD_FRACTION:
                        return False, f"spread {spread_frac:.1%} > MAX_SPREAD_FRACTION ({MAX_SPREAD_FRACTION:.1%})"
    if (
        PRICE_GUARD_ENABLED
        and MAX_PRICE_DEVIATION_VS_TARGET > 0
        and (side.upper() != "SELL" or PRICE_GUARD_APPLY_TO_SELL)
    ):
        ok, detail = price_guard_allows(
            side, reference_price, current, MAX_PRICE_DEVIATION_VS_TARGET
        )
        if not ok:
            return False, detail
    return True, ""


def _log_portfolio_line(
    my_value: float,
    target_value: float,
    raw_bankroll: float,
    position_value: float,
    cash_usdc: float,
    idle_suffix: str = "",
) -> None:
    """Log portfolio; when we have real bankroll data, show positions + CLOB cash breakdown."""
    tail = idle_suffix
    if raw_bankroll > 0:
        logger.info(
            "Portfolio: me=$%.2f (positions $%.2f + CLOB cash $%.2f)%s | target=$%.2f",
            my_value,
            position_value,
            cash_usdc,
            tail,
            target_value,
        )
    else:
        logger.info("Portfolio: me=$%.2f%s | target=$%.2f", my_value, tail, target_value)


def run_once() -> None:
    """Poll target trades, mirror any new ones with proportional sizing."""
    global _poll_count, _startup_window_initialized
    _poll_count += 1

    trades = _get_recent_trades()

    # Data API /value = mark-to-market of open positions only (0 if no positions).
    # CLOB collateral = USDC cash available for trading — both matter for bankroll sizing.
    position_value = get_portfolio_value(FUNDER_ADDRESS)
    cash_usdc = get_collateral_balance_usdc()
    raw_bankroll = position_value + cash_usdc
    my_value = raw_bankroll
    target_value = get_portfolio_value(TARGET_WALLET)
    if my_value <= 0 and TEST_MODE:
        my_value = 500.0  # placeholder for sizing and theoretical PnL
        if _poll_count == 1:
            logger.info("Test mode: using placeholder portfolio value $500 (actual value 0 or unknown)")

    if not trades:
        # No trades at all: log balance only every N-th poll to avoid log spam
        if _poll_count % IDLE_LOG_EVERY_N_POLLS == 1:
            _log_portfolio_line(my_value, target_value, raw_bankroll, position_value, cash_usdc, " (no new trades)")
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

    if STARTUP_MODE == "live_safe" and not _startup_window_initialized:
        boot_hashes = [
            t.get("transactionHash") or t.get("transaction_hash")
            for group in unseen_by_asset.values()
            for t in group
            if (t.get("transactionHash") or t.get("transaction_hash"))
        ]
        if boot_hashes:
            mark_seen_batch(boot_hashes)
            logger.info(
                "Startup live-safe mode: marked %s visible trade(s) seen; only future trades will be mirrored",
                len(boot_hashes),
            )
            send_alert(
                "startup_live_safe",
                f"Startup live-safe mode skipped {len(boot_hashes)} visible trade(s); bot will mirror only new trades.",
            )
        _startup_window_initialized = True
        return
    _startup_window_initialized = True

    # When we have new trades to mirror, always log balance. When idle (all seen), only every N-th poll.
    should_log_balance = len(unseen_by_asset) > 0 or _poll_count % IDLE_LOG_EVERY_N_POLLS == 1
    if should_log_balance:
        _log_portfolio_line(my_value, target_value, raw_bankroll, position_value, cash_usdc)
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
            if my_notional <= 0:
                logger.info(
                    "Skip mirror (size=0): asset=%s... | target_value=$%.2f | "
                    "set SKIP_COPY_WHEN_TARGET_VALUE_UNKNOWN=0 or MIN_NOTIONAL_MODE=floor if unintended",
                    asset[:16],
                    target_value,
                )
                mark_seen(tx_hash)
                continue
            if side == "BUY":
                worst_price = min(0.99, price * (1 + SLIPPAGE_FRACTION))
            else:
                worst_price = max(0.01, price * (1 - SELL_SLIPPAGE_FRACTION))
            ok, reason = _pre_trade_allows(asset, side, price, trade)
            if not ok:
                logger.info(
                    "Skip mirror (%s): %s | %s",
                    reason,
                    side,
                    ((trade.get("title") or "").strip() or "Unknown")[:50],
                )
                mark_seen(tx_hash)
                continue
            if (
                side == "SELL"
                and not TEST_MODE
                and REQUIRE_CLOB_BALANCE_FOR_SELL
            ):
                skip_sell, have_shares, need_shares = _skip_sell_insufficient_shares(
                    asset, my_notional, worst_price
                )
                if skip_sell:
                    logger.info(
                        "Skip SELL mirror (no CLOB position): have %.6f shares, need ~%.6f | %s | tx %s...",
                        have_shares if have_shares is not None else 0.0,
                        need_shares,
                        ((trade.get("title") or "").strip() or "Unknown")[:50],
                        (tx_hash or "")[:14],
                    )
                    mark_seen(tx_hash)
                    continue
                if have_shares is None:
                    logger.warning(
                        "Could not read CLOB balance for SELL; attempting order anyway | token=%s...",
                        asset[:16],
                    )
            if _place_one(
                asset,
                condition_id,
                side,
                my_notional,
                worst_price,
                trade.get("title", ""),
                outcome=_normalize_outcome(trade),
            ):
                mark_seen(tx_hash)
            elif MAX_LIVE_ORDER_ATTEMPTS > 0 and note_live_order_failure(
                [tx_hash], MAX_LIVE_ORDER_ATTEMPTS
            ):
                logger.warning(
                    "Giving up after %s failed live orders for tx %s...; marking seen (copy manually if needed)",
                    MAX_LIVE_ORDER_ATTEMPTS,
                    (tx_hash or "")[:18],
                )
                send_alert(
                    "live_order_give_up",
                    f"Giving up after {MAX_LIVE_ORDER_ATTEMPTS} failed live orders for tx {(tx_hash or '')[:18]}...",
                )
                mark_seen(tx_hash)
            continue

        # Multiple trades for same asset (catching up)
        has_buy = any((t.get("side") or "").upper() == "BUY" for t in group)
        has_sell = any((t.get("side") or "").upper() == "SELL" for t in group)
        group_hashes = [
            h
            for h in (
                t.get("transactionHash") or t.get("transaction_hash") for t in group
            )
            if h
        ]

        # If target both entered and exited (full or partial), skip: we'd be getting in at bad odds (late).
        if has_buy and has_sell:
            mark_seen_batch(group_hashes)
            logger.info(
                "Catch-up: skip asset %s... (target entered then sold; not mirroring late entry)",
                asset[:16],
            )
            continue

        # Only BUYs: net them and place one BUY (mark batch only after success or intentional skip)
        if has_buy:
            net_notional = sum(
                float(t.get("size", 0)) * float(t.get("price", 0))
                for t in group
                if (t.get("side") or "").upper() == "BUY"
            )
            if net_notional < MIN_NET_NOTIONAL:
                mark_seen_batch(group_hashes)
                continue
            last_trade = group[-1]
            condition_id = last_trade.get("conditionId") or last_trade.get("condition_id")
            last_price = float(last_trade.get("price", 0.5))
            my_notional = compute_my_notional(net_notional, my_value, target_value)
            if my_notional <= 0:
                logger.info(
                    "Catch-up skip (size=0): asset=%s... | target_value=$%.2f",
                    asset[:16],
                    target_value,
                )
                mark_seen_batch(group_hashes)
                continue
            ref_for_guard = vwap_price_buy_group(group) or last_price
            ok, reason = _pre_trade_allows(asset, "BUY", ref_for_guard, group)
            if not ok:
                logger.info(
                    "Catch-up skip (%s): BUY net=$%.2f | %s",
                    reason,
                    net_notional,
                    ((last_trade.get("title") or "").strip() or "Unknown")[:50],
                )
                mark_seen_batch(group_hashes)
                continue
            worst_price = min(0.99, last_price * (1 + SLIPPAGE_FRACTION))
            logger.info("Catch-up: net BUY notional=%.2f -> our notional=%.2f (one order)", net_notional, my_notional)
            if _place_one(
                asset,
                condition_id,
                "BUY",
                my_notional,
                worst_price,
                last_trade.get("title", ""),
                outcome=_normalize_outcome(last_trade),
            ):
                mark_seen_batch(group_hashes)
            elif MAX_LIVE_ORDER_ATTEMPTS > 0 and note_live_order_failure(
                group_hashes, MAX_LIVE_ORDER_ATTEMPTS
            ):
                logger.warning(
                    "Giving up catch-up after %s failed live orders; marking %s tx(es) seen",
                    MAX_LIVE_ORDER_ATTEMPTS,
                    len(group_hashes),
                )
                send_alert(
                    "catchup_order_give_up",
                    f"Giving up catch-up after {MAX_LIVE_ORDER_ATTEMPTS} failed live orders; marking {len(group_hashes)} tx(es) seen.",
                )
                mark_seen_batch(group_hashes)
            continue

        # Only SELLs: skip (we weren't in the position when they sold; mirroring would be wrong)
        if has_sell:
            mark_seen_batch(group_hashes)
            logger.info(
                "Catch-up: skip asset %s... (only SELLs; not mirroring without position)",
                asset[:16],
            )


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
    logger.info(
        "Risk: price_guard=%s (sell=%s) max_dev=%.0f%% | buy_slip=%.0f%% sell_slip=%.0f%% | max_trade_age=%ss | skip_unknown_target=%s | max_live_order_attempts=%s | require_clob_shares_for_sell=%s",
        PRICE_GUARD_ENABLED,
        PRICE_GUARD_APPLY_TO_SELL,
        100.0 * MAX_PRICE_DEVIATION_VS_TARGET,
        100.0 * SLIPPAGE_FRACTION,
        100.0 * SELL_SLIPPAGE_FRACTION,
        MAX_TRADE_AGE_SEC if MAX_TRADE_AGE_SEC > 0 else "off",
        SKIP_COPY_WHEN_TARGET_VALUE_UNKNOWN,
        MAX_LIVE_ORDER_ATTEMPTS if MAX_LIVE_ORDER_ATTEMPTS > 0 else "unlimited",
        REQUIRE_CLOB_BALANCE_FOR_SELL,
    )
    logger.info(
        "Late-entry controls: startup_mode=%s | recent_window=%sx%s | max_buy_price=%.2f | max_spread=%s | alerts=%s",
        STARTUP_MODE,
        RECENT_TRADES_MAX_PAGES,
        RECENT_TRADES_PAGE_SIZE,
        MAX_BUY_PRICE,
        f"{100.0 * MAX_SPREAD_FRACTION:.0f}%%" if MAX_SPREAD_FRACTION > 0 else "off",
        bool(ALERT_WEBHOOK_URL),
    )
    while True:
        try:
            run_once()
        except Exception as e:
            logger.exception("Poll cycle error: %s", e)
        time.sleep(POLL_INTERVAL_SEC)


if __name__ == "__main__":
    main()
