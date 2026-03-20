"""Tests for seen-trade state + memory cache."""

import importlib
import json

import pytest


@pytest.fixture
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setenv("TARGET_WALLET", "0x" + "1" * 40)
    import config
    import state as st

    importlib.reload(config)
    importlib.reload(st)
    monkeypatch.setattr(st, "STATE_FILE", str(tmp_path / "seen.json"))
    st.clear_seen_memory_cache()
    yield st
    st.clear_seen_memory_cache()


def test_is_already_seen_false_then_true_after_mark(isolated_state):
    st = isolated_state
    assert st.is_already_seen("0xabc") is False
    st.mark_seen("0xabc")
    assert st.is_already_seen("0xabc") is True


def test_mark_seen_batch(isolated_state):
    st = isolated_state
    st.mark_seen_batch(["0xa", "0xb"])
    assert st.is_already_seen("0xa") and st.is_already_seen("0xb")


def test_reload_from_disk_after_clear_cache(isolated_state, tmp_path):
    st = isolated_state
    st.mark_seen("persist")
    st.clear_seen_memory_cache()
    assert st.is_already_seen("persist") is True
    data = json.loads((tmp_path / "seen.json").read_text(encoding="utf-8"))
    assert "persist" in data["seen_tx_hashes"]


def test_note_live_order_failure_abandons_after_max(isolated_state):
    st = isolated_state
    assert st.note_live_order_failure(["0xfail"], max_attempts=3) is False
    assert st.note_live_order_failure(["0xfail"], max_attempts=3) is False
    assert st.note_live_order_failure(["0xfail"], max_attempts=3) is True
    assert st.is_already_seen("0xfail") is False
    st.mark_seen("0xfail")
    assert st.note_live_order_failure(["0xfail"], max_attempts=3) is False


def test_note_live_order_failure_unlimited(isolated_state):
    st = isolated_state
    assert st.note_live_order_failure(["0xa"], max_attempts=0) is False
    assert st.note_live_order_failure(["0xa"], max_attempts=0) is False


def test_mark_seen_clears_failure_count(isolated_state, tmp_path):
    st = isolated_state
    st.note_live_order_failure(["0xb"], max_attempts=99)
    mid = json.loads((tmp_path / "seen.json").read_text(encoding="utf-8"))
    assert mid["order_failure_counts"].get("0xb", 0) >= 1
    st.mark_seen("0xb")
    final = json.loads((tmp_path / "seen.json").read_text(encoding="utf-8"))
    assert "0xb" not in (final.get("order_failure_counts") or {})
