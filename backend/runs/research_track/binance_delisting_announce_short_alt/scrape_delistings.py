"""Scrape Binance Futures USDS-M perp delisting announcements (cat 161)
2024-01-01 to 2026-05-18, output delisting_events.csv with
columns: announce_ts (UTC), delist_ts (UTC), symbol, gap_days.

Two-step:
  1) list endpoint -> filter titles by `Binance Futures Will Delist...USDⓈ-M`
  2) detail endpoint (per article code) -> publishDate (epoch ms) + body JSON tree
     Body JSON tree -> walk to extract text -> regex symbols + delist dates
"""
from __future__ import annotations
import csv
import json
import logging
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)

OUT_DIR = Path(__file__).resolve().parent
OUT_CSV = OUT_DIR / "delisting_events.csv"
CAT_ID = 161
PAGE_SIZE = 50
START_DATE = datetime(2024, 1, 1, tzinfo=timezone.utc)
END_DATE = datetime(2026, 5, 18, tzinfo=timezone.utc)


def fetch_catalog(page: int) -> dict:
    url = (
        f"https://www.binance.com/bapi/composite/v1/public/cms/article/catalog/list/query"
        f"?catalogId={CAT_ID}&pageNo={page}&pageSize={PAGE_SIZE}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def fetch_article(code: str) -> dict:
    url = f"https://www.binance.com/bapi/composite/v1/public/cms/article/detail/query?articleCode={code}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


# --- title filtering ---
DELIST_RX = re.compile(r"Binance Futures Will Delist", re.I)
USDS_M_RX = re.compile(r"USD[ⓈⓢS]-?M", re.I)
COIN_M_ONLY_RX = re.compile(r"^[^()]*COIN-?M[^()]*$", re.I)  # only COIN-M with no USDS-M
DATE_RX = re.compile(r"\((\d{4}-\d{2}-\d{2})(?:\s*&\s*(\d{4}-\d{2}-\d{2}))?\)")
SYM_RX = re.compile(r"\b([A-Z0-9]{2,15}USDT)\b")
MULTIPLE_RX = re.compile(r"Multiple", re.I)


def is_futures_delist_title(title: str) -> bool:
    if not DELIST_RX.search(title):
        return False
    # Skip "Update the Leverage" — those are margin tier announcements, not actual delistings
    if "Update the Leverage" in title:
        return False
    # If title contains COIN-M AND no USDS-M reference, skip (we want USDS-M only)
    has_coin_m = "COIN-M" in title or "COIN-Ⓜ" in title
    has_usds_m = bool(USDS_M_RX.search(title))
    if has_coin_m and not has_usds_m and "Multiple" not in title:
        return False
    return True


def walk_text(node) -> str:
    """Walk Binance body JSON tree and concat text content."""
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return " ".join(walk_text(n) for n in node)
    if isinstance(node, dict):
        if node.get("node") == "text":
            return node.get("text", "")
        chunks = []
        for child in node.get("child", []) or []:
            chunks.append(walk_text(child))
        return " ".join(chunks)
    return ""


def parse_body_text(body_str: str) -> str:
    if not body_str:
        return ""
    try:
        tree = json.loads(body_str)
        return walk_text(tree)
    except json.JSONDecodeError:
        # Fallback: strip HTML
        return re.sub(r"<[^>]+>", " ", body_str)


def parse_date(s: str) -> datetime | None:
    try:
        return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def extract_delist_date_from_text(text: str) -> datetime | None:
    """Find the actual delisting date in body text.
    Patterns:
      'delist ... at YYYY-MM-DD HH:MM (UTC)' or 'on YYYY-MM-DD'
      'remove ... contract(s) on YYYY-MM-DD HH:MM (UTC)'
    Returns earliest matching date >= 2024-01-01.
    """
    if not text:
        return None
    candidates = []
    # Pattern 1: explicit ' YYYY-MM-DD HH:MM (UTC)' — prefer this (delisting time)
    for m in re.finditer(r"(\d{4}-\d{2}-\d{2})\s+\d{2}:\d{2}\s*\(?\s*UTC\s*\)?", text):
        d = parse_date(m.group(1))
        if d and d >= START_DATE:
            candidates.append(d)
    # Pattern 2: any 'YYYY-MM-DD' (less reliable)
    if not candidates:
        for m in re.finditer(r"\b(\d{4}-\d{2}-\d{2})\b", text):
            d = parse_date(m.group(1))
            if d and d >= START_DATE:
                candidates.append(d)
    if not candidates:
        return None
    # Choose the FIRST candidate (earliest text mention is usually the delisting time)
    return candidates[0]


def extract_symbols_from_text(text: str) -> list[str]:
    """USDT-suffixed symbols only (USDS-M perps)."""
    syms = set()
    # Common false-positive filter: USDT alone, BUSDT, mark price tokens
    blacklist = {"USDT", "BUSDT"}
    for m in SYM_RX.finditer(text):
        s = m.group(1)
        if s in blacklist:
            continue
        if s.endswith("USDT") and len(s) > 4:
            syms.add(s)
    return sorted(syms)


def main():
    log.info("Phase 1a: scanning catalog %s pages ...", CAT_ID)
    raw_candidates = []
    for page in range(1, 12):
        try:
            j = fetch_catalog(page)
        except Exception as e:
            log.error("catalog page %d failed: %s", page, e)
            break
        arts = (j.get("data") or {}).get("articles", [])
        if not arts:
            log.info("page %d empty -- end of catalog", page)
            break
        for a in arts:
            title = a.get("title", "")
            code = a.get("code", "")
            if not is_futures_delist_title(title):
                continue
            raw_candidates.append({"code": code, "title": title})
        time.sleep(0.2)
    log.info("phase 1a done: %d candidate titles (cat %s)", len(raw_candidates), CAT_ID)

    log.info("Phase 1b: fetching per-article detail (publishDate + body) ...")
    events = []
    skipped = []
    for i, c in enumerate(raw_candidates):
        title = c["title"]
        code = c["code"]
        try:
            j = fetch_article(code)
        except Exception as e:
            log.warning("detail fetch %s failed: %s", code, e)
            time.sleep(0.5)
            continue
        data = j.get("data") or {}
        publish_ms = data.get("publishDate")
        if not publish_ms:
            skipped.append(("no_publishDate", title))
            time.sleep(0.25)
            continue
        announce_ts = datetime.fromtimestamp(publish_ms / 1000, tz=timezone.utc)
        if announce_ts < START_DATE or announce_ts > END_DATE:
            skipped.append((f"out_of_range_{announce_ts.date()}", title[:80]))
            time.sleep(0.25)
            continue
        body_text = parse_body_text(data.get("body", "") or "")
        # Title can also yield symbols (preferred), body fills "Multiple" cases
        syms_title = extract_symbols_from_text(title)
        syms_body = extract_symbols_from_text(body_text)
        syms = sorted(set(syms_title) | set(syms_body))

        # Date: title parenthesized date, fallback to body
        title_date_match = DATE_RX.search(title)
        delist_dt = parse_date(title_date_match.group(1)) if title_date_match else None
        if not delist_dt:
            delist_dt = extract_delist_date_from_text(body_text)
        if not syms:
            skipped.append(("no_symbols", title[:120]))
            time.sleep(0.25)
            continue
        if not delist_dt:
            skipped.append(("no_delist_date", title[:120]))
            time.sleep(0.25)
            continue
        if delist_dt <= announce_ts:
            skipped.append((f"delist_<=_announce_{delist_dt.date()}_vs_{announce_ts.date()}", title[:80]))
            time.sleep(0.25)
            continue
        for s in syms:
            gap_days = (delist_dt - announce_ts).total_seconds() / 86400.0
            events.append({
                "announce_ts": announce_ts.isoformat(),
                "delist_ts": delist_dt.isoformat(),
                "symbol": s,
                "gap_days": round(gap_days, 3),
                "source_title": title[:200],
            })
        if (i + 1) % 10 == 0:
            log.info("  detail progress %d/%d -> %d events so far",
                     i + 1, len(raw_candidates), len(events))
        time.sleep(0.3)

    log.info("phase 1b done: %d (symbol, event) rows; %d titles skipped", len(events), len(skipped))
    for tag, t in skipped[:25]:
        log.info("  skip: %s | %s", tag, t)

    # Dedup
    seen = set()
    uniq = []
    for e in events:
        k = (e["symbol"], e["announce_ts"], e["delist_ts"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(e)
    log.info("dedup: %d -> %d", len(events), len(uniq))

    with open(OUT_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["announce_ts", "delist_ts", "symbol", "gap_days", "source_title"])
        w.writeheader()
        for r in uniq:
            w.writerow(r)
    log.info("wrote %s (%d rows)", OUT_CSV, len(uniq))

    if uniq:
        log.info("first 5 events:")
        for r in uniq[:5]:
            log.info("  %s -> %s | %s (gap %.1fd)",
                     r["announce_ts"], r["delist_ts"], r["symbol"], r["gap_days"])
        log.info("last 5 events:")
        for r in uniq[-5:]:
            log.info("  %s -> %s | %s (gap %.1fd)",
                     r["announce_ts"], r["delist_ts"], r["symbol"], r["gap_days"])
    return uniq


if __name__ == "__main__":
    main()
