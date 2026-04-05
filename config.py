"""Load configuration from environment variables."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

# Chain and API
CLOB_HOST = os.getenv("CLOB_HOST", "https://clob.polymarket.com")
DATA_API_BASE = os.getenv("DATA_API_BASE", "https://data-api.polymarket.com")
try:
    CHAIN_ID = int(os.getenv("CHAIN_ID", "137"))
except (TypeError, ValueError):
    CHAIN_ID = 137


def _clean_hex_key(val: str) -> str:
    """Strip whitespace, quotes, and any non-hex characters that might be pasted by mistake."""
    if not val:
        return ""
    s = val.strip().strip('"').strip("'").replace(" ", "").replace("\n", "").replace("\r", "")
    # Keep only 0x prefix and hex digits
    if s.startswith("0x"):
        return "0x" + "".join(c for c in s[2:] if c in "0123456789abcdefABCDEF")
    return "".join(c for c in s if c in "0123456789abcdefABCDEF")

# Wallets and auth
TARGET_WALLET = os.getenv("TARGET_WALLET", "").strip()
FUNDER_ADDRESS = os.getenv("FUNDER_ADDRESS", "").strip()
PRIVATE_KEY = _clean_hex_key(os.getenv("PRIVATE_KEY", ""))

# API credentials (L2)
POLY_API_KEY = os.getenv("POLY_API_KEY", "").strip()
POLY_API_SECRET = os.getenv("POLY_API_SECRET", "").strip()
POLY_API_PASSPHRASE = os.getenv("POLY_API_PASSPHRASE", "").strip()

# Polling
try:
    POLL_INTERVAL_SEC = max(10, int(os.getenv("POLL_INTERVAL_SEC", "45")))
except (TypeError, ValueError):
    POLL_INTERVAL_SEC = 45
try:
    RECENT_TRADES_PAGE_SIZE = max(10, int(os.getenv("RECENT_TRADES_PAGE_SIZE", "100")))
except (TypeError, ValueError):
    RECENT_TRADES_PAGE_SIZE = 100
try:
    RECENT_TRADES_MAX_PAGES = max(1, int(os.getenv("RECENT_TRADES_MAX_PAGES", "5")))
except (TypeError, ValueError):
    RECENT_TRADES_MAX_PAGES = 5

STARTUP_MODE = os.getenv("STARTUP_MODE", "resume").strip().lower()
if STARTUP_MODE not in ("resume", "live_safe"):
    STARTUP_MODE = "resume"

# Sizing


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default

MAX_PCT_PER_TRADE = _float_env("MAX_PCT_PER_TRADE", 0.10)
SIZE_MULTIPLIER = _float_env("SIZE_MULTIPLIER", 1.0)
MIN_NOTIONAL = _float_env("MIN_NOTIONAL", 5.0)
MAX_TRADE_USD = _float_env("MAX_TRADE_USD", 0)  # 0 = no absolute cap, only % cap

# BUY: worst acceptable price vs target fill (FOK limit). Default 2% — tight entries.
SLIPPAGE_FRACTION = _float_env("SLIPPAGE_FRACTION", 0.02)
# SELL: default very wide so we follow target exits even if market dropped (floor 0.01).
SELL_SLIPPAGE_FRACTION = _float_env("SELL_SLIPPAGE_FRACTION", 0.99)
MAX_BUY_PRICE = _float_env("MAX_BUY_PRICE", 0.95)
MAX_SPREAD_FRACTION = _float_env("MAX_SPREAD_FRACTION", 0.12)

# Live CLOB: after this many failed posts (no orderID) for the same tx(es), mark seen and stop retrying. 0 = unlimited.
try:
    MAX_LIVE_ORDER_ATTEMPTS = max(0, int(os.getenv("MAX_LIVE_ORDER_ATTEMPTS", "10")))
except (TypeError, ValueError):
    MAX_LIVE_ORDER_ATTEMPTS = 10

# Min notional: "floor" = bump tiny sizes up to MIN_NOTIONAL (legacy). "skip" = skip trade if below floor.
_MIN_NOTIONAL_MODE_RAW = os.getenv("MIN_NOTIONAL_MODE", "floor").strip().lower()
MIN_NOTIONAL_MODE = (
    _MIN_NOTIONAL_MODE_RAW if _MIN_NOTIONAL_MODE_RAW in ("floor", "skip") else "floor"
)

# If True (default), do not mirror when target portfolio value is 0/unknown — avoids blind MIN_NOTIONAL sizing.
def _bool_env(name: str, default: bool) -> bool:
    v = os.getenv(name, "").strip().lower()
    if not v:
        return default
    return v in ("1", "true", "yes", "on")

SKIP_COPY_WHEN_TARGET_VALUE_UNKNOWN = _bool_env("SKIP_COPY_WHEN_TARGET_VALUE_UNKNOWN", True)

# Price guard: extra CLOB midpoint vs target's fill; skip if market moved too much against you.
PRICE_GUARD_ENABLED = _bool_env("PRICE_GUARD_ENABLED", True)
# If False (default): do not skip SELLs on price guard — prioritize exiting when target exits.
PRICE_GUARD_APPLY_TO_SELL = _bool_env("PRICE_GUARD_APPLY_TO_SELL", False)

# Before mirroring a SELL, check CLOB conditional token balance; skip + mark seen if we can't cover size.
REQUIRE_CLOB_BALANCE_FOR_SELL = _bool_env("REQUIRE_CLOB_BALANCE_FOR_SELL", True)
# e.g. 0.08 = 8% worse than target's price → skip (BUY: pay more; SELL: receive less, when enabled)
MAX_PRICE_DEVIATION_VS_TARGET = _float_env("MAX_PRICE_DEVIATION_VS_TARGET", 0.08)

# Skip mirrors when trade is older than N seconds (0 = disabled). Reduces late entries after downtime.
try:
    MAX_TRADE_AGE_SEC = max(0, int(os.getenv("MAX_TRADE_AGE_SEC", "3600")))
except (TypeError, ValueError):
    MAX_TRADE_AGE_SEC = 3600

# Safety: test mode logs what would be done without placing orders
TEST_MODE = os.getenv("TEST_MODE", "").strip().lower() in ("1", "true", "yes")
ALERT_WEBHOOK_URL = os.getenv("ALERT_WEBHOOK_URL", "").strip()
try:
    ALERT_MIN_INTERVAL_SEC = max(0, int(os.getenv("ALERT_MIN_INTERVAL_SEC", "300")))
except (TypeError, ValueError):
    ALERT_MIN_INTERVAL_SEC = 300

# CLOB client
try:
    SIGNATURE_TYPE = int(os.getenv("SIGNATURE_TYPE", "2"))
except (TypeError, ValueError):
    SIGNATURE_TYPE = 2


@dataclass
class SizingParams:
    max_pct_per_trade: float
    size_multiplier: float
    min_notional: float
    max_trade_usd: float


def get_sizing_params() -> SizingParams:
    return SizingParams(
        max_pct_per_trade=MAX_PCT_PER_TRADE,
        size_multiplier=SIZE_MULTIPLIER,
        min_notional=MIN_NOTIONAL,
        max_trade_usd=MAX_TRADE_USD,
    )


def validate_config() -> list[str]:
    """Return list of validation errors (empty if valid)."""
    errors = []
    if not TARGET_WALLET or not TARGET_WALLET.startswith("0x"):
        errors.append("TARGET_WALLET must be set to a 0x-prefixed address")
    if not FUNDER_ADDRESS or not FUNDER_ADDRESS.startswith("0x"):
        errors.append("FUNDER_ADDRESS must be set to your Polymarket wallet (0x...)")
    if not TEST_MODE:
        if not PRIVATE_KEY or not PRIVATE_KEY.startswith("0x"):
            errors.append("PRIVATE_KEY must be set (0x-prefixed)")
        if not all([POLY_API_KEY, POLY_API_SECRET, POLY_API_PASSPHRASE]):
            errors.append("POLY_API_KEY, POLY_API_SECRET, POLY_API_PASSPHRASE must all be set")
    if not (0 < MAX_PCT_PER_TRADE <= 1):
        errors.append("MAX_PCT_PER_TRADE must be in (0, 1]")
    if not (0 < SIZE_MULTIPLIER <= 2):
        errors.append("SIZE_MULTIPLIER should be in (0, 2]")
    if MIN_NOTIONAL < 0:
        errors.append("MIN_NOTIONAL must be >= 0")
    if MAX_TRADE_USD < 0:
        errors.append("MAX_TRADE_USD must be >= 0")
    if not (0 <= MAX_PRICE_DEVIATION_VS_TARGET <= 0.99):
        errors.append("MAX_PRICE_DEVIATION_VS_TARGET should be in [0, 0.99]")
    if not (0 < SLIPPAGE_FRACTION < 0.5):
        errors.append("SLIPPAGE_FRACTION should be in (0, 0.5)")
    if not (0 < SELL_SLIPPAGE_FRACTION <= 1.0):
        errors.append("SELL_SLIPPAGE_FRACTION should be in (0, 1]")
    if not (0 < MAX_BUY_PRICE <= 0.99):
        errors.append("MAX_BUY_PRICE should be in (0, 0.99]")
    if not (0 <= MAX_SPREAD_FRACTION <= 1.0):
        errors.append("MAX_SPREAD_FRACTION should be in [0, 1]")
    if _MIN_NOTIONAL_MODE_RAW not in ("", "floor", "skip"):
        errors.append("MIN_NOTIONAL_MODE must be 'floor' or 'skip'")
    if STARTUP_MODE not in ("resume", "live_safe"):
        errors.append("STARTUP_MODE must be 'resume' or 'live_safe'")
    return errors
