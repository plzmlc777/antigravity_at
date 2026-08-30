"""운동학 신호 — **2년치**로 다시 잰다. 틱 4.3일이 아니라.

## 왜 (2026-08-30)

오늘 밤 여섯 번 기각했는데 전부 같은 이유로 죽었다 — **표본이 48블록**이다.
회전 위약만으로 총손익 ±3% 가 나오는데 관측이 +3% 면 아무것도 못 가린다.

    구간        틱 4.3일   →   ohlcv_1m 758일
    120분 블록    48개      →   9,096개      **190배**

`z_vel` 은 틱이 필요 없다. 선도 승률·속도·가속도가 전부 종가에서 나온다.
익절·손절도 고가·저가가 있어 그대로 된다. 틱이 꼭 필요했던 축(주문 흐름
불균형)은 이미 기각됐다. **틱이 있다는 이유로 틱에서만 쟀던 게 잘못이었다.**

기질은 `build_bars5m.py` 가 만든 5분봉 캐시다.

## 검정 규약 (이 세션에서 배운 것 전부)

  · **시각 가중** — 슬롯 실현으로 자본을 나눠 복리. 사건 풀링 금지
  · **비겹침 블록** 단위 추론 — 거래 단위가 아니다
  · **짝지은 대조** — 청산만 바꿔 비교하면 시장 표류가 상쇄된다
  · **회전 위약**, 시프트 하한 = 신호 기억 (교훈#108)
  · **한쪽 검정** — 개선과 해로움을 갈라 묻는다
  · **총손익**이 판정 주축 (대표님 지시)

⚠ 5분봉이라 한 봉 안에서 익절·손절이 같이 닿으면 순서를 모른다.
  **손절이 먼저** 닿은 것으로 본다(보수적).

사용:
  python3 -m scripts.research.kine_long --smoke 8 --reps 20
  python3 -m scripts.research.kine_long --reps 1000
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
CACHE = ROOT / "runs" / "bars5m"
OUT = ROOT / "runs" / "research_track" / "regime"
log = logging.getLogger("kinelong")

BAR = 5                                   # 봉 길이(분)
WIN_H, WINDOW, DELTA, HOLD = 12, 72, 36, 24        # 봉 단위 = 60·360·180·120분
Z_LO, Z_HI, ACC_MAX = -1.25, -0.25, 0.5            # 동결 밴드
TPS = (None, 1.0, 1.5, 2.0, 3.0)
SLS = (None, 2.0)
KEYS = [(tp, sl) for tp in TPS for sl in SLS]
KIDX = {k: i for i, k in enumerate(KEYS)}
COLS = {k: f"c{i}" for i, k in enumerate(KEYS)}
BASE = (None, None)
MEMORY = WINDOW + DELTA + WIN_H + HOLD             # 144봉 = 720분


@dataclass(frozen=True)
class Cfg:
    slots: int = 10
    fee_pct: float = 0.036
    min_bars_in_5: float = 3.0     # 5분 중 최소 몇 개의 1분봉이 있어야 살아있나
    block_bars: int = 24           # 비겹침 블록 = 120분
    seed: int = 20260830


def build(f: Path, cfg: Cfg, d_from: str = "", d_to: str = ""):
    d = pd.read_parquet(f)
    if d_from or d_to:
        # ⚠ 신호가 여물려면 기억(144봉)만큼 앞을 더 읽어야 한다. 구간 시작에서
        #   바로 자르면 첫 12시간이 통째로 결측이 된다.
        lo = (pd.Timestamp(d_from, tz="UTC") - pd.Timedelta(minutes=MEMORY * BAR)
              if d_from else None)
        hi = pd.Timestamp(d_to, tz="UTC") if d_to else None
        ts = pd.to_datetime(d.ts, utc=True)
        m = pd.Series(True, index=d.index)
        if lo is not None:
            m &= ts >= lo
        if hi is not None:
            m &= ts < hi
        d = d[m].reset_index(drop=True)
    if len(d) < MEMORY * 4:
        return None
    C = d.c.to_numpy(dtype=np.float64)
    HI = d.h.to_numpy(dtype=np.float64)
    LO = d.l.to_numpy(dtype=np.float64)
    n = len(C)
    cs = pd.Series(C)
    fw = cs.shift(-WIN_H) / cs - 1.0
    win = (fw > 0).astype(float).where(fw.notna())
    rate = win.rolling(WINDOW, min_periods=WINDOW // 2).mean().shift(WIN_H)
    vel = rate - rate.shift(DELTA)
    acc = vel - vel.shift(DELTA)
    p_ = rate.clip(0.01, 0.99)
    se = np.sqrt(p_ * (1 - p_) / (WINDOW / WIN_H))
    zv = (vel / (se * np.sqrt(2))).to_numpy()
    za = (acc / (se * 2.0)).to_numpy()
    # ⚠ 결손 구간을 살아있다고 보면 안 된다. 5분 안에 1분봉이 몇 개였나로 판단.
    live = (d.n.rolling(12).median().shift(1) >= cfg.min_bars_in_5).to_numpy()
    # ⚠ 워밍업으로 앞을 더 읽었으므로 **거래 가능 구간**을 여기서 정한다.
    #   밖에서 tz 를 다시 맞추려다 두 번 깨졌다.
    tsu = pd.to_datetime(d.ts, utc=True)
    tradeable = (tsu >= pd.Timestamp(d_from, tz="UTC")).to_numpy() if d_from \
        else np.ones(n, bool)
    return {"ts": tsu.to_numpy(), "C": C, "HI": HI, "LO": LO,
            "zv": zv, "za": za, "live": live, "n": n, "ok_win": tradeable}


def exits(s, cfg: Cfg) -> np.ndarray:
    """(익절, 손절) 마다 각 봉에 진입했다면 순수익(%). shape (칸, n)."""
    n, C, HI, LO = s["n"], s["C"], s["HI"], s["LO"]
    BIG = HOLD + 1
    k_tp = {tp: np.full(n, BIG, np.int32) for tp in TPS if tp}
    k_sl = {sl: np.full(n, BIG, np.int32) for sl in SLS if sl}
    sl_ret = {sl: np.full(n, np.nan) for sl in SLS if sl}
    for k in range(1, HOLD + 1):
        h = np.full(n, np.nan); h[:n-k] = HI[k:]
        l = np.full(n, np.nan); l[:n-k] = LO[k:]
        cc = np.full(n, np.nan); cc[:n-k] = C[k:]
        for tp, arr in k_tp.items():
            arr[(arr == BIG) & (h >= C * (1 + tp / 100.0))] = k
        for sl, arr in k_sl.items():
            m = (arr == BIG) & (l <= C * (1 - sl / 100.0))
            arr[m] = k
            if m.any():
                sl_ret[sl][m] = np.minimum(-sl, (cc[m] / C[m] - 1.0) * 100.0)
    tr = np.full(n, np.nan)
    tr[:n-HOLD] = (C[HOLD:] / C[:n-HOLD] - 1.0) * 100.0
    out = np.empty((len(KEYS), n), dtype=np.float32)
    for k in KEYS:
        r = tr.copy()
        kt = k_tp[k[0]] if k[0] else np.full(n, BIG, np.int32)
        ks = k_sl[k[1]] if k[1] else np.full(n, BIG, np.int32)
        if k[0]:
            r[(kt < ks) & (kt <= HOLD)] = k[0]        # 지정가 → 그 가격
        if k[1]:
            # ⚠ 같은 봉에 둘 다 닿으면 **손절 먼저**로 본다(보수적)
            m = (ks <= kt) & (ks <= HOLD)
            r[m] = sl_ret[k[1]][m]
        out[KIDX[k]] = r - cfg.fee_pct
    return out


def realize(net: np.ndarray, grp, sym: np.ndarray, zv: np.ndarray, cfg: Cfg):
    """슬롯 실현 — 자본을 슬롯으로 나눠 복리. `grp`=(봉색인, 시작, 끝)."""
    held: dict = {}
    equity, ts_out, m_out, all_ret = 1.0, [], [], []
    for tb, a, b in grp:
        for k in [k for k, v in held.items() if v[0] <= tb]:
            _, stake, nt = held.pop(k)
            equity += stake * nt / 100.0
        free = cfg.slots - len(held)
        if free <= 0:
            continue
        sl_ = slice(a, b)
        cs, cz, cn = sym[sl_], zv[sl_], net[sl_]
        ok = np.isfinite(cn)
        for i, sy in enumerate(cs):
            if ok[i] and sy in held:
                ok[i] = False
        ii = np.where(ok)[0]
        if not len(ii):
            continue
        ii = ii[np.argsort(cz[ii], kind="stable")][:free]
        stake = equity / cfg.slots
        for i in ii:
            held[cs[i]] = (tb + HOLD, stake, float(cn[i]))
        all_ret.extend(cn[ii].tolist())
        ts_out.append(tb); m_out.append(float(cn[ii].mean()))
    for _, (_, stake, nt) in held.items():
        equity += stake * nt / 100.0
    # ⚠ 복리 총손익만 보면 **엣지가 아니라 사이징을 재게 된다**. 거래 7만 건에
    #   10% 사이징이면 (0.1σ)²/2 변동성 손실만으로 -30~45% 가 깎이고 위약도
    #   같이 죽어 가르는 힘이 사라진다(예비비행 실측: 관측 -58%, 위약 -92%).
    #   그래서 **단리 합계**(거래당 평균 × 거래수 ÷ 슬롯)를 같이 낸다.
    ret = np.asarray(all_ret)
    simple = float(ret.sum() / cfg.slots) if len(ret) else 0.0
    return ((equity - 1.0) * 100.0, simple, len(ret),
            float(ret.mean()) if len(ret) else np.nan,
            np.asarray(ts_out, np.int64), np.asarray(m_out))


def blocks(tb: np.ndarray, m: np.ndarray, cfg: Cfg) -> pd.Series:
    return pd.Series(m).groupby(tb // cfg.block_bars).mean()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--smoke", type=int, default=0)
    p.add_argument("--slots", type=int, default=None)
    p.add_argument("--reps", type=int, default=500)
    p.add_argument("--from", dest="d_from", default="",
                   help="구간 제한 — 5분봉 근사가 신호를 뭉갰는지 확인할 때 쓴다")
    p.add_argument("--to", dest="d_to", default="")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    cfg = Cfg(**({"slots": a.slots} if a.slots is not None else {}))
    log.info("설정 %s · 격자 %d칸 · 기억 %d봉(%d분)",
             json.dumps(asdict(cfg), ensure_ascii=False), len(KEYS),
             MEMORY, MEMORY * BAR)

    fs = sorted(CACHE.glob("*.parquet"))
    if a.smoke:
        fs = fs[:a.smoke]
    if not fs:
        raise SystemExit(f"캐시가 없다: {CACHE}\n"
                         f"  만들기: python3 -m scripts.research.build_bars5m")
    t0, parts, EX = time.time(), [], {}
    for i, f in enumerate(fs, 1):
        s = build(f, cfg, a.d_from, a.d_to)
        if s is None:
            continue
        E = exits(s, cfg)
        ok = (s["live"] & (s["zv"] >= Z_LO) & (s["zv"] <= Z_HI)
              & (s["za"] < ACC_MAX))
        ok &= s["ok_win"]        # 워밍업 구간은 **거래하지 않는다**
        idx = np.where(ok)[0]
        if not len(idx):
            continue
        si = len(EX)
        d = {"ts": s["ts"][idx], "sym": si, "zv": s["zv"][idx], "ri": idx}
        for k in KEYS:
            d[COLS[k]] = E[KIDX[k]][idx]
        parts.append(pd.DataFrame(d))
        EX[si] = (E, s["n"] - HOLD - 1)
        if i % 20 == 0:
            log.info("[%d/%d] 후보 %s · %.1f분", i, len(fs),
                     f"{sum(len(x) for x in parts):,}", (time.time()-t0)/60)
    P = pd.concat(parts, ignore_index=True).sort_values("ts").reset_index(drop=True)
    # 봉 색인을 **전역 시간축**으로 통일한다 — 종목마다 시작이 다르다
    EPOCH = pd.Timestamp("1970-01-01", tz="UTC")
    tb = ((pd.to_datetime(P.ts, utc=True) - EPOCH)
          // pd.Timedelta(minutes=BAR)).to_numpy()
    log.info("후보 %s건 · 종목 %d · 봉시각 %s · %.1f분", f"{len(P):,}",
             P.sym.nunique(), f"{len(np.unique(tb)):,}", (time.time()-t0)/60)

    u, st = np.unique(tb, return_index=True)
    en = np.r_[st[1:], len(tb)]
    grp = list(zip(u.tolist(), st.tolist(), en.tolist()))
    symc = P.sym.to_numpy(); zvv = P.zv.to_numpy()
    sidx = P.sym.to_numpy(); ridx = P.ri.to_numpy()
    POS = {si: np.where(sidx == si)[0] for si in EX}

    rows, BLK = [], {}
    for k in KEYS:
        tot, simp, ntr, per, tbo, mo = realize(
            P[COLS[k]].to_numpy(np.float64), grp, symc, zvv, cfg)
        b = blocks(tbo, mo, cfg)
        v = b.to_numpy(); h = len(v) // 2
        def _t(x):
            return (float(x.mean()/(x.std(ddof=1)/np.sqrt(len(x))))
                    if len(x) > 2 and x.std(ddof=1) > 0 else np.nan)
        BLK[k] = b
        rows.append({"익절": k[0] or "―", "손절": k[1] or "―",
                     "단리합": simp, "총손익": tot, "거래": ntr, "거래당": per,
                     "블록": len(v), "블록평균": float(v.mean()), "t": _t(v),
                     "전반": float(v[:h].mean()), "후반": float(v[h:].mean()),
                     "t후반": _t(v[h:])})
    R = pd.DataFrame(rows).sort_values("단리합", ascending=False)
    print(f"\n■ 슬롯 {cfg.slots} · 보유 {HOLD*BAR}분 · 시각 가중 · 마찰 {cfg.fee_pct}%")
    print(R.to_string(index=False, float_format=lambda x: f"{x:.4f}"))

    # ── 짝지은 대조 + 회전 위약(한쪽) ──────────────────────
    bs = BLK[BASE]
    drows = []
    for k in KEYS:
        if k == BASE:
            continue
        j = BLK[k].index.intersection(bs.index)
        d = (BLK[k].loc[j] - bs.loc[j]).to_numpy()
        if len(d) < 5 or d.std(ddof=1) <= 0:
            continue
        h = len(d) // 2
        drows.append({"익절": k[0] or "―", "손절": k[1] or "―",
                      "단리합차": float(R.loc[(R.익절 == (k[0] or "―")) &
                                             (R.손절 == (k[1] or "―")),
                                             "단리합"].iloc[0]
                                       - R.loc[(R.익절 == "―") & (R.손절 == "―"),
                                               "단리합"].iloc[0]),
                      "블록차": float(d.mean()),
                      "t짝": float(d.mean()/(d.std(ddof=1)/np.sqrt(len(d)))),
                      "후반차": float(d[h:].mean())})
    D = pd.DataFrame(drows).sort_values("단리합차", ascending=False)
    print("\n■ 짝지은 대조 — 동결 규칙(익절·손절 없음) 대비")
    print(D.to_string(index=False, float_format=lambda x: f"{x:.4f}"))

    rng = np.random.default_rng(cfg.seed)
    V = np.empty((len(KEYS), len(P)), np.float32)
    null = np.empty(a.reps); dnull = np.empty(a.reps); hnull = np.empty(a.reps)
    for r_ in range(a.reps):
        for si, (arr, lim) in EX.items():
            pos = POS.get(si)
            if pos is None or not len(pos):
                continue
            # ⚠ 시프트 하한 = 신호 기억(교훈#108). 회차당 종목 하나(교훈#95).
            sh = int(rng.integers(MEMORY, max(lim - MEMORY, MEMORY + 1)))
            V[:, pos] = arr[:, (ridx[pos] + sh) % lim]
        tots = {}
        for k in KEYS:
            # [1] = 단리합. 복리는 변동성 손실이 지배해 판정을 못 한다.
            tots[k] = realize(V[KIDX[k]].astype(np.float64),
                              grp, symc, zvv, cfg)[1]
        # ⚠ **부호 있는** 최대다. abs 를 쓰면 전 칸이 음수인 판에서 가장 나쁜
        #   칸을 관측값으로 집는다(예비비행에서 실제로 그랬다).
        null[r_] = max(tots.values())
        dnull[r_] = max(tots[k] - tots[BASE] for k in KEYS if k != BASE)
        hnull[r_] = min(tots[k] - tots[BASE] for k in KEYS if k != BASE)
        if (r_ + 1) % 20 == 0:
            log.info("위약 %d/%d · %.1f분", r_+1, a.reps, (time.time()-t0)/60)
    obs = float(R.단리합.max())
    dobs, hobs = float(D.단리합차.max()), float(D.단리합차.min())
    print(f"\n■ 회전 위약 ({a.reps}회 · {len(KEYS)}칸 · **단리합** 기준)")
    print(f"  ⓪ 절대  관측 {obs:+.2f}% · 귀무 중앙 {np.median(null):+.2f}% "
          f"· 95분위 {np.quantile(null,.95):+.2f}%  **p = {(null>=obs).mean():.3f}**")
    print(f"  ① 개선  관측 {dobs:+.2f}% · 귀무 중앙 {np.median(dnull):+.2f}% "
          f"· 95분위 +{np.quantile(dnull,.95):.2f}%  **p = {(dnull>=dobs).mean():.3f}**")
    print(f"  ② 해로움 관측 {hobs:+.2f}% · 귀무 중앙 {np.median(hnull):+.2f}% "
          f"· 5분위 {np.quantile(hnull,.05):.2f}%  **p = {(hnull<=hobs).mean():.3f}**")
    OUT.mkdir(parents=True, exist_ok=True)
    R.to_csv(OUT / f"kine_long_s{cfg.slots}.csv", index=False)
    D.to_csv(OUT / f"kine_long_paired_s{cfg.slots}.csv", index=False)
    log.info("저장 · %.1f분", (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
