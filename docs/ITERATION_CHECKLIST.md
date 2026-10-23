# Bot iteration checklist

Authorized October 22, 2026: implement the recommendations, preserve recovery checkpoints, save completed code and documentation to GitHub, and deploy validated changes to the VPS.

- [x] Cash-aware BUY budget, including pending/uncertain orders and multiple orders in one polling cycle.
- [x] Configurable cash reserve and explicit low-cash reporting.
- [x] Durable, bounded low-cash deferrals; funding must not silently replay stale entries.
- [x] Persistent manual-exit protection with an inspect/resume workflow; normal SELLs remain available.
- [x] Distinguish bot fills from account activity using journaled settlement identities and quantities, including mixed bot/external settlement batches.
- [x] Identify Combo markets from structured identifiers; review current official execution documentation.
- [x] Include Combo holdings in account review and explain cost-basis versus market-value limitations.
- [x] Stop repeated ordinary-market submissions for unsupported Combo/closed markets.
- [x] Record reason-specific copy decisions and confirmed fill outcomes; expose a read-only health report.
- [x] Review current startup-cleanup candidates, manual-position conflicts and indicative bid proceeds; record the decision.
- [x] Preserve current sizing caps and price guards; document remaining sizing/feed/attribution limits.
- [x] Test order lifecycle, affordability, manual-exit attribution, restart recovery and failure handling.
- [x] Verify current credentials/quotes and readiness without forcing test trades.
- [x] Save a consistent private VPS checkpoint; stage an isolated release and retain current processed state/journal.
- [x] Commit and push source/documentation to GitHub, deploy, verify service/health checks, and record recovery instructions.
- [ ] Observe the next natural copied order under the new controls; no test trade will be forced to satisfy this checkbox.

Progress and material choices are recorded here as they are verified. A reviewed limitation must include its reason and operational behavior, rather than being silently omitted.

## Choices and validation

The user asked for a logical/statistical cash policy and explicit confirmation of manual-exit behavior, then approved the concrete settings and deployment: no fixed reserve, fresh affordability limits, five-minute bounded BUY deferrals, persistent per-asset BUY pause after a newly detected external settled sale, and continued normal SELLs. No measured return benefit is claimed. Release `2a65e3e` activated at 10:38 PM Eastern on October 22.

All 105 offline tests pass locally and on the VPS. Compilation, dependency consistency, whitespace checks and authenticated live readiness pass. Source commit `2a65e3e5630b2807b309ff34603d9eaaf6fe62b2` runs at `/root/polymarket-deploy/releases/2a65e3e` with its own native environment. The archive SHA-256 is `e9616d4bf4e556908614ea34e3f23a6e4930ae730f222ea1fa34dc3afde34a29`. A verified local checkpoint is `checkpoints/cash-controls-2a65e3e-2026-10-22`.

The separate Combo requester workflow was reviewed: it requires RFQ/Exchange v3 execution and currently exposes YES-side requests. This release intentionally records unsupported Combos without submitting them as ordinary CLOB orders. Dedicated live RFQ execution is not enabled or claimed as complete. See [control behavior and limits](COPY_CONTROLS.md).

The fresh holdings snapshot has 154 potential ordinary-market sales (68 target-absent, 86 overweight), about $805.44 marked excess. All 154 share-balance/book reads succeeded. Available bids within the configured floor produced approximately $770.42 indicative gross proceeds; not every requested share had a bid, and fees are excluded. This is a sequence of snapshots, not guaranteed executable proceeds. The target has 627 retained Combo holdings, all `RESOLVED_LOSS`, while this account has none. This remaining-holdings sample can omit redeemed positions; it does not establish Combo strategy PnL or a benefit from copying/skipping Combos. No sales have been submitted by the review. Bulk cleanup stays off: current snapshot mismatches do not establish manual intent or an expected-return benefit from liquidating them.

Private server reports are `/root/polymarket-deploy/reviews/holdings-2a65e3e.json` and `staging-2a65e3e.json`. The consistent pre-activation checkpoint is `/root/polymarket-deploy/checkpoints/before-controls-20261023T023827Z`; validated recovery source/configuration is `/root/polymarket-deploy/checkpoints/api-v2-controls-validated-2a65e3e`. The original shared credentials, processed state and order journal were retained; no source IDs were reseeded. Current process overrides match the approved settings, the service has zero restarts, polling and both activity/Combo observers are healthy, and the automatic health check reports no issues. The five-minute health timer is active. No bulk sale was submitted. At the 10:44 PM Eastern verification, no new natural order had been submitted since this activation; the new journal/health snapshots will capture subsequent activity.
