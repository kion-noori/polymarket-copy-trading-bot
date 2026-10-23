# Project status — October 22, 2026

## Objective and authorization

Improve copying fidelity and diagnose the gap versus the target trader. The operator approved local implementation, testing, and a read-only account comparison. VPS deployment remains a separate review step. No higher percentage cap, higher minimum buy, automatic portfolio top-up, or automatic redemption has been enabled.

## Implemented locally

- Data API v2 envelope, field normalization, cursor walks, explicit `taker_only=false`, rate-limit retries, and complete position snapshots.
- Transaction/asset/side identities, with legacy plain hashes honored to avoid replaying historical orders.
- Explicit SELL shares based on reference value, independent of the minimum execution price. Dust checks also use reference value.
- Correct JSON quote parsing and bid/ask side mapping. Temporary quote outages defer without consuming the source trade.
- Persistent SQLite order intents, pending-fill reconciliation, confirmed execution CSV, and no automatic repost after unknown submission outcomes.
- FAK as the ordinary-copy default. Partial fills are accepted; unfilled remainder is not automatically chased. Optional FOK and smaller fallback remain supported.
- One POST per attempt; definitive rejections retry on later polls with bounded price widening. Tick rounding stays within the configured BUY cap.
- Five-second default delay between completed polls; existing `.env` overrides remain authoritative.
- Sizing floor respects percentage and dollar caps; separate test/live state; atomic state writes; single-process lock.
- Read-only performance and order-inspection scripts. Journal-only bot attribution; public/manual activity remains separate.
- Execution SDK pinned to `py-clob-client-v2==1.2.1`. The unified SDK was reviewed but its full migration is deferred for independent validation.

## Deployment state

Local code has not been deployed to the VPS. The last historical deployment evidence is May 4, 2026, commit `2cdc997`. Do not present that historical evidence as confirmation of current server health.

The local `.env` was observed with `TEST_MODE=1` and `POLL_INTERVAL_SEC=45`; it is not the production configuration and was not changed. The server's present configuration must be read before deployment.

Polymarket's current Data API migration guide announces v1 retirement on **October 24, 2026**. Prioritize deploying the tested read-path migration after review.

## Known limits and next evaluation

- Target cash is not part of the sizing denominator; the $5 floor changes portfolio weights.
- SELLs mirror proportional dollar notional, not a measured percentage of the target's original position.
- Legacy processed tx hashes suppress all associated new-style keys; missed historical maker legs cannot be safely replayed automatically.
- The recent feed is deliberately bounded; downtime beyond that window may require account review.
- Accepted orders with no returned ID and interrupted posts stay blocked for explicit exchange reconciliation. This favors preventing duplicate purchases over guessing a retry.
- FAK partials and zero fills are terminal for the source group. Residual quantities are measured, not blindly resubmitted.
- Pending fills block subsequent activity in that asset until settled. Read failures do not release the block.
- Old trade CSVs describe intentions and cannot establish actual historical executions.
- A read-only report can measure account activity now, but exact bot attribution starts with the new journal. Manual profit-taking cannot be inferred from public trades.
- No tests place live orders. Authenticated readiness and a controlled deployment still need verification on the actual server.

## Re-entry workflow

Read this file, README, deployment notes, and ops notes. Inspect `git status`. Review the recorded local validation and generated report if available. Obtain current server status/configuration without restarting the service before making deployment decisions.

## Local validation and measured baseline

- 73 offline tests passed with the repository's dependency constraints in a fresh Python 3.13 virtual environment. The original laptop `.venv` is an incompatible CPU build and was not replaced.
- Tests include real signing/serialization with the pinned SDK and a fake HTTP transport, as well as recovery after a committed order whose processed-state update was interrupted.
- Dependency consistency, Python compilation, local config-format checks and whitespace checks passed. No live orders were placed by this work.
- A public seven-day review was generated at `logs/performance_review.md` and `.json` (gitignored). The latest sample contains 2,042 target transaction/asset/side groups, of which 380 appear in the taker-only feed, and 143 groups on the operator account. Feed visibility was about 19% before the maker-filter fix; this is not a copy success rate.
- Five deposits in the sampled window total $731.60. They are reported as capital movements. Same-time daily PnL changes are included without inventing a percentage return or attributing manual activity to the bot.
- No production order journal is available on this laptop; exact historical bot attribution and current VPS configuration remain unverified.

## Deployment automation and rollback follow-up

The operator asked for agent-managed VPS deployment and checkpoints. A BatchMode SSH access check reached `216.238.91.62` but authentication was rejected. No remote state or service was changed. The operator is enrolling their existing public key with `ssh-copy-id`; retry unattended access after they confirm completion.

A verified source-only checkpoint of the prior `2cdc997` revision is saved under `checkpoints/pre-upgrade-2026-10-22/`. The checkpoint tool and its tests are included in the upcoming committed revision. See [CHECKPOINTS.md](CHECKPOINTS.md) for the release and rollback procedure. Current local validation: 77 offline tests pass.

Cash availability is an alternative explanation for missed BUYs. Fully deployed funds can prevent entries even when the feed is complete. The 19% figure measures old feed visibility only; it does not attribute the account's underperformance. Inspect live-server balance/allowance failures and exit history before attributing the gap to one cause. Missing SELLs of held shares require a separate explanation from a lack of buying cash.
