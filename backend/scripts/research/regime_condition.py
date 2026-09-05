"""**어떤 성질의 시기에 이기는가** — 전략을 국면으로 조건 짓는다.

## 왜 (2026-09-02 대표님 지시)

"하나의 전략으로 모든 시기를 이길 가능성은 거의 없다. 검사의 목적은
**어느 특성의 시기에 이기는가**를 밝히는 것이어야 한다."

⚠ 이 트랙은 국면 조건을 **열두 번 기각**했다. 다만 닫힌 것은 한 형태다 —
  "지금이 어떤 국면인지 **미리 알아** 스위치를 켠다"(전략 자기성과 p 0.112 ·
  외부 지표 6종 p 0.438 · 유니버스 중앙 가속도 p 0.500). **사후 진단**은
  아직 제대로 안 했다. 여기서는 그것을 한다.

⚠ 열두 번의 기각은 전부 **방향**(오르나 내리나)이었다. 롱숏 시장중립
  전략에 필요한 건 방향이 아니라 **분산**이다 — 종목이 다 같이 움직이면
  구조적으로 0이고, 흩어질수록 먹을 게 생긴다. 이 축은 한 번도 안 쟀다.

⚠ 교훈#96 — **탐지기보다 지속성을 먼저.** 국면이 이어지지 않으면 사후
  진단이 사전 활용으로 못 간다. 국면 자기상관을 같이 낸다.
⚠ 국면 값은 **전부 진입 시점 후행**이다. 선도값을 쓰면 미래참조다.

사용:
  python3 -m scripts.research.regime_condition
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger("regime_cond")
ROOT = Path(__file__).resolve().parents[2]
MICRO = ROOT / "runs" / "micro1m"
OUT = ROOT / "runs" / "research_track" / "regime_condition"


@dataclass(frozen=True)
class Cfg:
    win_h: int = 60
    window: int = 360
    delta: int = 180
    z_lo: float = -1.25
    z_hi: float = -0.25
    acc_max: float = 0.5
    min_live: float = 5.0
    fee_rt: float = 0.072
    hold: int = 120
    noise_win: int = 60
    slots: int = 6
    nq: int = 5                # 국면 분위 수
    def dump(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=1)


def feats(path: Path, c: Cfg):
    d = pd.read_parquet(path).sort_values("ts")
    ix = pd.DatetimeIndex(d.ts)
    g = d.set_index(ix).reindex(pd.date_range(ix.min(), ix.max(), freq="1min",
                                              tz="UTC"))
    cl = g.cl.ffill(); n = len(cl)
    if n < c.win_h + c.window + 2*c.delta + c.hold + 100:
        return None
    cc = cl.to_numpy(float)
    fw = np.full(n, np.nan); fw[:n-c.win_h] = cc[c.win_h:]/cc[:n-c.win_h] - 1.0
    win = pd.Series(np.where(np.isfinite(fw), (fw > 0).astype(float), np.nan))
    rate = win.rolling(c.window, min_periods=c.window//2).mean().shift(c.win_h)
    vel = rate - rate.shift(c.delta); acc = vel - vel.shift(c.delta)
    p_ = rate.clip(0.01, 0.99)
    se = np.sqrt(p_*(1-p_)/max(c.window/c.win_h, 1.0))
    n60 = g.ntr.rolling(c.noise_win).sum().to_numpy()
    f60 = g.flip.rolling(c.noise_win).sum().to_numpy()
    lr = np.diff(np.log(cc), prepend=np.log(cc[0]))
    with np.errstate(invalid="ignore", divide="ignore"):
        bump = np.where(n60 > 0, f60/n60, np.nan)
        dm = g.dtm.rolling(c.noise_win).mean().to_numpy()
        ds = g.dts.rolling(c.noise_win).mean().to_numpy()
        irr = np.where(dm > 0, ds/dm, np.nan)
    fwd = np.full(n, np.nan)
    fwd[:n-c.hold] = (cc[c.hold:]/cc[:n-c.hold] - 1.0)*100.0
    # ── 갈래별 신호 — **엔진의 부호 규약 그대로** (교훈#88) ─────
    #   엔진은 `z_vel 낮은 쪽을 롱 · 높은 쪽을 숏`. 각 신호는 그 자리에
    #   대입되며 부호가 신호마다 다르다:
    #     rmz · ac1 · skew : 그대로   (가장 **높은** 것을 숏)
    #     imp              : 부호 반전 (가장 **낮은** imp 를 숏)
    #     rev · sess       : 부호 반전
    qvv = g.qv.to_numpy(float)
    ar = np.abs(np.diff(np.log(np.maximum(cc, 1e-12)), prepend=np.nan))*100.0
    ai = pd.Series(ar/np.maximum(qvv, 1e-9)).rolling(60).mean()
    med = ai.rolling(1440, min_periods=360).median().shift(1)
    with np.errstate(invalid="ignore", divide="ignore"):
        imp = np.where(med.to_numpy() > 0, ai.to_numpy()/med.to_numpy(), np.nan)
        qsk = (g.q90/g.qmed.replace(0, np.nan)).rolling(60).mean().to_numpy()
        rmv = g.rmax.astype(float)
        rmz = np.where(
            rmv.rolling(1440, min_periods=360).median().shift(1).to_numpy() > 0,
            rmv.rolling(60).max().to_numpy()
            / rmv.rolling(1440, min_periods=360).median().shift(1).to_numpy(),
            np.nan)
    # ac1 — 분당 체결 수의 1차 자기상관(최근 60분). rolling corr 로 벡터화.
    nt = g.ntr.astype(float)
    ac1 = nt.rolling(60).corr(nt.shift(1)).to_numpy()
    rev = np.full(n, np.nan)
    rev[61:] = -(cc[61:]/cc[:-61] - 1.0)*100.0
    # ── 국면 재료 (전부 **후행**) ──────────────────────
    r6 = np.full(n, np.nan); k6 = 360
    r6[k6:] = (cc[k6:]/cc[:-k6] - 1.0)*100.0
    r24 = np.full(n, np.nan); k24 = 1440
    r24[k24:] = (cc[k24:]/cc[:-k24] - 1.0)*100.0
    rv = pd.Series(lr).rolling(360).std().to_numpy()*100
    return pd.DataFrame(
        {"zv": (vel/(se*np.sqrt(2))).to_numpy(),
         "za": (acc/(se*2.0)).to_numpy(),
         "live": g.ntr.rolling(60).median().shift(1).to_numpy(),
         "bump": bump, "irr": irr, "fwd": fwd,
         "imp": -imp, "skew": qsk, "ac1": ac1, "rmz": rmz, "rev": rev,
         "r6": r6, "r24": r24, "rv": rv,
         "ntr": g.ntr.rolling(60).sum().to_numpy()}, index=cl.index)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--signal", default="noise",
                   choices=["noise","kine","imp","skew","ac1","rmz","rev"],
                   help="갈래의 신호. noise=잡음순위합 · kine=z_vel 밴드 · "
                        "나머지는 신호값 순위(부호는 엔진 규약)")
    p.add_argument("--mode", default="both", choices=["both","short"],
                   help="both=롱n+숏n · short=숏만")
    p.add_argument("--slots", type=int, default=6)
    p.add_argument("--hold", type=int, default=120)
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    c = Cfg(slots=a.slots, hold=a.hold)
    log.info("설정 전문:\n%s", c.dump())
    log.info("인자 도달 — 신호 %s · 모드 %s · 슬롯 %d · 보유 %d분",
             a.signal, a.mode, a.slots, a.hold)
    t0 = time.time()

    fs = sorted(MICRO.glob("*.parquet"))
    if a.limit: fs = fs[:a.limit]
    F, names = {}, []
    for i, f in enumerate(fs, 1):
        try: r = feats(f, c)
        except Exception as e: log.warning("%s %s", f.stem, e); r = None  # noqa
        if r is not None: F[f.stem] = r; names.append(f.stem)
        if i % 10 == 0: log.info("[%d/%d] %.1f분", i, len(fs), (time.time()-t0)/60)
    lo = min(x.index.min() for x in F.values())
    hi = max(x.index.max() for x in F.values())
    grid = pd.date_range(lo, hi, freq=f"{c.hold}min", tz="UTC")
    K = ("zv","za","live","bump","irr","fwd","r6","r24","rv","ntr",
         "imp","skew","ac1","rmz","rev")
    Z = {k: np.full((len(grid), len(names)), np.nan, np.float32) for k in K}
    for j, s in enumerate(names):
        r = F[s].reindex(grid)
        for k in K: Z[k][:, j] = r[k].to_numpy(np.float32)
    del F
    log.info("앵커 %d · 종목 %d · %s ~ %s", len(grid), len(names), grid[0], grid[-1])

    # ── 앵커별 **국면 값** (전부 후행) ──────────────────
    with np.errstate(invalid="ignore", all="ignore"):
        med6 = np.nanmedian(Z["r6"], axis=1)          # 방향(6시간)
        med24 = np.nanmedian(Z["r24"], axis=1)        # 방향(24시간)
        q75 = np.nanpercentile(Z["r6"], 75, axis=1)
        q25 = np.nanpercentile(Z["r6"], 25, axis=1)
        disp = q75 - q25                              # **분산** — 사분위폭
        vol = np.nanmedian(Z["rv"], axis=1)           # 변동성
        mbump = np.nanmedian(Z["bump"], axis=1)       # 미시구조 — 반전율
        mirr = np.nanmedian(Z["irr"], axis=1)         # 미시구조 — 불규칙성
        act = np.nanmedian(Z["ntr"], axis=1)          # 활동량
    REG = {"분산(IQR6h)": disp, "방향(중앙6h)": med6, "방향(중앙24h)": med24,
           "변동성": vol, "반전율": mbump, "불규칙성": mirr, "활동량": act}

    # ── 거래 생성 — **신호는 파라미터**다(하네스 규칙 3) ─────
    half = c.slots // 2
    rows = []
    for t in range(len(grid)):
        lv, fw = Z["live"][t], Z["fwd"][t]
        base = np.isfinite(lv) & np.isfinite(fw) & (lv >= c.min_live)
        if a.signal == "noise":
            zv, za = Z["zv"][t], Z["za"][t]
            bp, ir = Z["bump"][t], Z["irr"][t]
            ok = base & np.isfinite(zv) & np.isfinite(za) & np.isfinite(bp) & np.isfinite(ir)
            L = ok & (zv >= c.z_lo) & (zv <= c.z_hi) & (za < c.acc_max)
            S = ok & (zv >= -c.z_hi) & (zv <= -c.z_lo) & (za > -c.acc_max)
            pool = L | S
            if not pool.any(): continue
            rb = pd.Series(np.where(pool, bp, np.nan)).rank(pct=True).to_numpy()
            ri = pd.Series(np.where(pool, ir, np.nan)).rank(pct=True).to_numpy()
            sc = rb + ri
            for mask, sh in ((L, False), (S, True)):
                i = np.flatnonzero(mask)
                if len(i) < half: continue
                for j in i[np.argsort(-sc[i])][:half]:
                    rows.append((t, sh, (-fw[j] if sh else fw[j]) - c.fee_rt))
            continue
        if a.signal == "kine":
            zv, za = Z["zv"][t], Z["za"][t]
            ok = base & np.isfinite(zv) & np.isfinite(za)
            L = ok & (zv >= c.z_lo) & (zv <= c.z_hi) & (za < c.acc_max)
            S = ok & (zv >= -c.z_hi) & (zv <= -c.z_lo) & (za > -c.acc_max)
            # ⚠ 롱은 z_vel **낮은** 순, 숏은 **높은** 순 — 밴드 끝에서 먼 쪽부터
            if a.mode == "short":
                i = np.flatnonzero(S)
                if len(i) < c.slots: continue
                for j in i[np.argsort(-zv[i])][:c.slots]:
                    rows.append((t, True, -fw[j] - c.fee_rt))
            else:
                for mask, sh, key in ((L, False, zv), (S, True, -zv)):
                    i = np.flatnonzero(mask)
                    if len(i) < half: continue
                    for j in i[np.argsort(key[i])][:half]:
                        rows.append((t, sh, (-fw[j] if sh else fw[j]) - c.fee_rt))
            continue
        # imp · skew · ac1 · rmz · rev — **밴드 없음**. 신호값 순위로 가른다.
        sg = Z[a.signal][t]
        ok = base & np.isfinite(sg)
        i = np.flatnonzero(ok)
        if a.mode == "short":
            if len(i) < c.slots: continue
            for j in i[np.argsort(-sg[i])][:c.slots]:      # 높은 쪽 숏
                rows.append((t, True, -fw[j] - c.fee_rt))
        else:
            if len(i) < c.slots: continue
            o = i[np.argsort(sg[i])]
            for j in o[:half]:                              # 낮은 쪽 롱
                rows.append((t, False, fw[j] - c.fee_rt))
            for j in o[-half:]:                             # 높은 쪽 숏
                rows.append((t, True, -fw[j] - c.fee_rt))
    T = pd.DataFrame(rows, columns=["t","short","net"])
    log.info("거래 %s건", f"{len(T):,}")

    print(f"\n■ 국면별 거래당 — 신호 **{a.signal}** · {a.mode} · 슬롯 {c.slots} · 보유 {c.hold}분 · {len(T):,}거래 · {c.nq}분위")
    print(f"  국면값은 **전부 진입 시점 후행**이다(미래참조 없음)")
    for nm, arr in REG.items():
        v = arr[T.t.to_numpy()]
        m = np.isfinite(v)
        if m.sum() < 500: continue
        q = pd.qcut(pd.Series(v[m]), c.nq, labels=False, duplicates="drop")
        g = pd.DataFrame({"q": q, "net": T.net.to_numpy()[m]}).groupby("q").net
        mu, n_ = g.mean(), g.size()
        sp = mu.iloc[-1] - mu.iloc[0]
        # 국면 자체의 지속성 — 다음 앵커와의 자기상관(비겹침)
        aa = arr[np.isfinite(arr)]
        ac = np.corrcoef(aa[:-1], aa[1:])[0,1] if len(aa) > 100 else np.nan
        print(f"\n  ▸ {nm}  (국면 자기상관 {ac:+.3f})")
        print("     " + "".join(f"{i:>10d}" for i in mu.index))
        print("     " + "".join(f"{x:>+10.4f}" for x in mu.values)
              + f"   최상-최하 **{sp:+.4f}%p**")
        print("     " + "".join(f"{int(x):>10,}" for x in n_.values))
    # ── 최대통계량 귀무 — **35칸을 뒤진 최고값**이 기준이다(교훈#95) ──
    #   국면 배열을 **원형회전**해 거래와의 대응만 끊는다. 국면 자체의
    #   자기상관 구조는 보존되므로 "국면이 뭉쳐 있어서" 나오는 몫이 제거된다.
    rng = np.random.default_rng(20260902)
    tt = T.t.to_numpy(); net = T.net.to_numpy()
    def best_cell(shift=0):
        b = -np.inf
        for arr in REG.values():
            v = np.roll(arr, shift)[tt]
            m = np.isfinite(v)
            if m.sum() < 500: continue
            try:
                q = pd.qcut(pd.Series(v[m]), c.nq, labels=False, duplicates="drop")
            except ValueError:
                continue
            mu = pd.DataFrame({"q": q, "n": net[m]}).groupby("q").n.mean()
            b = max(b, float(mu.max()))
        return b
    obs = best_cell(0)
    null = np.array([best_cell(int(rng.integers(200, len(grid)-200)))
                     for _ in range(200)])
    print(f"\n■ 최대통계량 — 국면 원형회전 200판 (35칸 중 최고 칸)")
    print(f"  관측 최고 칸 **{obs:+.4f}%** · 귀무 중앙 {np.median(null):+.4f}% "
          f"· 95분위 {np.percentile(null,95):+.4f}% · **p = {(null>=obs).mean():.3f}**")
    print(f"  전체 거래당 {net.mean():+.4f}% · 거래 {len(net):,}")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/f"cfg_{a.signal}_{a.mode}{a.slots}_h{a.hold}.json").write_text(c.dump())
    np.savez_compressed(OUT/"regime.npz", **{k: v for k, v in REG.items()})
    T.to_csv(OUT/f"trades_{a.signal}_{a.mode}{a.slots}_h{a.hold}.csv", index=False)
    log.info("완료 %.1f분 · 저장 %s", (time.time()-t0)/60, OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
