"""R-5 시드 `btc_rv_highvol` — **진짜 표본 밖 3개월** 재검정.

## 왜 이 창인가

이 시드는 2026-05-14 에 13종목 페이퍼로 배포됐다. 그런데 실측하니:

    predictions.jsonl 31줄 · 전부 `prediction 0.0` · `hold`
    마지막 타임스탬프 **2026-05-12T23:55** — 세션 생성(05-14)보다 **이전**이고 반복

`runs/ohlcv_cache/*.joblib` 이 2026-05-12 에 정지했고 소스가 같은 마지막 봉을
영원히 읽었다. 캐시의 14종목이 **정확히 이 패러다임의 유니버스**다 — 이 시드를
위해 만든 캐시가 만들자마자 얼었다.

**따라서 전진 검증은 "부정"이 아니라 "무효"다.** 거래 0건은 신호가 없어서가
아니라 데이터가 안 움직여서다. [[project-research-substrate-stall-2026-08-09]]

DB 의 1분봉으로 진짜 표본 밖을 만들 수 있다:

    BTC 1분봉 DB 보유    2026-03-29 ~ 2026-08-14   (⚠ 알트는 2021~ 인데 BTC 만 잘려 있다)
    30분 RV z(30일) 워밍업 필요  30일  → 2026-04-28 부터 신호 가능
    **표본 밖 = 2026-05-13 ~ 2026-08-14 (3개월)**

원본 R-3 는 2024-01 ~ 2026-05-12 (캐시 구간)를 썼다. 위 창은 그 **뒤**이므로
한 번도 본 적 없는 구간이다.

## 규칙 (원본 스펙 그대로)

    트리거  BTC 30분 RV 의 z(30일) 가 **+2.5 를 상향 돌파**
            AND 60분 쿨다운
            AND BTC 30분 수익률 > 0
            AND BTC 30일 변동성 >= 직전 90일의 **p90**
    집행    13개 알트 **롱** · 보유 270분 · 익절 **+5%** · 손절 없음

⚠ BTC 30일 변동성과 그 90일 백분위는 **일봉**으로 낸다(`ohlcv_daily`, 전 구간
  보유). 1분봉이 4.5개월뿐이라 90일 백분위를 1분봉으로는 못 만든다.

⚠ 진입은 트리거 **다음 5분봉 시가**. 같은 봉 종가로 넣으면 그 봉을 보고 들어간다.

사용:
  python3 -m scripts.research.btc_rv_highvol_oos
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
log = logging.getLogger("rvhv")

OUT = ROOT / "runs" / "research_track" / "btc_rv_highvol_oos.json"
ALTS = ["ADAUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOGEUSDT", "ETHUSDT",
        "FILUSDT", "LINKUSDT", "LTCUSDT", "NEARUSDT", "SOLUSDT", "WIFUSDT",
        "XRPUSDT"]
BENCH = "BTCUSDT"


@dataclass
class RVConfig:
    rv_z: float = 2.5           # 30분 RV z 임계
    rv_win_days: int = 30       # z 계산 창
    cooldown_min: int = 60
    vol_pct: float = 90.0       # BTC 30일 변동성의 90일 백분위 하한
    hold_min: int = 270
    tp: float = 0.05
    sl: float = 0.0             # 0 = 없음 (원본 스펙)
    fee: float = 0.0004
    oos_start: str = "2026-05-13"
    warmup_start: str = "2026-03-29"
    rot: int = 200

    def __post_init__(self):
        if self.hold_min % 5:
            raise SystemExit("hold_min 은 5분 배수여야 한다 (5분봉 집행)")
        if not (0 < self.vol_pct < 100):
            raise SystemExit("vol_pct 는 0~100")


def load_1m(conn, sym: str, a: str, b: str) -> pd.DataFrame:
    from sqlalchemy import text
    r = conn.execute(text(
        "SELECT timestamp, open, high, low, close FROM ohlcv "
        "WHERE symbol=:s AND time_frame='1m' AND timestamp>=:a AND timestamp<=:b "
        "ORDER BY timestamp"), {"s": sym, "a": a, "b": b}).fetchall()
    if not r:
        return pd.DataFrame()
    d = pd.DataFrame(r, columns=["ts", "open", "high", "low", "close"])
    d["ts"] = pd.to_datetime(d["ts"])
    return d.set_index("ts").astype(float)


def resample(d: pd.DataFrame, rule: str) -> pd.DataFrame:
    return pd.DataFrame({
        "open": d["open"].resample(rule).first(),
        "high": d["high"].resample(rule).max(),
        "low": d["low"].resample(rule).min(),
        "close": d["close"].resample(rule).last()}).dropna()


def main() -> int:
    p = argparse.ArgumentParser(description="btc_rv_highvol 표본 밖 재검정")
    for f_ in RVConfig.__dataclass_fields__.values():
        p.add_argument("--" + f_.name.replace("_", "-"),
                       type=type(f_.default), default=f_.default)
    a = p.parse_args()
    cfg = RVConfig(**{k: getattr(a, k) for k in RVConfig.__dataclass_fields__})

    from sqlalchemy import text

    from app.db.session import engine
    end = "2026-08-15"
    with engine.connect() as conn:
        btc1 = load_1m(conn, BENCH, cfg.warmup_start, end)
        # BTC 일봉 변동성 — 90일 백분위를 내려면 일봉이 필요하다(1분봉은 4.5개월뿐)
        dr = conn.execute(text(
            "SELECT date, close FROM ohlcv_daily WHERE symbol=:s "
            "AND is_partial=false ORDER BY date"), {"s": BENCH}).fetchall()
    if btc1.empty:
        raise SystemExit("BTC 1분봉이 없다")
    dd = pd.DataFrame(dr, columns=["ts", "close"])
    dd["ts"] = pd.to_datetime(dd["ts"])
    dd = dd.set_index("ts").astype(float)
    dvol = dd["close"].pct_change().rolling(30).std()
    thr = dvol.rolling(90).quantile(cfg.vol_pct / 100.0)
    hi_vol = (dvol >= thr)                       # 일 단위 HIGH-vol 국면
    log.info("BTC 1분봉 %s행 · %s ~ %s · HIGH-vol 일수 %d/%d",
             f"{len(btc1):,}", btc1.index[0], btc1.index[-1],
             int(hi_vol.loc[cfg.oos_start:].sum()),
             int(hi_vol.loc[cfg.oos_start:].notna().sum()))

    b30 = resample(btc1, "30min")
    r30 = b30["close"].pct_change()
    win = cfg.rv_win_days * 48                   # 30분봉 개수
    rv = r30.rolling(6).std()                    # 3시간 창의 30분 RV
    z = (rv - rv.rolling(win).mean()) / rv.rolling(win).std()

    # 트리거 — 상향 돌파 + BTC 30분 수익률 > 0 + HIGH-vol 일자
    cross = (z >= cfg.rv_z) & (z.shift(1) < cfg.rv_z)
    up = r30 > 0
    day = pd.Series(b30.index.normalize(), index=b30.index)
    hv = day.map(hi_vol.to_dict()).fillna(False).astype(bool)
    trig = cross & up & hv
    trig = trig[trig.index >= pd.Timestamp(cfg.oos_start)]
    # 쿨다운
    keep, last = [], None
    for ts in trig[trig].index:
        if last is None or (ts - last).total_seconds() >= cfg.cooldown_min * 60:
            keep.append(ts)
            last = ts
    log.info("트리거 %d회 (표본 밖 %s ~ %s)", len(keep), cfg.oos_start, end)
    if not keep:
        print("트리거 0회 — HIGH-vol 국면이 이 창에 없었다는 뜻이다")
        return 0

    rows = []
    with engine.connect() as conn:
        for s in ALTS:
            a1 = load_1m(conn, s, cfg.oos_start, end)
            if a1.empty:
                log.warning("%s 1분봉 없음", s)
                continue
            a5 = resample(a1, "5min")
            for t0 in keep:
                idx = a5.index.searchsorted(t0)
                if idx + 1 >= len(a5):
                    continue
                j = idx + 1                      # 다음 5분봉 시가 진입
                entry = float(a5["open"].iloc[j])
                if not (entry > 0):
                    continue
                nb = cfg.hold_min // 5
                seg = a5.iloc[j:j + nb]
                if len(seg) < max(2, nb // 2):
                    continue
                tp_px = entry * (1 + cfg.tp)
                hit = seg.index[seg["high"] >= tp_px]
                if len(hit):
                    ex, reason = tp_px, "tp"
                else:
                    ex, reason = float(seg["close"].iloc[-1]), "time"
                ret = (ex / entry - 1.0) - 2 * cfg.fee
                rows.append({"symbol": s, "ts": t0, "ret": float(ret) * 100,
                             "reason": reason})
    d = pd.DataFrame(rows)
    print("=" * 100)
    print(f"  **btc_rv_highvol 표본 밖 재검정** — {cfg.oos_start} ~ {end} "
          f"(원본 R-3 구간 2024-01~2026-05-12 **이후**)")
    print(f"  트리거 {len(keep)}회 × 알트 {d['symbol'].nunique() if not d.empty else 0}종목 "
          f"= 거래 {len(d)}건")
    print(f"  원본 예측: **+126bp/거래** · 연 455거래 · 연 +57%")
    print("=" * 100)
    if d.empty:
        print("  거래 0건")
        return 0
    v = d["ret"].values
    se = v.std(ddof=1) / np.sqrt(len(v))
    print(f"\n  전체      거래 {len(v):>4} · 평균 **{v.mean()*100:+.1f}bp** · "
          f"중앙 {np.median(v)*100:+.1f}bp · 승률 {100*(v>0).mean():.1f}% · "
          f"**t {v.mean()/se:+.2f}**")
    # 트리거 단위로 묶기 — 같은 트리거의 13종목은 독립이 아니다 (교훈 #92)
    g = d.groupby("ts")["ret"].mean()
    se2 = g.std(ddof=1) / np.sqrt(len(g)) if len(g) > 1 else np.nan
    print(f"  **트리거 묶음** 트리거 {len(g):>3} · 평균 {g.mean()*100:+.1f}bp · "
          f"**t {g.mean()/se2 if se2 else np.nan:+.2f}** · 양수 "
          f"{int((g>0).sum())}/{len(g)}")
    print(f"  청산 사유 {d['reason'].value_counts().to_dict()}")
    print(f"\n  종목별")
    for s, gg in d.groupby("symbol"):
        print(f"     {s:<10} {len(gg):>3}건 {gg['ret'].mean()*100:+8.1f}bp "
              f"승률 {100*(gg['ret']>0).mean():5.1f}%")
    out = {"config": asdict(cfg), "n_triggers": len(keep), "n_trades": int(len(d)),
           "mean_bp": float(v.mean() * 100), "t_trade": float(v.mean() / se),
           "t_trigger": float(g.mean() / se2) if se2 else None,
           "win_pct": float(100 * (v > 0).mean()),
           "per_symbol": {s: {"n": int(len(gg)),
                              "mean_bp": float(gg["ret"].mean() * 100)}
                          for s, gg in d.groupby("symbol")}}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    print("\n" + "=" * 100)
    print(f"  → {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
