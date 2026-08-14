"""paradigm_253 R-0 prescreen — CBOE VIX 90d z extreme × alt bilateral 7d.

R-0 checklist (dispatch brief items 1-9):
  1. Lesson #61 slug grep  — no prior VIX paradigm in INDEX
  2. Lesson #79 predictive-content pretest  — |corr(vix_z, fwd_7d_alt_ret)|
     on OOS half.  Threshold for 7d cross-asset: >= 0.02 (base) / 0.05 (ideal).
  3. Lesson #28 substrate audit  — FRED VIX CSV reachable + 2y+ history
  4. Lesson #62 DNA 5/6 overlap  — recorded from dispatch brief
  5. Lesson #56 family proxy  — vs paradigm 239 graveyard 7d prescription
  6. Lesson #40 structural threshold feasibility  — vix_z range
  7. Lesson #11 sample density  — events per symbol per year
  8. Lesson #39 direction-axis pre-check  — non-bar_direction axis
  9. Lesson #82 candidate  — timestamp-explicit price (open at T+1 midnight)

Data sources chosen for this paradigm:
  - VIX daily: FRED CSV via curl (proven reliable)
  - Alt daily OHLCV: Binance REST /klines interval=1d (fresh, fast,
    ~1s per symbol, current to yesterday).  Local DB ohlcv table only
    stores 1m data at 27GB with GROUP BY-hostile query plan, and joblib
    cache is 89-day stale — REST is the honest path for 3군 판정 since
    tier3_gate wt_edge weighs by (now - t) with 90d halflife.

Outputs:
  runs/research_track/paradigm_253_.../r0_prescreen.json
"""
from __future__ import annotations

import io
import json
import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE / "scripts"))
sys.path.insert(0, str(BASE))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("paradigm_253_r0")

PARADIGM = "paradigm_253_cboe_vix_extreme_regime_alt_bilateral_7d"
OUT_DIR = BASE / "runs" / "research_track" / PARADIGM
OUT_DIR.mkdir(parents=True, exist_ok=True)

FRED_VIX_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=VIXCLS"
BINANCE_KLINES = "https://api.binance.com/api/v3/klines"

UNIVERSE = [
    "ADAUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "BTCUSDT",
    "DOGEUSDT", "ETHUSDT", "FILUSDT", "LINKUSDT", "LTCUSDT",
    "NEARUSDT", "SOLUSDT", "WIFUSDT", "XRPUSDT",
]
PRETEST_SYMS = ["SOLUSDT", "BTCUSDT", "DOGEUSDT", "ETHUSDT", "AVAXUSDT"]

ROLL_WINDOW = 90
HOLD_DAYS = 7
THRESHOLDS = [1.0, 1.5, 2.0]
FEE_ROUND_TRIP = 0.0008

CORR_MIN_HARD = 0.02
CORR_MIN_SOFT = 0.05


def _curl(url: str, timeout: int = 30) -> str:
    result = subprocess.run(
        ["curl", "-sS", "--max-time", str(timeout), url],
        capture_output=True, timeout=timeout + 10,
    )
    if result.returncode != 0:
        raise RuntimeError(f"curl failed for {url[:80]}: "
                           f"{result.stderr.decode()[:200]}")
    return result.stdout.decode("utf-8", errors="replace")


def fetch_vix() -> pd.DataFrame:
    log.info("FRED VIX CSV fetch: %s", FRED_VIX_URL)
    raw = _curl(FRED_VIX_URL, timeout=30)
    df = pd.read_csv(io.StringIO(raw))
    df.columns = [c.strip() for c in df.columns]
    date_col = "observation_date" if "observation_date" in df.columns else "DATE"
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.rename(columns={date_col: "d", "VIXCLS": "vix"})
    df["vix"] = pd.to_numeric(df["vix"], errors="coerce")
    df = df.dropna(subset=["d", "vix"]).set_index("d").sort_index()
    log.info("VIX rows=%d  span=%s..%s", len(df),
             df.index.min().date(), df.index.max().date())
    return df


def fetch_binance_daily(symbol: str, limit: int = 1000) -> pd.DataFrame:
    """Fetch daily klines via binance REST. Returns DataFrame indexed by
    UTC midnight open time with columns open/high/low/close/volume/quote_vol."""
    url = f"{BINANCE_KLINES}?symbol={symbol}&interval=1d&limit={limit}"
    raw = _curl(url, timeout=15)
    data = json.loads(raw)
    if not data:
        return pd.DataFrame()
    rows = []
    for k in data:
        rows.append({
            "d": pd.to_datetime(k[0], unit="ms"),
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5]),
            "quote_vol": float(k[7]),
        })
    df = pd.DataFrame(rows).set_index("d").sort_index()
    return df


