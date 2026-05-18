"""
compile_unlock_events.py
========================
Manual compilation of historical token unlock events for paradigm
`token_unlock_cliff_short_alt` (Category A external event injection,
lifecycle_pump_decay analog, lesson #26 entry-side mechanism hypothesis).

Source rules (BINDING — see feedback_no_freemium_trial):
- ONLY public unauthenticated web scrape
- cryptorank.io per-coin /price/{slug}/vesting endpoint (Next.js __NEXT_DATA__
  JSON embed). Server returns 1 allocation per coin even when allocations
  total > 1 in the underlying schema (isAuthProtected: True). We treat the
  returned allocation as the publicly-known "headline" cohort and accept
  the partial-coverage caveat in compilation_report.md.

Data quality caveats:
- Per-coin coverage is single-allocation only (the cryptorank-exposed cohort).
  For some coins this is the high-impact cohort (Team/Investors/Early
  Contributors) — typically the cliff/dilution cohort that drives supply
  pressure. For others it is "Community" or "Ecosystem Incentives" which
  may be continuous emission rather than discrete cliff events.
- Cross-validation: the scraper records primary source URL. Secondary
  source (tokenomist.ai per-coin page URL) recorded but its data is
  client-side hidden behind chunked JS, so cross-validation marked as
  source URL match only, not value comparison.
- Filter: unlock_date in [2024-01-01, 2026-05-18], unlock_pct_supply >= 0.5.

Idempotent: re-running uses raw_html_cache/{ticker}_cryptorank.html if
present (delete cache to refresh). Sleeps 2s between live requests.
"""

from __future__ import annotations

import csv
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

OUT_DIR = Path(__file__).resolve().parent
CACHE_DIR = OUT_DIR / "raw_html_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

CSV_PATH = OUT_DIR / "token_unlock_events.csv"

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}

DATE_START = datetime(2024, 1, 1)
DATE_END = datetime(2026, 5, 18)
MIN_PCT_TOTAL_SUPPLY = 0.5  # noise filter — 0.5% of total supply per event

# (ticker, slug). slugs verified manually 2026-05-18.
# JTO, WLD, JUP, PORTAL all return n_alloc=0 from cryptorank public endpoint
# (auth-gated to empty); excluded from universe. SEI uses sei-network slug.
# AVAIL excluded (no Binance USDS-M perp). OMNI excluded (perp status=SETTLING).
SEED_UNIVERSE = [
    ("APT",    "aptos"),
    ("ARB",    "arbitrum"),
    ("OP",     "optimism"),
    ("SUI",    "sui"),
    ("STRK",   "starknet"),
    ("PYTH",   "pyth-network"),
    ("W",      "wormhole"),
    ("ENA",    "ethena"),
    ("TIA",    "celestia"),
    ("SEI",    "sei-network"),
    ("MANTA",  "manta-network"),
    ("ALT",    "altlayer"),
    ("PORTAL", "portal-coin"),
    ("AEVO",   "aevo"),
    ("IO",     "io-net"),
    ("ZK",     "zksync"),
    ("ZRO",    "layerzero"),
    ("DYM",    "dymension"),
    ("PIXEL",  "pixels"),
    ("XAI",    "xai-games"),
    ("ACE",    "fusionist"),
    ("NFP",    "nfprompt"),
    ("MERL",   "merlin-chain"),
    ("ETHFI",  "ether-fi"),
    ("BB",     "bouncebit"),
    # Expansion candidates (Binance USDS-M perp verified):
    ("EIGEN",  "eigenlayer"),
    ("HYPE",   "hyperliquid"),
    ("SCR",    "scroll"),
    ("ONDO",   "ondo-finance"),
    ("CELO",   "celo"),
    ("IMX",    "immutable-x"),
    ("GMX",    "gmx"),
    ("MORPHO", "morpho"),
    ("USUAL",  "usual"),
    ("REZ",    "renzo-protocol"),
    ("GRASS",  "grass"),
    # Below: failed cryptorank lookup but kept in attempt log for transparency
    ("JTO",    "jito"),     # n_alloc=0
    ("WLD",    "worldcoin"),  # n_alloc=0
    ("JUP",    "jupiter"),  # n_alloc=0
]


