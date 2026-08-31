"""세션 이월 — **4년 합본**으로 미리 고정한 칸만 잰다.

## 왜 (2026-08-31)

두 창 격자(108칸)가 창을 건너 살아남았다. 오늘 닫은 축들엔 없던 성질이다:

    108칸 짝지은 상관   일평균 +0.475 · 초과 +0.681 · 날짜t +0.623
    부호일치            63.9 ~ 73.1%  (우연 50%)
    집중도 단조         상위롱 3 > 5 > 10 이 **두 창 모두**

그런데 날짜 t 가 창별로 1.87 / 0.89 라 각각으로는 2를 못 넘는다. 일 SD 가 커서
샤프가 1.2 수준이고, 그러면 t 2 에 **약 4년**이 필요하다 — 창을 나눠 보면
원리적으로 못 넘는다. 그래서 합쳐서 한 번에 잰다.

⚠ 칸은 **이 파일에 박아 미리 고정한다**. 격자를 다시 뒤지면 최대통계량 보정이
  또 필요하고, 그건 이미 두 창에서 했다. 여기서는 **선언된 칸만** 잰다.
⚠ 미주 13-17 UTC 좁힌 판본은 활동 곡선(거래대금 13시 5.23 · 14시 5.76 ·
  15시 5.63 · 16시 5.43 · 17시 4.50)에서 유도했다. **전략 결과를 보고 정한 게
  아니다** — 지형을 그린 시점에 선언했다.
⚠ 종목 수가 다르다(밖 125 · 본 240). 상위 3개의 극단성이 다르므로 합본에서는
  **백분위 기준 선별**도 같이 잰다(교훈#110).
⚠ 분기별로 쪼개 감쇠를 본다. 뒤로 갈수록 죽으면 알파 소멸이다.

사용:
  python3 -m scripts.research.session_combined
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
OUT = ROOT / "runs" / "research_track" / "session_2026_08_31"
log = logging.getLogger("sesscomb")

# 구획 — 기본과 **좁힌 미주** 두 벌
SESS_A = {"아시아": (0, 8), "유럽": (8, 13), "미주": (13, 21), "야간": (21, 24)}
SESS_B = {"아시아": (0, 8), "유럽": (8, 13), "미주": (13, 17), "야간": (21, 24)}

# ⚠ **미리 고정한 칸**. 두 창 격자에서 살아남은 것들만. 여기서 더 뒤지지 않는다.
CELLS = [("아시아", "미주", 3, "추세스프레드"),
         ("아시아", "미주", 5, "추세스프레드"),
         ("아시아", "미주", 3, "상위롱"),
         ("아시아", "미주", 5, "상위롱"),
         ("유럽", "미주", 3, "추세스프레드"),
         ("아시아", "미주", 3, "하위숏")]


@dataclass(frozen=True)
class Cfg:
    fee_rt: float = 0.072
    min_alive: int = 40
    min_cover: float = 90.0
    reps: int = 400
    seed: int = 20260831

    def dump(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


def sess_returns(caches, sess, cfg: Cfg):
    """(날짜 × 종목) 세션별 수익률. 여러 캐시를 날짜축으로 잇는다."""
    frames = {nm: [] for nm in sess}
    for cache in caches:
        per = {}
        for f in sorted((ROOT/cache).glob("*.parquet")):
            d = pd.read_parquet(f, columns=["ts", "c"])
            if len(d) < 5_000:
                continue
            ts = pd.to_datetime(d.ts, utc=True)
            d = d.assign(ts=ts, date=ts.dt.normalize(), hour=ts.dt.hour)
            lab = pd.Series("", index=d.index, dtype=object)
            for nm, (a_, b_) in sess.items():
                lab[(d.hour >= a_) & (d.hour < b_)] = nm
            d["sess"] = lab
            d = d[d.sess != ""]
            g = d.groupby(["date", "sess"], sort=False)
            r = pd.DataFrame({"first": g.c.first(), "last": g.c.last(),
                              "bars": g.size()}).reset_index()
            full = {nm: (b_-a_)*12 for nm, (a_, b_) in sess.items()}
            r = r[100.0*r.bars/r.sess.map(full) >= cfg.min_cover]
            r["ret"] = (r["last"]/r["first"] - 1.0)*100.0
            per[f.stem] = r
        for nm in sess:
            frames[nm].append(pd.DataFrame(
                {s: v[v.sess == nm].set_index("date").ret for s, v in per.items()}))
    RET = {}
    for nm in sess:
        x = pd.concat(frames[nm], axis=0)
        # ⚠ 두 캐시가 겹치는 날짜가 있으면 **뒤엣것 우선**(더 최신 적재)
        x = x[~x.index.duplicated(keep="last")].sort_index()
        RET[nm] = x
    syms = sorted(set().union(*[set(v.columns) for v in RET.values()]))
    dates = sorted(set().union(*[set(v.index) for v in RET.values()]))
    return {k: v.reindex(index=dates, columns=syms) for k, v in RET.items()}, \
        dates, syms


def leg_daily(sig, ret, N, leg, cfg, pct=False, nalive=None):
    nd = len(sig)
    out = np.full(nd, np.nan)
    for i in range(nd):
        ok = np.where(np.isfinite(sig[i]) & np.isfinite(ret[i]))[0]
        if len(ok) < cfg.min_alive:
            continue
        k = max(1, int(round(len(ok)*N/240.0))) if pct else N
        if len(ok) < 2*k:
            continue
        o = ok[np.argsort(-sig[i][ok])]
        h, l = float(ret[i][o[:k]].mean()), float(ret[i][o[-k:]].mean())
        v = {"상위롱": h, "상위숏": -h, "하위롱": l, "하위숏": -l,
             "추세스프레드": (h-l)/2.0, "반전스프레드": (l-h)/2.0}[leg]
        out[i] = v - cfg.fee_rt
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--reps", type=int, default=400)
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    cfg = Cfg(reps=a.reps)
    t0 = time.time()
    caches = ["runs/bars5m_oos", "runs/bars5m"]
    rows = []
    for tag, sess in (("기본 미주13-21", SESS_A), ("좁힌 미주13-17", SESS_B)):
        RET, dates, syms = sess_returns(caches, sess, cfg)
        di = pd.DatetimeIndex(dates)
        log.info("[%s] 날짜 %d (%s ~ %s) · 종목 %d · %.1f분", tag, len(dates),
                 di.min().date(), di.max().date(), len(syms), (time.time()-t0)/60)
        # 펀딩
        FUND = {nm: pd.DataFrame(0.0, index=di, columns=syms) for nm in sess}
        with engine.connect() as c_:
            c_.execute(text("SET statement_timeout='300s'"))
            rr = c_.execute(text(
                "SELECT symbol, funding_time, funding_rate FROM binance_funding_rate "
                "WHERE funding_time>=:a AND funding_time<:b"),
                {"a": di.min().tz_convert(None), "b": di.max().tz_convert(None)}).all()
        colset = set(syms)
        for s, t_, v in rr:
            if s not in colset:
                continue
            ts = pd.Timestamp(t_, tz="UTC"); d0 = ts.normalize()
            if d0 not in FUND["아시아"].index:
                continue
            for nm, (a_, b_) in sess.items():
                if a_ <= ts.hour < b_:
                    FUND[nm].at[d0, s] += float(v)*100.0
                    break
        SIG = {nm: RET[nm].to_numpy(np.float32) for nm in sess}
        ADJ = {nm: (RET[nm]-FUND[nm]).to_numpy(np.float32) for nm in sess}
        rng = np.random.default_rng(cfg.seed)
        q = pd.PeriodIndex(di, freq="Q")
        for (si, sj, N, leg) in CELLS:
            for pct in (False, True):
                v = leg_daily(SIG[si], ADJ[sj], N, leg, cfg, pct=pct)
                ok = np.isfinite(v)
                x = v[ok]
                if len(x) < 200:
                    continue
                # 방향맞춤 위약
                pl = []
                for _ in range(min(cfg.reps, 60)):
                    rs = rng.random(SIG[si].shape).astype(np.float32)
                    rs[~np.isfinite(SIG[si])] = np.nan
                    w = leg_daily(rs, ADJ[sj], N, leg, cfg, pct=pct)
                    pl.append(np.nanmean(w))
                pl = float(np.median([z for z in pl if np.isfinite(z)]))
                m, sd = float(x.mean()), float(x.std(ddof=1))
                srt = np.sort(x)
                # 분기별
                qq = pd.Series(x, index=q[ok]).groupby(level=0).mean()
                rows.append({
                    "구획": tag, "선별": "백분위" if pct else "고정",
                    "신호": si, "거래": sj, "종목": N, "다리": leg,
                    "날짜": len(x), "일평균": m, "일중앙": float(np.median(x)),
                    "날짜t": m/(sd/np.sqrt(len(x))),
                    "샤프": m/sd*np.sqrt(365.25),
                    "양수일%": float(100*(x > 0).mean()),
                    "상위5일뺀": float(srt[:-5].mean()),
                    "위약": pl, "초과": m-pl,
                    "연환산%": m*365.25,
                    "양수분기": f"{int((qq>0).sum())}/{len(qq)}",
                    "전반": float(x[:len(x)//2].mean()),
                    "후반": float(x[len(x)//2:].mean())})
                log.info("  [%s/%s] %s→%s %s%d → %+.4f · t %+.2f · 샤프 %.2f "
                         "· 초과 %+.4f · 분기 %s · %.1f분", tag,
                         "백분위" if pct else "고정", si, sj, leg, N, m,
                         m/(sd/np.sqrt(len(x))), m/sd*np.sqrt(365.25), m-pl,
                         f"{int((qq>0).sum())}/{len(qq)}", (time.time()-t0)/60)
    T = pd.DataFrame(rows).sort_values("날짜t", ascending=False)
    print(f"\n■ 4년 합본 — **미리 고정한 칸만** · 왕복 {cfg.fee_rt}% · 펀딩 · 날짜 t")
    print(T.to_string(index=False, float_format=lambda z: f"{z:+.4f}"))
    OUT.mkdir(parents=True, exist_ok=True)
    T.to_csv(OUT / "combined.csv", index=False)
    log.info("저장 · %.1f분", (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