def z90(s: pd.Series, window: int = ROLL_WINDOW) -> pd.Series:
    mu = s.rolling(window, min_periods=window // 2).mean()
    sd = s.rolling(window, min_periods=window // 2).std()
    return (s - mu) / sd


def load_alt_daily(symbols):
    out = {}
    for sym in symbols:
        try:
            df = fetch_binance_daily(sym, limit=1000)
        except Exception as exc:
            log.warning("skip %s: %s", sym, exc)
            continue
        if df.empty:
            log.warning("skip %s: empty", sym)
            continue
        out[sym] = df
        log.info("loaded %s rows=%d span=%s..%s", sym, len(df),
                 df.index.min().date(), df.index.max().date())
    return out


def forward_ret(px_open: pd.Series, hold_days: int) -> pd.Series:
    entry = px_open.shift(-1)
    exit_ = px_open.shift(-(1 + hold_days))
    return (exit_ / entry) - 1.0


def _describe(a: np.ndarray) -> dict:
    a = a[np.isfinite(a)]
    if len(a) == 0:
        return {}
    return {
        "n": int(len(a)),
        "mean": round(float(a.mean()), 6),
        "std": round(float(a.std(ddof=1)) if len(a) > 1 else 0.0, 6),
        "min": round(float(a.min()), 4),
        "p05": round(float(np.percentile(a, 5)), 4),
        "p50": round(float(np.percentile(a, 50)), 4),
        "p95": round(float(np.percentile(a, 95)), 4),
        "max": round(float(a.max()), 4),
    }


def main() -> int:
    started = datetime.utcnow()
    report = {
        "paradigm": PARADIGM,
        "paradigm_number": 253,
        "started_at": started.isoformat(timespec="seconds"),
        "checks": {},
    }

    report["checks"]["lesson61_slug_grep"] = {
        "status": "PASS",
        "note": "no VIX / CBOE paradigm in INDEX.json (verified pre-dispatch)",
    }

    try:
        vix = fetch_vix()
    except Exception as exc:
        report["checks"]["lesson28_substrate"] = {
            "status": "HALT", "error": f"FRED fetch failed: {exc}",
        }
        (OUT_DIR / "r0_prescreen.json").write_text(json.dumps(report, indent=2))
        log.error("FRED fetch failed — R-0 HALT")
        return 1

    report["checks"]["lesson28_substrate"] = {
        "status": "PASS",
        "rows": int(len(vix)),
        "span": [str(vix.index.min().date()), str(vix.index.max().date())],
        "coverage_years": round(
            (vix.index.max() - vix.index.min()).days / 365.25, 2),
    }

    vix_z = z90(vix["vix"]).dropna()
    z_desc = _describe(vix_z.values)
    report["checks"]["lesson40_structural"] = {
        "status": "PASS" if (z_desc["max"] >= max(THRESHOLDS) and
                             z_desc["min"] <= -max(THRESHOLDS)) else "HALT",
        "vix_z_dist": z_desc,
        "thresholds_tested": THRESHOLDS,
        "note": "|vix_z| >= 2.0 must be achievable in BOTH signs",
    }
    if report["checks"]["lesson40_structural"]["status"] == "HALT":
        (OUT_DIR / "r0_prescreen.json").write_text(json.dumps(report, indent=2))
        log.error("structural feasibility HALT")
        return 1

    density = {}
    for T in THRESHOLDS:
        mask = (vix_z.abs() >= T)
        mask_recent = mask.loc["2024-01-01":]
        n_events = int(mask_recent.sum())
        yrs = (mask_recent.index.max() - mask_recent.index.min()).days / 365.25
        density[f"T={T}"] = {
            "n_events_2024_present": n_events,
            "years": round(yrs, 2),
            "events_per_year": round(n_events / yrs if yrs > 0 else 0.0, 1),
            "trigger_rate_pct": round(100.0 * mask_recent.mean(), 2),
        }
    per_sym_per_year_at_T15 = density["T=1.5"]["events_per_year"]
    report["checks"]["lesson11_density"] = {
        "status": "PASS" if per_sym_per_year_at_T15 >= 20 else "MARGINAL",
        "detail": density,
        "note": "target: >= 30 events per cell across 2.7y backtest",
    }

    report["checks"]["lesson39_direction_axis"] = {
        "status": "PASS",
        "note": "vix_z sign = macro fear/complacency regime axis (not bar_direction)",
    }

    try:
        alt_daily = load_alt_daily(PRETEST_SYMS)
    except Exception as exc:
        report["checks"]["lesson79_pretest"] = {
            "status": "HALT", "error": f"binance daily load failed: {exc}",
        }
        (OUT_DIR / "r0_prescreen.json").write_text(json.dumps(report, indent=2))
        log.error("alt daily load failed — R-0 HALT")
        return 1

    if not alt_daily:
        report["checks"]["lesson79_pretest"] = {
            "status": "HALT",
            "error": "no alt data loaded",
        }
        (OUT_DIR / "r0_prescreen.json").write_text(json.dumps(report, indent=2))
        return 1

    corr_table = {}
    max_abs = 0.0
    for sym, df in alt_daily.items():
        alt_open = df["open"].copy()
        alt_open.index = pd.to_datetime(alt_open.index).normalize()
        fwd = forward_ret(alt_open, HOLD_DAYS)
        vz = vix_z.copy()
        vz.index = pd.to_datetime(vz.index).normalize()
        aligned = pd.concat([vz.rename("z"), fwd.rename("r")], axis=1).dropna()
        n = len(aligned)
        if n < 100:
            corr_table[sym] = {"n": n, "corr_oos": None, "status": "SKIP_LOWN"}
            continue
        oos = aligned.iloc[n // 2 :]
        c_oos = float(oos["z"].corr(oos["r"]))
        c_full = float(aligned["z"].corr(aligned["r"]))
        corr_table[sym] = {
            "n_full": n,
            "n_oos": int(len(oos)),
            "corr_oos": round(c_oos, 4),
            "corr_full": round(c_full, 4),
            "span_full": [str(aligned.index.min().date()),
                          str(aligned.index.max().date())],
        }
        max_abs = max(max_abs, abs(c_oos))

    if max_abs >= CORR_MIN_SOFT:
        pretest_status = "PASS_IDEAL"
    elif max_abs >= CORR_MIN_HARD:
        pretest_status = "PASS_MARGINAL"
    else:
        pretest_status = "HALT"

    report["checks"]["lesson79_pretest"] = {
        "status": pretest_status,
        "hold_days": HOLD_DAYS,
        "threshold_hard": CORR_MIN_HARD,
        "threshold_soft": CORR_MIN_SOFT,
        "max_abs_corr_oos": round(max_abs, 4),
        "per_sym": corr_table,
    }

    report["checks"]["lesson62_dna"] = {
        "status": "PASS",
        "closest_predecessors": {
            "paradigm_239_btc_dominance": "2/6 (substrate+universe)",
            "paradigm_248_btc_onchain": "2/6 (external substrate+universe)",
            "btc_spot_etf_netflow_regime_weekly_bilateral":
                "3/6 (external substrate+universe+bilateral+weekly hold)",
        },
        "max_overlap": "3/6",
        "hard_fail_threshold": "5/6",
    }

    report["checks"]["lesson56_family_proxy"] = {
        "status": "PASS",
        "note": ("paradigm 239 graveyard prescribed extend hold >= 7d; "
                 "this paradigm implements that at 7d with |corr|>=0.05 "
                 "soft threshold (fee/hold=1.14bp/day vs 8bp/day at 1d)"),
    }

    report["checks"]["lesson82_timestamp"] = {
        "status": "PASS",
        "note": ("entry at day T+1 UTC 00:00 open; VIX close is 21:15 "
                 "UTC same day so trigger→entry is chronologically clean"),
    }

    halts = [k for k, v in report["checks"].items() if v.get("status") == "HALT"]
    marginals = [k for k, v in report["checks"].items()
                 if v.get("status") in ("MARGINAL", "PASS_MARGINAL")]

    if halts:
        overall = "R0_HALT"
    elif marginals:
        overall = "R0_PROCEED_WITH_CAUTION"
    else:
        overall = "R0_PROCEED"

    report["overall"] = overall
    report["halts"] = halts
    report["marginals"] = marginals
    report["finished_at"] = datetime.utcnow().isoformat(timespec="seconds")

    out_path = OUT_DIR / "r0_prescreen.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    log.info("R-0 verdict: %s  halts=%s  marginals=%s",
             overall, halts, marginals)
    log.info("saved: %s", out_path)
    return 0 if overall != "R0_HALT" else 1


if __name__ == "__main__":
    sys.exit(main())
