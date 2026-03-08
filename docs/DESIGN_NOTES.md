# Design notes (from brief)

## Trade monitoring

- Poll the target wallet’s trade history via the Polymarket Data API (`GET /trades?user=TARGET`).
- Compare against last known state: we persist seen `transactionHash` in `state/seen_trades.json` so we only act on **new** trades.
- **Entries and exits**: We monitor both BUY and SELL. When the target sells or reduces a position, the bot places a proportional SELL so you exit too.

## Execution

- Use **py-clob-client exclusively** for order execution. Do not interact with the Polygon blockchain directly; the SDK handles signing and submission to the CLOB.
- No MetaMask or manual signing — the private key in `.env` handles all transaction signing programmatically.

## Safety

- **Max trade size cap**: `MAX_PCT_PER_TRADE` (percentage of portfolio) and optional `MAX_TRADE_USD` (absolute dollar cap). No single trade exceeds the configured limits.
- **Test mode**: Set `TEST_MODE=1` (or `true`/`yes`) to log what the bot *would* do without placing orders. Validate behavior before going live.
- Keep all credentials in `.env`: private key, API key, API secret, target wallet address. Never commit `.env`.

## Edge cases

- **Target sells a position you’re holding** → Bot mirrors SELL; you exit too.
- **Market resolves while you’re holding** → Handle gracefully: positions resolve on Polymarket; user can redeem on the site. Bot does not auto-redeem.
- **Partial fills** → We use FOK orders (fill-or-kill), so no partial fills. Responses are logged for debugging.
- **API errors or timeouts** → Retry logic with delay in Data API and executor; main loop catches exceptions and continues so the bot doesn’t crash.
