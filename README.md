# Polymarket Copy-Trading Bot

A personal Python service that watches one Polymarket wallet and mirrors BUYs and SELLs on your account, with proportional sizing and configurable price limits.

The bot runs independently on a VPS. Your laptop is used to inspect logs and deploy changes; it does not need to stay awake.

## Current status

The October 22, 2026 update is implemented locally and tested offline. **VPS deployment and live fill validation are pending.** See [project status](docs/PROJECT_STATUS.md) for the handoff and [deployment notes](docs/DEPLOYMENT_NOTES.md) for the last known server setup.

This update uses Data API **v2**. Polymarket's [migration guide](https://docs.polymarket.com/migrate/data-api-v1-to-v2) announces retirement of the old Data API on October 24, 2026. Changing the base URL alone is insufficient: v2 uses an envelope, renamed fields, and cursor pagination.

## How copying works

1. Fetch a recent window of target fills, explicitly including maker and taker activity.
2. Group transaction legs by asset and side, preserving separate outcomes in one transaction.
3. Skip mixed BUY/SELL catch-up groups to avoid entering after the target has already reduced or exited.
4. Calculate your proportional order size and apply caps and entry filters.
5. Write a durable order intent, then submit a price-bounded immediate order.
6. Confirm actual fills through authenticated order/trade reads and export their executed quantities and prices.

Ordinary copies default to **FAK**: fill the available amount and cancel the remainder. Partial fills are accepted without automatically buying the remainder. `COPY_ORDER_TYPE=FOK` restores all-or-nothing copies. The smaller BUY fallback remains available after repeated definitive rejections.

**SELL quantity is independent of the price limit.** A proportional $5 sale referenced at $0.50 means 10 shares, even if the minimum permitted execution price is $0.01. The bot caps those shares to your actual balance when the balance read succeeds. Manual partial profit-taking is supported.

## Sizing and tracking limits

```text
my_bankroll = open_position_value + CLOB_collateral_cash
raw_notional = target_notional × my_bankroll / target_position_value × SIZE_MULTIPLIER
```

BUY size is capped by `MAX_PCT_PER_TRADE` and optional `MAX_TRADE_USD`. In floor mode, small buys are raised toward `MIN_NOTIONAL`, but the floor cannot override either cap. SELL sizing has no minimum-floor bump.

This does **not** perfectly reproduce the trader's portfolio weights:

- The target denominator is position value; their cash is not included.
- A $5 minimum weights small target bets differently.
- SELLs scale the target's sale notional, rather than calculating the exact percentage of their original position sold.
- Polling, price changes, incomplete liquidity, policy skips, and manual trades change your outcome.
- Adding funds changes subsequent sizing; it does not automatically purchase a matching portfolio.

## Setup

Use **Python 3.11+**. Create a virtual environment compatible with the machine where it runs; do not copy a Mac virtual environment to Linux.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Fill in `TARGET_WALLET`, `FUNDER_ADDRESS`, private key, and L2 credentials. Keep `.env` out of git. For a Safe/proxy account, the signer and funder may legitimately differ.

```bash
python scripts/check_env.py
python scripts/check_live_ready.py
```

The readiness checker only performs reads. With `TEST_MODE=1`, run `python main.py` to simulate. Stop with Ctrl+C. Test-mode state is separate from live processed-trade state.

