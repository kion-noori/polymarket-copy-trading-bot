# Design notes (from brief)

## Trade monitoring

- Poll the target wallet’s trade history via the Polymarket Data API (`GET /trades?user=TARGET`).
- Fetch both maker and taker fills rather than relying on a taker-only trade feed.
- Compare against last known state: we persist seen `transactionHash` in `state/seen_trades.json` so we only act on **new** trades.
- **Entries and exits**: We monitor both BUY and SELL. When the target sells or reduces a position, the bot places a proportional SELL so you exit too.

## Execution

- Use **py-clob-client exclusively** for order execution. Do not interact with the Polygon blockchain directly; the SDK handles signing and submission to the CLOB.
- No MetaMask or manual signing — the private key in `.env` handles all transaction signing programmatically.
- BUY retries can widen by fixed price points on later attempts so slightly moved markets are still catchable.
- SELLs are capped to actually held conditional-token shares before placement.

## Safety

- **Max trade size cap**: `MAX_PCT_PER_TRADE` (percentage of portfolio) and optional `MAX_TRADE_USD` (absolute dollar cap). No single trade exceeds the configured limits.
- **Test mode**: Set `TEST_MODE=1` (or `true`/`yes`) to log what the bot *would* do without placing orders. Validate behavior before going live.
- Keep all credentials in `.env`: private key, API key, API secret, target wallet address. Never commit `.env`.

## Edge cases

- **Target sells a position you’re holding** → Bot mirrors SELL; you exit too.
- **Manual partial profit-taking** → Bot caps later SELLs to what you still hold and skips dust-sized leftovers instead of trying to submit invalid tiny orders.
- **SELL-only catch-up batch** → If the bot sees only target SELLs during catch-up and you still hold shares, it now attempts the exit instead of auto-skipping the batch.
- **Market resolves while you’re holding** → Handle gracefully: positions resolve on Polymarket; user can redeem on the site. Bot does not auto-redeem.
- **Partial fills** → We use FOK orders (fill-or-kill), so no partial fills. Responses are logged for debugging.
- **API errors or timeouts** → Retry logic with delay in Data API and executor; main loop catches exceptions and continues so the bot doesn’t crash.
