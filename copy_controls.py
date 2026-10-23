"""Durable copy decisions, bounded deferrals and operator overrides.

This database is shared across releases, separate from secrets and processed IDs.
Rows are scoped to account/target; manual pauses apply account-wide per asset.
"""
from contextlib import contextmanager
import json
import math
from pathlib import Path
import sqlite3
import time

import config

CONTROL_FILE = None


def database_path():
    return Path(CONTROL_FILE) if CONTROL_FILE else Path(__file__).parent / 'state' / (
        'test_controls.sqlite3' if config.TEST_MODE else 'controls.sqlite3')


@contextmanager
def connect():
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA synchronous=FULL')
    db.executescript('''
        CREATE TABLE IF NOT EXISTS decisions (
          account TEXT, target TEXT, source TEXT, asset TEXT, side TEXT,
          action TEXT, reason TEXT, first_at REAL, last_at REAL, observations INTEGER,
          details TEXT, PRIMARY KEY(account,target,source,reason));
        CREATE TABLE IF NOT EXISTS deferrals (
          account TEXT, target TEXT, source TEXT, deadline REAL,
          PRIMARY KEY(account,target,source));
        CREATE TABLE IF NOT EXISTS pauses (
          account TEXT, asset TEXT, active INTEGER, reason TEXT, evidence TEXT,
          updated_at REAL, PRIMARY KEY(account,asset));
        CREATE TABLE IF NOT EXISTS metadata (
          account TEXT, target TEXT, key TEXT, value TEXT,
          PRIMARY KEY(account,target,key));
        CREATE TABLE IF NOT EXISTS observed_sales (
          account TEXT, target TEXT, source TEXT, classification TEXT,
          PRIMARY KEY(account,target,source));
        CREATE INDEX IF NOT EXISTS decisions_recent ON decisions(account,target,last_at);
    ''')
    try:
        with db:
            yield db
    finally:
        db.close()


def scope():
    return config.FUNDER_ADDRESS.lower(), config.TARGET_WALLET.lower()


def record(source_ids, asset, side, action, reason, **details):
    now = time.time()
    with connect() as db:
        for source in source_ids:
            db.execute('''INSERT INTO decisions VALUES (?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(account,target,source,reason) DO UPDATE SET
                action=excluded.action,last_at=excluded.last_at,
                observations=decisions.observations+1,details=excluded.details''',
                (*scope(), source, asset, side, action, reason, now, now, 1, json.dumps(details)))


def deferred_expired(source, now=None):
    now = time.time() if now is None else now
    with connect() as db:
        row = db.execute('SELECT deadline FROM deferrals WHERE account=? AND target=? AND source=?',
                         (*scope(), source)).fetchone()
    return row is not None and now >= row['deadline']


def defer(source_ids, now=None):
    now = time.time() if now is None else now
    with connect() as db:
        db.executemany('INSERT OR IGNORE INTO deferrals VALUES (?,?,?,?)',
                       [(*scope(), source, now + config.CASH_DEFERRAL_SEC) for source in source_ids])


def paused(asset):
    with connect() as db:
        row = db.execute('SELECT active FROM pauses WHERE account=? AND asset=?',
                         (scope()[0], asset)).fetchone()
    return bool(row and row['active'])


def set_pause(asset, active, reason, evidence=''):
    with connect() as db:
        db.execute('INSERT OR REPLACE INTO pauses VALUES (?,?,?,?,?,?)',
                   (scope()[0], asset, int(active), reason, evidence, time.time()))


def get_meta(key, default=None):
    with connect() as db:
        row = db.execute('SELECT value FROM metadata WHERE account=? AND target=? AND key=?',
                         (*scope(), key)).fetchone()
    return json.loads(row['value']) if row else default


def set_meta(key, value):
    with connect() as db:
        db.execute('INSERT OR REPLACE INTO metadata VALUES (?,?,?,?)', (*scope(), key, json.dumps(value)))


def sale_classification(source):
    with connect() as db:
        row = db.execute('SELECT classification FROM observed_sales WHERE account=? AND target=? AND source=?',
                         (*scope(), source)).fetchone()
    return row['classification'] if row else None


def remember_sale(source, classification):
    with connect() as db:
        db.execute('INSERT OR REPLACE INTO observed_sales VALUES (?,?,?,?)', (*scope(), source, classification))


def cash_budget(cash, nav, pending=0):
    if not all(math.isfinite(v) and v >= 0 for v in (cash, nav, pending)):
        raise ValueError('Invalid cash budget inputs')
    reserve = max(config.CASH_RESERVE_USD, config.CASH_RESERVE_FRACTION * nav)
    return max(0.0, cash - reserve - pending), reserve


def summary(since=0):
    with connect() as db:
        decisions = [dict(r) for r in db.execute('''SELECT action,reason,COUNT(*) AS source_reason_pairs,
            SUM(observations) AS observations FROM decisions WHERE account=? AND target=? AND last_at>=?
            GROUP BY action,reason''', (*scope(), since))]
        pauses = [dict(r) for r in db.execute('SELECT * FROM pauses WHERE account=? AND active=1', (scope()[0],))]
    return {'decisions': decisions, 'paused_assets': pauses,
            'cash': get_meta('cash_snapshot'), 'manual_observer': get_meta('manual_observer'),
            'observer_started_at': get_meta('observer_started_at')}