The pinned execution dependency is `py-clob-client-v2==1.2.1`. Polymarket also offers a [unified Python SDK](https://docs.polymarket.com/getting-started/python); a wholesale SDK replacement is deferred so it can be validated separately from this Data API migration.

## Main settings

Existing `.env` values override code defaults. In particular, changing the default poll interval will not change a server with an explicit `POLL_INTERVAL_SEC` value.

| Setting | Default | Meaning |
|---|---|---|
| `POLL_INTERVAL_SEC` | `5` | Delay between completed cycles; network work adds latency. Minimum 2 seconds. |
| `RECENT_TRADES_PAGE_SIZE` / `RECENT_TRADES_MAX_PAGES` | `100` / `5` | Bounded recent window; older missed trades are not automatically reconstructed. |
| `COPY_ORDER_TYPE` | `FAK` | Allow partial fills; `FOK` requires complete immediate execution. |
| `MAX_PCT_PER_TRADE` | `0.10` | Sizing cap as a fraction of your bankroll. |
| `MAX_TRADE_USD` | `0` | Extra dollar cap; zero disables it. |
| `MIN_NOTIONAL` / `MIN_NOTIONAL_MODE` | `5` / `floor` | Raise small BUYs toward $5 within caps; `skip` omits small buys. |
| `SIZE_MULTIPLIER` | `1` | Scale proportional sizing. |
| `MAX_BUY_PRICE` | `0.97` | Skip entries at/above this price; submitted BUY limits cannot exceed it. |
| `SLIPPAGE_FRACTION` | `0.02` | Initial BUY price allowance relative to target fill. |
| `SELL_SLIPPAGE_FRACTION` | `0.99` | Wide SELL limit, usually down to $0.01; does not change shares. |
| `PRICE_GUARD_ENABLED` / `MAX_PRICE_DEVIATION_VS_TARGET` | `true` / `0.08` | Compare current price to target fill; applies to SELL only if explicitly enabled. |
| `MAX_SPREAD_FRACTION` | `0.12` | Skip wide-spread BUYs. Missing quotes defer rather than consume the trade. |
| `MAX_TRADE_AGE_SEC` | `3600` | Age cutoff; `.env.example` and last documented VPS use `0` to disable it. |
| `STARTUP_MODE` | `resume` | Resume unseen recent activity; `live_safe` skips activity visible at boot. |
| `MAX_LIVE_ORDER_ATTEMPTS` | `10` | Bound definitive rejections; unknown post outcomes are never blindly retried. |
| `PARTIAL_FALLBACK_ENABLED` / `PARTIAL_FALLBACK_FRACTION` | `true` / `0.5` | Smaller last-chance BUY after definitive failures, minimum $1. |
| `RECONCILE_ON_START` | `false` | Optional one-time excess-position SELL reconciliation. |
| `RECONCILE_SELL_ONLY` / `RECONCILE_MIN_NOTIONAL` | `true` / `1` | Reconciliation only sells; no catch-up portfolio purchases. |
| `TEST_MODE` | `true` | Simulate without posting orders. Set explicitly on the server. |
| `ALERT_WEBHOOK_URL` | empty | Optional Discord, Slack, or generic webhook alerts. |

Price widening occurs on later polls after definitive rejections: +2 points per attempt, up to +5 points, bounded by `MAX_BUY_PRICE` and market tick size. Each order is posted once. A timeout after submission blocks that asset for review instead of creating another purchase.

## Logs and order recovery

- `state/seen_trades.json`: processed live source groups and failure counts. Existing plain transaction hashes remain honored, so migration does not replay old trades.
- `state/test_seen_trades.json`: simulation-only state.
- `state/orders.sqlite3`: durable live intents, order IDs, lifecycle state, and confirmed executions. Preserve it alongside processed-trade state during deployment.
- `logs/confirmed_fills.csv`: rebuilt from the journal; actual confirmed prices and quantities only, before separately charged fees.
- `logs/trades_*.csv`: historical intended-order logs or current simulations. They cannot establish historical actual fills.
- `logs/bot_*.log` / systemd journal: operations and decision logs.

An order ID means submitted, not filled. Pending orders are checked on subsequent polls. Unknown submissions without an order ID remain blocked; inspect exchange activity before using [the journal recovery tool](docs/OPS_NOTES.md#uncertain-orders). Do not delete state to retry an ambiguous purchase.

The migration cannot safely recover previously missed maker fills sharing an already processed legacy transaction hash. They remain suppressed to avoid replaying prior trades.

## Read-only performance review

```bash
python scripts/review_performance.py --days 7
```

This fetches public trades, positions, PnL history, deposits and withdrawals, and joins any local journal-linked fills. It writes `logs/performance_review.json`. It cannot place orders or change the server.

Public trades alone cannot distinguish manual activity from bot activity. A target trade without an attributed order may be a skip, downtime, or pre-journal activity. The report does not infer ROI from deposits or from the target's position value alone. Run it **on the VPS** to include that machine's order journal.

## Tests

```bash
pip install -r requirements-dev.txt
pytest tests/ -q
```

Tests use temporary state and block unexpected network calls. Coverage includes v2 pagination, maker coverage, SELL quantities, quote parsing, partial/delayed fills, ambiguous submissions, and restart idempotency. These checks do not validate current live credentials or exchange execution.

See [ops notes](docs/OPS_NOTES.md) for exact Mac/server commands and [design notes](docs/DESIGN_NOTES.md) for limitations. Resolved winnings still require redemption; the bot does not auto-redeem. A server's location does not determine your eligibility to use Polymarket; follow its geographic restrictions and terms.

## Version checkpoints

Committed source revisions can be archived with checksum verification using `scripts/checkpoint.py`. [Checkpoint and rollback notes](docs/CHECKPOINTS.md) describe the agent-managed deployment workflow. Rollback retains current trading state; restoring old state after live orders can cause duplicates. The old API v1 version is a historical checkpoint, not a permanent fallback after API retirement.
