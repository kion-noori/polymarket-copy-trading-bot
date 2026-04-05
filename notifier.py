"""Best-effort alert delivery for important bot events."""

from __future__ import annotations

import logging
import time

import requests

from config import ALERT_MIN_INTERVAL_SEC, ALERT_WEBHOOK_URL

logger = logging.getLogger(__name__)

_last_alert_sent_at: dict[str, float] = {}


def _build_payload(kind: str, message: str, ts: int) -> dict:
    url = ALERT_WEBHOOK_URL.lower()
    if "discord.com/api/webhooks" in url or "discordapp.com/api/webhooks" in url:
        return {"content": f"[{kind}] {message}"}
    if "hooks.slack.com/" in url:
        return {"text": f"[{kind}] {message}"}
    return {"kind": kind, "text": message, "ts": ts}


def send_alert(kind: str, message: str) -> bool:
    """
    Send a webhook alert with simple auto-formatting for Discord and Slack.
    Returns True if we posted an alert, False if disabled, throttled, or failed.
    """
    if not ALERT_WEBHOOK_URL:
        return False
    now = time.time()
    last = _last_alert_sent_at.get(kind, 0.0)
    if ALERT_MIN_INTERVAL_SEC > 0 and now - last < ALERT_MIN_INTERVAL_SEC:
        return False
    payload = _build_payload(kind, message, int(now))
    try:
        r = requests.post(ALERT_WEBHOOK_URL, json=payload, timeout=10)
        r.raise_for_status()
        _last_alert_sent_at[kind] = now
        return True
    except requests.RequestException as e:
        logger.warning("Alert send failed (%s): %s", kind, e)
        return False