# ---------------------------------------------------------------------------
# Binance Futures perp gate
# ---------------------------------------------------------------------------
def fetch_binance_perps() -> set[str]:
    r = requests.get(
        "https://fapi.binance.com/fapi/v1/exchangeInfo",
        headers={"User-Agent": USER_AGENT},
        timeout=20,
    )
    r.raise_for_status()
    data = r.json()
    return {
        s["symbol"]
        for s in data["symbols"]
        if s["quoteAsset"] == "USDT"
        and s["contractType"] == "PERPETUAL"
        and s["status"] == "TRADING"
    }


# ---------------------------------------------------------------------------
# cryptorank scrape
# ---------------------------------------------------------------------------
def fetch_cryptorank_html(slug: str, ticker: str) -> str | None:
    cache_file = CACHE_DIR / f"{ticker}_cryptorank.html"
    if cache_file.exists():
        return cache_file.read_text(encoding="utf-8")
    url = f"https://cryptorank.io/price/{slug}/vesting"
    try:
        r = requests.get(url, headers=HEADERS, timeout=25)
        if r.status_code != 200:
            print(f"  {ticker:7s} HTTP {r.status_code}, skip")
            return None
        cache_file.write_text(r.text, encoding="utf-8")
        time.sleep(2)
        return r.text
    except Exception as e:
        print(f"  {ticker:7s} fetch error: {e}")
        return None


