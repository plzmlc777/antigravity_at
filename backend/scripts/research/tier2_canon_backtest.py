"""2군 리그 좌석 백테스트 — **정본(Canon) 커널로**.

무엇을 묻는가
    "승격 근거가 맞았나"가 아니다. **lookahead 를 뺀 지금 이 전략에 엣지가
    남아 있나** 다.

    volume_burst 소스는 1분 트리거를 트리거를 **포함하는** 봉에 부착하고
    있었고, 실행기는 봉 시가에 체결하므로 트리거보다 과거 가격에 들어갔다.
    소스 주석의 실측(2026-08-08, FILUSDT 43건): 트리거의 67.4%가 봉 시작
    이후 발생, 평균 1.47분 과거 가격 체결. 편향 제거 시 거래당 엣지
    **0.7203% → 0.0175%**, 승률 **88.4% → 41.9%**.

    2026-08-14 에 그 구간 페이퍼 거래 133건을 무효 처리했고 리그에 남은
    유효 거래는 **4건**이다. 페이퍼로는 판정할 수 없으니 백테스트로 잰다.

스펙을 다시 쓰지 않는다
    좌석의 `session.json` 에 있는 `pipeline_spec` 을 **그대로** 읽는다.
    라이브 세션이 쓰는 바로 그 스펙이다. 여기서 다시 조립하면 교훈 #88 —
    인자가 조용히 버려져도 모른다.

⚠ `signal_lag_bars = 0` 인 이유
    1군 러너는 1 이다. 신상저격수 소스가 **달력 규칙**이라 창 안 모든 봉에
    신호를 내고, 밀지 않으면 상장가에 들어가기 때문이다.

    volume_burst 는 반대다 — 소스가 **이미** 트리거를 다음 eval 봉에 부착한다
    (그게 cd0ca27f 수정이다). 여기서 또 밀면 **두 번 밀려** 실제보다 한 봉
    늦게 체결한 셈이 된다. 계열마다 값이 다르므로 반드시 명시한다.

사용:
  python3 -m scripts.research.tier2_canon_backtest --days 120
  python3 -m scripts.research.tier2_canon_backtest --days 120 --seat ADAUSDT
"""
from __future__ import annotations

import argparse
import glob
import json
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("tier2_canon_bt")

OUT = ROOT / "runs" / "research_track" / "tier2_canon_backtest.json"

# 소스가 이미 다음 봉에 부착한다 — 여기서 또 밀면 두 번 밀린다 (위 주석 참조)
SIGNAL_LAG_BARS = 0

# 1분봉 워밍업 — **평가 구간보다 앞서 더 읽는다.**
#
# volume_burst 는 트리거 기준선으로 **30일 롤링 p99 거래량**(43,200봉)을 쓰고
# `min_periods` 가 그 25%(약 7.5일)다. 평가 구간만 불러오면 구간 전체가 30일에
# 못 미치는 **부분 기준선**으로 계산된다. 짧은 창의 p99 는 낮게 나오므로
# 트리거가 과다 발생하고 거래 수와 성과가 부풀려진다.
#
# 실측(ADAUSDT 30일, 워밍업 없음): 18거래 · 평균 +0.4046% · t 0.97.
# 골든 재생의 `START_MARGIN_DAYS` 와 같은 이유의 장치다.
WARMUP_DAYS = 31


def league_seats() -> list[dict]:
    """리그 좌석 — `tier_governor.is_governed` 하나로만 정한다."""
    from tier_governor import SESS_DIR, is_governed  # type: ignore
    out = []
    for d in sorted(glob.glob(os.path.join(SESS_DIR, "*"))):
        sj = os.path.join(d, "session.json")
        if not os.path.exists(sj):
            continue
        try:
            meta = json.load(open(sj))
        except Exception:
            continue
        if is_governed(meta, "binance") and meta.get("status") == "active":
            out.append(meta)
    return out


def load_ohlcv(conn, sym: str, start, end) -> pd.DataFrame:
    from sqlalchemy import text
    r = conn.execute(text(
        "SELECT timestamp, open, high, low, close, volume FROM ohlcv "
        "WHERE symbol=:s AND time_frame='1m' AND timestamp >= :a AND timestamp < :b "
        "ORDER BY timestamp"), {"s": sym, "a": start, "b": end}).fetchall()
    if not r:
        return pd.DataFrame()
    df = pd.DataFrame(r, columns=["ts", "open", "high", "low", "close", "volume"])
    df["ts"] = pd.to_datetime(df["ts"])
    return df.set_index("ts").astype(float)


def resample(df_1m: pd.DataFrame, minutes: int) -> pd.DataFrame:
    if minutes <= 1:
        return df_1m
    rule = f"{minutes}min"
    return pd.DataFrame({
        "open": df_1m["open"].resample(rule).first(),
        "high": df_1m["high"].resample(rule).max(),
        "low": df_1m["low"].resample(rule).min(),
        "close": df_1m["close"].resample(rule).last(),
        "volume": df_1m["volume"].resample(rule).sum(),
    }).dropna()


def run_seat(meta: dict, df_1m: pd.DataFrame, df_eval: pd.DataFrame):
    from app.composer_framework.backtester import GenericBacktester
    from app.composer_framework.pipeline_spec import build_pipeline
    from app.composer_framework.signal_source import SourceContext

    ps = meta["pipeline_spec"]
    ctx = SourceContext(
        symbol=meta["symbol"],
        eval_freq_minutes=ps.get("config", {}).get("eval_freq_minutes", 5),
        ohlcv_1m=df_1m, ohlcv_eval=df_eval)
    pipeline = build_pipeline(ps, {})
    bt = GenericBacktester(
        initial_capital=float(meta.get("initial_capital") or 1_000_000),
        fee_rate=float(meta.get("fee_rate") or 0.0004),
        apply_fee_to_short=True)
    return bt.run_rule_based(pipeline=pipeline, ctx=ctx,
                             signal_lag_bars=SIGNAL_LAG_BARS).trades


