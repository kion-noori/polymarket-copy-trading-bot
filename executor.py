"""CLOB client: authenticate and place market orders to mirror target trades."""

from __future__ import annotations

import logging
import time
from typing import Any

try:
    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import (
        ApiCreds,
        AssetType,
        BalanceAllowanceParams,
        MarketOrderArgs,
        OrderType,
        PartialCreateOrderOptions,
    )
    from py_clob_client.order_builder.constants import BUY, SELL
except ImportError:
    ClobClient = None
    ApiCreds = None
    AssetType = None
    BalanceAllowanceParams = None
    MarketOrderArgs = None
    OrderType = None
    PartialCreateOrderOptions = None
    BUY = "BUY"
    SELL = "SELL"

from config import (
    CHAIN_ID,
    CLOB_HOST,
    FUNDER_ADDRESS,
    POLY_API_KEY,
    POLY_API_PASSPHRASE,
    POLY_API_SECRET,
    PRIVATE_KEY,
    SIGNATURE_TYPE,
)

logger = logging.getLogger(__name__)

# Retry on transient API errors
ORDER_RETRIES = 3
ORDER_RETRY_DELAY_SEC = 3
BUY_RETRY_PRICE_STEP_FRACTION = 0.03
BUY_MAX_RETRY_PRICE_MULTIPLIER = 1.15

_client: ClobClient | None = None


def _require_client_lib() -> None:
    if ClobClient is None:
        raise RuntimeError(
            "py-clob-client is not installed. Install requirements.txt before live trading."
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
        )
    return _client


def get_market_options(condition_id: str, token_id: str) -> PartialCreateOrderOptions:
    """Get tick_size and neg_risk for a market (required for order placement)."""
    _require_client_lib()
    client = get_client()
    try:
        market = client.get_market(condition_id)
        if isinstance(market, dict):
            tick = market.get("minimum_tick_size", "0.01")
            neg = market.get("neg_risk", False)
        else:
            tick = getattr(market, "minimum_tick_size", "0.01")
            neg = getattr(market, "neg_risk", False)
        tick_str = str(tick) if tick is not None else "0.01"
        return PartialCreateOrderOptions(tick_size=tick_str, neg_risk=bool(neg))
    except Exception as e:
        logger.warning("get_market failed for %s, using defaults: %s", condition_id[:16], e)
        try:
            tick = client.get_tick_size(token_id)
            neg = client.get_neg_risk(token_id)
            return PartialCreateOrderOptions(
                tick_size=str(tick) if tick is not None else "0.01",
                neg_risk=bool(neg),
            )
        except Exception:
            return PartialCreateOrderOptions(tick_size="0.01", neg_risk=False)


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
        if raw is None:
            return None
        return float(raw) / 1_000_000.0
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
    Returns 0.0 if credentials are missing or the call fails.
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
        if raw is None:
            return 0.0
        return float(raw) / 1_000_000.0
    except Exception as e:
        logger.debug("get_collateral_balance_usdc failed: %s", e)
        return 0.0


def get_current_price(token_id: str) -> float | None:
    """Return current midpoint price for a token (for mark-to-market). None if unavailable."""
    try:
        _require_client_lib()
        client = get_client()
        mid = client.get_midpoint(token_id)
        if mid is not None:
            return float(mid)
        price = client.get_price(token_id, "BUY")
        return float(price) if price is not None else None
    except Exception as e:
        logger.debug("get_current_price failed for %s: %s", token_id[:16] if token_id else "", e)
        return None


def get_bid_ask_prices(token_id: str) -> tuple[float | None, float | None]:
    """
    Return (best_bid, best_ask) using client price helpers.
    Assumes SELL price is current bid and BUY price is current ask.
    """
    try:
        _require_client_lib()
        client = get_client()
        best_bid = client.get_price(token_id, "SELL")
        best_ask = client.get_price(token_id, "BUY")
        bid = float(best_bid) if best_bid is not None else None
        ask = float(best_ask) if best_ask is not None else None
        return bid, ask
    except Exception as e:
        logger.debug("get_bid_ask_prices failed for %s: %s", token_id[:16] if token_id else "", e)
        return None, None


def place_market_order(
    token_id: str,
    condition_id: str,
    side: str,
    notional_usd: float,
    worst_price: float,
) -> dict[str, Any] | None:
    """
    Place a market order (FOK).
    - BUY: amount = notional_usd (dollars to spend), price = worst acceptable price (slippage).
    - SELL: amount = shares to sell (notional_usd / price ≈ shares), price = worst acceptable.
    Returns response dict with orderID, status, etc., or None on failure.
    """
    if notional_usd <= 0:
        logger.warning("place_market_order: notional_usd <= 0, skipping")
        return None
    _require_client_lib()
    options = get_market_options(condition_id, token_id)
    side_val = BUY if side.upper() == "BUY" else SELL
    client = get_client()
    last_err = None
    for attempt in range(ORDER_RETRIES):
        try:
            attempt_price = worst_price
            if side_val == BUY and attempt > 0:
                retry_multiplier = min(
                    1.0 + BUY_RETRY_PRICE_STEP_FRACTION * attempt,
                    BUY_MAX_RETRY_PRICE_MULTIPLIER,
                )
                attempt_price = min(0.99, worst_price * retry_multiplier)
            if side_val == BUY:
                amount = notional_usd
            else:
                amount = notional_usd / attempt_price if attempt_price > 0 else notional_usd
            order_args = MarketOrderArgs(
                token_id=token_id,
                amount=amount,
                side=side_val,
                price=attempt_price,
                order_type=OrderType.FOK,
            )
            signed = client.create_market_order(order_args, options=options)
            resp = client.post_order(signed, OrderType.FOK)
            if isinstance(resp, dict):
                return resp
            return {"orderID": getattr(resp, "orderID", ""), "status": getattr(resp, "status", "unknown")}
        except Exception as e:
            last_err = e
            logger.warning(
                "place_market_order attempt %s/%s failed at price %.4f: %s",
                attempt + 1,
                ORDER_RETRIES,
                attempt_price,
                e,
            )
            if attempt < ORDER_RETRIES - 1:
                time.sleep(ORDER_RETRY_DELAY_SEC)
    logger.exception("place_market_order failed after %s attempts: %s", ORDER_RETRIES, last_err)
    return None
