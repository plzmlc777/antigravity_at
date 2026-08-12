"""숏 수수료 결함 수정 — 수정 전/후 A/B 재백테스트.

배경 (2026-08-12)
  `GenericBacktester._close_position` / `PaperOrchestrator._close_position` 의
  숏 분기에 수수료 항이 아예 없었다. 롱 분기에만 `fee_rate` 가 곱해져 있었고,
  최초 커밋(70ffae67, 2026-05-07) 이후 3개월간 손대지 않았다.
  주석·docstring 어디에도 "숏은 무료"라는 근거가 없다 → 의도가 아니라 누락.

  그런데 source 문서화에는 "수수료 왕복 8bp", "fee-adjusted" 가 적혀 있다.
  즉 **연구는 수수료를 전제하고 통과시킨 전략을, 실행 엔진이 숏에서는 0bp 로
  돌려왔다.**

무엇을 재는가
  같은 스펙·같은 바·**같은 예측값**으로 시뮬레이터만 두 번 돌린다.
    A = apply_fee_to_short=False  (구동작 재현)
    B = apply_fee_to_short=True   (수정 후)
  예측을 한 번만 계산해 양쪽에 주입한다 — 각자 fit/predict 하게 두면 ML 컴포저
  에서 예측 자체가 갈려 수수료 효과와 구분되지 않는다 (engine_parity_gate 와
  같은 원칙).

  따라서 A→B 차이는 **오직 숏 수수료**다. 롱 수수료는 양쪽 동일하게 걸린다.

수수료율
  스펙이 선언한 `fee_rate` 를 그대로 쓴다(대부분 0.0004). 실제 바이낸스 선물
  테이커는 편도 5bp 이므로 이것도 낙관적이다 — `--fee-override 0.0005` 로
  따로 잴 수 있다.

사용:
  python3 scripts/research/short_fee_fix_ab.py
  python3 scripts/research/short_fee_fix_ab.py --fee-override 0.0005
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import warnings
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if not (ROOT / "app").exists():
    ROOT = Path("/home/mint/auto_trading/backend")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("short_fee_ab")
logging.getLogger("app").setLevel(logging.ERROR)

from app.composer_framework import build_pipeline  # noqa: E402
from app.composer_framework.backtester import GenericBacktester  # noqa: E402
from app.composer_framework.signal_source import SourceContext  # noqa: E402

import backtest_paper_specs as BPS  # noqa: E402

SPEC_DIRS = [ROOT / "configs" / "paper_sessions",
             ROOT / "configs" / "paper_sessions" / "lifecycle"]
SHORT_POLICIES = {"long_short_threshold", "lifecycle_decay_early_exit", "funding_reversal"}

_eval_cache: dict[str, pd.DataFrame | None] = {}
_runtime_cache: dict[str, dict] = {}
_leader_1m: dict[str, pd.DataFrame | None] = {}

# BPS.load_runtime 은 **심볼마다** BTCUSDT 전체 1분봉을 다시 읽는다. 40심볼이면
# 거대한 테이블을 40번 읽어 I/O 로 죽는다(첫 시도에서 7분간 1스펙도 못 끝냄).
# 원본을 캐시판으로 갈아끼워 심볼당 1회, BTC 는 전 과정 1회만 읽게 한다.
_BPS_EVAL = BPS.load_ohlcv_eval


def eval_df(symbol: str):
    if symbol not in _eval_cache:
        try:
            _eval_cache[symbol] = _BPS_EVAL(symbol)
        except Exception as exc:
            log.warning("%s: ohlcv load failed: %s", symbol, exc)
            _eval_cache[symbol] = None
    return _eval_cache[symbol]


BPS.load_ohlcv_eval = eval_df          # leader_ohlcv_eval(BTC) 도 캐시를 타게 한다


def leader_1m(symbol: str = "BTCUSDT"):
    if symbol not in _leader_1m:
        from sqlalchemy import text as _t
        from app.db.session import SessionLocal as _S
        log.info("리더 1분봉 적재 (1회) — %s", symbol)
        db = _S()
        try:
            rows = db.execute(_t(
                "SELECT timestamp, open, high, low, close, volume FROM ohlcv "
                "WHERE symbol = :s AND time_frame = '1m' ORDER BY timestamp"),
                {"s": symbol}).fetchall()
        finally:
            db.close()
        if not rows:
            _leader_1m[symbol] = None
        else:
            d = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
            d["timestamp"] = pd.to_datetime(d["timestamp"])
            d = d.set_index("timestamp")
            for c in ("open", "high", "low", "close", "volume"):
                d[c] = pd.to_numeric(d[c])
            _leader_1m[symbol] = d.dropna()
    return _leader_1m[symbol]


def runtime_for(symbol: str, need_leader_1m: bool) -> dict:
    """심볼별 런타임. BTC 1분봉은 요구하는 소스가 있을 때만, 그리고 전역 1회."""
    if symbol not in _runtime_cache:
        rt: dict = {"symbol": symbol}
        import joblib
        for p in sorted(BPS.PATTERN_DIR.glob(f"{symbol}__*d__signals.joblib")):
            rt["signals_df"] = joblib.load(p)
            break
        for key, path in (("binance_metrics_5m", BPS.MICRO_DIR / f"{symbol}_full_metrics.joblib"),
                          ("book_depth_daily", BPS.BOOK_DIR / f"{symbol}_bookdepth.joblib"),
                          ("premium_df", BPS.PREMIUM_DIR / f"{symbol}_premium.joblib")):
            if path.exists():
                rt[key] = joblib.load(path)
        try:
            from sqlalchemy import text as _t
            from app.db.session import SessionLocal as _S
            with _S() as s:
                rows = s.execute(_t(
                    "SELECT symbol, funding_time, funding_rate, mark_price "
                    "FROM binance_funding_rate WHERE symbol = :sym ORDER BY funding_time"),
                    {"sym": symbol}).fetchall()
            if rows:
                d = pd.DataFrame(rows, columns=["symbol", "funding_time", "funding_rate", "mark_price"])
                d["funding_time"] = pd.to_datetime(d["funding_time"])
                d["funding_rate"] = pd.to_numeric(d["funding_rate"])
                d["mark_price"] = pd.to_numeric(d["mark_price"])
                rt["binance_funding_df"] = d
        except Exception:
            pass
        led = eval_df("BTCUSDT")
        if led is not None and len(led):
            rt["leader_ohlcv_eval"] = led
        _runtime_cache[symbol] = rt
    rt = dict(_runtime_cache[symbol])
    if need_leader_1m:
        d = leader_1m()
        if d is not None:
            rt["leader_ohlcv_1m"] = d
    return rt


def family_of(name: str, spec: dict) -> str:
    srcs = [s.get("type", "") for s in spec.get("pipeline_spec", {}).get("sources", [])]
    for s in srcs:
        if "lifecycle" in s:
            return "lifecycle (신상저격수)"
        if "volume_burst_neg" in s:
            return "alt_volume_burst_neg (되치기)"
    pol = spec.get("pipeline_spec", {}).get("policy", {}).get("type", "?")
    if pol == "funding_reversal":
        return "funding_reversal"
    return "기타 복합"


def run_spec(path: Path, fee_override: float | None) -> dict | None:
    spec = json.loads(path.read_text())
    pspec = spec.get("pipeline_spec", {})
    pol = pspec.get("policy", {}).get("type", "?")
    if pol not in SHORT_POLICIES:
        return None
    name = spec.get("name", path.stem)
    symbol = spec.get("symbol")
    fee = float(fee_override if fee_override is not None else spec.get("fee_rate", 0.0004))

    df = eval_df(symbol)
    if df is None or len(df) < 60:
        return {"spec": name, "err": "데이터부족"}

    srcs = [s.get("type", "") for s in pspec.get("sources", [])]
    rt = runtime_for(symbol, need_leader_1m=any("btc_rv_highvol" in s for s in srcs))
    rt["ohlcv_eval"] = df
    ctx = SourceContext(symbol=symbol,
                        eval_freq_minutes=pspec.get("config", {}).get("eval_freq_minutes", 1440),
                        ohlcv_eval=df)
    try:
        pipeline = build_pipeline(pspec, rt)
        feat = pipeline.build_features(ctx)
    except Exception as exc:
        return {"spec": name, "err": f"build:{str(exc)[:40]}"}

    n = len(feat)
    split = int(n * 0.5)
    train, test = feat.iloc[:split], feat.iloc[split:]
    if len(test) < 10:
        return {"spec": name, "err": "테스트구간부족"}
    try:
        bars = ctx.ohlcv_eval.loc[test.index]
        pipeline.fit(train)
        preds = pd.Series(np.asarray(pipeline.predict(test), dtype=float), index=test.index)
    except Exception as exc:
        return {"spec": name, "err": f"fit:{str(exc)[:40]}"}

    out = {}
    for tag, flag in (("A", False), ("B", True)):
        bt = GenericBacktester(initial_capital=1_000_000.0, size_pct=0.95,
                               fee_rate=fee, apply_fee_to_short=flag)
        try:
            k = bt._simulate(symbol=symbol, bars=bars, predictions=preds,
                             policy=pipeline.policy)
        except Exception as exc:
            return {"spec": name, "err": f"sim{tag}:{str(exc)[:40]}"}
        sh = [t for t in k.trades if t.side == "short"]
        out[tag] = {"ret": k.total_return_pct * 100, "n": k.n_trades,
                    "n_short": len(sh),
                    "short_mean_bp": (float(np.mean([t.return_pct for t in sh])) * 1e4
                                      if sh else 0.0),
                    "mdd": k.max_drawdown_pct * 100,
                    "wr": k.win_rate * 100}
    if out["A"]["n_short"] == 0:
        return {"spec": name, "err": "숏거래없음"}

    return {"spec": name, "symbol": symbol, "family": family_of(name, spec), "fee": fee,
            "n": out["A"]["n"], "n_short": out["A"]["n_short"],
            "retA": out["A"]["ret"], "retB": out["B"]["ret"],
            "d_ret": out["B"]["ret"] - out["A"]["ret"],
            "sA": out["A"]["short_mean_bp"], "sB": out["B"]["short_mean_bp"],
            "d_short_bp": out["B"]["short_mean_bp"] - out["A"]["short_mean_bp"],
            "mddA": out["A"]["mdd"], "mddB": out["B"]["mdd"],
            "flipped": (out["A"]["short_mean_bp"] > 0) and (out["B"]["short_mean_bp"] <= 0)}


def main() -> int:
    ap = argparse.ArgumentParser(description="숏 수수료 수정 전/후 A/B")
    ap.add_argument("--fee-override", type=float, default=None,
                    help="스펙 선언값 대신 이 편도 요율 사용 (예: 0.0005 = 바이낸스 테이커)")
    ap.add_argument("--out", default=str(ROOT / "runs" / "research_track" /
                                         "short_fee_fix_ab.json"))
    args = ap.parse_args()

    paths = []
    for d in SPEC_DIRS:
        if d.exists():
            paths += sorted(d.glob("*.json"))
    log.info("스펙 %d개 검사", len(paths))

    rows, errs = [], []
    for i, p in enumerate(paths, 1):
        r = run_spec(p, args.fee_override)
        if r is None:
            continue
        if "err" in r:
            errs.append((r["spec"], r["err"]))
        else:
            rows.append(r)
        if i % 10 == 0:
            log.info("%d/%d (유효 %d, 제외 %d)", i, len(paths), len(rows), len(errs))

    if not rows:
        log.error("유효 결과 0건")
        return 1

    D = pd.DataFrame(rows)
    fee_lbl = f"{args.fee_override*1e4:.1f}bp(강제)" if args.fee_override else "스펙선언값"

    print("\n" + "=" * 118)
    print(f"숏 수수료 결함 수정 — A(구동작: 숏 무료) vs B(수정: 숏 과금)   요율 {fee_lbl}")
    print("=" * 118)
    print("  같은 바 · 같은 예측값 · 시뮬레이터만 교체 → 차이는 오직 숏 수수료")
    print("-" * 118)
    print(f"  {'스펙':<44}{'숏거래':>7}{'숏평균A':>10}{'숏평균B':>10}{'차이bp':>9}"
          f"{'총수익A%':>11}{'총수익B%':>11}{'차이%p':>9}")
    print("-" * 118)
    for _, r in D.sort_values("d_ret").iterrows():
        flag = "  ← 부호반전" if r["flipped"] else ""
        print(f"  {r['spec'][:43]:<44}{r['n_short']:>7}{r['sA']:>10.1f}{r['sB']:>10.1f}"
              f"{r['d_short_bp']:>9.1f}{r['retA']:>11.2f}{r['retB']:>11.2f}"
              f"{r['d_ret']:>+9.2f}{flag}")

    print("-" * 118)
    print("  ** 계열별 집계 **")
    print(f"  {'계열':<28}{'스펙':>6}{'숏거래':>8}{'숏평균A':>11}{'숏평균B':>11}"
          f"{'엣지잠식':>10}{'부호반전':>9}")
    for fam, g in D.groupby("family"):
        wA = np.average(g["sA"], weights=g["n_short"])
        wB = np.average(g["sB"], weights=g["n_short"])
        erode = (abs(wA - wB) / abs(wA) * 100) if wA else float("nan")
        print(f"  {fam:<28}{len(g):>6}{int(g['n_short'].sum()):>8}{wA:>11.1f}{wB:>11.1f}"
              f"{erode:>9.1f}%{int(g['flipped'].sum()):>9}")

    wA = np.average(D["sA"], weights=D["n_short"])
    wB = np.average(D["sB"], weights=D["n_short"])
    print("-" * 118)
    print(f"  전체 {len(D)}스펙 / 숏 {int(D['n_short'].sum())}건 — "
          f"거래당 {wA:+.1f}bp → {wB:+.1f}bp  (잠식 {abs(wA-wB)/abs(wA)*100:.1f}%)")
    print(f"  숏 평균이 **양수 → 음수로 뒤집힌 스펙: {int(D['flipped'].sum())}개**")
    if errs:
        print("-" * 118)
        ec = defaultdict(int)
        for _, e in errs:
            ec[e.split(":")[0]] += 1
        print(f"  제외 {len(errs)}건: {dict(ec)}")
    print("=" * 118 + "\n")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    json.dump({"fee_mode": fee_lbl, "n_specs": len(D),
               "rows": rows, "errors": errs},
              open(args.out, "w"), ensure_ascii=False, indent=2, default=str)
    log.info("저장: %s", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
