"""마틴게일 파산 하네스 **판독** — 승률·파산률·파산 당시 상황·종목 비교.

`martingale_ruin_harness.py` 가 낸 CSV 세 벌(실측 strict / 위약 shuffle /
민감도 close_only)을 읽어 대표님이 물은 것만 뽑는다:

    ① 배수·스텝이 승률과 파산률을 각각 어떻게 움직이는가
    ② 파산이 **언제** 오는가 (사이클 시작 후 시간)
    ③ 파산 당시 **시장이 무엇을 하고 있었나** — 무조건 분포 대비 백분위
    ④ 종목마다 파산률이 다른가 (그리고 그 차이가 지속되는가)
    ⑤ 위약(추세 제거) 대비 실측 파산률 — 파산의 원인이 추세인가

⚠ ③은 **기준선 없이는 아무 말도 못 한다**. "파산 때 30일 하락률 -35%" 는
  그 종목이 원래 자주 -35% 이면 정보가 아니다. 그래서 전 봉 분포에서의
  **백분위**로 환산해 출력한다.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

D = ROOT / "runs" / "research_track" / "martingale_ruin"
CTX_COLS = ["ret_24h", "ret_7d", "ret_30d", "rv_7d", "rv_30d", "dd_30d",
            "btc_ret_7d", "btc_ret_30d"]


def line(t=""):
    print(t)


def sec(t):
    print("\n" + "=" * 104)
    print(t)
    print("=" * 104)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline-symbols", type=int, default=120,
                   help="무조건 분포 기준선을 만들 종목 수 (0=건너뜀)")
    a = ap.parse_args()

    real = pd.read_csv(D / "agg_long_short_strict_real.csv")
    null = pd.read_csv(D / "agg_long_short_strict_null_shuffle.csv")
    conly = pd.read_csv(D / "agg_long_short_close_only_real.csv")
    P = pd.read_csv(D / "persym_long_short_strict_real.csv")
    R = pd.read_csv(D / "ruins_long_short_strict_real.csv")
    meta = json.load(open(D / "meta_long_short_strict_real.json"))

    sec(f"마틴게일 파산 — 종합 판독  ({meta['n_symbols']}종목 · "
        f"{meta['total_bars']:,}봉 1h · 2021-01 ~ 2026-08)")
    line(f"  격자: 스텝 {meta['grid']['steps']} bp × 배수 {meta['grid']['mults']} "
         f"× 자본 {meta['grid']['caps']}배 × 방향 2 = {len(real)}칸")
    line(f"  총 사이클 {real.n_cycles.sum():,}건 · 총 파산 "
         f"{int((real.ruin_rate/100*real.n_closed).sum()):,}건")

    # ── ① 배수·스텝의 효과를 분리한다 ────────────────────────────
    sec("① 물타기 배수와 스텝값이 승률·파산률을 어떻게 움직이나 (자본 30배 고정)")
    q = real[real.cap == 30]
    for side in ("long", "short"):
        s = q[q.side == side]
        line(f"\n  ── {side} ──")
        line(f"{'스텝bp':>8}" + "".join(f"{'배수'+str(m):>17}"
                                       for m in sorted(s['mult'].unique())))
        line(f"{'':>8}" + "".join(f"{'승률/파산률':>17}"
                                  for _ in sorted(s['mult'].unique())))
        for st in sorted(s.step_bp.unique()):
            row = f"{st:>8.0f}"
            for m in sorted(s['mult'].unique()):
                r = s[(s.step_bp == st) & (s['mult'] == m)]
                if r.empty:
                    row += f"{'-':>17}"
                else:
                    r = r.iloc[0]
                    row += f"{r.win_rate:>10.2f}/{r.ruin_rate:<6.2f}"
            line(row)

    # ── ② 위약 대비 — 파산의 원인이 추세인가 ────────────────────
    sec("② 실측 vs 위약(봉 모양 IID 섞기 — 추세 지속성 제거)")
    line("  위약은 같은 봉들을 순서만 섞는다. 변동성·꼬리는 그대로고 **추세만** 사라진다.")
    line("  실측 파산률이 위약보다 높으면 파산의 원인은 추세다.\n")
    m = real.merge(null, on=["side", "step_bp", "mult", "cap"],
                   suffixes=("_r", "_n"))
    line(f"{'방향':<7}{'스텝bp':>7}{'배수':>6}{'자본':>6}"
         f"{'실측파산%':>11}{'위약파산%':>11}{'배율':>8}"
         f"{'실측ROI중앙%':>14}{'위약ROI중앙%':>14}")
    line("-" * 104)
    for _, r in m[m.cap == 30].sort_values(["side", "step_bp", "mult"]).iterrows():
        rt = (f"{r.ruin_rate_r / r.ruin_rate_n:>8.2f}" if r.ruin_rate_n > 0
              else f"{'-':>8}")
        line(f"{r.side:<7}{r.step_bp:>7.0f}{r['mult']:>6.1f}{r.cap:>6.0f}"
             f"{r.ruin_rate_r:>11.2f}{r.ruin_rate_n:>11.2f}{rt}"
             f"{r.roi_med_r:>+14.1f}{r.roi_med_n:>+14.1f}")
    line("")
    ok = m[(m.ruin_rate_n > 0.01) & (m.cap == 30)]
    if len(ok):
        line(f"  파산률 배율(실측/위약) 중앙 **{(ok.ruin_rate_r/ok.ruin_rate_n).median():.2f}배** "
             f"· 실측이 더 높은 칸 {(ok.ruin_rate_r > ok.ruin_rate_n).sum()}/{len(ok)}")
        line(f"  ROI 중앙값: 실측 {m[m.cap==30].roi_med_r.median():+.1f}% vs "
             f"위약 {m[m.cap==30].roi_med_n.median():+.1f}%")

    # ── ③ 파산 시점 ──────────────────────────────────────────────
    sec("③ 파산은 언제 오나 — 사이클 시작 후 경과 시간")
    line(f"  파산 상세 표본 {len(R):,}건 (설정당 상한 400건 균등추출)\n")
    for side in ("long", "short"):
        s = R[R.side == side]
        if s.empty:
            continue
        qs = s.bars.quantile([.10, .25, .50, .75, .90])
        line(f"  {side:<6} 중앙 {qs[.50]:>7.0f}시간 ({qs[.50]/24:>5.1f}일) · "
             f"10%분위 {qs[.10]:>5.0f}h · 90%분위 {qs[.90]:>7.0f}h "
             f"({qs[.90]/24:.0f}일) · 최단 {s.bars.min():.0f}h")
    line("")
    line("  물타기 계단 사용 — 파산 사이클은 사다리를 끝까지 쓰는가")
    line(f"{'방향':<7}{'평균계단':>9}{'최대계단':>9}{'평균명목(배)':>13}"
         f"{'진입가대비이동%':>16}")
    line("-" * 104)
    for side in ("long", "short"):
        s = R[R.side == side]
        if s.empty:
            continue
        line(f"{side:<7}{s.rungs.mean():>9.2f}{s.rungs.max():>9.0f}"
             f"{s.notional.mean():>13.1f}{s.adverse_pct.median():>+16.1f}")

    # ── ④ 파산 당시 상황 — 무조건 분포 대비 백분위 ──────────────
    sec("④ 파산 당시 시장은 무엇을 하고 있었나 (전 봉 무조건 분포 대비 백분위)")
    base = None
    if a.baseline_symbols:
        from sqlalchemy import text
        from app.db.session import engine
        from scripts.research.martingale_ruin_harness import bar_context
        syms = sorted(R.symbol.unique())[:a.baseline_symbols]
        with engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT symbol, ts, open, high, low, close, volume FROM "
                "ohlcv_hourly WHERE symbol = ANY(:s) ORDER BY symbol, ts"),
                {"s": syms}).fetchall()
        df = pd.DataFrame(rows, columns=["symbol", "ts", "open", "high",
                                         "low", "close", "volume"])
        b_all = []
        btc = None
        for sym, g in df.groupby("symbol"):
            g = g.reset_index(drop=True)
            if sym == "BTCUSDT":
                btc = pd.Series(g["close"].to_numpy(float),
                                index=pd.to_datetime(g["ts"]).to_numpy())
        for sym, g in df.groupby("symbol"):
            b_all.append(bar_context(g.reset_index(drop=True), btc))
        base = pd.concat(b_all, ignore_index=True)
        line(f"  기준선 = {len(syms)}종목 전 봉 {len(base):,}개의 무조건 분포\n")

    line("  ⚠ 아래 통합 중앙값은 **롱·숏을 섞은 것이라 방향성 지표에서는 무의미**하다")
    line("    (롱은 폭락에, 숏은 급등에 파산하므로 서로를 상쇄한다). 방향성 지표는")
    line("    아래 '방향별' 표를 봐라. 여기서 의미 있는 것은 **변동성** 두 줄이다.\n")
    line(f"{'지표':<14}{'파산시 중앙':>14}{'기준선 중앙':>14}"
         f"{'파산시 백분위':>15}   해석")
    line("-" * 104)
    NAME = {"ret_24h": "24h 수익률", "ret_7d": "7일 수익률",
            "ret_30d": "30일 수익률", "rv_7d": "7일 실현변동성",
            "rv_30d": "30일 실현변동성", "dd_30d": "30일 고점대비",
            "btc_ret_7d": "BTC 7일", "btc_ret_30d": "BTC 30일"}
    for col in CTX_COLS:
        if col not in R.columns:
            continue
        v = R[col].dropna()
        if v.empty:
            continue
        med = v.median()
        if base is not None and col in base.columns:
            bb = base[col].dropna()
            pct = 100.0 * (bb < med).mean()
            bmed = bb.median()
            tag = ("**극단**" if pct <= 5 or pct >= 95 else
                   "치우침" if pct <= 20 or pct >= 80 else "보통")
            line(f"{NAME[col]:<14}{med:>+14.3f}{bmed:>+14.3f}{pct:>14.1f}%   {tag}")
        else:
            line(f"{NAME[col]:<14}{med:>+14.3f}{'-':>14}{'-':>15}")

    # 롱/숏 갈라서 — **이쪽이 본판**이다
    line("\n  ── 방향별 (본판) — 괄호는 무조건 분포에서의 백분위 ──")
    line(f"{'방향':<7}{'24h':>18}{'7일':>18}{'30일':>18}"
         f"{'30일고점대비':>18}{'7일변동성':>16}")
    line("-" * 104)
    for side in ("long", "short"):
        s = R[R.side == side]
        if s.empty:
            continue
        cells = []
        for col in ("ret_24h", "ret_7d", "ret_30d", "dd_30d", "rv_7d"):
            v = s[col].median()
            if base is not None and col in base.columns:
                pc = 100.0 * (base[col].dropna() < v).mean()
                cells.append(f"{v:+7.1%}({pc:>4.1f}%)" if col != "rv_7d"
                             else f"{v:>6.2f}({pc:>4.1f}%)")
            else:
                cells.append(f"{v:+7.1%}")
        line(f"{side:<7}{cells[0]:>18}{cells[1]:>18}{cells[2]:>18}"
             f"{cells[3]:>18}{cells[4]:>16}")

    # 시간대·요일
    if "hour" in R.columns:
        h = R.groupby("hour").size()
        line(f"\n  파산 시각(UTC) 최다 {h.idxmax():.0f}시 {100*h.max()/h.sum():.1f}% / "
             f"최소 {h.idxmin():.0f}시 {100*h.min()/h.sum():.1f}% "
             f"(균등이면 4.2%)")

    # ── ⑤ 종목별 비교 ────────────────────────────────────────────
    sec("⑤ 종목마다 파산률이 다른가 (스텝 200bp · 배수 2.0 · 자본 30배 · long)")
    k_all = P[(P.step_bp == 200) & (P['mult'] == 2.0) & (P.cap == 30) &
              (P.side == "long") & (P.n_cycles >= 30)].copy()
    k_all["ruin_rate"] = k_all["ruin_rate"].astype(float)

    # ⚠ **이력 길이로 먼저 가른다.** 기질은 두 무리다 — 장기 보유 종목(1년+)과
    #   신상저격수 코호트(상장 ~ +35일, 약 850봉). 섞어 놓고 "종목마다 다르다"
    #   고 말하면 그건 종목 차이가 아니라 **상장 직후 대 정상 구간**의 차이다.
    LONG_HIST = 8760
    grp = {"장기(1년+)": k_all[k_all.bars >= LONG_HIST],
           "신규상장 코호트(~35일)": k_all[k_all.bars < LONG_HIST]}
    line(f"  판정 가능 종목 {len(k_all)}개 (사이클 30건 이상)\n")
    line(f"{'무리':<24}{'종목':>6}{'중앙봉수':>10}{'파산률중앙%':>12}"
         f"{'파산0건%':>10}{'ROI중앙%':>11}{'ROI양수%':>10}")
    line("-" * 104)
    for lab, g in grp.items():
        if g.empty:
            continue
        line(f"{lab:<24}{len(g):>6}{g.bars.median():>10.0f}"
             f"{g.ruin_rate.median():>12.2f}{100*(g.n_ruin==0).mean():>10.1f}"
             f"{g.roi_pct.median():>+11.1f}{100*(g.roi_pct>0).mean():>10.1f}")
    line("\n  → 두 무리가 갈리면 위 '파산률 상위 종목'은 종목 성질이 아니라 "
         "**상장 직후 구간**을 보고 있는 것이다.\n")

    k = grp["장기(1년+)"] if len(grp["장기(1년+)"]) > 20 else k_all
    line(f"  이하 표는 **장기 무리 {len(k)}종목**만 — 이력 길이 교란을 뺀다")
    line(f"  파산률 분포 — 중앙 {k.ruin_rate.median():.2f}% · "
         f"사분위 {k.ruin_rate.quantile(.25):.2f}~{k.ruin_rate.quantile(.75):.2f}% · "
         f"최대 {k.ruin_rate.max():.2f}%")
    line(f"  **파산 0건 종목 {int((k.n_ruin==0).sum())}개 / {len(k)}개 "
         f"({100*(k.n_ruin==0).mean():.1f}%)**")
    line(f"  ROI 양수 종목 {int((k.roi_pct>0).sum())}/{len(k)} "
         f"({100*(k.roi_pct>0).mean():.1f}%) · ROI 중앙 {k.roi_pct.median():+.1f}%")
    line("\n  파산률 상위 10종목")
    line(f"{'종목':<14}{'봉수':>8}{'사이클':>8}{'승률%':>8}{'파산률%':>9}"
         f"{'ROI%':>10}{'MDD%':>10}")
    line("-" * 104)
    for _, r in k.nlargest(10, "ruin_rate").iterrows():
        line(f"{r.symbol:<14}{r.bars:>8.0f}{r.n_cycles:>8.0f}{r.win_rate:>8.2f}"
             f"{r.ruin_rate:>9.2f}{r.roi_pct:>+10.1f}{r.mdd_pct:>+10.1f}")
    line("\n  ROI 상위 10종목 (파산률과 같이 본다)")
    line(f"{'종목':<14}{'봉수':>8}{'사이클':>8}{'승률%':>8}{'파산률%':>9}"
         f"{'ROI%':>10}{'MDD%':>10}")
    line("-" * 104)
    for _, r in k.nlargest(10, "roi_pct").iterrows():
        line(f"{r.symbol:<14}{r.bars:>8.0f}{r.n_cycles:>8.0f}{r.win_rate:>8.2f}"
             f"{r.ruin_rate:>9.2f}{r.roi_pct:>+10.1f}{r.mdd_pct:>+10.1f}")
    if len(k) > 20:
        c = k[["ruin_rate", "roi_pct"]].corr().iloc[0, 1]
        line(f"\n  파산률 ↔ ROI 상관 **{c:+.3f}** "
             f"(음수면 '파산 잦은 종목이 손해' — 즉 파산이 그냥 비용)")

    # ── ⑥ 민감도 ────────────────────────────────────────────────
    sec("⑥ 체결 규약 민감도 — strict vs close_only")
    mm = real.merge(conly, on=["side", "step_bp", "mult", "cap"],
                    suffixes=("_s", "_c"))
    q = mm[mm.cap == 30]
    line(f"  파산률 중앙 : strict {q.ruin_rate_s.median():.2f}% vs "
         f"close_only {q.ruin_rate_c.median():.2f}%")
    line(f"  승률   중앙 : strict {q.win_rate_s.median():.2f}% vs "
         f"close_only {q.win_rate_c.median():.2f}%")
    line(f"  ROI중앙 중앙: strict {q.roi_med_s.median():+.1f}% vs "
         f"close_only {q.roi_med_c.median():+.1f}%")
    line(f"  ROI 부호가 갈리는 칸 "
         f"{int((np.sign(q.roi_med_s) != np.sign(q.roi_med_c)).sum())}/{len(q)}")

    # ── 결론 요약 ────────────────────────────────────────────────
    sec("종합")
    best = real[(real.n_closed > 1000)].nlargest(1, "roi_med").iloc[0]
    line(f"  ROI 중앙 최고 칸: {best.side} 스텝 {best.step_bp:.0f}bp · "
         f"배수 {best['mult']:.1f} · 자본 {best.cap:.0f}배 → "
         f"ROI중앙 {best.roi_med:+.1f}% / 승률 {best.win_rate:.2f}% / "
         f"파산률 {best.ruin_rate:.2f}% / MDD중앙 {best.mdd_med:+.1f}%")

    # ⚠ 사다리 vs 대조군은 **같은 방향·같은 스텝·같은 자본**에서만 비교한다.
    #   방향과 자본이 다른 두 칸의 최고끼리 견주면 아무것도 증명하지 못한다.
    flat = real[real['mult'] == 1.0].set_index(["side", "step_bp", "cap"])
    wins, tot, deltas = 0, 0, []
    for _, r in real[real['mult'] > 1.0].iterrows():
        kk = (r.side, r.step_bp, r.cap)
        if kk not in flat.index:
            continue
        f0 = flat.loc[kk]
        tot += 1
        deltas.append(r.roi_med - float(f0.roi_med))
        wins += int(r.roi_med > float(f0.roi_med))
    line(f"\n  ── 같은 칸 대조: 물타기 배수(>1.0) vs 고정 배수(1.0) ──")
    line(f"  배수가 이긴 칸 **{wins}/{tot}** · ROI중앙 차이 중앙값 "
         f"{np.median(deltas):+.1f}%p")
    line(f"  **물타기 배수가 대조군을 이겼나: "
         f"{'예' if wins > tot / 2 and np.median(deltas) > 0 else '아니오'}**")
    line(f"  전 격자에서 ROI중앙 > 0 인 칸 {int((real.roi_med > 0).sum())}/{len(real)}")
    line(f"  그중 MDD중앙 > -20% 인 칸 "
         f"{int(((real.roi_med > 0) & (real.mdd_med > -20)).sum())}/{len(real)}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
