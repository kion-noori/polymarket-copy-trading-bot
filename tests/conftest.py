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
    monkeypatch.setattr(notifier, "ALERT_WEBHOOK_URL", "")
    import httpx
    monkeypatch.setattr(order_journal, "JOURNAL_FILE", tmp_path / "orders.sqlite3")
    def offline(*args, **kwargs):
        raise AssertionError("Unexpected network call in offline test")
    monkeypatch.setattr(requests.sessions.Session, "request", offline)
    monkeypatch.setattr(httpx.Client, "send", offline)
