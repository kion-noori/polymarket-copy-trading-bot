import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from check_bot_health import assess_health


def test_low_cash_is_not_a_reason_to_restart_the_bot():
    snapshot = {'last_cycle': {'at': 100, 'ok': True}, 'active_orders': [],
                'controls': {'manual_observer': {'ok': True}, 'cash': {'available_for_buy': 0}},
                'settings': {'manual_exit_protection': True}}
    assert assess_health(snapshot, now=101) == []


def test_unknown_order_and_stale_poll_are_explicit_health_issues():
    snapshot = {'last_cycle': {'at': 0, 'ok': True},
                'active_orders': [{'status': 'unknown', 'age_seconds': 10}],
                'controls': {'manual_observer': {'ok': False}},
                'settings': {'manual_exit_protection': True}}
    assert assess_health(snapshot, now=400) == [
        'manual_activity_unavailable', 'order_requires_review', 'poll_heartbeat_stale']
