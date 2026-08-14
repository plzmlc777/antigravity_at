"""Scrape Binance Futures USDS-M perp MM tier / leverage bracket change announcements.

Two catalog IDs to probe:
  - 161  (Trading Rules / Futures Announcements)
  - 48   (general Binance Futures)

Title filter: needle = ("Update the Leverage" OR "Adjust the Leverage" OR
                       "Adjust ... Margin Tier" OR "Adjust ... Position Limits"
                       OR "Update ... Maintenance Margin")

Output: mm_tier_events.csv
    columns: announce_ts (UTC ISO), effective_ts (UTC ISO or blank),
             symbol, direction (hike/cut/unknown), source_title
"""
from __future__ import annotations
import csv
import json
import logging
import re
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)

OUT_DIR = Path(__file__).resolve().parent
OUT_CSV = OUT_DIR / "mm_tier_events.csv"
CAT_IDS = [49, 161, 48]
PAGE_SIZE = 50
START_DATE = datetime(2024, 1, 1, tzinfo=timezone.utc)
END_DATE = datetime(2026, 7, 18, tzinfo=timezone.utc)

# Title needles for MM tier / leverage bracket / notional cap changes
MM_TITLE_RX = re.compile(
    r"(Update the Leverage|Adjust the Leverage|Update Leverage & Margin|"
    r"Margin\s+Tier|Maintenance\s+Margin|Position\s+Limit|Risk\s+Limit|Notional Cap)",
    re.I,
)
DATE_RX = re.compile(r"\((\d{4}-\d{2}-\d{2})\)")
SYM_RX = re.compile(r"\b([A-Z0-9]{2,15}USDT)\b")


def _do_get(url: str, max_retries: int = 5):
    backoff = 10
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < max_retries - 1:
                log.warning("  429; backoff %ds (attempt %d)", backoff, attempt + 1)
                time.sleep(backoff)
                backoff = min(backoff * 2, 300)
                continue
            raise


def fetch_catalog(cat_id: int, page: int) -> dict:
    url = (
        f"https://www.binance.com/bapi/composite/v1/public/cms/article/catalog/list/query"
        f"?catalogId={cat_id}&pageNo={page}&pageSize={PAGE_SIZE}"
    )
    return _do_get(url)


def fetch_article(code: str) -> dict:
    url = f"https://www.binance.com/bapi/composite/v1/public/cms/article/detail/query?articleCode={code}"
    return _do_get(url)


def walk_text(node) -> str:
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
        return re.sub(r"<[^>]+>", " ", body_str)


def extract_symbols(text: str) -> list[str]:
    syms = set()
    blacklist = {"USDT", "BUSDT"}
    for m in SYM_RX.finditer(text):
        s = m.group(1)
        if s in blacklist:
            continue
        if s.endswith("USDT") and len(s) > 4:
            syms.add(s)
    return sorted(syms)


def infer_direction(title: str, body_text: str) -> str:
    """Heuristic direction inference:
      - 'reduce' / 'decrease' / 'lower' max leverage OR 'raise' maintenance margin
        -> tier HIKE (stricter, forces deleveraging)
      - 'increase' / 'raise' max leverage OR 'lower' maintenance margin OR
        'expand notional cap' -> tier CUT (relaxed)
    Return 'hike' / 'cut' / 'unknown'.
    """
    joined = (title + " " + body_text[:5000]).lower()
    hike_signals = 0
    cut_signals = 0
    if re.search(r"reduc(e|ing)\s+.*(max|maximum)\s+leverage", joined):
        hike_signals += 2
    if re.search(r"decreas(e|ing)\s+.*(max|maximum)\s+leverage", joined):
        hike_signals += 2
    if re.search(r"lower\s+.*(max|maximum)\s+leverage", joined):
        hike_signals += 2
    if re.search(r"increas(e|ing)\s+.*maintenance\s+margin", joined):
        hike_signals += 2
    if re.search(r"rais(e|ing)\s+.*maintenance\s+margin", joined):
        hike_signals += 2
    if re.search(r"tighter|stricter", joined):
        hike_signals += 1
    # cut signals
    if re.search(r"increas(e|ing)\s+.*(max|maximum)\s+leverage", joined):
        cut_signals += 2
    if re.search(r"rais(e|ing)\s+.*(max|maximum)\s+leverage", joined):
        cut_signals += 2
    if re.search(r"expand(ed|ing)?\s+.*(notional|position)\s+limit", joined):
        cut_signals += 2
    if re.search(r"increas(e|ing)\s+.*notional\s+cap", joined):
        cut_signals += 2
    if re.search(r"decreas(e|ing)\s+.*maintenance\s+margin", joined):
        cut_signals += 2
    if re.search(r"lower\s+.*maintenance\s+margin", joined):
        cut_signals += 2
    if hike_signals > cut_signals and hike_signals >= 2:
        return "hike"
    if cut_signals > hike_signals and cut_signals >= 2:
        return "cut"
    # fallback via title keywords
    if "reduce" in title.lower() or "decrease" in title.lower():
        return "hike"
    if "increase" in title.lower() or "raise" in title.lower() or "expand" in title.lower():
        return "cut"
    return "unknown"


