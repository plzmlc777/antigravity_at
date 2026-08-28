"""결합 이상 탐지 — 축 하나가 아니라 **동시에 터진** 것만 잡는다.

## 왜 (2026-08-28)

단축 탐지기로 하루 20회 발화시켰더니 1.83일에 진짜 사건 **1건**을 잡았다.

    MOVRUSDT 08-27 03:17 — 1분에 +15.3%, 그 뒤 60분 **+55.4%**

그런데 나머지 36건은 평균 −1.3% 였다. 기댓값은 양수인데 그 양수가 관측
**1건**에 얹혀 있다. 복권 구조다.

무작정 표본을 기다리기 전에 **헛발화를 줄이는 게** 먼저다. MOVR 그 순간을 보면
네 축이 **동시에** 터졌다.

    가격 점프  변동성 19배 · 체결 수 3배 · 거래대금 4배 · 매수 주도 66%

단축 탐지기는 하나씩만 본다. 결합하면 발화가 줄면서 이건 남을 것이다.

## 결합 방식 — 최소 순위

축마다 전체를 백분위로 줄 세우고 **가장 낮은 백분위**를 점수로 쓴다.
평균이나 곱이 아니라 최소인 이유: 한 축만 극단이고 나머지가 평범하면
"동시에"가 아니다. 최소는 그걸 걸러낸다.

## 고친 결함 둘 (2026-08-28 실측)

  ① 고저폭급증이 **12억·25억** 을 냈다. 직전 60분 고저폭이 0 인 종목 —
     거래가 없어 가격이 멈춰 있다가 다시 움직인 것이다. 이상 움직임이 아니라
     **결측에서 깨어난 것**이다. → 생존 조건(직전 창 최소 체결)을 건다.
  ② 흐름불균형 상위가 전부 값 **1.0**(완전 포화)이었다. 동점이 많아 상위 K
     선택이 사실상 무작위였다. → 최소 거래대금을 걸고 동점은 대금으로 가른다.

⚠ 방향은 파라미터다. 규칙과 거울을 같이 돌린다(교훈#91).
⚠ 같은 K 로 무작위 발화를 200회 돌려 기준선을 만든다. 359종목이면 아무 데나
  찍어도 가끔 큰 게 걸린다 — 그게 넘어야 할 선이다.
⚠ 표본 1.83일. 결론이 아니라 지형이다.

사용:
  python3 -m scripts.research.tick_combo_detector --smoke 60
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
log = logging.getLogger("combo")

HORIZONS = (15, 30, 60, 120)
RATES = (2, 5, 20)                  # 하루 발화 횟수(유니버스 전체)
TAILS = (2.0, 5.0, 10.0)


@dataclass(frozen=True)
class Cfg:
    lookback: int = 60
    cooldown: int = 60
    min_ticks: int = 2_000
    min_live_tr: float = 5.0     # 직전 창 분당 체결 중앙이 이보다 적으면 죽은 종목
    min_qv: float = 5_000.0      # 그 분 거래대금 하한($)
    fee_pct: float = 0.036
    n_random: int = 200
    seed: int = 20260828


def features(sym: str, cfg: Cfg) -> pd.DataFrame | None:
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
    t["bqv"] = np.where(~t.is_buyer_maker, t.qv, 0.0)
    g = t.groupby(t.ts_ms // 60_000)
    b = pd.DataFrame({"cl": g.price.last(), "hi": g.price.max(),
                      "lo": g.price.min(), "qv": g.qv.sum(),
                      "ntr": g.price.size(), "bqv": g.bqv.sum()})
    b.index = pd.to_datetime(b.index * 60_000, unit="ms", utc=True)
    b = b.reindex(pd.date_range(b.index.min(), b.index.max(), freq="1min",
                                tz="UTC"))
    b[["cl", "hi", "lo"]] = b[["cl", "hi", "lo"]].ffill()
    b[["qv", "ntr", "bqv"]] = b[["qv", "ntr", "bqv"]].fillna(0.0)
    L = cfg.lookback
    if len(b) < L + max(HORIZONS) + 30:
        return None
    eps = 1e-12
    base_q = b.qv.rolling(L).median().shift(1)
    base_n = b.ntr.rolling(L).median().shift(1)
    lr = np.log(b.cl.clip(lower=eps)).diff()
    rv = lr.rolling(L).std().shift(1)

    f = pd.DataFrame(index=b.index)
    f["cl"] = b.cl
    f["qv"] = b.qv
    # ⚠ 생존 조건 — 죽어 있던 종목이 깨어난 것을 이상 신호로 읽지 않는다
    f["live"] = (base_n >= cfg.min_live_tr) & (b.qv >= cfg.min_qv)
    f["ax_점프"] = (lr / (rv + eps)).abs()
    f["ax_체결수"] = b.ntr / (base_n + eps)
    f["ax_대금"] = b.qv / (base_q + eps)
    imb = (2.0 * b.bqv - b.qv) / (b.qv + eps)          # (매수-매도)/전체
    # ⚠ 불균형 비율 그대로 쓰면 **체결 3건이 전부 매수인 분**이 1.0 으로 상위를
    #   독차지한다. 실측(2026-08-28): MOVR 03:17 은 9,994건에 66% 매수라
    #   비율은 0.32 였는데 백분위로 밀려 결합 탐지에서 탈락했다.
    #   건수를 반영한다 — 이항 표준오차가 1/√n 이므로 imb×√n 이 t 다.
    #   9,994건의 0.32 는 32σ, 3건의 1.0 은 1.7σ.
    f["ax_흐름"] = imb * np.sqrt(b.ntr) * np.sign(lr)
    f["ret_sign"] = np.sign(lr).replace(0, 1.0)
    f["symbol"] = sym

    hi, lo, cl = (b.hi.to_numpy(float), b.lo.to_numpy(float),
                  b.cl.to_numpy(float))
    for h in HORIZONS:
        top = pd.Series(hi).rolling(h).max().shift(-h).to_numpy()
        bot = pd.Series(lo).rolling(h).min().shift(-h).to_numpy()
        nxt = pd.Series(cl).shift(-h).to_numpy()
        f[f"up_{h}"] = (top / cl - 1.0) * 100.0
        f[f"dn_{h}"] = (1.0 - bot / cl) * 100.0
        f[f"r_{h}"] = (nxt / cl - 1.0) * 100.0
    return f.iloc[L:].reset_index(names="ts")


AXES = ["ax_점프", "ax_체결수", "ax_대금", "ax_흐름"]
# ⚠ 네 축을 **동등하게** 요구했더니 하나만 평범해도 탈락했다 — MOVR 이 그렇게
#   빠졌다. 그래서 구조를 바꾼다: **점프가 주축**이고 나머지는 헛발화를
#   걷어내는 **필터**다. 필터는 백분위 하한으로 건다.
PRIMARY = "ax_점프"
COMBOS: dict[str, dict] = {
    "점프": {},
    "체결수": {"primary": "ax_체결수"},
    "대금": {"primary": "ax_대금"},
    "흐름": {"primary": "ax_흐름"},
    "점프|체결수50": {"f": {"ax_체결수": 0.50}},
    "점프|체결수80": {"f": {"ax_체결수": 0.80}},
    "점프|대금80": {"f": {"ax_대금": 0.80}},
    "점프|흐름50": {"f": {"ax_흐름": 0.50}},
    "점프|흐름80": {"f": {"ax_흐름": 0.80}},
    "점프|체결수80+대금80": {"f": {"ax_체결수": 0.80, "ax_대금": 0.80}},
    "점프|셋다80": {"f": {"ax_체결수": 0.80, "ax_대금": 0.80, "ax_흐름": 0.80}},
    "점프|셋다50": {"f": {"ax_체결수": 0.50, "ax_대금": 0.50, "ax_흐름": 0.50}},
}


def pick(P: pd.DataFrame, score: np.ndarray, K: int, sym_code: np.ndarray,
         ts: np.ndarray, cfg: Cfg) -> np.ndarray:
    order = np.argsort(np.where(np.isfinite(score), -score, np.inf))
    got, last = [], {}
    cd = cfg.cooldown * 60_000_000_000
    for g in order:
        if len(got) >= K:
            break
        if not np.isfinite(score[g]):
            break
        sc = sym_code[g]
        if sc in last and ts[g] - last[sc] < cd:
            continue
        got.append(g); last[sc] = ts[g]
    return np.asarray(got, dtype=int)


def outcomes(P: pd.DataFrame, idx: np.ndarray, sign: np.ndarray,
             cfg: Cfg) -> dict:
    out = {}
    for h in HORIZONS:
        up = P[f"up_{h}"].to_numpy()[idx]
        dn = P[f"dn_{h}"].to_numpy()[idx]
        r = P[f"r_{h}"].to_numpy()[idx]
        mfe = np.where(sign > 0, up, dn)
        ret = sign * r
        ok = np.isfinite(mfe) & np.isfinite(ret)
        if ok.sum() < 5:
            continue
        mfe, ret = mfe[ok], ret[ok]
        net = ret - cfg.fee_pct
        o = {"n": int(ok.sum()), "ret_mean": float(ret.mean()),
             "ret_med": float(np.median(ret)),
             "net_total": float(net.sum()),
             "ret_max": float(ret.max()), "ret_min": float(ret.min()),
             "mfe_max": float(mfe.max()), "mfe_med": float(np.median(mfe)),
             "ret_mean_ex1": float(np.sort(ret)[:-1].mean()) if len(ret) > 1
                             else np.nan}
        for x in TAILS:
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
        if i % 100 == 0 or i == len(syms):
            log.info("[%d/%d] %.1f분", i, len(syms), (time.time()-t0)/60)
    P = pd.concat(parts, ignore_index=True)
    days = (P.ts.max() - P.ts.min()).total_seconds() / 86400
    live = P.live.fillna(False).to_numpy()
    log.info("판 %s분봉 · 종목 %d · %.2f일 · 생존 %.1f%%", f"{len(P):,}",
             P.symbol.nunique(), days, 100.0 * live.mean())

    # 축별 백분위 — 생존한 칸 안에서만 매긴다
    RK = {}
    for ax in AXES:
        v = P[ax].to_numpy(float)
        v = np.where(live & np.isfinite(v), v, np.nan)
        RK[ax] = pd.Series(v).rank(pct=True).to_numpy()

    sym_code = pd.factorize(P.symbol)[0]
    ts = P.ts.astype("int64").to_numpy()
    rng = np.random.default_rng(cfg.seed)
    rows, fired = [], []
    for name, spec in COMBOS.items():
        prim = spec.get("primary", PRIMARY)
        score = RK[prim].copy()
        keep = live.copy()
        for ax, lo in spec.get("f", {}).items():
            keep &= np.nan_to_num(RK[ax], nan=-1.0) >= lo
        score = np.where(keep, score, np.nan)
        for rate in RATES:
            K = max(int(round(rate * days)), 8)
            idx = pick(P, score, K, sym_code, ts, cfg)
            if len(idx) < 8:
                continue
            sg = P.ret_sign.to_numpy(float)[idx]
            for arm, sign in (("실측", sg), ("반대", -sg)):
                for h, o in outcomes(P, idx, sign, cfg).items():
                    rows.append({"detector": name, "rate": rate, "K": len(idx),
                                 "arm": arm, "horizon": h, **o})
            for rep in range(cfg.n_random):
                r2 = rng.choice(np.where(live)[0], size=len(idx), replace=False)
                rs = P.ret_sign.to_numpy(float)[r2]
                for h, o in outcomes(P, r2, rs, cfg).items():
                    rows.append({"detector": name, "rate": rate, "K": len(idx),
                                 "arm": "무작위", "rep": rep, "horizon": h, **o})
            if rate == RATES[-1]:
                for g in idx:
                    fired.append({"detector": name, "symbol": P.symbol.iat[g],
                                  "ts": P.ts.iat[g],
                                  "score": float(score[g]),
                                  "점프": float(P.ax_점프.iat[g]),
                                  "체결수": float(P.ax_체결수.iat[g]),
                                  "대금": float(P.ax_대금.iat[g]),
                                  "흐름": float(P.ax_흐름.iat[g]),
                                  "ret_60": float(P.ret_sign.iat[g]
                                                  * P.r_60.iat[g])})
    R = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    path = Path(a.out) if a.out else OUT / "tick_combo_detector.csv"
    R.to_csv(path, index=False)
    pd.DataFrame(fired).to_csv(path.with_name(path.stem + "_fired.csv"),
                               index=False)
    log.info("저장 %s — %s행 · %.1f분", path, f"{len(R):,}", (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
