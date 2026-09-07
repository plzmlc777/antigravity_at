"""운동학 밴드 위치 × 보유 격자 — 아카이브 검정.

## 왜

페이퍼 원장(225건)에서 롱숏3h4 의 롱 다리가 **r +0.195 (p 0.040)** 로 나왔는데
**부호가 규칙과 반대**였다. 규칙은 "z_vel 이 낮을수록(많이 떨어졌을수록) 롱이 좋다"
인데, 실측은 **밴드 상단(-0.25 쪽)이 35배 좋았다**(하 +0.028% / 상 +0.983%).

225건 · 다리 하나 · 오늘 수십 개 값을 훑은 뒤의 p 0.040 은 통과가 아니다(교훈#95).
아카이브 2,000일로 **밴드 위치와 보유를 같이** 갈라 다시 묻는다.

    ① 밴드 위치   하(-1.25~) · 중 · 상(~-0.25) 3등분 — 어디가 버나
    ② 보유        120 · 240 · 480분 — 회전을 줄이면 마찰을 넘나
    ③ 방향 대조군 뒤집으면 어떻게 되나 (교훈#91)
    ④ 최대통계량  섞은 자료로 **같은 격자 전부**를 다시 뒤진 최고 t (교훈#95)

## 신호 — 페이퍼와 같은 식, 5분봉 눈금

    1분 기준   WIN_H 60 · WINDOW 360 · DELTA 180 · 이력 790분
    5분 기준   12 · 72 · 36 · 158봉

    fw[i] = c[i+12]/c[i] - 1
    win   = 1 if fw > 0
    rate  = win.rolling(72, min_periods=36).mean().shift(12)   ⚠ shift 필수(미래참조)
    vel   = rate - rate.shift(36)
    acc   = vel - vel.shift(36)
    z_vel = vel / (se*sqrt(2))   ·   z_acc = acc / (se*2)   ·   se = sqrt(p(1-p)/6)

    밴드   롱 -1.25 <= z_vel <= -0.25 & z_acc < +0.5
           숏 +0.25 <= z_vel <= +1.25 & z_acc > -0.5

## 관측 단위는 **날**이다

보유 480분이면 앵커가 겹친다. 겹친 표본을 거래 단위로 t 내면 부풀린다(교훈#92).
날별 묶음 수익 하나를 관측 하나로 센다.

## 페이퍼와 다른 점

    체결가   페이퍼 1분봉 종가 / 여기 5분봉 종가
    생존필터 페이퍼는 분당 체결수>=5. 아카이브에 체결수가 없어 거래대금으로 대신
    손절     5% · 보유 구간 5분봉 저/고 (페이퍼보다 촘촘)
    지연     페이퍼 롱숏1/3h4 는 지연 0 이므로 여기도 0

사용:
    python3 -m scripts.research.kine_band_hold --smoke
    python3 -m scripts.research.kine_band_hold --perm 200
    python3 -m scripts.research.kine_band_hold --reuse --perm 200
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
log = logging.getLogger("kine_band")


@dataclass
class Cfg:
    bars: str = "runs/bars5m_ext"
    out: str = "runs/research_track/kine_band_hold"
    bar_min: int = 5
    win_h: int = 60          # 지평(분)
    window: int = 360        # 창(분)
    delta: int = 180         # 간격(분)
    z_lo: float = -1.25
    z_hi: float = -0.25
    acc_max: float = 0.5
    n_side: int = 3          # 다리당 종목 수 (롱숏3h4 와 같게)
    holds: tuple = (120, 240, 480)
    terciles: tuple = ("하", "중", "상", "전체")
    dirs: tuple = (1, -1)
    stop_pct: float = 5.0
    # ⚠ 익절 격자. 0 = 끔(현행 규칙). 손절과 익절이 **같은 창에서 둘 다 닿으면
    #   무엇이 먼저인지 5분봉 저/고로는 못 가린다** — 엔진과 같게 **손절 우선**으로
    #   본다(비관 쪽). 낙관 경계는 --tp-optimistic 으로 따로 잰다.
    tps: tuple = (0.0,)
    fee_rt: float = 0.072
    tp_first: bool = False      # True 면 익절 우선(낙관 경계)
    min_dv_usd: float = 50_000.0
    n_perm: int = 200
    seed: int = 20260907
    min_days: int = 60
    symbols: int = 0

    @property
    def wb(self) -> int: return self.win_h // self.bar_min      # 12
    @property
    def wn(self) -> int: return self.window // self.bar_min     # 72
    @property
    def db(self) -> int: return self.delta // self.bar_min      # 36
    @property
    def warm(self) -> int: return self.wb + self.wn + 2 * self.db + 2   # 158


def zsig(c: np.ndarray, cfg: Cfg) -> tuple[np.ndarray, np.ndarray]:
    """페이퍼 `signal_now` 와 같은 식. 배열 전체에 대해 한 번에."""
    n = len(c)
    fw = np.full(n, np.nan)
    fw[:n - cfg.wb] = c[cfg.wb:] / c[:n - cfg.wb] - 1.0
    win = pd.Series(np.where(np.isfinite(fw), (fw > 0).astype(float), np.nan))
    # ⚠ shift(wb) — 승부가 끝난 앵커만 쓴다. 빼면 미래참조다.
    rate = win.rolling(cfg.wn, min_periods=cfg.wn // 2).mean().shift(cfg.wb)
    vel = rate - rate.shift(cfg.db)
    acc = vel - vel.shift(cfg.db)
    neff = max(cfg.window / cfg.win_h, 1.0)
    p = rate.clip(0.01, 0.99)
    se = np.sqrt(p * (1 - p) / neff)
    return (vel / (se * np.sqrt(2))).to_numpy(), (acc / (se * 2.0)).to_numpy()


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
        dv = d.v.to_numpy(np.float64) * c
        zv, za = zsig(c, cfg)

        idx = np.arange(n)
        ok = (idx >= cfg.warm) & (idx + maxh < n) & np.isfinite(zv) & np.isfinite(za)
        # 정각 앵커만 — 24/일
        anc_all = pd.DatetimeIndex(ts)
        ok &= np.asarray(anc_all.minute) == 0
        idx = idx[ok]
        if len(idx) == 0:
            continue
        # ⚠ 격자 결손 확인 — 인덱스 산술이 시각을 어기면 안 된다
        step = np.timedelta64(cfg.bar_min, "m")
        good = (ts[idx + maxh] - ts[idx]) == step * maxh
        idx = idx[good]
        if len(idx) == 0:
            continue

        dvm = pd.Series(dv).rolling(288, min_periods=96).median().shift(1).to_numpy()[idx]
        rec = {"sym": f.stem,
               "day": anc_all[idx].normalize().values,
               "z_vel": zv[idx].astype(np.float32),
               "z_acc": za[idx].astype(np.float32),
               "dvm": dvm.astype(np.float32)}
        px = c[idx]
        for H in cfg.holds:
            hb = H // cfg.bar_min
            lo_r = pd.Series(lo).rolling(hb).min().to_numpy()
            hi_r = pd.Series(hi).rolling(hb).max().to_numpy()
            j = idx + hb
            rec[f"fwd{H}"] = (c[j] / px - 1.0).astype(np.float32)
            rec[f"lo{H}"] = (lo_r[j] / px - 1.0).astype(np.float32)
            rec[f"hi{H}"] = (hi_r[j] / px - 1.0).astype(np.float32)
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


def cell(p: pd.DataFrame, cfg: Cfg, H: int, terc: str, direction: int,
         fwd=None, lor=None, hir=None, tp: float = 0.0) -> np.ndarray:
    """한 칸(보유·밴드위치·방향)의 **날별** 묶음 수익(%)."""
    fwd = p[f"fwd{H}"].to_numpy() if fwd is None else fwd
    lor = p[f"lo{H}"].to_numpy() if lor is None else lor
    hir = p[f"hi{H}"].to_numpy() if hir is None else hir
    zv, za, day = p.z_vel.to_numpy(), p.z_acc.to_numpy(), p.day.to_numpy()

    okL = (zv >= cfg.z_lo) & (zv <= cfg.z_hi) & (za < cfg.acc_max)
    okS = (zv >= -cfg.z_hi) & (zv <= -cfg.z_lo) & (za > -cfg.acc_max)
    # 밴드 안 위치 — 롱은 z_vel 이 낮을수록 "하", 숏은 거울
    def band_mask(ok, lo_edge, hi_edge, flip):
        if terc == "전체":
            return ok
        pos = (zv - lo_edge) / (hi_edge - lo_edge)          # 0=하 .. 1=상
        if flip:
            pos = 1.0 - pos
        third = {"하": (0.0, 1 / 3), "중": (1 / 3, 2 / 3), "상": (2 / 3, 1.0)}[terc]
        return ok & (pos >= third[0]) & (pos <= third[1])
    mL = band_mask(okL, cfg.z_lo, cfg.z_hi, False)
    mS = band_mask(okS, -cfg.z_hi, -cfg.z_lo, True)

    st = cfg.stop_pct / 100.0
    rets, days = [], []
    order = np.lexsort((zv, day))
    day_s = day[order]
    bnd = np.flatnonzero(np.r_[True, day_s[1:] != day_s[:-1], True])
    for a, b in zip(bnd[:-1], bnd[1:]):
        sl = order[a:b]
        L = sl[mL[sl]]
        S = sl[mS[sl]]
        if len(L) < cfg.n_side or len(S) < cfg.n_side:
            continue
        L = L[np.argsort(zv[L])][:cfg.n_side]          # 롱: z_vel 낮은 순
        S = S[np.argsort(-zv[S])][:cfg.n_side]         # 숏: z_vel 높은 순
        if direction < 0:
            L, S = S, L                                 # 거울
        # 롱: 저가가 -손절 을 스치면 손절 · 아니면 고가가 +익절 을 스치면 익절
        # 숏: 거울 (고가가 +손절 → 손절 · 저가가 -익절 → 익절)
        tpf = tp / 100.0
        if tpf > 0 and not cfg.tp_first:
            rl = np.where(lor[L] <= -st, -st,
                          np.where(hir[L] >= tpf, tpf, fwd[L]))
            rs = np.where(hir[S] >= st, -st,
                          np.where(lor[S] <= -tpf, tpf, -fwd[S]))
        elif tpf > 0:
            rl = np.where(hir[L] >= tpf, tpf,
                          np.where(lor[L] <= -st, -st, fwd[L]))
            rs = np.where(lor[S] <= -tpf, tpf,
                          np.where(hir[S] >= st, -st, -fwd[S]))
        else:
            rl = np.where(lor[L] <= -st, -st, fwd[L])
            rs = np.where(hir[S] >= st, -st, -fwd[S])
        net = np.r_[rl, rs] * 100.0 - cfg.fee_rt
        rets.append(net.mean()); days.append(day_s[a])
    return np.asarray(rets)


def tstat(x):
    return float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))) \
        if len(x) > 2 and x.std(ddof=1) > 0 else np.nan


def sweep(p, cfg, fwd=None, lor=None, hir=None) -> pd.DataFrame:
    rows = []
    for H in cfg.holds:
        f = p[f"fwd{H}"].to_numpy() if fwd is None else fwd[H]
        l = p[f"lo{H}"].to_numpy() if lor is None else lor[H]
        h = p[f"hi{H}"].to_numpy() if hir is None else hir[H]
        for terc in cfg.terciles:
            for d in cfg.dirs:
                for tp in cfg.tps:
                    r = cell(p, cfg, H, terc, d, f, l, h, tp)
                    if len(r) < 3:
                        continue
                    rows.append({"보유": H, "밴드": terc, "방향": d,
                                 "익절%": tp, "날": len(r),
                                 "일평균%": r.mean(), "합%": r.sum(),
                                 "t": tstat(r), "양수일%": 100 * (r > 0).mean()})
    return pd.DataFrame(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--symbols", type=int, default=0)
    ap.add_argument("--perm", type=int, default=200)
    ap.add_argument("--reuse", action="store_true")
    ap.add_argument("--tps", default="0",
                    help="익절 격자(%%). 쉼표. 0=끔. 예: 0,10,20,30,50")
    ap.add_argument("--n-side", type=int, default=3,
                    help="다리당 종목 수. 롱숏1=1 · 롱숏3h4=3 · 롱숏10=5")
    ap.add_argument("--tp-first", action="store_true",
                    help="손절·익절 동시 접촉 시 **익절 우선**(낙관 경계)")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    cfg = Cfg(symbols=30 if a.smoke else a.symbols, n_perm=a.perm,
              tps=tuple(float(x) for x in a.tps.split(",")),
              n_side=a.n_side,
              tp_first=a.tp_first)
    log.info("설정 전문: %s", json.dumps(asdict(cfg), ensure_ascii=False))
    log.info("파생 봉: 지평 %d · 창 %d · 간격 %d · 워밍업 %d", cfg.wb, cfg.wn, cfg.db, cfg.warm)

    d = ROOT / cfg.out
    d.mkdir(parents=True, exist_ok=True)
    cache = d / ("panel_%s.parquet" % (cfg.symbols or "all"))
    if a.reuse and cache.exists():
        p = pd.read_parquet(cache); p["sym"] = p.sym.astype("category")
        log.info("앵커 표 재사용 — %s (%s행)", cache, f"{len(p):,}")
    else:
        p = load_panel(cfg)
        p.to_parquet(cache, index=False)
        log.info("앵커 표 저장 — %s", cache)

    obs = sweep(p, cfg).sort_values("t", ascending=False)
    pd.set_option("display.width", 200)
    print("\n■ 관측 — %d칸 (방향 +1 = 페이퍼 규칙: 많이 떨어진 쪽 롱)" % len(obs))
    print(obs.to_string(index=False, float_format=lambda x: f"{x:9.4f}"))
    obs.to_csv(d / "observed.csv", index=False)
    (d / "config.json").write_text(json.dumps(asdict(cfg), ensure_ascii=False, indent=1))
    log.info("관측·설정 기록 — %s", d)

    rng = np.random.default_rng(cfg.seed)
    codes = p.sym.cat.codes.to_numpy()
    order = np.argsort(codes, kind="stable")
    bnd = np.flatnonzero(np.r_[True, codes[order][1:] != codes[order][:-1], True])
    base = {H: (p[f"fwd{H}"].to_numpy(), p[f"lo{H}"].to_numpy(), p[f"hi{H}"].to_numpy())
            for H in cfg.holds}
    null, t1 = [], time.time()
    for j in range(cfg.n_perm):
        F, L, Hh = {}, {}, {}
        for H in cfg.holds:
            f0, l0, h0 = base[H]
            F[H], L[H], Hh[H] = f0.copy(), l0.copy(), h0.copy()
        for x, y in zip(bnd[:-1], bnd[1:]):
            ii = order[x:y]
            k = int(rng.integers(1, max(len(ii) - 1, 2)))
            for H in cfg.holds:
                f0, l0, h0 = base[H]
                F[H][ii] = np.roll(f0[ii], k)
                L[H][ii] = np.roll(l0[ii], k)
                Hh[H][ii] = np.roll(h0[ii], k)
        s = sweep(p, cfg, F, L, Hh)
        null.append(np.nanmax(s.t.to_numpy()))
        if (j + 1) % 10 == 0:
            el = time.time() - t1
            log.info("  위약 %d/%d · %.1f분 · 남은 %.1f분", j + 1, cfg.n_perm,
                     el / 60, el / 60 * (cfg.n_perm - j - 1) / (j + 1))
            np.save(d / "null_partial.npy", np.asarray(null))
    null = np.asarray(null)
    om = float(np.nanmax(obs.t.to_numpy()))
    pv = float((null >= om).mean())
    print("\n■ 최대통계량 귀무 (원형회전 %d회 · 같은 %d칸을 매번 다시 뒤짐)"
          % (cfg.n_perm, len(obs)))
    print("  관측 최고 t %.3f  (보유 %s · 밴드 %s · 방향 %+d)"
          % (om, obs.iloc[0]["보유"], obs.iloc[0]["밴드"], obs.iloc[0]["방향"]))
    print("  귀무 최고 t 중앙 %.3f · 90%% %.3f · 최대 %.3f"
          % (np.median(null), np.quantile(null, 0.9), null.max()))
    print("  **p = %.3f**" % pv)
    np.save(d / "null_max_t.npy", null)
    (d / "verdict.json").write_text(json.dumps(
        {"obs_max_t": om, "p": pv, "n_perm": cfg.n_perm,
         "best": obs.iloc[0].to_dict()}, ensure_ascii=False, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
