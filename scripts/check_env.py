"""Quick local sanity-check for .env wallet/trading configuration."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config

ADDR_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
PRIV_RE = re.compile(r"^0x[a-fA-F0-9]{64}$")


def _ok(flag: bool) -> str:
    return "OK" if flag else "CHECK"


def main() -> int:
    errors = config.validate_config()

    print(f"TARGET_WALLET: {_ok(bool(ADDR_RE.fullmatch(config.TARGET_WALLET)))}")
    print(f"FUNDER_ADDRESS: {_ok(bool(ADDR_RE.fullmatch(config.FUNDER_ADDRESS)))}")
    print(f"PRIVATE_KEY format: {_ok(bool(PRIV_RE.fullmatch(config.PRIVATE_KEY)))}")
    print(f"API credentials present: {_ok(all([config.POLY_API_KEY, config.POLY_API_SECRET, config.POLY_API_PASSPHRASE]))}")
    print(f"POLL_INTERVAL_SEC: {config.POLL_INTERVAL_SEC}")
    print(f"RECENT_WINDOW: {config.RECENT_TRADES_PAGE_SIZE} x {config.RECENT_TRADES_MAX_PAGES}")
    print(f"STARTUP_MODE: {config.STARTUP_MODE}")
    print(f"TEST_MODE: {config.TEST_MODE}")
    print(f"SIGNATURE_TYPE: {config.SIGNATURE_TYPE}")

    if config.SIGNATURE_TYPE == 2:
        print("Note: SIGNATURE_TYPE=2 usually means your signing EOA and Polymarket funder address may be different.")

    if errors:
        print("\nValidation errors:")
        for err in errors:
            print(f"- {err}")
        return 1

    print("\nConfig format checks passed.")
    print("Final pre-live checklist:")
    print("- Confirm FUNDER_ADDRESS exactly matches polymarket.com/settings")
    print("- Run TEST_MODE=1 first and confirm balance/trade logs look sane")
    print("- Confirm your VPS region is not geoblocked before TEST_MODE=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
