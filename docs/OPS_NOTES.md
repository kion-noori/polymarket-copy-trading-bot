# Ops Notes

Short operational cheat sheet for the live VPS deployment.

## Connect

```bash
ssh root@YOUR_SERVER_IP
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
cd /root/polymarket-copy-trading-bot
```

## Environment / Readiness Checks

```bash
python scripts/check_env.py
.venv/bin/python scripts/check_live_ready.py
```

## Edit Config

```bash
nano /root/polymarket-copy-trading-bot/.env
systemctl restart polymarket-bot
```

## Update Code On VPS

```bash
cd /root/polymarket-copy-trading-bot
git pull origin main
source .venv/bin/activate
pip install -r requirements.txt
systemctl restart polymarket-bot
```

## Useful Interpretation Notes

- `me=$...` in logs is the bot/operator bankroll snapshot.
- `target=$...` in logs is the copied wallet's portfolio value used for sizing.
- `Skip SELL mirror (no CLOB position)` is expected when the target exits a market you never entered.
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
