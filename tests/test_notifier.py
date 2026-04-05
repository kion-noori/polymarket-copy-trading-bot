"""Tests for webhook alert helper."""

import importlib


def test_send_alert_posts_once_and_throttles(monkeypatch):
    monkeypatch.setenv("ALERT_WEBHOOK_URL", "https://example.com/hook")
    monkeypatch.setenv("ALERT_MIN_INTERVAL_SEC", "300")

    import config
    import notifier

    importlib.reload(config)
    importlib.reload(notifier)

    calls: list[tuple[str, dict]] = []

    class _Resp:
        def raise_for_status(self):
            return None

    def fake_post(url, json, timeout):
        calls.append((url, json))
        return _Resp()

    monkeypatch.setattr(notifier.requests, "post", fake_post)

    assert notifier.send_alert("give_up", "hello") is True
    assert notifier.send_alert("give_up", "hello again") is False
    assert len(calls) == 1
