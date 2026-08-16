"""저베타 롱 후보 — **남은 장치 전부**. 통과하면 후보, 하나라도 죽으면 종결.

배경 (2026-08-16 `xsection_harness`)
    `beta_btc_60d` 롱이 사전 확정 규칙을 통과했다:
        IS  31앵커  Q5−Q1 **-4.46%p** · t -2.38 · 양수 26%
        OOS 11앵커  Q5−Q1 **-7.25%p** · t -3.31 · 양수 27%
        최대통계량(결합) 관측 2.38 · 귀무 중앙 1.05 → **p 0.000**
        시장방향 회귀 절편 **-5.39%p** (기계적 효과만은 아니다)

    ⚠ 그러나 [[feedback-lesson-96-measure-persistence-before-building-a-detector]] —
      **장치 하나 통과는 통과가 아니다.** 오늘 처음 위약을 통과한 결과가 다른
      세 장치에서 전부 죽은 전례가 있다.

거는 장치
    A **마찰 포함 포트폴리오** — 실제로 거래할 물건을 만든다. 수수료는 커널이
      이미 반영하므로 **펀딩**을 더한다(롱은 양수 펀딩을 낸다). 이게 최종
      관문이다 — 스프레드가 커도 집행에서 사라지면 없는 것이다(교훈 #82).
    B **이중정렬** — 베타가 **크기·변동성 위에 증분**을 주는가. 안 주면
      베타는 그것들의 재포장이다(교훈 #94 의 요건).
    C **고정 교차자산 위약** — 종목마다 **다른 종목의 베타**를 붙여 쓴다.
      뒤섞기와 달리 각 종목의 성질 시계열 구조는 보존하고 짝만 깬다(교훈 #93).
    D **확장 창** — 2021-03 부터. 상승장 앵커를 늘려 t -1.40 짜리 약한 구간을
      보강한다. ⚠ 결과를 보고 창을 고른 것이 아니라, **미리 지목된 약점**을
      메우는 것이다. 두 창을 **둘 다** 보고한다.
    E **하위기간 안정성** — 표본 안을 반으로 갈라 부호가 유지되는가.

⚠ 수집은 `xsection_harness.collect_samples` 를 쓴다. 재구현하지 않는다(규칙 ⑤).

사용:
  python3 -m scripts.research.beta_anomaly_devices
"""
from __future__ import annotations

import json
import logging
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("beta_dev")

OUT = ROOT / "runs" / "research_track" / "xsection" / "beta_anomaly_devices.json"
TRAIT = "beta_btc_60d"


def t_of(v: np.ndarray) -> float:
    if len(v) < 2:
        return float("nan")
    se = v.std(ddof=1) / np.sqrt(len(v))
    return float(v.mean() / se) if se else float("nan")


def quintile_spread(df: pd.DataFrame, trait: str, n_bins: int,
                    min_per_bin: int) -> pd.DataFrame:
    """앵커별 Q_top − Q_bot. `xsection_harness.judge` 와 같은 규약."""
    rows = []
    for an, g in df.groupby("anchor"):
        g = g.dropna(subset=[trait, "ret"])
        if len(g) < n_bins * min_per_bin:
            continue
        q = pd.qcut(g[trait].rank(method="first"), n_bins,
                    labels=list(range(1, n_bins + 1)))
        g = g.assign(q=q)
        if g.groupby("q", observed=True).size().min() < min_per_bin:
            continue
        m = g.groupby("q", observed=True)["ret"].mean()
        rows.append({"anchor": an, "spread": float(m[n_bins] - m[1]),
                     "q1": float(m[1]), "q5": float(m[n_bins])})
    return pd.DataFrame(rows)


def report_split(sp: pd.DataFrame, split: pd.Timestamp, label: str) -> dict:
    out = {}
    print(f"     {label:<22}", end="")
    for name, m in (("IS", sp["anchor"] < split), ("OOS", sp["anchor"] >= split)):
        v = sp.loc[m, "spread"].values
        out[name] = {"n": int(len(v)),
                     "mean": float(v.mean()) if len(v) else None,
                     "t": t_of(v) if len(v) > 1 else None}
        print(f"{name} {len(v):>3}앵커 {v.mean() if len(v) else np.nan:+7.2f}%p "
              f"t {t_of(v) if len(v)>1 else np.nan:+6.2f}   ", end="")
    print()
    return out


