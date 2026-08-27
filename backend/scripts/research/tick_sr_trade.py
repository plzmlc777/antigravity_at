"""레벨을 실제로 거래하면 뭐가 나오나 — 익절을 미리 박지 않고 잰다.

## 왜 MFE·MAE 인가 (2026-08-27)

익절 몇 %를 먼저 정하고 재면 그 숫자를 정당화하는 답만 나온다. 그래서 정하지
않는다. 터치 이후 **얼마까지 유리하게 갔나(MFE)** 와 **얼마까지 불리하게
갔나(MAE)** 를 그대로 뽑으면, 익절·손절을 얼마로 잡아야 하는지가 자료에서 나온다.

    지지 롱  진입 = 레벨(지정가)   MFE = (구간최고 − 레벨)/레벨
                                   MAE = (레벨 − 구간최저)/레벨
    저항 숏  진입 = 레벨(지정가)   MFE = (레벨 − 구간최저)/레벨
                                   MAE = (구간최고 − 레벨)/레벨

⚠ 진입가는 **레벨 그 자체**다. 레벨에 지정가를 걸어두고 가격이 거기 닿아야
  체결된 것으로 본다(밴드 안에 들어온 것만으로는 안 친다). 지정가는 체결되면
  그 가격이다 — 슬리피지를 다시 걱정하지 않는다(대표님 지시 2026-08-22).

## 대조군 둘 — 하나만으로는 부족하다

  ① 무작위 시각   같은 종목·같은 방향·같은 구간, 앵커만 아무 데나.
                  이게 없으면 그날의 표류를 레벨 효과로 읽는다.
  ② 반대 방향     같은 앵커에서 반대로. 손절·익절 규칙이 버는지 방향이
                  버는지 가른다(교훈#91).

⚠ 표본이 **하루**다. 357종목을 모아도 같은 장 하나다 — 종목 간 상관이 커서
  유의성이 부풀려진다. 이건 결론이 아니라 **한 사례**다.

사용:
  python3 -m scripts.research.tick_sr_trade --smoke 10
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
SR = ROOT / "runs" / "research_track" / "tick_sr" / "tick_sr_24h.csv"
OUT = ROOT / "runs" / "research_track" / "tick_sr"

log = logging.getLogger("sr_trade")
HORIZONS = (15, 30, 60, 120, 240)      # 분
# 익절·손절 격자 — 도달 **시각**을 적어 두면 나중에 어떤 조합이든 재조립된다.
# ⚠ MFE·MAE 만으로는 순서를 모른다. 손절이 먼저 왔는데 익절률로 세면 다 이긴다.
LEVELS_PCT = (0.5, 1.0, 1.5, 2.0, 2.4, 3.0, 4.0, 5.0)
CAP_MIN = 240                          # 이 시간 안에 못 닿으면 미도달


@dataclass(frozen=True)
class Cfg:
    hours: int = 24
    min_sep_bp: float = 50.0    # 재진입 재무장 거리 — 한 번 붙으면 떨어져야 다시
    n_control: int = 20         # 종목당 무작위 앵커 수
    min_ticks: int = 2_000
    seed: int = 20260827


def _ohlc_1m(t: pd.DataFrame) -> pd.DataFrame:
    g = t.groupby(t.ts_ms // 60_000)
    return pd.DataFrame({"hi": g.price.max(), "lo": g.price.min(),
                         "cl": g.price.last()}).reset_index(drop=True)


def _excursions(hi: np.ndarray, lo: np.ndarray, i: int, entry: float,
                long: bool) -> dict:
    """앵커 i 이후 각 지평의 MFE·MAE(%). 구간이 안 여물면 NaN — 잘라 쓰지 않는다."""
    out = {}
    for h in HORIZONS:
        j = i + h
        if j > len(hi):
            out[f"mfe_{h}"] = np.nan
            out[f"mae_{h}"] = np.nan
            out[f"ret_{h}"] = np.nan
            continue
        top, bot = float(hi[i:j].max()), float(lo[i:j].min())
        cl = float(hi[j - 1] + lo[j - 1]) / 2.0
        if long:
            out[f"mfe_{h}"] = 100.0 * (top - entry) / entry
            out[f"mae_{h}"] = 100.0 * (entry - bot) / entry
            out[f"ret_{h}"] = 100.0 * (cl - entry) / entry
        else:
            out[f"mfe_{h}"] = 100.0 * (entry - bot) / entry
            out[f"mae_{h}"] = 100.0 * (top - entry) / entry
            out[f"ret_{h}"] = 100.0 * (entry - cl) / entry
    return out


def _first_hit(hi: np.ndarray, lo: np.ndarray, i: int, entry: float,
               long: bool) -> dict:
    """+x% / −y% 에 **처음 닿은 분**. 안 닿으면 NaN.

    이걸 적어 두면 익절·손절 어떤 조합이든 `t_up < t_dn` 한 번으로 판정된다.
    """
    j = min(i + CAP_MIN, len(hi))
    if j - i < 2:
        return {}
    up = 100.0 * ((hi[i:j] - entry) if long else (entry - lo[i:j])) / entry
    dn = 100.0 * ((entry - lo[i:j]) if long else (hi[i:j] - entry)) / entry
    cu, cd = np.maximum.accumulate(up), np.maximum.accumulate(dn)
    out = {"n_fwd": j - i}
    for x in LEVELS_PCT:
        iu = np.argmax(cu >= x) if (cu >= x).any() else -1
        idn = np.argmax(cd >= x) if (cd >= x).any() else -1
        out[f"tup_{x}"] = float(iu) if iu >= 0 else np.nan
        out[f"tdn_{x}"] = float(idn) if idn >= 0 else np.nan
    return out


def one(sym: str, level: float, side: str, cfg: Cfg, cut_ms: int,
        rng: np.random.Generator) -> list[dict]:
    d = TICKS / sym
    fs = sorted(d.glob("*.parquet"))[-2:] if d.is_dir() else []
    if not fs:
        return []
    t = pd.concat([pd.read_parquet(f, columns=["ts_ms", "price", "qty"])
                   for f in fs], ignore_index=True)
    t = t[(t.ts_ms >= cut_ms) & (t.price > 0) & (t.qty > 0)]
    if len(t) < cfg.min_ticks:
        return []
    b = _ohlc_1m(t.sort_values("ts_ms"))
    hi, lo = b.hi.to_numpy(float), b.lo.to_numpy(float)
    if len(hi) < max(HORIZONS) + 10:
        return []
    long = side == "지지"
    sep = level * cfg.min_sep_bp / 1e4

    rows: list[dict] = []
    # ── 실측: 레벨에 걸어둔 지정가가 채워지는 순간마다
    armed = True
    for i in range(len(hi)):
        touched = lo[i] <= level if long else hi[i] >= level
        if touched and armed:
            r = {"symbol": sym, "arm": "실측", "side": side, "i": i,
                 "entry": level}
            r.update(_excursions(hi, lo, i, level, long))
            r.update(_first_hit(hi, lo, i, level, long))
            rows.append(r)
            armed = False
        elif not armed:
            away = (lo[i] - level) if long else (level - hi[i])
            if away >= sep:
                armed = True

    # ── 대조 ①: 무작위 시각, 같은 방향. 진입가는 그때 종가
    for k in rng.choice(len(hi) - max(HORIZONS), size=min(
            cfg.n_control, max(len(hi) - max(HORIZONS), 1)), replace=False):
        e = float(b.cl.iloc[int(k)])
        r = {"symbol": sym, "arm": "무작위", "side": side, "i": int(k), "entry": e}
        r.update(_excursions(hi, lo, int(k), e, long))
        r.update(_first_hit(hi, lo, int(k), e, long))
        rows.append(r)

    # ── 대조 ②: 같은 앵커에서 반대 방향 — 규칙이 버는지 방향이 버는지 가른다
    for r0 in [x for x in rows if x["arm"] == "실측"]:
        r = {"symbol": sym, "arm": "반대", "side": side, "i": r0["i"],
             "entry": r0["entry"]}
        r.update(_excursions(hi, lo, r0["i"], r0["entry"], not long))
        r.update(_first_hit(hi, lo, r0["i"], r0["entry"], not long))
        rows.append(r)
    return rows


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--sr", default="")
    p.add_argument("--smoke", type=int, default=0)
    p.add_argument("--out", default="")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    cfg = Cfg()
    log.info("설정 %s", json.dumps(asdict(cfg), ensure_ascii=False))

    sr = pd.read_csv(Path(a.sr) if a.sr else SR)
    if a.smoke:
        sr = sr.head(a.smoke)
    cut_ms = int((time.time() - cfg.hours * 3600) * 1000)
    rng = np.random.default_rng(cfg.seed)
    log.info("레벨 거래 실측 — %d종목", len(sr))

    t0, rows = time.time(), []
    for i, r in enumerate(sr.itertuples(), 1):
        try:
            rows += one(r.symbol, float(r.level), r.side, cfg, cut_ms, rng)
        except Exception as e:                                  # noqa: BLE001
            log.warning("%s 실패: %s", r.symbol, str(e)[:100])
        if i % 50 == 0 or i == len(sr):
            el = time.time() - t0
            log.info("[%d/%d] 사건 %s · %.1f분 · 남은 %.1f분", i, len(sr),
                     f"{len(rows):,}", el / 60, (len(sr) - i) * el / i / 60)

    R = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    path = Path(a.out) if a.out else OUT / "tick_sr_trade.csv"
    R.to_csv(path, index=False)
    log.info("저장 %s — %s행 · %.1f분", path, f"{len(R):,}", (time.time() - t0) / 60)

    print(f"\n■ 사건 수 — {dict(R.arm.value_counts())}")
    for h in HORIZONS:
        print(f"\n■ {h}분 지평 (여문 사건만)")
        sub = R.dropna(subset=[f"mfe_{h}"])
        g = sub.groupby("arm").agg(
            n=("symbol", "size"),
            MFE중앙=(f"mfe_{h}", "median"), MFE평균=(f"mfe_{h}", "mean"),
            MAE중앙=(f"mae_{h}", "median"), MAE평균=(f"mae_{h}", "mean"),
            순익평균=(f"ret_{h}", "mean"), 순익중앙=(f"ret_{h}", "median"))
        print(g.round(3).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
