# Project status — October 23, 2026

## Current live iteration

The operator explicitly approved the cash/manual settings and deployment after review. Release `2a65e3e` activated October 22 at 10:38 PM Eastern: cash budgets excluding pending/unknown BUYs, expiring deferrals, optional external-sale attribution/BUY pauses, structured Combo detection/explicit skips, holdings/book review and local health reporting. Reserve is zero pending evidence for a fixed percentage. The deployed source passed all 105 local/VPS tests. See [checklist](ITERATION_CHECKLIST.md) and [control behavior](COPY_CONTROLS.md).

At the operator's request, automatic external-sale pauses were disabled October 23 at 12:45 AM Eastern. Fresh eligible target BUYs may reopen an asset after manual sales, within existing cash, sizing and price limits. No automatic pauses existed to clear. Systemd and the shared `.env` both set `MANUAL_EXIT_PROTECTION=0`; trading source remains `2a65e3e`. The updated local defaults and regression pass all 106 tests. Explicit operator pauses remain available. Lower prices alone do not trigger purchases, and processed sources are not replayed.

Authenticated readiness, running-process overrides, healthy polling and Combo coverage, and the five-minute health timer are verified. No restarts or health issues were observed after the policy change. All 154 cleanup candidates received successful live share/book checks; indicative gross proceeds are about $770 versus $805 marked excess, with unquoted remainder and fees excluded. No cleanup orders were submitted. Subsequent journal inspection verified three natural BUYs in filled status since this controls release activated; no test trade was forced. See [deployment notes](DEPLOYMENT_NOTES.md) for recovery and runtime paths.

## Objective and authorization

Improve copying fidelity and diagnose the gap versus the target trader. The operator approved implementation and agent-managed VPS deployment, then enrolled an SSH public key. Deployment completed on October 22, 2026 at 9:18 PM Eastern. No higher percentage cap, higher minimum buy, automatic portfolio top-up, or automatic redemption has been enabled.

The operator requests that completed code and documentation changes be committed and pushed to GitHub. Credentials, raw trading logs and live state remain private. See [historical log review](HISTORICAL_REVIEW.md) for the April–October forensic findings: actual insufficient BUY balance, no-share SELL skips consistent with manual exits, historical execution bugs, and a newly identified Combo compatibility gap. This review did not change the live trading rules.

## Implemented and deployed

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

Live code is commit `2a65e3e5630b2807b309ff34603d9eaaf6fe62b2` in `/root/polymarket-deploy/releases/2a65e3e`. Systemd uses this release's own virtual environment and working directory. Previous API v2 release `dfc8cf0` and the original checkout at `/root/polymarket-copy-trading-bot` (`2cdc997`) are retained; neither is the active code path.

Effective service overrides: `POLL_INTERVAL_SEC=5`, `COPY_ORDER_TYPE=FAK`, `RECONCILE_ON_START=0`, zero fixed cash reserve, `CASH_DEFERRAL_SEC=300`, `MANUAL_EXIT_PROTECTION=0`. Original credentials and trade-size limits remain in the shared original `.env`. State and logs are shared from the original checkout. The 407-source migration seed belongs to the earlier 9:18 PM API v2 deployment; this iteration did not reseed historical signals.

The consistent pre-activation backup is `/root/polymarket-deploy/checkpoints/before-controls-20261023T023827Z`. The subsequent policy-change backup is `/root/polymarket-deploy/checkpoints/before-reentry-policy-20261023T044528Z`; current validated recovery source/configuration is `/root/polymarket-deploy/checkpoints/api-v2-controls-validated-2a65e3e-no-external-pauses`. The active manifest is `/root/polymarket-deploy/deployment.json`. Secret-bearing backups remain private on the VPS.

The local `.env` was observed with `TEST_MODE=1` and `POLL_INTERVAL_SEC=45`; it is not the production configuration and was not changed. The server's present configuration must be read before deployment.

Polymarket's current Data API migration guide announces v1 retirement on **October 24, 2026**. The tested read-path migration is deployed.

## Known limits and next evaluation

