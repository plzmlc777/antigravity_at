"""온체인 신호 검정 — **시계열**로. 15종밖에 없으므로 횡단면은 못 한다.

왜 시계열인가
    온체인 커버리지가 **15종**이다(우리 유동성 유니버스는 190종). 3분위 롱숏은
    5종씩 나누는 셈이라 성립하지 않는다. 대신 종목별로 독립 검정하면 15종 ×
    여러 시점이라 관측이 충분하다.

무엇을 묻나
    "온체인 지표가 **자기 과거 대비** 극단이면 이후 수익이 다른가"

    지표별 z 점수(직전 90일 기준)를 내고 상·하위 구간의 forward 수익을 본다.
    가격이 아니라 **네트워크 활동**이 기준이라, 오늘 다섯 번 기각된 가격 기반
    접근과 기질이 다르다.

⚠ 오늘 배운 규율을 처음부터 건다
    · `--split` 필수 (표본 밖 선언 없는 최적화는 과최적화 기계다)
    · **방향 대조** — 롱과 숏을 함께 낸다 (교훈 #91: 한쪽만 재면 국면 효과를
      신호 효과로 읽는다)
    · **겹치면 HAC 보정** (교훈 #92: 비겹침 소표본 t 2.01 이 -0.62 가 됐다)
    · z 는 **직전 90일만** 쓴다 — 미래를 섞으면 그 순간 lookahead
    · 마찰을 함께 낸다 (교훈 #82)

⚠ 온체인 지표는 하루 늦게 확정된다
    체인 데이터는 그날이 끝나야 집계된다. `t` 일 지표로 `t` 일 종가에 진입하면
    lookahead 다. **하루 밀어서** `t+1` 시가에 진입한다.

사용:
  python3 -m scripts.research.onchain_signal_scan --split 2024-01-01
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
log = logging.getLogger("onchain_scan")

OUT = ROOT / "runs" / "research_track" / "onchain_signal_scan.json"

# 검정할 지표. 원값이 아니라 **가격 대비 비율**이나 z 로 본다.
SIGNALS = {
    "adr_z": "활성주소 z (90일)",
    "adr_per_cap_z": "활성주소/시총 z — factor zoo 의 new-address-to-price 계열",
    "tx_z": "거래수 z",
    "fee_z": "수수료 z",
    "supply_growth_z": "유통량 증가율 z — 발행 압력",
}
Z_WINDOW = 90
MIN_OBS = 30


def load(conn) -> pd.DataFrame:
    from sqlalchemy import text
    oc = pd.DataFrame(conn.execute(text(
        "SELECT asset, date, active_addresses, tx_count, market_cap, supply, "
        "fee_total FROM onchain_metric ORDER BY asset, date")).fetchall(),
        columns=["asset", "date", "adr", "tx", "cap", "supply", "fee"])
    px = pd.DataFrame(conn.execute(text(
        "SELECT symbol, date, open, close FROM ohlcv_daily "
        "WHERE is_partial = false ORDER BY symbol, date")).fetchall(),
        columns=["symbol", "date", "open", "close"])
    return oc, px


def zscore(s: pd.Series, w: int) -> pd.Series:
    """직전 w일 기준 z. **당일을 포함하지 않는다** — 포함하면 lookahead."""
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


def stats(a: np.ndarray, lags: int = 0) -> dict:
    if len(a) < 2:
        return {"n": int(len(a))}
    se = a.std(ddof=1) / np.sqrt(len(a))
    t = float(a.mean() / se) if se else None
    out = {"n": int(len(a)), "mean": float(a.mean()), "med": float(np.median(a)),
           "win": float(100 * (a > 0).mean()), "t": t}
    if lags:
        out["t_naive"], out["t"] = t, newey_west_t(a, lags)
    return out


def bucket_t(z: np.ndarray, fwd: np.ndarray, hi: float, lags: int) -> float | None:
    """z 상위 구간 롱의 HAC t. 위약 분포를 만들 때 반복 호출된다."""
    m = z >= hi
    if m.sum() < MIN_OBS:
        return None
    return newey_west_t(fwd[m], lags)


def placebo_null(groups: list[tuple[np.ndarray, np.ndarray]], hi: float,
                 lags: int, n_rep: int, seed: int) -> dict:
    """위약 1 — **신호 뒤섞기**.

    자산 안에서 z 를 무작위로 섞는다. 분포와 수익은 그대로 두고 **시점 대응만**
    끊는다. 관측 t 가 이 분포의 꼬리에 있지 않으면 신호가 아니라 우연이다.

    ⚠ 시드를 고정한다 — 교훈 #87(무작위는 재현이 깨진다).
    """
    rng = np.random.default_rng(seed)
    ts = []
    for _ in range(n_rep):
        zs, fs = [], []
        for z, f in groups:
            zs.append(rng.permutation(z))
            fs.append(f)
        t = bucket_t(np.concatenate(zs), np.concatenate(fs), hi, lags)
        if t is not None:
            ts.append(t)
    if not ts:
        return {}
    arr = np.array(ts)
    return {"n_rep": len(arr), "null_mean": float(arr.mean()),
            "null_p05": float(np.percentile(arr, 5)),
            "null_p95": float(np.percentile(arr, 95)),
            "null_std": float(arr.std(ddof=1))}


def cross_asset_null(groups: list[tuple[np.ndarray, np.ndarray]], hi: float,
                     lags: int) -> float | None:
    """위약 2 — **다른 자산 신호 빌려쓰기**.

    자산 A 의 z 로 자산 B 를 거래한다. 신호가 그 자산 고유의 것이면 무너지고,
    시장 전체 국면을 재고 있었다면 살아남는다. 교훈 #85 가 요구하는
    '사건 안 겪는 대조군'에 대응한다.
    """
    if len(groups) < 2:
        return None
    zs, fs = [], []
    for i, (z, f) in enumerate(groups):
        z_other = groups[(i + 1) % len(groups)][0]
        n = min(len(z_other), len(f))
        zs.append(z_other[:n])
        fs.append(f[:n])
    return bucket_t(np.concatenate(zs), np.concatenate(fs), hi, lags)


def main() -> int:
    p = argparse.ArgumentParser(description="온체인 시계열 신호 검정")
    p.add_argument("--split", required=True, help="표본 안/밖 분할 날짜 (필수)")
    p.add_argument("--hold", type=int, default=7, help="보유일")
    p.add_argument("--z-hi", type=float, default=1.5, help="상위 구간 z 임계")
    p.add_argument("--fee-bp", type=float, default=5.0)
    p.add_argument("--placebo", type=int, default=0,
                   help="위약 반복 횟수(예 200). 0 이면 위약 없이 관측만")
    p.add_argument("--seed", type=int, default=42,
                   help="위약 난수 시드 — 고정해야 재현된다(교훈 #87)")
    p.add_argument("--out", default=str(OUT))
    a = p.parse_args()

    from app.db.session import engine
    from scripts.collect_onchain import ASSET_TO_SYMBOL

    split = pd.Timestamp(datetime.fromisoformat(a.split))
    with engine.connect() as conn:
        oc, px = load(conn)
    oc["date"] = pd.to_datetime(oc["date"])
    px["date"] = pd.to_datetime(px["date"])
    log.info("온체인 %d행 · 가격 %d행", len(oc), len(px))

    recs = []
    for asset, sym in ASSET_TO_SYMBOL.items():
        o = oc[oc["asset"] == asset].set_index("date").sort_index()
        q = px[px["symbol"] == sym].set_index("date").sort_index()
        if len(o) < 200 or len(q) < 200:
            continue
        df = o.join(q[["open", "close"]], how="inner")
        if len(df) < 200:
            continue
        for c in ("adr", "tx", "cap", "supply", "fee"):
            df[c] = pd.to_numeric(df[c], errors="coerce")

        df["adr_z"] = zscore(df["adr"], Z_WINDOW)
        df["adr_per_cap_z"] = zscore(df["adr"] / df["cap"], Z_WINDOW)
        df["tx_z"] = zscore(df["tx"], Z_WINDOW)
        df["fee_z"] = zscore(df["fee"], Z_WINDOW)
        df["supply_growth_z"] = zscore(df["supply"].pct_change(), Z_WINDOW)

        # ⚠ 온체인은 그날이 끝나야 확정된다. t 일 지표로 t+1 시가에 진입한다.
        entry = df["open"].shift(-1)
        exit_ = df["open"].shift(-(1 + a.hold))
        df["fwd"] = (exit_ / entry - 1) * 100

        for sig in SIGNALS:
            sub = df[[sig, "fwd"]].dropna()
            if len(sub) < MIN_OBS:
                continue
            for r in sub.itertuples():
                recs.append({"asset": asset, "date": r.Index, "signal": sig,
                             "z": float(getattr(r, sig)), "fwd": float(r.fwd),
                             "split": "OOS" if r.Index >= split else "IS"})
        log.info("%s (%s) — %d행", asset, sym, len(df))

    if not recs:
        raise SystemExit("표본이 없다 — 온체인과 가격의 교집합을 확인하라")
    d = pd.DataFrame(recs)
    fric = 2 * a.fee_bp / 100.0          # 왕복 %
    lags = max(0, a.hold - 1)            # 매일 관측 · hold 일 보유 → 겹친다

    res = {}
    print("=" * 92)
    print(f"온체인 시계열 신호 — 표본 {len(d):,} · 자산 {d['asset'].nunique()} · "
          f"보유 {a.hold}일 · z 임계 ±{a.z_hi} · 분할 {a.split}")
    print(f"⚠ 겹치는 관측 — t 는 **HAC 보정**(lags={lags}) · 마찰 {fric:.2f}% 차감")
    print("=" * 92)
    print(f"  {'신호':<16}{'구간':<5}{'방향':<6}{'n':>7}{'순%':>9}{'승률%':>8}"
          f"{'t(HAC)':>9}{'t(보정전)':>10}")
    for sig in SIGNALS:
        for sp in ("IS", "OOS"):
            m = (d["signal"] == sig) & (d["split"] == sp)
            hi = d.loc[m & (d["z"] >= a.z_hi), "fwd"].values - fric
            lo = d.loc[m & (d["z"] <= -a.z_hi), "fwd"].values - fric
            for lab, arr in (("z高 롱", hi), ("z低 롱", lo)):
                s = stats(arr, lags)
                if "mean" not in s:
                    continue
                res[f"{sig}/{sp}/{lab}"] = s
                print(f"  {sig:<16}{sp:<5}{lab:<6}{s['n']:>7}{s['mean']:>9.3f}"
                      f"{s['win']:>8.1f}{(s['t'] or 0):>9.2f}"
                      f"{(s.get('t_naive') or 0):>10.2f}")
        print()

    # ── 위약 ───────────────────────────────────────────────────────────
    if a.placebo:
        print("=" * 92)
        print(f"위약 검정 — 반복 {a.placebo}회 · 시드 {a.seed} (교훈 #85 두 종)")
        print("=" * 92)
        print(f"  {'신호':<16}{'구간':<5}{'관측 t':>9}{'위약평균':>10}"
              f"{'위약 p95':>10}{'경험 p':>9}{'교차자산 t':>11}  판정")
        for sig in SIGNALS:
            for sp in ("IS", "OOS"):
                m = (d["signal"] == sig) & (d["split"] == sp)
                sub = d.loc[m]
                if len(sub) < MIN_OBS * 2:
                    continue
                groups = [(g["z"].values, g["fwd"].values - fric)
                          for _, g in sub.groupby("asset") if len(g) >= MIN_OBS]
                if len(groups) < 2:
                    continue
                obs = bucket_t(np.concatenate([g[0] for g in groups]),
                               np.concatenate([g[1] for g in groups]),
                               a.z_hi, lags)
                if obs is None:
                    continue
                nul = placebo_null(groups, a.z_hi, lags, a.placebo, a.seed)
                xa = cross_asset_null(groups, a.z_hi, lags)
                pval = None
                if nul:
                    rng = np.random.default_rng(a.seed)
                    # 경험적 p — 위약이 관측 이상을 낸 비율
                    ts = []
                    for _ in range(a.placebo):
                        zs = [rng.permutation(g[0]) for g in groups]
                        t = bucket_t(np.concatenate(zs),
                                     np.concatenate([g[1] for g in groups]),
                                     a.z_hi, lags)
                        if t is not None:
                            ts.append(t)
                    pval = float(np.mean(np.array(ts) >= obs)) if ts else None
                verdict = "—"
                if pval is not None:
                    if pval > 0.05:
                        verdict = "**위약과 구별 안 됨**"
                    elif xa is not None and abs(xa) >= abs(obs) * 0.5:
                        verdict = "⚠ 교차자산도 비슷 — 자산 고유가 아님"
                    else:
                        verdict = "위약 통과"
                res[f"{sig}/{sp}/placebo"] = {"obs_t": obs, "p_value": pval,
                                              "cross_asset_t": xa, **nul}
                print(f"  {sig:<16}{sp:<5}{obs:>9.2f}"
                      f"{nul.get('null_mean', 0):>10.2f}"
                      f"{nul.get('null_p95', 0):>10.2f}"
                      f"{(pval if pval is not None else -1):>9.3f}"
                      f"{(xa if xa is not None else 0):>11.2f}  {verdict}")
            print()

    Path(a.out).write_text(json.dumps(
        {"params": vars(a), "n": len(d), "hac_lags": lags, "results": res},
        ensure_ascii=False, indent=2, default=str))

    print("-" * 92)
    print("  **읽는 법** — `z高 롱`이 벌고 `z低 롱`이 지면 그 지표는 방향 신호다.")
    print("     둘 다 벌거나 둘 다 지면 신호가 아니라 **국면**이다(교훈 #91).")
    print("     t(보정전)과 t(HAC)의 차이가 크면 겹침 때문에 부풀려진 것이다.")
    print("=" * 92)
    print(f"  → {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
