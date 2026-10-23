"""CLOB client: authenticate and place market orders to mirror target trades."""

from __future__ import annotations

import logging
import math
from decimal import Decimal, ROUND_FLOOR, ROUND_CEILING
from typing import Any

try:
    from py_clob_client_v2 import (
        ApiCreds,
        ClobClient,
        AssetType,
        BalanceAllowanceParams,
        MarketOrderArgs,
        OrderType,
        PartialCreateOrderOptions,
        Side,
    )
    BUY = Side.BUY
    SELL = Side.SELL
    USING_CLOB_V2 = True
except ImportError:
    ClobClient = ApiCreds = AssetType = BalanceAllowanceParams = None
    MarketOrderArgs = OrderType = PartialCreateOrderOptions = None
    BUY, SELL = "BUY", "SELL"
    USING_CLOB_V2 = False

from config import (
    CHAIN_ID,
    CLOB_HOST,
    FUNDER_ADDRESS,
    POLY_API_KEY,
    POLY_API_PASSPHRASE,
    POLY_API_SECRET,
    PRIVATE_KEY,
    SIGNATURE_TYPE,
    MAX_BUY_PRICE,
)

logger = logging.getLogger(__name__)

_client: ClobClient | None = None


def _require_client_lib() -> None:
    if ClobClient is None or not USING_CLOB_V2:
        raise RuntimeError(
            "No Polymarket CLOB client is installed. Install requirements.txt before live trading."
        )


def get_client() -> ClobClient:
    """Singleton CLOB client with L2 credentials."""
    global _client
    _require_client_lib()
    if _client is None:
        creds = ApiCreds(
            api_key=POLY_API_KEY,
            api_secret=POLY_API_SECRET,
            api_passphrase=POLY_API_PASSPHRASE,
        )
        _client = ClobClient(
            host=CLOB_HOST,
            chain_id=CHAIN_ID,
            key=PRIVATE_KEY,
            creds=creds,
            signature_type=SIGNATURE_TYPE,
            funder=FUNDER_ADDRESS,
            retry_on_error=False,
        )
        logger.info("Using Polymarket CLOB V2 client for live trading")
    return _client


def get_market_options(condition_id: str, token_id: str) -> PartialCreateOrderOptions:
    """Get tick_size and neg_risk for a market (required for order placement)."""
    _require_client_lib()
    client = get_client()
    info = client.get_clob_market_info(condition_id)
    if not isinstance(info, dict) or not info.get("mts"):
        raise ValueError("Market metadata unavailable; refusing guessed tick size")
    return PartialCreateOrderOptions(tick_size=str(info["mts"]), neg_risk=bool(info.get("nr", False)))


def get_conditional_token_balance_shares(token_id: str) -> float | None:
    """
    Outcome-token (conditional) balance on the CLOB for the funder, in **shares** (human float).
    API returns the same 1e6-scaled integer style as collateral; we divide by 1e6.

    Returns None if credentials missing or the call fails (caller may still attempt the sell).
    """
    if not token_id or not PRIVATE_KEY or not POLY_API_KEY:
        return None
    try:
        _require_client_lib()
        client = get_client()
        params = BalanceAllowanceParams(
            asset_type=AssetType.CONDITIONAL, token_id=token_id
        )
        resp = client.get_balance_allowance(params)
        if isinstance(resp, dict):
            raw = resp.get("balance")
        else:
            raw = getattr(resp, "balance", None)
        value = float(raw) / 1_000_000.0
        return value if math.isfinite(value) and value >= 0 else None
    except Exception as e:
        logger.debug(
            "get_conditional_token_balance_shares failed for %s: %s",
            token_id[:16] if token_id else "",
            e,
        )
        return None


def get_collateral_balance_usdc() -> float:
    """
    USDC collateral on the CLOB (cash available for new buys). Requires L2 auth.
    Balance is returned in micro-USDC (1e6); we convert to dollars.
    Returns 0.0 without credentials; raises if an authenticated read fails.
    """
    if not PRIVATE_KEY or not POLY_API_KEY:
        return 0.0
    try:
        _require_client_lib()
        client = get_client()
        params = BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
        resp = client.get_balance_allowance(params)
        if isinstance(resp, dict):
            raw = resp.get("balance")
        else:
            raw = getattr(resp, "balance", None)
        value = float(raw) / 1_000_000.0
        if not math.isfinite(value) or value < 0:
            raise ValueError("Invalid collateral balance")
        return value
    except Exception as e:
        raise RuntimeError("Collateral balance unavailable; execution deferred") from e


def _price(response, key: str) -> float | None:
    raw = response.get(key) if isinstance(response, dict) else response
    try:
        value = float(raw)
        return value if math.isfinite(value) and 0 < value < 1 else None
    except (TypeError, ValueError):
        return None


def get_current_price(token_id: str) -> float | None:
    """Parse SDK JSON responses; try the ask if midpoint is unavailable."""
    client = get_client()
    try:
        mid = _price(client.get_midpoint(token_id), "mid")
        if mid is not None:
            return mid
    except Exception:
        pass
    try:
        return _price(client.get_price(token_id, "SELL"), "price")
    except Exception:
        return None


