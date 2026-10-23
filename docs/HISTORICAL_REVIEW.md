# Historical log review — October 22, 2026

## Scope and interpretation

Read-only review of retained VPS logs, from April 5 through October 22 Eastern time (April 5 23:16 UTC through October 23 01:39 UTC). Ten application log files, the archived `bot_week_review.log`, and the retained service journal were scanned: approximately 1.93 million lines before removing duplicate events. The service journal itself only reaches September 10; application files preserve the earlier history. Application filenames reflect process start dates, so a May filename can contain July events.

Matching timestamp, level and message entries were deduplicated across files and the service journal. Retry-attempt totals below use the application's `place_market_order attempt ... failed` lines, rather than adding SDK errors or final failure summaries for the same attempt. A separate scan of application files verified these totals and captured nearby trade/cash context.

Counts describe logged attempts or decisions, **not distinct missed trades, lost dollars, or a measured cause of underperformance**. Historical `Order placed` messages and trade CSV rows do not establish settled fills. The new order journal provides stronger attribution going forward.

Detailed reports remain private and gitignored on the laptop:

- `logs/historical_review_2026-10-22.json`
- `logs/historical_details_2026-10-22.json`

## Cash shortages are supported by direct evidence

There were **21,226 BUY retry attempts rejected for insufficient balance**, including 11,565 in June and 7,045 in October. These totals include repeated retries for the same signal and smaller fallback orders.

Concrete examples:

- June 7, 2026, 3:36 PM Eastern: logged cash $3.94, attempted BUY $5.00; exchange rejected it for insufficient balance.
- October 2, 2026, 8:16 AM Eastern: logged positions $964.25 and cash $3.22; attempted BUY $5.00; exchange rejected it for insufficient balance.
- October 6–7 UTC: every retained portfolio sample showed cash below $5, around $1.77–$1.80.
- October 21, 2026, 12:48 AM Eastern: even the smaller $2.50 BUY fallback exceeded the roughly $2.00 available cash and was rejected.

This confirms that being almost fully invested prevented some new entries. It does not establish how profitable those missed entries would have been.

Cash snapshots are observations rather than a time-weighted measure. The old balance reader also returned zero after API failures. In particular, zero readings during the April–May API migration period cannot safely be treated as proof of an empty account. Successful routine `/balance-allowance` HTTP requests were not counted as allowance failures.

The 150 explicit insufficient-allowance retry attempts were confined to the initial April setup. They are a separate issue from insufficient cash.

## Manual profit-taking plausibly explains some missing SELLs

- **764 decisions skipped a SELL because the CLOB reported no shares.** Those messages contained 739 distinct source transaction prefixes; some catch-up decisions contain no transaction prefix.
- **856 decisions capped a SELL to the shares actually held.** The old quantity bug described below can also cause this message.
- **541 decisions skipped a tiny SELL remainder.**

Selling shares manually before the target sells is consistent with these outcomes. So are never buying that asset, an earlier bot exit, or an earlier failed BUY. Logs cannot assign every no-shares event to a manual sale, and these categories should not be added as independent affected trades.

The old SELL sizing path also divided dollar notional by the minimum permitted sale price, often $0.01, rather than the source/reference price. For example, an April 7 cap message requested about 500 shares and capped to 23.379129 held shares. Code inspection confirms that the low execution limit inflated the requested quantity. This could turn a partial mirrored exit into an attempt to sell the whole holding. The deployed October release separates intended shares from the price limit.

Only three historical insufficient-balance retry attempts had nearby SELL context; all were from one April 7 episode involving changing/reserved share balances. Lack of BUY cash therefore does not explain the general pattern of SELL skips. Manual transactions cannot be conclusively identified from these logs alone.

## Separate execution and compatibility problems

