# Bot iteration checklist

Authorized October 22, 2026: implement the recommendations, preserve recovery checkpoints, save completed code and documentation to GitHub, and deploy validated changes to the VPS.

- [x] Cash-aware BUY budget, including pending/uncertain orders and multiple orders in one polling cycle.
- [x] Configurable cash reserve and explicit low-cash reporting.
- [x] Durable, bounded low-cash deferrals; funding must not silently replay stale entries.
- [x] Manual-exit policy reviewed and applied: automatic external-sale pauses disabled at operator request; explicit CLI pauses/resumes remain available and normal SELLs continue.
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
- [x] Observe natural copied orders under the new controls: three BUYs reached filled status; no test trade was forced.

Progress and material choices are recorded here as they are verified. A reviewed limitation must include its reason and operational behavior, rather than being silently omitted.

## Choices and validation

The user initially approved no fixed reserve, fresh affordability limits, five-minute bounded BUY deferrals, automatic pauses after external settled sales, and continued normal SELLs. They then requested allowing later target BUYs after manual exits. That revised policy was applied October 23 at 12:45 AM Eastern: `MANUAL_EXIT_PROTECTION=0` in systemd and the shared `.env`, with the tested `2a65e3e` trading source retained. No active automatic pauses needed clearing, explicit operator pauses were preserved, and processed IDs/order history were not reset. The updated local suite passes 106 tests. Fresh polling, disabled monitoring in both processes, clean health and the timer were verified. No measured return benefit is claimed.

At release activation, all 105 offline tests passed locally and on the VPS, along with compilation, dependency consistency, whitespace checks and authenticated live readiness. Source commit `2a65e3e5630b2807b309ff34603d9eaaf6fe62b2` runs at `/root/polymarket-deploy/releases/2a65e3e` with its own native environment. The archive SHA-256 is `e9616d4bf4e556908614ea34e3f23a6e4930ae730f222ea1fa34dc3afde34a29`. A verified local checkpoint is `checkpoints/cash-controls-2a65e3e-2026-10-22`. Current local validation is 106 tests after the re-entry regression; see the [session handoff](SESSION_HANDOFF.md) for future conversation context and next evaluation.

The separate Combo requester workflow was reviewed: it requires RFQ/Exchange v3 execution and currently exposes YES-side requests. This release intentionally records unsupported Combos without submitting them as ordinary CLOB orders. Dedicated live RFQ execution is not enabled or claimed as complete. See [control behavior and limits](COPY_CONTROLS.md).

The fresh holdings snapshot has 154 potential ordinary-market sales (68 target-absent, 86 overweight), about $805.44 marked excess. All 154 share-balance/book reads succeeded. Available bids within the configured floor produced approximately $770.42 indicative gross proceeds; not every requested share had a bid, and fees are excluded. This is a sequence of snapshots, not guaranteed executable proceeds. The target has 627 retained Combo holdings, all `RESOLVED_LOSS`, while this account has none. This remaining-holdings sample can omit redeemed positions; it does not establish Combo strategy PnL or a benefit from copying/skipping Combos. No sales have been submitted by the review. Bulk cleanup stays off: current snapshot mismatches do not establish manual intent or an expected-return benefit from liquidating them.

Private server reports are `/root/polymarket-deploy/reviews/holdings-2a65e3e.json` and `staging-2a65e3e.json`. The consistent pre-activation checkpoint is `/root/polymarket-deploy/checkpoints/before-controls-20261023T023827Z`; the policy-change backup is `/root/polymarket-deploy/checkpoints/before-reentry-policy-20261023T044528Z`. Current validated recovery source/configuration is `/root/polymarket-deploy/checkpoints/api-v2-controls-validated-2a65e3e-no-external-pauses`, which retains the revised policy on rollback. The original shared credentials, processed state and order journal were retained; no source IDs were reseeded. Current process overrides match the revised settings, the service has zero restarts, polling and Combo coverage are healthy, and the health check reports no issues. The five-minute health timer is active. No bulk sale was submitted. Subsequent journal inspection verified three natural filled BUYs and one rejected BUY attempt since the controls release activated.
