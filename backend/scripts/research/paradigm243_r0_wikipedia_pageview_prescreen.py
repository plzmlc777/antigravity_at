"""Paradigm #243 R-0 prescreen — Wikipedia page views attention spike (bilateral 1d-3d).

Steps
-----
0. Slug grep — verify no prior wikipedia/pageview paradigm exists.
1. Fetch daily Wikipedia article page views for 13 mapped Binance perps
   via Wikimedia REST API (free, no auth). Sequential, 0.5s sleep.
2. Cache raw data to wiki_views_cache.json.
3. Substrate audit: for each symbol, report n_days available.
4. Empirical trigger rate at z_log_views ≥ +1.5 and ≤ -1.5 on rolling 30d baseline.
5. Predictive content pretest (Lesson #79): BTC z_log_views vs next-day BTC return.
6. Sample density check per Lesson #11.
7. Save r0_prescreen.json.
"""
from __future__ import annotations

import json
import logging
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import joblib

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("p243_r0")

PARADIGM = "alt_wikipedia_pageview_attention_spike_bilateral_1d_to_3d"
ROOT = Path("/home/mint/auto_trading/backend")
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM
OUT_DIR.mkdir(parents=True, exist_ok=True)
CACHE_PATH = OUT_DIR / "wiki_views_cache.json"
METRICS_PATH = OUT_DIR / "r0_prescreen.json"
INDEX_PATH = ROOT / "runs" / "research_track" / "INDEX.json"
OHLCV_DIR = ROOT / "runs" / "ohlcv_cache"

ARTICLE_MAP: Dict[str, List[str]] = {
    "BTCUSDT":  ["Bitcoin"],
    "ETHUSDT":  ["Ethereum"],
    "SOLUSDT":  ["Solana_(blockchain_platform)", "Solana_(blockchain)"],
    "ADAUSDT":  ["Cardano_(blockchain_platform)"],
    "XRPUSDT":  ["XRP_Ledger", "XRP_(cryptocurrency)", "Ripple_(payment_protocol)"],
    "DOGEUSDT": ["Dogecoin"],
    "LINKUSDT": ["Chainlink_(blockchain_oracle)", "Chainlink_(blockchain)"],
    "BNBUSDT":  ["BNB_(cryptocurrency)", "Binance_Coin", "Binance"],
    "AVAXUSDT": ["Avalanche_(blockchain_platform)"],
    "LTCUSDT":  ["Litecoin"],
    "NEARUSDT": ["Near_Protocol", "NEAR_Protocol"],
    "FILUSDT":  ["Filecoin"],
}

START_DATE = "20240102"
END_DATE = "20260512"


def slug_grep() -> Dict[str, object]:
    """Search INDEX.json for wikipedia/pageview/wiki_view slugs."""
    txt = INDEX_PATH.read_text() if INDEX_PATH.exists() else ""
    hits: List[str] = []
    for token in ("wikipedia", "pageview", "wiki_view", "wiki_"):
        if token.lower() in txt.lower():
            hits.append(token)
    return {"tokens_checked": ["wikipedia", "pageview", "wiki_view", "wiki_"],
            "hits": hits, "clean": len(hits) == 0}


