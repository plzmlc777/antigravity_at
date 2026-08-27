"""띠 **경계**에서 진입한다 — 중심이 아니라.

## 왜 (2026-08-27)

거래대금 최대 가격대로 지지·저항을 뽑았더니 전부 **띠의 한가운데**였다.
GPSUSDT 의 "지지선 0.0095105" 는 실제로 중심선(0.0094935)이었다. 횡보장에서
거래대금 최빈 가격대는 구조적으로 VWAP 근처에 생기기 때문이다. 중심은 자주
지나가고(45회) 되튕기지 않으며 거기서 진입하면 진다 — 실측으로 확인했다.

아직 안 잰 것이 **경계**다. GPSUSDT 경계는 7.28% 벌어져 있었다. 경계에서
들어가 중심에서 나오면 한 번에 3.6%, 수수료의 100배다.

## 미래참조를 막는 방식

⚠ 24시간 전체의 고·저로 경계를 그으면 **그 경계는 나중에야 알 수 있다**.
  이 트랙은 같은 실수로 85거래를 날린 적이 있다. 그래서 경계는 **직전 W분**
  에서만 만들고, 그 봉에서 앞으로 나아간다. band 는 t-1 까지만 본다.

## 규칙

    띠      sup = 직전 W분 최저(또는 하위 q분위) · res = 최고(상위 q분위)
    진입    저점이 sup 에 닿으면 **롱**(지정가 sup) · 고점이 res 에 닿으면 **숏**
    익절    sup + tp_frac × 띠폭    (0.5 = 중심)
    손절    sup − sl_frac × 띠폭    (경계 바깥)
    같은 봉에서 둘 다 닿으면 **손절 우선** — 낙관 금지

## 대조군

    반대     같은 자리에서 반대 방향(=경계 이탈 추종). 규칙이 버는지 방향이
             버는지 가른다(교훈#91)
    무작위   같은 종목·같은 방향, 진입 시각만 아무 데나. 그날 표류를 규칙
             효과로 읽지 않기 위해

⚠ **총손익으로 판정한다.** 거래당 엣지만 보면 결론이 뒤집힌다 — 빈도가
  결합돼야 한다(대표님 지시).

⚠ 표본은 하루다. 격자를 뒤지므로 칸별 p 는 못 믿는다(교훈#95).

사용:
  python3 -m scripts.research.tick_band_edge --smoke 10
"""
from __future__ import annotations

import argparse
import itertools
import json
import logging
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
TICKS = ROOT / "runs" / "ticks"
OUT = ROOT / "runs" / "research_track" / "tick_sr"
log = logging.getLogger("band_edge")


@dataclass(frozen=True)
class Cfg:
    hours: int = 24
    hold: int = 360            # 최대 보유(분)
    min_width_pct: float = 1.0  # 띠가 이보다 좁으면 안 거래한다 — 수수료 밑
    fee_pct: float = 0.036     # 지정가 왕복(메이커 0.018×2)
    n_control: int = 30        # 종목당 무작위 앵커
    min_ticks: int = 2_000
    seed: int = 20260827


BAND_WINS = (180, 360, 720)
TP_FRACS = (0.35, 0.5, 0.75)
SL_FRACS = (0.35, 0.5)
# 경계에서 얼마나 **물러나** 살 것인가(bp). 0 은 최저 체결가 그 자리다.
# ⚠ 0 만 재면 호가 튐을 알파로 착각한다 — 최저가는 얇은 호가를 때린 한 건일 수
#   있고, 그 뒤 되돌림은 스프레드지 되돌림이 아니다. 물러나도 남아야 진짜다.
BUFS_BP = (0.0, 5.0, 10.0, 20.0)


def _walk(hi, lo, i, entry, tp, sl, long, hold) -> tuple[float, str, int]:
    """진입 후 익절·손절·만기 중 먼저 오는 것. 같은 봉 동시 도달은 손절 우선.

    ⚠ **진입 봉부터 본다.** 경계 진입은 극단에서 채워지므로 그 봉이 더 내려가
      손절선을 뚫었을 수 있다. i+1 부터 보면 그 손절이 통째로 사라져 실측에만
      유리해진다 — 무작위 대조군은 중간에서 들어가 이 편향을 안 받는다.
      봉 안 순서는 모르므로 보수적으로 **체결 후 계속 갔다**고 본다.
    """
    j = min(i + hold, len(hi) - 1)
    if long and lo[i] <= sl:
        return 100.0 * (sl - entry) / entry, "손절", 0
    if (not long) and hi[i] >= sl:
        return 100.0 * (entry - sl) / entry, "손절", 0
    for k in range(i + 1, j + 1):
        if long:
            if lo[k] <= sl:
                return 100.0 * (sl - entry) / entry, "손절", k - i
            if hi[k] >= tp:
                return 100.0 * (tp - entry) / entry, "익절", k - i
        else:
            if hi[k] >= sl:
                return 100.0 * (entry - sl) / entry, "손절", k - i
            if lo[k] <= tp:
                return 100.0 * (entry - tp) / entry, "익절", k - i
    c = (hi[j] + lo[j]) / 2.0
    r = 100.0 * (c - entry) / entry
    return (r if long else -r), "만기", j - i


