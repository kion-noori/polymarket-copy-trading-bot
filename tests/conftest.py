"""Pytest configuration."""

import os
import sys

# Ensure repo root is on path when running `pytest` from project root.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


import pytest

@pytest.fixture(autouse=True)
def isolated_io(tmp_path, monkeypatch):
    """Unit tests never access the operator's journal, logs or network."""
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