def fetch_wiki_views(article: str, start: str = START_DATE,
                     end: str = END_DATE) -> Optional[List[Tuple[str, int]]]:
    url = (
        f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
        f"en.wikipedia/all-access/all-agents/{article}/daily/{start}00/{end}00"
    )
    req = urllib.request.Request(url, headers={
        "User-Agent": "research-paradigm-243/1.0 (hyeongchol.park@gmail.com)"
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        log.warning("HTTP %s for %s", e.code, article)
        return None
    except Exception as e:
        log.warning("fetch fail %s: %s", article, e)
        return None
    return [(item["timestamp"][:8], int(item["views"]))
            for item in payload.get("items", [])]


def fetch_symbol(sym: str, candidates: List[str]) -> Dict[str, object]:
    for article in candidates:
        log.info("try %s -> article=%s", sym, article)
        data = fetch_wiki_views(article)
        time.sleep(0.5)
        if data and len(data) >= 500:
            log.info("  OK %s: n=%d rows via %s", sym, len(data), article)
            return {"sym": sym, "article": article, "n_days": len(data),
                    "rows": data}
        log.warning("  MISS %s article=%s (n=%s)", sym, article,
                    len(data) if data else 0)
    return {"sym": sym, "article": None, "n_days": 0, "rows": []}


def load_or_fetch_all() -> Dict[str, dict]:
    if CACHE_PATH.exists():
        log.info("loading cached wiki data %s", CACHE_PATH)
        with CACHE_PATH.open() as f:
            raw = json.load(f)
        return raw
    out: Dict[str, dict] = {}
    for sym, candidates in ARTICLE_MAP.items():
        out[sym] = fetch_symbol(sym, candidates)
    with CACHE_PATH.open("w") as f:
        json.dump(out, f, indent=2)
    log.info("cached wiki data -> %s", CACHE_PATH)
    return out


def build_views_df(raw: Dict[str, dict]) -> pd.DataFrame:
    """Return DataFrame indexed by date with column per symbol (raw views)."""
    frames = []
    for sym, rec in raw.items():
        rows = rec.get("rows") or []
        if not rows:
            continue
        s = pd.Series({pd.Timestamp(ts): int(v) for ts, v in rows},
                      name=sym).sort_index()
        frames.append(s)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, axis=1)


def load_daily_close(sym: str) -> Optional[pd.Series]:
    p = OHLCV_DIR / f"{sym}_1m.joblib"
    if not p.exists():
        return None
    df = joblib.load(p)
    close = df["close"].astype(float)
    # daily close = last close of day (naive UTC as stored)
    daily = close.resample("1D").last().dropna()
    return daily


def compute_z(views: pd.Series, window: int = 30) -> pd.Series:
    lv = np.log(views.astype(float).clip(lower=1) + 1.0)
    m = lv.rolling(window, min_periods=window).mean()
    s = lv.rolling(window, min_periods=window).std(ddof=1)
    return (lv - m) / s.replace(0, np.nan)


def predictive_pretest(views_btc: pd.Series,
                       close_btc: pd.Series) -> Dict[str, float]:
    """Lesson #79 pretest: BTC z_log_views vs next-day return."""
    z = compute_z(views_btc, 30)
    ret = close_btc.pct_change().shift(-1)  # next-day return
    df = pd.concat([z.rename("z"), ret.rename("r")], axis=1).dropna()
    if len(df) < 30:
        return {"n": len(df), "note": "too few overlapping rows"}
    r = float(df["z"].corr(df["r"]))
    # sign-based t-stat: mean return conditioned on z ≥ +1.5 vs baseline
    hi = df.loc[df["z"] >= 1.5, "r"].values
    lo = df.loc[df["z"] <= -1.5, "r"].values
    def _t(a: np.ndarray) -> float:
        if len(a) < 2:
            return 0.0
        sd = a.std(ddof=1)
        if sd == 0:
            return 0.0
        return float(a.mean() / sd * np.sqrt(len(a)))
    return {
        "n_overlap": int(len(df)),
        "pearson_corr_z_vs_next_ret": r,
        "n_hi_events": int(len(hi)),
        "mean_ret_next_hi_bp": float(hi.mean() * 1e4) if len(hi) else 0.0,
        "t_hi": _t(hi),
        "n_lo_events": int(len(lo)),
        "mean_ret_next_lo_bp": float(lo.mean() * 1e4) if len(lo) else 0.0,
        "t_lo": _t(lo),
    }


def main() -> None:
    log.info("=== paradigm #243 R-0 prescreen: %s ===", PARADIGM)

    # Step 0 — slug grep
    grep = slug_grep()
    log.info("slug_grep: %s", grep)
    if not grep["clean"]:
        log.error("slug grep HIT — halt")
        METRICS_PATH.write_text(json.dumps({"phase": "R-0",
                                            "verdict": "HALT_SLUG_HIT",
                                            "slug_grep": grep}, indent=2))
        return

    # Step 1 — fetch
    raw = load_or_fetch_all()

    # Step 2 — substrate audit
    substrate: Dict[str, dict] = {}
    for sym, rec in raw.items():
        substrate[sym] = {
            "article_used": rec.get("article"),
            "n_days": rec.get("n_days", 0),
            "ok": (rec.get("n_days") or 0) >= 500,
        }
    n_pass = sum(1 for v in substrate.values() if v["ok"])
    log.info("substrate: %d/%d syms with n≥500", n_pass, len(substrate))
    if n_pass < 5:
        verdict = "R0_HALT_SUBSTRATE_INSUFFICIENT"
        log.error(verdict)
        METRICS_PATH.write_text(json.dumps({"phase": "R-0", "verdict": verdict,
                                            "slug_grep": grep,
                                            "substrate": substrate}, indent=2))
        return

    # Step 3 — build DF and empirical trigger rates
    views_df = build_views_df(raw)
    log.info("views_df shape %s dates %s..%s",
             views_df.shape, views_df.index.min(), views_df.index.max())

    trigger_stats: Dict[str, dict] = {}
    for sym in views_df.columns:
        v = views_df[sym].dropna()
        if len(v) < 60:
            continue
        z = compute_z(v, 30).dropna()
        hi = int((z >= 1.5).sum())
        lo = int((z <= -1.5).sum())
        n = len(z)
        trigger_stats[sym] = {
            "n_z_measurable": n,
            "hi_events": hi,
            "lo_events": lo,
            "hi_rate": hi / n if n else 0.0,
            "lo_rate": lo / n if n else 0.0,
        }
    hi_total = sum(v["hi_events"] for v in trigger_stats.values())
    lo_total = sum(v["lo_events"] for v in trigger_stats.values())
    n_syms_trigger = len(trigger_stats)
    hi_per_cell_est = hi_total   # per quadrant total events
    lo_per_cell_est = lo_total
    log.info("trigger totals: hi=%d lo=%d syms=%d", hi_total, lo_total,
             n_syms_trigger)

    # Step 4 — Lesson #79 predictive pretest on BTC
    btc_views = views_df.get("BTCUSDT")
    btc_close = load_daily_close("BTCUSDT") if btc_views is not None else None
    pretest = {}
    if btc_views is not None and btc_close is not None:
        pretest = predictive_pretest(btc_views, btc_close)
        log.info("BTC predictive pretest: %s", pretest)

    # Lesson #79 halt: only if BOTH tails simultaneously flat
    lesson79_halt = False
    if pretest and "t_hi" in pretest and "t_lo" in pretest:
        corr = abs(pretest.get("pearson_corr_z_vs_next_ret", 0.0))
        t_hi = abs(pretest["t_hi"])
        t_lo = abs(pretest["t_lo"])
        if t_hi < 0.5 and t_lo < 0.5 and corr < 0.02:
            lesson79_halt = True

    # Step 5 — Lesson #11 sample density (per quadrant/cell across quarters)
    # 12 quarters (2024Q1..2027Q1 range subset). Approx per-quarter events
    # per quadrant = hi_total / n_quarters (or lo_total). Threshold 30.
    n_quarters_est = 10  # 2024Q1..2026Q2
    per_q_per_quad = {
        "hi_per_quarter_avg": hi_total / n_quarters_est,
        "lo_per_quarter_avg": lo_total / n_quarters_est,
        "threshold": 30,
        "hi_meets_lesson11": (hi_total / n_quarters_est) >= 30,
        "lo_meets_lesson11": (lo_total / n_quarters_est) >= 30,
    }

    verdict = "R0_PASS"
    reasons: List[str] = []
    if not per_q_per_quad["hi_meets_lesson11"]:
        verdict = "R0_HALT_SAMPLE_DENSITY"
        reasons.append("hi tail <30 per quarter")
    if not per_q_per_quad["lo_meets_lesson11"]:
        verdict = "R0_HALT_SAMPLE_DENSITY"
        reasons.append("lo tail <30 per quarter")
    if lesson79_halt:
        verdict = "R0_HALT_LESSON79_ZERO_PREDICTIVE_CONTENT"
        reasons.append("BTC pretest: |t_hi|<0.5 AND |t_lo|<0.5 AND |corr|<0.02")

    out = {
        "paradigm": PARADIGM,
        "phase": "R-0",
        "verdict": verdict,
        "reasons": reasons,
        "slug_grep": grep,
        "substrate": substrate,
        "n_syms_pass": n_pass,
        "date_range": [str(views_df.index.min()), str(views_df.index.max())],
        "trigger_stats_per_sym": trigger_stats,
        "hi_total_events": hi_total,
        "lo_total_events": lo_total,
        "lesson11_check": per_q_per_quad,
        "lesson79_pretest_btc": pretest,
        "lesson79_halt": lesson79_halt,
    }
    METRICS_PATH.write_text(json.dumps(out, indent=2, default=str))
    log.info("=== R-0 verdict: %s ===", verdict)
    log.info("metrics -> %s", METRICS_PATH)


if __name__ == "__main__":
    main()
