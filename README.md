# Polymarket Copy-Trading Bot

**Side project — automated mirroring of another trader’s Polymarket activity on your own account, with proportional sizing and safety limits.**

This README is written for **both product and engineering** readers: high-level behavior up front, setup and formulas below.

---

## At a glance

| | |
|--|--|
| **Problem** | Manually copying a specific trader on [Polymarket](https://polymarket.com) is slow and easy to mess up (timing, sizing, missing exits). |
| **Solution** | A small Python service polls the trader’s public trade feed, detects new fills, and places **proportionally sized** BUY/SELL orders on **your** account within caps you configure. |
| **Primary user** | You (single account); one **target** wallet to copy. |
| **Stack** | Python 3.9+, Polymarket **Data API** (read) + **CLOB** via `py-clob-client` (trade). |
| **Safety** | Test mode (no real orders), % and optional $ caps per trade, min trade floor, credentials only in `.env`. |

---

## Table of contents

1. [Product overview](#product-overview)  
2. [User journey (happy path)](#user-journey-happy-path)  
3. [What you can configure (“knobs”)](#what-you-can-configure-knobs)  
4. [Known limitations & risks](#known-limitations--risks)  
5. [How it works (system summary)](#how-it-works-system-summary)  
6. [Observability (logs & exports)](#observability-logs--exports)  
7. [Requirements & setup](#requirements--setup) (includes [VPS / 24×7](#run-on-a-vps-247))  
8. [Sizing (plain English + formula)](#sizing-plain-english--formula)  
9. [Slippage (plain English)](#slippage-plain-english)  
10. [Security](#security)  
11. [Test mode](#test-mode)  
12. [State & edge cases](#state--edge-cases)  
13. [Further reading](#further-reading)  

---

## Product overview

**Job to be done:** *“When trader X opens or changes a position on Polymarket, I want my account to reflect that decision at a scale appropriate to my bankroll—without babysitting the UI.”*

**Core behaviors:**

- **Entries:** Target buys → you buy the same outcome (YES/NO token), scaled to your settings.  
- **Exits:** Target sells → you sell proportionally so you’re not stuck holding alone.  
- **No double-counting:** Each of the target’s trades is keyed off a transaction hash; we process it once.  
- **Catch-up after downtime:** If several trades appear at once, we **group** by market and apply rules (e.g. skip if they both bought and sold in the same batch so we don’t enter “late”).  

**Bankroll for sizing (important):** Your “portfolio” number combines **(1) mark-to-market value of open positions** from Polymarket’s public Data API and **(2) USDC cash** sitting in the **CLOB** (so you can size correctly even when you have **cash but no open positions yet**). The target’s size uses public position value only.

---

## User journey (happy path)

1. Configure **who to copy** (`TARGET_WALLET`) and **your** Polymarket profile address (`FUNDER_ADDRESS` from [settings](https://polymarket.com/settings)).  
2. Run in **test mode** → confirm logs and optional `logs/trades_*.csv` look right.  
3. Fund your Polymarket / CLOB balance; verify logs show **positions + CLOB cash**.  
4. Turn off test mode → bot places real orders; you confirm fills on Polymarket.  
5. Leave the process running on a machine that **stays awake** (or use a small always-on box).

---

## What you can configure (“knobs”)

| Area | What it does |
|------|----------------|
| **Poll interval** | How often we check for new target trades (`POLL_INTERVAL_SEC`, default 45s). |
| **Risk per trade** | Max **% of your bankroll** per trade (`MAX_PCT_PER_TRADE`); optional **hard $ cap** (`MAX_TRADE_USD`). |
| **Smallest copy** | `MIN_NOTIONAL` + `MIN_NOTIONAL_MODE` (`floor` = bump tiny sizes up; `skip` = skip dust trades). |
| **Late / worse fills** | `PRICE_GUARD_ENABLED` + `MAX_PRICE_DEVIATION_VS_TARGET` (skip if CLOB mid moved too far vs target’s fill). |
| **Late-entry controls** | `RECENT_TRADES_PAGE_SIZE` × `RECENT_TRADES_MAX_PAGES`, `MAX_BUY_PRICE`, and `STARTUP_MODE` help avoid chasing stale or near-resolved entries. |
| **Stale trades** | `MAX_TRADE_AGE_SEC` (skip mirrors older than N seconds; `0` = off). |
| **Target value unknown** | `SKIP_COPY_WHEN_TARGET_VALUE_UNKNOWN` (default on: no copy when target `/value` is 0). |
| **Aggression** | `SIZE_MULTIPLIER` scales proportional size (1.0 = match target’s *weight*; not dollar-for-dollar). |
| **Slippage** | `SLIPPAGE_FRACTION` (BUY, default 2%) vs `SELL_SLIPPAGE_FRACTION` (SELL, default 99% wide) — see [Slippage](#slippage-plain-english). |
| **Exit fidelity** | `PRICE_GUARD_APPLY_TO_SELL` default `false` — don’t skip SELLs when mid moved; prioritize following target exits. |
| **SELL without shares** | `REQUIRE_CLOB_BALANCE_FOR_SELL` (default `true`) — before a **single-tx** SELL, check CLOB conditional balance; if you hold fewer shares than needed, skip and mark seen (avoids useless retries). |
| **Failed live orders** | `MAX_LIVE_ORDER_ATTEMPTS` (default `10`) — after this many failed CLOB posts per trade, mark seen and stop retrying; `0` = retry forever. |
| **Alerts** | `ALERT_WEBHOOK_URL` + `ALERT_MIN_INTERVAL_SEC` send throttled webhook notifications for repeated live-order failures / startup skips. |
| **Test mode** | `TEST_MODE=1` → full logic, **no** orders sent (safe rehearsal). |
| **Wallet model** | `SIGNATURE_TYPE` (typically `2` for Polymarket proxy/Safe + separate funder address). |

Full variable list: [Env reference](#env-reference-all-variables) in Setup below.

---

## Known limitations & risks

- **Not a recommendation engine** — you copy **one** wallet; outcome quality is entirely theirs.  
- **Latency** — polling is not instant; you may enter after the target.  
- **Guards** — optional max trade age and price-vs-target checks can **skip** a mirror (still marked seen so the bot doesn’t retry forever).  
- **Late entries** — the bot now checks a wider recent trade window by default (**500 trades** = `RECENT_TRADES_PAGE_SIZE=100` × `RECENT_TRADES_MAX_PAGES=5`) so it is less likely to buy something the target already exited.  
- **Liquidity** — market / FOK orders can fail if the book can’t fill at your limits. **Live:** failed orders are **not** marked seen at first — the bot **retries** each poll until the CLOB returns an `orderID`, or until **`MAX_LIVE_ORDER_ATTEMPTS`** is reached (then it marks seen and moves on). **CSV** rows are written only after a **successful** live order (or always in test mode).  
- **SELL without prior BUY** — if you start late, mirroring a target **sell** may fail if you don’t hold that position.  
- **Operational** — sleep mode, VPN drops, or API outages pause or skip cycles; retries exist but aren’t infinite.  
- **Security** — running with a private key on a machine means **that machine is part of your threat model**.  

---

## How it works (system summary)

1. **Poll** Data API for the target’s recent trades.  
2. **Filter** to trades we haven’t seen; normalize side (BUY/SELL), outcome (YES/NO), size, price.  
3. **Group** by asset for catch-up; apply skip / net rules where needed.  
4. **Size** each mirror order: proportional to target vs your bankroll, then **cap** (% and optional $), then **floor** (min notional).  
5. **Guard late entries** with a recent-trade window, max buy price, optional spread check, and optional `live_safe` startup behavior.  
6. **Execute** via **py-clob-client** only (signed orders to the CLOB; no MetaMask popups).  

---

## Observability (logs & exports)

- **Console + daily file:** `logs/bot_YYYY-MM-DD.log` — portfolio line (positions + CLOB cash when available), each mirrored intent, errors.  
- **Trade ledger (CSV):** `logs/trades_YYYY-MM-DD.csv` — timestamp, side, outcome (YES/NO), market title, notional, price, implied shares, `test` vs `live`.  
- **State:** `state/seen_trades.json` — processed tx hashes so restarts don’t duplicate mirrors (kept in memory while running to avoid re-reading the file every poll).  
- **Webhook alerts (optional):** configure `ALERT_WEBHOOK_URL` to receive throttled JSON alerts for startup skips and repeated live-order failures.  

### Tests (optional)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest tests/ -q
```

---

## Requirements & setup

- **Python 3.9+** (required by `py-clob-client`)

Assumes you have the repo cloned and are in the project directory.

### 1. Install dependencies

Check `python3 --version`; install 3.9+ from [python.org](https://www.python.org/downloads/), Homebrew (`brew install python@3.11`), or your OS package manager if needed.

```bash
cd polymarket-copy-trading-bot
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

Use a 3.9+ interpreter for `venv` (e.g. `python3.11 -m venv .venv`). **Activate the venv** before running the bot or the credential snippet below.

### 2. Configure environment (first pass)

```bash
cp .env.example .env
# Edit .env: TARGET_WALLET, FUNDER_ADDRESS, PRIVATE_KEY
```

### 3. Derive L2 API credentials

From the project directory with venv activated; `load_dotenv()` loads `.env`:

```python
from dotenv import load_dotenv
load_dotenv()

from py_clob_client.client import ClobClient
import os

client = ClobClient(
    host="https://clob.polymarket.com",
    chain_id=137,
    key=os.getenv("PRIVATE_KEY"),
)
creds = client.create_or_derive_api_creds()
print(creds)  # Copy api_key, api_secret, api_passphrase into .env
```

### 4. Run the bot

```bash
python main.py
```

Stop with `Ctrl+C`. Optional: `chmod 600 .env`.

### Run on a VPS (24×7)

Use a small **Ubuntu 22.04/24.04** VM (e.g. Hetzner, DigitalOcean, Vultr, Linode).

**Region matters for live orders:** Polymarket blocks order placement from certain countries based on the **server’s public IP** (same idea as geo rules for users). The **United States is blocked** for placing orders — do **not** rely on a US-region VPS for live trading. See [Polymarket geographic restrictions / geoblock](https://docs.polymarket.com/developers/CLOB/geoblock) for the current list.

After SSH’ing into a new VPS, verify:

```bash
curl -s https://polymarket.com/api/geoblock
```

You want `"blocked": false`. If `"blocked": true`, choose another provider region or datacenter. Do not use VPNs to bypass restrictions (against Polymarket’s terms).

**On the server:**

```bash
sudo apt update && sudo apt install -y git python3.11-venv python3-pip
# If python3.11 is not available: use python3 -m venv with whatever is 3.9+
git clone https://github.com/YOUR_USER/polymarket-copy-trading-bot.git
cd polymarket-copy-trading-bot
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Copy your **`.env`** from your laptop (do **not** commit it):

```bash
# From your laptop:
scp .env user@YOUR_SERVER_IP:~/polymarket-copy-trading-bot/.env
# On server:
chmod 600 .env
```

**Smoke test (no real orders):** set `TEST_MODE=1` in `.env`, then `source .venv/bin/activate && python main.py`. Confirm logs look sane (`Ctrl+C` to stop). Then set `TEST_MODE=0` for live trading.

**systemd** (survives disconnects and reboots):

1. Edit `deploy/polymarket-bot.service.example`: replace `ubuntu` and paths with your Linux user and clone path.
2. `sudo cp deploy/polymarket-bot.service.example /etc/systemd/system/polymarket-bot.service`
3. `sudo systemctl daemon-reload && sudo systemctl enable --now polymarket-bot`
4. Logs: `journalctl -u polymarket-bot -f` (and `logs/` under the repo if you need CSV).

**Travel:** Your laptop IP and your **VPS IP** are checked independently. A region that works on Wi‑Fi may still be blocked from the datacenter. Always run `curl` geoblock **from the VPS** before relying on live `TEST_MODE=0`. This is not legal advice.

### Env reference (all variables)

| Variable | Description |
|----------|-------------|
| `TARGET_WALLET` | Address of the trader to copy (`0x…`). |
| `FUNDER_ADDRESS` | **Your** Polymarket profile address from [settings](https://polymarket.com/settings) (often differs from your Phantom/MetaMask EOA). |
| `PRIVATE_KEY` | Private key for the wallet that **signs** for Polymarket (usually your EOA; `SIGNATURE_TYPE=2` ties it to the funder). |
| `POLY_API_KEY`, `POLY_API_SECRET`, `POLY_API_PASSPHRASE` | L2 API credentials from the step above. |
| `POLL_INTERVAL_SEC` | Seconds between polls (default 45). |
| `RECENT_TRADES_PAGE_SIZE` | Trades fetched per Data API page when building the recent decision window (default `100`). |
| `RECENT_TRADES_MAX_PAGES` | Number of recent Data API pages to inspect for catch-up / late-entry logic (default `5` = about 500 recent trades). |
| `STARTUP_MODE` | `resume` (default) = normal catch-up behavior on boot; `live_safe` = mark all currently visible trades seen on startup and only mirror trades that appear afterward. |
| `MAX_PCT_PER_TRADE` | Max fraction of **your** bankroll per trade (e.g. `0.10` = 10%). |
| `SIZE_MULTIPLIER` | Scales proportional size (`1.0` = same weight as target). |
| `MIN_NOTIONAL` | Minimum USDC notional per copy (see `MIN_NOTIONAL_MODE`). |
| `MIN_NOTIONAL_MODE` | `floor` (default) = raise tiny sizes to `MIN_NOTIONAL`; `skip` = skip trade if proportional size is below that. |
| `MAX_TRADE_USD` | Optional absolute max $ per trade (`0` = use only % cap). |
| `SLIPPAGE_FRACTION` | **BUY** only: max pay above target fill (default `0.02` = 2%). Range `(0, 0.5)`. |
| `SELL_SLIPPAGE_FRACTION` | **SELL** only: how far below target’s sell price you allow (default `0.99` → floor **0.01**, i.e. take best bid down to a penny). Range `(0, 1]`. |
| `MAX_BUY_PRICE` | Skip BUY mirrors when the live/current price is at or above this level (default `0.95`). Useful for avoiding near-resolved markets. |
| `MAX_SPREAD_FRACTION` | Skip BUY mirrors when the bid/ask spread is wider than this fraction of the midpoint (default `0.12` = 12%). Set `0` to disable. |
| `PRICE_GUARD_APPLY_TO_SELL` | If `true`, apply `MAX_PRICE_DEVIATION_VS_TARGET` to SELLs too (can skip exits). Default `false` = **follow their exit** even if the market dropped. |
| `REQUIRE_CLOB_BALANCE_FOR_SELL` | Default `true`: for **single-trade** SELL mirrors, require enough **conditional** token balance on the CLOB vs sized sell; otherwise skip + mark seen. Set `false` to always attempt the sell (e.g. if balance API scaling misbehaves). |
| `SKIP_COPY_WHEN_TARGET_VALUE_UNKNOWN` | Default `true`: if target portfolio `/value` is 0, skip mirror (no blind sizing). Set `false` to restore old “use `MIN_NOTIONAL` anyway” behavior. |
| `PRICE_GUARD_ENABLED` | Default `true`: can skip **BUYs** if mid moved up vs target fill. **SELLs** only if `PRICE_GUARD_APPLY_TO_SELL=true`. |
| `MAX_PRICE_DEVIATION_VS_TARGET` | Max fraction worse than target’s price (default `0.08` = 8%). Set `0` to disable the check (no extra price API call). |
| `MAX_TRADE_AGE_SEC` | Skip mirrors for trades older than this many seconds (default `3600`; `0` = disabled). |
| `MAX_LIVE_ORDER_ATTEMPTS` | After this many failed live order posts (no `orderID`) for the same transaction(s), mark them seen and stop retrying (default `10`). `0` = unlimited retries. |
| `ALERT_WEBHOOK_URL` | Optional webhook endpoint that accepts a JSON POST body `{kind, text, ts}` for important bot alerts. |
| `ALERT_MIN_INTERVAL_SEC` | Per-alert-type throttle window in seconds (default `300`) to avoid spam. |
| `TEST_MODE` | `1` / `true` / `yes` = simulate only (no orders). |
| `SIGNATURE_TYPE` | `0` EOA, `1` POLY_PROXY, `2` GNOSIS_SAFE (default `2` for typical Polymarket users). |

**Safety:** Never commit `.env`. See [Security](#security).

---

## Sizing (plain English + formula)

**Plain English:** We aim to put the same **share of your bankroll** into a trade as the target put of theirs, then **clamp** so no single trade is too large (percent of your bankroll, optional dollar cap). With `MIN_NOTIONAL_MODE=floor`, tiny amounts are **raised** to `MIN_NOTIONAL`; with `skip`, trades below that are **skipped**.

**Your bankroll** = **open position value** (public Data API) **+** **CLOB USDC cash** (so cash-only accounts still size correctly). **Target** sizing denominator uses public **position value** only.

**Order of operations:** proportional → caps → floor.

```
raw_notional = target_notional × (my_bankroll / target_portfolio_value) × SIZE_MULTIPLIER
capped       = min(raw_notional, my_bankroll × MAX_PCT_PER_TRADE)
if MAX_TRADE_USD > 0:
    capped   = min(capped, MAX_TRADE_USD)
my_notional  = max(capped, MIN_NOTIONAL)   # floor mode
# skip mode: if capped < MIN_NOTIONAL → my_notional = 0 (skip)
```

| Step | Effect |
|------|--------|
| Proportional | Match target’s portfolio *weight* (× `SIZE_MULTIPLIER`). |
| % cap | No trade larger than `MAX_PCT_PER_TRADE` × your bankroll. |
| $ cap | Optional `MAX_TRADE_USD` ceiling. |
| Floor / skip | `floor`: at least `MIN_NOTIONAL` USDC. `skip`: 0 if below minimum. |

---

## Slippage (plain English)

**Slippage** is the gap between the **price you expect** and the **price you actually get** when an order executes.

- The target’s trade tells us a **reference price** (what they paid or received).  
- Your order is a **FOK market-style** order with a **worst acceptable price** (a limit). The CLOB fills you at the best available prices **up to** that limit.  
- **`SLIPPAGE_FRACTION` (BUY)** — max you’ll pay **above** their price: limit = target × (1 + fraction), capped at **0.99**.
- **`SELL_SLIPPAGE_FRACTION` (SELL)** — how low you’ll sell **below** their price: limit = max(**0.01**, target × (1 − fraction)). Default **0.99** means you accept selling down to **1¢** so you’re not stuck holding after they exit.

**Price guard:** For **BUYs**, we can still skip if the midpoint moved too far vs their fill. For **SELLs**, **`PRICE_GUARD_APPLY_TO_SELL`** defaults to **off** so we don’t skip their exit and leave you in the position.

**Late-entry guard:** Even if the target has not sold yet, buying at **0.95+** usually means you are paying for a trade whose edge may already be mostly gone. `MAX_BUY_PRICE` gives you a simple brake for that scenario, while the recent-trade window helps detect cases where they already bought and sold before you saw it.

Examples: target bought at **0.50**, `SLIPPAGE_FRACTION=0.02` → your BUY limit **0.51**. Target sold at **0.50**, default sell settings → your SELL floor **0.01** (aggressive exit).

Tighter **SELL** slippage (e.g. `SELL_SLIPPAGE_FRACTION=0.05`) = “don’t sell more than 5% below what they got” — safer price, higher risk you **don’t** fill and stay in the trade.

### Startup Modes

- `STARTUP_MODE=resume` means the bot behaves normally after boot: it looks at the recent trade window and may still mirror active positions if they pass the guards.
- `STARTUP_MODE=live_safe` means the bot intentionally ignores anything already visible at startup, marks those tx hashes seen, and only mirrors trades that happen after the process is already running.

If you are on a stable VPS and want to follow active positions, `resume` is usually what you want. If you restart often, are testing a new server, or are nervous about catching up on ambiguous old activity, `live_safe` is the safest mode.

---

## Security

- **Secrets only in `.env`** (gitignored); not logged in normal operation.  
- **Runtime exposure** — keys live in memory while the process runs; use a machine you control.  
- **Scope** — Prefer a **dedicated** wallet + limited capital for the bot.  
- **Permissions** — `chmod 600 .env` on shared-user systems.  
- **Test first** — `TEST_MODE=1` validates flow without orders; with key + creds, test mode also reads **CLOB cash** for realistic sizing.

---

## Test mode

`TEST_MODE=1` runs the full detection and sizing pipeline and writes logs / CSV rows, but **does not** post orders. Use until behavior and risk caps look right, then set `TEST_MODE=0` for live trading.

---

## Alerts

The bot can send simple JSON webhook alerts for important events like:

- repeated live-order failures where it gives up
- `STARTUP_MODE=live_safe` skipping visible trades on boot

Set these in `.env`:

```dotenv
ALERT_WEBHOOK_URL=https://your-webhook-endpoint
ALERT_MIN_INTERVAL_SEC=300
```

The bot auto-detects common webhook types:

- Discord webhook URL -> sends `{"content":"[kind] message"}`
- Slack Incoming Webhook URL -> sends `{"text":"[kind] message"}`
- Anything else -> sends generic JSON

Generic JSON looks like:

```json
{"kind":"live_order_give_up","text":"Giving up after 10 failed live orders for tx 0x1234...","ts":1712345678}
```

Easy ways to receive alerts:

1. Discord
   Create a channel webhook in Server Settings -> Integrations -> Webhooks, then paste the webhook URL into `ALERT_WEBHOOK_URL`.
2. Slack
   Create an Incoming Webhook app, choose a channel, and paste that webhook URL into `ALERT_WEBHOOK_URL`.
3. Pipedream / Zapier / Make
   Use a catch-all webhook URL there, then forward alerts to email, SMS, Telegram, or whatever you prefer.

If you want the fastest setup, Discord is usually the easiest. Create a private channel just for the bot, add a webhook, and you’ll get near-real-time notifications in that channel.

You can sanity-check your local `.env` any time with:

```bash
python scripts/check_env.py
```

For a stronger authenticated readiness check that derives the signer address from your private key and makes safe authenticated client reads without placing any orders:

```bash
.venv/bin/python scripts/check_live_ready.py
```

---

## State & edge cases

- **State file:** `state/seen_trades.json` stores `seen_tx_hashes` and optional `order_failure_counts` for live retry / give-up (gitignored).  
- **Target sells, you hold** → we attempt a proportional SELL so you exit together.  
- **Market resolves** → Bot does not auto-redeem; use Polymarket UI.  
- **FOK orders** → Fill completely or cancel; no partial fills by design.  
- **API flakiness** → Retries on Data API and CLOB calls; main loop survives a bad cycle and continues polling.  
- **Skipped mirrors** (price guard, age, sizing=0) → Transaction is still **marked seen** so the same fill isn’t retried every poll.  
- **Live order failed** (no `orderID`) → **Retries** on later polls until success or **`MAX_LIVE_ORDER_ATTEMPTS`** (then marked seen; increase the limit or copy manually if you still want the trade).  
- **SELL with no / insufficient CLOB shares** (single trade) → **Skipped** and marked seen when `REQUIRE_CLOB_BALANCE_FOR_SELL=true` and balance is readable; avoids infinite retries when you never had the position. If the balance call fails, we **still attempt** the sell and log a warning.  

---

## Further reading

- `docs/POLYMARKET_API_REFERENCE.md` — API surfaces, polling, sizing notes.  
- `docs/DESIGN_NOTES.md` — design decisions (entries/exits, execution, safety).  

---

## Pushing to GitHub

If this is a new remote:

```bash
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

SSH: `git@github.com:YOUR_USERNAME/YOUR_REPO.git`
