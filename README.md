# Solana Arb Scanner

Cross-DEX price spread alerts for a watched list of Solana tokens. Alert-only —
never places a trade, never touches a wallet. $0 to run: DEX Screener's free API,
GitHub Actions cron (free), no hosting needed.

## How it works

`scripts/arb_scan.py` runs every 15 minutes via GitHub Actions. For each mint in
`watchlist.txt`, it fetches all DEX Screener pairs, keeps only pools with at least
`MIN_LIQUIDITY_USD` (default $20K — filters out the thin/broken pools that would
otherwise show fake huge spreads), and compares the cheapest vs. most expensive
liquid pool. If the spread is between `SPREAD_THRESHOLD_PCT` (default 1.5%) and
`SANITY_CAP_PCT` (default 25% — above this it's almost certainly a bad price feed,
not a real edge, so it's skipped rather than alerted), it sends a Telegram alert.
Per-token 1-hour cooldown (`ALERT_COOLDOWN_SECONDS`) to avoid repeat spam while a
spread persists. State committed back to `state/arb_state.json` by the workflow.

**What this does NOT account for:** swap fees, slippage at trade size, gas/priority
fees, or execution latency between the two legs. Every alert says so explicitly —
treat it as a lead to verify manually, not a guaranteed profitable trade.

## Setup

Push to GitHub, then in the repo's Settings → Secrets and variables → Actions, add:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

The workflow runs automatically once those are set — no hosting, no deploy step.

To watch more tokens, add verified mints to `watchlist.txt` (check them against
`https://lite-api.jup.ag/tokens/v2/search?query=<symbol>` first — a wrong mint
fails silently).
