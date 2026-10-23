"""Tests for _place_one success vs mark_seen behavior."""

from unittest.mock import patch

import pytest


@pytest.fixture
def main_mod(monkeypatch, tmp_path):
    monkeypatch.setenv("TARGET_WALLET", "0x" + "1" * 40)
    monkeypatch.setenv("FUNDER_ADDRESS", "0x" + "2" * 40)
    monkeypatch.setenv("TEST_MODE", "0")
    monkeypatch.setenv("PRIVATE_KEY", "0x" + "a" * 64)
    monkeypatch.setenv("POLY_API_KEY", "k")
    monkeypatch.setenv("POLY_API_SECRET", "s")
    monkeypatch.setenv("POLY_API_PASSPHRASE", "p")
    import importlib

    import config
    import main

    importlib.reload(config)
    importlib.reload(main)
    monkeypatch.setattr(main, "LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setattr(main, "get_order_execution", lambda *args: ("pending", []))
    monkeypatch.setattr(main, 'get_collateral_balance_usdc', lambda: 1000.0)
    return main


def test_place_one_live_success_returns_true(main_mod):
    with patch.object(main_mod, "place_market_order", return_value={"orderID": "abc", "status": "ok"}):
        assert (
            main_mod._place_one(
                "token",
                "cond",
                "BUY",
                10.0,
                0.55,
                "Market",
                "YES",
            )
            is True
        )


def test_place_one_live_failure_returns_false(main_mod):
    with patch.object(main_mod, "place_market_order", return_value={"success": False, "status": "rejected"}):
        assert (
            main_mod._place_one(
                "token",
                "cond",
                "BUY",
                10.0,
                0.55,
                "Market",
                "YES",
            )
            is False
        )


def test_place_one_test_mode_returns_true_without_order(main_mod, monkeypatch):
    monkeypatch.setenv("TEST_MODE", "1")
    import importlib

    import config
    import main

    importlib.reload(config)
    importlib.reload(main)
    monkeypatch.setattr(main, "LOG_DIR", str(main_mod.journal.JOURNAL_FILE.parent / "logs"))
    with patch.object(main, "place_market_order") as m:
        assert main._place_one("t", "c", "BUY", 10.0, 0.5, "M", "YES") is True
        m.assert_not_called()


def test_place_one_passes_custom_order_type(main_mod):
    with patch.object(main_mod, "place_market_order", return_value={"orderID": "abc", "status": "ok"}) as mocked:
        assert main_mod._place_one("token", "cond", "SELL", 1.0, 0.25, "Market", "YES", order_type="FAK") is True
        mocked.assert_called_once()
        assert mocked.call_args.kwargs["order_type"] == "FAK"
