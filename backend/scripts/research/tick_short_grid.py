"""틱 미시구조 **숏 전용** 선별 — 잡음이 급등의 대리변수인가.

## 왜 (2026-08-31)

운동학 z_vel 밴드를 닫았다. 총엣지 +0.040~0.084% 대 왕복 통행료 0.072% —
정보는 있으나 통행료 크기의 물건이었다. 그런데 같은 날 페이퍼 감사에서:

    잡음6 첫 사이클  롱 다리 초과 +0.071%p   (유니버스 중앙과 같음 = 0)
                     숏 다리 초과 +5.226%p   (358종목 중 최하위 2개)

74배 차이다. 그리고 이 값은 밴드가 만든 게 아니다(밴드 총엣지 +0.04%). 그래서
**밴드를 들어내고 전 유니버스를 틱 점수로 순위 매겨 숏만** 친다.

## 반드시 넘어야 하는 대조군

ZORA·ZK 는 둘 다 **먼저 급등한 뒤** 무너졌다. 그러면 잡음 점수가 실은 "최근
급등"의 대리변수일 수 있고, 급등 페이드는 이 트랙이 이미 아는 것이라 새 정보가
아니다. 그래서 격자에 급등(`pump`)을 나란히 넣고 **이중정렬로 증분**을 잰다
(교훈#94 의 모양 — 새 신호는 이미 아는 것을 이겨야 한다).

    noise         뒤집힘율 + 체결간격변동
    pump          최근 수익률                    ← 대조군
    vol · taker · ntr                            ← 다른 축
    noise|pump    급등 상위 5분위 **안에서** 잡음 순위   ← 증분 검정
    pump|noise    잡음 상위 5분위 **안에서** 급등 순위   ← 반대 증분

## 규약

⚠ 방향맞춤 위약(교훈#91·#101) — 같은 블록·같은 종목수를 **무작위로 숏**. 빈도가
  다른 신호끼리는 각자의 위약 대비 초과분으로만 비교한다.
⚠ 회전 위약(교훈#108) — 이동량이 신호 기억(되돌아보기 + 보유)을 넘어야 한다.
⚠ 최대통계량(교훈#95) — 섞은 자료로 **같은 격자를 전부** 다시 뒤진 최고값이 기준.
⚠ 위상(교훈#111) — 비겹침 블록의 시작 위상을 전부 평균한다.
⚠ 숏 수익률 규약(교훈#89) — (진입-청산)/진입. 펀딩은 숏이 받으므로 +f.
⚠ 검정력 — 5.1일뿐이다. 블록 수와 탐지 가능 크기를 **먼저 찍는다**.

사용:
  python3 -m scripts.research.tick_short_grid --smoke
  python3 -m scripts.research.tick_short_grid --reps 400
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

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from sqlalchemy import text                                     # noqa: E402

from app.db.session import engine                               # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
BARS = ROOT / "runs" / "tickbars5m"
OUT = ROOT / "runs" / "research_track" / "tick_short_2026_08_31"
log = logging.getLogger("tickshort")

SCORES = ["noise", "pump", "vol", "taker", "ntr", "noise|pump", "pump|noise"]


@dataclass(frozen=True)
class Cfg:
    bar_min: int = 5
    look_bars: int = 12          # 되돌아보기 60분
    holds: tuple = (12, 24, 48)  # 60 · 120 · 240분
    picks: tuple = (3, 5, 10)
    fee_rt: float = 0.072        # 왕복(메이커 양쪽)
    min_alive: int = 100         # 앵커당 유효 종목 최소
    quint: float = 0.2           # 이중정렬 상위 분위
    max_phase: int = 24
    reps: int = 400
    seed: int = 20260831

    def dump(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


def load(cfg: Cfg):
    fs = sorted(BARS.glob("*.parquet"))
    if len(fs) < 50:
        raise SystemExit(f"특징봉이 {len(fs)}개뿐 — tick_features 를 먼저 돌려라")
    cols = {}
    for f in fs:
        d = pd.read_parquet(f)
        if len(d) < 300:
            continue
        cols[f.stem] = d.set_index("ts_ms")
    step = cfg.bar_min*60*1000
    lo = min(v.index.min() for v in cols.values())
    hi = max(v.index.max() for v in cols.values())
    idx = np.arange(lo, hi+step, step)
    F = {}
    for k in ("cl", "ntr", "qsum", "flip", "dtm", "dts", "tkb"):
        F[k] = pd.DataFrame({s: v[k].reindex(idx) for s, v in cols.items()})
    F["cl"] = F["cl"].ffill()
    return F, list(cols), idx


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--reps", type=int, default=None)
    p.add_argument("--smoke", action="store_true",
                   help="본실행과 같은 경로로 한 칸만")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    cfg = Cfg(**({"reps": a.reps} if a.reps else {}))
    if a.smoke:
        cfg = Cfg(holds=(24,), picks=(3,), reps=40)
    log.info("설정 %s", cfg.dump())
    t0 = time.time()
    F, syms, idx = load(cfg)
    n, m = len(idx), len(syms)
    log.info("판 %s봉 × %d종목 · %s ~ %s · %.1f분", f"{n:,}", m,
             pd.to_datetime(idx[0], unit="ms", utc=True),
             pd.to_datetime(idx[-1], unit="ms", utc=True), (time.time()-t0)/60)

    # ── 펀딩 (숏이 받는다) ────────────────────────────────
    CUM = np.zeros((n, m), np.float32)
    q = text("SELECT symbol, funding_time, funding_rate FROM binance_funding_rate "
             "WHERE funding_time>=:a AND funding_time<:b")
    with engine.connect() as c_:
        c_.execute(text("SET statement_timeout='120s'"))
        rr = c_.execute(q, {"a": pd.to_datetime(idx[0], unit="ms"),
                            "b": pd.to_datetime(idx[-1], unit="ms")}).all()
    col = {s: j for j, s in enumerate(syms)}
    hit = 0
    for s, t_, v in rr:
        j = col.get(s)
        if j is None:
            continue
        pos = int(np.clip(np.searchsorted(idx, int(pd.Timestamp(t_).timestamp()*1000)),
                          0, n-1))
        CUM[pos, j] += float(v)*100.0
        hit += 1
    CUM = np.cumsum(CUM, axis=0)
    log.info("펀딩 %s건 반영 · %.1f분", f"{hit:,}", (time.time()-t0)/60)

    # ── 신호 (되돌아보기 창) ──────────────────────────────
    L = cfg.look_bars
    CL = F["cl"].to_numpy(np.float32)
    ntr = F["ntr"].fillna(0).rolling(L).sum().to_numpy(np.float32)
    flip = F["flip"].fillna(0).rolling(L).sum().to_numpy(np.float32)
    dtm = F["dtm"].rolling(L).mean().to_numpy(np.float32)
    dts = F["dts"].rolling(L).mean().to_numpy(np.float32)
    tkb = F["tkb"].rolling(L).mean().to_numpy(np.float32)
    lr = np.log(np.maximum(CL, 1e-12))
    S = {
        "noise": None,                                    # 아래에서 순위합
        "pump": (CL/np.roll(CL, L, axis=0) - 1.0)*100.0,
        "vol": pd.DataFrame(lr).diff().rolling(L).std().to_numpy(np.float32)*100.0,
        "taker": tkb,
        # ⚠ 미래참조 — 분모를 전 구간 중앙값으로 쓰면 5일 전체를 보고 나서
        #   "이 종목치고 체결이 많은 시각"을 고르게 된다. **후행 창**으로 바꾼다
        #   (하루 288봉, 최소 72봉, 한 봉 밀어 당시점 제외).
        "ntr": ntr/np.maximum(
            F["ntr"].fillna(0).rolling(288, min_periods=72).median()
                    .shift(1).to_numpy(np.float32)*L, 1e-9),
    }
    S["pump"][:L] = np.nan
    BUMP = flip/np.maximum(ntr, 1.0)
    IRR = dts/np.maximum(dtm, 1e-9)
    ALIVE = np.isfinite(CL) & (ntr >= 3*L) & np.isfinite(BUMP) & np.isfinite(IRR)
    log.info("신호 준비 · 살아있는 종목 중앙 %d · %.1f분",
             int(np.median(ALIVE.sum(1))), (time.time()-t0)/60)

    def rank_row(v, ok):
        """행 안에서 큰 값이 1.0 이 되는 백분위. 무효는 nan."""
        r = np.full(v.shape, np.nan)
        for i in range(v.shape[0]):
            j = np.where(ok[i] & np.isfinite(v[i]))[0]
            if len(j) < 2:
                continue
            o = np.argsort(np.argsort(v[i][j]))
            r[i, j] = o/(len(j)-1)
        return r

    RK = {k: rank_row(v, ALIVE) for k, v in S.items() if v is not None}
    RK["noise"] = (rank_row(BUMP, ALIVE) + rank_row(IRR, ALIVE))/2.0
    S["noise"] = RK["noise"]
    # 이중정렬 — 상위 분위 안에서만 다른 축으로 순위
    def conditional(inner, outer):
        gate = RK[outer] >= (1.0 - cfg.quint)
        v = np.where(gate, RK[inner], np.nan)
        return v
    S["noise|pump"] = conditional("noise", "pump")
    S["pump|noise"] = conditional("pump", "noise")

    rng = np.random.default_rng(cfg.seed)
    rows, best = [], None
    MEM = L
    for H in cfg.holds:
        hi_ = n - H
        R = np.full(CL.shape, np.nan, np.float32)     # 롱 관점 수익(%) 펀딩조정
        R[:hi_] = ((CL[H:H+hi_]/CL[:hi_] - 1.0)*100.0
                   - (CUM[H:H+hi_] - CUM[:hi_]))
        base = np.arange(MEM, n - H - 1)
        Ra, AL = R[base], ALIVE[base]
        nb_ = len(base)
        phases = (np.arange(H) if H <= cfg.max_phase
                  else np.unique(np.linspace(0, H-1, cfg.max_phase).astype(int)))
        # 블록 목록 — 모든 칸이 **같은 앵커**를 쓴다
        blocks = []
        for ph in phases:
            kk = [i for i in range(ph, nb_ - H - 1, H)
                  if AL[i].sum() >= cfg.min_alive]
            if kk:
                blocks.append(np.asarray(kk))
        nblk = sum(len(k) for k in blocks)
        sd = float(np.nanstd(Ra))
        log.info("보유 %3d분 — 위상 %d · 블록 %d · 종목수익 SD %.2f%% · "
                 "**탐지가능(t2) %.3f%%p** (숏3 기준)",
                 H*cfg.bar_min, len(blocks), nblk, sd,
                 2*sd/np.sqrt(3)/np.sqrt(max(nblk, 1)))

        for name in SCORES:
            sc = S[name][base]
            for N in cfg.picks:
                def run(Rm, sc_=sc, N_=N):
                    per = []
                    for kk in blocks:
                        v = []
                        for i in kk:
                            ok = np.where(AL[i] & np.isfinite(sc_[i]))[0]
                            if len(ok) < N_:
                                continue
                            pick = ok[np.argsort(-sc_[i][ok])[:N_]]
                            r = Rm[i][pick]
                            r = r[np.isfinite(r)]
                            if len(r):
                                v.append(-float(r.mean()))   # 숏
                        if v:
                            per.append(np.mean(v))
                    return float(np.mean(per)) - cfg.fee_rt if per else np.nan

                def rand(Rm, N_=N):
                    per = []
                    for kk in blocks:
                        v = []
                        for i in kk:
                            ok = np.where(AL[i])[0]
                            if len(ok) < N_:
                                continue
                            r = Rm[i][rng.choice(ok, N_, replace=False)]
                            r = r[np.isfinite(r)]
                            if len(r):
                                v.append(-float(r.mean()))
                        if v:
                            per.append(np.mean(v))
                    return float(np.mean(per)) - cfg.fee_rt if per else np.nan

                obs = run(Ra)
                pl = np.asarray([rand(Ra) for _ in range(min(cfg.reps, 120))])
                pl = pl[np.isfinite(pl)]
                rows.append({"보유분": H*cfg.bar_min, "점수": name, "숏": N,
                             "블록": nblk, "순액": obs,
                             "방향위약": float(np.median(pl)),
                             "초과": obs - float(np.median(pl)),
                             "위약p": float((pl >= obs).mean())})
                log.info("  %-11s 숏%-3d 보유%4d분 → 순 %+.4f · 위약 %+.4f · "
                         "초과 %+.4f · p %.3f · %.1f분", name, N, H*cfg.bar_min,
                         obs, float(np.median(pl)), obs-float(np.median(pl)),
                         float((pl >= obs).mean()), (time.time()-t0)/60)
        # 회전 위약 — 격자 전체를 다시 뒤진 최고값(최대통계량)
        lo_s = max(MEM, H) + 5
        if best is None:
            best = np.full(cfg.reps, -9e9)
        for rep in range(cfg.reps):
            sh = int(rng.integers(lo_s, nb_ - lo_s))
            Rs = np.roll(Ra, sh, axis=0)
            for name in SCORES:
                sc = S[name][base]
                for N in cfg.picks:
                    v = run(Rs, sc, N)
                    if np.isfinite(v):
                        best[rep] = max(best[rep], v)
            if (rep+1) % 50 == 0:
                log.info("    회전 위약 %d/%d · %.1f분", rep+1, cfg.reps,
                         (time.time()-t0)/60)
        del R, Ra

    # 날짜별 — 한 날이 전부 만든 것인지 본다(5일뿐이라 필수)
    day_rows = []
    for H in cfg.holds:
        hi_ = n - H
        R = np.full(CL.shape, np.nan, np.float32)
        R[:hi_] = ((CL[H:H+hi_]/CL[:hi_] - 1.0)*100.0
                   - (CUM[H:H+hi_] - CUM[:hi_]))
        base = np.arange(MEM, n - H - 1)
        Ra, AL = R[base], ALIVE[base]
        nb_ = len(base)
        day = pd.to_datetime(idx[base], unit="ms", utc=True).date
        phases = (np.arange(H) if H <= cfg.max_phase
                  else np.unique(np.linspace(0, H-1, cfg.max_phase).astype(int)))
        for name in SCORES:
            sc = S[name][base]
            for N in cfg.picks:
                acc = {}
                for ph in phases:
                    for i in range(ph, nb_ - H - 1, H):
                        if AL[i].sum() < cfg.min_alive:
                            continue
                        ok = np.where(AL[i] & np.isfinite(sc[i]))[0]
                        if len(ok) < N:
                            continue
                        r = Ra[i][ok[np.argsort(-sc[i][ok])[:N]]]
                        r = r[np.isfinite(r)]
                        if len(r):
                            acc.setdefault(day[i], []).append(-float(r.mean()))
                for d_, v in acc.items():
                    day_rows.append({"보유분": H*cfg.bar_min, "점수": name,
                                     "숏": N, "날짜": str(d_), "블록": len(v),
                                     "순액": float(np.mean(v)) - cfg.fee_rt})
        del R, Ra
    D = pd.DataFrame(day_rows)
    T = pd.DataFrame(rows).sort_values("순액", ascending=False)
    print(f"\n■ 틱 숏 전용 선별 — 종목 {m} · 왕복 {cfg.fee_rt}% · 위상 평균 · "
          f"방향맞춤 위약")
    print(T.to_string(index=False, float_format=lambda z: f"{z:+.4f}"))
    obs = float(T.순액.max())
    pm = float((best >= obs).mean())
    print(f"\n■ 회전 위약 최대통계량 ({cfg.reps}회 · {len(T)}칸)")
    print(f"  관측 최대 {obs:+.4f}% · 귀무 중앙 {np.median(best):+.4f}% "
          f"· 95분위 {np.quantile(best,.95):+.4f}%  **p = {pm:.3f}**")
    print("\n■ 증분 — 잡음이 급등을 이기는가")
    for H in sorted(T.보유분.unique()):
        s = T[T.보유분 == H].set_index(["점수", "숏"]).순액
        for N in cfg.picks:
            try:
                print(f"  보유{H}분 숏{N}  급등 {s[('pump',N)]:+.4f} · "
                      f"잡음 {s[('noise',N)]:+.4f} · "
                      f"급등안의잡음 {s[('noise|pump',N)]:+.4f} · "
                      f"잡음안의급등 {s[('pump|noise',N)]:+.4f}")
            except KeyError:
                pass
    print("\n■ 날짜별 — 한 날이 전부 만들었는가")
    for (H, name, N), g in D.groupby(["보유분", "점수", "숏"]):
        if T[(T.보유분 == H) & (T.점수 == name) & (T.숏 == N)].순액.iloc[0] <= 0:
            continue
        g = g.sort_values("날짜")
        print(f"  보유{H}분 {name:11s} 숏{N:<3d} " +
              " ".join(f"{r.날짜[5:]} {r.순액:+.3f}" for r in g.itertuples()) +
              f"   양수 {int((g.순액>0).sum())}/{len(g)}")
    OUT.mkdir(parents=True, exist_ok=True)
    T.to_csv(OUT / "grid.csv", index=False)
    D.to_csv(OUT / "by_day.csv", index=False)
    (OUT / "cfg.json").write_text(cfg.dump())
    (OUT / "null.json").write_text(json.dumps(
        {"obs": obs, "p": pm, "null_median": float(np.median(best))},
        ensure_ascii=False, indent=1))
    log.info("저장 %s · %.1f분", OUT, (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
