import json
import order_journal as journal


def request(asset="token", source="tx:token:BUY"):
    return {"asset": asset, "side": "BUY", "source_ids": [source], "reference_price": 0.5}


def test_reservation_survives_restart_and_blocks_ambiguous_repost():
    key, prior = journal.reserve(request())
    assert prior is None
    same_key, prior = journal.reserve(request())
    assert same_key == key and prior["status"] == "submitting"
    other_key, prior = journal.reserve(request(source="newtx:token:BUY"))
    assert other_key != key and prior["intent_id"] == key
    assert journal.asset_pending("token")


def test_only_rejected_orders_can_be_reposted():
    key, _ = journal.reserve(request())
    journal.update(key, "rejected", response={"success": False})
    _, previous = journal.reserve(request())
    assert previous is None
    journal.update(key, "pending", response={"orderID": "order"})
    _, previous = journal.reserve(request())
    assert previous["order_id"] == "order"


def test_confirmed_partial_fill_export_is_idempotent(tmp_path):
    key, _ = journal.reserve(request())
    journal.update(key, "filled", response={"orderID": "order"}, fills=[{
        "trade_id": "fill", "shares": 3, "price": 0.48, "notional_usd": 1.44,
        "timestamp": 100, "transaction_hash": "0xtx"}])
    journal.export_fills(tmp_path)
    first = (tmp_path / "confirmed_fills.csv").read_text()
    journal.export_fills(tmp_path)
    assert (tmp_path / "confirmed_fills.csv").read_text() == first
    assert len(first.splitlines()) == 2
    assert not journal.asset_pending("token")
