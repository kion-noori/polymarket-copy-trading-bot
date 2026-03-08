# Polymarket API Reference for Copy-Trading Bot

Summary of [Polymarket's official docs](https://docs.polymarket.com/) relevant to building the copy-trading bot.  
Full index: https://docs.polymarket.com/llms.txt

---

## 1. Three APIs

| API | Base URL | Purpose |
|-----|----------|---------|
| **Gamma API** | `https://gamma-api.polymarket.com` | Markets, events, tags, search — **no auth** |
| **Data API** | `https://data-api.polymarket.com` | User positions, **trades**, **activity**, leaderboards — **no auth** |
| **CLOB API** | `https://clob.polymarket.com` | Orderbook, prices, **order placement/cancel** — **auth required for trading** |

- **Watching the target trader**: Use the **Data API** (public). No API key needed.
- **Executing your orders**: Use the **CLOB API** with L1 (private key) + L2 (API credentials).

---

## 2. Watching the Target Wallet — Data API

### Get trades for a user

**Endpoint:** `GET https://data-api.polymarket.com/trades`

| Param | Type | Notes |
|-------|------|--------|
| `user` | address | **Target wallet address** (0x-prefixed, 40 hex). |
| `limit` | int | Default 100, max 10000. |
| `offset` | int | Pagination. |
| `takerOnly` | bool | Default true. |
| `side` | string | `BUY` or `SELL`. |
| `market` | array | Condition IDs (optional filter). |
| `eventId` | array | Event IDs (optional). Mutually exclusive with `market`. |

**Response:** Array of **Trade** objects:

- `proxyWallet`, `side`, `asset`, `conditionId`, `size`, `price`, `timestamp`
- `title`, `slug`, `eventSlug`, `outcome`, `outcomeIndex`
- `transactionHash` — use for idempotency (don’t mirror same trade twice)

Use this to poll the target’s recent trades (e.g. every 15–30s) and detect new ones.

### Get user activity (alternative)

**Endpoint:** `GET https://data-api.polymarket.com/activity`

| Param | Type | Notes |
|-------|------|--------|
| `user` | address | **Required.** |
| `limit` | int | Default 100, max 500. |
| `offset` | int | Pagination. |
| `type` | array | e.g. `TRADE`, `SPLIT`, `MERGE`, `REDEEM`. |
| `start`, `end` | int | Timestamp range. |
| `sortBy` | string | `TIMESTAMP`, `TOKENS`, `CASH`. Default `TIMESTAMP`. |
| `sortDirection` | string | `ASC` or `DESC`. Default `DESC`. |
| `side` | string | `BUY` or `SELL`. |

**Response:** Array of **Activity** with `type`, `size`, `usdcSize`, `price`, `asset`, `side`, `conditionId`, `timestamp`, etc.

Either **trades** or **activity** can drive “target just traded” logic; trades are the most direct.

### Get total value of a user’s positions (for sizing)

**Endpoint:** `GET https://data-api.polymarket.com/value`

| Param | Type | Notes |
|-------|------|--------|
| `user` | address | **Required.** |

**Response:** `{ "user": "0x...", "value": number }` — total position value in USDC.  
Use for **proportional sizing** (e.g. target’s trade size vs target’s portfolio value).

---

## 3. Executing Your Orders — CLOB API + Python SDK

### Auth (L1 + L2)

- **L1**: Private key signs EIP-712; used to create/derive API credentials and to sign orders.
- **L2**: API key + secret + passphrase; used for HMAC on every CLOB request (post order, cancel, etc.).

**Getting API credentials (Python):**

```python
from py_clob_client.client import ClobClient
import os

client = ClobClient(
    host="https://clob.polymarket.com",
    chain_id=137,  # Polygon mainnet
    key=os.getenv("PRIVATE_KEY")
)
api_creds = client.create_or_derive_api_creds()
# Store api_key, secret, passphrase in .env for L2
```

**Trading client (with L2):**

```python
client = ClobClient(
    host="https://clob.polymarket.com",
    chain_id=137,
    key=os.getenv("PRIVATE_KEY"),
    creds=api_creds,
    signature_type=0,   # 0=EOA, 1=POLY_PROXY, 2=GNOSIS_SAFE
    funder="YOUR_WALLET_ADDRESS"  # Polymarket profile/funder address
)
```

- **Signature type**: Most users who use Polymarket with a normal wallet use **2 (GNOSIS_SAFE)** with the **proxy/funder** address from [polymarket.com/settings](https://polymarket.com/settings). EOA = 0.
- Never commit private keys; use `.env`.

### Placing orders (Python)

**Limit order (create + sign + post):**

```python
from py_clob_client.clob_types import OrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY

market = client.get_market("CONDITION_ID")
tick_size = str(market["minimum_tick_size"])
neg_risk = market["neg_risk"]

response = client.create_and_post_order(
    OrderArgs(
        token_id="TOKEN_ID",  # from market / trade
        price=0.50,
        size=10,
        side=BUY,
        order_type=OrderType.GTC,
    ),
    options={"tick_size": tick_size, "neg_risk": neg_risk},
)
# response["orderID"], response["status"] (live / matched / delayed)
```

**Market order (immediate fill, FOK):**

```python
response = client.create_and_post_market_order(
    token_id="TOKEN_ID",
    side=BUY,
    amount=100,   # dollar amount for BUY
    price=0.55,    # worst-price limit (slippage)
    options={"tick_size": tick_size, "neg_risk": neg_risk},
    order_type=OrderType.FOK,
)
```

- **BUY**: `amount` = dollar amount to spend.  
- **SELL**: `amount` = number of shares.  
- Copy-trading often uses **market orders (FOK/FAK)** to mirror quickly; limit orders are fine if you want to queue at a price.

### Market metadata (tick size, neg risk)

- **Tick size**: `client.get_tick_size("TOKEN_ID")` or `market["minimum_tick_size"]`.  
- **Neg risk**: `client.get_neg_risk("TOKEN_ID")` or `market["neg_risk"]`.  
- Both are required in `options` for every order.

### Your balance (for sizing)

- **CLOB**: `client.get_balance_allowance(asset_type="COLLATERAL")` for USDC.e (and allowances).  
- **Data API**: `GET https://data-api.polymarket.com/value?user=YOUR_ADDRESS` for total position value.  
Use one or both to compute “X% of my portfolio” or “fixed dollar” size.

### Heartbeat (required for live orders)

If you leave orders on the book, you must send heartbeats or **all open orders are cancelled** (after ~10s without valid heartbeat).

```python
heartbeat_id = ""
while True:
    resp = client.post_heartbeat(heartbeat_id)
    heartbeat_id = resp["heartbeat_id"]
    time.sleep(5)
```

Run this in a background loop when the bot is active.

---

## 4. Rate limits (stay under these)

- **Data API**: 1000 req/10s general; **/trades** 200 req/10s.  
  Polling every 15–30s is well within limits.
- **CLOB**:  
  - `POST /order`: 3500/10s burst, 36000/10min sustained.  
  - Ledger (orders/trades): 900/10s.  
  - Balance/allowance: 200/10s.

---

## 5. Copy-trading flow (mapped to APIs)

1. **Poll** `GET https://data-api.polymarket.com/trades?user=TARGET_ADDRESS&limit=100` every 15–30s.
2. **Deduplicate** by `transactionHash` (or trade id) so each target trade is mirrored at most once.
3. **Parse** each new trade: `asset` (token ID), `side`, `size`, `price`, `conditionId`, `outcome`, etc.
4. **Resolve market** (e.g. CLOB `get_market(conditionId)` or Gamma) to get `minimum_tick_size` and `neg_risk`.
5. **Size** your order: see [Sizing formula](#sizing-formula-small-account-copying-large-trader) below.
6. **Execute**:  
   - **Market**: `create_and_post_market_order(...)` with your size and a worst-price (slippage) limit.  
   - **Limit**: `create_and_post_order(OrderArgs(...), options={...})`.
7. **Log** target trade + your order ID and status; handle errors and retries.
8. **Heartbeat** in a loop if you ever post limit orders that rest on the book.

---

## 6. Polling frequency

- **Rate limits**: Data API allows 1000 req/10s overall and 200 req/10s for `/trades`. Even polling every 10s is only 6 requests per minute per endpoint — well under limits.
- **More often** (e.g. 15–20s): You see the target’s trades sooner and mirror faster. No downside except a tiny bit more traffic.
- **Less often** (e.g. 60–120s): Still safe; you just react slower. Good if you want to be conservative or reduce load.

**Recommendation:** 30–60 seconds is a good default. Use 15–30s if you want lower latency; use 60–90s if you prefer “set and forget.” It doesn’t harm you either way as long as you stay under the limits above.

---

## 7. Sizing formula (small account copying large trader)

When you have much less capital than the target (e.g. $500 vs thousands per trade), mirroring their raw size would over-concentrate your account. Use proportional sizing with a cap.

**Target trade notional** = `target_size * target_price` (in USDC).  
**Your portfolio** = your USDC + position value (e.g. from Data API `/value`).  
**Target portfolio** = their total value from `/value?user=TARGET`.

**Proportional notional (same portfolio weight as target):**

```text
my_notional = target_notional × (my_portfolio_value / target_portfolio_value)
```

Example: Target has $50k, trades $2k (4%). You have $500. Proportional = $2k × (500/50000) = **$20** per trade — same 4% of portfolio.

**Recommended formula:**

1. **Proportional** so you match their *relative* bet size:
   - `raw_notional = target_notional * (my_value / target_value)`  
2. **Cap** (percentage-based): one trade never risks more than max_pct_per_trade of your portfolio (scales as bankroll grows):
   - `capped = min(raw_notional, my_value * max_pct_per_trade)`  
   - At $500 with 10% → max **$50**; at $2000 with 10% → max **$200**.  
3. **Floor**: If the result is tiny, still execute — use `min_notional` as a floor so small trades always go through (small wins matter). No skipping.  
4. **Optional scaling**: To be more conservative, multiply by a factor &lt; 1 (e.g. `0.5` = half the proportional size).

**Config-style summary:**

| Parameter              | Example   | Meaning                                      |
|------------------------|-----------|----------------------------------------------|
| `max_pct_per_trade`    | 0.10–0.20 | Cap: Max share of portfolio per trade; scales with bankroll. |
| `size_multiplier`      | 0.5–1.0   | Scale proportional size (1.0 = same weight as target).        |
| `min_notional`         | 5–10      | Floor: if proportional size is below this, use this so we still trade. |

Then:

```text
raw = target_notional * (my_value / target_value) * size_multiplier
capped = min(raw, my_value * max_pct_per_trade)
my_notional = max(capped, min_notional)   # always execute; floor for tiny sizes
```

---

## 8. Useful links

- [Introduction](https://docs.polymarket.com/api-reference/introduction)  
- [Authentication](https://docs.polymarket.com/api-reference/authentication)  
- [Clients & SDKs (Python)](https://docs.polymarket.com/api-reference/clients-sdks)  
- [Get trades for a user](https://docs.polymarket.com/api-reference/core/get-trades-for-a-user-or-markets)  
- [Get user activity](https://docs.polymarket.com/api-reference/core/get-user-activity)  
- [Get total value](https://docs.polymarket.com/api-reference/core/get-total-value-of-a-users-positions)  
- [Post a new order](https://docs.polymarket.com/api-reference/trade/post-a-new-order)  
- [Create Order (trading guide)](https://docs.polymarket.com/trading/orders/create)  
- [L2 Methods (Python)](https://docs.polymarket.com/trading/clients/l2)  
- [Rate limits](https://docs.polymarket.com/api-reference/rate-limits)  
- [Quickstart](https://docs.polymarket.com/quickstart)  

Install: `pip install py-clob-client`
