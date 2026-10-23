# Deployment Notes

This file is a lightweight snapshot of the historical deployment setup so future sessions can re-anchor quickly.

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

## October 22, 2026 local update — not deployed

See [PROJECT_STATUS.md](PROJECT_STATUS.md). Local tests cover the v2 API migration, quote fixes, SELL quantity corrections, FAK partials and durable order recovery. The old Data API is scheduled to retire October 24.

The new default poll delay is 5 seconds. Existing server `.env` values override this default. Inspect them before choosing an interval. Keep the existing target, funder, keys and intended sizing settings. Do not copy the laptop `.env` over the server's file.

Before deployment, record the server commit and relevant nonsecret settings, back up the entire `state/` directory and `.env` on the server, stop the service, update dependencies in the service's virtual environment, and validate readiness. Preserve `state/seen_trades.json` and `state/orders.sqlite3`. Review existing `RECONCILE_ON_START` settings: corrected dust/quantity math can cause previously skipped excess positions to be sold on restart.

This update does not infer full portfolio alignment or automatically buy positions after a deposit. A controlled server rollout and actual confirmed-fill validation remain outstanding.
