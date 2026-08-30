"""살아남은 게이트를 **거래 가능한 형태**로 잰다.

## 지금까지 (2026-08-31 02:30)

    신호   1시간 최대 급락 롱 · 최대 급등 숏 (횡단면 상·하위 20%)
    진입   신호 5분 뒤 · 보유 24h · 펀딩 포함
    게이트 최근 13블록 평균 양수일 때만 (여유 2블록)

    다중검정 p 0.006 · 전진 선택 p 0.004 · 변동성 정규화 p 0.022

⚠ 그 수치는 **상·하위 20%(각 48종목)에 단위 자본**을 넣은 스프레드의 단순
  합이다. 실제로는 슬롯이 제한되고 복리가 돌고 편입이 매일 바뀐다.

## 무엇을 재나

    ① 슬롯 N=3·5·10·20   양쪽 각 N종목만. 적을수록 신호 극단만 잡는다
    ② 복리 자본곡선       총손익 · 최대낙폭 · 월별
    ③ 회전율              하루에 몇 종목이 바뀌나 = 실행 부담
    ④ 마찰 민감도         왕복 0.036/0.072/0.144% 에서 각각
    ⑤ 위약 대조           같은 슬롯·같은 게이트로 회전 위약

⚠ 슬롯을 줄이면 **극단만 잡게 되고** 극단은 호가 튐이 심하다. N 이 작을수록
  좋아 보이면 그건 신호가 아니라 튐일 수 있다 — 진입 지연을 함께 본다.

사용:
  python3 -m scripts.research.persist_realize --reps 300
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
CACHE = ROOT / "runs" / "bars5m"
OUT = ROOT / "runs" / "research_track" / "night_2026_08_31"
log = logging.getLogger("preal")

BAR, ANCH = 5, 12
SIG_BARS, HOLD_H = 12, 24
K_GATE, LAG_GATE = 13, 2
SLOTS = (3, 5, 10, 20, 48)         # 48 = 상·하위 20% 근사(240종목)
DELAYS = (1, 2, 6)                 # 5분 · 10분 · 30분
FEES = (0.036, 0.072, 0.144)       # 왕복 한 다리 기준


@dataclass(frozen=True)
class Cfg:
    min_syms: int = 40
    min_bars_in_5: float = 3.0
    min_per_side: int = 30
    reps: int = 300
    seed: int = 20260831


def load(files):
    cl, nb = {}, {}
    for f in files:
        d = pd.read_parquet(f)
        if len(d) < 5_000:
            continue
        ts = pd.to_datetime(d.ts, utc=True)
        cl[f.stem] = pd.Series(d.c.to_numpy(np.float32), index=ts)
        nb[f.stem] = pd.Series(d.n.to_numpy(np.float32), index=ts)
    idx = pd.date_range(min(v.index.min() for v in cl.values()),
                        max(v.index.max() for v in cl.values()),
                        freq=f"{BAR}min", tz="UTC")
    return (pd.DataFrame(cl).reindex(idx).ffill(),
            pd.DataFrame(nb).reindex(idx).fillna(0.0), idx)


def funding_cum(syms, idx):
    q = text("SELECT funding_time, funding_rate FROM binance_funding_rate "
             "WHERE symbol=:s AND funding_time >= :a AND funding_time < :b "
             "ORDER BY funding_time")
    a = idx.min().tz_convert(None); b = idx.max().tz_convert(None)
    cum = np.zeros((len(idx), len(syms)), np.float32)
    with engine.connect() as c:
        c.execute(text("SET statement_timeout='240s'"))
        for j, s in enumerate(syms):
            r = c.execute(q, {"s": s, "a": a, "b": b}).all()
            if not r:
                continue
            t = pd.to_datetime([x[0] for x in r], utc=True)
            v = np.asarray([float(x[1]) for x in r], np.float64) * 100.0
            pos = np.clip(idx.searchsorted(t, side="left"), 0, len(idx)-1)
            acc = np.zeros(len(idx)); np.add.at(acc, pos, v)
            cum[:, j] = np.cumsum(acc).astype(np.float32)
    return cum


def block_series(X, R, N, fee):
    """블록마다 상·하위 N종목만. 한 다리 마찰 `fee`. 편입 목록도 돌려준다."""
    out, picks = [], []
    for i in range(X.shape[0]):
        x, r = X[i], R[i]
        m = np.isfinite(x) & np.isfinite(r)
        if m.sum() < 2 * N + 10:
            out.append(np.nan); picks.append((frozenset(), frozenset()))
            continue
        ii = np.where(m)[0]
        o = ii[np.argsort(x[ii])]
        lo_, hi_ = o[:N], o[-N:]            # x 큰 쪽 = 롱
        v = float(r[hi_].mean() - r[lo_].mean()) - 2 * fee
        out.append(v); picks.append((frozenset(hi_.tolist()),
                                     frozenset(lo_.tolist())))
    return np.asarray(out), picks


def gated(v, k=K_GATE, lag=LAG_GATE):
    prev = pd.Series(v).rolling(k).mean().shift(lag).to_numpy()
    return np.isfinite(prev) & (prev > 0) & np.isfinite(v)


def curve(v, mask):
    """복리 — 블록마다 자본 전액을 스프레드에 넣는다(롱 50% · 숏 50%)."""
    eq, path = 1.0, []
    for i in range(len(v)):
        if mask[i] and np.isfinite(v[i]):
            eq *= (1.0 + v[i] / 100.0)
        path.append(eq)
    p = np.asarray(path)
    dd = float((p / np.maximum.accumulate(p) - 1.0).min() * 100.0)
    return (eq - 1.0) * 100.0, dd


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--smoke", type=int, default=0)
    p.add_argument("--reps", type=int, default=None)
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    cfg = Cfg(**({"reps": a.reps} if a.reps is not None else {}))
    fs = sorted(CACHE.glob("*.parquet"))
    if a.smoke:
        fs = fs[:a.smoke]
    t0 = time.time()
    CL, NB, idx = load(fs)
    syms = list(CL.columns); n = len(CL)
    CUM = funding_cum(syms, idx)
    live = (NB.rolling(12).median().shift(1) >= cfg.min_bars_in_5).to_numpy()
    C = CL.to_numpy(np.float32)
    r = np.full(C.shape, np.nan, np.float32)
    r[SIG_BARS:] = (C[SIG_BARS:] / C[:-SIG_BARS] - 1.0) * 100.0
    X = np.where(live, -r, np.nan)
    warm = SIG_BARS + 12
    kk = HOLD_H * 12
    anc = np.arange(warm, n - kk - max(DELAYS) - 1)
    anc = anc[anc % ANCH == 0]
    pos = np.arange(0, len(anc) - HOLD_H - 1, HOLD_H)
    XA = X[anc][pos]
    RA = {}
    for d in DELAYS:
        f = np.full(C.shape, np.nan, np.float32)
        hi_ = n - kk - d
        f[:hi_] = ((C[d+kk:d+kk+hi_] / C[d:d+hi_] - 1.0) * 100.0
                   - (CUM[d+kk:d+kk+hi_] - CUM[d:d+hi_]))
        RA[d] = f[anc][pos]
    ts = idx[anc[pos]]
    log.info("블록 %d개 · %s ~ %s · 종목 %d · %.1f분", len(pos),
             ts.min().date(), ts.max().date(), len(syms), (time.time()-t0)/60)

    rows = []
    BASE = {}
    for N in SLOTS:
        for d in DELAYS:
            for fee in FEES:
                v, picks = block_series(XA, RA[d], N, fee)
                g = gated(v)
                al = np.isfinite(v)
                tg, ddg = curve(v, g)
                ta, dda = curve(v, al)
                # 회전율 — 블록마다 편입이 얼마나 바뀌나
                ch = [len(picks[i][0] ^ picks[i-1][0]) / (2*N)
                      for i in range(1, len(picks)) if g[i]]
                h = len(v) // 2
                rows.append({
                    "슬롯": N, "지연": d, "마찰": fee,
                    "게이트복리": tg, "게이트낙폭": ddg,
                    "항상복리": ta, "항상낙폭": dda,
                    "거래블록": int(g.sum()),
                    "게이트평균": float(np.nanmean(v[g])),
                    "항상평균": float(np.nanmean(v[al])),
                    "전반": float(np.nanmean(v[:h][g[:h]])),
                    "후반": float(np.nanmean(v[h:][g[h:]])),
                    "회전율": float(np.mean(ch)) if ch else np.nan})
                if d == 1 and fee == 0.036:      # 왕복 0.072% = 지정가 양다리
                    BASE[N] = (v, g)
    R = pd.DataFrame(rows)
    print(f"\n■ 슬롯 실현 (신호 1h 되돌림 · 보유{HOLD_H}h · 게이트 k{K_GATE} 여유{LAG_GATE})")
    print(R[R.마찰 == 0.072].sort_values(["슬롯", "지연"]).to_string(
        index=False, float_format=lambda z: f"{z:+.3f}"))
    print("\n■ 마찰 민감도 (지연 1봉)")
    print(R[R.지연 == 1].pivot_table(index="슬롯", columns="마찰",
                                     values="게이트복리")
          .to_string(float_format=lambda z: f"{z:+.1f}"))

    rng = np.random.default_rng(cfg.seed)
    na = len(anc)
    mem = HOLD_H * 2 + SIG_BARS
    # ⚠ **게이트와 항상거래를 둘 다** 위약에 건다. 슬롯10 에서는 항상거래가
    #   게이트보다 좋았다(+284 대 +212) — 발견이 게이트가 아니라 **슬롯 집중**
    #   자체일 수 있는데, 그건 아직 위약으로 재본 적이 없다.
    print(f"\n■ 회전 위약 ({cfg.reps}회 · 슬롯별 · 지연1봉 · 한다리 0.036%)")
    pr = []
    for N in SLOTS:
        vb, gb = BASE[N]
        obs = curve(vb, gb)[0]
        obsA = curve(vb, np.isfinite(vb))[0]
        null = np.empty(cfg.reps); nullA = np.empty(cfg.reps)
        for i in range(cfg.reps):
            sh = int(rng.integers(mem, na - mem))
            f = np.full(C.shape, np.nan, np.float32)
            hi_ = n - kk - 1
            f[:hi_] = ((C[1+kk:1+kk+hi_] / C[1:1+hi_] - 1.0) * 100.0
                       - (CUM[1+kk:1+kk+hi_] - CUM[1:1+hi_]))
            Rr = np.roll(f[anc][pos], sh % len(pos), axis=0)
            vv, _ = block_series(XA, Rr, N, 0.036)
            null[i] = curve(vv, gated(vv))[0]
            nullA[i] = curve(vv, np.isfinite(vv))[0]
        pr.append({"슬롯": N, "게이트관측": obs,
                   "게이트귀무중앙": float(np.median(null)),
                   "게이트p": float((null >= obs).mean()),
                   "항상관측": obsA,
                   "항상귀무중앙": float(np.median(nullA)),
                   "항상귀무95": float(np.quantile(nullA, .95)),
                   "항상p": float((nullA >= obsA).mean())})
        log.info("  슬롯 %d 완료 · %.1f분", N, (time.time()-t0)/60)
    PR = pd.DataFrame(pr)
    print(PR.to_string(index=False, float_format=lambda z: f"{z:+.3f}"))
    OUT.mkdir(parents=True, exist_ok=True)
    R.to_csv(OUT / "persist_realize.csv", index=False)
    PR.to_csv(OUT / "persist_realize_null.csv", index=False)
    log.info("저장 · %.1f분", (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