def one(sym: str, cfg: Cfg, cut_ms: int, rng) -> list[dict]:
    d = TICKS / sym
    fs = sorted(d.glob("*.parquet"))[-2:] if d.is_dir() else []
    if not fs:
        return []
    t = pd.concat([pd.read_parquet(f, columns=["ts_ms", "price", "qty"])
                   for f in fs], ignore_index=True)
    t = t[(t.ts_ms >= cut_ms) & (t.price > 0) & (t.qty > 0)]
    if len(t) < cfg.min_ticks:
        return []
    t = t.sort_values("ts_ms")
    g = t.groupby(t.ts_ms // 60_000)
    H = g.price.max().to_numpy(float)
    L = g.price.min().to_numpy(float)
    C = g.price.last().to_numpy(float)
    # ⚠ 봉 **번호**만 남기면 나중에 다른 표와 못 붙인다. 창 시작이 다르면
    #   10시간씩 어긋난 채 100% 매칭됐다고 보고된다(2026-08-27 실측).
    #   시각은 지어내지 말고 자료에서 가져온다.
    TS = pd.to_datetime(g.price.max().index.to_numpy() * 60_000,
                        unit="ms", utc=True)
    n = len(C)
    if n < max(BAND_WINS) + cfg.hold + 10:
        return []
    sH, sL = pd.Series(H), pd.Series(L)

    rows = []
    for W in BAND_WINS:
        # ⚠ shift(1) — 이 봉은 아직 못 본다. 이게 미래참조를 막는 한 줄이다.
        res = sH.rolling(W).max().shift(1).to_numpy()
        sup = sL.rolling(W).min().shift(1).to_numpy()
        width = res - sup
        ok = np.isfinite(sup) & (width / np.maximum(sup, 1e-12) * 100
                                 >= cfg.min_width_pct)
        for tpf, slf, buf in itertools.product(TP_FRACS, SL_FRACS, BUFS_BP):
            busy = -1
            for i in range(W, n - cfg.hold):
                if i <= busy or not ok[i]:
                    continue
                w = width[i]
                for long in (True, False):
                    edge = (sup[i] * (1 + buf / 1e4) if long
                            else res[i] * (1 - buf / 1e4))
                    hit = (L[i] <= edge) if long else (H[i] >= edge)
                    if not hit:
                        continue
                    tp = edge + tpf * w if long else edge - tpf * w
                    sl = edge - slf * w if long else edge + slf * w
                    for arm, dirn in (("실측", long), ("반대", not long)):
                        tp2 = tp if dirn == long else (edge - tpf * w if long
                                                       else edge + tpf * w)
                        sl2 = sl if dirn == long else (edge + slf * w if long
                                                       else edge - slf * w)
                        r, why, mins = _walk(H, L, i, edge, tp2, sl2,
                                             dirn, cfg.hold)
                        rows.append({"symbol": sym, "ts": TS[i],
                                     "W": W, "tpf": tpf,
                                     "slf": slf, "buf": buf, "arm": arm,
                                     "side": "지지" if long else "저항",
                                     "dir": "롱" if dirn else "숏",
                                     "i": i, "width_pct": 100.0 * w / edge,
                                     "ret": r, "net": r - cfg.fee_pct,
                                     "why": why, "mins": mins})
                    busy = i + mins
                    break
            # 무작위 대조 — 같은 방향 분포, 진입 시각만 무작위
            idx = [x for x in range(W, n - cfg.hold) if ok[x]]
            if not idx:
                continue
            for k in rng.choice(idx, size=min(cfg.n_control, len(idx)),
                                replace=False):
                k = int(k); w = width[k]
                for long in (True, False):
                    edge = C[k]
                    tp = edge + tpf * w if long else edge - tpf * w
                    sl = edge - slf * w if long else edge + slf * w
                    r, why, mins = _walk(H, L, k, edge, tp, sl, long, cfg.hold)
                    rows.append({"symbol": sym, "ts": TS[k],
                                 "W": W, "tpf": tpf, "slf": slf,
                                 "buf": buf, "arm": "무작위",
                                 "side": "지지" if long else "저항",
                                 "dir": "롱" if long else "숏", "i": k,
                                 "width_pct": 100.0 * w / edge, "ret": r,
                                 "net": r - cfg.fee_pct, "why": why,
                                 "mins": mins})
    return rows


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
    log.info("격자 — 띠창 %s · 익절비 %s · 손절비 %s", BAND_WINS, TP_FRACS, SL_FRACS)

    syms = [s.strip().upper() for s in
            (ROOT / a.universe).read_text().split() if s.strip()]
    if a.smoke:
        syms = syms[:a.smoke]
    cut_ms = int((time.time() - cfg.hours * 3600) * 1000)
    rng = np.random.default_rng(cfg.seed)
    t0, parts = time.time(), []
    for i, s in enumerate(syms, 1):
        try:
            r = one(s, cfg, cut_ms, rng)
        except Exception as e:                                  # noqa: BLE001
            log.warning("%s 실패: %s", s, str(e)[:100]); r = []
        if r:
            parts.append(pd.DataFrame(r))
        if i % 50 == 0 or i == len(syms):
            el = time.time() - t0
            log.info("[%d/%d] %s건 · %.1f분 · 남은 %.1f분", i, len(syms),
                     f"{sum(len(x) for x in parts):,}", el / 60,
                     (len(syms) - i) * el / i / 60)
    if not parts:
        raise SystemExit("한 건도 못 냈다 — 띠 최소폭·창 길이를 확인하라")
    R = pd.concat(parts, ignore_index=True)
    OUT.mkdir(parents=True, exist_ok=True)
    path = Path(a.out) if a.out else OUT / "tick_band_edge.csv"
    R.to_csv(path, index=False)
    log.info("저장 %s — %s행 · %.1f분", path, f"{len(R):,}", (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
