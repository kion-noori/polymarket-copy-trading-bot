# Polymarket Copy-Trading Bot

**What problem this solves:** Copying a specific Polymarket trader manually is slow and error-prone—you see their position only after the fact and must size and submit each order yourself. This bot automates that: it polls the target’s trade feed, detects new fills, and places proportionally sized orders on your account so your book tracks theirs within configurable risk limits.

A Python bot that watches a target trader’s Polymarket activity and mirrors their trades on your account with proportional sizing (cap and floor). It mirrors **both entries and exits**: when the target buys, you buy; when they sell or reduce a position, the bot sells the same side so you exit too.

## How it works

1. **Poll** the Data API for the target wallet’s recent trades (configurable interval, e.g. 45s). Compare against last known state (stored transaction hashes) to detect new trades.
2. **Entries and exits**: We mirror both BUY and SELL. When the target sells or reduces a position, the bot places a proportional SELL on your account.
3. **Deduplicate** by transaction hash so each of their trades is mirrored at most once.
4. **Size** your order: same portfolio weight as the target, capped by a % of your portfolio and an optional absolute $ cap, with a minimum notional floor (small trades still execute).
5. **Execute** via **py-clob-client only** — no direct Polygon RPC or MetaMask. The private key in `.env` handles all signing programmatically; the SDK signs and submits orders to the CLOB.

## Requirements

- **Python 3.9+** (py-clob-client requires 3.9+)

## Setup

Assumes you have the repo (clone or download) and are in the project directory.

### 1. Install dependencies

