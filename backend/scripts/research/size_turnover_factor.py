"""SMB(사이즈)·회전율 요인 — 온체인 시총으로 처음 만들어 본다.

왜 이제야 가능한가
    2026-08-15 오전에 SMB 와 회전율을 만들려다 **유통량·시총이 없어** 못 했다.
    같은 날 온체인 수집기(CoinMetrics Community, 무료)로 `market_cap` 과
    `supply` 를 확보하면서 열렸다.

    `Crypto factor zoo`(2026)가 꼽은 핵심 3 중 **turnover volatility** 가
    이것이다(나머지는 bid-ask spread — 수집 시작했으나 6개월 필요, 그리고
    new-address-to-price — 교차자산 위약에서 기각).

⚠ **자산이 13종이다. 이게 결과를 지배할 수 있다.**
    큰 쪽은 BTC·ETH·XRP, 작은 쪽은 ALGO·ICP·AAVE 다. 그러면 SMB 는 사이즈
    요인이 아니라 **"알트 롱 / BTC 숏"** 일 뿐이다. 그래서 이 스크립트는
    반드시 그 대조군을 함께 낸다 — 둘이 같으면 사이즈 요인이 아니다.

    3분위는 4~5종씩이라 성립하지 않는다. **중위 분할**(6/7)을 쓴다.

⚠ 오늘 배운 규율을 처음부터 건다
    `--split` 필수 · 방향별 분해(교훈 #91) · 겹치면 HAC(교훈 #92) ·
    뒤섞기 위약 · 마찰 차감(교훈 #82)

사용:
  python3 -m scripts.research.size_turnover_factor --split 2024-01-01
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
log = logging.getLogger("size_factor")

OUT = ROOT / "runs" / "research_track" / "size_turnover_factor.json"
MIN_NAMES = 8       # 중위 분할이라도 이보다 적으면 의미 없다
BIG_PROXY = "BTCUSDT"


def newey_west_t(a: np.ndarray, lags: int) -> float | None:
    n = len(a)
    if n < 3 or lags < 1:
        return None
    x = a - a.mean()
    var = float(np.dot(x, x) / n)
    for j in range(1, min(lags, n - 1) + 1):
        var += 2.0 * (1.0 - j / (lags + 1.0)) * float(np.dot(x[j:], x[:-j]) / n)
    return float(a.mean() / np.sqrt(var / n)) if var > 0 else None


def stats(a: np.ndarray, lags: int = 0) -> dict:
    if len(a) < 2:
        return {"n": int(len(a))}
    se = a.std(ddof=1) / np.sqrt(len(a))
    t = float(a.mean() / se) if se else None
    out = {"n": int(len(a)), "mean": float(a.mean()), "med": float(np.median(a)),
           "win": float(100 * (a > 0).mean()), "t": t,
           "total": float(a.sum())}
    if lags:
        out["t_naive"], out["t"] = t, newey_west_t(a, lags)
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="SMB·회전율 요인")
    p.add_argument("--split", required=True)
    p.add_argument("--hold", type=int, default=7)
    p.add_argument("--stride", type=int, default=7)
    p.add_argument("--fee-bp", type=float, default=5.0)
    p.add_argument("--placebo", type=int, default=200)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out", default=str(OUT))
    a = p.parse_args()

    from sqlalchemy import text

    from app.db.session import engine
    from scripts.collect_onchain import ASSET_TO_SYMBOL

    split = pd.Timestamp(datetime.fromisoformat(a.split))
    with engine.connect() as conn:
        oc = pd.DataFrame(conn.execute(text(
            "SELECT asset, date, market_cap FROM onchain_metric "
            "WHERE market_cap IS NOT NULL ORDER BY date")).fetchall(),
            columns=["asset", "date", "cap"])
        px = pd.DataFrame(conn.execute(text(
            "SELECT symbol, date, open, close, volume FROM ohlcv_daily "
            "WHERE is_partial = false ORDER BY date")).fetchall(),
            columns=["symbol", "date", "open", "close", "volume"])
    oc["date"] = pd.to_datetime(oc["date"])
    px["date"] = pd.to_datetime(px["date"])
    oc["symbol"] = oc["asset"].map(ASSET_TO_SYMBOL)
    oc = oc.dropna(subset=["symbol"])

    df = px.merge(oc[["symbol", "date", "cap"]], on=["symbol", "date"],
                  how="inner")
    df["cap"] = pd.to_numeric(df["cap"], errors="coerce")
    df["dv"] = df["close"] * df["volume"]
    df["turnover"] = df["dv"] / df["cap"]
    df = df.dropna(subset=["cap", "open"])
    log.info("교집합 %d행 · 종목 %d · %s ~ %s", len(df), df["symbol"].nunique(),
             df["date"].min().date(), df["date"].max().date())

    cap_m = df.pivot(index="date", columns="symbol", values="cap")
    to_m = df.pivot(index="date", columns="symbol", values="turnover")
    op_m = df.pivot(index="date", columns="symbol", values="open")
    dates = op_m.index

    lags = max(0, a.hold // a.stride - 1)
    fric = 2 * a.fee_bp / 100.0
    recs = []
    i = 30
    while i + a.hold < len(dates):
        t0 = dates[i]
        # ⚠ 정렬은 t0 **까지**. 진입은 t0 시가, 청산은 t0+hold 시가.
        cap = cap_m.iloc[i].dropna()
        to = to_m.iloc[i].dropna()
        fwd = (op_m.iloc[i + a.hold] / op_m.iloc[i] - 1) * 100
        names = cap.index.intersection(fwd.dropna().index)
        if len(names) < MIN_NAMES:
            i += a.stride
            continue
        cap, fwd_ok = cap[names], fwd[names]
        med = cap.median()
        small = [s for s in names if cap[s] <= med]
        big = [s for s in names if cap[s] > med]
        if not small or not big:
            i += a.stride
            continue

        smb = float(fwd_ok[small].mean() - fwd_ok[big].mean())
        # ⚠ 대조군 — SMB 가 그냥 "알트 롱 / BTC 숏"인가
        alt = [s for s in names if s != BIG_PROXY]
        alt_btc = (float(fwd_ok[alt].mean() - fwd_ok[BIG_PROXY])
                   if BIG_PROXY in names and alt else np.nan)

        rec = {"date": str(t0.date()), "n": len(names),
               "smb": smb - fric, "smb_gross": smb,
               "small": float(fwd_ok[small].mean()),
               "big": float(fwd_ok[big].mean()),
               "alt_minus_btc": alt_btc - fric if alt_btc == alt_btc else None,
               "split": "OOS" if t0 >= split else "IS"}

        # 회전율 요인 — 고회전 롱 / 저회전 숏 (반대 부호도 함께 본다)
        tn = to.index.intersection(names)
        if len(tn) >= MIN_NAMES:
            t_med = to[tn].median()
            hi = [s for s in tn if to[s] > t_med]
            lo = [s for s in tn if to[s] <= t_med]
            if hi and lo:
                rec["turn_hi_minus_lo"] = float(
                    fwd_ok[hi].mean() - fwd_ok[lo].mean()) - fric
        recs.append(rec)
        i += a.stride

    if not recs:
        raise SystemExit("표본이 없다")
    d = pd.DataFrame(recs)

    res = {}
    print("=" * 88)
    print(f"SMB·회전율 요인 — 기간 {len(d)}회 · 종목 {int(d['n'].mean())} "
          f"(중위 분할) · 보유 {a.hold}일 · 분할 {a.split}")
    if lags:
        print(f"⚠ 중첩 — t 는 HAC 보정(lags={lags})")
    print("=" * 88)
    print(f"  {'항목':<18}{'구간':<5}{'n':>6}{'평균%':>9}{'총%':>10}"
          f"{'승률%':>8}{'t':>8}")
    for col, lab in (("smb", "SMB(소-대)"),
                     ("alt_minus_btc", "대조 알트-BTC"),
                     ("turn_hi_minus_lo", "회전율(고-저)"),
                     ("small", "소형 롱"), ("big", "대형 롱")):
        if col not in d.columns:
            continue
        for sp in ("IS", "OOS"):
            v = d.loc[(d["split"] == sp), col].dropna().values
            s = stats(v, lags)
            if "mean" not in s:
                continue
            res[f"{col}/{sp}"] = s
            print(f"  {lab:<18}{sp:<5}{s['n']:>6}{s['mean']:>9.3f}"
                  f"{s['total']:>10.1f}{s['win']:>8.1f}{(s['t'] or 0):>8.2f}")
        print()

    # ── SMB 가 알트-BTC 와 구별되는가 ──────────────────────────────────
    both = d[["smb", "alt_minus_btc"]].dropna()
    corr = float(both["smb"].corr(both["alt_minus_btc"])) if len(both) > 5 else None
    print("-" * 88)
    print(f"  **SMB 와 '알트-BTC' 상관: {corr if corr is not None else float('nan'):+.3f}**")
    if corr is not None and corr > 0.9:
        print("     → 사실상 같은 것이다. **사이즈 요인이 아니라 알트/BTC 베타**다.")
    elif corr is not None and corr > 0.7:
        print("     → 상당 부분 겹친다. 사이즈 고유분이 얼마인지 따로 봐야 한다.")

    # ── 뒤섞기 위약 ────────────────────────────────────────────────────
    if a.placebo:
        rng = np.random.default_rng(a.seed)
        obs = res.get("smb/IS", {}).get("t")
        if obs is not None:
            ts = []
            caps = cap_m.copy()
            for _ in range(a.placebo):
                # 시점마다 시총 순위를 무작위로 섞는다 — 크기 정보만 끊는다
                vals = []
                j = 30
                while j + a.hold < len(dates):
                    c = caps.iloc[j].dropna()
                    f = (op_m.iloc[j + a.hold] / op_m.iloc[j] - 1) * 100
                    nm = c.index.intersection(f.dropna().index)
                    if len(nm) >= MIN_NAMES and dates[j] < split:
                        perm = rng.permutation(len(nm))
                        half = len(nm) // 2
                        sm = [nm[k] for k in perm[:half]]
                        bg = [nm[k] for k in perm[half:]]
                        vals.append(float(f[sm].mean() - f[bg].mean()) - fric)
                    j += a.stride
                if len(vals) > 3:
                    t = newey_west_t(np.array(vals), lags) if lags else \
                        float(np.mean(vals) / (np.std(vals, ddof=1) /
                                               np.sqrt(len(vals))))
                    if t is not None:
                        ts.append(t)
            if ts:
                arr = np.array(ts)
                pval = float(np.mean(arr >= obs))
                res["smb/placebo"] = {"obs_t": obs, "null_mean": float(arr.mean()),
                                      "null_p95": float(np.percentile(arr, 95)),
                                      "p_value": pval, "n_rep": len(arr)}
                print(f"  **뒤섞기 위약** (IS, {len(arr)}회) — 관측 t {obs:+.2f} · "
                      f"위약 평균 {arr.mean():+.2f} · p95 {np.percentile(arr,95):+.2f} · "
                      f"경험 p **{pval:.3f}**")
                if pval > 0.05:
                    print("     → **위약과 구별되지 않는다**")

    Path(a.out).write_text(json.dumps(
        {"params": vars(a), "n_periods": len(d), "hac_lags": lags,
         "smb_vs_altbtc_corr": corr, "results": res},
        ensure_ascii=False, indent=2, default=str))
    print("=" * 88)
    print(f"  → {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
