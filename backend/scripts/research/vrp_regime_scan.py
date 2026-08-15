"""변동성 위험 프리미엄(VRP) 국면 검정 — 옵션이 보는 미래로 알트를 조건화한다.

왜 새 차원인가
    지금까지 쓴 기질은 전부 **과거를 요약한 값**이었다 — OHLCV, 펀딩, OI,
    호가 깊이, 온체인, 포지셔닝. 옵션은 **미래 변동성의 가격**이고
    **참여자 집단이 다르다**. 열두 축을 닫는 동안 한 번도 안 건드렸다.

        VRP = 내재변동성(DVOL) - 실현변동성

    금융 전체에서 가장 견고한 이상현상 중 하나이고, 결정적으로 **예측이 아니라
    위험을 떠안는 대가**다. 우리가 아홉 번 실패한 "특성으로 수익률 맞히기"와
    종류가 다르다. 같은 계열이 우리 유일한 R-5 시드(펀딩 캐리)다.

⚠ 직접 수확은 못 한다 — 옵션을 팔아야 하고 $720 으로 무한 꼬리를 질 수 없다.
    그래서 **국면 조건 신호**로만 쓴다. BTC·ETH 옵션이 보는 미래로
    알트 유니버스 거래를 조건화한다. (옵션은 BTC·ETH 만 있다 — 횡단면 불가)

⚠⚠ **이 검정의 급소는 "그냥 사서 들고 있기"다**
    2021~2026 에는 대세 상승이 섞여 있다. 무조건 매수 대조군을 안 깔면
    국면 신호가 아니라 **그냥 롱**을 발견하고 만다. SMB 를 '알트-BTC' 와
    대조한 것과 같은 자리. 모든 칸을 **무조건 매수 대비 초과분**으로 낸다.

⚠ 위약은 뒤섞기가 아니라 **원형 회전**이다
    시장 국면 신호는 **하나의 시계열**이다. 그냥 섞으면 자기상관이 파괴돼
    귀무가 실제보다 만만해진다. 무작위 회전(circular shift)은 신호의
    자기상관을 **그대로 두고** 수익률과의 정렬만 끊는다.

거는 장치
    `--split` 필수 · 무조건 매수 대조 · 방향 대조(#91) · 비겹침+HAC(#92) ·
    **최대통계량 귀무분포**(#95) · 마찰 선차감(#82) · 위험축 과거변동성 대조(#94)

사용:
  python3 -m scripts.research.vrp_regime_scan --split 2025-01-01
"""
from __future__ import annotations

import argparse
import itertools
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
log = logging.getLogger("vrp")

OUT = ROOT / "runs" / "research_track" / "vrp_regime_scan.json"
# --target 별로 결과 파일을 나눈다 (덮어쓰기 방지)

ZWIN = 250          # 국면 z 는 1년 창 (변동성 국면은 길다)
RVWIN = 30
HOLDS = [5, 10, 20]
CUTS = [("top", 0.10), ("top", 0.20), ("top", 0.30),
        ("bot", 0.10), ("bot", 0.20), ("bot", 0.30)]
MIN_PERIODS = 20    # 비겹침 기간이 이보다 적으면 판정 안 한다


def nw_t(a: np.ndarray, lags: int, center: float = 0.0) -> float:
    a = a[np.isfinite(a)] - center
    n = len(a)
    if n < 5:
        return 0.0
    x = a - a.mean()
    var = float(x @ x / n)
    for j in range(1, min(lags, n - 1) + 1):
        var += 2.0 * (1.0 - j / (lags + 1.0)) * float(x[j:] @ x[:-j] / n)
    return float(a.mean() / np.sqrt(var / n)) if var > 0 else 0.0