**Requires Python 3.9+** (py-clob-client does not support 3.8). Check with `python3 --version`; if needed, install 3.9+ via [python.org](https://www.python.org/downloads/), Homebrew (`brew install python@3.11`), or your system package manager.

```bash
cd polymarket-copy-trading-bot
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

Use the same `python3` that is 3.9+ when creating the venv (e.g. `python3.11 -m venv .venv` if that’s your 3.9+ binary). **Always activate the venv** before running the bot or the credential script below.

### 2. Configure environment (first pass)

Copy the example env and set at least wallet addresses and private key (API creds come in step 3):

```bash
cp .env.example .env
# Edit .env: set TARGET_WALLET, FUNDER_ADDRESS, and PRIVATE_KEY
```

### 3. Derive L2 API credentials

You need L2 API credentials (api key, secret, passphrase). Derive them once from your private key. **Run from the project directory with venv activated;** ensure `PRIVATE_KEY` is available (e.g. the project’s `config` loads `.env` when you run Python from this repo, or export it: `set -a && source .env && set +a`).

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

Add the printed `api_key`, `api_secret`, and `api_passphrase` to your `.env`.

**Env reference (all variables):**

| Variable | Description |
|----------|-------------|
| `TARGET_WALLET` | Polymarket address of the trader to copy (0x...). |
| `FUNDER_ADDRESS` | Your Polymarket wallet address (from [polymarket.com/settings](https://polymarket.com/settings)). |
| `PRIVATE_KEY` | Private key controlling that wallet (0x...). |
| `POLY_API_KEY`, `POLY_API_SECRET`, `POLY_API_PASSPHRASE` | L2 API credentials from the step above. |
| `POLL_INTERVAL_SEC` | Seconds between polls (default 45). |
| `MAX_PCT_PER_TRADE` | Max fraction of your portfolio per trade (e.g. 0.10 = 10%). |
| `SIZE_MULTIPLIER` | Scale for proportional size (1.0 = same weight as target). |
| `MIN_NOTIONAL` | Minimum notional in USDC (floor; we always trade at least this when copying). |
| `MAX_TRADE_USD` | Optional absolute max $ per trade (0 = only % cap). No single trade exceeds this. |
| `TEST_MODE` | Set to `1`, `true`, or `yes` to log what would be done **without placing orders** (validate before going live). |
| `SIGNATURE_TYPE` | 0 = EOA, 1 = POLY_PROXY, 2 = GNOSIS_SAFE (default 2 for typical Polymarket). |

**Safety:** Keep all credentials in `.env` only — private key, API key, API secret, target wallet. Never commit `.env` or your private key. See [Security](#security) below.

### 4. Run the bot

With the venv activated and `.env` complete:

```bash
python main.py
```

The bot runs until you stop it (Ctrl+C). It logs each detected trade and each order it places. Optional: restrict `.env` to your user with `chmod 600 .env`.

## Sizing

Order of operations: **proportional → cap(s) → floor**. Portfolio values come from the Data API (`/value`) for both you and the target.

```
raw_notional = target_notional × (my_portfolio_value / target_portfolio_value) × SIZE_MULTIPLIER
capped        = min(raw_notional, my_portfolio_value × MAX_PCT_PER_TRADE)
if MAX_TRADE_USD > 0:
    capped   = min(capped, MAX_TRADE_USD)
my_notional  = max(capped, MIN_NOTIONAL)
```

| Step | Effect |
|------|--------|
| Proportional | Same portfolio weight as the target (scaled by `SIZE_MULTIPLIER`). |
| % cap | No single trade exceeds `MAX_PCT_PER_TRADE` × your portfolio (scales with bankroll). |
| $ cap | If `MAX_TRADE_USD` is set, no trade exceeds that dollar amount. |
| Floor | Result is at least `MIN_NOTIONAL` so small trades still execute. |

## Security

- **Key storage:** Private key and API credentials live only in `.env` (gitignored). The app loads them at runtime; they are not logged or echoed in errors.
- **Exposure surface:** The process holds keys in memory while running. Compromise of the machine (or a dump) exposes them. Run on a machine you control (e.g. a dedicated laptop or a locked-down VPS), not on shared or untrusted hosts.
- **Key management:** Prefer a wallet used only for this bot (and fund it with only what you’re willing to copy-trade). Using a main wallet increases impact if the bot or machine is compromised.
- **File permissions:** Restrict `.env` to the current user (e.g. `chmod 600 .env`) so other accounts on the same box cannot read it.
- **Test before live:** Use `TEST_MODE=1` to validate behavior without placing orders; you can run with only `TARGET_WALLET` and `FUNDER_ADDRESS` set (no key/creds required for polling and sizing logs).

## Test mode

Set `TEST_MODE=1` (or `true`/`yes`) in `.env`. The bot will poll and detect trades, compute sizing, and **log exactly what order it would place** without calling the CLOB. Use this to confirm behavior before going live. You can leave `PRIVATE_KEY` and API creds empty in test mode (only `TARGET_WALLET` and `FUNDER_ADDRESS` required for polling and value checks).

## State

Processed trade transaction hashes are stored under `state/seen_trades.json` so after a restart we don’t mirror the same trade again. The `state/` directory is gitignored.

## Edge cases

- **Target sells a position you hold** → We mirror SELLs; the bot will place a proportional SELL so you exit too.
- **Market resolves while you’re holding** → Positions resolve on Polymarket as usual; you can redeem winnings on the site. The bot does not auto-redeem.
- **Partial fills** → We use FOK (fill-or-kill) market orders, so orders either fill completely or are cancelled; there are no partial fills. Order responses are logged for debugging.
- **API errors or timeouts** → Data API and CLOB calls use retry logic (several attempts with a short delay). The main loop catches exceptions so a single failed cycle doesn’t crash the bot; it logs and continues on the next poll.

## Pushing to GitHub

The project is already a git repo with an initial commit. To push to your GitHub:

1. Create a **new repository** on [GitHub](https://github.com/new) (do not add a README or .gitignore; the project has them).
2. Run (replace `YOUR_USERNAME` and `YOUR_REPO` with your GitHub username and repo name):

```bash
cd polymarket-copy-trading-bot
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

If you use SSH: `git remote add origin git@github.com:YOUR_USERNAME/YOUR_REPO.git`

## Docs

See `docs/POLYMARKET_API_REFERENCE.md` for API details, rate limits, and sizing notes.  
See `docs/DESIGN_NOTES.md` for design decisions (entries/exits, safety, edge cases).
