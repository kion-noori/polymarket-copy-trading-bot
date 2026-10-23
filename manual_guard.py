"""Identify external settled sales without guessing from balance decreases.

Public on-chain trades cover browser activity that another API credential may
not expose. Journal fill transaction/asset identities identify this bot's sales.
Active/unknown bot submissions defer attribution until exchange reconciliation.
"""
import json
import logging
import time

import config
import copy_controls as controls
import order_journal as journal
from data_api import get_trades, trade_key

logger = logging.getLogger(__name__)


def fetch_account_trades(start, end):
    return get_trades(config.FUNDER_ADDRESS, limit=100, max_pages=100,
                      start=start, end=end, bounded=False)


def observe_sales(trades, started_at, orders):
    known = {}
    uncertain_assets = set()
    for order in orders:
        request = json.loads(order['request'])
        if request.get('side') != 'SELL':
            continue
        if order['status'] in journal.ACTIVE:
            uncertain_assets.add(order['asset'])
        for fill in json.loads(order['fills']):
            tx = fill.get('transaction_hash')
            if tx:
                key = (tx.lower(), order['asset'])
                known[key] = known.get(key, 0) + float(fill['shares'])
    new_pauses = []
    earliest_unresolved = None
    for trade in trades:
        if trade.get('side', '').upper() != 'SELL' or float(trade['timestamp']) < started_at:
            continue
        source = trade_key(trade)
        asset = trade['asset']
        if not source:
            raise ValueError('External sale lacks stable identity')
        if controls.sale_classification(source) == 'external':
            continue
        tx = trade.get('transactionHash') or trade.get('transaction_hash')
        # A settlement transaction can batch bot and browser orders. Identity
        # alone is insufficient: compare the account's aggregate sold quantity.
        if known.get((tx.lower(), asset), 0) + 1e-6 >= float(trade['size']):
            controls.remember_sale(source, 'bot')
        elif asset in uncertain_assets:
            # Do not advance a per-trade seen flag: later polls revisit it.
            earliest_unresolved = min(earliest_unresolved or float(trade['timestamp']), float(trade['timestamp']))
            continue
        else:
            # One transaction prevents a crash between remembering and pausing.
            with controls.connect() as db:
                db.execute('INSERT OR REPLACE INTO pauses VALUES (?,?,?,?,?,?)',
                           (controls.scope()[0], asset, 1, 'external_sale', source, time.time()))
                db.execute('INSERT OR REPLACE INTO observed_sales VALUES (?,?,?,?)',
                           (*controls.scope(), source, 'external'))
            controls.record([source], asset, 'SELL', 'observed', 'external_sale',
                            shares=trade['size'], title=trade.get('title', ''))
            new_pauses.append(asset)
    controls.set_meta('observer_pending_since', earliest_unresolved)
    return new_pauses


def refresh(now=None, force=False):
    if config.TEST_MODE or not config.MANUAL_EXIT_PROTECTION:
        return True
    now = time.time() if now is None else now
    started = controls.get_meta('observer_started_at')
    if started is None:
        started = int(now)
        controls.set_meta('observer_started_at', started)
    previous = controls.get_meta('manual_observer', {})
    if not force and previous.get('ok') and now - previous.get('checked_at', 0) < 30:
        return True
    # Retain an overlap for delayed public indexing and settlement. After an
    # outage the complete downtime range is read, not just the most recent page.
    start = max(started, int(previous.get('checked_at', started) - 3600))
    pending_since = controls.get_meta('observer_pending_since')
    if pending_since is not None:
        start = max(started, min(start, int(pending_since) - 1))
    try:
        trades = fetch_account_trades(start, int(now))
        pauses = observe_sales(trades, started, journal.all_orders())
        controls.set_meta('manual_observer', {'ok': True, 'checked_at': now, 'rows': len(trades)})
        for asset in pauses:
            logger.warning('External settled sale detected; new BUYs paused for asset %s', asset)
        return True
    except Exception:
        controls.set_meta('manual_observer', {'ok': False, 'checked_at': previous.get('checked_at', started),
                                             'failed_at': now})
        logger.warning('Manual-exit activity unavailable; BUYs deferred, SELLs remain active')
        return False
