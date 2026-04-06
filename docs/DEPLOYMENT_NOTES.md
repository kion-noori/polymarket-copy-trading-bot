# Deployment Notes

This file is a lightweight snapshot of the current known-good deployment setup so future sessions can re-anchor quickly.

## Current Live Setup

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

## Current Strategy / Runtime Choices

- `POLL_INTERVAL_SEC=45`
- `MAX_TRADE_AGE_SEC=0`
  This disables the pure age-based skip and relies on the other entry guards instead.
- `MAX_PCT_PER_TRADE=0.10`
- `MAX_TRADE_USD=0`
  This means there is no separate hard dollar cap beyond the percentage cap.
- `STARTUP_MODE=resume`
- `RECENT_TRADES_PAGE_SIZE=100`
- `RECENT_TRADES_MAX_PAGES=5`
- `MAX_BUY_PRICE=0.95`
- `MAX_SPREAD_FRACTION=0.12`
- `SIGNATURE_TYPE=2`

## Important Notes

- The signer EOA and `FUNDER_ADDRESS` can be different when `SIGNATURE_TYPE=2`; that is expected.
- The bot is designed to skip SELLs when there is no matching held conditional-token balance.
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
