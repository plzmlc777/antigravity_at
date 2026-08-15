"""포지셔닝 신호 검정 — **다른 참가자의 실제 포지션**.

왜 이 축인가
    2026-08-15 에 일곱 축이 기각됐다(신규상장·종목선별·성질선별·무차별규칙·
    횡단면모멘텀·온체인·SMB). 전부 **가격이거나 네트워크 활동**이었다.

    포지셔닝은 다르다 — 다른 참가자가 **실제로 어느 쪽에 얼마를 걸고 있는가**다.
    바이낸스 공개 아카이브(`metrics`)가 4년치를 무료로 준다:

        toptrader_ls_med       상위 트레이더 **포지션** 롱숏 비율
        toptrader_ls_cnt_med   상위 트레이더 **계정 수** 롱숏 비율
        long_short_ratio_med   전체 계정 롱숏 비율
        taker_ls_med           테이커 매수/매도 **거래량** 비율
        oi_med / oi_range_pct  미결제약정과 그 일중 변동

    상위 트레이더와 전체 계정이 **갈릴 때**가 특히 흥미롭다 — 소위 스마트머니
    대 개미다. 그 차이를 별도 신호로 만든다.

⚠ 오늘 배운 규율을 처음부터 전부 건다
    · `--split` 필수
    · **방향 대조** — z高/z低 양쪽 (교훈 #91)
    · **HAC 보정** (교훈 #92)
    · **위약 2종** — 뒤섞기 + **교차자산** (교훈 #93). 교차자산이 결정적이었다:
      온체인에서 뒤섞기 p 0.000 이던 신호가 교차자산에서 무너졌다
    · z 는 **당일 제외** 직전 90일 (lookahead 방지)
    · 마찰 차감 (교훈 #82)

⚠ 포지셔닝 지표는 그날 안에 확정된다
    5분 간격 관측의 일별 중앙값이라 그날 종가 시점에 이미 알 수 있다.
    그래도 **하루 밀어 t+1 시가**에 진입한다 — 집계 시점 애매함을 피한다.

사용:
  python3 -m scripts.research.positioning_signal_scan --split 2025-06-01
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("pos_scan")

OUT = ROOT / "runs" / "research_track" / "positioning_signal_scan.json"
Z_WINDOW = 90
MIN_OBS = 50
T_COLLAPSE = 1000.0

SIGNALS = {
    "top_ls_z": "상위 트레이더 포지션 롱숏 z",
    "acct_ls_z": "전체 계정 롱숏 z",
    "smart_dumb_z": "상위-전체 괴리 z — 스마트머니 대 개미",
    "taker_ls_z": "테이커 거래량 롱숏 z",
    "oi_z": "미결제약정 z",
    "oi_range_z": "OI 일중 변동 z",
}


def zscore(s: pd.Series, w: int) -> pd.Series:
    """직전 w일 기준. **당일 제외** — 포함하면 lookahead."""
    m = s.shift(1).rolling(w, min_periods=w // 2).mean()
    sd = s.shift(1).rolling(w, min_periods=w // 2).std()
    return (s - m) / sd.replace(0, np.nan)


def newey_west_t(a: np.ndarray, lags: int) -> float | None:
    n = len(a)
    if n < 3 or lags < 1:
        return None
    x = a - a.mean()
    var = float(np.dot(x, x) / n)
    for j in range(1, min(lags, n - 1) + 1):
        var += 2.0 * (1.0 - j / (lags + 1.0)) * float(np.dot(x[j:], x[:-j]) / n)
    return float(a.mean() / np.sqrt(var / n)) if var > 0 else None


def tfmt(t) -> str:
    if t is None:
        return "   —  "
    return f"{t:>7.2f}" if abs(t) < T_COLLAPSE else "    ∞* "


def stats(a: np.ndarray, lags: int) -> dict:
    if len(a) < 2:
        return {"n": int(len(a))}
    se = a.std(ddof=1) / np.sqrt(len(a))
    naive = float(a.mean() / se) if se else None
    t = newey_west_t(a, lags) if lags else naive
    return {"n": int(len(a)), "mean": float(a.mean()), "med": float(np.median(a)),
            "win": float(100 * (a > 0).mean()), "t": t, "t_naive": naive}


def bucket_t(z, fwd, hi, lags, side="hi"):
    m = (z >= hi) if side == "hi" else (z <= -hi)
    if m.sum() < MIN_OBS:
        return None
    return newey_west_t(fwd[m], lags)


def main() -> int:
    p = argparse.ArgumentParser(description="포지셔닝 신호 검정")
    p.add_argument("--split", required=True)
    p.add_argument("--hold", type=int, default=7)
    p.add_argument("--z-hi", type=float, default=1.5)
    p.add_argument("--fee-bp", type=float, default=5.0)
    p.add_argument("--placebo", type=int, default=200)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out", default=str(OUT))
    a = p.parse_args()

    from sqlalchemy import text

    from app.db.session import engine

    split = pd.Timestamp(datetime.fromisoformat(a.split))
    with engine.connect() as conn:
        m = pd.DataFrame(conn.execute(text(
            "SELECT symbol, date, oi_med, oi_range_pct, toptrader_ls_med, "
            "long_short_ratio_med, taker_ls_med FROM binance_archive_metrics "
            "ORDER BY symbol, date")).fetchall(),
            columns=["symbol", "date", "oi", "oi_range", "top_ls", "acct_ls",
                     "taker_ls"])
        px = pd.DataFrame(conn.execute(text(
            "SELECT symbol, date, open FROM ohlcv_daily "
            "WHERE is_partial = false ORDER BY symbol, date")).fetchall(),
            columns=["symbol", "date", "open"])
    m["date"] = pd.to_datetime(m["date"])
    px["date"] = pd.to_datetime(px["date"])
    log.info("포지셔닝 %d행 · 종목 %d", len(m), m["symbol"].nunique())

    lags = max(0, a.hold - 1)
    fric = 2 * a.fee_bp / 100.0
    recs = []
    for sym, g in m.groupby("symbol"):
        q = px[px["symbol"] == sym].set_index("date")["open"]
        d = g.set_index("date").sort_index().join(q.rename("open"), how="inner")
        if len(d) < 200:
            continue
        for c in ("oi", "oi_range", "top_ls", "acct_ls", "taker_ls"):
            d[c] = pd.to_numeric(d[c], errors="coerce")

        d["top_ls_z"] = zscore(d["top_ls"], Z_WINDOW)
        d["acct_ls_z"] = zscore(d["acct_ls"], Z_WINDOW)
        # 스마트머니 대 개미 — 비율의 **로그 차이**를 쓴다(비율은 비대칭이다)
        d["smart_dumb_z"] = zscore(
            np.log(d["top_ls"].clip(lower=1e-6)) -
            np.log(d["acct_ls"].clip(lower=1e-6)), Z_WINDOW)
        d["taker_ls_z"] = zscore(d["taker_ls"], Z_WINDOW)
        d["oi_z"] = zscore(d["oi"], Z_WINDOW)
        d["oi_range_z"] = zscore(d["oi_range"], Z_WINDOW)

        # ⚠ 하루 밀어 t+1 시가 진입 — 집계 시점 애매함을 피한다
        entry = d["open"].shift(-1)
        d["fwd"] = (d["open"].shift(-(1 + a.hold)) / entry - 1) * 100

        for sig in SIGNALS:
            sub = d[[sig, "fwd"]].dropna()
            for r in sub.itertuples():
                recs.append({"symbol": sym, "date": r.Index, "signal": sig,
                             "z": float(getattr(r, sig)), "fwd": float(r.fwd),
                             "split": "OOS" if r.Index >= split else "IS"})

    if not recs:
        raise SystemExit("표본이 없다")
    d = pd.DataFrame(recs)
    log.info("표본 %d · 종목 %d", len(d), d["symbol"].nunique())

    res = {}
    print("=" * 96)
    print(f"포지셔닝 신호 — 표본 {len(d):,} · 종목 {d['symbol'].nunique()} · "
          f"보유 {a.hold}일 · z 임계 ±{a.z_hi} · 분할 {a.split}")
    print(f"⚠ t 는 HAC 보정(lags={lags}) · 마찰 {fric:.2f}% 차감")
    print("=" * 96)
    print(f"  {'신호':<16}{'구간':<5}{'방향':<7}{'n':>7}{'순%':>9}{'승률%':>8}"
          f"{'t(HAC)':>9}{'t(보정전)':>10}")
    for sig in SIGNALS:
        for sp in ("IS", "OOS"):
            mm = (d["signal"] == sig) & (d["split"] == sp)
            for lab, arr in (
                    ("z高 롱", d.loc[mm & (d["z"] >= a.z_hi), "fwd"].values - fric),
                    ("z低 롱", d.loc[mm & (d["z"] <= -a.z_hi), "fwd"].values - fric)):
                s = stats(arr, lags)
                if "mean" not in s:
                    continue
                res[f"{sig}/{sp}/{lab}"] = s
                print(f"  {sig:<16}{sp:<5}{lab:<7}{s['n']:>7}{s['mean']:>9.3f}"
                      f"{s['win']:>8.1f}{tfmt(s['t']):>9}{tfmt(s['t_naive']):>10}")
        print()

    # ── 위약 2종 ───────────────────────────────────────────────────────
    if a.placebo:
        print("=" * 96)
        print(f"위약 — 뒤섞기 {a.placebo}회 + 교차자산 (교훈 #93)")
        print("=" * 96)
        print(f"  {'신호':<16}{'구간':<5}{'관측 t':>9}{'위약평균':>10}"
              f"{'경험 p':>9}{'교차자산 t':>11}  판정")
        rng = np.random.default_rng(a.seed)
        for sig in SIGNALS:
            for sp in ("IS", "OOS"):
                sub = d[(d["signal"] == sig) & (d["split"] == sp)]
                groups = [(g["z"].values, g["fwd"].values - fric)
                          for _, g in sub.groupby("symbol") if len(g) >= MIN_OBS]
                if len(groups) < 3:
                    continue
                Z = np.concatenate([g[0] for g in groups])
                F = np.concatenate([g[1] for g in groups])
                obs = bucket_t(Z, F, a.z_hi, lags)
                if obs is None:
                    continue
                ts = []
                for _ in range(a.placebo):
                    zp = np.concatenate([rng.permutation(g[0]) for g in groups])
                    t = bucket_t(zp, F, a.z_hi, lags)
                    if t is not None:
                        ts.append(t)
                pval = float(np.mean(np.array(ts) >= obs)) if ts else None
                # 교차자산 — 한 칸 밀어 짝짓는다
                zs, fs = [], []
                for i, (z, f) in enumerate(groups):
                    zo = groups[(i + 1) % len(groups)][0]
                    n = min(len(zo), len(f))
                    zs.append(zo[:n])
                    fs.append(f[:n])
                xa = bucket_t(np.concatenate(zs), np.concatenate(fs), a.z_hi, lags)
                verdict = "—"
                if pval is not None:
                    if pval > 0.05:
                        verdict = "**위약과 구별 안 됨**"
                    elif xa is not None and abs(xa) >= abs(obs) * 0.5:
                        verdict = "⚠ 교차자산도 비슷 — 자산 고유가 아님"
                    else:
                        verdict = "★ 위약 통과"
                res[f"{sig}/{sp}/placebo"] = {
                    "obs_t": obs, "p_value": pval, "cross_asset_t": xa,
                    "null_mean": float(np.mean(ts)) if ts else None}
                print(f"  {sig:<16}{sp:<5}{obs:>9.2f}"
                      f"{(np.mean(ts) if ts else 0):>10.2f}"
                      f"{(pval if pval is not None else -1):>9.3f}"
                      f"{(xa if xa is not None else 0):>11.2f}  {verdict}")
            print()

    Path(a.out).write_text(json.dumps(
        {"params": vars(a), "n": len(d), "hac_lags": lags, "results": res},
        ensure_ascii=False, indent=2, default=str))
    print("=" * 96)
    print(f"  → {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
