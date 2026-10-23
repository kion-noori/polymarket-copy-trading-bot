"""Read-only public-account review. Does not import the executor or place orders."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config import FUNDER_ADDRESS, TARGET_WALLET
from data_api import get_activity, get_pnl_series, get_positions, get_trades, DataAPIError
from performance import build_report, aligned_pnl_changes, markdown_report


def read_orders(path: Path) -> list[dict]:
    if not path.exists():
        return []
    # URI read-only mode cannot create or modify a journal.
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        return [dict(row) for row in db.execute("SELECT * FROM orders WHERE account=? AND target=?",
                                               (FUNDER_ADDRESS.lower(), TARGET_WALLET.lower()))]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--output", type=Path, default=ROOT / "logs" / "performance_review.json")
    parser.add_argument("--journal", type=Path, default=ROOT / "state" / "orders.sqlite3")
    args = parser.parse_args()
    if args.days <= 0 or not TARGET_WALLET or not FUNDER_ADDRESS:
        parser.error("Use positive --days and configure both wallet addresses")
    end = int(time.time())
    start = end - args.days * 86400
    try:
        target = get_trades(TARGET_WALLET, limit=1000, max_pages=1000, start=start, end=end, bounded=False)
        target_takers = get_trades(TARGET_WALLET, limit=1000, max_pages=1000, start=start, end=end, bounded=False, taker_only=True)
        mine = get_trades(FUNDER_ADDRESS, limit=1000, max_pages=1000, start=start, end=end, bounded=False)
        activity = get_activity(FUNDER_ADDRESS, start, end)
        result = build_report(target, mine, read_orders(args.journal), activity, start, end)
        result["target_taker_only_groups"] = len(target_takers)
        result["generated_at"] = datetime.now(timezone.utc).isoformat()
        result["raw_target_trades"] = target
        result["raw_my_trades"] = mine
        result["current_positions"] = {"target": get_positions(TARGET_WALLET), "mine": get_positions(FUNDER_ADDRESS)}
        result["pnl_series"] = {"target": get_pnl_series(TARGET_WALLET), "mine": get_pnl_series(FUNDER_ADDRESS)}
    except DataAPIError as exc:
        print(f"Review incomplete: {exc}. No partial report written.", file=sys.stderr)
        return 1
    result["aligned_pnl"] = aligned_pnl_changes(result["pnl_series"], start, end)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    args.output.with_suffix(".md").write_text(markdown_report(result), encoding="utf-8")
    print(f"Saved read-only review: {args.output}")
    print(f"Target groups: {len(target)}; your public groups: {len(mine)}")
    print(f"Journal order outcomes: {result['order_statuses']}")
    print("Unattributed activity and manual trades need review; this report does not claim investment returns.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
