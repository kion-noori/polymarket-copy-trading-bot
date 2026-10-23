"""Inspect copy decisions and manage asset-level BUY pauses; never place orders."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config
import copy_controls as controls
import order_journal as journal


def health_report(hours=24):
    since = time.time() - hours * 3600
    orders = journal.all_orders()
    recent = [row for row in orders if row['submitted_at'] >= since]
    statuses = Counter(row['status'] for row in recent)
    executions = []
    for row in recent:
        if row['status'] != 'filled':
            continue
        request, fills = json.loads(row['request']), json.loads(row['fills'])
        shares = sum(fill['shares'] for fill in fills)
        notional = sum(fill['notional_usd'] for fill in fills)
        average = notional / shares if shares else None
        reference = request['reference_price']
        executions.append({'order_id': row['order_id'], 'side': request['side'],
                           'asset': row['asset'], 'shares': shares, 'notional_usd': notional,
                           'average_price': average, 'reference_price': reference,
                           'adverse_price_points': None if average is None else (
                               average - reference if request['side'] == 'BUY' else reference - average),
                           'filled_fraction_of_request': notional / request['notional_usd'] if request['side'] == 'BUY'
                           else shares / request['shares'],
                           'fill_fraction_units': 'pre_fee_notional / requested_cash_budget' if request['side'] == 'BUY'
                           else 'confirmed_shares / requested_shares'})
    return {'generated_at': time.time(), 'hours': hours, 'controls': controls.summary(since),
            'order_outcomes': dict(statuses), 'confirmed_executions': executions,
            'active_orders': [{'intent_id': row['intent_id'], 'asset': row['asset'], 'status': row['status'],
                              'age_seconds': time.time()-row['submitted_at']} for row in orders if row['status'] in journal.ACTIVE],
            'combo_coverage': controls.get_meta('combo_registry'),
            'last_cycle': controls.get_meta('last_cycle'),
            'settings': {'cash_reserve_fraction': config.CASH_RESERVE_FRACTION,
                         'cash_reserve_usd': config.CASH_RESERVE_USD,
                         'cash_deferral_sec': config.CASH_DEFERRAL_SEC,
                         'manual_exit_protection': config.MANUAL_EXIT_PROTECTION},
            'limitations': ['Execution amounts exclude separately charged fees; no ROI is inferred.',
                           'Source/reason counts overlap across reasons and must not be added as unique trades.',
                           'External means not attributed to this bot, not proof of a specific person or interface.',
                           'Unresolved Combo portfolio values are cost basis, not executable quotes.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest='action', required=True)
    status = actions.add_parser('status')
    status.add_argument('--hours', type=float, default=24)
    for name in ('pause', 'resume'):
        sub = actions.add_parser(name)
        sub.add_argument('asset')
        sub.add_argument('--reason', required=True)
    args = parser.parse_args()
    if args.action == 'status':
        print(json.dumps(health_report(args.hours), indent=2))
    else:
        controls.set_pause(args.asset, args.action == 'pause', args.reason)
        print(f"Asset {args.asset}: BUY pause {'enabled' if args.action == 'pause' else 'cleared'}; SELLs remain enabled")


if __name__ == '__main__':
    main()
