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
- [ ] Review current startup-cleanup candidates, manual-position conflicts and expected proceeds; record the decision.
- [x] Preserve current sizing caps and price guards; document remaining sizing/feed/attribution limits.
- [x] Test order lifecycle, affordability, manual-exit attribution, restart recovery and failure handling.
- [ ] Verify current credentials/quotes and readiness without forcing test trades.
- [ ] Save a consistent private VPS checkpoint; stage an isolated release and retain current processed state/journal.
- [ ] Commit and push source/documentation to GitHub, deploy, verify service/first natural execution activity, and record rollback commands.

Progress and material choices are recorded here as they are verified. A reviewed limitation must include its reason and operational behavior, rather than being silently omitted.

## Choices and validation

The user asked for a logical/statistical cash policy and explicit confirmation of manual-exit behavior. Proposed activation: no fixed reserve, fresh affordability limits, five-minute bounded BUY deferrals, persistent per-asset BUY pause after a newly detected external settled sale, and continued normal SELLs. No measured return benefit is claimed. Preparation is authorized; activation of these settings awaits that confirmation.

All 105 offline tests pass locally. Compilation, dependency consistency and whitespace checks pass. The 103-test candidate also passed on the VPS after isolating tests from the real `.env`; final changes clarify decision units and parse the pinned SDK's raw book dictionaries. The separate Combo requester workflow was reviewed: it requires RFQ/Exchange v3 execution and currently exposes YES-side requests. This release intentionally records unsupported Combos without submitting them as ordinary CLOB orders. Dedicated live RFQ execution is not enabled or claimed as complete. See [control behavior and limits](COPY_CONTROLS.md).

The fresh holdings snapshot has 154 potential ordinary-market sales (68 target-absent, 86 overweight), about $805 marked excess. The target has 627 retained Combo holdings, all `RESOLVED_LOSS`, while this account has none. This remaining-holdings sample can omit redeemed positions; it does not establish Combo strategy PnL or a benefit from copying/skipping Combos. No sales have been submitted by the review.
