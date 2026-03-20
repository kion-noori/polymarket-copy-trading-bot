"""Tests for proportional sizing."""

import importlib

import pytest

import sizing


@pytest.fixture(autouse=True)
def _sizing_env_defaults(monkeypatch):
    monkeypatch.setenv("SKIP_COPY_WHEN_TARGET_VALUE_UNKNOWN", "true")
    monkeypatch.setenv("MIN_NOTIONAL_MODE", "floor")
    monkeypatch.setenv("MAX_PCT_PER_TRADE", "0.10")
    monkeypatch.setenv("SIZE_MULTIPLIER", "1.0")
    monkeypatch.setenv("MIN_NOTIONAL", "5")
    monkeypatch.setenv("MAX_TRADE_USD", "0")
    import config as config_mod

    importlib.reload(config_mod)
    importlib.reload(sizing)
    yield


def test_compute_my_notional_proportional():
    # target spent 100 of 1000 = 10%; we have 500 -> raw 50, cap 10% of 500 = 50, floor 5 -> 50
    n = sizing.compute_my_notional(100.0, 500.0, 1000.0)
    assert abs(n - 50.0) < 1e-6


def test_compute_my_notional_target_unknown_skips(monkeypatch):
    monkeypatch.setenv("SKIP_COPY_WHEN_TARGET_VALUE_UNKNOWN", "true")
    import config as config_mod

    importlib.reload(config_mod)
    importlib.reload(sizing)
    assert sizing.compute_my_notional(100.0, 500.0, 0.0) == 0.0


def test_compute_my_notional_skip_dust(monkeypatch):
    monkeypatch.setenv("MIN_NOTIONAL_MODE", "skip")
    monkeypatch.setenv("MIN_NOTIONAL", "5")
    import config as config_mod

    importlib.reload(config_mod)
    importlib.reload(sizing)
    n = sizing.compute_my_notional(1.0, 500.0, 100_000.0)
    assert n == 0.0
