"""초단타 새 관점 — **언제 이 장사를 쉴 것인가**.

배경 (2026-08-11, 가설 1~7 전부 접은 뒤):
  일곱 가설이 전부 **"호가창 안 어디에 어떻게 설까"** 였다.
    1 최우선 / 2 흐름회피 / 3 큐회피 / 4 결합 / 5 깊이 / 6 불균형 / 7 깊이+불균형
  결과는 여섯 깊이 전부 음수였고 0 과 구분되지 않았다(|t| <= 2.56).

  그런데 일곱 가설이 공통으로 깔고 있던 가정이 있다 — **항상 호가를 댄다.**
  "언제 아예 쉴 것인가" 는 한 번도 정하지 않았다.

가설
  역선택은 **정보를 가진 주문**에게 당하는 것이다. 정보성 주문은 뉴스·급변동
  국면에 몰린다. 조용한 시간엔 그냥 필요해서 사고파는 주문뿐이다.
  → **정보성 주문이 적은 국면에만 호가를 대면 역선택이 줄어야 한다.**

  이 방향을 뒷받침하는 실측이 이미 있다. markout 로버스트 검정(2026-08-09)을
  통과한 3종목이 전부 **토큰화 주식**이었다(HK1810/SMCI/HIMS). 실물이 다른
  시장에서 거래되니 이쪽 호가창에 오는 정보성 주문이 적기 때문이다.
  **같은 원리를 종목축이 아니라 시간축에 적용한다.**

무엇을 재는가
  markout(내가 호가를 댔다면의 손익)을 **국면별로** 가른다. 국면 지표 넷:
    · 실현변동성 — 정보성 주문의 가장 직접적 대리지표
    · 체결 도착률 — 관심이 몰리는가
    · 대형 체결 비중 — 큰 주문이 정보성일 가능성이 높다
    · 스프레드 — 시장이 스스로 위험하다고 판단한 정도

  각 지표의 십분위별 markout 을 보고, **하위 국면(조용할 때)이 실제로 나은지**
  확인한다. 나으면 그 조건이 새 가설의 관문이 되고, 아니면 이 방향도 닫힌다.

주의
  · 국면 지표는 **그 시점까지의 정보로만** 만든다(롤링). 미래를 보면 안 된다.
  · 십분위 차이가 잡음인지 확인한다 — 2026-08-10 에 조건부 지형이 전부
    잡음으로 판명된 전례가 있다(ANOVA p 0.118~0.818).
  · 셀당 표본이 작으면 판정하지 않는다.

사용:
  python3 scripts/research/ultra_regime_markout.py --days 60 --min-dvol-usd 3000000
"""
from __future__ import annotations

import argparse
import glob
import json
import logging
import os
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("ultra_regime_markout")

MAKER_FEE_BP = 2.0
MARKOUT_MIN = 5              # markout 지평 (분)
ROLL = 1440                  # 국면 지표 롤링 창 (분) = 24시간


