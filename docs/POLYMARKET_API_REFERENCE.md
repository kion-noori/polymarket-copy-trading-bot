# Polymarket integration reference — checked October 22, 2026

## Read APIs

The bot uses `https://data-api.polymarket.com/v2`:

| Route | Usage |
|---|---|
| `/trades` | Cursor-paged wallet trades; explicitly set `taker_only=false`. |
| `/positions` | Complete wallet holdings; `include_archived=true`, normalize `current_size` and `current_price`. |
| `/value` | Position value only; not the wallet's collateral cash. |
| `/activity` | Review trades, redemption and other activity; set `exclude_deposits_withdrawals=false` to include cash flows. |
| `/user-pnl` | Cumulative public PnL history; unavailable/null economics remain unavailable. |

Responses wrap payloads in `data`. Paged reads include `pagination.next_cursor`; follow until null, preserving filters. Never send `offset`. A page limit is acceptable for the deliberate recent-trade window, but not for a purported complete position snapshot or historical review. Honor `Retry-After` on retryable reads.

Trade fields use snake_case: `transaction_hash`, `token_id`, `condition_id`, `size` (shares), `price`, `timestamp` (epoch seconds). Position fields include `current_size`, `current_price`, `entry_cost_usdc` (fee-exclusive) and separately disclosed fees. Do not treat missing fields as zero.

## Trading

Production CLOB host: `https://clob.polymarket.com`. Current execution dependency: `py-clob-client-v2==1.2.1`; no fallback to V1 signing. The unified `polymarket-client` SDK is the documented long-term migration path and will be evaluated separately.

- BUY market amount is a dollar budget; SELL amount is explicit shares.
- Query tick size from market metadata; do not guess. Round BUY caps down and SELL minimums up to valid ticks.
- SDK price helpers return JSON objects. Parse `mid` or `price` rather than casting the whole response.
- `/price?side=BUY` is the bid; `side=SELL` is the ask. These describe book sides, not the price paid by an incoming taker BUY.
- FAK fills available liquidity and cancels the remainder. FOK requires complete immediate execution.
- `orderID` is an acknowledgement, not proof of a fill. Delayed orders must be followed.
- Successful responses may supply `tradeIDs` before transaction hashes exist. Follow authenticated trade status to CONFIRMED before treating executions as settled.
- The authenticated user stream covers the authenticated account; it is not permission to subscribe to another trader's private stream.
- Fees and minimum sizes depend on market metadata; do not assume every category has fees. The SDK BUY balance budget is passed to account for applicable charges. The fill export records execution notional before separately charged fees.

## Official references

- [Documentation index](https://docs.polymarket.com/llms.txt)
- [Data API migration and October 24 retirement](https://docs.polymarket.com/migrate/data-api-v1-to-v2)
- [Machine-readable Data API schema](https://data-api.polymarket.com/v2/openapi.json)
- [Unified Python SDK](https://docs.polymarket.com/getting-started/python)
- [Place orders, FAK/FOK and delayed responses](https://docs.polymarket.com/trading/place-orders)
- [Price endpoint book-side semantics](https://docs.polymarket.com/api-reference/market-data/get-market-price)
- [Authenticated order updates](https://docs.polymarket.com/trading/realtime-order-updates)
- [Fees](https://docs.polymarket.com/trading/fees)
- [Predictions changelog](https://docs.polymarket.com/changelog/predictions)