def stats(a: np.ndarray) -> dict:
    if len(a) < 2:
        return {"n": int(len(a))}
    se = a.std(ddof=1) / np.sqrt(len(a))
    return {"n": int(len(a)), "mean": float(a.mean()), "med": float(np.median(a)),
            "win": float(100 * (a > 0).mean()),
            "t": float(a.mean() / se) if se else float("nan")}


def main() -> int:
    p = argparse.ArgumentParser(description="2군 리그 백테스트 (정본 커널)")
    p.add_argument("--days", type=int, default=120, help="오늘 기준 소급 일수")
    p.add_argument("--seat", default="", help="종목 필터 (부분 일치)")
    p.add_argument("--out", default=str(OUT))
    a = p.parse_args()

    from app.db.session import engine

    seats = league_seats()
    if a.seat:
        seats = [s for s in seats if a.seat.upper() in (s.get("symbol") or "")]
    end = datetime.utcnow()
    start = end - timedelta(days=a.days)
    warm = start - timedelta(days=WARMUP_DAYS)   # 기준선 워밍업 (위 상수 주석)
    log.info("좌석 %d석 · 평가 %s ~ %s · 워밍업 %s 부터",
             len(seats), start.date(), end.date(), warm.date())

    results, all_rows = [], []
    with engine.connect() as conn:
        cache: dict[str, pd.DataFrame] = {}
        for i, meta in enumerate(seats, 1):
            sym = meta["symbol"]
            name = meta.get("name", "")
            ev = meta["pipeline_spec"].get("config", {}).get("eval_freq_minutes", 5)
            src = (meta["pipeline_spec"].get("sources") or [{}])[0].get("type", "?")
            if sym not in cache:
                cache[sym] = load_ohlcv(conn, sym, warm, end)
            df_1m = cache[sym]        # 워밍업 포함 — 소스가 기준선을 여기서 만든다
            if df_1m.empty:
                log.warning("%s 1분봉 없음 — 건너뜀", sym)
                continue
            # **평가 봉은 워밍업을 제외한다.** 신호는 전 구간에서 계산되지만
            # 거래는 평가 구간에서만 일어나야 비교가 성립한다.
            df_eval = resample(df_1m, ev)
            df_eval = df_eval[df_eval.index >= start]
            try:
                trades = run_seat(meta, df_1m, df_eval)
            except Exception as exc:
                log.warning("%s/%s 실패: %s: %s", sym, src, type(exc).__name__, exc)
                results.append({"symbol": sym, "source": src, "name": name,
                                "error": f"{type(exc).__name__}: {exc}"})
                continue
            rets = np.array([float(t.return_pct) * 100 for t in trades])
            s = stats(rets)
            results.append({"symbol": sym, "source": src, "name": name,
                            "eval_min": ev, **s})
            for t in trades:
                all_rows.append({"symbol": sym, "source": src,
                                 "side": t.side, "ret": float(t.return_pct) * 100,
                                 "reason": t.exit_reason,
                                 "entry_ts": str(t.entry_ts), "exit_ts": str(t.exit_ts)})
            log.info("%d/%d %s %s 거래 %d", i, len(seats), sym, src, len(trades))

    # 계열 합산 — 좌석별 표본이 작아 계열로 묶어야 판정이 선다
    fam: dict[str, list[float]] = {}
    for r in all_rows:
        key = "VB" if "volume_burst" in r["source"] else (
            "SC" if "stablecoin" in r["source"] else "기타")
        fam.setdefault(key, []).append(r["ret"])

    out = {"window_days": a.days, "start": str(start.date()), "end": str(end.date()),
           "warmup_days": WARMUP_DAYS,
           "engine": "canon_kernel", "signal_lag_bars": SIGNAL_LAG_BARS,
           "seats": results,
           "families": {k: stats(np.array(v)) for k, v in fam.items()},
           "trades": all_rows}
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=2))

    print("=" * 84)
    print(f"2군 리그 백테스트 (정본 커널) — 최근 {a.days}일 · "
          f"signal_lag={SIGNAL_LAG_BARS} · 워밍업 {WARMUP_DAYS}일")
    print("=" * 84)
    print(f"  {'종목':<10}{'계열':<26}{'주기':>5}{'n':>6}{'평균%':>9}{'중앙%':>9}{'승률%':>8}{'t':>8}")
    for r in results:
        if "error" in r:
            print(f"  {r['symbol']:<10}{r['source'][:25]:<26}  실패 {r['error'][:40]}")
            continue
        if "mean" not in r:
            print(f"  {r['symbol']:<10}{r['source'][:25]:<26}{r.get('eval_min',''):>5}"
                  f"{r.get('n',0):>6}   (표본 부족)")
            continue
        print(f"  {r['symbol']:<10}{r['source'][:25]:<26}{r['eval_min']:>5}{r['n']:>6}"
              f"{r['mean']:>9.4f}{r['med']:>9.4f}{r['win']:>8.1f}{r['t']:>8.2f}")
    print("-" * 84)
    print("  ** 계열 합산 **")
    for k, s in out["families"].items():
        if "mean" not in s:
            print(f"  {k:<6}{s.get('n',0):>6}   (표본 부족)")
            continue
        print(f"  {k:<6}{s['n']:>6}{s['mean']:>9.4f}{s['med']:>9.4f}"
              f"{s['win']:>8.1f}{s['t']:>8.2f}")
    print("=" * 84)
    print(f"  → {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