def main() -> int:
    from research.xsection_harness import (HarnessConfig, collect_samples,
                                           load_panel)
    from app.db.session import engine

    base = HarnessConfig(side="long", trait="all", start="2023-01-01",
                         split="2025-08-18", shuffle_null=0)
    split = pd.Timestamp(base.split)
    log.info("표본 수집 (기준 창 %s~)", base.start)
    df = collect_samples(base)
    sp0 = quintile_spread(df, TRAIT, base.n_bins, base.min_per_bin)

    print("=" * 100)
    print("  **저베타 롱 — 남은 장치**   기준 창 2023-01 ~ · 분할 2025-08-18")
    print("  ⚠ 스프레드는 Q5(고베타) − Q1(저베타). **음수면 저베타 승**이다")
    print("=" * 100)
    res: dict = {}
    print("\n  기준선")
    res["baseline"] = report_split(sp0, split, "beta_btc_60d")

    # ── C. 고정 교차자산 위약 ─────────────────────────────────────────
    print("\n  C. **고정 교차자산 위약** — 종목마다 다른 종목의 베타를 붙인다")
    syms = sorted(df["symbol"].unique())
    shift_map = {s: syms[(i + 1) % len(syms)] for i, s in enumerate(syms)}
    key = df.set_index(["anchor", "symbol"])[TRAIT]
    df_pl = df.copy()
    df_pl[TRAIT] = [key.get((a, shift_map.get(s)), np.nan)
                    for a, s in zip(df["anchor"], df["symbol"])]
    sp_pl = quintile_spread(df_pl, TRAIT, base.n_bins, base.min_per_bin)
    res["cross_asset_placebo"] = report_split(sp_pl, split, "위약(짝 어긋남)")

    # ── B. 이중정렬 ───────────────────────────────────────────────────
    print("\n  B. **이중정렬** — 통제변수 오분위 **안에서** 베타 스프레드")
    res["double_sort"] = {}
    for ctrl in ("log_dollar_vol", "rv_30d"):
        inner = []
        for an, g in df.groupby("anchor"):
            g = g.dropna(subset=[TRAIT, ctrl, "ret"])
            if len(g) < 40:
                continue
            g = g.assign(cq=pd.qcut(g[ctrl].rank(method="first"), 4,
                                    labels=[1, 2, 3, 4]))
            vals = []
            for _, gg in g.groupby("cq", observed=True):
                if len(gg) < 8:
                    continue
                gg = gg.assign(bq=pd.qcut(gg[TRAIT].rank(method="first"), 2,
                                          labels=[1, 2]))
                m = gg.groupby("bq", observed=True)["ret"].mean()
                if len(m) == 2:
                    vals.append(float(m[2] - m[1]))
            if vals:
                inner.append({"anchor": an, "spread": float(np.mean(vals))})
        sp_i = pd.DataFrame(inner)
        res["double_sort"][ctrl] = report_split(sp_i, split, f"{ctrl} 통제 안")

    # ── A. 마찰 포함 포트폴리오 ───────────────────────────────────────
    print("\n  A. **마찰 포함 포트폴리오** — 저베타 Q1 롱 · 수수료는 커널 반영 · "
          "펀딩 추가")
    with engine.connect() as conn:
        _, _, fund = load_panel(conn)
    fcost = []
    for a_, s_ in zip(df["anchor"], df["symbol"]):
        if s_ not in fund.columns:
            fcost.append(0.0)
            continue
        w = fund[s_].loc[(fund.index >= a_)
                         & (fund.index < a_ + pd.Timedelta(days=base.hold))]
        fcost.append(float(w.sum()) * 100)      # 롱은 양수 펀딩을 **낸다**
    df["fund_cost"] = fcost
    df["ret_net"] = df["ret"] - df["fund_cost"]
    log.info("펀딩 비용 — 30일 평균 %.2f%%p (롱 부담)", df["fund_cost"].mean())

    rows = []
    for an, g in df.groupby("anchor"):
        g = g.dropna(subset=[TRAIT, "ret_net"])
        if len(g) < base.n_bins * base.min_per_bin:
            continue
        q = pd.qcut(g[TRAIT].rank(method="first"), base.n_bins,
                    labels=list(range(1, base.n_bins + 1)))
        g = g.assign(q=q)
        m = g.groupby("q", observed=True)["ret_net"].mean()
        rows.append({"anchor": an, "q1": float(m[1]),
                     "q5": float(m[base.n_bins]),
                     "all": float(g["ret_net"].mean())})
    pf = pd.DataFrame(rows)
    print(f"     {'판본':>18}{'앵커':>6}{'평균%/30일':>12}{'t':>8}"
          f"{'누적%':>10}{'MDD%':>9}")
    for k, lab in (("q1", "저베타 Q1 롱"), ("q5", "고베타 Q5 롱"),
                   ("all", "전체 동일가중 롱")):
        v = pf[k].values / 100.0
        cum = np.cumprod(1 + v)
        peak = np.maximum.accumulate(cum)
        mdd = float(np.min(cum / peak - 1) * 100)
        print(f"     {lab:>18}{len(v):>6}{v.mean()*100:>+12.2f}{t_of(v*100):>+8.2f}"
              f"{(cum[-1]-1)*100:>+10.1f}{mdd:>9.1f}")
        res.setdefault("portfolio", {})[k] = {
            "n": int(len(v)), "mean_pct": float(v.mean() * 100),
            "t": t_of(v * 100), "cum_pct": float((cum[-1] - 1) * 100),
            "mdd_pct": mdd}
    exc = (pf["q1"] - pf["all"]).values
    print(f"     저베타 − 전체 초과 {exc.mean():+.2f}%p/30일 · t {t_of(exc):+.2f}"
          f" · 양수 {int((exc>0).sum())}/{len(exc)}")
    res["portfolio"]["excess_vs_all"] = {"mean": float(exc.mean()),
                                         "t": t_of(exc),
                                         "pos": int((exc > 0).sum()),
                                         "n": int(len(exc))}

    # ── E. 하위기간 안정성 ────────────────────────────────────────────
    print("\n  E. **하위기간 안정성** — 표본 안을 반으로")
    is_sp = sp0[sp0["anchor"] < split].sort_values("anchor")
    half = len(is_sp) // 2
    for lab, g in (("IS 전반", is_sp.iloc[:half]), ("IS 후반", is_sp.iloc[half:])):
        v = g["spread"].values
        print(f"     {lab:<22}{len(v):>3}앵커 {v.mean():+7.2f}%p t {t_of(v):+6.2f}"
              f" · 음수 {int((v<0).sum())}/{len(v)}")
        res.setdefault("subperiod", {})[lab] = {
            "n": int(len(v)), "mean": float(v.mean()), "t": t_of(v)}

    # ── D. 확장 창 ────────────────────────────────────────────────────
    print("\n  D. **확장 창** 2021-03 ~ (상승장 앵커 보강)")
    cfg2 = replace(base, start="2021-03-01")
    df2 = collect_samples(cfg2)
    sp2 = quintile_spread(df2, TRAIT, cfg2.n_bins, cfg2.min_per_bin)
    res["extended_window"] = report_split(sp2, split, "2021-03 ~")
    # 확장 창에서 시장 방향별
    mkt = df2.groupby("anchor")["ret"].mean()
    sp2 = sp2.assign(mkt=sp2["anchor"].map(mkt))
    for lab, m in (("시장 상승", sp2["mkt"] > 0), ("시장 하락", sp2["mkt"] <= 0)):
        v = sp2.loc[m, "spread"].values
        if len(v) < 3:
            continue
        print(f"     {lab:<22}{len(v):>3}앵커 {v.mean():+7.2f}%p t {t_of(v):+6.2f}"
              f" · 음수 {int((v<0).sum())}/{len(v)}")
        res.setdefault("extended_by_market", {})[lab] = {
            "n": int(len(v)), "mean": float(v.mean()), "t": t_of(v)}

    print("\n" + "=" * 100)
    print("  판정 규칙 — **하나라도 죽으면 종결**")
    print("    C 위약이 기준선만큼 크면 → 종목 신호가 아니다")
    print("    B 증분이 사라지면 → 크기·변동성의 재포장이다")
    print("    A 초과가 마찰 후 사라지면 → 거래할 물건이 아니다")
    print("    E 하위기간 부호가 갈리면 → 한 구간의 성질이다")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=2, default=str))
    print(f"  → {OUT}")
    print("=" * 100)
    return 0


if __name__ == "__main__":
    sys.exit(main())
