"""Pytest configuration."""

import os
import sys
from unittest.mock import patch

# Test collection itself imports config/executor. Prevent a checkout's real
# .env (including credentials and startup-liquidation flags) from participating.
_dotenv_patch = patch('dotenv.load_dotenv', return_value=False)
_dotenv_patch.start()


def pytest_unconfigure(config):
    _dotenv_patch.stop()

# Ensure repo root is on path when running `pytest` from project root.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


import pytest

@pytest.fixture(autouse=True)
def isolated_io(tmp_path, monkeypatch):
    """Unit tests never access the operator's journal, logs or network."""
    for name, value in {'RECONCILE_ON_START': '0', 'CASH_RESERVE_FRACTION': '0',
                        'CASH_RESERVE_USD': '0', 'CASH_DEFERRAL_SEC': '300',
                        'MANUAL_EXIT_PROTECTION': '1'}.items():
        monkeypatch.setenv(name, value)
    import order_journal
    import requests
    import notifier
    import copy_controls
    import manual_guard
    import market_support
    monkeypatch.setattr(notifier, "ALERT_WEBHOOK_URL", "")
    import httpx
    monkeypatch.setattr(order_journal, "JOURNAL_FILE", tmp_path / "orders.sqlite3")
    monkeypatch.setattr(copy_controls, 'CONTROL_FILE', tmp_path / 'controls.sqlite3')
    monkeypatch.setattr(manual_guard, 'fetch_account_trades', lambda *args: [])
    monkeypatch.setattr(market_support, 'refresh_registry', lambda *args: None)
    def offline(*args, **kwargs):
        raise AssertionError("Unexpected network call in offline test")
    monkeypatch.setattr(requests.sessions.Session, "request", offline)
    monkeypatch.setattr(httpx.Client, "send", offline)