| Logged retry-attempt failure | Count | Interpretation |
| --- | ---: | --- |
| Insufficient BUY balance | 21,226 | Some intended entries exceeded available collateral |
| FOK could not fully fill | 13,666 | Entire requested size could not fill within the price constraint |
| Invalid tick size | 7,629 | Order used an incompatible market price increment |
| Market not found | 21,446 | Requested market metadata was unavailable through the attempted route |
| Missing order book | 1,162 | Exchange explicitly reported no book for that token |
| Order version mismatch | 2,583 | Old order format rejected between April 28 and May 4 |

These categories count retries. They are not independent estimates of missed source trades or PnL.

The invalid tick-size problem still appeared on October 22 before deployment, with over $584 cash logged nearby. FOK failures also appeared with over $561 cash. Thus insufficient cash and manual selling do not explain all historical execution failures. The October release uses market metadata for tick size, rounds prices, and ordinarily accepts immediate partial fills through FAK; continued live monitoring is needed to assess the result.

### Combined markets need a dedicated compatibility review

Of 21,446 `market not found` retry attempts, **21,443 had nearby trade titles containing ` AND `**. Across the category there were 371 distinct titles, rather than 21,446 different markets. One eight-game sports combination alone accounted for 5,537 attempts. The largest concentration was July. Examples also occurred with substantial cash available.

Polymarket's [Combo overview](https://docs.polymarket.com/trading/combos/overview) describes a request-for-quote execution flow for combined outcomes. Its [Requester guide](https://docs.polymarket.com/trading/combos/requesters) documents a separate gateway for requesting and accepting Combo quotes. [Combinatorial positions](https://docs.polymarket.com/trading/positions/combinatorial) have their own position identifiers and protocol handling.

The titles, errors and documentation strongly suggest that the bot tried routing some Combo activity through an incompatible ordinary-market path. This is an inference; every affected identifier has not been independently classified. The current bot has no dedicated Combo RFQ executor. Do not claim that the ordinary API migration fixes this coverage gap. Investigate explicit market-type detection, valuation coverage, and a supported execution path separately before enabling Combo copying.

## What startup cleanup means

Startup reconciliation compares existing holdings with a proportional snapshot of the target's current holdings. If your account holds more than that calculation requests, it attempts to sell the excess. If the target holds none of a market, the calculation can request selling your entire remaining holding. It does not distinguish a deliberately retained manual position from an accidental mismatch, and it does not only select losing positions.

Example: you own 20 shares of a market the target no longer owns. Startup cleanup could attempt to sell all 20 shares when the bot restarts. Ordinary copying instead reacts to new target trades.

Historical logs show this routine did run: it reported five sale submissions on May 4 Eastern and six on July 20 Eastern, with other startup passes reporting zero. These are submission messages, not independently verified fills.

The October deployment preview identified 154 candidate sales with about $808 of marked excess value. That is a holdings valuation, not guaranteed proceeds. Because this is a substantial batch of existing positions, the live systemd override keeps `RECONCILE_ON_START=0`. Ordinary new-trade SELL copying remains enabled. No cleanup was executed as part of this review.

## Follow-up proposals, not trading changes

1. Add clear cash-aware BUY deferral and low-cash reporting. Decide separately whether to preserve a cash reserve and how to treat source signals missed while cash was unavailable; automatic catch-up after funding could buy stale entries.
2. Review Combo detection, valuation and execution compatibility. Avoid repeatedly treating unsupported identifiers as ordinary tradable markets.
3. Decide how manual profit-taking should interact with later bot activity, including whether a manual exit should pause further buys of that asset.
4. Assess the deployed fixes using confirmed fills and reason-specific skip/rejection counts. Historical logs cannot reconstruct an exact bot-only percentage return.

No live strategy, risk limit or bulk-liquidation setting was changed during this forensic review. At the end of that review, the service was active/running with zero process restarts and three filled journal entries; the then-live release was `dfc8cf0`. Subsequent authorized changes deployed cash controls and disabled automatic external-sale pauses. See [project status](PROJECT_STATUS.md) and the [session handoff](SESSION_HANDOFF.md) for the current recorded deployment and decisions.
