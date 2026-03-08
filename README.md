# Polymarket Copy-Trading Bot

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

### 1. Install dependencies

**Requires Python 3.9+** (py-clob-client does not support 3.8). If your default `python3` is 3.8, use Python 3.11 from Homebrew:

```bash
cd polymarket-copy-trading-bot
# Use Python 3.11 (Homebrew). If you use a different 3.9+ Python, replace the path.
/usr/local/opt/python@3.11/bin/python3.11 -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install --upgrade pip
pip install -r requirements.txt
```

Then **always activate the venv** before running the bot: `source .venv/bin/activate`.

### 2. Get Polymarket API credentials

You need L2 API credentials (api key, secret, passphrase). With your private key you can derive them once:

```python
from py_clob_client.client import ClobClient
import os

client = ClobClient(
    host="https://clob.polymarket.com",
    chain_id=137,
    key=os.getenv("PRIVATE_KEY"),
)
creds = client.create_or_derive_api_creds()
print(creds)  # Save api_key, api_secret, api_passphrase to .env
```

### 3. Configure environment

Copy the example env and fill in your values:

```bash
cp .env.example .env
# Edit .env with your TARGET_WALLET, FUNDER_ADDRESS, PRIVATE_KEY, and API creds
```

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

**Safety:** Keep all credentials in `.env` only — private key, API key, API secret, target wallet. Never commit `.env` or your private key.

### 4. Run the bot

```bash
python main.py
```

The bot runs until you stop it. It logs each detected trade and each order it places.

## Sizing

- **Proportional**: Your notional = target notional × (your portfolio value / target portfolio value) × `SIZE_MULTIPLIER`.
- **Cap**: Your notional is capped at `MAX_PCT_PER_TRADE` × your portfolio value (so it scales as your bankroll grows). If `MAX_TRADE_USD` is set (e.g. 50), no single trade exceeds that dollar amount regardless of the target.
- **Floor**: If the result is below `MIN_NOTIONAL`, we use `MIN_NOTIONAL` so small trades are still executed.

Portfolio values are read from the Data API (`/value`) for both you and the target.

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