def parse_date(s: str) -> datetime | None:
    try:
        return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def main():
    log.info("Phase 1: scanning MM tier candidates ...")
    seen_codes = set()
    raw = []
    for cat_id in CAT_IDS:
        log.info("  catalog %s ...", cat_id)
        for page in range(1, 20):
            try:
                j = fetch_catalog(cat_id, page)
            except Exception as e:
                log.error("catalog %s page %d failed: %s", cat_id, page, e)
                break
            arts = (j.get("data") or {}).get("articles", [])
            if not arts:
                log.info("  cat %s page %d empty -- end", cat_id, page)
                break
            for a in arts:
                title = a.get("title", "") or ""
                code = a.get("code", "") or ""
                if not code or code in seen_codes:
                    continue
                if not MM_TITLE_RX.search(title):
                    continue
                # Filter obvious non-MM: mark-price / index / API updates
                low = title.lower()
                if "mark price" in low or "index price" in low or "api rate" in low:
                    continue
                # STANDALONE MM tier: exclude delisting-bundled events (confounded mechanism)
                if re.search(r"Delist", title, re.I):
                    continue
                seen_codes.add(code)
                raw.append({"cat": cat_id, "code": code, "title": title})
            time.sleep(0.5)
    log.info("phase 1 done: %d candidate titles", len(raw))

    if not raw:
        log.warning("NO MM tier candidates found via catalog endpoint. Substrate unavailable.")
        with open(OUT_CSV, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["announce_ts", "effective_ts", "symbol", "direction", "source_title"])
            w.writeheader()
        log.info("wrote empty %s", OUT_CSV)
        return []

    log.info("Phase 2: fetching per-article body ...")
    events = []
    skipped = []
    for i, c in enumerate(raw):
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
            skipped.append(("no_publishDate", title[:80]))
            time.sleep(1.0)
            continue
        announce_ts = datetime.fromtimestamp(publish_ms / 1000, tz=timezone.utc)
        if announce_ts < START_DATE or announce_ts > END_DATE:
            skipped.append((f"out_of_range_{announce_ts.date()}", title[:80]))
            time.sleep(1.0)
            continue
        body_text = parse_body_text(data.get("body", "") or "")

        # symbols: title first
        syms_title = extract_symbols(title)
        syms_body = extract_symbols(body_text)
        syms = sorted(set(syms_title) | set(syms_body))

        if not syms:
            skipped.append(("no_symbols", title[:80]))
            time.sleep(1.0)
            continue

        direction = infer_direction(title, body_text)

        # effective_ts: parenthesized (YYYY-MM-DD) in title
        eff_dt = None
        m = DATE_RX.search(title)
        if m:
            eff_dt = parse_date(m.group(1))

        for s in syms:
            events.append({
                "announce_ts": announce_ts.isoformat(),
                "effective_ts": eff_dt.isoformat() if eff_dt else "",
                "symbol": s,
                "direction": direction,
                "source_title": title[:200],
            })
        if (i + 1) % 10 == 0:
            log.info("  progress %d/%d -> %d symbol-event rows", i + 1, len(raw), len(events))
        time.sleep(1.2)

    log.info("phase 2 done: %d rows | %d skipped", len(events), len(skipped))
    for tag, t in skipped[:15]:
        log.info("  skip: %s | %s", tag, t)

    # Dedup by (symbol, announce_ts)
    seen = set()
    uniq = []
    for e in events:
        k = (e["symbol"], e["announce_ts"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(e)
    log.info("dedup: %d -> %d", len(events), len(uniq))

    with open(OUT_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["announce_ts", "effective_ts", "symbol", "direction", "source_title"])
        w.writeheader()
        for r in uniq:
            w.writerow(r)
    log.info("wrote %s (%d rows)", OUT_CSV, len(uniq))

    # Diagnostics: per-direction, per-quarter
    from collections import Counter
    dir_ct = Counter(r["direction"] for r in uniq)
    log.info("direction counts: %s", dict(dir_ct))
    q_ct = Counter()
    for r in uniq:
        d = datetime.fromisoformat(r["announce_ts"])
        q = f"{d.year}Q{(d.month - 1) // 3 + 1}"
        q_ct[(q, r["direction"])] += 1
    log.info("per-quarter × direction:")
    for k in sorted(q_ct):
        log.info("  %s %s = %d", k[0], k[1], q_ct[k])

    return uniq


if __name__ == "__main__":
    main()
