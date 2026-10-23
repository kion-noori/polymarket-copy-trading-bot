# Session handoff — October 23, 2026

This is the starting point for a future conversation. It summarizes recorded work, rather than asserting that the server is still in the same state. Inspect Git and read current VPS status before making operational changes. Times below use America/New_York unless marked UTC.

## Operator preferences and decisions

- The goal is better copying fidelity and evidence about the performance gap versus the target trader. Increased returns have not been established by these changes.
- Save completed code and documentation to GitHub. The operator prefers the agent to manage code and VPS deployments without requiring manual coding.
- Agent-managed SSH deployment is authorized within the agreed scope. Confirm proposed new trading policies before activation unless already explicitly authorized.
- Manual profit-taking must allow a later fresh eligible target BUY of the same asset. Automatic external-sale pauses were explicitly disabled; retain this preference on deployment and rollback. Explicit operator-requested CLI pauses remain available.
- Keep no fixed cash reserve, account for pending BUY budgets, and expire cash/quote/pending/activity BUY deferrals after five minutes. Preserve existing sizing and price limits.
- Bulk startup cleanup and live Combo execution remain disabled. Funding the account or a lower market price alone does not trigger catch-up purchases.

## Completed work and last verified state

API v2 migration, maker/taker coverage, SELL share sizing, quotes/ticks, FAK partials, persistent order recovery, cash controls, structured Combo skips, a holdings review and five-minute local health checks are implemented. The forensic review found actual historical insufficient BUY balance and several independent execution problems. Manual sales plausibly explain some no-share SELL skips; the evidence does not establish a precise bot-only ROI or one cause for the entire performance gap.

The manual-sale policy update was saved and pushed in `05367b4` (`Allow fresh target buys after manual exits`). It changes future source defaults/examples and adds a regression. The VPS uses the existing release's supported configuration flag; its trading source was not replaced. Later documentation commits are available in `git log`.

| Item | Last verified value |
|---|---|
| SSH | `root@216.238.91.62`, key authentication working |
| Bot service | `polymarket-bot`, systemd |
| Live source | `2a65e3e5630b2807b309ff34603d9eaaf6fe62b2` |
| Working directory | `/root/polymarket-deploy/releases/2a65e3e` |
| Interpreter | Active release's `.venv/bin/python` |
| Configuration change | October 23, 12:45 AM Eastern; `2026-10-23T04:45:28Z` |
| Poll / order / cleanup | `POLL_INTERVAL_SEC=5`, `COPY_ORDER_TYPE=FAK`, `RECONCILE_ON_START=0` |
| Cash policy | Both reserve settings `0`; `CASH_DEFERRAL_SEC=300` |
| Manual-sale policy | `MANUAL_EXIT_PROTECTION=0` in systemd and shared `.env` |
| Health timer | `polymarket-bot-health.timer`, every five minutes |
| Validation | 106 local tests; deployed source passed 105 local/VPS tests at activation |

After the configuration change, a fresh successful poll, active service/timer, zero restarts and no health issues were verified. No existing automatic pauses needed clearing. Later journal inspection verified three filled BUYs and one rejected BUY attempt since the controls release's original activation at `2026-10-23T02:38:28Z`. These observations are not a claim about future health, returns or re-entry after a particular manual sale. No test trade was forced.

The release symlinks `.env`, `state/` and `logs/` to `/root/polymarket-copy-trading-bot`. The original checkout remains at older source and is not the active code path. A pull there will not deploy the bot. Systemd overrides take precedence over `.env`; the separate health process reads the shared `.env` and needs matching policy settings.

## Recovery and private records

- Current recovery bundle: `/root/polymarket-deploy/checkpoints/api-v2-controls-validated-2a65e3e-no-external-pauses`.
- Consistent private backup before the policy change: `/root/polymarket-deploy/checkpoints/before-reentry-policy-20261023T044528Z`.
- Deployment manifest: `/root/polymarket-deploy/deployment.json`.
- Health snapshot: `/root/polymarket-copy-trading-bot/logs/health_latest.json`.
- Preserve the latest `state/seen_trades.json`, `state/orders.sqlite3` and `state/controls.sqlite3`. Restoring an old state snapshot after live trading can replay purchases.

The earlier recovery bundle without `-no-external-pauses` would re-enable the previous automatic-pause policy. Use the current [recovery procedure](CHECKPOINTS.md). Raw reports, credentials and state stay private and out of Git.

## Resume procedure and next work

1. Read `git status --short` and recent commits. Read [project status](PROJECT_STATUS.md), [deployment notes](DEPLOYMENT_NOTES.md) and [ops commands](OPS_NOTES.md) for the relevant task.
2. For server work, inspect current service working directory/interpreter, effective nonsecret settings, recent logs, health snapshot and pending/unknown orders without restarting first. Do not treat this document's snapshots as live readings.
3. For code changes, use a compatible local environment. The Mac's existing `.venv` has an incompatible CPU build; the last working test interpreter was `/tmp/polymarket-review-venv/bin/python`. If that temporary environment is gone, create a compatible environment from `requirements-dev.txt`.
4. The current iteration checklist is complete. The next evaluation is to collect confirmed fills and reason-specific skips/rejections over a useful window, account for deposits/manual activity, and measure remaining copying gaps before proposing another trading change.
5. Dedicated Combo execution, target-cash-aware sizing, automatic redemption, bulk cleanup and automatic portfolio top-ups are unresolved capabilities or separate policy choices. This list does not authorize activation.

The [API reference](POLYMARKET_API_REFERENCE.md) records official documentation checked October 22, including the announced October 24 Data API v1 retirement. Recheck official documentation when changing integrations. Avoid confusing historical retry counts, feed visibility or retained Combo holdings with missed-profit estimates.

## Document map

- [README](../README.md): product behavior, setup and settings.
- [Project status](PROJECT_STATUS.md): implemented work, current deployment and historical validation.
- [Copy controls](COPY_CONTROLS.md): cash, re-entry, optional attribution and Combo limitations.
- [Iteration checklist](ITERATION_CHECKLIST.md): completed release scope and validation.
- [Deployment notes](DEPLOYMENT_NOTES.md), [ops commands](OPS_NOTES.md), [checkpoints](CHECKPOINTS.md): live operations and recovery.
- [Design notes](DESIGN_NOTES.md), [API reference](POLYMARKET_API_REFERENCE.md): implementation and integration context.
- [Historical review](HISTORICAL_REVIEW.md): retained log evidence and limits of causal attribution.
