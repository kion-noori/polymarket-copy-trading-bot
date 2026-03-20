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
7. [Requirements & setup](#requirements--setup)  
8. [Sizing (plain English + formula)](#sizing-plain-english--formula)  
9. [Security](#security)  
10. [Test mode](#test-mode)  
11. [State & edge cases](#state--edge-cases)  
12. [Further reading](#further-reading)  

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
| **Smallest copy** | Floor so tiny proportional trades still execute (`MIN_NOTIONAL`). |
| **Aggression** | `SIZE_MULTIPLIER` scales proportional size (1.0 = match target’s *weight*; not dollar-for-dollar). |
| **Test mode** | `TEST_MODE=1` → full logic, **no** orders sent (safe rehearsal). |
| **Wallet model** | `SIGNATURE_TYPE` (typically `2` for Polymarket proxy/Safe + separate funder address). |

Full variable list: [Env reference](#env-reference-all-variables) in Setup below.

---

## Known limitations & risks

- **Not a recommendation engine** — you copy **one** wallet; outcome quality is entirely theirs.  
- **Latency** — polling is not instant; you may enter after the target.  
- **Liquidity** — market / FOK orders can fail if the book can’t fill at your limits; logged, not retried forever on the same trade.  
- **SELL without prior BUY** — if you start late, mirroring a target **sell** may fail if you don’t hold that position.  
- **Operational** — sleep mode, VPN drops, or API outages pause or skip cycles; retries exist but aren’t infinite.  
- **Security** — running with a private key on a machine means **that machine is part of your threat model**.  

---

## How it works (system summary)

1. **Poll** Data API for the target’s recent trades.  
2. **Filter** to trades we haven’t seen; normalize side (BUY/SELL), outcome (YES/NO), size, price.  
3. **Group** by asset for catch-up; apply skip / net rules where needed.  
4. **Size** each mirror order: proportional to target vs your bankroll, then **cap** (% and optional $), then **floor** (min notional).  
5. **Execute** via **py-clob-client** only (signed orders to the CLOB; no MetaMask popups).  

---

## Observability (logs & exports)

- **Console + daily file:** `logs/bot_YYYY-MM-DD.log` — portfolio line (positions + CLOB cash when available), each mirrored intent, errors.  
- **Trade ledger (CSV):** `logs/trades_YYYY-MM-DD.csv` — timestamp, side, outcome (YES/NO), market title, notional, price, implied shares, `test` vs `live`.  
- **State:** `state/seen_trades.json` — processed tx hashes so restarts don’t duplicate mirrors.  

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

### Env reference (all variables)

| Variable | Description |
|----------|-------------|
| `TARGET_WALLET` | Address of the trader to copy (`0x…`). |
| `FUNDER_ADDRESS` | **Your** Polymarket profile address from [settings](https://polymarket.com/settings) (often differs from your Phantom/MetaMask EOA). |
| `PRIVATE_KEY` | Private key for the wallet that **signs** for Polymarket (usually your EOA; `SIGNATURE_TYPE=2` ties it to the funder). |
| `POLY_API_KEY`, `POLY_API_SECRET`, `POLY_API_PASSPHRASE` | L2 API credentials from the step above. |
| `POLL_INTERVAL_SEC` | Seconds between polls (default 45). |
| `MAX_PCT_PER_TRADE` | Max fraction of **your** bankroll per trade (e.g. `0.10` = 10%). |
| `SIZE_MULTIPLIER` | Scales proportional size (`1.0` = same weight as target). |
| `MIN_NOTIONAL` | Minimum USDC notional per copy (floor). |
| `MAX_TRADE_USD` | Optional absolute max $ per trade (`0` = use only % cap). |
| `TEST_MODE` | `1` / `true` / `yes` = simulate only (no orders). |
| `SIGNATURE_TYPE` | `0` EOA, `1` POLY_PROXY, `2` GNOSIS_SAFE (default `2` for typical Polymarket users). |

**Safety:** Never commit `.env`. See [Security](#security).

---

## Sizing (plain English + formula)

**Plain English:** We aim to put the same **share of your bankroll** into a trade as the target put of theirs, then **clamp** so no single trade is too large (percent of your bankroll, optional dollar cap), and **raise** tiny amounts to a minimum floor so small signals still copy.

**Your bankroll** = **open position value** (public Data API) **+** **CLOB USDC cash** (so cash-only accounts still size correctly). **Target** sizing denominator uses public **position value** only.

**Order of operations:** proportional → caps → floor.

```
raw_notional = target_notional × (my_bankroll / target_portfolio_value) × SIZE_MULTIPLIER
capped       = min(raw_notional, my_bankroll × MAX_PCT_PER_TRADE)
if MAX_TRADE_USD > 0:
    capped   = min(capped, MAX_TRADE_USD)
my_notional  = max(capped, MIN_NOTIONAL)
```

| Step | Effect |
|------|--------|
| Proportional | Match target’s portfolio *weight* (× `SIZE_MULTIPLIER`). |
| % cap | No trade larger than `MAX_PCT_PER_TRADE` × your bankroll. |
| $ cap | Optional `MAX_TRADE_USD` ceiling. |
| Floor | At least `MIN_NOTIONAL` USDC. |

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

## State & edge cases

- **State file:** `state/seen_trades.json` stores seen transaction hashes (gitignored).  
- **Target sells, you hold** → we attempt a proportional SELL so you exit together.  
- **Market resolves** → Bot does not auto-redeem; use Polymarket UI.  
- **FOK orders** → Fill completely or cancel; no partial fills by design.  
- **API flakiness** → Retries on Data API and CLOB calls; main loop survives a bad cycle and continues polling.  

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
