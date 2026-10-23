# Cash, manual exits and copy coverage

## Approved live settings

- No fixed reserve: `CASH_RESERVE_FRACTION=0`, `CASH_RESERVE_USD=0`. There is no measured evidence that a fixed 10% reserve improves returns. The reserve remains configurable for a later evidence-based decision.
- A BUY must fit both a fresh cash read minus active BUY budgets and the remaining budget in the current polling cycle. Pending or unknown orders reserve their full requested budget. This can temporarily underestimate cash; it avoids reusing unsettled funds.
- Unaffordable BUYs are deferred without posting, increasing rejection counters or invoking the smaller fallback. Cash, quote, pending-order and account-activity BUY delays expire after `CASH_DEFERRAL_SEC=300`, including across restarts. A deposit after that deadline does not replay the delayed source. Normal price/age guards still apply within the window.
- `MANUAL_EXIT_PROTECTION=false`: manual/external sales do not pause later BUYs. A fresh eligible target BUY can reopen the same asset, subject to the usual cash, sizing and entry guards. A lower price alone does not trigger a purchase. Previously processed signals are not replayed.
- Bulk startup cleanup remains disabled. Review proposals do not authorize or submit sales.

Release `2a65e3e` activated October 22 at 10:38 PM Eastern. At the operator's request, automatic external-sale pauses were disabled October 23 at 12:45 AM Eastern (`2026-10-23T04:45:28Z`). The existing feature flag was set to zero in both systemd and the shared server environment; the tested trading code was retained. No existing automatic pauses needed clearing. Runtime, health reporting and the new recovery checkpoint were verified with `MANUAL_EXIT_PROTECTION=0`; the bot completed successful polls with no health issues. The local suite passes 106 tests, including a fresh-BUY regression with external-sale monitoring disabled. Explicit operator-requested asset pauses remain available through the CLI.

## Manual attribution and limits

This optional observer is disabled under the current policy. The following describes its behavior if explicitly re-enabled; disabled monitoring does not gate BUYs on account-activity reads or create automatic pauses.

The public on-chain wallet feed captures settled sales, including browser trades that another API credential may not expose. Transaction/asset identities and sold quantities are compared with journaled bot fills. A settlement batch can contain both bot and external orders, so identity alone is insufficient; excess sold quantity triggers protection. An active/unknown bot SELL delays classification; it does not get guessed as manual. Detection starts at the first activation of this observer, rather than labeling old unattributed trades as manual.

Account activity is checked every 30 seconds and immediately before each BUY. Public indexing and settlement introduce delay, so automatic detection cannot guarantee an instantaneous pause when a user clicks Sell. Activity read failures defer BUYs; they do not turn off normal SELL copying. A complete overlapping lookback handles service downtime; unresolved sale attribution keeps its older lookback until resolved. Sales indexed more than an hour late after a successful scan may require account review.

An external sale means not attributed to this bot. It can originate from the user, another program or another credential; the code does not claim to identify the person/interface. All bot instances must retain the shared journal. Never restore an old journal to force attribution.

## Inspect and change a pause

The agent can run these commands on the VPS from the active release; the operator does not need to edit code:

```bash
.venv/bin/python scripts/control_bot.py status --hours 24
.venv/bin/python scripts/control_bot.py pause ASSET_ID --reason 'Operator requested a pause'
.venv/bin/python scripts/control_bot.py resume ASSET_ID --reason 'Operator approved new buys'
```

Resuming does not remove remembered sale identities, so an old sale cannot immediately reapply the pause. A new external sale can pause the asset again only if automatic protection is explicitly re-enabled. Pauses are account-wide per asset; decisions and observer cursors also record the target. Simulation uses separate control state.

## Combo compatibility result

The current official [Combo Requester guide](https://docs.polymarket.com/trading/combos/requesters) requires a dedicated RFQ gateway, quote acceptance, Exchange v3 signing and execution reconciliation. Requests currently specify the YES side; this is not a general replacement for ordinary CLOB BUY/SELL orders. Ambiguous RFQ creation also has no idempotency key or unknown-request lookup. Enabling an unvalidated partial executor would add financial risk and would not provide complete target coverage.

This release therefore records and skips identified Combos before ordinary submission. A registry uses the separate held-Combo endpoint, and structured protocol candidates are quarantined. A random CTF hash starting `03`, or a title containing `AND`, alone is insufficient for classification. A definitive ordinary-metadata 404 is handled once with an explicit unsupported-market decision instead of repeated order attempts. Other metadata failures remain distinguishable from definitive rejection.

The [official Data API schema](https://data-api.polymarket.com/v2/openapi.json) defines `/v2/value` as single-market holdings marked to market plus unresolved Combos at cost basis. The total must not be described as a wholly marked-to-market NAV, and Combo basis must not be added a second time. Account review now fetches Combo holdings separately, retaining their lifecycle status, legs and basis. It does not estimate Combo liquidation prices from the product of leg prices.

Dedicated live Combo copying is a documented coverage limitation. It requires a separately validated quote/signing/settlement integration. Unsupported signals are intentionally recorded as skipped; they are not counted as copied trades or silently replayed after a future upgrade.

## Monitoring and evidence

`state/controls.sqlite3` records source/reason decisions, bounded deferrals, observer status and manual pauses. The authoritative execution journal remains `state/orders.sqlite3`. Both survive release changes and remain private.

The status command reports source/reason counts separately from repeated observations, order outcomes, confirmed fill prices and partial-fill fractions, active-order age, cash availability, paused assets and Combo coverage. Decision categories can overlap for one source and must not be summed as unique missed trades. Quotes and execution amounts are before separately charged fees. No percentage-return claim is inferred.

`scripts/check_bot_health.py --output logs/health_latest.json` checks the service, poll heartbeat, unresolved/old orders and activity observer. It never restarts the bot or submits orders. An automatic health-check failure is a reason to inspect state, not to replay orders. Low cash alone is not a process failure. Existing configured webhook alerts remain throttled; installing a timer does not create a new external recipient.

## Retained limits

The target's cash is unknown; existing sizing uses target position value. The $5 BUY floor alters proportional weights and remains unchanged. The 10% single-order cap and price guards remain unchanged. This is not full portfolio mirroring. Recent source polling is bounded; historical replay, automatic top-up purchases after funding, automatic redemption and bulk liquidation remain separate decisions. No fixed cash policy or execution change has been proven to improve investment returns.

Rollback must preserve the latest controls database as well as the processed IDs and order journal. The earlier `dfc8cf0` release does not enforce these new controls; inspect active pauses before considering that code as a fallback. The validated `2a65e3e` recovery checkpoint is the baseline for subsequent control-preserving rollbacks; see checkpoint notes for its path.