def parse_next_data(html: str) -> dict | None:
    m = re.search(
        r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
        html,
        re.DOTALL,
    )
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def extract_events(ticker: str, slug: str, html: str) -> list[dict]:
    """Return list of unlock-event dicts for a single token."""
    data = parse_next_data(html)
    if not data:
        return []
    pp = data.get("props", {}).get("pageProps", {})
    coin = pp.get("coin", {})
    if not coin or coin.get("symbol", "").upper() != ticker:
        # slug mismatch (e.g. wrong project)
        return []
    vi = pp.get("vestingInfo", {})
    allocs = vi.get("allocations", [])
    if not allocs:
        return []

    coin_name = coin.get("name", ticker)
    total_supply = coin.get("totalSupply") or coin.get("maxSupply") or 0

    rows: list[dict] = []
    source_url = f"https://cryptorank.io/price/{slug}/vesting"

    for alloc in allocs:
        alloc_name = alloc.get("name", "").strip()
        alloc_pct_total = float(alloc.get("tokens_percent", 0.0))  # % of total supply
        alloc_tokens = float(alloc.get("tokens", 0.0))
        unlock_type = alloc.get("unlock_type", "unknown")  # 'linear' / 'cliff' / ...
        # Map unlock_type -> cliff_or_linear category
        if unlock_type == "linear":
            cliff_or_linear = "linear"
        elif unlock_type == "cliff":
            cliff_or_linear = "cliff"
        else:
            cliff_or_linear = "unknown"

        batches = alloc.get("batches", [])
        for b in batches:
            try:
                dt_iso = b["date"]
                pct_of_alloc = float(b["unlock_percent"])
            except (KeyError, ValueError, TypeError):
                continue
            # Convert pct_of_alloc (% of this allocation) to % of total supply
            pct_total = pct_of_alloc / 100.0 * alloc_pct_total
            # Token amount
            amount_token = pct_of_alloc / 100.0 * alloc_tokens
            try:
                dt = datetime.fromisoformat(dt_iso.replace("Z", "+00:00"))
            except ValueError:
                continue
            dt_naive = dt.replace(tzinfo=None)
            if not (DATE_START <= dt_naive <= DATE_END):
                continue
            if pct_total < MIN_PCT_TOTAL_SUPPLY:
                continue

            # Per-batch cliff inference: TGE batches treated as cliff,
            # other batches inherit the allocation's unlock_type. If unlock_type
            # is "linear" we honor that even for individual batches.
            is_tge = bool(b.get("is_tge", False))
            row_cliff = cliff_or_linear
            if is_tge:
                row_cliff = "cliff"  # TGE is always a cliff event

            rows.append(
                {
                    "token": coin_name,
                    "ticker": ticker,
                    "ticker_perp": f"{ticker}USDT",
                    "unlock_date": dt_naive.strftime("%Y-%m-%d"),
                    "unlock_ts_utc": dt.astimezone(timezone.utc).strftime(
                        "%Y-%m-%dT%H:%M:%S+00:00"
                    ),
                    "unlock_pct_supply": round(pct_total, 4),
                    "unlock_amount_token": round(amount_token, 2),
                    "unlock_amount_usd_est": "",  # populated later if price fetched
                    "allocation_category": alloc_name,
                    "cliff_or_linear": row_cliff,
                    "source_url_1": source_url,
                    "source_url_2": f"https://tokenomist.ai/{slug}",
                    "cross_validated": False,  # see notes — secondary is URL-only
                    "notes": (
                        "tge"
                        if is_tge
                        else (
                            "partial_coverage_single_allocation"
                            if len(allocs) == 1
                            else ""
                        )
                    ),
                }
            )
    return rows


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    print("=" * 70)
    print("token_unlock_cliff_short_alt — Phase 1 manual compilation")
    print("=" * 70)
    print(f"Universe attempted: {len(SEED_UNIVERSE)} tickers")
    print(f"Filter: {DATE_START.date()} ≤ unlock_date ≤ {DATE_END.date()}, "
          f"pct_supply ≥ {MIN_PCT_TOTAL_SUPPLY}%")
    print()

    print("Verifying Binance Futures USDS-M perp listings...")
    perps = fetch_binance_perps()
    print(f"  Binance perps live: {len(perps)}")

    all_rows: list[dict] = []
    drops: list[tuple[str, str]] = []
    universe_kept: list[str] = []
    for ticker, slug in SEED_UNIVERSE:
        perp = f"{ticker}USDT"
        if perp not in perps:
            drops.append((ticker, "perp_not_listed"))
            continue
        html = fetch_cryptorank_html(slug, ticker)
        if not html:
            drops.append((ticker, "fetch_failed"))
            continue
        rows = extract_events(ticker, slug, html)
        if not rows:
            drops.append((ticker, "no_allocation_data_or_filtered_zero"))
            print(f"  {ticker:7s} {slug:25s} 0 events post-filter")
            continue
        all_rows.extend(rows)
        universe_kept.append(ticker)
        print(f"  {ticker:7s} {slug:25s} {len(rows)} events kept")

    print()
    print(f"Final universe: {len(universe_kept)} tokens kept, {len(drops)} dropped")
    for t, reason in drops:
        print(f"  DROP {t:7s} -> {reason}")

    print(f"Total events compiled: {len(all_rows)}")
    if not all_rows:
        print("NO EVENTS — abort.")
        sys.exit(1)

    # Sort by date
    all_rows.sort(key=lambda r: (r["unlock_date"], r["ticker"]))

    # Write CSV
    fieldnames = [
        "token",
        "ticker",
        "ticker_perp",
        "unlock_date",
        "unlock_ts_utc",
        "unlock_pct_supply",
        "unlock_amount_token",
        "unlock_amount_usd_est",
        "allocation_category",
        "cliff_or_linear",
        "source_url_1",
        "source_url_2",
        "cross_validated",
        "notes",
    ]
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in all_rows:
            w.writerow(r)
    print(f"Wrote {CSV_PATH}  ({CSV_PATH.stat().st_size} bytes)")

    # Quick stats
    print()
    print("--- Stats ---")
    from collections import Counter

    by_year = Counter(r["unlock_date"][:4] for r in all_rows)
    by_quarter = Counter(
        f"{r['unlock_date'][:4]}Q{(int(r['unlock_date'][5:7]) - 1) // 3 + 1}"
        for r in all_rows
    )
    by_type = Counter(r["cliff_or_linear"] for r in all_rows)
    by_token = Counter(r["ticker"] for r in all_rows)

    print(f"  by year:    {dict(sorted(by_year.items()))}")
    print(f"  by quarter: {dict(sorted(by_quarter.items()))}")
    print(f"  by type:    {dict(by_type)}")
    print(f"  per-token:  {dict(by_token.most_common(15))}")

    cliff_only = sum(1 for r in all_rows if r["cliff_or_linear"] == "cliff")
    print(f"  cliff events: {cliff_only}")


if __name__ == "__main__":
    main()