- Target cash is not part of the sizing denominator; the $5 floor changes portfolio weights.
- SELLs mirror proportional dollar notional, not a measured percentage of the target's original position.
- Legacy processed tx hashes suppress all associated new-style keys; missed historical maker legs cannot be safely replayed automatically.
- The recent feed is deliberately bounded; downtime beyond that window may require account review.
- Accepted orders with no returned ID and interrupted posts stay blocked for explicit exchange reconciliation. This favors preventing duplicate purchases over guessing a retry.
- FAK partials and zero fills are terminal for the source group. Residual quantities are measured, not blindly resubmitted.
- Pending fills block subsequent activity in that asset until settled. Read failures do not release the block.
- Old trade CSVs describe intentions and cannot establish actual historical executions.
- Combined-market trades are not handled by a dedicated Combo RFQ executor. Historical `market not found` errors overwhelmingly followed titles containing `AND`; investigate market-type and valuation coverage before claiming full target coverage.
- A read-only report can measure account activity now, but exact bot attribution starts with the new journal. Manual profit-taking cannot be inferred from public trades.
- No tests place live orders. Server readiness, quote/book consistency and an existing confirmed-trade parse are verified. Fresh post-deployment BUY and SELL executions have both reached confirmed status.

## Re-entry workflow

Read this file, README, deployment notes, and ops notes. Inspect `git status`. Review the recorded local validation and generated report if available. Obtain current server status/configuration without restarting the service before making deployment decisions.

## Local validation and measured baseline

- 73 offline tests passed with the repository's dependency constraints in a fresh Python 3.13 virtual environment. The original laptop `.venv` is an incompatible CPU build and was not replaced.
- Tests include real signing/serialization with the pinned SDK and a fake HTTP transport, as well as recovery after a committed order whose processed-state update was interrupted.
- Dependency consistency, Python compilation, local config-format checks and whitespace checks passed. No live orders were placed by this work.
- A public seven-day review was generated at `logs/performance_review.md` and `.json` (gitignored). The latest sample contains 2,042 target transaction/asset/side groups, of which 380 appear in the taker-only feed, and 143 groups on the operator account. Feed visibility was about 19% before the maker-filter fix; this is not a copy success rate.
- Five deposits in the sampled window total $731.60. They are reported as capital movements. Same-time daily PnL changes are included without inventing a percentage return or attributing manual activity to the bot.
- No production order journal is available on this laptop; exact historical bot attribution remains unavailable; current VPS configuration was subsequently verified during deployment.

## Deployment automation and rollback follow-up

The initial SSH key enrollment failed before installing the key. Password-only `ssh-copy-id` succeeded, and unattended SSH was verified. The agent inspected, backed up, and deployed the VPS. No additional terminal setup is currently needed.

A verified source-only checkpoint of the prior `2cdc997` revision is saved under `checkpoints/pre-upgrade-2026-10-22/`. The checkpoint tool and its tests are included in the upcoming committed revision. See [CHECKPOINTS.md](CHECKPOINTS.md) for the release and rollback procedure. Current local validation: 77 offline tests pass.

Cash availability is an alternative explanation for missed BUYs. Fully deployed funds can prevent entries even when the feed is complete. The 19% figure measures old feed visibility only; it does not attribute the account's underperformance. Inspect live-server balance/allowance failures and exit history before attributing the gap to one cause. Missing SELLs of held shares require a separate explanation from a lack of buying cash.

## October 22 deployment verification

- All 77 tests and dependency checks passed in the VPS's native Python 3.11 environment before activation.
- Authenticated API credentials and collateral reads passed; cash was approximately $547 during staging, subsequently $561 in live logs.
- No `not enough balance` messages were found in the preceding 24-hour log sample; liquidity/FOK failures were present. This does not establish cash availability over earlier periods.
- A read-only startup reconciliation preview found 154 candidates totaling about $808 in marked excess value. Bulk startup reconciliation is deliberately disabled in the live override pending a separate holdings review. Normal new-trade SELL copying remains active.
- Live midpoint and bid/ask helpers matched an actual order book. The confirmed-fill parser correctly read an existing settled taker execution.
- The new process is active with no observed restarts or poll-cycle errors. Fresh target activity subsequently produced a confirmed SELL and a confirmed BUY. The BUY succeeded on a later poll after an initial liquidity rejection. No extra test trade was forced.
- Preserve the original shared `.env`, current processed state and current SQLite order journal. Do not use an old JSON state backup to replay live orders.

The server's validated compatible checkpoint is `/root/polymarket-deploy/checkpoints/api-v2-validated-dfc8cf0`. It retains the verified source archive and deployment manifest; the release's native environment remains installed. Both BUY and SELL execution confirmations establish this as the recovery baseline for future compatible code updates.
