"""Probe additional Binance CMS catalogs for MM tier / leverage bracket changes
independent of delisting events.

Try common Binance Futures catalog IDs to expand coverage.
"""
from __future__ import annotations
import json
import logging
import re
import time
import urllib.request

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)

# Known Binance CMS catalog IDs to probe
CANDIDATE_CATS = [
    (48, "Futures announcements (general)"),
    (161, "Futures trading rules"),
    (49, "Perpetual Futures updates"),
    (50, "COIN-M updates"),
    (79, "Delisting"),
    (94, "Latest Binance news"),
    (24, "New listings"),
    (57, "System maintenance"),
    (128, "Trading rule updates"),
    (166, "Futures market"),
    (162, "Margin trading"),
]

# Needles that would indicate a MM tier / leverage change WITHOUT delisting
MM_TITLE_RX = re.compile(
    r"(Update the Leverage|Adjust the Leverage|Update Leverage|Margin\s+Tier|"
    r"Maintenance\s+Margin|Position\s+Limit|Risk\s+Limit|Notional Cap|"
    r"Position Bracket|leverage tier)",
    re.I,
)
DELIST_RX = re.compile(r"Delist", re.I)


def fetch_catalog(cat_id: int, page: int) -> dict:
    url = (
        f"https://www.binance.com/bapi/composite/v1/public/cms/article/catalog/list/query"
        f"?catalogId={cat_id}&pageNo={page}&pageSize=50"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def main():
    total_hits = 0
    standalone_hits = 0
    matrix = []
    for cat_id, label in CANDIDATE_CATS:
        log.info("catalog %d (%s) ...", cat_id, label)
        cat_total = 0
        cat_mm = 0
        cat_mm_standalone = 0
        for page in range(1, 8):
            try:
                j = fetch_catalog(cat_id, page)
            except Exception as e:
                log.warning("  cat %d page %d fail: %s", cat_id, page, e)
                break
            arts = (j.get("data") or {}).get("articles", [])
            if not arts:
                break
            cat_total += len(arts)
            for a in arts:
                title = a.get("title", "") or ""
                if MM_TITLE_RX.search(title):
                    cat_mm += 1
                    if not DELIST_RX.search(title):
                        cat_mm_standalone += 1
                        if cat_mm_standalone <= 15:
                            log.info("    MM-standalone: %s", title[:120])
            time.sleep(0.2)
        log.info(
            "  cat %d total_articles=%d mm_hits=%d mm_standalone=%d",
            cat_id, cat_total, cat_mm, cat_mm_standalone,
        )
        total_hits += cat_mm
        standalone_hits += cat_mm_standalone
        matrix.append((cat_id, label, cat_total, cat_mm, cat_mm_standalone))

    log.info("=" * 80)
    log.info("SUMMARY (across all probed catalogs):")
    log.info("  total MM/leverage-titled articles: %d", total_hits)
    log.info("  standalone (NOT delisting): %d", standalone_hits)
    log.info("catalog matrix:")
    for row in matrix:
        log.info("  cat %d %-35s articles=%-5d mm=%-3d standalone=%d",
                 row[0], row[1], row[2], row[3], row[4])


if __name__ == "__main__":
    main()
