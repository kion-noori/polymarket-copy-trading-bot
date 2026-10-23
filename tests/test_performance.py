import json
from data_api import trade_key
from performance import build_report


def trade():
    return {"transactionHash": "tx", "asset": "token", "side": "BUY", "price": 0.5}


def test_manual_public_activity_is_not_attributed_to_bot():
    t = trade()
    result = build_report([t], [t], [], [{"type": "DEPOSIT", "usdc_size": 100}], 0, 200)
    assert result["comparisons"][0]["status"] == "no_attributed_order"
    assert result["my_public_trade_groups"] == 1
    assert result["cashflows"][0]["usdc_size"] == 100
    assert "roi" not in result


def test_execution_price_difference_uses_confirmed_fill():
    t = trade()
    order = {"submitted_at": 100, "status": "filled", "order_id": "order",
             "request": json.dumps({"source_ids": [trade_key(t)]}),
             "fills": json.dumps([{"shares": 3, "price": 0.52, "notional_usd": 1.56}])}
    comparison = build_report([t], [], [order], [], 0, 200)["comparisons"][0]
    assert abs(comparison["adverse_price_points"] - 0.02) < 1e-10


def test_grouped_order_does_not_claim_per_trade_slippage():
    t = trade()
    order = {"submitted_at": 100, "status": "filled", "order_id": "order",
             "request": json.dumps({"source_ids": [trade_key(t), "other"]}),
             "fills": json.dumps([{"shares": 3, "price": 0.52, "notional_usd": 1.56}])}
    comparison = build_report([t], [], [order], [], 0, 200)["comparisons"][0]
    assert comparison["grouped_order"] is True
    assert comparison["adverse_price_points"] is None


def test_pnl_uses_identical_snapshots_and_preserves_missing_values():
    from performance import aligned_pnl_changes
    series = {"target": {"points": [{"timestamp": 1, "economic_pnl": 10},
                                      {"timestamp": 2, "economic_pnl": 15}]},
              "mine": {"points": [{"timestamp": 1, "economic_pnl": None},
                                    {"timestamp": 2, "economic_pnl": 2},
                                    {"timestamp": 3, "economic_pnl": 999}]}}
    result = aligned_pnl_changes(series, 0, 5)
    assert result["end"] == 2
    assert result["changes_usd"]["target"]["economic_pnl"] == 5
    assert result["changes_usd"]["mine"]["economic_pnl"] is None
