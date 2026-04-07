"""SELL path: skip when CLOB conditional balance is below required shares."""

import pytest


@pytest.fixture
def main_mod(monkeypatch):
    monkeypatch.setenv("TARGET_WALLET", "0x" + "1" * 40)
    monkeypatch.setenv("FUNDER_ADDRESS", "0x" + "2" * 40)
    monkeypatch.setenv("TEST_MODE", "1")
    import importlib

    import config
    import main

    importlib.reload(config)
    importlib.reload(main)
    return main


def test_skip_sell_when_balance_below_need(main_mod, monkeypatch):
    monkeypatch.setattr(
        main_mod, "get_conditional_token_balance_shares", lambda tid: 5.0
    )
    skip, bal, need, executable = main_mod._skip_sell_insufficient_shares("tok", 100.0, 0.5)
    assert skip is False
    assert bal == 5.0
    assert need == 200.0
    assert executable == 2.5


def test_no_skip_when_balance_adequate(main_mod, monkeypatch):
    monkeypatch.setattr(
        main_mod, "get_conditional_token_balance_shares", lambda tid: 300.0
    )
    skip, bal, need, executable = main_mod._skip_sell_insufficient_shares("tok", 100.0, 0.5)
    assert skip is False
    assert bal == 300.0
    assert need == 200.0
    assert executable == 100.0


def test_no_skip_when_balance_unknown(main_mod, monkeypatch):
    monkeypatch.setattr(
        main_mod, "get_conditional_token_balance_shares", lambda tid: None
    )
    skip, bal, need, executable = main_mod._skip_sell_insufficient_shares("tok", 100.0, 0.5)
    assert skip is False
    assert bal is None
    assert need == 200.0
    assert executable == 100.0


def test_skip_sell_when_balance_effectively_zero(main_mod, monkeypatch):
    monkeypatch.setattr(
        main_mod, "get_conditional_token_balance_shares", lambda tid: 0.0
    )
    skip, bal, need, executable = main_mod._skip_sell_insufficient_shares("tok", 100.0, 0.5)
    assert skip is True
    assert bal == 0.0
    assert need == 200.0
    assert executable == 0.0


def test_is_dust_sell_thresholds(main_mod):
    assert main_mod._is_dust_sell(0.05, 0.5) is True
    assert main_mod._is_dust_sell(0.50, 100.0) is True
    assert main_mod._is_dust_sell(0.50, 0.5) is False
