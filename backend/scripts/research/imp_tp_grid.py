"""충격(imp) 계열 — 익절 격자 아카이브 검정.

## 왜 별도 하네스인가

`kine_band_hold` 로 잰 익절 결과는 **kine 신호·롱 밴드** 것이다. 그런데 페이퍼에서
익절 30% 에 걸릴 거래는 전부 **충격 계열의 숏**이었다.

    kine 계열 (롱숏1·롱숏3h4·롱숏10)  1,471거래 중 ≥30% **1건**
    충격 계열 (탄성저울·충격스프3)       202거래 중 ≥30% **2건**(AKE 중복) · ≥10% **18건**

충격 계열은 꼬리가 **열 배 이상 두껍다**. 롱 수치로 답한 것이 잘못이었다(2026-09-07).

## 신호 — 페이퍼 `signal_now` 의 imp

    1분 기준   ar = |log수익| × 100 ·  ai = (ar/거래대금).rolling(60).mean()
               med = ai.rolling(1440, min_periods=360).median().shift(1)
               imp = ai[-1] / med
    5분 기준   rolling(12) · rolling(288, min_periods=72)

의미는 "거래대금 대비 가격이 얼마나 움직였나"를 **자기 하루 중앙 대비**로 본 것.
수준만 쓰면 시가총액 순위를 다시 그리므로 자기대비로 정규화한다.

## 방향 — 엔진과 같게

    엔진: cands 에 z_vel = **-imp** 를 넣고, 낮은 z_vel 을 롱 / 높은 z_vel 을 숏.
    즉  **imp 가 가장 낮은 종목을 숏** (거래는 많은데 가격이 안 움직인 종목)
        **imp 가 가장 높은 종목을 롱**
    ⚠ 이 부호는 원본 주석이 두 번 강조한 자리다. 뒤집으면 다른 전략이 된다.

    모드  short3 = 숏 3종목만 (탄성저울)
          both6  = 롱3 + 숏3 (충격스프3)

## 익절 · 손절

손절 5% 는 현행. 익절은 격자. 둘 다 닿으면 **손절 우선**(비관 쪽) — 5분봉 저/고로는
순서를 못 가린다. 낙관 경계는 `--tp-first`.

## 관측 단위는 **날**

보유 480분이면 앵커가 겹친다(교훈#92).

사용:
    python3 -m scripts.research.imp_tp_grid --smoke
    python3 -m scripts.research.imp_tp_grid --tps 0,10,20,30,50
    python3 -m scripts.research.imp_tp_grid --reuse --tps 0,20,30 --perm 200
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
log = logging.getLogger("imp_tp")


@dataclass
class Cfg:
    bars: str = "runs/bars5m_ext"
    out: str = "runs/research_track/imp_tp_grid"
    bar_min: int = 5
    ai_win: int = 60          # ai 이동평균(분)
    med_win: int = 1440       # 자기대비 중앙(분)
    med_min: int = 360        # 중앙 최소 표본(분)
    n_side: int = 3
    holds: tuple = (120, 240, 480)
    modes: tuple = ("short3", "both6")
    tps: tuple = (0.0,)
    dirs: tuple = (1, -1)
    stop_pct: float = 5.0
    fee_rt: float = 0.072
    tp_first: bool = False
    min_dv_usd: float = 50_000.0
    n_perm: int = 0
    seed: int = 20260907
    symbols: int = 0

    @property
    def aib(self) -> int: return self.ai_win // self.bar_min       # 12
    @property
    def medb(self) -> int: return self.med_win // self.bar_min     # 288
    @property
    def medmin(self) -> int: return self.med_min // self.bar_min   # 72
    @property
    def warm(self) -> int: return self.aib + self.medb + 12        # 312


def imp_sig(c: np.ndarray, qv: np.ndarray, cfg: Cfg) -> np.ndarray:
    ar = np.abs(np.diff(np.log(np.maximum(c, 1e-12)), prepend=np.nan)) * 100.0
    ai = pd.Series(ar / np.maximum(qv, 1e-9)).rolling(cfg.aib).mean()
    med = ai.rolling(cfg.medb, min_periods=cfg.medmin).median().shift(1)
    return (ai / med.where(med > 0)).to_numpy()


def load_panel(cfg: Cfg) -> pd.DataFrame:
    fs = sorted((ROOT / cfg.bars).glob("*.parquet"))
    if cfg.symbols:
        fs = fs[:cfg.symbols]
    log.info("종목 %d개 적재 시작 (보유 %s)", len(fs), cfg.holds)
    out, t0 = [], time.time()
    maxh = max(cfg.holds) // cfg.bar_min
    for i, f in enumerate(fs, 1):
        d = pd.read_parquet(f, columns=["ts", "h", "l", "c", "v"])
        if len(d) < cfg.warm + maxh + 10:
            continue
        d = d.sort_values("ts").reset_index(drop=True)
        ts, n = d.ts.to_numpy(), len(d)
        c = d.c.to_numpy(np.float64)
        hi, lo = d.h.to_numpy(np.float64), d.l.to_numpy(np.float64)
        qv = d.v.to_numpy(np.float64) * c
        imp = imp_sig(c, qv, cfg)

        idx = np.arange(n)
        anc = pd.DatetimeIndex(ts)
        ok = (idx >= cfg.warm) & (idx + maxh < n) & np.isfinite(imp)
        ok &= np.asarray(anc.minute) == 0
        idx = idx[ok]
        if len(idx) == 0:
            continue
        step = np.timedelta64(cfg.bar_min, "m")
        idx = idx[(ts[idx + maxh] - ts[idx]) == step * maxh]
        if len(idx) == 0:
            continue

        dvm = pd.Series(qv).rolling(288, min_periods=96).median().shift(1).to_numpy()[idx]
        rec = {"sym": f.stem, "day": anc[idx].normalize().values,
               "imp": imp[idx].astype(np.float32), "dvm": dvm.astype(np.float32)}
        px = c[idx]
        for H in cfg.holds:
            hb = H // cfg.bar_min
            lr = pd.Series(lo).rolling(hb).min().to_numpy()
            hr = pd.Series(hi).rolling(hb).max().to_numpy()
            j = idx + hb
            rec[f"fwd{H}"] = (c[j] / px - 1.0).astype(np.float32)
            rec[f"lo{H}"] = (lr[j] / px - 1.0).astype(np.float32)
            rec[f"hi{H}"] = (hr[j] / px - 1.0).astype(np.float32)
        out.append(pd.DataFrame(rec))
        if i % 50 == 0:
            el = time.time() - t0
            log.info("  [%d/%d] %.1f분 · 남은 %.1f분", i, len(fs), el / 60,
                     el / 60 * (len(fs) - i) / max(i, 1))
    p = pd.concat(out, ignore_index=True).dropna()
    p = p[p.dvm >= cfg.min_dv_usd]
    p["sym"] = p.sym.astype("category")
    log.info("앵커 %s행 · 종목 %d · 날 %d", f"{len(p):,}", p.sym.nunique(), p.day.nunique())
    return p


def legs(net_l, net_s, cfg, tp, lorL, hirL, lorS, hirS, fwdL, fwdS):
    """손절·익절 적용. 롱/숏 각각 배열."""
    st, tpf = cfg.stop_pct / 100.0, tp / 100.0
    if tpf <= 0:
        rl = np.where(lorL <= -st, -st, fwdL)
        rs = np.where(hirS >= st, -st, -fwdS)
    elif not cfg.tp_first:
        rl = np.where(lorL <= -st, -st, np.where(hirL >= tpf, tpf, fwdL))
        rs = np.where(hirS >= st, -st, np.where(lorS <= -tpf, tpf, -fwdS))
    else:
        rl = np.where(hirL >= tpf, tpf, np.where(lorL <= -st, -st, fwdL))
        rs = np.where(lorS <= -tpf, tpf, np.where(hirS >= st, -st, -fwdS))
    return rl, rs


def cell(p, cfg, H, mode, direction, tp, fwd, lor, hir) -> np.ndarray:
    imp, day = p.imp.to_numpy(), p.day.to_numpy()
    order = np.lexsort((imp, day))
    day_s = day[order]
    bnd = np.flatnonzero(np.r_[True, day_s[1:] != day_s[:-1], True])
    rets = []
    for a, b in zip(bnd[:-1], bnd[1:]):
        sl = order[a:b]
        if len(sl) < 2 * cfg.n_side:
            continue
        # sl 은 imp 오름차순. **imp 최저 = 숏**, imp 최고 = 롱 (엔진 부호)
        S = sl[:cfg.n_side]
        L = sl[-cfg.n_side:]
        if direction < 0:
            S, L = L, S
        rl, rs = legs(None, None, cfg, tp, lor[L], hir[L], lor[S], hir[S], fwd[L], fwd[S])
        net = rs if mode == "short3" else np.r_[rl, rs]
        rets.append((net * 100.0 - cfg.fee_rt).mean())
    return np.asarray(rets)


def tstat(x):
    return float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))) \
        if len(x) > 2 and x.std(ddof=1) > 0 else np.nan


def sweep(p, cfg, base=None) -> pd.DataFrame:
    rows = []
    for H in cfg.holds:
        f, l, h = (base[H] if base else
                   (p[f"fwd{H}"].to_numpy(), p[f"lo{H}"].to_numpy(), p[f"hi{H}"].to_numpy()))
        for mode in cfg.modes:
            for d in cfg.dirs:
                for tp in cfg.tps:
                    r = cell(p, cfg, H, mode, d, tp, f, l, h)
                    if len(r) < 3:
                        continue
                    rows.append({"보유": H, "모드": mode, "방향": d, "익절%": tp,
                                 "날": len(r), "일평균%": r.mean(), "합%": r.sum(),
                                 "t": tstat(r), "양수일%": 100 * (r > 0).mean()})
    return pd.DataFrame(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--symbols", type=int, default=0)
    ap.add_argument("--reuse", action="store_true")
    ap.add_argument("--tps", default="0,10,20,30,50")
    ap.add_argument("--tp-first", action="store_true")
    ap.add_argument("--perm", type=int, default=0)
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    cfg = Cfg(symbols=30 if a.smoke else a.symbols,
              tps=tuple(float(x) for x in a.tps.split(",")),
              tp_first=a.tp_first, n_perm=a.perm)
    log.info("설정 전문: %s", json.dumps(asdict(cfg), ensure_ascii=False))
    log.info("파생 봉: ai %d · 중앙 %d(최소 %d) · 워밍업 %d", cfg.aib, cfg.medb, cfg.medmin, cfg.warm)

    d = ROOT / cfg.out
    d.mkdir(parents=True, exist_ok=True)
    cache = d / ("panel_%s.parquet" % (cfg.symbols or "all"))
    if a.reuse and cache.exists():
        p = pd.read_parquet(cache); p["sym"] = p.sym.astype("category")
        log.info("앵커 표 재사용 — %s (%s행)", cache, f"{len(p):,}")
    else:
        p = load_panel(cfg)
        p.to_parquet(cache, index=False)

    obs = sweep(p, cfg).sort_values("t", ascending=False)
    pd.set_option("display.width", 220)
    print("\n■ 관측 %d칸 (방향 +1 = 엔진 규칙: imp 최저 숏 · 최고 롱)" % len(obs))
    print(obs.to_string(index=False, float_format=lambda x: f"{x:9.4f}"))
    obs.to_csv(d / "observed.csv", index=False)
    (d / "config.json").write_text(json.dumps(asdict(cfg), ensure_ascii=False, indent=1))

    print("\n■ 익절 발동률 (손절에 안 걸리고 익절에 닿은 비율)")
    lowq = p.groupby("day", observed=True).imp.transform(lambda s: s.rank(pct=True))
    shortside = lowq <= 0.05          # 숏 대상 근사(하위 5%)
    for H in cfg.holds:
        lo, hi = p[f"lo{H}"], p[f"hi{H}"]
        g = shortside
        cells = []
        for tp in (0.10, 0.20, 0.30, 0.50):
            cells.append(100 * (((hi[g] < 0.05) & (lo[g] <= -tp)).mean()))
        print("  %3d분  손절 %5.2f%% · 익절10 %.3f%% · 20 %.3f%% · 30 %.3f%% · 50 %.3f%%"
              % (H, 100 * (hi[g] >= 0.05).mean(), *cells))
    if cfg.n_perm <= 0:
        log.info("기록 — %s (위약 생략: --perm 0)", d)
        return 0

    # ── 최대통계량 귀무 — 종목별 원형회전으로 신호↔미래 대응만 끊는다 (교훈#95)
    # ⚠ 오늘 뒤진 격자 **전부**를 매 회 다시 뒤진다. 일부만 뒤지면 기준선이 낮아진다.
    import numpy.random as _r
    rng = _r.default_rng(cfg.seed)
    codes = p.sym.cat.codes.to_numpy()
    order = np.argsort(codes, kind="stable")
    bnd = np.flatnonzero(np.r_[True, codes[order][1:] != codes[order][:-1], True])
    base = {H: (p[f"fwd{H}"].to_numpy(), p[f"lo{H}"].to_numpy(), p[f"hi{H}"].to_numpy())
            for H in cfg.holds}
    null, t1 = [], time.time()
    for j in range(cfg.n_perm):
        rot = {}
        for H in cfg.holds:
            f0, l0, h0 = base[H]
            rot[H] = (f0.copy(), l0.copy(), h0.copy())
        for x, y in zip(bnd[:-1], bnd[1:]):
            ii = order[x:y]
            k = int(rng.integers(1, max(len(ii) - 1, 2)))
            for H in cfg.holds:
                f0, l0, h0 = base[H]
                rot[H][0][ii] = np.roll(f0[ii], k)
                rot[H][1][ii] = np.roll(l0[ii], k)
                rot[H][2][ii] = np.roll(h0[ii], k)
        sN = sweep(p, cfg, rot)
        null.append(np.nanmax(sN.t.to_numpy()))
        if (j + 1) % 10 == 0:
            el = time.time() - t1
            log.info("  위약 %d/%d · %.1f분 · 남은 %.1f분", j + 1, cfg.n_perm,
                     el / 60, el / 60 * (cfg.n_perm - j - 1) / (j + 1))
            np.save(d / "null_partial.npy", np.asarray(null))
    null = np.asarray(null)
    om = float(np.nanmax(obs.t.to_numpy()))
    pv = float((null >= om).mean())
    print("\n\u25a0 \ucd5c\ub300\ud1b5\uacc4\ub7c9 \uadc0\ubb34 (\uc6d0\ud615\ud68c\uc804 %d\ud68c \u00b7 \uac19\uc740 %d\uce78\uc744 \ub9e4\ubc88 \ub2e4\uc2dc \ub4a4\uc9d0)"
          % (cfg.n_perm, len(obs)))
    print("  \uad00\uce21 \ucd5c\uace0 t %.3f  (\ubcf4\uc720 %s \u00b7 \ubaa8\ub4dc %s \u00b7 \ubc29\ud5a5 %+d \u00b7 \uc775\uc808 %.0f%%)"
          % (om, obs.iloc[0]["보유"], obs.iloc[0]["모드"], obs.iloc[0]["방향"], obs.iloc[0]["익절%"]))
    print("  \uadc0\ubb34 \ucd5c\uace0 t \uc911\uc559 %.3f \u00b7 90%% %.3f \u00b7 \ucd5c\ub300 %.3f"
          % (np.median(null), np.quantile(null, 0.9), null.max()))
    print("  **p = %.3f**" % pv)
    np.save(d / "null_max_t.npy", null)
    (d / "verdict.json").write_text(json.dumps(
        {"obs_max_t": om, "p": pv, "n_perm": cfg.n_perm, "n_cells": len(obs),
         "best": obs.iloc[0].to_dict()}, ensure_ascii=False, indent=1, default=str))
    log.info("기록 — %s", d)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
