"""Read-only startup-sale proposals; this module cannot submit orders."""
import math


def build_plan(mine, target, my_nav, target_value, paused_assets=(), minimum=1.0):
    if not all(math.isfinite(x) and x > 0 for x in (my_nav, target_value)):
        raise ValueError('Complete positive valuation required for holdings review')
    ratio = my_nav / target_value
    target_by_asset = {r['asset']: float(r['size']) for r in target}
    candidates, excluded = [], []
    for pos in mine:
        shares, mark = float(pos['size']), float(pos.get('curPrice') or 0)
        if not all(math.isfinite(x) and x >= 0 for x in (shares, mark)):
            raise ValueError('Invalid held position')
        desired = max(0, target_by_asset.get(pos['asset'], 0) * ratio)
        excess = max(0, shares - desired)
        if not excess:
            continue
        row = {'asset': pos['asset'], 'condition_id': pos.get('conditionId'),
               'title': pos.get('title', ''), 'held_shares': shares, 'desired_shares': desired,
               'excess_shares': excess, 'reference_price': mark, 'marked_excess_usd': excess * mark,
               'reason': 'target_absent' if pos['asset'] not in target_by_asset else 'overweight'}
        if pos['asset'] in paused_assets:
            row['excluded_reason'] = 'manual_exit_pause'
        elif pos.get('redeemable'):
            row['excluded_reason'] = 'resolved_redeemable'
        elif mark <= 0:
            row['excluded_reason'] = 'no_positive_mark'
        elif excess * mark < minimum:
            row['excluded_reason'] = 'below_review_minimum'
        if row.get('excluded_reason'):
            excluded.append(row)
        else:
            candidates.append(row)
    return {'ratio': ratio, 'candidates': sorted(candidates, key=lambda r: -r['marked_excess_usd']),
            'excluded': excluded, 'marked_excess_usd': sum(r['marked_excess_usd'] for r in candidates),
            'decision': 'review_only_no_orders', 'limitations': [
                'Target cash is unknown; the ratio is not a full cash-inclusive portfolio match.',
                'Unresolved Combo values enter NAV at cost basis, not a quoted liquidation value.',
                'A position mismatch does not prove that selling it improves expected returns.',
                'Historical manual position intent is unknown; automatic cleanup remains disabled.']}


def book_sale_estimate(shares, bids, price_floor=0.01):
    remaining, value = shares, 0.0
    for price, size in sorted(bids, reverse=True):
        if not all(math.isfinite(x) and x >= 0 for x in (price, size)):
            raise ValueError('Invalid book level')
        if price < price_floor:
            continue
        take = min(remaining, size)
        value += take * price
        remaining -= take
        if remaining <= 1e-8:
            break
    return {'quoted_shares': shares - remaining, 'unquoted_shares': remaining,
            'indicative_gross_proceeds': value,
            'note': 'Snapshot estimate before fees; neither an order nor guaranteed proceeds.'}
