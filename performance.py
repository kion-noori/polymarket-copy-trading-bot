"""Compare observed activity; never infer bot attribution or ROI from public trades alone."""
from __future__ import annotations
import json
from collections import Counter
from data_api import trade_key


def build_report(target_trades: list[dict], my_trades: list[dict], orders: list[dict],
                 my_activity: list[dict], start: int, end: int) -> dict:
    target = {trade_key(row): row for row in target_trades}
    attributed: dict[str, list[dict]] = {}
    statuses = Counter()
    for order in orders:
        if not start <= order["submitted_at"] <= end:
            continue
        statuses[order["status"]] += 1
        request = json.loads(order["request"])
        for source in request["source_ids"]:
            attributed.setdefault(source, []).append(order)
    details = []
    for key, trade in target.items():
        matched = attributed.get(key, [])
        fills = [fill for order in matched if order["status"] == "filled"
                 for fill in json.loads(order["fills"])]
        quantity = sum(fill["shares"] for fill in fills)
        notional = sum(fill["notional_usd"] for fill in fills)
        # A catch-up order can cover multiple source trades. Report it once against
        # the group's requested reference, not repeatedly against each constituent.
        grouped = any(len(json.loads(order["request"])["source_ids"]) > 1 for order in matched)
        average = notional / quantity if quantity else None
        reference = trade["price"]
        adverse_points = None if average is None or grouped else (
            average - reference if trade["side"] == "BUY" else reference - average)
        details.append({"source_id": key, "asset": trade["asset"], "side": trade["side"],
                        "title": trade.get("title", ""), "target_price": reference,
                        "status": matched[-1]["status"] if matched else "no_attributed_order",
                        "grouped_order": grouped, "our_average_price": average,
                        "adverse_price_points": adverse_points,
                        "order_ids": sorted({order["order_id"] for order in matched if order["order_id"]})})
    activity_counts = Counter(row.get("type") for row in my_activity)
    cashflows = [row for row in my_activity if row.get("type") in ("DEPOSIT", "WITHDRAWAL")]
    return {"start": start, "end": end, "target_trade_groups": len(target),
            "my_public_trade_groups": len(my_trades), "order_statuses": dict(statuses),
            "activity_counts": dict(activity_counts), "cashflows": cashflows, "comparisons": details,
            "limitations": [
                "No attributed order does not prove a missed trade: policy skips, pre-journal trades and downtime can explain it.",
                "Public trades cannot distinguish manual sales from bot trades; only journal-linked executions are attributed.",
                "Grouped order fills are shared across source trades and must not be summed per comparison row.",
                "Prices/notionals are execution amounts before any separately charged fees; no return percentage is inferred.",
                "Compare PnL on identical dates; deposits and withdrawals are capital movements, not profit.",
                "Target cash and historical NAV are unavailable from position value alone; proportional ROI is not established."]}


def aligned_pnl_changes(series: dict, start: int, end: int) -> dict:
    """Compare the identical available daily snapshots; never substitute null with zero."""
    by_wallet = {wallet: {p["timestamp"]: p for p in data.get("points", [])
                          if start <= p["timestamp"] <= end}
                 for wallet, data in series.items()}
    common = sorted(set(by_wallet.get("target", {})) & set(by_wallet.get("mine", {})))
    if len(common) < 2:
        return {"available": False, "reason": "Fewer than two common PnL snapshots"}
    first, last = common[0], common[-1]
    changes = {}
    for wallet, points in by_wallet.items():
        changes[wallet] = {}
        for metric in ("economic_pnl", "realized_pnl", "unrealized_pnl", "trade_pnl", "fees_paid"):
            a, b = points[first].get(metric), points[last].get(metric)
            changes[wallet][metric] = None if a is None or b is None else b - a
    return {"available": True, "start": first, "end": last, "changes_usd": changes,
            "note": "Absolute changes in cumulative metrics, not percentage returns or an exact bot attribution."}


def markdown_report(result: dict) -> str:
    from datetime import datetime, timezone
    def date(ts):
        return datetime.fromtimestamp(ts, timezone.utc).isoformat()
    cash = result["cashflows"]
    deposits = sum(float(row["usdc_size"]) for row in cash if row["type"] == "DEPOSIT")
    withdrawals = sum(float(row["usdc_size"]) for row in cash if row["type"] == "WITHDRAWAL")
    lines = ["# Account activity review", "", f"UTC window: {date(result['start'])} to {date(result['end'])}", "",
             f"- Target trade groups: {result['target_trade_groups']}",
             f"- Your public trade groups: {result['my_public_trade_groups']}",
             f"- Deposits: ${deposits:,.2f}; withdrawals: ${withdrawals:,.2f} (capital movements)",
             f"- Locally journaled order outcomes: {result['order_statuses'] or 'none in this window'}", ""]
    if "target_taker_only_groups" in result:
        lines += [f"Target groups visible to the old taker-only feed: {result['target_taker_only_groups']}.",
                  "This measures feed coverage, not the number of trades the bot should necessarily copy.", ""]
    for wallet, key in (("Target", "raw_target_trades"), ("Yours", "raw_my_trades")):
        counts = Counter(row["side"] for row in result[key])
        lines.append(f"{wallet}: {counts.get('BUY', 0)} BUYs and {counts.get('SELL', 0)} SELLs.")
    pnl = result.get("aligned_pnl", {})
    if pnl.get("available"):
        lines += ["", f"Common PnL snapshot span: {date(pnl['start'])} to {date(pnl['end'])}.", "",
                  "| Cumulative metric change (USD) | Target | Yours |", "|---|---:|---:|"]
        for metric in ("economic_pnl", "realized_pnl", "unrealized_pnl", "trade_pnl"):
            vals = [pnl["changes_usd"][wallet][metric] for wallet in ("target", "mine")]
            pretty = ["unavailable" if v is None else f"${v:,.2f}" for v in vals]
            lines.append(f"| {metric} | {pretty[0]} | {pretty[1]} |")
        lines += ["", pnl["note"]]
    lines += ["", "## Interpretation limits", ""]
    lines += [f"- {text}" for text in result["limitations"]]
    return "\n".join(lines) + "\n"
