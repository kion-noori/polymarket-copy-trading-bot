"""Cash, external-sale attribution and restart behavior have financial impact."""
import json
import pytest
import config
import copy_controls as controls
import manual_guard
import market_support


def test_reserve_and_pending_buys_are_not_spendable(monkeypatch):
    monkeypatch.setattr(config, 'CASH_RESERVE_FRACTION', .1)
    monkeypatch.setattr(config, 'CASH_RESERVE_USD', 0)
    assert controls.cash_budget(50, 200, 15) == (15, 20)
    assert controls.cash_budget(10, 200, 0) == (0, 20)
    with pytest.raises(ValueError):
        controls.cash_budget(float('nan'), 100)


def test_cash_deadline_survives_retries_and_restart(monkeypatch):
    monkeypatch.setattr(config, 'CASH_DEFERRAL_SEC', 300)
    controls.defer(['source'], now=100)
    controls.defer(['source'], now=399)
    assert not controls.deferred_expired('source', now=399)
    assert controls.deferred_expired('source', now=400)


def sale(tx='external', asset='token'):
    return {'transactionHash': tx, 'asset': asset, 'side': 'SELL', 'timestamp': 200,
            'size': 3, 'price': .5}


def order(status='filled', tx='bot', asset='token'):
    return {'asset': asset, 'status': status, 'request': json.dumps({'side': 'SELL'}),
            'fills': json.dumps([{'transaction_hash': tx, 'shares': 3}]) if status == 'filled' else '[]'}


def test_external_partial_exit_pauses_only_that_asset_and_resume_is_durable():
    assert manual_guard.observe_sales([sale()], 100, []) == ['token']
    assert controls.paused('token')
    assert not controls.paused('other')
    controls.set_pause('token', False, 'operator_resume')
    manual_guard.observe_sales([sale()], 100, [])
    assert not controls.paused('token')


def test_bot_sale_is_not_misclassified_as_manual():
    assert manual_guard.observe_sales([sale('bot')], 100, [order()]) == []
    assert not controls.paused('token')


def test_pending_sale_attribution_waits_then_recognizes_bot():
    assert manual_guard.observe_sales([sale('bot')], 100, [order('pending')]) == []
    assert controls.sale_classification('bot:token:SELL') is None
    assert manual_guard.observe_sales([sale('bot')], 100, [order()]) == []
    assert controls.sale_classification('bot:token:SELL') == 'bot'


def test_external_sale_with_different_transaction_after_bot_fill_is_detected():
    assert manual_guard.observe_sales([sale('manual')], 100, [order()]) == ['token']


def test_combined_settlement_with_bot_and_manual_quantity_is_detected():
    combined = {**sale('bot'), 'size': 5}
    assert manual_guard.observe_sales([combined], 100, [order()]) == ['token']


def test_later_indexed_manual_leg_in_same_settlement_is_not_hidden_by_bot_match():
    assert manual_guard.observe_sales([sale('bot')], 100, [order()]) == []
    combined = {**sale('bot'), 'size': 5}
    assert manual_guard.observe_sales([combined], 100, [order()]) == ['token']


def test_pre_monitoring_history_does_not_silently_pause_old_positions():
    assert manual_guard.observe_sales([sale()], 201, []) == []


def test_combo_detection_does_not_depend_on_display_title():
    controls.set_meta('combo_registry', {'conditions': ['combo']})
    assert market_support.unsupported_reason({'conditionId': 'combo', 'title': 'Unenriched'}) == 'combo_requires_rfq'
    assert market_support.unsupported_reason({'conditionId': '0x03'+'ab'*31, 'asset': '123', 'title': 'A AND B'}) is None
    assert market_support.unsupported_reason({'conditionId': 'ordinary', 'title': 'A AND B'}) is None


def test_protocol_candidate_requires_position_layout_and_condition_prefix():
    candidate = {'conditionId': '0x03'+'ab'*31, 'asset': str((3 << 248) + 256)}
    assert market_support.unsupported_reason(candidate) == 'combo_protocol_candidate'


def test_decision_reports_separate_source_counts_from_repeated_observations():
    controls.record(['s'], 'token', 'BUY', 'deferred', 'cash')
    controls.record(['s'], 'token', 'BUY', 'deferred', 'cash')
    row = controls.summary()['decisions'][0]
    assert row['source_reason_pairs'] == 1
    assert row['observations'] == 2
