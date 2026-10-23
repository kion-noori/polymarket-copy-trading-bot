# Deployment Notes

## Current live release — cash/manual-exit iteration

Commit `2a65e3e5630b2807b309ff34603d9eaaf6fe62b2` runs in `/root/polymarket-deploy/releases/2a65e3e`, with a dedicated native virtual environment. All 105 tests pass locally and on the VPS; dependency consistency and authenticated read-only readiness pass. The operator explicitly approved the settings and deployment. Activation completed October 22, 2026 at 10:38:28 PM Eastern (`2026-10-23T02:38:28.596553+00:00`). Previous release `dfc8cf0` remains retained.

Verified process-level overrides: polling 5 seconds, FAK, `RECONCILE_ON_START=0`, `CASH_RESERVE_FRACTION=0`, `CASH_RESERVE_USD=0`, `CASH_DEFERRAL_SEC=300`, `MANUAL_EXIT_PROTECTION=1`. The service is active/running with zero restarts; successful polling, the manual activity observer and Combo registry are verified. The health report has no issues. No new natural order had been submitted at the 10:44 PM Eastern verification; no test trade was forced.

Archive `/root/polymarket-deploy/incoming/2a65e3e.tar.gz` has SHA-256 `e9616d4bf4e556908614ea34e3f23a6e4930ae730f222ea1fa34dc3afde34a29`. Verified local checkpoint: `checkpoints/cash-controls-2a65e3e-2026-10-22`. A consistent private backup was taken with the service stopped at `/root/polymarket-deploy/checkpoints/before-controls-20261023T023827Z`; it contains state, environment, previous service/dependency metadata and staging artifacts. The live `.env` contents were retained, and the release now shares the original live `state/` and `logs/`. No source IDs were reseeded. Backup directory mode 700 and environment file mode 600 were verified.

The release's health-service/timer templates were installed with the actual release path. `polymarket-bot-health.timer` is enabled and active; it runs every five minutes and writes `/root/polymarket-copy-trading-bot/logs/health_latest.json`. Health checks do not trade or automatically restart. `/root/polymarket-deploy/checkpoints/api-v2-controls-validated-2a65e3e` retains verified recovery source, release configuration and validation metadata. Preserve `controls.sqlite3` on rollback; earlier `dfc8cf0` code does not enforce new asset pauses. See [iteration checklist](ITERATION_CHECKLIST.md) and [control behavior](COPY_CONTROLS.md).

The full read-only review quoted all 154 startup-sale candidates without errors: about $805.44 marked excess and $770.42 indicative gross bid proceeds before fees, with some unfilled remainder. It submitted no orders. Bulk cleanup remains disabled.

## Previous API v2 release — October 22, 2026, 9:18 PM Eastern

- Verified key-based SSH: `root@216.238.91.62`.
- Previous commit: `dfc8cf0f1152f474f471047620aba45682b3e480`.
- Retained working directory: `/root/polymarket-deploy/releases/dfc8cf0`.
- Retained interpreter: `/root/polymarket-deploy/releases/dfc8cf0/.venv/bin/python`.
- Service: `polymarket-bot`; override file: `/etc/systemd/system/polymarket-bot.service.d/90-release.conf`.
- Effective overrides: polling 5 seconds, FAK copies, startup reconciliation disabled.
- Shared credentials: `/root/polymarket-copy-trading-bot/.env` (symlinked into the release).
- Shared state/logs: original checkout's `state/` and `logs/`, symlinked into the release.
- Original checkout and virtual environment remain untouched at commit `2cdc997` for recovery/inspection.
- Backup: `/root/polymarket-deploy/checkpoints/before-20261023T011809Z` (private, server only).
- Deployment manifest: `/root/polymarket-deploy/deployment.json`.

The release passed all 77 tests on the VPS, dependency validation and read-only authenticated readiness. Live quote parsing matched the order book, and an existing confirmed trade was parsed correctly. The process is active without observed cycle errors/restarts. Fresh post-deployment BUY and SELL orders both executed and reached confirmed status; the BUY succeeded after one liquidity rejection and a retry.

Before activation, 407 visible source groups were marked processed while the old bot was stopped. This avoided buying historical entries newly exposed by maker coverage. Startup reconciliation was left off after a preview identified about $808 across 154 potential sales. Review that batch separately before enabling bulk cleanup.

