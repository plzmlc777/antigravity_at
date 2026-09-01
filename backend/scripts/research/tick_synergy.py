"""보조지표 × **위약 운동학** 시너지 — 틱 기질에서 먼저 거른다.

## 왜 (2026-09-01, 대표님 지시)

"지표 단독이 아니라 **위약 전략과 함께 썼을 때** 시너지를 내는 지표를 찾아라.
그리고 틱에서 먼저 시험하라 — 거기서 좋지 않으면 몇 년치 백테스트를 할 이유가
없다."

맞는 순서다. 오늘 ADX 를 4년으로 먼저 돌린 것은 낭비였다.

## 무엇이 기준선인가

위약 운동학 밴드가 후보를 준다(z_vel ∈ [-1.25,-0.25] 롱 · 거울 숏).
그 안에서 **무엇으로 고를 것인가**가 질문이다.

    무작위      밴드 안 무작위          ← 바닥. 이걸 못 이기면 지표는 값어치 0
    z_vel      현행 규칙(극단 순)      ← 지금 페이퍼가 쓰는 것
    지표 X     지표로 순위             ← 대체
    z_vel+X    두 순위의 합            ← **시너지**
    X|밴드     지표 상위 분위 안에서 z_vel 순  ← 게이트형 시너지

**시너지는 `z_vel+X` 와 `X|밴드` 가 `z_vel` 단독을 이기는가**로만 판정한다.
지표가 단독으로 좋아도 z_vel 과 겹치면 값어치가 없다.

## 지표 12종 (틱 5분봉에서 계산)

    rsi · macd · adx_di · boll_b · atr · stoch · vol_r · ema_sl · obv_sl
    tkb(테이커 불균형) · flip(뒤집힘율) · irr(체결간격 변동)

뒤 셋은 **틱에만 있다**. 앞 아홉은 봉으로도 되지만 같은 자리에서 재야
비교가 된다.

⚠ 표본 — 틱이 6일뿐이다. 독립 단위는 **날짜 6개**(교훈#112). 여기서 나오는
  건 판정이 아니라 **선별**이다. 통과한 것만 몇 년치로 넘긴다.
⚠ 방향맞춤 위약 · 같은 앵커 · 블록 수 표기(교훈#116) · 상위/하위 마스킹 분리.
⚠ 다리 이름은 실제 동작대로.

사용:
  python3 -m scripts.research.tick_synergy --smoke
  python3 -m scripts.research.tick_synergy --reps 200
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
BARS = ROOT / "runs" / "tickbars5m"
OUT = ROOT / "runs" / "research_track" / "tick_synergy_2026_09_01"
log = logging.getLogger("synergy")

IND = ["rsi", "macd", "adx_di", "boll_b", "atr", "stoch", "vol_r",
       "ema_sl", "obv_sl", "tkb", "flip", "irr"]
MODES = ["무작위", "z_vel", "지표", "z_vel+지표", "지표게이트"]


@dataclass(frozen=True)
class Cfg:
    win_h: int = 12              # 선도 지평 60분
    window: int = 72             # 창 360분
    delta: int = 36              # 간격 180분
    z_lo: float = -1.25
    z_hi: float = -0.25
    acc_max: float = 0.5
    holds: tuple = (12, 24, 48, 72, 96, 144)   # 1·2·4·6·8·12시간
    picks: tuple = (3, 5)
    gates: tuple = (0.3, 0.5, 0.7)   # 게이트형: 지표 상위 이 분위 안에서
    dirs: tuple = (1, -1)        # ⚠ 지표 방향을 **결과 보고 고르지 않는다**(교훈#91)
    fee_rt: float = 0.072
    min_side: int = 8
    reps: int = 200
    seed: int = 20260901

    def dump(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


def rank_rows(v, ok):
    """행 안 백분위(큰 값 1.0). 무효는 nan. 두 번 argsort 로 통째 처리."""
    x = np.where(ok & np.isfinite(v), v, np.nan)
    o = np.argsort(np.where(np.isnan(x), np.inf, x), axis=1)
    r = np.empty(o.shape, np.int32)
    np.put_along_axis(r, o, np.arange(x.shape[1], dtype=np.int32)[None, :], axis=1)
    cnt = (~np.isnan(x)).sum(1, keepdims=True)
    return np.where(np.isnan(x), np.nan, r/np.maximum(cnt-1, 1)).astype(np.float32)


def wilder(x, n):
    r = pd.DataFrame(x).ewm(alpha=1.0/n, adjust=False).mean().to_numpy(np.float32)
    return np.array(r, dtype=np.float32, copy=True)


def build_all(cfg):
    """틱 특징봉 → (지표 12종, z_vel, z_acc, 생존, 종가, 시각축, 종목).

    ⚠ `tick_combo.py` 가 같은 것을 쓴다. 복제하면 두 하네스가 조용히
      갈라진다 — 여기 한 곳에서만 만든다.
    """
    import time as _t
    t0 = _t.time()
    cols = ("op", "hi", "lo", "cl", "ntr", "qsum", "flip", "dtm", "dts", "tkb")
    d = {c: {} for c in cols}
    for f in sorted(BARS.glob("*.parquet")):
        x = pd.read_parquet(f)
        if len(x) < 400:
            continue
        ts = pd.to_datetime(x.ts_ms, unit="ms", utc=True)
        for c in cols:
            d[c][f.stem] = pd.Series(x[c].to_numpy(np.float32), index=ts)
    idx = pd.date_range(min(v.index.min() for v in d["cl"].values()),
                        max(v.index.max() for v in d["cl"].values()),
                        freq="5min", tz="UTC")
    F = {c: pd.DataFrame(d[c]).reindex(idx) for c in cols}
    F["cl"] = F["cl"].ffill()
    syms = list(F["cl"].columns)
    C = F["cl"].to_numpy(np.float32)
    HI = F["hi"].to_numpy(np.float32); LO = F["lo"].to_numpy(np.float32)
    NT = F["ntr"].fillna(0).to_numpy(np.float32)
    QS = F["qsum"].fillna(0).to_numpy(np.float32)
    n, m = C.shape
    log.info("판 %s봉 × %d종목 · %s ~ %s · %.1f분", f"{n:,}", m,
             idx.min(), idx.max(), (time.time()-t0)/60)

    # ── 위약 운동학 z_vel (기준 신호) ─────────────────────
    fw = F["cl"].shift(-cfg.win_h)/F["cl"] - 1.0
    win = (fw > 0).astype(np.float32).where(fw.notna())
    rate = win.rolling(cfg.window, min_periods=cfg.window//2).mean().shift(cfg.win_h)
    vel = (rate - rate.shift(cfg.delta)).to_numpy(np.float32)
    acc = (vel - np.roll(vel, cfg.delta, axis=0)).astype(np.float32)
    acc[:cfg.delta] = np.nan
    pr = np.clip(rate.to_numpy(np.float32), 0.01, 0.99)
    se = np.sqrt(pr*(1-pr)/(cfg.window/cfg.win_h), dtype=np.float32)
    ZV = (vel/(se*np.float32(np.sqrt(2)))).astype(np.float32)
    ZA = (acc/(se*np.float32(2.0))).astype(np.float32)
    del fw, win, rate, vel, acc, pr, se

    # ── 지표 12종 ─────────────────────────────────────────
    lr = pd.DataFrame(np.log(np.maximum(C, 1e-12)))
    dif = lr.diff()
    up = dif.clip(lower=0); dn = (-dif).clip(lower=0)
    rs = up.ewm(alpha=1/14, adjust=False).mean() / \
        dn.ewm(alpha=1/14, adjust=False).mean().replace(0, np.nan)
    S = {}
    S["rsi"] = (100 - 100/(1+rs)).to_numpy(np.float32)
    e12 = lr.ewm(span=12, adjust=False).mean(); e26 = lr.ewm(span=26, adjust=False).mean()
    macd = e12 - e26
    S["macd"] = (macd - macd.ewm(span=9, adjust=False).mean()).to_numpy(np.float32)*1e4
    pc = np.roll(C, 1, 0); pc[0] = np.nan
    ph = np.roll(HI, 1, 0); ph[0] = np.nan
    pl = np.roll(LO, 1, 0); pl[0] = np.nan
    tr = np.fmax(HI-LO, np.fmax(np.abs(HI-pc), np.abs(LO-pc)))
    u_, dw = HI-ph, pl-LO
    atr = wilder(np.nan_to_num(tr), 14)
    pdi = 100*wilder(np.where((u_ > dw) & (u_ > 0), u_, 0.0), 14)/np.maximum(atr, 1e-12)
    ndi = 100*wilder(np.where((dw > u_) & (dw > 0), dw, 0.0), 14)/np.maximum(atr, 1e-12)
    S["adx_di"] = np.array(pdi - ndi, np.float32)
    S["atr"] = np.array(100*atr/np.maximum(C, 1e-12), np.float32)
    ma = pd.DataFrame(C).rolling(20).mean(); sd = pd.DataFrame(C).rolling(20).std()
    S["boll_b"] = ((pd.DataFrame(C)-ma)/(2*sd.replace(0, np.nan))).to_numpy(np.float32)
    hh = pd.DataFrame(HI).rolling(14).max(); ll = pd.DataFrame(LO).rolling(14).min()
    S["stoch"] = (100*(pd.DataFrame(C)-ll)/(hh-ll).replace(0, np.nan)).to_numpy(np.float32)
    vm = pd.DataFrame(QS).rolling(288, min_periods=72).median().shift(1)
    S["vol_r"] = (pd.DataFrame(QS).rolling(12).sum()/np.maximum(vm*12, 1e-9)
                  ).to_numpy(np.float32)
    e20 = lr.ewm(span=20, adjust=False).mean()
    S["ema_sl"] = (e20 - e20.shift(12)).to_numpy(np.float32)*1e4
    obv = (pd.DataFrame(QS)*np.sign(np.nan_to_num(dif.to_numpy()))).cumsum()
    S["obv_sl"] = ((obv - obv.shift(12))/np.maximum(
        pd.DataFrame(QS).rolling(12).sum(), 1e-9)).to_numpy(np.float32)
    S["tkb"] = F["tkb"].rolling(12).mean().to_numpy(np.float32)
    # ⚠ 열 이름이 다른 두 DataFrame 을 나누면 열이 **합집합**이 된다.
    #   F["flip"] 은 종목명 열, pd.DataFrame(NT) 는 정수 열이라 359 → 718 로
    #   불어나 조용히 전부 NaN 이 된다(2026-09-01 실측). numpy 로 계산한다.
    _fl = F["flip"].fillna(0).rolling(12).sum().to_numpy(np.float32)
    _nt = pd.DataFrame(NT).rolling(12).sum().to_numpy(np.float32)
    S["flip"] = (_fl/np.maximum(_nt, 1.0)).astype(np.float32)
    S["irr"] = (F["dts"].rolling(12).mean()
                / F["dtm"].rolling(12).mean().replace(0, np.nan)).to_numpy(np.float32)
    log.info("지표 %d종 준비 · %.1f분", len(S), (time.time()-t0)/60)

    live = (F["ntr"].fillna(0).rolling(12).median().shift(1) >= 3.0).to_numpy()
    return S, ZV, ZA, live, C, idx, syms, F


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--reps", type=int, default=None)
    p.add_argument("--smoke", action="store_true")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    cfg = Cfg(**({"reps": a.reps} if a.reps else {}))
    if a.smoke:
        cfg = Cfg(reps=30)
    log.info("설정 %s", cfg.dump())
    t0 = time.time()

    S, ZV, ZA, live, C, idx, syms, F = build_all(cfg)
    n, m = C.shape
    OKL = ((ZV >= cfg.z_lo) & (ZV <= cfg.z_hi) & (ZA < cfg.acc_max) & live
           & np.isfinite(ZV))
    OKS = ((ZV >= -cfg.z_hi) & (ZV <= -cfg.z_lo) & (ZA > -cfg.acc_max) & live
           & np.isfinite(ZV))
    warm = cfg.win_h + cfg.window + 2*cfg.delta
    rng = np.random.default_rng(cfg.seed)
    rows = []
    best = np.full(cfg.reps, -9e9)
    for H in cfg.holds:
        hi_ = n - H
        R = np.full(C.shape, np.nan, np.float32)
        R[:hi_] = (C[H:H+hi_]/C[:hi_] - 1.0)*100.0
        base = np.arange(warm, n - H - 1)
        Ra = R[base]; L0 = OKL[base]; S0 = OKS[base]
        nb_ = len(base)
        day = pd.Series(pd.DatetimeIndex(idx[base]).date)
        blocks = []
        for ph in range(H):
            kk = np.arange(ph, nb_ - H - 1, H)
            kk = kk[(L0[kk].sum(1) >= cfg.min_side) & (S0[kk].sum(1) >= cfg.min_side)]
            if len(kk):
                blocks.append(kk)
        allk = np.concatenate(blocks) if blocks else np.array([], int)
        log.info("보유 %d분 · 앵커 %s · 날짜 %d", H*5, f"{len(allk):,}",
                 day.iloc[allk].nunique() if len(allk) else 0)
        RZV = {"L": rank_rows(-ZV[base], L0), "S": rank_rows(ZV[base], S0)}

        def pick(score_L, score_S, Np):
            """상위/하위 마스킹을 따로(교훈#116). 롱·숏 각각 자기 밴드에서."""
            out = []
            for sc, ok in ((score_L, L0), (score_S, S0)):
                v = np.where(ok & np.isfinite(sc), sc, -np.inf)
                out.append(np.argsort(-v, axis=1)[:, :Np].astype(np.int32))
            return out

        def stat(li, si, Rm):
            with np.errstate(invalid="ignore"):
                l_ = np.nanmean(np.take_along_axis(Rm, li, 1), 1)
                s_ = np.nanmean(np.take_along_axis(Rm, si, 1), 1)
            return (l_ - s_)/2.0 - cfg.fee_rt

        cells = []          # (라벨dict, li, si) — 위약에서 다시 쓴다
        for Np in cfg.picks:
            def add(name, mode, sl, ss, dr=0, gq=np.nan):
                li, si = pick(sl, ss, Np)
                cells.append(({"지표": name, "방식": mode, "방향": dr,
                               "게이트": gq, "N": Np, "보유분": H*5}, li, si))
            rr = rng.random(L0.shape).astype(np.float32)
            add("—", "무작위", rr, rr.copy())
            add("—", "z_vel", RZV["L"], RZV["S"])
            for name in IND:
                v0 = S[name][base]
                for dr in cfg.dirs:
                    v = v0*dr
                    rl, rs_ = rank_rows(v, L0), rank_rows(v, S0)
                    add(name, "지표", rl, rs_, dr)
                    add(name, "z_vel+지표", RZV["L"]+rl, RZV["S"]+rs_, dr)
                    for gq in cfg.gates:
                        gl = np.where(rl >= gq, RZV["L"], -np.inf)
                        gs = np.where(rs_ >= gq, RZV["S"], -np.inf)
                        add(name, "지표게이트", gl, gs, dr, gq)
        log.info("  보유 %d분 — 칸 %d · %.1f분", H*5, len(cells),
                 (time.time()-t0)/60)
        dayk = day.to_numpy()[allk]
        for lab, li, si in cells:
            v = stat(li, si, Ra)[allk]
            d_ = pd.Series(v, index=dayk).dropna()
            if len(d_) < 50:
                continue
            dd = d_.groupby(level=0).mean()
            mn, sdv = float(dd.mean()), float(dd.std(ddof=1))
            rows.append({**lab, "앵커": int(len(d_)), "날짜": len(dd),
                         "거래당": float(d_.mean()), "일평균": mn,
                         "날짜t": mn/(sdv/np.sqrt(len(dd))) if len(dd) > 2 else np.nan,
                         "양수일": f"{int((dd>0).sum())}/{len(dd)}"})
        # ── 회전 위약 최대통계량 — **격자 전체를 다시 뒤진다**(교훈#95)
        #    이동량은 신호 기억(창+델타+지평)과 보유를 넘겨야 한다(교훈#108)
        lo_s = max(warm, H) + 10
        if nb_ - 2*lo_s > 50:
            for rep in range(cfg.reps):
                sh = int(rng.integers(lo_s, nb_ - lo_s))
                Rs = Ra[(np.arange(nb_) - sh) % nb_]
                mx = -9e9
                for lab, li, si in cells:
                    if lab["방식"] == "무작위":
                        continue
                    v = stat(li, si, Rs)[allk]
                    v = v[np.isfinite(v)]
                    if len(v):
                        mx = max(mx, float(v.mean()))
                best[rep] = max(best[rep], mx)
                if (rep+1) % 50 == 0:
                    log.info("    위약 %d/%d · %.1f분", rep+1, cfg.reps,
                             (time.time()-t0)/60)
        del R, Ra
    T = pd.DataFrame(rows)
    # 기준선은 **보유별로** 다르다 — 같은 보유끼리 비교해야 한다
    zb = T[T.방식 == "z_vel"].set_index("보유분").일평균.to_dict()
    rb = T[T.방식 == "무작위"].set_index("보유분").일평균.to_dict()
    T["z대비"] = T.일평균 - T.보유분.map(zb)
    print(f"\n■ 지표 × 위약 운동학 시너지 — 틱 {m}종목 · 왕복 {cfg.fee_rt}% "
          f"· 칸 {len(T)}")
    print("  기준선(보유별)  " + " · ".join(
        f"{k}분 무작위 {rb.get(k, np.nan):+.4f} / **z_vel {v:+.4f}**"
        for k, v in sorted(zb.items())))
    for mode in ("z_vel+지표", "지표게이트", "지표"):
        sub = T[T.방식 == mode].sort_values("z대비", ascending=False).head(10)
        print(f"\n  [{mode}] 상위 10")
        print(sub[["지표", "방향", "게이트", "N", "보유분", "날짜", "거래당",
                   "일평균", "날짜t", "양수일", "z대비"]].to_string(
            index=False, float_format=lambda z: f"{z:+.4f}", na_rep="—"))
    obs = float(T[T.방식 != "무작위"].일평균.max())
    bb = best[np.isfinite(best) & (best > -8e9)]
    pm = float((bb >= obs).mean()) if len(bb) else np.nan
    print(f"\n■ 회전 위약 최대통계량 ({len(bb)}회 · {len(T)}칸)")
    print(f"  관측 최대 {obs:+.4f}%/일 · 귀무 중앙 {np.median(bb):+.4f} "
          f"· 95분위 {np.quantile(bb, .95):+.4f}  **p = {pm:.3f}**")
    print(f"\n  z_vel 을 이긴 칸 {int((T.z대비 > 0).sum())}/{len(T)} · "
          f"그중 날짜t>1 인 칸 {int(((T.z대비 > 0) & (T.날짜t > 1)).sum())}")

    # ── 보유 곡선 — 신호의 **초과**가 통행료를 어디서 넘는가
    print("\n■ 보유 곡선 — z_vel 의 무작위 대비 초과 (통행료는 양쪽 다 같은 0.072%)")
    print(f"  {'보유':>8s} {'앵커':>7s} {'날짜':>4s} {'무작위':>9s} {'z_vel':>9s} "
          f"{'초과':>9s} {'초과/시간':>10s} {'날짜t':>7s} {'양수일':>7s}")
    # ⚠ z_vel 기준선은 **종목수마다 하나씩**이라 보유별로 여러 행이다.
    #   한 행으로 가정하면 Series 가 나와 죽는다(2026-09-01).
    zr = T[T.방식 == "z_vel"].set_index(["보유분", "N"])
    rr2 = T[T.방식 == "무작위"].set_index(["보유분", "N"])
    for (h, Np) in sorted(zr.index):
        z = zr.loc[(h, Np)]
        if (h, Np) not in rr2.index:
            continue
        r_ = rr2.loc[(h, Np)]
        ex = float(z.일평균) - float(r_.일평균)
        print(f"  {int(h):5d}분 N{int(Np)} {int(z.앵커):7,d} {int(z.날짜):4d} "
              f"{float(r_.일평균):+9.4f} {float(z.일평균):+9.4f} {ex:+9.4f} "
              f"{ex/(h/60):+10.4f} {float(z.날짜t):+7.2f} {str(z.양수일):>7s}")
    print("  ⚠ 초과는 수수료가 상쇄된 값이다 — 자란다면 신호가 **더 먼 미래를 맞힌다**는 뜻.")
    print("  ⚠ 보유가 길수록 비겹침 블록이 준다. 12시간이면 6일에 하루 2블록뿐이다.")
    OUT.mkdir(parents=True, exist_ok=True)
    T.to_csv(OUT / "synergy.csv", index=False)
    (OUT / "cfg.json").write_text(cfg.dump())
    log.info("저장 %s · %.1f분", OUT, (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
