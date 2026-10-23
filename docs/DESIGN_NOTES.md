# Design notes

This is a single-operator service copying one target wallet. Source reads use public Data API v2; execution uses the pinned official CLOB V2 client. It does not sign direct blockchain transactions or auto-redeem positions.

## Source identity and snapshots

Every cursor page re-sends the same filters, including `taker_only=false`. Fills sharing transaction, asset and side are aggregated by share-weighted price. Distinct assets/directions within a transaction remain separate. Legacy plain seen hashes suppress all their new composite identities to prevent migration replay.

A bounded recent trade window supports catch-up. Mixed BUY/SELL groups are skipped deliberately. Complete position reads must reach the last cursor; a failed, malformed, cyclic or truncated snapshot raises and cannot masquerade as an empty portfolio.

## Sizing

The operator bankroll includes marked positions plus CLOB cash. The target denominator includes marked positions only. BUYs use proportional size, percentage/dollar caps, and an optional desired minimum within those caps. SELLs have no minimum floor.

SELL shares equal the proportional sale notional divided by its target reference price (VWAP for a group), capped by held shares when known. The minimum execution price does not determine quantity. This fixes over-exiting but does not implement exact target-position percentage reductions.

Startup reconciliation is optional, sell-only and one-time. It compares complete current position snapshots, values excess shares at reference prices for dust checks, and posts explicit share quantities using FAK. It does not buy missing positions or guarantee portfolio synchronization.

## Execution state

Before a POST, SQLite commits a submission intent. Only a definitive rejection permits another attempt. A timeout or interrupted submission without an exchange order ID remains blocked until the operator checks exchange history. Pending orders block the asset, not unrelated markets.

Returned order IDs reserve source groups but do not constitute completed fills. Authenticated order and trade reads confirm executions; MATCHED and MINED trade states are provisional. Only CONFIRMED quantities and prices enter the execution ledger. Trade IDs distinguish fills, and maker matches use the submitted order's own matched quantity.

FAK partials are accepted and the unfilled remainder is canceled. No full-notional repost follows a partial fill. FOK remains configurable. Definitive rejections can retry on later polls with bounded price widening; no synchronous multi-POST retry loop delays every other asset.

SQLite is the authoritative execution ledger. CSV is an idempotent export, so a failed export cannot justify replaying an order. Preserve both JSON processed state and SQLite across updates. Test-mode state is separate. A local file lock prevents two processes in one checkout; running separate copies against one account is unsupported.

## Performance interpretation

Public account trades include manual actions. Attribute bot fills only through source IDs in the execution journal. Deposits/withdrawals are capital flows, not profit. Historical NAV and target cash are needed for comparable returns; public position value and a PnL headline are insufficient. The report preserves raw observations and explicitly labels missing attribution and grouped orders.
