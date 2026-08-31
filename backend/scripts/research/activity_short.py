"""활동량 **숏 전용** — 2년 5분봉. 틱 5일이 못 하는 판정을 여기서 한다.

## 왜 (2026-08-31)

운동학 z_vel 밴드를 닫고(총엣지 +0.04~0.08% 대 통행료 0.072%) 틱 미시구조로
옮겼다. 틱 격자(5.1일 · 359종목)가 준 것:

    noise (뒤집힘율+체결간격변동)  초과 -0.009  p 0.575   ← 값어치 0
    taker (테이커 불균형)          초과 -0.001  p 0.550   ← 값어치 0
    vol · pump · vlm               완전한 4일에서 t +3.0~3.5, 6일 전부면 0 이하

**틱이 있어야만 재는 두 축이 정확히 0이었다.** 그러니 5일에 갇힐 이유가 없다.
살아남은 셋은 전부 가격·거래대금이라 **2년 5분봉이면 된다**(교훈#109).

## 무엇이 달라지나

    독립 단위   틱: 4~6일  →  여기: **730일**
    판정 주축   블록 t 가 아니라 **날짜 군집 t**. 하루 안 블록은 얽혀 있고
                위상끼리도 겹친다 — 블록 1,411개는 표본이 아니었다

## 보유 시간 (2026-08-31 개정)

2시간·4시간에서 두 창 모두 부정이었다(초과 +0.018 / +0.025 대 통행료 0.072).
그런데 같은 날 운동학 밴드에서 **총엣지가 보유에 따라 자란다**는 것을 쟀다
(2시간 +0.0402 → 8시간 +0.0842, 2.1배). 통행료는 고정이다. 그래서 보유를
**1~7일**로 옮겨 통행료가 움직임 대비 무의미해지는 구간을 본다.

⚠ 보유가 길면 펀딩 정산이 여러 번 낀다(하루 3회). 이미 종목별 `r - f` 로
  반영돼 있고 숏은 부호를 뒤집는다. **급등 종목의 펀딩 부호를 따로 확인하라** —
  이 트랙엔 "급등 페이드는 붐비는 거래"라는 관측이 있다.
⚠ 보유 1일이면 위상이 288가지다. 24개만 고르게 뽑는다(편향 없는 부분추출).

⚠ 이 트랙은 "1시간 횡단면 되돌림"을 위상 인공물로 닫은 적이 있다(위상평균
  -0.087 · p 0.780). 그건 **보유 24시간 · 롱숏 양다리**였다. 여기는 **보유
  1~4시간 · 숏 전용**이라 다른 칸이다. 같은 결과가 나오면 그때 닫는다.
⚠ 방향맞춤 위약(교훈#91·#101) — 같은 블록·같은 수를 무작위로 숏.
⚠ 거울 대조(교훈#91) — 같은 규칙을 **롱으로** 돌린다. 둘 다 벌면 규칙이 아니라
  국면이다.
⚠ 최대통계량(교훈#95) — 섞은 자료로 격자 전체를 다시 뒤진 최고값이 기준선.
⚠ 위상(교훈#111) — 비겹침 블록의 시작 위상을 전부 평균.
⚠ 숏 규약(교훈#89) — (진입-청산)/진입. 펀딩은 숏이 받는다.

사용:
  python3 -m scripts.research.activity_short --smoke
  python3 -m scripts.research.activity_short --reps 400
  python3 -m scripts.research.activity_short --cache runs/bars5m_oos --reps 400
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

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from sqlalchemy import text                                     # noqa: E402

from app.db.session import engine                               # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "runs" / "research_track" / "activity_short_2026_08_31"
log = logging.getLogger("actshort")

FEATS = ["pump", "vol", "rng", "vlm", "vol+pump"]


@dataclass(frozen=True)
class Cfg:
    bar_min: int = 5
    look: int = 12               # 되돌아보기 60분
    med_win: int = 288           # 거래대금 후행 중앙값 창 (하루)
    holds: tuple = (288, 576, 864, 1440, 2016)   # 1 · 2 · 3 · 5 · 7일
    picks: tuple = (3, 5, 10)
    fee_rt: float = 0.072
    min_alive: int = 60
    min_bars: float = 3.0
    max_phase: int = 24
    reps: int = 400
    seed: int = 20260831

    def dump(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cache", default="runs/bars5m")
    p.add_argument("--reps", type=int, default=None)
    p.add_argument("--smoke", action="store_true",
                   help="본실행과 같은 경로로 한 보유·한 종목수만")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    cfg = Cfg(**({"reps": a.reps} if a.reps else {}))
    if a.smoke:
        cfg = Cfg(holds=(288,), picks=(3,), reps=40)
    log.info("설정 %s · 기질 %s", cfg.dump(), a.cache)
    t0 = time.time()

    C_, H_, L_, V_, N_ = {}, {}, {}, {}, {}
    for f in sorted((ROOT/a.cache).glob("*.parquet")):
        d = pd.read_parquet(f, columns=["ts", "h", "l", "c", "v", "n"])
        if len(d) < 5_000:
            continue
        ts = pd.to_datetime(d.ts, utc=True)
        C_[f.stem] = pd.Series(d.c.to_numpy(np.float32), index=ts)
        H_[f.stem] = pd.Series(d.h.to_numpy(np.float32), index=ts)
        L_[f.stem] = pd.Series(d.l.to_numpy(np.float32), index=ts)
        V_[f.stem] = pd.Series(d.v.to_numpy(np.float32), index=ts)
        N_[f.stem] = pd.Series(d.n.to_numpy(np.float32), index=ts)
    idx = pd.date_range(min(v.index.min() for v in C_.values()),
                        max(v.index.max() for v in C_.values()),
                        freq=f"{cfg.bar_min}min", tz="UTC")
    CL = pd.DataFrame(C_).reindex(idx).ffill()
    HI = pd.DataFrame(H_).reindex(idx)
    LO = pd.DataFrame(L_).reindex(idx)
    VO = pd.DataFrame(V_).reindex(idx).fillna(0.0)
    NB = pd.DataFrame(N_).reindex(idx).fillna(0.0)
    syms, n, m = list(CL.columns), len(idx), len(CL.columns)
    log.info("판 %s봉 × %d종목 · %s ~ %s · %.1f분", f"{n:,}", m,
             idx.min().date(), idx.max().date(), (time.time()-t0)/60)

    # ── 펀딩 ─────────────────────────────────────────────
    CUM = np.zeros((n, m), np.float32)
    with engine.connect() as c_:
        c_.execute(text("SET statement_timeout='240s'"))
        q = text("SELECT funding_time, funding_rate FROM binance_funding_rate "
                 "WHERE symbol=:s AND funding_time>=:a AND funding_time<:b")
        for j, s in enumerate(syms):
            r = c_.execute(q, {"s": s, "a": idx.min().tz_convert(None),
                               "b": idx.max().tz_convert(None)}).all()
            if not r:
                continue
            t_ = pd.to_datetime([x[0] for x in r], utc=True)
            v = np.asarray([float(x[1]) for x in r])*100.0
            pos = np.clip(idx.searchsorted(t_, side="left"), 0, n-1)
            acc = np.zeros(n); np.add.at(acc, pos, v)
            CUM[:, j] = np.cumsum(acc).astype(np.float32)
    log.info("펀딩 적재 · %.1f분", (time.time()-t0)/60)

    # ── 특징 ─────────────────────────────────────────────
    L = cfg.look
    Cn = CL.to_numpy(np.float32)
    live = (NB.rolling(12).median().shift(1) >= cfg.min_bars).to_numpy()
    lr = np.log(np.maximum(Cn, 1e-12))
    S = {}
    S["pump"] = (Cn/np.roll(Cn, L, axis=0) - 1.0)*100.0
    S["vol"] = (pd.DataFrame(lr).diff().rolling(L).std().to_numpy(np.float32)
                * 100.0)
    S["rng"] = (np.log(np.maximum(HI.to_numpy(np.float32), 1e-12))
                - np.log(np.maximum(LO.to_numpy(np.float32), 1e-12)))
    S["rng"] = pd.DataFrame(S["rng"]).rolling(L).mean().to_numpy(np.float32)*100.0
    # ⚠ 미래참조 방지 — 분모는 **후행** 중앙값이고 한 봉 민다(틱 격자에서 이
    #   자리를 전 구간 중앙값으로 썼다가 값이 3배 부풀었다)
    vsum = VO.rolling(L).sum().to_numpy(np.float32)
    vmed = (VO.rolling(cfg.med_win, min_periods=cfg.med_win//4).median()
              .shift(1).to_numpy(np.float32) * L)
    S["vlm"] = vsum/np.maximum(vmed, 1e-9)
    for k in ("pump", "vol", "rng", "vlm"):
        S[k][:max(L, cfg.med_win)] = np.nan
    del HI, LO, VO, NB, C_, H_, L_, V_, N_

    ALIVE = live & np.isfinite(Cn) & np.isfinite(S["pump"]) & np.isfinite(S["vol"])

    def rank_row(v):
        """행 안 백분위(큰 값이 1.0). ⚠ 행 단위 파이썬 반복은 21만 행에서
        몇 시간이다 — 두 번 argsort 로 통째 처리한다."""
        x = np.where(ALIVE & np.isfinite(v), v, np.nan)
        o = np.argsort(np.where(np.isnan(x), np.inf, x), axis=1)
        r = np.empty(o.shape, np.int32)
        np.put_along_axis(r, o, np.arange(x.shape[1], dtype=np.int32)[None, :],
                          axis=1)
        cnt = (~np.isnan(x)).sum(1, keepdims=True)
        return np.where(np.isnan(x), np.nan,
                        r/np.maximum(cnt-1, 1)).astype(np.float32)
    S["vol+pump"] = (rank_row(S["vol"]) + rank_row(S["pump"]))/2.0
    log.info("특징 준비 · 살아있는 종목 중앙 %d · %.1f분",
             int(np.median(ALIVE.sum(1))), (time.time()-t0)/60)

    rng = np.random.default_rng(cfg.seed)
    rows, best = [], np.full(cfg.reps, -9e9)
    day_rows = []
    for H in cfg.holds:
        hi_ = n - H
        R = np.full(Cn.shape, np.nan, np.float32)
        R[:hi_] = ((Cn[H:H+hi_]/Cn[:hi_] - 1.0)*100.0
                   - (CUM[H:H+hi_] - CUM[:hi_]))
        base = np.arange(max(L, cfg.med_win), n - H - 1)
        Ra = R[base]; AL = ALIVE[base]; nb_ = len(base)
        day = pd.Series(pd.to_datetime(idx[base]).date)
        ok_row = AL.sum(1) >= cfg.min_alive
        phases = (np.arange(H) if H <= cfg.max_phase
                  else np.unique(np.linspace(0, H-1, cfg.max_phase).astype(int)))
        blocks = []
        for ph in phases:
            kk = np.arange(ph, nb_ - H - 1, H)
            kk = kk[ok_row[kk]]
            if len(kk):
                blocks.append(kk)
        nblk = sum(len(k) for k in blocks)
        log.info("보유 %3d분 — 위상 %d · 블록 %s · 날짜 %d · %.1f분",
                 H*cfg.bar_min, len(blocks), f"{nblk:,}", day.nunique(),
                 (time.time()-t0)/60)

        def stat(pick, sh=0):
            """pick: (nb_, N) 색인. sh 만큼 **수익만** 돌린다(회전 위약)."""
            per = []
            for kk in blocks:
                src = (kk - sh) % nb_
                g = np.take_along_axis(Ra[src], pick[kk], axis=1)
                with np.errstate(invalid="ignore"):
                    v = -np.nanmean(g, axis=1)
                v = v[np.isfinite(v)]
                if len(v):
                    per.append(v.mean())
            return float(np.mean(per)) - cfg.fee_rt if per else np.nan

        def daily(pick):
            acc = {}
            for kk in blocks:
                g = np.take_along_axis(Ra[kk], pick[kk], axis=1)
                with np.errstate(invalid="ignore"):
                    v = -np.nanmean(g, axis=1)
                for d_, x in zip(day.to_numpy()[kk], v):
                    if np.isfinite(x):
                        acc.setdefault(d_, []).append(x)
            return pd.Series({d_: np.mean(x) - cfg.fee_rt
                              for d_, x in acc.items()}).sort_index()

        PICKS = {}
        for name in FEATS:
            sc = np.where(AL & np.isfinite(S[name][base]), S[name][base], -np.inf)
            order = np.argsort(-sc, axis=1)
            for N in cfg.picks:
                PICKS[(name, N)] = order[:, :N].astype(np.int32)
        def rand_pick(N):
            """살아있는 것 중 무작위 N — **통째로** 뽑는다. 행마다
            rng.choice 하면 21만 행 × 60회 = 1,300만 호출이라 못 끝난다."""
            rs = np.where(AL, rng.random(AL.shape).astype(np.float32),
                          -np.float32(np.inf))
            return np.argsort(-rs, axis=1)[:, :N].astype(np.int32)

        for name in FEATS:
            for N in cfg.picks:
                pick = PICKS[(name, N)]
                obs = stat(pick)
                d_ = daily(pick)
                t_ = float(d_.mean()/(d_.std(ddof=1)/np.sqrt(len(d_))))
                # 방향맞춤 위약 — 살아있는 것 중 무작위 N
                pl = np.asarray([stat(rand_pick(N))
                                 for _ in range(min(cfg.reps, 60))])
                pl = pl[np.isfinite(pl)]
                # 거울 — 같은 규칙을 롱으로
                mir = -(stat(pick) + cfg.fee_rt) - cfg.fee_rt
                rows.append({"보유분": H*cfg.bar_min, "특징": name, "숏": N,
                             "블록": nblk, "날짜": len(d_), "순액": obs,
                             "날짜t": t_, "양수일%": float(100*(d_ > 0).mean()),
                             "방향위약": float(np.median(pl)),
                             "초과": obs - float(np.median(pl)),
                             "거울(롱)": mir})
                for k_, v_ in d_.items():
                    day_rows.append({"보유분": H*cfg.bar_min, "특징": name,
                                     "숏": N, "날짜": str(k_), "순액": float(v_)})
                log.info("  %-9s 숏%-3d 보유%4d분 → 순 %+.4f · 날짜t %+.2f · "
                         "양수일 %.0f%% · 위약 %+.4f · 초과 %+.4f · %.1f분",
                         name, N, H*cfg.bar_min, obs, t_,
                         100*(d_ > 0).mean(), float(np.median(pl)),
                         obs-float(np.median(pl)), (time.time()-t0)/60)
        # 회전 위약 — 격자 전체 다시 뒤진 최고값
        lo_s = max(L, cfg.med_win, H) + 10
        for rep in range(cfg.reps):
            sh = int(rng.integers(lo_s, nb_ - lo_s))
            for name in FEATS:
                for N in cfg.picks:
                    v = stat(PICKS[(name, N)], sh)
                    if np.isfinite(v):
                        best[rep] = max(best[rep], v)
        log.info("  회전 위약 %d회 완료 · %.1f분", cfg.reps, (time.time()-t0)/60)
        del R, Ra

    T = pd.DataFrame(rows).sort_values("순액", ascending=False)
    print(f"\n■ 활동량 숏 전용 — 종목 {m} · 왕복 {cfg.fee_rt}% · 위상 평균 "
          f"· **날짜 군집 t**")
    print(T.to_string(index=False, float_format=lambda z: f"{z:+.4f}"))
    obs = float(T.순액.max())
    pm = float((best >= obs).mean())
    print(f"\n■ 회전 위약 최대통계량 ({cfg.reps}회 · {len(T)}칸)")
    print(f"  관측 최대 {obs:+.4f}% · 귀무 중앙 {np.median(best):+.4f}% "
          f"· 95분위 {np.quantile(best,.95):+.4f}%  **p = {pm:.3f}**")
    OUT.mkdir(parents=True, exist_ok=True)
    tag = "oos" if "oos" in a.cache else "is"
    T.to_csv(OUT / f"grid_{tag}.csv", index=False)
    pd.DataFrame(day_rows).to_csv(OUT / f"by_day_{tag}.csv", index=False)
    (OUT / f"cfg_{tag}.json").write_text(cfg.dump())
    log.info("저장 %s · %.1f분", OUT, (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
