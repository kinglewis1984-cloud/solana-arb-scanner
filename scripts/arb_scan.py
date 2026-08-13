"""
Cross-DEX spread scanner (alert-only — never trades). For each watched token,
compares priceUsd across its DEX Screener pairs and alerts on Telegram when the
spread between the cheapest and most expensive liquid pool exceeds a threshold.

Run on a schedule by .github/workflows/arb-scan.yml. State (last alert time per
token) persisted in state/arb_state.json, committed back by the workflow.

Caveats this deliberately does NOT account for: swap fees, slippage on size,
gas/priority fees, or execution latency. A flagged spread is a lead to verify
manually, not a guaranteed profitable trade — Telegram alerts say so explicitly.
"""
import json
import os
from pathlib import Path

import requests

MIN_LIQUIDITY_USD = float(os.environ.get("MIN_LIQUIDITY_USD", "20000"))
SPREAD_THRESHOLD_PCT = float(os.environ.get("SPREAD_THRESHOLD_PCT", "1.5"))
SANITY_CAP_PCT = float(os.environ.get("SANITY_CAP_PCT", "25"))  # above this, treat as bad data, not a real edge
ALERT_COOLDOWN_SECONDS = int(os.environ.get("ALERT_COOLDOWN_SECONDS", str(3600)))

WATCHLIST_FILE = Path(__file__).resolve().parent.parent / "watchlist.txt"
STATE_FILE = Path(__file__).resolve().parent.parent / "state" / "arb_state.json"

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]


def load_watchlist():
    mints = []
    with open(WATCHLIST_FILE) as f:
        for line in f:
            mint = line.split("#", 1)[0].strip()
            if mint:
                mints.append(mint)
    return mints


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2))


def fetch_pairs(mint):
    url = f"https://api.dexscreener.com/token-pairs/v1/solana/{mint}"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    return resp.json() or []


def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    resp = requests.post(
        url,
        json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"},
        timeout=15,
    )
    resp.raise_for_status()


def scan_token(mint, pairs):
    liquid = []
    for p in pairs:
        try:
            price = float(p["priceUsd"])
            liq = float(p.get("liquidity", {}).get("usd") or 0)
        except (KeyError, TypeError, ValueError):
            continue
        if liq >= MIN_LIQUIDITY_USD and price > 0:
            liquid.append({"dex": p.get("dexId", "?"), "price": price, "liq": liq, "pair": p.get("pairAddress")})

    if len(liquid) < 2:
        return None

    cheapest = min(liquid, key=lambda x: x["price"])
    priciest = max(liquid, key=lambda x: x["price"])
    spread_pct = (priciest["price"] - cheapest["price"]) / cheapest["price"] * 100

    if spread_pct > SANITY_CAP_PCT:
        return None  # almost certainly a bad price feed, not a real edge — skip silently

    if spread_pct < SPREAD_THRESHOLD_PCT:
        return None

    symbol = pairs[0].get("baseToken", {}).get("symbol", mint[:4])
    return {
        "symbol": symbol,
        "spread_pct": spread_pct,
        "buy_dex": cheapest["dex"],
        "buy_price": cheapest["price"],
        "sell_dex": priciest["dex"],
        "sell_price": priciest["price"],
    }


def main():
    watchlist = load_watchlist()
    state = load_state()
    now = __import__("time").time()

    for mint in watchlist:
        try:
            pairs = fetch_pairs(mint)
        except Exception:
            continue

        hit = scan_token(mint, pairs)
        if not hit:
            continue

        last_alerted = state.get(mint, 0)
        if now - last_alerted < ALERT_COOLDOWN_SECONDS:
            continue

        send_telegram(
            f"⚖️ *Spread: {hit['symbol']}*\n"
            f"Buy on {hit['buy_dex']} @ ${hit['buy_price']:.6g}\n"
            f"Sell on {hit['sell_dex']} @ ${hit['sell_price']:.6g}\n"
            f"Spread: {hit['spread_pct']:.2f}%\n"
            f"_Before fees/slippage/gas — verify manually, not a guaranteed profit._"
        )
        state[mint] = now

    save_state(state)


if __name__ == "__main__":
    main()
