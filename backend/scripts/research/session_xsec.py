"""세션 간 **횡단면** 이월/반전 — 아시아에서 오른 종목이 미주에서 어떻게 되나.

## 왜 (2026-08-31, 대표님 지시)

연속 횡단면 선별이 통행료에서 막혔다(여섯 계열 · 회수율 0~117%). 세션 기반은
하루 최대 세 번 거래하고 세션 한 칸이 1~2% 움직이니 **통행료 비율이 두 자릿수
유리하다** — 애초에 그 벽에 안 걸린다.

지형(session_map)에서 본 것:

    미주가 움직임을 만든다   시간당 SD 1.49 (나머지 1.18~1.28) · 거래대금 38.6%
    세션끼리 뭉뚱그린 상관    -0.057 ~ +0.032 = 0

뭉뚱그린 상관이 0이어도 **횡단면은 살아 있을 수 있다** — "아시아가 오른 날에
미주가 떨어지나"와 "아시아에서 오른 종목이 미주에서 떨어지나"는 다른 질문이다.

## 규약

    구획(UTC)  아시아 00-08 · 유럽 08-13 · 미주 13-21 · 야간 21-24
    신호       세션 i 안 수익률 (첫 종가 → 마지막 종가)
    거래       세션 j **시작 봉 종가에 진입**, 세션 j 마지막 봉 종가에 청산
               → 신호 세션과 거래 세션이 **겹치지 않는다**
    방향       상위 숏 / 하위 롱 (반전) 과 그 **거울**(추세)을 둘 다 돌린다

⚠ 방향을 결과 보고 고르면 안 된다(교훈#91). 두 방향을 격자에 같이 넣고
  최대통계량으로 보정한다(교훈#95).
⚠ 독립 단위는 **날짜**다. 블록 수로 t 를 내면 부풀린다(교훈#112).
⚠ 방향맞춤 위약(교훈#101) — 같은 날·같은 수를 무작위로 골라 같은 다리를 만든다.
⚠ 겹치는 세션쌍은 뺀다. 같은 날 안에서 i 가 j 보다 앞서야 한다
  (야간→다음날 아시아는 날짜가 바뀌므로 별도로 다룬다 — 여기서는 제외).
⚠ 펀딩 — 세션 하나가 5~8시간이라 정산이 1회 낀다. 종목별 `r - f` 로 반영.

사용:
  python3 -m scripts.research.session_xsec --smoke
  python3 -m scripts.research.session_xsec --reps 400
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
log = logging.getLogger("sessxsec")

SESS = [("아시아", 0, 8), ("유럽", 8, 13), ("미주", 13, 21), ("야간", 21, 24)]
ORDER = {nm: k for k, (nm, _, _) in enumerate(SESS)}
PAIRS = [(i, j) for i in ORDER for j in ORDER if ORDER[j] > ORDER[i]]


@dataclass(frozen=True)
class Cfg:
    picks: tuple = (3, 5, 10)
    # ⚠ 다리는 **실제 동작 그대로** 이름 붙인다. 예전엔 (숏만/롱만)×(반전/추세)
    #   로 두어 부호가 두 번 뒤집혔고, "숏만·추세"가 실제로는 롱이었다.
    #   이름만 보고 읽으면 정반대로 보고한다.
    legs: tuple = ("상위롱", "상위숏", "하위롱", "하위숏", "추세스프레드",
                   "반전스프레드")
    fee_rt: float = 0.072
    min_alive: int = 40
    min_cover: float = 90.0
    reps: int = 400
    seed: int = 20260831

    def dump(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


def build(cache: str, cfg: Cfg):
    """(날짜 × 종목) 세션별 수익률 · 펀딩조정. 커버리지 미달은 결측."""
    fs = sorted((ROOT/cache).glob("*.parquet"))
    per = {}
    for f in fs:
        d = pd.read_parquet(f, columns=["ts", "c", "n"])
        if len(d) < 5_000:
            continue
        ts = pd.to_datetime(d.ts, utc=True)
        d = d.assign(ts=ts, date=ts.dt.normalize(), hour=ts.dt.hour)
        lab = pd.Series("", index=d.index, dtype=object)
        for nm, a_, b_ in SESS:
            lab[(d.hour >= a_) & (d.hour < b_)] = nm
        d["sess"] = lab
        d = d[d.sess != ""]
        g = d.groupby(["date", "sess"], sort=False)
        r = pd.DataFrame({"first": g.c.first(), "last": g.c.last(),
                          "bars": g.size()}).reset_index()
        full = {nm: (b_-a_)*12 for nm, a_, b_ in SESS}
        r = r[100.0*r.bars/r.sess.map(full) >= cfg.min_cover]
        r["ret"] = (r["last"]/r["first"] - 1.0)*100.0
        per[f.stem] = r
    RET = {nm: pd.DataFrame({s: v[v.sess == nm].set_index("date").ret
                             for s, v in per.items()}) for nm in ORDER}
    dates = sorted(set().union(*[set(v.index) for v in RET.values()]))
    syms = sorted(set().union(*[set(v.columns) for v in RET.values()]))
    RET = {k: v.reindex(index=dates, columns=syms) for k, v in RET.items()}
    return RET, dates, syms


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cache", default="runs/bars5m")
    p.add_argument("--reps", type=int, default=None)
    p.add_argument("--smoke", action="store_true")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    cfg = Cfg(**({"reps": a.reps} if a.reps else {}))
    if a.smoke:
        cfg = Cfg(picks=(5,), reps=40)
    log.info("설정 %s · 기질 %s", cfg.dump(), a.cache)
    t0 = time.time()
    RET, dates, syms = build(a.cache, cfg)
    log.info("판 날짜 %d · 종목 %d · %.1f분", len(dates), len(syms),
             (time.time()-t0)/60)

    # 펀딩 — 세션별 누적(%)을 빼준다
    di = pd.DatetimeIndex(dates)
    FUND = {nm: pd.DataFrame(0.0, index=di, columns=syms) for nm in ORDER}
    with engine.connect() as c_:
        c_.execute(text("SET statement_timeout='240s'"))
        rr = c_.execute(text(
            "SELECT symbol, funding_time, funding_rate FROM binance_funding_rate "
            "WHERE funding_time>=:a AND funding_time<:b"),
            {"a": di.min().tz_convert(None), "b": di.max().tz_convert(None)}).all()
    nf = 0
    for s, t_, v in rr:
        if s not in FUND["아시아"].columns:
            continue
        ts = pd.Timestamp(t_, tz="UTC")
        d0 = ts.normalize()
        if d0 not in FUND["아시아"].index:
            continue
        for nm, a_, b_ in SESS:
            if a_ <= ts.hour < b_:
                FUND[nm].at[d0, s] += float(v)*100.0
                nf += 1
                break
    log.info("펀딩 %s건 · %.1f분", f"{nf:,}", (time.time()-t0)/60)
    ADJ = {nm: (RET[nm] - FUND[nm]).to_numpy(np.float32) for nm in ORDER}
    SIG = {nm: RET[nm].to_numpy(np.float32) for nm in ORDER}   # 신호는 순수 가격

    rng = np.random.default_rng(cfg.seed)
    rows, best = [], np.full(cfg.reps, -9e9)
    nd = len(dates)

    def legs_ret(sig, ret, N, leg):
        """날짜별 다리 수익(%). hi = 신호 상위 N · lo = 신호 하위 N.

        상위롱   신호 상위를 산다              추세(모멘텀)
        상위숏   신호 상위를 판다              반전
        하위롱   신호 하위를 산다              반전
        하위숏   신호 하위를 판다              추세
        추세스프레드  상위롱 + 하위숏 (자본 반반)
        반전스프레드  상위숏 + 하위롱 (자본 반반)
        """
        out = np.full(nd, np.nan)
        for i in range(nd):
            ok = np.where(np.isfinite(sig[i]) & np.isfinite(ret[i]))[0]
            if len(ok) < cfg.min_alive:
                continue
            o = ok[np.argsort(-sig[i][ok])]
            h, l = float(ret[i][o[:N]].mean()), float(ret[i][o[-N:]].mean())
            v = {"상위롱": h, "상위숏": -h, "하위롱": l, "하위숏": -l,
                 "추세스프레드": (h - l)/2.0,
                 "반전스프레드": (l - h)/2.0}[leg]
            out[i] = v - cfg.fee_rt
        return out

    def rand_ret(ret, N, leg):
        """방향맞춤 위약 — 같은 날·같은 수를 무작위로. 다리 모양을 그대로 흉내낸다."""
        out = np.full(nd, np.nan)
        for i in range(nd):
            ok = np.where(np.isfinite(ret[i]))[0]
            if len(ok) < cfg.min_alive:
                continue
            pk = rng.permutation(ok)
            h, l = float(ret[i][pk[:N]].mean()), float(ret[i][pk[N:2*N]].mean())
            v = {"상위롱": h, "상위숏": -h, "하위롱": l, "하위숏": -l,
                 "추세스프레드": (h - l)/2.0,
                 "반전스프레드": (l - h)/2.0}[leg]
            out[i] = v - cfg.fee_rt
        return out

    cells = []
    for (si, sj) in PAIRS:
        sig, ret = SIG[si], ADJ[sj]
        for N in cfg.picks:
            for leg in cfg.legs:
                v = legs_ret(sig, ret, N, leg)
                v = v[np.isfinite(v)]
                if len(v) < 100:
                    continue
                pl = np.asarray([np.nanmean(rand_ret(ret, N, leg))
                                 for _ in range(min(cfg.reps, 40))])
                m, sd = float(v.mean()), float(v.std(ddof=1))
                # ⚠ 소수 대박 진단(교훈#81) — 평균이 양수인데 이긴 날이 절반
                #   미만이면 꼬리가 전부 만든 것이다. 상위 5일을 빼고 다시 잰다.
                srt = np.sort(v)
                m5 = float(srt[:-5].mean()) if len(srt) > 20 else np.nan
                top5 = float(srt[-5:].sum()/ (m*len(v))) if m*len(v) != 0 else np.nan
                rows.append({
                    "신호": si, "거래": sj, "종목": N, "다리": leg,
                    "날짜": len(v), "일평균": m, "일중앙": float(np.median(v)),
                    "날짜t": m/(sd/np.sqrt(len(v))),
                    "양수일%": float(100*(v > 0).mean()),
                    "상위5일뺀평균": m5, "상위5일몫%": 100*top5,
                    "위약": float(np.median(pl)), "초과": m-float(np.median(pl)),
                    "연환산": m*365.25})
                cells.append((si, sj, N, leg))
        log.info("  %s→%s 완료 · %.1f분", si, sj, (time.time()-t0)/60)

    # 최대통계량 — 신호 세션의 **날짜를 섞어** 격자 전체를 다시 뒤진다
    for rep in range(cfg.reps):
        perm = rng.permutation(nd)
        for (si, sj, N, leg) in cells:
            v = legs_ret(SIG[si][perm], ADJ[sj], N, leg)
            v = v[np.isfinite(v)]
            if len(v) >= 100:
                best[rep] = max(best[rep], float(v.mean()))
        if (rep+1) % 50 == 0:
            log.info("  위약 %d/%d · %.1f분", rep+1, cfg.reps, (time.time()-t0)/60)

    T = pd.DataFrame(rows).sort_values("일평균", ascending=False)
    print(f"\n■ 세션 간 횡단면 — 종목 {len(syms)} · 날짜 {len(dates)} · "
          f"왕복 {cfg.fee_rt}% · 펀딩 · **날짜 t**")
    print(T.head(25).to_string(index=False, float_format=lambda z: f"{z:+.4f}"))
    obs = float(T.일평균.max())
    pm = float((best >= obs).mean())
    print(f"\n■ 최대통계량 위약 ({cfg.reps}회 · {len(T)}칸 · 신호 날짜 뒤섞기)")
    print(f"  관측 최대 {obs:+.4f}%/일 · 귀무 중앙 {np.median(best):+.4f} "
          f"· 95분위 {np.quantile(best,.95):+.4f}  **p = {pm:.3f}**")
    OUT.mkdir(parents=True, exist_ok=True)
    tag = "oos" if "oos" in a.cache else "is"
    T.to_csv(OUT / f"xsec_{tag}.csv", index=False)
    (OUT / f"xsec_{tag}.cfg.json").write_text(cfg.dump())
    log.info("저장 %s · %.1f분", OUT, (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