def main() -> int:
    p = argparse.ArgumentParser(description="국면별 메이킹 손익")
    p.add_argument("--data-dir", default=str(ROOT / "runs" / "aggtrade_1m"))
    p.add_argument("--days", type=int, default=60)
    p.add_argument("--min-dvol-usd", type=float, default=3_000_000)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--depth3d", action="store_true",
                   help="국면(스프레드x대형체결) x **가격이동 크기** 3차원. "
                        "aggTrades 로는 최우선 너머 호가가 없어 깊이를 직접 못 잰다 — "
                        "물러선 호가는 가격이 그만큼 쓸고 갈 때만 체결되므로 "
                        "봉의 이동 크기를 깊이의 대리로 쓴다")
    p.add_argument("--joint", action="store_true",
                   help="스프레드 x 대형체결 2차원 격자. 1차원 결과(스프레드 4.04bp, "
                        "대형체결 0.34bp)가 더해지는지 확인한다 — 더해진다는 보장이 "
                        "없으므로 곱해서 재야 한다")
    p.add_argument("--out", default=str(ROOT / "runs" / "research_track" /
                                        "ultra_regime_markout.json"))
    args = p.parse_args()

    files = sorted(glob.glob(os.path.join(args.data_dir, "*_agg1m.joblib")))
    if args.limit:
        files = files[:args.limit]

    # 국면지표 → 십분위 → markout 누적
    acc: dict[tuple, list] = {}
    n_used = 0
    for i, f in enumerate(files, 1):
        sym = os.path.basename(f).replace("_agg1m.joblib", "")
        try:
            d = joblib.load(f)
        except Exception:
            continue
        d = d[~d.index.duplicated(keep="last")].sort_index()
        d = d.loc[d.index >= d.index.max() - pd.Timedelta(days=args.days)]
        if len(d) < ROLL * 3:
            continue
        dv = d["quote_volume"].resample("1D").sum().median()
        if not np.isfinite(dv) or dv < args.min_dvol_usd:
            continue
        n_used += 1

        px = d["vwap"]
        ret = px.pct_change()
        fwd = px.shift(-MARKOUT_MIN)
        ok = (d["vwap_buy"].notna() & d["vwap_sell"].notna()
              & fwd.notna() & (px > 0))
        if ok.sum() < ROLL:
            continue

        # 내가 양쪽에 호가를 댔다면의 손익 (체결량 가중)
        sell_bp = (d["vwap_buy"] - fwd) / px * 1e4      # ask 에 팔았다면
        buy_bp = (fwd - d["vwap_sell"]) / px * 1e4      # bid 에 샀다면
        wq_s, wq_b = d["taker_buy_quote"], d["taker_sell_quote"]
        tot = (wq_s + wq_b).replace(0, np.nan)
        mk = (sell_bp * wq_s + buy_bp * wq_b) / tot - MAKER_FEE_BP

        # 국면 지표 — 전부 **그 시점까지의 정보만** (롤링 백분위)
        rv = ret.rolling(60, min_periods=30).std()
        large_frac = ((d["large_buy_quote"] + d["large_sell_quote"])
                      / d["quote_volume"].replace(0, np.nan))
        regs = {
            "실현변동성": rv,
            "체결도착률": d["n_trades"],
            "대형체결비중": large_frac,
            "스프레드": d["eff_spread_bp_adj"],
        }
        m = ok & mk.notna() & tot.notna()
        if args.depth3d:
            ps = (d["eff_spread_bp_adj"].rolling(ROLL, min_periods=ROLL // 4)
                  .rank(pct=True))
            pl = large_frac.rolling(ROLL, min_periods=ROLL // 4).rank(pct=True)
            # 깊이 대리 — 그 봉의 |가격이동| 을 변동성으로 정규화한 뒤 백분위.
            # 물러선 호가는 큰 이동에서만 체결되므로 상위 분위가 "깊은 체결" 이다.
            mv = (ret.abs() / rv.replace(0, np.nan))
            pm = mv.rolling(ROLL, min_periods=ROLL // 4).rank(pct=True)
            mm = m & ps.notna() & pl.notna() & pm.notna()
            if mm.sum() >= 500:
                bs = np.clip((ps[mm].values * 5).astype(int), 0, 4)
                bl = np.clip((pl[mm].values * 5).astype(int), 0, 4)
                bm = np.clip((pm[mm].values * 5).astype(int), 0, 4)
                v, w = mk[mm].values, tot[mm].values
                for a_ in range(5):
                    for b_ in range(5):
                        for c_ in range(5):
                            sel = (bs == a_) & (bl == b_) & (bm == c_)
                            if sel.any():
                                acc.setdefault(("d3", a_, b_, c_), []).append(
                                    np.column_stack([v[sel], w[sel]]))
            if i % 100 == 0:
                log.info("%d/%d (사용 %d)", i, len(files), n_used)
            continue
        if args.joint:
            # 스프레드 x 대형체결 2차원. 두 효과가 더해지는지는 곱해서 재야 안다.
            ps = (d["eff_spread_bp_adj"].rolling(ROLL, min_periods=ROLL // 4)
                  .rank(pct=True))
            pl = large_frac.rolling(ROLL, min_periods=ROLL // 4).rank(pct=True)
            mm = m & ps.notna() & pl.notna()
            if mm.sum() >= 500:
                bs = np.clip((ps[mm].values * 5).astype(int), 0, 4)   # 5분위
                bl = np.clip((pl[mm].values * 5).astype(int), 0, 4)
                v, w = mk[mm].values, tot[mm].values
                for a_ in range(5):
                    for b_ in range(5):
                        sel = (bs == a_) & (bl == b_)
                        if sel.any():
                            acc.setdefault(("joint", a_ * 5 + b_), []).append(
                                np.column_stack([v[sel], w[sel]]))
            if i % 100 == 0:
                log.info("%d/%d (사용 %d)", i, len(files), n_used)
            continue
        for name, sr in regs.items():
            pct = sr.rolling(ROLL, min_periods=ROLL // 4).rank(pct=True)
            mm = m & pct.notna()
            if mm.sum() < 500:
                continue
            b = np.clip((pct[mm].values * 10).astype(int), 0, 9)
            v = mk[mm].values
            w = tot[mm].values
            for k in range(10):
                sel = b == k
                if sel.any():
                    acc.setdefault((name, k), []).append(
                        np.column_stack([v[sel], w[sel]]))
        if i % 100 == 0:
            log.info("%d/%d (사용 %d)", i, len(files), n_used)

    if not acc:
        log.error("표본 0")
        return 1
    log.info("사용 %d종목", n_used)

    if args.depth3d:
        def cell(a_, b_, c_):
            ch = acc.get(("d3", a_, b_, c_))
            if not ch:
                return None
            arr = np.vstack(ch); v, w = arr[:, 0], arr[:, 1]
            return {"net": float((v * w).sum() / w.sum()),
                    "se": float(v.std(ddof=1) / np.sqrt(len(v))), "n": len(v)}
        print("\n" + "=" * 96)
        print(f"국면 x 가격이동(깊이 대리) 3차원 — {n_used}종목 / 최근 {args.days}일")
        print("=" * 96)
        print("  ※ 가격이동 상위 분위 = 큰 이동에서만 체결 = **물러선 호가**의 성격")
        for a_, alab in [(4, "스프 최고"), (2, "스프 중간"), (0, "스프 최저")]:
            print(f"\n  [{alab}]  행 = 대형체결 5분위 / 열 = 가격이동 5분위 (작음→큼)")
            for b_ in range(5):
                row = []
                for c_ in range(5):
                    x = cell(a_, b_, c_)
                    row.append(f"{x['net']:+9.2f}" if x else f"{'--':>9}")
                blab = ["대형최저", "2", "3", "4", "대형최고"][b_]
                print(f"    {blab:<9} " + " ".join(row))
        allc = [((a_, b_, c_), cell(a_, b_, c_))
                for a_ in range(5) for b_ in range(5) for c_ in range(5)]
        allc = [(k, v) for k, v in allc if v and v["n"] >= 10000]
        allc.sort(key=lambda kv: -kv[1]["net"])
        print("\n  상위 5칸 (표본 1만 이상):")
        for (a_, b_, c_), v in allc[:5]:
            print(f"    스프{a_+1} x 대형{b_+1} x 이동{c_+1} → "
                  f"{v['net']:+.2f} ± {v['se']:.2f} bp (n={v['n']:,})")
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        with open(args.out, "w") as fh:
            json.dump({"mode": "depth3d", "n_symbols": n_used,
                       "cells": [{"spread_q": k[0]+1, "large_q": k[1]+1,
                                  "move_q": k[2]+1, **v} for k, v in allc]},
                      fh, indent=2, ensure_ascii=False)
        print("=" * 96 + "\n")
        log.info("저장: %s", args.out)
        return 0

    if args.joint:
        print("\n" + "=" * 92)
        print(f"스프레드 x 대형체결 2차원 — {n_used}종목 / 최근 {args.days}일 / "
              f"메이커 {MAKER_FEE_BP}bp 차감")
        print("=" * 92)
        print("  행 = 스프레드 5분위 (좁음→넓음) / 열 = 대형체결 비중 5분위 (적음→많음)")
        print("  %-14s %10s %10s %10s %10s %10s" % ("", "대형 최저", "2", "3", "4", "대형 최고"))
        grid = {}
        for a_ in range(5):
            cells = []
            for b_ in range(5):
                ch = acc.get(("joint", a_ * 5 + b_))
                if not ch:
                    cells.append(None); continue
                arr = np.vstack(ch)
                v, w = arr[:, 0], arr[:, 1]
                mean = float((v * w).sum() / w.sum())
                se = float(v.std(ddof=1) / np.sqrt(len(v)))
                grid[(a_, b_)] = {"net_bp": mean, "se_bp": se, "n": len(v)}
                cells.append(mean)
            lab = ["스프 최저", "2", "3", "4", "**스프 최고**"][a_]
            print("  %-14s %s" % (lab, "  ".join(
                f"{c:+10.2f}" if c is not None else f"{'--':>10}" for c in cells)))
        best = max(grid.items(), key=lambda kv: kv[1]["net_bp"])
        (ba, bb), bv = best
        print("\n  최고 칸: 스프레드 %d분위 x 대형체결 %d분위 → "
              "%+.2f ± %.2f bp (n=%s)" % (ba + 1, bb + 1, bv["net_bp"],
                                          bv["se_bp"], f"{bv['n']:,}"))
        base = grid.get((4, 4)); solo_s = grid.get((4, 2)); solo_l = grid.get((2, 0))
        print("  참고 — 스프 최고x대형 최고 %s / 스프 최고x대형 중간 %s / "
              "스프 중간x대형 최저 %s"
              % (f"{base['net_bp']:+.2f}" if base else "--",
                 f"{solo_s['net_bp']:+.2f}" if solo_s else "--",
                 f"{solo_l['net_bp']:+.2f}" if solo_l else "--"))
        print("=" * 92 + "\n")
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        with open(args.out, "w") as fh:
            json.dump({"mode": "joint", "n_symbols": n_used,
                       "grid": {f"{k[0]}_{k[1]}": v for k, v in grid.items()}},
                      fh, indent=2, ensure_ascii=False)
        log.info("저장: %s", args.out)
        return 0

    res = []
    print("\n" + "=" * 88)
    print(f"국면별 메이킹 손익 — {n_used}종목 / 최근 {args.days}일 / "
          f"markout {MARKOUT_MIN}분 / 메이커 {MAKER_FEE_BP}bp 차감")
    print("=" * 88)
    for name in ["실현변동성", "체결도착률", "대형체결비중", "스프레드"]:
        cells = []
        for k in range(10):
            ch = acc.get((name, k))
            if not ch:
                continue
            a = np.vstack(ch)
            v, w = a[:, 0], a[:, 1]
            mean = float((v * w).sum() / w.sum())
            n = len(v)
            se = float(v.std(ddof=1) / np.sqrt(n)) if n > 1 else float("nan")
            cells.append({"regime": name, "decile": k, "n": n,
                          "net_bp": mean, "se_bp": se})
        if len(cells) < 10:
            print(f"  {name}: 십분위 부족")
            continue
        res.extend(cells)
        row = "  ".join(f"{c['net_bp']:+.1f}" for c in cells)
        lo = cells[0]["net_bp"]
        hi = cells[-1]["net_bp"]
        # 하위(조용) 대 상위(시끄러움)
        groups = [np.vstack(acc[(name, k)])[:, 0] for k in range(10)]
        F, pv = stats.f_oneway(*groups)
        print(f"\n  {name}  (십분위 낮음→높음)")
        print(f"    net: {row}")
        print(f"    하위1 {lo:+.2f}bp  vs  상위1 {hi:+.2f}bp   차이 {lo - hi:+.2f}bp"
              f"   ANOVA p={pv:.4f} {'← 구조 있음' if pv < 0.01 else '(잡음과 구분 불가)'}")
        best = max(cells, key=lambda c: c["net_bp"])
        print(f"    최고 십분위 {best['decile']}: {best['net_bp']:+.2f} "
              f"± {best['se_bp']:.2f}bp (n={best['n']:,})")
    print("\n" + "=" * 88 + "\n")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump({"n_symbols": n_used, "days": args.days, "results": res},
                  fh, indent=2, ensure_ascii=False)
    log.info("저장: %s", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