def get_bid_ask_prices(token_id: str) -> tuple[float | None, float | None]:
    try:
        client = get_client()
        return (_price(client.get_price(token_id, "BUY"), "price"),
                _price(client.get_price(token_id, "SELL"), "price"))
    except Exception:
        return None, None


def place_market_order(
    token_id: str, condition_id: str, side: str, notional_usd: float,
    worst_price: float, order_type: str = "FAK", *, shares: float | None = None,
) -> dict[str, Any] | None:
    """One submission only. Unknown network outcomes must never be blindly retried.

    SELL quantity is explicit shares, independent of the minimum sale price.
    The caller writes a durable submission intent before entering this function.
    """
    if side not in ("BUY", "SELL") or order_type not in ("FAK", "FOK"):
        raise ValueError("Invalid side/order type")
    if not math.isfinite(notional_usd) or notional_usd <= 0:
        raise ValueError("Invalid order notional")
    if not math.isfinite(worst_price) or not 0 < worst_price < 1:
        raise ValueError("Invalid price limit")
    if side == "SELL" and (shares is None or not math.isfinite(shares) or shares <= 0):
        raise ValueError("SELL requires explicit positive shares")
    _require_client_lib()
    options = get_market_options(condition_id, token_id)
    tick = Decimal(str(options.tick_size))
    rounding = ROUND_FLOOR if side == "BUY" else ROUND_CEILING
    price = min(worst_price, MAX_BUY_PRICE) if side == "BUY" else worst_price
    price = float((Decimal(str(price)) / tick).to_integral_value(rounding=rounding) * tick)
    if not float(tick) <= price <= 1 - float(tick):
        raise ValueError("Price limit cannot be represented by market tick size")
    chosen = getattr(OrderType, order_type)
    args = MarketOrderArgs(token_id=token_id, amount=notional_usd if side == "BUY" else shares,
                           side=BUY if side == "BUY" else SELL, price=price, order_type=chosen,
                           user_usdc_balance=notional_usd if side == "BUY" else 0)
    client = get_client()
    # Signing failures happen before submission and are safe to retry next poll.
    signed = client.create_market_order(args, options=options)
    try:
        response = client.post_order(signed, chosen)
    except Exception as exc:
        status = getattr(exc, "status_code", None)
        if status in (400, 401, 403, 404, 422, 429):
            return {"success": False, "status": "rejected", "errorMsg": str(exc)}
        return {"status": "unknown", "errorMsg": "Order submission outcome unknown; manual reconciliation required"}
    return response if isinstance(response, dict) else {"status": "unknown"}


def get_order_execution(order_id: str, response: dict) -> tuple[str, list[dict]]:
    """Return pending/filled/unfilled and confirmed executions only.

    FAK may be partial. MATCHED/MINED are provisional; wait for CONFIRMED.
    """
    client = get_client()
    order = client.get_order(order_id)
    if not isinstance(order, dict):
        return "pending", []
    trade_ids = set(response.get("tradeIDs") or []) | set(order.get("associate_trades") or [])
    fills = []
    unresolved = False
    if trade_ids:
        from py_clob_client_v2 import TradeParams
        for trade_id in sorted(trade_ids):
            rows = client.get_trades(TradeParams(id=trade_id))
            trade = next((row for row in rows if row.get("id") == trade_id), None)
            if not trade:
                unresolved = True
                continue
            status = str(trade.get("status", "")).upper()
            if status == "FAILED":
                continue
            if status != "CONFIRMED":
                unresolved = True
                continue
            if trade.get("taker_order_id") == order_id:
                quantity, price = float(trade["size"]), float(trade["price"])
            else:
                maker = next((m for m in trade.get("maker_orders", []) if m.get("order_id") == order_id), None)
                if maker is None:
                    raise ValueError("Trade does not belong to submitted order")
                quantity, price = float(maker["matched_amount"]), float(maker["price"])
            if not math.isfinite(quantity) or not math.isfinite(price) or quantity <= 0 or not 0 < price <= 1:
                raise ValueError("Invalid confirmed fill")
            fills.append({"trade_id": trade_id, "shares": quantity, "price": price,
                          "notional_usd": quantity * price,
                          "timestamp": trade.get("match_time"),
                          "transaction_hash": trade.get("transaction_hash", "")})
    state = str(order.get("status", "")).upper()
    if unresolved or state in ("LIVE", "DELAYED", "PENDING"):
        return "pending", []
    if fills:
        return "filled", fills
    if trade_ids and not unresolved:
        # Every known execution failed definitively; no confirmed proceeds exist.
        return "unfilled", []
    if float(order.get("size_matched", 0) or 0) > 0:
        return "pending", []
    if state in ("CANCELED", "CANCELLED", "UNMATCHED", "INVALID", "EXPIRED"):
        return "unfilled", []
    return "pending", []
