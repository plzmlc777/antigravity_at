"""이상 움직임 사냥 — 평균이 아니라 **꼬리**를 노린다.

## 전제가 바뀌었다 (2026-08-28, 대표님 지시)

지금까지는 "359종목 평균으로 버는 보편 규칙"을 찾았다. 그래서 평균을 냈고,
평균은 이상값을 지운다 — 5,095건 평균 +0.046% 안에 +5% 짜리 50건이 섞여
있어도 똑같이 나온다.

새 목표는 다르다. **24시간에 단 한 번이라도 비정상 움직임을 짚어내면 성공**이다.
그러니 재는 것도 평균이 아니라 **분포와 꼬리**여야 한다.

## 🚫 반드시 피해야 할 함정

사후에 "오늘 제일 많이 움직인 종목"을 찾는 건 **아무 가치가 없다**. 24시간마다
30% 움직인 종목은 반드시 있다. 검정이 성립하려면 두 가지를 지켜야 한다.

  ① 탐지기는 **그 순간 가진 정보만** 쓴다(후행 특징만).
  ② **같은 횟수로 아무 데나 찍은 것**보다 나아야 한다. 359종목에서 하루 20번
     무작위로 찍어도 가끔은 큰 움직임에 걸린다. 그게 기준선이다.

## 탐지 축 — 가격만이 아니다

지금까지 가격만 봤다. 틱에는 `is_buyer_maker` 가 있어 **누가 공격했는지**를
안다. 실측(SOLUSDT 하루): 체결 1건 대금 중앙 $99 인데 최대 $2,455,650 —
2만 4천 배다. 이런 건 가격으로는 안 보인다.

    거래대금급증  분당 대금 / 직전 60분 중앙
    체결수급증    분당 체결 건수 / 직전 60분 중앙
    대형체결      그 분 최대 단일 체결 / 직전 60분 체결 중앙   ← 새 축
    주문흐름      공격적 매수·매도 불균형                      ← 새 축
    가격점프      |1분 수익률| / 직전 실현변동성 (고정 % 아님)
    고저폭급증    분 고저폭 / 직전 60분 중앙

## 희소성으로 눈금을 맞춘다

문턱을 %로 박지 않는다. 탐지기 값으로 전체를 줄 세워 **상위 K개**만 취한다.
K 를 바꿔 "하루 5번 / 20번 / 100번" 세 눈금으로 본다. 그래야 서로 다른
탐지기를 같은 조건에서 비교할 수 있고, 무작위 대조도 같은 K 로 맞춘다.

⚠ 방향은 **파라미터**다. 규칙과 그 거울을 같이 돌린다(교훈#91).
⚠ 판정은 **총손익**(빈도×엣지)과 **꼬리 비율**로 한다. 승률은 성과가 아니다.
⚠ 표본은 아직 하루 반이다. 결론이 아니라 지형이다.

사용:
  python3 -m scripts.research.tick_anomaly_hunt --smoke 60
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
TICKS = ROOT / "runs" / "ticks"
OUT = ROOT / "runs" / "research_track" / "regime"
log = logging.getLogger("anomaly")

HORIZONS = (5, 15, 30, 60, 120)     # 분
RATES = (5, 20, 100)                # 하루 몇 번 발화시킬 것인가(유니버스 전체)
TAILS = (1.0, 2.0, 3.0, 5.0)        # 꼬리 비율을 볼 문턱(%)


@dataclass(frozen=True)
class Cfg:
    lookback: int = 60       # 후행 기준선 창(분)
    cooldown: int = 60       # 같은 종목 재발화 금지(분)
    min_ticks: int = 2_000
    fee_pct: float = 0.036
    n_random: int = 200      # 무작위 대조 반복
    seed: int = 20260828


def features(sym: str, cfg: Cfg) -> pd.DataFrame | None:
    """분봉 + 이상 탐지 특징. **전부 후행**이다."""
    d = TICKS / sym
    fs = sorted(d.glob("*.parquet"))
    if not fs:
        return None
    t = pd.concat([pd.read_parquet(f) for f in fs], ignore_index=True)
    t = t[(t.price > 0) & (t.qty > 0)]
    if len(t) < cfg.min_ticks:
        return None
    t = t.sort_values("ts_ms")
    t["qv"] = t.price * t.qty
    # 공격적 매수 = 매수자가 테이커 = is_buyer_maker False
    t["bqv"] = np.where(~t.is_buyer_maker, t.qv, 0.0)
    t["sqv"] = np.where(t.is_buyer_maker, t.qv, 0.0)
    k = t.ts_ms // 60_000
    g = t.groupby(k)
    b = pd.DataFrame({
        "cl": g.price.last(), "hi": g.price.max(), "lo": g.price.min(),
        "qv": g.qv.sum(), "ntr": g.price.size(), "mx": g.qv.max(),
        "bqv": g.bqv.sum(), "sqv": g.sqv.sum(), "med_tr": g.qv.median()})
    b.index = pd.to_datetime(b.index * 60_000, unit="ms", utc=True)
    full = pd.date_range(b.index.min(), b.index.max(), freq="1min", tz="UTC")
    b = b.reindex(full)
    b[["cl", "hi", "lo"]] = b[["cl", "hi", "lo"]].ffill()
    b[["qv", "ntr", "mx", "bqv", "sqv"]] = b[["qv", "ntr", "mx", "bqv",
                                              "sqv"]].fillna(0.0)
    b["med_tr"] = b.med_tr.ffill()
    L = cfg.lookback
    if len(b) < L + max(HORIZONS) + 30:
        return None

    # ⚠ 기준선은 **직전** 창만 본다. shift(1) 이 그 한 줄이다.
    def base(x):
        return x.rolling(L).median().shift(1)

    eps = 1e-12
    f = pd.DataFrame(index=b.index)
    f["cl"] = b.cl
    f["대금급증"] = b.qv / (base(b.qv) + eps)
    f["체결수급증"] = b.ntr / (base(b.ntr) + eps)
    f["대형체결"] = b.mx / (base(b.med_tr) + eps)
    tot = b.bqv + b.sqv
    imb = (b.bqv - b.sqv) / (tot + eps)
    f["흐름불균형"] = imb.rolling(5).mean()
    f["흐름불균형절대"] = f["흐름불균형"].abs()
    lr = np.log(b.cl.clip(lower=eps)).diff()
    rv = lr.rolling(L).std().shift(1)
    f["가격점프"] = (lr / (rv + eps)).abs()
    f["고저폭급증"] = ((b.hi - b.lo) / b.cl) / (
        base((b.hi - b.lo) / b.cl) + eps)
    f["ret1m"] = lr * 100.0
    f["imb_sign"] = np.sign(f["흐름불균형"])
    f["ret_sign"] = np.sign(lr)

    hi, lo, cl = b.hi.to_numpy(float), b.lo.to_numpy(float), b.cl.to_numpy(float)
    n = len(cl)
    for h in HORIZONS:
        top = pd.Series(hi).rolling(h).max().shift(-h).to_numpy()
        bot = pd.Series(lo).rolling(h).min().shift(-h).to_numpy()
        nxt = pd.Series(cl).shift(-h).to_numpy()
        f[f"up_{h}"] = (top / cl - 1.0) * 100.0     # 롱 유리 / 숏 불리
        f[f"dn_{h}"] = (1.0 - bot / cl) * 100.0
        f[f"r_{h}"] = (nxt / cl - 1.0) * 100.0
    f["symbol"] = sym
    return f.iloc[L:].reset_index(names="ts")


DETECTORS = {
    "대금급증": ("대금급증", "ret_sign"),
    "체결수급증": ("체결수급증", "ret_sign"),
    "대형체결": ("대형체결", "ret_sign"),
    "흐름불균형": ("흐름불균형절대", "imb_sign"),
    "가격점프": ("가격점프", "ret_sign"),
    "고저폭급증": ("고저폭급증", "ret_sign"),
}


def outcomes(P: pd.DataFrame, idx: np.ndarray, sign: np.ndarray,
             cfg: Cfg) -> dict:
    """발화 지점들의 결과 분포. 평균 하나로 뭉개지 않는다."""
    out = {}
    for h in HORIZONS:
        up = P[f"up_{h}"].to_numpy()[idx]
        dn = P[f"dn_{h}"].to_numpy()[idx]
        r = P[f"r_{h}"].to_numpy()[idx]
        mfe = np.where(sign > 0, up, dn)      # 방향에 맞춘 유리폭
        mae = np.where(sign > 0, dn, up)
        ret = sign * r
        ok = np.isfinite(mfe) & np.isfinite(ret)
        if ok.sum() < 5:
            continue
        mfe, mae, ret = mfe[ok], mae[ok], ret[ok]
        o = {"n": int(ok.sum()), "ret_mean": float(ret.mean()),
             "ret_med": float(np.median(ret)),
             "net_total": float((ret.mean() - cfg.fee_pct) * ok.sum()),
             "mfe_med": float(np.median(mfe)),
             "mfe_p90": float(np.quantile(mfe, 0.9)),
             "mfe_max": float(mfe.max()),
             "mae_med": float(np.median(mae)),
             "ret_max": float(ret.max()), "ret_min": float(ret.min())}
        for x in TAILS:
            o[f"p_mfe_{x}"] = float(100.0 * (mfe >= x).mean())
            o[f"p_ret_{x}"] = float(100.0 * (ret >= x).mean())
        out[h] = o
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--universe", default="configs/rsi_live_universe.txt")
    p.add_argument("--smoke", type=int, default=0)
    p.add_argument("--out", default="")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    cfg = Cfg()
    log.info("설정 %s", json.dumps(asdict(cfg), ensure_ascii=False))

    syms = [s.strip().upper() for s in
            (ROOT / a.universe).read_text().split() if s.strip()]
    if a.smoke:
        syms = syms[:a.smoke]
    t0 = time.time()
    parts = []
    for i, s in enumerate(syms, 1):
        try:
            f = features(s, cfg)
        except Exception as e:                                  # noqa: BLE001
            log.warning("%s 실패: %s", s, str(e)[:100]); f = None
        if f is not None:
            parts.append(f)
        if i % 50 == 0 or i == len(syms):
            el = time.time() - t0
            log.info("[%d/%d] 행 %s · %.1f분 · 남은 %.1f분", i, len(syms),
                     f"{sum(len(x) for x in parts):,}", el/60,
                     (len(syms)-i)*el/i/60)
    P = pd.concat(parts, ignore_index=True)
    days = (P.ts.max() - P.ts.min()).total_seconds() / 86400
    log.info("판 %s분봉 · 종목 %d · %.2f일", f"{len(P):,}", P.symbol.nunique(), days)

    rng = np.random.default_rng(cfg.seed)
    sym_code = pd.factorize(P.symbol)[0]
    rows = []
    for det, (col, dircol) in DETECTORS.items():
        v = P[col].to_numpy(float)
        order = np.argsort(np.where(np.isfinite(v), -v, np.inf))
        for rate in RATES:
            K = max(int(round(rate * days)), 10)
            # 재무장 — 같은 종목이 연달아 걸리면 한 사건을 여러 번 세게 된다
            picked, last = [], {}
            for g in order:
                if len(picked) >= K:
                    break
                sc, ts = sym_code[g], P.ts.iat[g]
                if sc in last and (ts - last[sc]).total_seconds() < cfg.cooldown*60:
                    continue
                picked.append(g); last[sc] = ts
            picked = np.asarray(picked)
            if len(picked) < 10:
                continue
            sg = P[dircol].to_numpy(float)[picked]
            sg[sg == 0] = 1.0
            for arm, sign in (("실측", sg), ("반대", -sg)):
                for h, o in outcomes(P, picked, sign, cfg).items():
                    rows.append({"detector": det, "rate": rate, "K": len(picked),
                                 "arm": arm, "horizon": h, **o})
            # ── 무작위 대조: 같은 횟수로 아무 데나. 359종목이면 우연히도 걸린다
            for rep in range(cfg.n_random):
                ridx = rng.choice(len(P), size=len(picked), replace=False)
                rs = P[dircol].to_numpy(float)[ridx]
                rs[rs == 0] = 1.0
                for h, o in outcomes(P, ridx, rs, cfg).items():
                    rows.append({"detector": det, "rate": rate, "K": len(picked),
                                 "arm": "무작위", "rep": rep, "horizon": h, **o})
    R = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    path = Path(a.out) if a.out else OUT / "tick_anomaly_hunt.csv"
    R.to_csv(path, index=False)
    log.info("저장 %s — %s행 · %.1f분", path, f"{len(R):,}", (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