def main() -> int:
    p = argparse.ArgumentParser(description="VRP 국면 검정")
    p.add_argument("--split", required=True)
    p.add_argument("--fee-bp", type=float, default=5.0)
    p.add_argument("--target", choices=["basket", "btc"],
                   default="basket", help="거래 대상")
    p.add_argument("--reps", type=int, default=200)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out", default="")
    a = p.parse_args()

    if not a.out:
        a.out = str(OUT).replace(".json", f"_{a.target}.json")
    split = pd.Timestamp(datetime.fromisoformat(a.split))
    fric = 2 * a.fee_bp / 100.0

    from sqlalchemy import text

    from app.db.session import engine
    with engine.connect() as conn:
        dv = pd.DataFrame(conn.execute(text(
            "SELECT currency, date, dvol_close FROM deribit_dvol "
            "ORDER BY date")).fetchall(),
            columns=["cur", "date", "dvol"])
        px = pd.DataFrame(conn.execute(text(
            "SELECT symbol, date, open, close FROM ohlcv_daily "
            "WHERE is_partial = false ORDER BY date")).fetchall(),
            columns=["symbol", "date", "open", "close"])
    for f in (dv, px):
        f["date"] = pd.to_datetime(f["date"])
    dv["dvol"] = pd.to_numeric(dv["dvol"], errors="coerce")
    for c in ("open", "close"):
        px[c] = pd.to_numeric(px[c], errors="coerce")

    piv_o = px.pivot(index="date", columns="symbol", values="open")
    piv_c = px.pivot(index="date", columns="symbol", values="close")
    lr = np.log(piv_c / piv_c.shift(1))

    # ⚠ VRP 는 **같은 자산끼리** 빼야 한다.
    #   DVOL 은 BTC 내재변동성이므로 BTC 실현변동성과 짝지어야 한다.
    #   바스켓 실현변동성을 빼면 VRP 가 아니라 'BTC내재 - 알트실현' 이라는
    #   정체불명의 값이 된다 (첫 실행에서 실제로 그렇게 쟀다).
    if "BTCUSDT" not in lr.columns:
        raise SystemExit("BTCUSDT 가 ohlcv_daily 에 없다 — VRP 를 만들 수 없다")
    # ⚠ 피벗은 **모든 종목의 날짜 합집합**이라 BTCUSDT 가 없는 날이 NaN 으로
    #   들어간다. 그대로 rolling(30) 을 걸면 창마다 NaN 이 섞여 전멸한다
    #   (첫 수정본에서 실제로 0행이 나왔다). 결측을 뺀 뒤 굴리고 되붙인다.
    btc_lr = lr["BTCUSDT"].dropna()
    rv_btc = (btc_lr.rolling(RVWIN).std() * np.sqrt(365) * 100
              ).reindex(lr.index).ffill(limit=3)
    rv_bskt = lr.mean(axis=1).rolling(RVWIN).std() * np.sqrt(365) * 100

    d = dv.pivot(index="date", columns="cur", values="dvol")
    df = pd.DataFrame(index=d.index.union(rv_btc.index).sort_values())
    df["dvol_btc"] = d.get("BTC")
    df["dvol_eth"] = d.get("ETH")
    df["rv"] = rv_btc                 # ← VRP 의 짝
    df["rv_bskt"] = rv_bskt
    df = df.dropna(subset=["dvol_btc", "rv"])

    # ── 신호 ──────────────────────────────────────────────────────────
    df["vrp"] = df["dvol_btc"] - df["rv"]
    def z(c):
        return ((df[c] - df[c].rolling(ZWIN, min_periods=ZWIN).mean())
                / df[c].rolling(ZWIN, min_periods=ZWIN).std())
    df["vrp_z"] = z("vrp")
    df["dvol_z"] = z("dvol_btc")
    df["dvol_chg5"] = df["dvol_btc"] - df["dvol_btc"].shift(5)
    df["btc_eth_sp"] = df["dvol_btc"] - df["dvol_eth"]
    df["rv_z"] = z("rv")          # ⚠ 대조 신호 — 옵션 없이 아는 것
    # ⚠ 정직한 VRP: 같은 자산의 내재 - 실현
    SIGS = ["vrp", "vrp_z", "dvol_z", "dvol_chg5", "btc_eth_sp", "rv_z"]

    # ── 미래 수익 ─────────────────────────────────────────────────────
    # ⚠ 신호 t일 → 진입 t+1 시가 → 청산 t+1+H 시가 (교훈 #90)
    #   거래 대상 둘: 알트 바스켓(354종목 동일가중) / BTC 자체.
    #   DVOL 은 BTC 것이므로 BTC 를 거래하는 쪽이 더 직접적이다.
    for h in HOLDS:
        fwd = (piv_o.shift(-(1 + h)) / piv_o.shift(-1) - 1) * 100
        src = fwd["BTCUSDT"] if a.target == "btc" else fwd.mean(axis=1)
        df[f"f{h}"] = src.reindex(df.index)

    df = df.dropna(subset=["vrp_z"], how="all")
    df["oos"] = df.index >= split
    n_is = int((~df["oos"]).sum())
    print("=" * 96)
    print(f"VRP 국면 검정 — {df.index.min().date()} ~ {df.index.max().date()} "
          f"· 일 {len(df):,} (IS {n_is:,} / OOS {len(df)-n_is:,})")
    print(f"거래대상 {a.target}(바스켓 {piv_o.shape[1]}종목) · 분할 {a.split} · 마찰 "
          f"{2*a.fee_bp:.0f}bp · 국면 z 창 {ZWIN}일")
    print("⚠ 모든 수치는 **무조건 매수 대비 초과분**이다")
    print("=" * 96)

    idx = df.index
    is_mask = (~df["oos"]).to_numpy()
    sig_arr = {s: df[s].to_numpy(dtype=float) for s in SIGS}
    ret_arr = {h: df[f"f{h}"].to_numpy(dtype=float) for h in HOLDS}

    # 무조건 매수 기준선 (같은 비겹침 격자로)
    print("\n【0】 무조건 매수 — 이걸 못 이기면 아무것도 아니다")
    uncond = {}
    for h in HOLDS:
        for lab, m in (("IS", is_mask), ("OOS", ~is_mask)):
            v = ret_arr[h][m & np.isfinite(ret_arr[h])][::h]
            if len(v) >= MIN_PERIODS:
                uncond[(h, lab)] = float(v.mean())
                print(f"  보유 {h:>2}일  {lab:<4} 기간 {len(v):>4} · "
                      f"평균 {v.mean():>7.3f}% · 총 {v.sum():>8.1f}% · "
                      f"t {nw_t(v, 0):>5.2f}")

    cells = [(s, cut, pct, h, tr) for s, (cut, pct), h, tr
             in itertools.product(SIGS, CUTS, HOLDS, (+1, -1))]
    log.info("격자 %d칸", len(cells))

    def regime_mask(v: np.ndarray, cut: str, pct: float,
                    ref: np.ndarray) -> np.ndarray:
        r = ref[np.isfinite(ref)]
        if len(r) < 200:
            return np.zeros(len(v), dtype=bool)
        thr = np.quantile(r, 1 - pct if cut == "top" else pct)
        return np.isfinite(v) & ((v >= thr) if cut == "top" else (v <= thr))

    def eval_grid(sigs_now: dict, mask: np.ndarray, lab: str,
                  collect: bool) -> tuple[float, list]:
        best, rows = 0.0, []
        for s, cut, pct, h, tr in cells:
            v = sigs_now[s]
            m = regime_mask(v, cut, pct, v[is_mask]) & mask & np.isfinite(ret_arr[h])
            if m.sum() < MIN_PERIODS * h:
                continue
            # 비겹침 — 국면 안에서 h일 간격으로만 진입
            pos = np.flatnonzero(m)
            pick, last = [], -10**9
            for i in pos:
                if i - last >= h:
                    pick.append(i)
                    last = i
            if len(pick) < MIN_PERIODS:
                continue
            r = ret_arr[h][pick] * tr - fric
            base = uncond.get((h, lab))
            if base is None:
                continue
            excess = r - base * tr          # 무조건 매수 대비 초과분
            t = nw_t(excess, 0)
            if abs(t) > best:
                best = abs(t)
            if collect:
                rows.append({"sig": s, "cut": cut, "pct": pct, "hold": h,
                             "trade": tr, "n": len(pick),
                             "raw": float(r.mean()),
                             "excess": float(excess.mean()),
                             "win": float(100 * (r > 0).mean()),
                             "t": t})
        return best, rows

    obs_best, rows = eval_grid(sig_arr, is_mask, "IS", collect=True)
    if not rows:
        raise SystemExit("관문을 통과한 칸이 없다")
    R = pd.DataFrame(rows)
    R["absT"] = R["t"].abs()
    R = R.sort_values("absT", ascending=False)

    print(f"\n【1】 표본 안 상위 12칸 (총 {len(R)}칸) — 초과분 기준")
    print(f"  {'신호':<12}{'국면':>8}{'보유':>5}{'방향':>5}{'기간':>6}"
          f"{'원수익%':>9}{'초과%':>9}{'승률%':>8}{'t':>7}")
    print("  " + "-" * 88)
    for _, r in R.head(12).iterrows():
        print(f"  {r['sig']:<12}{r['cut']+str(int(r['pct']*100)):>8}"
              f"{r['hold']:>5}{'롱' if r['trade']>0 else '숏':>5}{r['n']:>6}"
              f"{r['raw']:>9.3f}{r['excess']:>9.3f}{r['win']:>8.1f}{r['t']:>7.2f}")

    # ── 최대통계량 귀무분포 (원형 회전) ───────────────────────────────
    print(f"\n【2】 최대통계량 귀무분포 — 신호를 **원형 회전**시키고 같은 "
          f"{len(cells)}칸을 다시 전부 뒤진다 ({a.reps}회)")
    print("     (뒤섞기가 아니다 — 국면 신호의 자기상관을 보존해야 귀무가 정직하다)")
    rng = np.random.default_rng(a.seed)
    n = len(idx)
    nulls = []
    for i in range(a.reps):
        rot = {s: np.roll(v, int(rng.integers(ZWIN, n - ZWIN)))
               for s, v in sig_arr.items()}
        b, _ = eval_grid(rot, is_mask, "IS", collect=False)
        nulls.append(b)
        if (i + 1) % 50 == 0:
            log.info("  위약 %d/%d · 귀무 최대 t 평균 %.2f", i + 1, a.reps,
                     float(np.mean(nulls)))
    nulls = np.array(nulls)
    pval = float(np.mean(nulls >= obs_best))
    print(f"  관측 최고 |t| **{obs_best:.2f}**  ·  귀무 최고 |t| 평균 "
          f"{nulls.mean():.2f} · p95 {np.percentile(nulls,95):.2f} · "
          f"최대 {nulls.max():.2f}")
    print(f"  **경험 p = {pval:.3f}**  "
          + ("→ 우연이 만드는 최고의 칸과 **구별되지 않는다**"
             if pval > 0.05 else "→ 우연을 넘는다"))

    # ── 표본 밖 ───────────────────────────────────────────────────────
    print("\n【3】 표본 밖 — 상위 8칸이 초과분 부호를 유지하는가")
    print(f"  {'신호':<12}{'국면':>8}{'보유':>5}{'방향':>5}"
          f"{'IS초과%':>9}{'IS t':>7}{'OOS기간':>8}{'OOS초과%':>10}"
          f"{'OOS t':>8}{'':>4}")
    print("  " + "-" * 88)
    _, oos_rows = eval_grid(sig_arr, ~is_mask, "OOS", collect=True)
    O = {(r["sig"], r["cut"], r["pct"], r["hold"], r["trade"]): r
         for r in oos_rows}
    survivors = []
    for _, r in R.head(8).iterrows():
        k = (r["sig"], r["cut"], r["pct"], r["hold"], r["trade"])
        o = O.get(k)
        nm = f"{r['sig']} {r['cut']}{int(r['pct']*100)} {r['hold']}일 " \
             f"{'롱' if r['trade']>0 else '숏'}"
        if o is None:
            print(f"  {r['sig']:<12}{r['cut']+str(int(r['pct']*100)):>8}"
                  f"{r['hold']:>5}{'롱' if r['trade']>0 else '숏':>5}"
                  f"{r['excess']:>9.3f}{r['t']:>7.2f}{'표본부족':>30}")
            continue
        ok = (o["excess"] > 0) and (r["excess"] > 0)
        if ok:
            survivors.append(nm)
        print(f"  {r['sig']:<12}{r['cut']+str(int(r['pct']*100)):>8}"
              f"{r['hold']:>5}{'롱' if r['trade']>0 else '숏':>5}"
              f"{r['excess']:>9.3f}{r['t']:>7.2f}{o['n']:>8}"
              f"{o['excess']:>10.3f}{o['t']:>8.2f}{'  ✓' if ok else '  ✗':>4}")

    verdict = ("기각 — 최대통계량 위약을 못 넘는다" if pval > 0.05
               else ("후보: " + ", ".join(survivors) if survivors
                     else "기각 — 위약은 넘었으나 표본 밖 부호 유지 실패"))
    print("\n" + "=" * 96)
    print(f"  판정: **{verdict}**")
    print("=" * 96)

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(
        {"params": vars(a), "n_cells": len(cells), "obs_best_t": obs_best,
         "null_mean": float(nulls.mean()),
         "null_p95": float(np.percentile(nulls, 95)),
         "p_value": pval, "verdict": verdict, "survivors": survivors,
         "unconditional": {f"{k[0]}d/{k[1]}": v for k, v in uncond.items()},
         "top": R.head(20).to_dict("records")},
        ensure_ascii=False, indent=2, default=str))
    print(f"  → {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
