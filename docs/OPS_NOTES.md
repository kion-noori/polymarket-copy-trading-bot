# Ops Notes

Short operational cheat sheet for the live VPS deployment.

## Connect

```bash
ssh root@216.238.91.62
```

## Service Commands

```bash
systemctl status polymarket-bot
systemctl restart polymarket-bot
systemctl stop polymarket-bot
systemctl start polymarket-bot
```

## Logs

```bash
# live logs
journalctl -u polymarket-bot -f

# recent logs
journalctl -u polymarket-bot -n 200

# logs since a time window
journalctl -u polymarket-bot --since "1 hour ago"
```

## Project Paths

```bash
cd /root/polymarket-deploy/releases/dfc8cf0
```

## Environment / Readiness Checks

```bash
python3 scripts/check_env.py
.venv/bin/python scripts/check_live_ready.py
```

## Edit Config

```bash
nano /root/polymarket-copy-trading-bot/.env
systemctl restart polymarket-bot
```

## Updates and rollback

The active code is a versioned release in `/root/polymarket-deploy/releases/dfc8cf0`, selected by a systemd override. The original Git checkout is retained and is not the running code path. A `git pull` in that old checkout will not update the service.

The agent can now stage, validate and deploy future releases over SSH. See [checkpoint notes](CHECKPOINTS.md) before rollback. Preserve current shared state and pending-order history; do not restore an old processed-trades snapshot after live fills.

The operator requests that completed code and documentation changes be committed and pushed to GitHub. Keep credentials, live state, raw logs and private diagnostic reports out of Git. Record deployments and recovery checkpoints in the project notes. SSH access supports direct agent deployment; it does not itself authorize new trading policies or bulk liquidation.

## Useful Interpretation Notes

- `me=$...` in logs is the bot/operator bankroll snapshot.
- `target=$...` in logs is the copied wallet's portfolio value used for sizing.
- `Skip SELL mirror (no CLOB position)` means the account currently has no matching shares. A manual exit, an earlier bot exit, or never entering the market can explain it.
- `Cap SELL mirror to held shares` means the requested copy size exceeded the remaining shares. Historical messages can also reflect the old quantity calculation bug; see [historical review](HISTORICAL_REVIEW.md).
- `Skip SELL mirror (dust remainder)` means the bot found only a tiny leftover position after manual or partial exits and intentionally skipped posting an invalid microscopic order.
- Historical `place_market_order attempt ... failed at price ...` messages describe retries. Read the actual error: insufficient balance, incompatible tick size, unavailable markets and liquidity failures require different explanations. The October release retries definitive rejections on later polls.
- If the laptop sleeps or disconnects, the `journalctl` stream stops locally, but the bot should continue running under `systemd`.

## Live Safety Reminders

- Verify VPS geoblock from the VPS itself:

```bash
curl -s https://polymarket.com/api/geoblock
```

- Start with a small bankroll.
- Rotate exposed passwords.
- Prefer SSH keys for long-term admin access.
- Use webhook alerts if possible.

## October 2026 update

Release `dfc8cf0` is deployed and key-based SSH works. See [project status](PROJECT_STATUS.md). Data API v1 is scheduled to retire October 24, 2026.

Do not copy the laptop `.env` to the server. The laptop was last observed in test mode with a 45-second override. Server credentials/settings must be inspected and retained separately. The new code default is five seconds, but an existing override wins.

## Read-only account review

On the **Mac**, connect first:

```bash
ssh root@216.238.91.62
```

Then, **on the server**:

```bash
cd /root/polymarket-deploy/releases/dfc8cf0
.venv/bin/python scripts/review_performance.py --days 7
cat logs/performance_review.md
```

The JSON file preserves raw public observations; the Markdown file summarizes them. Only the server's new journal can identify its confirmed bot fills. Historical CSVs, manual trades and new deposits must not be treated as proof of bot returns.

## Uncertain orders

New logs say `Order submitted` when accepted and `Order confirmed` when settled. Confirmed fills are exported to `logs/confirmed_fills.csv`. Pending orders reserve their source trades and block the same asset until resolved.

List uncertain/pending intents without changing them:

```bash
.venv/bin/python scripts/manage_orders.py
```

If a POST timed out without an order ID, inspect the account's exchange history. Do not delete the JSON state or SQLite journal. Once an existing order ID is identified, stop the bot while reconciling and attach it using the full intent ID and exchange order ID:

```bash
.venv/bin/python scripts/manage_orders.py --intent INTENT_ID --attach-order ORDER_ID
```

The tool checks asset and side before linking, and posts no order. On restart the bot verifies its fills.

If you have verified that **no order or fill exists**, clear only that uncertain intent:

```bash
.venv/bin/python scripts/manage_orders.py --intent INTENT_ID --close-unsubmitted --confirm-no-order
```

This releases the asset block without automatically replaying the original target trade. Never use this option to discard a real order whose outcome is unknown.

## Deployment review checklist

Before any restart/update, capture current service status, service interpreter path, server git revision, nonsecret config, and current holdings. The last recorded server path is `/root/polymarket-copy-trading-bot/.venv/bin/python`.

Stop the service before backing up state and updating code. Preserve `.env`, the full `state/` directory, and logs. Install `requirements.txt` using the exact service interpreter, run the readiness checker, then validate submitted and confirmed fills separately after a controlled restart. Review `RECONCILE_ON_START` before restarting because it can submit sales immediately.

Keep backups on the server; never commit credentials. Running two copies against the same funded account is unsupported even though one checkout has a process lock.

## Effective settings after deployment

The systemd override sets `POLL_INTERVAL_SEC=5`, `COPY_ORDER_TYPE=FAK`, and `RECONCILE_ON_START=0`. These take precedence over the shared original `.env`. The original credentials, 10% sizing cap and $5 desired minimum remain unchanged. Bulk reconciliation needs a separate holdings review; ordinary new target SELLs are still copied.

Server-only deployment records and consistent backup:

```text
/root/polymarket-deploy/deployment.json
/root/polymarket-deploy/checkpoints/before-20261023T011809Z
```

The backup contains credentials: keep it on the server and out of Git. Both old and new virtual environments are retained.
