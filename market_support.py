"""Keep Combo positions out of the ordinary CLOB execution path."""
import time

import config
import copy_controls as controls
from data_api import get_combo_positions


def refresh_registry(now=None):
    now = time.time() if now is None else now
    previous = controls.get_meta('combo_registry', {})
    if now - previous.get('checked_at', 0) < 120:
        return
    try:
        mine = get_combo_positions(config.FUNDER_ADDRESS)
        target = get_combo_positions(config.TARGET_WALLET)
        controls.set_meta('combo_registry', {
            'checked_at': now, 'ok': True,
            'conditions': sorted({r['combo_condition_id'].lower() for r in mine + target}),
            'my_positions': len(mine), 'target_positions': len(target),
            'my_entry_basis': sum(float(r['entry_cost_usdc']) for r in mine if r['status'] == 'OPEN'),
            'target_entry_basis': sum(float(r['entry_cost_usdc']) for r in target if r['status'] == 'OPEN')})
    except Exception:
        controls.set_meta('combo_registry', {**previous, 'checked_at': now, 'ok': False})


def unsupported_reason(trade):
    condition = str(trade.get('conditionId') or trade.get('condition_id') or '').lower()
    known = controls.get_meta('combo_registry', {}).get('conditions', [])
    if trade.get('combo_condition_id') or condition in known or str(trade.get('market_type', '')).lower() == 'combo':
        return 'combo_requires_rfq'
    # A random CTF hash can begin 03. Never classify on that prefix alone.
    # A matching condition prefix, Position ID module and outcome layout is a
    # protocol candidate; refuse ordinary signing until metadata is verified.
    try:
        position = int(trade.get('asset') or trade.get('token_id') or '')
        if condition.startswith('0x03') and position >> 248 == 3 and position & 255 in (0, 1):
            return 'combo_protocol_candidate'
    except (ValueError, TypeError):
        pass
    return None
