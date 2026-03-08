"""Load configuration from environment variables."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

# Chain and API
CLOB_HOST = os.getenv("CLOB_HOST", "https://clob.polymarket.com")
DATA_API_BASE = os.getenv("DATA_API_BASE", "https://data-api.polymarket.com")
CHAIN_ID = int(os.getenv("CHAIN_ID", "137"))

# Wallets and auth
TARGET_WALLET = os.getenv("TARGET_WALLET", "").strip()
FUNDER_ADDRESS = os.getenv("FUNDER_ADDRESS", "").strip()
PRIVATE_KEY = os.getenv("PRIVATE_KEY", "").strip()

# API credentials (L2)
POLY_API_KEY = os.getenv("POLY_API_KEY", "").strip()
POLY_API_SECRET = os.getenv("POLY_API_SECRET", "").strip()
POLY_API_PASSPHRASE = os.getenv("POLY_API_PASSPHRASE", "").strip()

# Polling
POLL_INTERVAL_SEC = max(10, int(os.getenv("POLL_INTERVAL_SEC", "45")))

# Sizing
MAX_PCT_PER_TRADE = float(os.getenv("MAX_PCT_PER_TRADE", "0.10"))
SIZE_MULTIPLIER = float(os.getenv("SIZE_MULTIPLIER", "1.0"))
MIN_NOTIONAL = float(os.getenv("MIN_NOTIONAL", "5.0"))
# Absolute max $ per trade (optional). 0 = no absolute cap, only % cap.
MAX_TRADE_USD = float(os.getenv("MAX_TRADE_USD", "0"))

# Safety: test mode logs what would be done without placing orders
TEST_MODE = os.getenv("TEST_MODE", "").strip().lower() in ("1", "true", "yes")

# CLOB client
SIGNATURE_TYPE = int(os.getenv("SIGNATURE_TYPE", "2"))


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
    return errors
