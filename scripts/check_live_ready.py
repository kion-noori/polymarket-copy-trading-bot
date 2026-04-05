"""Safe live-readiness checks for Polymarket trading configuration."""

from __future__ import annotations

import sys
from pathlib import Path

from eth_account import Account

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config
from executor import get_client, get_collateral_balance_usdc


def _line(label: str, ok: bool, detail: str = "") -> None:
    status = "OK" if ok else "CHECK"
    suffix = f" | {detail}" if detail else ""
    print(f"{label}: {status}{suffix}")


def main() -> int:
    errors = config.validate_config()
    if errors:
        print("Config validation errors:")
        for err in errors:
            print(f"- {err}")
        return 1

    print("Local checks")
    print("------------")
    signer = Account.from_key(config.PRIVATE_KEY).address
    _line("Private key parses", True, f"signer={signer}")

    same_addr = signer.lower() == config.FUNDER_ADDRESS.lower()
    if config.SIGNATURE_TYPE == 2:
        _line(
            "Signer vs funder",
            True,
            "SIGNATURE_TYPE=2, so different signer/funder can be normal"
            if not same_addr
            else "signer matches funder",
        )
    else:
        _line("Signer matches funder", same_addr, "expected for non-proxy setups")

    print("\nAuthenticated client checks")
    print("---------------------------")
    try:
        client = get_client()
        _line("Client init", True, f"host={config.CLOB_HOST}")
    except Exception as e:
        _line("Client init", False, str(e))
        return 1

    try:
        api_keys = client.get_api_keys()
        count = len(api_keys) if isinstance(api_keys, list) else 1
        _line("API auth", True, f"retrieved {count} API key record(s)")
    except Exception as e:
        _line("API auth", False, str(e))
        return 1

    try:
        balance = get_collateral_balance_usdc()
        _line("Collateral balance read", True, f"${balance:.2f}")
    except Exception as e:
        _line("Collateral balance read", False, str(e))
        return 1

    print("\nResult")
    print("------")
    print("Safe live-readiness checks passed.")
    print("This does not place any orders.")
    print("Recommended next step: keep TEST_MODE=1, run the bot, verify logs, then do one tiny live test.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
