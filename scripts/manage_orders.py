"""Inspect pending orders; reconcile an uncertain post only after checking the exchange."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import order_journal as journal


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--intent")
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--attach-order", help="Existing exchange order ID; validated before linking")
    actions.add_argument("--close-unsubmitted", action="store_true", help="Clear block without replaying the original trade")
    parser.add_argument("--confirm-no-order", action="store_true", help="You verified no exchange order or fill exists")
    args = parser.parse_args()
    if not Path(journal.JOURNAL_FILE).exists():
        print("No live order journal on this machine.")
        return 0
    # Listing is read-only, including when the bot is running.
    with sqlite3.connect(Path(journal.JOURNAL_FILE).resolve().as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        from config import FUNDER_ADDRESS
        rows = [dict(row) for row in db.execute("SELECT * FROM orders WHERE account=?", (FUNDER_ADDRESS.lower(),))]
    if not (args.attach_order or args.close_unsubmitted):
        for row in rows:
            if row["status"] in journal.ACTIVE:
                print(json.dumps({key: row[key] for key in ("intent_id", "asset", "status", "order_id", "submitted_at")}))
        return 0
    row = next((row for row in rows if row["intent_id"] == args.intent), None)
    if not row or row["status"] not in ("submitting", "unknown") or row["order_id"]:
        parser.error("Select an uncertain intent without an order ID")
    if args.attach_order:
        from executor import get_client
        order = get_client().get_order(args.attach_order)
        request = json.loads(row["request"])
        if not isinstance(order, dict) or order.get("asset_id") != row["asset"] or order.get("side", "").upper() != request["side"]:
            parser.error("Exchange order does not match the intent's asset and side")
        journal.update(row["intent_id"], "pending", response={"orderID": args.attach_order})
        print("Linked existing order. The bot will verify its fills; no order was posted.")
    else:
        if not args.confirm_no_order:
            parser.error("Verify exchange history first, then pass --confirm-no-order")
        journal.update(row["intent_id"], "unfilled", fills=[])
        print("Cleared uncertain intent. Its original source trade will not be replayed automatically.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
