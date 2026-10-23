"""Local health snapshot for a systemd timer. Does not restart or trade."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

from control_bot import health_report


def assess_health(snapshot, now=None):
    now = time.time() if now is None else now
    issues = []
    cycle = snapshot.get('last_cycle')
    if not cycle or now - cycle['at'] > 180:
        issues.append('poll_heartbeat_stale')
    elif not cycle['ok']:
        issues.append('last_poll_failed')
    for order in snapshot['active_orders']:
        if order['status'] in ('unknown', 'submitting') or order['age_seconds'] > 300:
            issues.append('order_requires_review')
    observer = snapshot['controls']['manual_observer']
    if snapshot['settings']['manual_exit_protection'] and (not observer or not observer['ok']):
        issues.append('manual_activity_unavailable')
    registry = snapshot.get('combo_coverage')
    if registry is not None and not registry.get('ok'):
        issues.append('combo_registry_unavailable')
    return sorted(set(issues))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    snapshot = health_report()
    snapshot['issues'] = assess_health(snapshot)
    service = subprocess.run(['systemctl', 'is-active', 'polymarket-bot'], capture_output=True, text=True)
    snapshot['service'] = service.stdout.strip()
    if service.returncode:
        snapshot['issues'].append('service_inactive')
    data = json.dumps(snapshot, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temp = args.output.with_suffix('.json.tmp')
        temp.write_text(data)
        temp.replace(args.output)
    print(json.dumps({'service': snapshot['service'], 'issues': snapshot['issues'],
                      'order_outcomes': snapshot['order_outcomes'],
                      'cash': snapshot['controls']['cash']}))
    return 1 if snapshot['issues'] else 0


if __name__ == '__main__':
    sys.exit(main())