The `.env` file still contains its older polling/reconciliation values; systemd overrides take precedence. Read the running process/service configuration when assessing effective settings. No wallet identity, private key or sizing cap was changed.

The remaining sections retain historical context.

## Last Known Live Setup (historical; verified during April–May 2026)

- Provider: Vultr
- Region: Mexico City, MX
- VPS type: Shared CPU
- Plan: `vc2-1c-1gb`
- OS: Ubuntu 22.04 LTS
- Deploy path: `/root/polymarket-copy-trading-bot`
- Process manager: `systemd`
- Service name: `polymarket-bot`
- Python env: `/root/polymarket-copy-trading-bot/.venv`
- Run user: `root`

## Polymarket Checks

- VPS geoblock check from server returned `"blocked": false`
- Authenticated live readiness check passed
- Collateral balance read succeeded during setup
- Bot was switched from `TEST_MODE=1` to `TEST_MODE=0` after VPS validation

## Last Recorded Strategy / Runtime Choices

- `POLL_INTERVAL_SEC=15`
- `MAX_TRADE_AGE_SEC=0`
  This disables the pure age-based skip and relies on the other entry guards instead.
- `MAX_PCT_PER_TRADE=0.10`
- `MAX_TRADE_USD=0`
  This means there is no separate hard dollar cap beyond the percentage cap.
- `STARTUP_MODE=resume`
- `RECENT_TRADES_PAGE_SIZE=100`
- `RECENT_TRADES_MAX_PAGES=5`
- `MAX_BUY_PRICE=0.97`
- `MAX_SPREAD_FRACTION=0.12`
- `SIGNATURE_TYPE=2`
- Historical BUY retries widened by absolute price points; the local October update moves definitive retries to later polls.
- SELL sizing uses a dedicated exit path without the buy-side `MIN_NOTIONAL` floor.
- SELL orders are capped to actually held conditional-token shares before placement.
- Dust SELL remainders are skipped instead of posting invalid microscopic exits.
- Prior notes claimed both maker and taker coverage after removing the filter. Current docs show that omission defaults to taker-only; the October update explicitly sets `taker_only=false`.

## Important Notes

- The signer EOA and `FUNDER_ADDRESS` can be different when `SIGNATURE_TYPE=2`; that is expected.
- The bot is designed to skip SELLs when there is no matching held conditional-token balance.
- SELL-only catch-up batches now attempt an exit when held shares exist, instead of always being discarded.
- The bot does not auto-redeem resolved markets.
- The live server uses a root-based systemd service example, which is reflected in `deploy/polymarket-bot.service.example`.

## Secrets

- Do not store secrets in this file.
- Real values live only in `.env` on the operator machine and the VPS.

## Update Policy

When the live deployment changes materially, update this file with:

- provider / region / OS changes
- process manager or path changes
- meaningful env / strategy changes
- any notable operational decisions

## October 22, 2026 migration history

See [PROJECT_STATUS.md](PROJECT_STATUS.md). Local and VPS tests cover the v2 API migration, quote fixes, SELL quantity corrections, FAK partials and durable order recovery. The old Data API is scheduled to retire October 24.

The new default poll delay is 5 seconds. Existing server `.env` values override this default. Inspect them before choosing an interval. Keep the existing target, funder, keys and intended sizing settings. Do not copy the laptop `.env` over the server's file.

Before deployment, record the server commit and relevant nonsecret settings, back up the entire `state/` directory and `.env` on the server, stop the service, update dependencies in the service's virtual environment, and validate readiness. Preserve `state/seen_trades.json` and `state/orders.sqlite3`. Review existing `RECONCILE_ON_START` settings: corrected dust/quantity math can cause previously skipped excess positions to be sold on restart.

This update does not infer full portfolio alignment or automatically buy positions after a deposit. The controlled rollout and read-only fill-parser validation completed; fresh post-deployment BUY and SELL confirmations also completed.

Validated recovery checkpoint: `/root/polymarket-deploy/checkpoints/api-v2-validated-dfc8cf0`, containing source and deployment metadata. The installed release environment is retained. The pre-update private backup remains separate; current processed state and order journal must be retained during future code rollback.
