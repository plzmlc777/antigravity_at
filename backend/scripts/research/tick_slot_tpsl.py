"""익절·손절을 **슬롯 실현**으로 다시 잰다 — 사건 풀링이 아니라 시각 가중으로.

## 왜 (2026-08-30)

`tick_kinematics_tpsl.py` 를 교훈#108(시프트 하한)로 고쳐 다시 돌렸더니
**판정이 뒤집혔다** — 관측 최대 |z| 13.87 · 위약 중앙 1.57 · p 0.000.
익절 1.5% · 손절 없음 · 보유 120분이 거래당 +0.1214%, 위약 대비 +0.0977%p.

그런데 그 z 는 **사건 118,422건을 독립으로 놓고** 낸 값이다. 사건은 시간에
뭉쳐 있고, 실제 전략은 5분 격자마다 **슬롯 수만큼만** 잡는다. 이 세션에서
셀 가중으로 두 번 속았다(엣지 3배·변동성필터 8배). 그래서 여기서는

    · 벽시계 5분 격자에서 z_vel 낮은 순으로 슬롯을 채운다
    · 자본을 슬롯 수로 나눠 **복리로** 굴린다  → 총손익
    · 추론 단위는 **비겹침 시각 블록**이지 거래가 아니다

## 체결 규약

    익절  지정가 → **그 가격에 체결**된다(대표님 지시: 지정가 논쟁 종결)
    손절  시장가 → 그 분의 종가가 손절선보다 나쁘면 **종가를 쓴다**(보수적).
          가격을 추정해 채우지 않는다(교훈#107)

사용:
  python3 -m scripts.research.tick_slot_tpsl --smoke 60
  python3 -m scripts.research.tick_slot_tpsl --slots 10
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
log = logging.getLogger("slottpsl")

WIN_H, WINDOW, DELTA = 60, 360, 180
Z_LO, Z_HI, ACC_MAX = -1.25, -0.25, 0.5          # 동결 밴드
STEP, HOLD = 5, 120
TPS = (None, 1.0, 1.5, 2.0, 3.0)
SLS = (None, 1.5, 2.0, 3.0)
MEMORY = WINDOW + DELTA + WIN_H + HOLD           # 720 — 신호 기억
KEYS = [(tp, sl) for tp in TPS for sl in SLS]
KIDX = {k: i for i, k in enumerate(KEYS)}
COLS = {k: f"c{i}" for i, k in enumerate(KEYS)}


@dataclass(frozen=True)
class Cfg:
    slots: int = 10
    fee_pct: float = 0.036
    min_live_tr: float = 5.0
    min_ticks: int = 2_000
    block_min: int = 120          # 비겹침 추론 블록
    seed: int = 20260830


def build(sym: str, cfg: Cfg):
    fs = sorted((TICKS / sym).glob("*.parquet"))
    if not fs:
        return None
    try:
        t = pd.concat([pd.read_parquet(f) for f in fs], ignore_index=True)
    except Exception:                                          # noqa: BLE001
        return None
    t = t[(t.price > 0) & (t.qty > 0)]
    if len(t) < cfg.min_ticks:
        return None
    g = t.sort_values("ts_ms").groupby(t.ts_ms // 60_000)
    c, hi, lo, nt = g.price.last(), g.price.max(), g.price.min(), g.price.size()
    ix = pd.to_datetime(c.index * 60_000, unit="ms", utc=True)
    for v in (c, hi, lo, nt):
        v.index = ix
    full = pd.date_range(ix.min(), ix.max(), freq="1min", tz="UTC")
    C = c.reindex(full).ffill()
    HI = hi.reindex(full).ffill()
    LO = lo.reindex(full).ffill()
    NT = nt.reindex(full).fillna(0.0)
    if len(C) < MEMORY * 2:
        return None
    fw = C.shift(-WIN_H) / C - 1.0
    win = (fw > 0).astype(float).where(fw.notna())
    rate = win.rolling(WINDOW, min_periods=WINDOW // 2).mean().shift(WIN_H)
    vel = rate - rate.shift(DELTA)
    acc = vel - vel.shift(DELTA)
    p_ = rate.clip(0.01, 0.99)
    se = np.sqrt(p_ * (1 - p_) / (WINDOW / WIN_H))
    zv = (vel / (se * np.sqrt(2))).to_numpy()
    za = (acc / (se * 2.0)).to_numpy()
    live = (NT.rolling(60).median().shift(1) >= cfg.min_live_tr).to_numpy()
    return {"sym": sym, "ts": full, "C": C.to_numpy(), "HI": HI.to_numpy(),
            "LO": LO.to_numpy(), "zv": zv, "za": za, "live": live,
            "n": len(C), "minute": full.minute.to_numpy()}


def exits(s, cfg: Cfg) -> dict:
    """(익절, 손절) 조합마다 **각 분에 진입했다면** 순수익 얼마인가."""
    n, C, HI, LO = s["n"], s["C"], s["HI"], s["LO"]
    BIG = HOLD + 1
    k_tp = {tp: np.full(n, BIG, dtype=np.int32) for tp in TPS if tp}
    k_sl = {sl: np.full(n, BIG, dtype=np.int32) for sl in SLS if sl}
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
                # ⚠ 시장가다. 그 분 종가가 손절선보다 나쁘면 **종가를 쓴다**.
                #   가격을 추정해 채우지 않는다(교훈#107).
                sl_ret[sl][m] = np.minimum(-sl, (cc[m] / C[m] - 1.0) * 100.0)
    time_ret = np.full(n, np.nan)
    time_ret[:n-HOLD] = (C[HOLD:] / C[:n-HOLD] - 1.0) * 100.0
    out = {}
    for tp in TPS:
        for sl in SLS:
            r = time_ret.copy()
            kt = k_tp[tp] if tp else np.full(n, BIG, dtype=np.int32)
            ks = k_sl[sl] if sl else np.full(n, BIG, dtype=np.int32)
            if tp:
                r[(kt < ks) & (kt <= HOLD)] = tp          # 지정가 → 그 가격
            if sl:
                m = (ks <= kt) & (ks <= HOLD)
                r[m] = sl_ret[sl][m]
            out[(tp, sl)] = r - cfg.fee_pct
    return out


def realize_np(net: np.ndarray, grp, sym: np.ndarray, zv: np.ndarray,
               cfg: Cfg) -> tuple[float, np.ndarray, np.ndarray]:
    """슬롯 실현(수치판) — 위약을 수백 회 돌리려면 DataFrame 으론 못 버틴다.

    `grp` 는 (시각(분), 시작, 끝) 목록이며 시각 오름차순으로 미리 잘라 둔다.
    돌려주는 것: 복리 총손익 · 시각별 평균 · 그 시각들
    """
    held: dict = {}
    equity, ts_out, m_out = 1.0, [], []
    for tsm, a, b in grp:
        for k in [k for k, v in held.items() if v[0] <= tsm]:
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
            held[cs[i]] = (tsm + HOLD, stake, float(cn[i]))
        ts_out.append(tsm); m_out.append(float(cn[ii].mean()))
    for _, (_, stake, nt) in held.items():
        equity += stake * nt / 100.0
    return ((equity - 1.0) * 100.0, np.asarray(ts_out, dtype=np.int64),
            np.asarray(m_out))


def realize(P: pd.DataFrame, key, cfg: Cfg) -> dict:
    """슬롯 실현 — 자본을 슬롯으로 나눠 복리."""
    # ⚠ `itertuples` 는 점이 든 컬럼명(`r_None_1.5`)을 조용히 `_4` 로 바꾼다.
    #   그래서 컬럼은 색인 이름(`c0`..)으로 두고 여기서 되찾는다.
    col = COLS[key]
    held: dict = {}
    equity, per_ts, rets = 1.0, [], []
    for ts, g in P.groupby("ts", sort=True):
        for sym in [k for k, v in held.items() if v[0] <= ts]:
            _, stake, net = held.pop(sym)
            equity += stake * net / 100.0
        free = cfg.slots - len(held)
        if free <= 0:
            continue
        g = g[~g.symbol.isin(held)].nsmallest(free, "zv")
        if g.empty:
            continue
        stake, vals = equity / cfg.slots, []
        for r in g.itertuples():
            net = getattr(r, col)
            if not np.isfinite(net):
                continue
            held[r.symbol] = (ts + pd.Timedelta(minutes=HOLD), stake, net)
            vals.append(net)
        if vals:
            rets.extend(vals)
            per_ts.append((ts, float(np.mean(vals))))
    for _, (_, stake, net) in held.items():
        equity += stake * net / 100.0
    if not per_ts:
        return {}
    T = pd.DataFrame(per_ts, columns=["ts", "m"])
    # ⚠ tz 인식 시각에 `.astype("int64")` 를 쓰면 안 된다 — 이 세션에서 이미
    #   한 번 당했고(시간 묶음이 전부 1로 뭉갬) 여기서 **또 반복했다**.
    #   기준시각을 빼서 명시적으로 나눈다.
    blk = (T.ts - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta(
        minutes=cfg.block_min)
    b = T.groupby(blk).m.mean().to_numpy()
    t = (b.mean() / (b.std(ddof=1) / np.sqrt(len(b)))
         if len(b) > 2 and b.std(ddof=1) > 0 else np.nan)
    a = np.asarray(rets)
    # ⚠ 전반·후반을 반드시 같이 낸다. 기준선이 백테스트 +0.099%/거래인데
    #   페이퍼는 -0.061%/거래다 — 감쇠인지 다른 결함인지 여기서 갈린다.
    h = len(b) // 2
    b1, b2 = b[:h], b[h:]

    def _t(v):
        return (float(v.mean() / (v.std(ddof=1) / np.sqrt(len(v))))
                if len(v) > 2 and v.std(ddof=1) > 0 else np.nan)
    return {"총손익": (equity - 1.0) * 100.0, "거래": len(a),
            "거래당": float(a.mean()), "승률": 100.0 * float((a > 0).mean()),
            "블록": len(b), "블록평균": float(b.mean()), "t": float(t),
            "전반": float(b1.mean()), "후반": float(b2.mean()),
            "t후반": _t(b2), "_blocks": (T.groupby(blk).m.mean(), b)}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--universe", default="configs/rsi_live_universe.txt")
    p.add_argument("--smoke", type=int, default=0)
    p.add_argument("--slots", type=int, default=None)
    p.add_argument("--reps", type=int, default=300, help="회전 위약 횟수")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    cfg = Cfg(**({"slots": a.slots} if a.slots is not None else {}))
    log.info("설정 %s · 격자 %d칸 · 기억 %d분",
             json.dumps(asdict(cfg), ensure_ascii=False), len(TPS)*len(SLS), MEMORY)
    syms = [s.strip().upper() for s in
            (ROOT / a.universe).read_text().split() if s.strip()]
    if a.smoke:
        syms = syms[:a.smoke]

    t0, parts, EX = time.time(), [], {}
    for i, sym in enumerate(syms, 1):
        s = build(sym, cfg)
        if s is None:
            continue
        E = exits(s, cfg)
        ok = (s["live"] & (s["zv"] >= Z_LO) & (s["zv"] <= Z_HI)
              & (s["za"] < ACC_MAX) & (s["minute"] % STEP == 0))
        idx = np.where(ok)[0]
        if not len(idx):
            continue
        d = {"ts": s["ts"][idx], "symbol": sym, "zv": s["zv"][idx],
             "sym": len(EX), "ri": idx}
        for k, v in E.items():
            d[COLS[k]] = v[idx]
        parts.append(pd.DataFrame(d))
        # 위약은 **진입시각을 회전**시킨다 — 그러려면 전체 배열이 있어야 한다.
        # float32 로 둔다(359종목 × 20칸 × 6천분 = 약 178MB).
        EX[len(EX)] = (np.stack([E[k].astype(np.float32) for k in
                                 (KEYS)]), s["n"] - HOLD - 1)
        if i % 60 == 0:
            log.info("[%d/%d] %.1f분", i, len(syms), (time.time()-t0)/60)
    P = pd.concat(parts, ignore_index=True).sort_values("ts")
    log.info("후보 %s건 · 종목 %d · 시각 %d · %.1f분", f"{len(P):,}",
             P.symbol.nunique(), P.ts.nunique(), (time.time()-t0)/60)

    rows, BLK = [], {}
    for tp in TPS:
        for sl in SLS:
            r = realize(P, (tp, sl), cfg)
            if r:
                BLK[(tp, sl)] = r.pop("_blocks")
                rows.append({"익절": tp or "―", "손절": sl or "―", **r})
    R = pd.DataFrame(rows).sort_values("총손익", ascending=False)
    # ── 최대통계량 회전 위약 ────────────────────────────────
    # ⚠ 20칸 중 최고를 골랐으므로 **같은 격자를 위약에서도 전부** 뒤진 최고가
    #   기준선이다(교훈#95). 시프트 하한은 신호 기억 720분(교훈#108).
    if EX:
        P2 = P.sort_values("ts").reset_index(drop=True)
        tsm = ((P2.ts - pd.Timestamp("1970-01-01", tz="UTC"))
               // pd.Timedelta(minutes=1)).to_numpy()
        symc = P2.symbol.astype("category").cat.codes.to_numpy()
        zvv = P2.zv.to_numpy()
        u, st = np.unique(tsm, return_index=True)
        en = np.r_[st[1:], len(tsm)]
        grp = list(zip(u.tolist(), st.tolist(), en.tolist()))
        sidx = P2.sym.to_numpy(); ridx = P2.ri.to_numpy()
        # ⚠ 종목별 행 위치를 **한 번만** 잡는다. 회차마다 전체 배열을 비교하면
        #   359종목 × 12만행 × 20칸 = 회차당 8.6억 연산이 된다.
        POS = {si: np.where(sidx == si)[0] for si in EX}
        keys = KEYS
        obs = float(R.총손익.abs().max())
        rng = np.random.default_rng(cfg.seed)
        null = np.empty(a.reps); dnull = np.empty(a.reps)
        hnull = np.empty(a.reps)     # 해로움 쪽(부호 반대) 귀무
        cell = {k: [] for k in keys}
        BASE = (None, None)
        V = np.empty((len(keys), len(P2)), dtype=np.float32)
        for r_ in range(a.reps):
            # ⚠ 시프트는 **회차당 종목 하나**다. 칸마다 따로 뽑으면 격자의
            #   상관 구조가 깨져 최대통계량이 제 뜻을 잃는다(교훈#95).
            for si, (arr, lim) in EX.items():
                pos = POS.get(si)
                if pos is None or not len(pos):
                    continue
                sh = int(rng.integers(MEMORY, max(lim - MEMORY, MEMORY + 1)))
                V[:, pos] = arr[:, (ridx[pos] + sh) % lim]
            best, tots = 0.0, {}
            for k in keys:
                tot, _, _ = realize_np(V[KIDX[k]].astype(np.float64),
                                       grp, symc, zvv, cfg)
                cell[k].append(tot); tots[k] = tot
                best = max(best, abs(tot))
            null[r_] = best
            # ⚠ 짝지은 차이 — 같은 진입·같은 시각, **청산만 다르다**.
            #   시장 표류가 상쇄되므로 "익절이 돕는가"는 이쪽이 맞는 질문이다.
            dnull[r_] = max(tots[k] - tots[BASE] for k in keys if k != BASE)
            hnull[r_] = min(tots[k] - tots[BASE] for k in keys if k != BASE)
            if (r_ + 1) % 20 == 0:
                log.info("위약 %d/%d · 귀무중앙 %.2f · %.1f분", r_+1, a.reps,
                         float(np.median(null[:r_+1])), (time.time()-t0)/60)
        pmax = float((null >= obs).mean())
        R["위약중앙"] = [float(np.median(cell[(None if r.익절 == "―" else r.익절,
                                              None if r.손절 == "―" else r.손절)]))
                        for r in R.itertuples()]
        R["초과"] = R.총손익 - R.위약중앙
        print(f"\n■ 회전 위약 최대통계량 ({a.reps}회 · {len(keys)}칸 · 총손익 기준)")
        print(f"  관측 최대 |총손익| {obs:.2f}% · 위약 중앙 {np.median(null):.2f}% "
              f"· 95분위 {np.quantile(null,.95):.2f}% · 최대 {null.max():.2f}%")
        print(f"  **p = {pmax:.3f}**")

        # ── 짝지은 대조: 익절·손절이 **동결 규칙보다** 나은가
        bs, bb = BLK[BASE]
        drows = []
        for k in keys:
            if k == BASE:
                continue
            ks_, kb = BLK[k]
            j = ks_.index.intersection(bs.index)
            d = (ks_.loc[j] - bs.loc[j]).to_numpy()
            if len(d) < 5 or d.std(ddof=1) <= 0:
                continue
            h = len(d) // 2
            d2 = d[h:]
            drows.append({
                "익절": k[0] or "―", "손절": k[1] or "―",
                "총손익차": float(R.loc[(R.익절 == (k[0] or "―")) &
                                       (R.손절 == (k[1] or "―")), "총손익"].iloc[0]
                                 - R.loc[(R.익절 == "―") & (R.손절 == "―"),
                                         "총손익"].iloc[0]),
                "블록차": float(d.mean()),
                "t짝": float(d.mean()/(d.std(ddof=1)/np.sqrt(len(d)))),
                "후반차": float(d2.mean()),
                "t후반짝": (float(d2.mean()/(d2.std(ddof=1)/np.sqrt(len(d2))))
                           if len(d2) > 2 and d2.std(ddof=1) > 0 else np.nan)})
        D = pd.DataFrame(drows).sort_values("총손익차", ascending=False)
        dobs = float(D.총손익차.max())          # 개선 — **부호 있는** 최대
        hobs = float(D.총손익차.min())          # 해로움
        dp = float((dnull >= dobs).mean())
        hp = float((hnull <= hobs).mean())
        print(f"\n■ 짝지은 대조 — 동결 규칙(익절·손절 없음) 대비")
        print(f"  같은 진입·같은 시각, **청산만 다르다** → 시장 표류가 상쇄된다")
        print(D.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
        print(f"\n  ① 개선 — 관측 최대 +{dobs:.2f}% · 귀무 중앙 "
              f"+{np.median(dnull):.2f}% · 95분위 +{np.quantile(dnull,.95):.2f}%"
              f"  **p = {dp:.3f}**")
        print(f"  ② 해로움 — 관측 최소 {hobs:.2f}% · 귀무 중앙 "
              f"{np.median(hnull):.2f}% · 5분위 {np.quantile(hnull,.05):.2f}%"
              f"  **p = {hp:.3f}**")
        D.to_csv(OUT / f"slot_tpsl_paired_s{cfg.slots}.csv", index=False)
        (OUT / f"slot_tpsl_s{cfg.slots}.null.json").write_text(json.dumps(
            {"obs": obs, "p_max": pmax, "reps": a.reps,
             "null_median": float(np.median(null)),
             "null_p95": float(np.quantile(null, .95)),
             "null_max": float(null.max())}, ensure_ascii=False, indent=1))
    print(f"\n■ 슬롯 {cfg.slots} · 보유 {HOLD}분 · 시각 가중 · 마찰 {cfg.fee_pct}%")
    print(R.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
    OUT.mkdir(parents=True, exist_ok=True)
    R.to_csv(OUT / f"slot_tpsl_s{cfg.slots}.csv", index=False)
    log.info("저장 · %.1f분", (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
