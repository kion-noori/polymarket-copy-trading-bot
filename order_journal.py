"""Durable submission intents and confirmed fills (single bot process).

An interrupted/ambiguous post stays blocked instead of creating another order.
SQLite is authoritative; CSV exports can always be rebuilt without duplicate rows.
"""
from __future__ import annotations
from contextlib import contextmanager
import csv
import hashlib
import json
import sqlite3
import time
from pathlib import Path

import config

JOURNAL_FILE = Path(__file__).parent / "state" / "orders.sqlite3"
ACTIVE = ("submitting", "pending", "unknown")


@contextmanager
def _connect():
    Path(JOURNAL_FILE).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(JOURNAL_FILE)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA synchronous=FULL")
    db.execute("""CREATE TABLE IF NOT EXISTS orders (
        intent_id TEXT PRIMARY KEY, account TEXT, target TEXT, asset TEXT,
        status TEXT, order_id TEXT, submitted_at REAL, updated_at REAL,
        request TEXT, response TEXT, fills TEXT, attempts INTEGER DEFAULT 1)""")
    db.execute("""CREATE TABLE IF NOT EXISTS order_sources (
        account TEXT, target TEXT, source_id TEXT, intent_id TEXT,
        PRIMARY KEY(account, target, source_id, intent_id))""")
    try:
        with db:
            yield db
    finally:
        db.close()


def intent_key(source_ids: list[str]) -> str:
    return hashlib.sha256(json.dumps([config.FUNDER_ADDRESS.lower(), config.TARGET_WALLET.lower(),
                                     sorted(source_ids)]).encode()).hexdigest()


def reserve(request: dict) -> tuple[str, dict | None]:
    """Commit intent BEFORE any signed order can be posted."""
    key = intent_key(request["source_ids"])
    with _connect() as db:
        db.execute("BEGIN IMMEDIATE")
        previous = db.execute("SELECT * FROM orders WHERE intent_id=?", (key,)).fetchone()
        if previous and previous["status"] not in ("rejected",):
            return key, dict(previous)
        busy = db.execute("SELECT * FROM orders WHERE account=? AND asset=? AND status IN (?,?,?)",
                          (config.FUNDER_ADDRESS.lower(), request["asset"], *ACTIVE)).fetchone()
        if busy:
            return key, dict(busy)
        now = time.time()
        db.execute("""INSERT INTO orders VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(intent_id) DO UPDATE SET status='submitting', order_id='',
            submitted_at=excluded.submitted_at, updated_at=excluded.updated_at,
            request=excluded.request, response='{}', fills='[]', attempts=orders.attempts+1""",
                   (key, config.FUNDER_ADDRESS.lower(), config.TARGET_WALLET.lower(), request["asset"],
                    "submitting", "", now, now, json.dumps(request), "{}", "[]", 1))
        db.executemany("INSERT OR IGNORE INTO order_sources VALUES (?,?,?,?)",
                       [(config.FUNDER_ADDRESS.lower(), config.TARGET_WALLET.lower(), source, key)
                        for source in request["source_ids"]])
    return key, None


def update(key: str, status: str, *, response: dict | None = None, fills: list | None = None):
    with _connect() as db:
        if response is not None:
            db.execute("UPDATE orders SET response=?, order_id=? WHERE intent_id=?",
                       (json.dumps(response), response.get("orderID", ""), key))
        if fills is not None:
            db.execute("UPDATE orders SET fills=? WHERE intent_id=?", (json.dumps(fills), key))
        db.execute("UPDATE orders SET status=?, updated_at=? WHERE intent_id=?", (status, time.time(), key))


def active_orders() -> list[dict]:
    with _connect() as db:
        return [dict(row) for row in db.execute(
            "SELECT * FROM orders WHERE account=? AND status IN (?,?,?)",
            (config.FUNDER_ADDRESS.lower(), *ACTIVE))]


def asset_pending(asset: str) -> bool:
    return any(row["asset"] == asset for row in active_orders())


def all_orders() -> list[dict]:
    with _connect() as db:
        return [dict(row) for row in db.execute("SELECT * FROM orders WHERE account=? ORDER BY submitted_at",
                                               (config.FUNDER_ADDRESS.lower(),))]


def export_fills(directory: str | Path):
    """Write confirmed receipts only; no intended price/quantity masquerading as fills."""
    rows = []
    for order in all_orders():
        if order["status"] != "filled":
            continue
        request = json.loads(order["request"])
        for fill in json.loads(order["fills"]):
            rows.append({"submitted_at": order["submitted_at"], "order_id": order["order_id"],
                         "asset": order["asset"], "side": request["side"],
                         "source_ids": json.dumps(request["source_ids"]),
                         "reference_price": request["reference_price"], **fill})
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "confirmed_fills.csv"
    fields = ["submitted_at", "order_id", "asset", "side", "source_ids", "reference_price",
              "trade_id", "shares", "price", "notional_usd", "timestamp", "transaction_hash"]
    temp = path.with_suffix(".csv.tmp")
    with temp.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    temp.replace(path)


def source_handled(source_id: str) -> bool:
    """Indexed membership survives a crash between submission and JSON state commit."""
    with _connect() as db:
        return db.execute("""SELECT 1 FROM order_sources s JOIN orders o ON s.intent_id=o.intent_id
            WHERE s.account=? AND s.target=? AND s.source_id=? AND o.status!='rejected' LIMIT 1""",
            (config.FUNDER_ADDRESS.lower(), config.TARGET_WALLET.lower(), source_id)).fetchone() is not None
