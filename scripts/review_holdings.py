"""Generate a private holdings and startup-cleanup review without placing orders."""
import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config
import copy_controls as controls
from data_api import get_positions, get_portfolio_value, get_combo_positions
from executor import get_client, get_collateral_balance_usdc, get_conditional_token_balance_shares
from holdings_review import build_plan, book_sale_estimate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--quote-all', action='store_true')
    args = parser.parse_args()
    cash = get_collateral_balance_usdc()
    mine, target = get_positions(config.FUNDER_ADDRESS), get_positions(config.TARGET_WALLET)
    my_nav = get_portfolio_value(config.FUNDER_ADDRESS) + cash
    target_value = get_portfolio_value(config.TARGET_WALLET)
    paused = [r['asset'] for r in controls.summary()['paused_assets']]
    report = build_plan(mine, target, my_nav, target_value, paused, config.RECONCILE_MIN_NOTIONAL)
    report.update(generated_at=time.time(), my_nav=my_nav, target_position_value=target_value, cash=cash,
                  combo_positions={'mine': get_combo_positions(config.FUNDER_ADDRESS),
                                   'target': get_combo_positions(config.TARGET_WALLET)})
    if args.quote_all:
        client = get_client()
        for row in report['candidates']:
            try:
                balance = get_conditional_token_balance_shares(row['asset'])
                if balance is None:
                    raise ValueError('Live share balance unavailable')
                row['clob_held_shares'] = balance
                book = client.get_order_book(row['asset'])
                floor = max(.01, row['reference_price'] * (1 - config.SELL_SLIPPAGE_FRACTION))
                row['book_snapshot'] = book_sale_estimate(min(balance, row['excess_shares']),
                    [(float(b.price), float(b.size)) for b in book.bids], floor)
            except Exception as exc:
                row['quote_error'] = type(exc).__name__
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2))
    print(json.dumps({'path': str(args.output), 'candidates': len(report['candidates']),
                      'marked_excess_usd': report['marked_excess_usd'], 'decision': report['decision']}))


if __name__ == '__main__':
    main()
