import pytest
from holdings_review import build_plan, book_sale_estimate


def test_holdings_review_excludes_manual_and_resolved_positions():
    rows = [{'asset': 'manual', 'size': 10, 'curPrice': .5},
            {'asset': 'resolved', 'size': 10, 'curPrice': 1, 'redeemable': True},
            {'asset': 'absent', 'size': 20, 'curPrice': .5},
            {'asset': 'aligned', 'size': 10, 'curPrice': .5}]
    plan = build_plan(rows, [{'asset': 'aligned', 'size': 10}], 100, 100, ['manual'])
    assert [r['asset'] for r in plan['candidates']] == ['absent']
    assert plan['marked_excess_usd'] == 10
    assert len(plan['excluded']) == 2


def test_book_estimate_does_not_value_unfillable_shares_at_mark():
    result = book_sale_estimate(20, [(.5, 3), (.4, 7), (.001, 100)])
    assert result['quoted_shares'] == 10
    assert result['unquoted_shares'] == 10
    assert result['indicative_gross_proceeds'] == pytest.approx(4.3)
