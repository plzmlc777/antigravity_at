"""R-5 시드 `volume_burst` 127/128 재검정 — 미검증 구간으로.

## 왜

    127 (LONG)   양의 1분 거래량 버스트 → 75분 지속  · TP/SL 없음
    128 (SHORT)  음의 1분 거래량 버스트 → 10분 되돌림 · **SL 0.5% 필수**

    주장 (2026-05-21 R-1~R-4 PASS)
      127  n=13,176 · net **+54.94bp** · sigex +49.83 · 13/13 ci_pos
           ann_gross **4,734%** · trades/yr 6,019
      128  n=14,843 · net **+39.80bp** · sigex +63.67 · 13/13 ci_pos
           ann_gross post-SL 1,990% · sharpe pre-SL **12.23**

⚠ **이 수치는 전부 재검증 대상이다** — 커밋 `cd0ca27f`(2026-08-08) lookahead
  수정 **이전** 기록이다. 2군 13세션 재시뮬에서 누적 +245.55% → **+11.32%**
  (성과의 **95.4%가 편향**)였다. [[project-ada-vb-pair-market-neutral]]

⚠ 연 4,734% · sharpe 12.23 은 그 자체로 경보다. 진짜면 이미 세상에 없다.

## 어떻게

  · **신호는 정본 소스에서** — `_compute_triggers` 를 그대로 호출한다.
    재구현하면 다른 걸 재게 된다(같은 날 `btc_rv_highvol` 에서 겪었다:
    내가 다시 짠 신호는 트리거가 원본의 1/13 이었다). 규칙 ⑤.
  · **미검증 창** 2021-01 ~ 2023-12. 원본은 2024~2026(joblib 캐시 구간)을
    썼으므로 이 앞 구간은 한 번도 안 봤다. BTC·ETH 1분봉을 2021 까지
    복구했으므로(2026-08-16) 이제 열린다.
  · **관측 단위는 날짜** — 이벤트가 시간에 뭉치므로 건별 t 는 부푼다(교훈 #92).
  · 마찰 **16bp/거래** (원본의 gross−net 차이와 동일하게 맞춘다).

사용:
  python3 -m scripts.research.volume_burst_127_128_revalidate \
      --start 2021-01-01 --end 2023-12-31
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("vb")

OUT = ROOT / "runs" / "research_track" / "volume_burst_127_128_revalidate.json"
ALTS = ["ADAUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOGEUSDT", "ETHUSDT",
        "FILUSDT", "LINKUSDT", "LTCUSDT", "NEARUSDT", "SOLUSDT", "WIFUSDT",
        "XRPUSDT"]


@dataclass
class VBConfig:
    start: str = "2021-01-01"
    end: str = "2023-12-31"
    fee_bp: float = 16.0        # 원본 gross−net 과 동일
    hold_long_min: int = 75     # 127
    hold_short_min: int = 10    # 128
    sl_short: float = 0.005     # 128 필수 손절
    split: str = "2022-07-01"

    def __post_init__(self):
        if self.fee_bp < 0:
            raise SystemExit("fee_bp >= 0")


def load_1m(conn, sym: str, a: str, b: str) -> pd.DataFrame:
    from sqlalchemy import text
    r = conn.execute(text(
        "SELECT timestamp, open, high, low, close, volume FROM ohlcv "
        "WHERE symbol=:s AND time_frame='1m' AND timestamp>=:a AND timestamp<=:b "
        "ORDER BY timestamp"), {"s": sym, "a": a, "b": b}).fetchall()
    if not r:
        return pd.DataFrame()
    d = pd.DataFrame(r, columns=["ts", "open", "high", "low", "close", "volume"])
    d["ts"] = pd.to_datetime(d["ts"])
    return d.set_index("ts").astype(float)


def forward(px: pd.DataFrame, t0, hold_min: int, side: int,
            sl: float, fee_bp: float) -> float | None:
    """진입은 트리거 **다음 1분봉 시가**. 손절은 보유 중 최악가로 판정."""
    i = px.index.searchsorted(t0)
    if i + 1 >= len(px):
        return None
    j = i + 1
    entry = float(px["open"].iloc[j])
    if not (entry > 0):
        return None
    seg = px.iloc[j:j + hold_min]
    if len(seg) < max(2, hold_min // 2):
        return None
    ex = float(seg["close"].iloc[-1])
    if sl > 0:
        # 숏이면 고가가, 롱이면 저가가 불리하다
        adverse = (seg["high"].max() if side < 0 else seg["low"].min())
        move = side * (float(adverse) / entry - 1.0)
        if move <= -sl:
            ex = entry * (1 - side * sl)
    return (side * (ex / entry - 1.0)) * 1e4 - fee_bp     # bp


def main() -> int:
    p = argparse.ArgumentParser(description="volume_burst 127/128 재검정")
    for f_ in VBConfig.__dataclass_fields__.values():
        p.add_argument("--" + f_.name.replace("_", "-"),
                       type=type(f_.default), default=f_.default)
    a = p.parse_args()
    cfg = VBConfig(**{k: getattr(a, k) for k in VBConfig.__dataclass_fields__})

    from app.composer_framework.sources.binance_alt_volume_burst_neg_reversion_short_source import (  # noqa: E501
        BinanceAltVolumeBurstNegReversionShortSource)
    from app.composer_framework.sources.binance_alt_volume_burst_pos_continuation_long_source import (  # noqa: E501
        BinanceAltVolumeBurstPosContinuationLongSource)
    from app.db.session import engine

    src127 = BinanceAltVolumeBurstPosContinuationLongSource()
    src128 = BinanceAltVolumeBurstNegReversionShortSource()

    rows = []
    with engine.connect() as conn:
        for s in ALTS:
            px = load_1m(conn, s, cfg.start, cfg.end)
            if px.empty or len(px) < 60_000:
                log.warning("%s 1분봉 부족(%d) — 건너뜀", s, len(px))
                continue
            for tag, src, hold, side, sl in (
                    ("127_long", src127, cfg.hold_long_min, 1, 0.0),
                    ("128_short", src128, cfg.hold_short_min, -1, cfg.sl_short)):
                try:
                    trig = src._compute_triggers(px)
                except Exception as exc:
                    log.warning("%s %s 트리거 실패: %s", s, tag, exc)
                    continue
                if trig is None or len(trig) == 0:
                    continue
                for t0 in trig.index:
                    r = forward(px, t0, hold, side, sl, cfg.fee_bp)
                    if r is not None:
                        rows.append({"paradigm": tag, "symbol": s,
                                     "ts": t0, "ret_bp": r})
            log.info("%s 완료 · 1분봉 %s · 누적 이벤트 %s",
                     s, f"{len(px):,}", f"{len(rows):,}")
    if not rows:
        raise SystemExit("이벤트 0건")
    d = pd.DataFrame(rows)

    print("=" * 100)
    print(f"  **volume_burst 127/128 재검정** — {cfg.start} ~ {cfg.end} "
          f"(원본 창 2024~2026 **이전**, 미검증)")
    print(f"  ⚠ 원본 수치는 lookahead 수정 **이전** 기록 — 2군 재시뮬에서 "
          f"성과의 **95.4%가 편향**이었다")
    print(f"  마찰 {cfg.fee_bp:.0f}bp/거래 · 관측 단위 **날짜**(이벤트가 뭉친다)")
    print("=" * 100)
    print(f"\n  {'패러다임':<12}{'이벤트':>8}{'평균bp':>10}{'중앙bp':>10}"
          f"{'승률%':>8}{'건별t':>8}{'날짜n':>7}{'날짜t':>8}")
    res = {"config": asdict(cfg)}
    claim = {"127_long": 54.94, "128_short": 39.80}
    for tag, g in d.groupby("paradigm"):
        v = g["ret_bp"].values
        se = v.std(ddof=1) / np.sqrt(len(v))
        day = g.set_index("ts")["ret_bp"].resample("D").mean().dropna()
        se_d = day.std(ddof=1) / np.sqrt(len(day)) if len(day) > 1 else np.nan
        res[tag] = {"n": int(len(v)), "mean_bp": float(v.mean()),
                    "med_bp": float(np.median(v)),
                    "win": float(100 * (v > 0).mean()),
                    "t_trade": float(v.mean() / se),
                    "n_days": int(len(day)),
                    "t_day": float(day.mean() / se_d) if se_d else None,
                    "claimed_bp": claim.get(tag)}
        print(f"  {tag:<12}{len(v):>8,}{v.mean():>+10.2f}{np.median(v):>+10.2f}"
              f"{100*(v>0).mean():>8.1f}{v.mean()/se:>+8.2f}{len(day):>7}"
              f"{(day.mean()/se_d if se_d else np.nan):>+8.2f}")
        print(f"  {'':12}{'주장':>8}{claim.get(tag, 0):>+10.2f}"
              f"   ← 원본 net (lookahead 이전)")
    # IS/OOS
    print(f"\n  분할 {cfg.split}")
    sp = pd.Timestamp(cfg.split)
    for tag, g in d.groupby("paradigm"):
        line = f"  {tag:<12}"
        for name, m in (("IS", g["ts"] < sp), ("OOS", g["ts"] >= sp)):
            gg = g[m]
            if gg.empty:
                continue
            day = gg.set_index("ts")["ret_bp"].resample("D").mean().dropna()
            se_d = day.std(ddof=1) / np.sqrt(len(day)) if len(day) > 1 else np.nan
            line += (f"{name} {len(gg):>6,}건 {gg['ret_bp'].mean():+7.2f}bp "
                     f"날짜t {(day.mean()/se_d if se_d else np.nan):+6.2f}   ")
            res[tag][name] = {"n": int(len(gg)),
                              "mean_bp": float(gg["ret_bp"].mean()),
                              "t_day": float(day.mean() / se_d) if se_d else None}
        print(line)
    print(f"\n  종목별 평균bp")
    for tag, g in d.groupby("paradigm"):
        per = g.groupby("symbol")["ret_bp"].mean().sort_values()
        pos = int((per > 0).sum())
        print(f"  {tag:<12} 양수 **{pos}/{len(per)}종목** · 최악 "
              f"{per.index[0]} {per.iloc[0]:+.1f} · 최고 {per.index[-1]} "
              f"{per.iloc[-1]:+.1f}")
        res[tag]["per_symbol_positive"] = f"{pos}/{len(per)}"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=2, default=str))
    print("\n" + "=" * 100)
    print(f"  → {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
