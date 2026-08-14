"""신상저격수 백테스트 — **정본(Canon) 커널로** 실행.

왜 새로 만드나
    같은 전략의 손익을 계산하는 코드가 연구 스크립트에 **6개** 따로 있었고 그중
    4개가 숏 수익률 규약을 틀리게 썼다(`진입/청산−1` 은 상한이 없어 이익 거래가
    부풀려진다). 2026-08-14 에 251 코호트 평균이 43.41% → 5.15%, t 5.73 → 1.74
    로 무너졌다.

    CANON·PA·REAL 은 커널 한 곳을 지나므로 서로 어긋나지 않는다. **BT 만 정본
    밖에 있어서 BT 만 계속 틀렸다.** 이 스크립트는 그 예외를 없앤다.

무엇이 달라지나
    · 공식이 한 곳 — 진입·청산·손절·수수료·수익률 전부 `kernel.step/close`
    · 골든 재생이 백테스트를 덮는다 — 규약 결함이 관문에서 걸린다
    · **BT↔CANON 격차가 구조적으로 0** 이 된다. 지금까지는 두 코드가 우연히
      같은 값을 낼 때만 0 이었다(DOSUSDT +0.04%p 는 운이었다)

정본과 같은 코드만 쓴다
    스펙   `lifecycle_session_spawner.build_session_spec`  ← CANON 세션과 동일
    조립   `pipeline_spec.build_pipeline`                  ← 동일
    실행   `backtester.GenericBacktester` (커널)           ← 동일

    스펙을 여기서 다시 쓰지 않는 것이 핵심이다. 교훈 #88 — 클래스만 고치고
    팩토리를 안 보면 인자가 조용히 버려진다.

패러다임 정의 (2026-08-14 대표님 개정)
    종전: "상장 Day-1 종가 숏 **한 번**".
    개정: **리스크를 줄이고 수익을 극대화하는 것이 절대 정의**다. "상장당 한 번"은
    그 수단이었을 뿐 목적이 아니다.

    따라서 익절로 나간 뒤 같은 종목이 다시 우위를 가지면 **재선택이 옳다**.
    다만 무제한은 아니다 — 상장 후 `entry_window_days` 까지만 재진입한다.

    ⚠ 진입창은 원래 익절 재진입을 막으려던 장치가 아니다. 소스가 -1.0 을 영원히
      내보내 REUSDT 가 8회, DATAIPUSDT 가 4회 진입한 **결함**(교훈 #88) 때문에
      2026-08-12 에 3일로 닫았다. 개정된 정의는 그 수정과 양립한다 — 창은 두되
      그 안에서는 경쟁으로 재선택한다. 창 값은 스윕으로 정한다.

코호트
    `lifecycle_variant_backtest.py` 와 같은 규칙 — `listing_dates.json` 의
    onboard_date 가 있고 상장 후 35일 창에 일봉 31개 이상. 비교가 목적이므로
    선별을 바꾸지 않는다.

사용:
  python3 -m scripts.research.lifecycle_canon_backtest --limit 20   # 빠른 확인
  python3 -m scripts.research.lifecycle_canon_backtest              # 전체
"""
from __future__ import annotations

import argparse
import json
import logging
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
log = logging.getLogger("canon_bt")

LISTINGS = ROOT / "runs" / "research_track" / "lifecycle_phase" / "listing_dates.json"
OUT = ROOT / "runs" / "research_track" / "lifecycle_canon_backtest.json"

# (이름, baseline_hold_days, early_exit_check_day, policy_variant)
VARIANTS = [("base", 30, None, "baseline"), ("h21", 21, None, "baseline"),
            ("earlyexit_d7", 30, 7, "early_exit"),
            ("earlyexit_d14", 30, 14, "early_exit"),
            ("bearskip", 30, None, "bear_skip")]

BEAR_THRESHOLD = -0.05

# 익절 스윕 기본값 (%). `none` 은 익절 없음 = **현행**이다.
#
# 배선: 정책 kwargs `tp_pct` 만 바꾼다. 커널·정책을 건드리지 않는다.
#   tp_pct = 1.0   → tp_price = 0.0        → 커널이 **비활성**으로 읽는다 (현행)
#   tp_pct = 0.10  → tp_price = 진입가×0.9 → 숏이 10% 하락하면 청산
# (`LifecycleDecayPolicy.decide`: `tp_price = open*(1-tp_pct) if tp_pct < 1.0 else 0.0`,
#  `kernel._forced_exit`: `tp_price > 0` 일 때만 수준으로 읽는다)
#
# ⚠ 익절은 이 패러다임에서 **사고 이력이 있다.** 2026-08-13 에 lifecycle 454거래
#   중 354건이 "선언한 적 없는 +10% 익절"로 나가 무효 처리됐다. 원인은
#   orchestrator 의 `action.tp_price or price*0.90` 이 0.0(명시적 비활성)과
#   None(미지정)을 뭉갠 것이다(2026-08-08 수정).
#
#   여기서 하는 것은 그것과 다르다 — **명시적으로 선언한 익절을 스윕**한다.
#   기본값은 `none` 이고, 스윕 결과가 좋아도 그것만으로 운영을 바꾸지 않는다.
#   같은 데이터에서 최적값을 고르면 과최적화다.
TP_SWEEP_DEFAULT = "none,5,10,15,20,30,50"


def tp_kwarg(tp: str | float) -> float:
    """스윕 값 → 정책 `tp_pct`. `none` 은 1.0(비활성)."""
    if isinstance(tp, str) and tp.lower() in ("none", "off", ""):
        return 1.0
    return float(tp) / 100.0

WINDOW_DAYS = 35
MIN_DAILY_BARS = 31


def daily_bars(conn, sym: str, a, b) -> pd.DataFrame:
    """1분봉 → 일봉. CANON 오케스트레이터와 같은 리샘플."""
    from sqlalchemy import text
    r = conn.execute(text(
        "SELECT timestamp, open, high, low, close, volume FROM ohlcv "
        "WHERE symbol=:s AND time_frame='1m' AND timestamp >= :a AND timestamp < :b "
        "ORDER BY timestamp"), {"s": sym, "a": a, "b": b}).fetchall()
    if not r:
        return pd.DataFrame()
    df = pd.DataFrame(r, columns=["ts", "open", "high", "low", "close", "volume"])
    df["ts"] = pd.to_datetime(df["ts"])
    d = df.set_index("ts").astype(float)
    return pd.DataFrame({
        "open": d["open"].resample("1D").first(),
        "high": d["high"].resample("1D").max(),
        "low": d["low"].resample("1D").min(),
        "close": d["close"].resample("1D").last(),
        "volume": d["volume"].resample("1D").sum(),
    }).dropna()


_BTC_PRE_RET: dict[str, float | None] = {}


def btc_pre_ret(listing_date: str) -> float | None:
    """BTC 30일 사전 수익률 — **스포너와 같은 함수**로 구한다.

    bearskip 은 이 값 하나로 진입을 억제한다(<= -5% 면 BEAR → 신호 0.0).
    여기서 다시 계산하면 CANON 세션과 다른 판정이 나올 수 있다. 상장일별로
    한 번만 부르고 캐시한다 — 코호트에 같은 날 상장이 여럿 있다.

    None 이면 그 사건의 bearskip 을 **건너뛴다**(스포너와 같은 보수적 기본값 —
    레짐을 모르는 채 세션을 만들지 않는다).
    """
    if listing_date not in _BTC_PRE_RET:
        from research.lifecycle_session_spawner import compute_btc_30d_pre_ret
        try:
            _BTC_PRE_RET[listing_date] = compute_btc_30d_pre_ret(listing_date)
        except Exception as exc:
            log.warning("BTC 사전 수익률 실패 %s: %s", listing_date, exc)
            _BTC_PRE_RET[listing_date] = None
    return _BTC_PRE_RET[listing_date]


def run_one(sym: str, ld, variant: str, hold: int, early, policy_variant,
            bars_1m, bars_daily, tp: str | float = "none",
            window: int | None = None, sl: float | None = None):
    """한 상장 사건 × 한 변형 — 정본 커널로 실행. 거래 목록을 돌려준다."""
    from app.composer_framework.backtester import GenericBacktester
    from app.composer_framework.pipeline_spec import build_pipeline
    from app.composer_framework.signal_source import SourceContext
    from research.lifecycle_session_spawner import build_session_spec

    pre_ret = None
    if policy_variant == "bear_skip":
        pre_ret = btc_pre_ret(str(ld))
        if pre_ret is None:
            return None          # 레짐 미상 — 사건 제외 (스포너와 같은 처리)

    spec = build_session_spec(
        sym, str(ld),
        policy_variant=policy_variant,
        early_exit_check_day=(early or 14),
        early_exit_vc_threshold=0.40,
        baseline_hold_days=hold,
        bear_skip_btc_30d_pre_ret=pre_ret,
        bear_skip_threshold=BEAR_THRESHOLD,
    )
    ps = spec["pipeline_spec"]
    # 익절 주입 — **스펙 사본에만** 쓴다. build_session_spec 이 준 원본을
    # 그대로 두어야 CANON 세션과 대조할 수 있다.
    tp_pct = tp_kwarg(tp)
    if tp_pct < 1.0 or window is not None or sl is not None:
        import copy
        ps = copy.deepcopy(ps)
    if tp_pct < 1.0:
        ps.setdefault("policy", {}).setdefault("kwargs", {})["tp_pct"] = tp_pct
    if sl is not None:
        # 손절 — 숏이므로 진입가 × (1 + sl_pct) 에 걸린다. 현행 0.50(+50%).
        #
        # 2026-08-14 익절 격자에서 **최악 거래가 전 칸 -50.1% 로 고정**이었다.
        # 익절을 아무리 조여도 왼쪽 꼬리가 안 줄어든 이유가 이 상수다 —
        # 축으로 열지 않으면 위험 쪽은 아예 탐색이 안 된다.
        ps.setdefault("policy", {}).setdefault("kwargs", {})["sl_pct"] = float(sl)
    if window is not None:
        # 재진입 창 — 상장 후 이 날까지만 다시 들어간다.
        # 모든 소스 kwargs 에 넣는다(base/early_exit/bear_skip 소스가 다르다).
        for src in ps.get("sources") or []:
            if "entry_window_days" in (src.get("kwargs") or {}):
                src["kwargs"]["entry_window_days"] = int(window)
    ctx = SourceContext(symbol=sym,
                        eval_freq_minutes=ps["config"]["eval_freq_minutes"],
                        ohlcv_1m=bars_1m, ohlcv_eval=bars_daily)
    pipeline = build_pipeline(ps, {})
    bt = GenericBacktester(
        initial_capital=float(spec["initial_capital"]),
        fee_rate=float(spec["fee_rate"]),
        apply_fee_to_short=True,          # 숏 수수료 — 2026-08-12 수정분
    )
    # 규칙 기반 전용 경로. `run_static` 은 학습/시험 분할이 상장일 진입을 잘라
    # 거래 0건을 만든다 — CANON 의 no-fit 경로와 같은 `run_rule_based` 를 쓴다.
    kpis = bt.run_rule_based(pipeline=pipeline, ctx=ctx)
    return kpis.trades


def stats(a: np.ndarray) -> dict:
    if len(a) < 2:
        return {"n": int(len(a))}
    se = a.std(ddof=1) / np.sqrt(len(a))
    return {"n": int(len(a)), "mean": float(a.mean()), "med": float(np.median(a)),
            "win": float(100 * (a > 0).mean()),
            "t": float(a.mean() / se) if se else float("nan")}


def main() -> int:
    p = argparse.ArgumentParser(description="신상저격수 백테스트 (정본 커널)")
    p.add_argument("--out", default=str(OUT))
    p.add_argument("--limit", type=int, default=0, help="앞에서 N 사건만 (빠른 확인)")
    p.add_argument("--split", default="",
                   help="표본 안/밖 분할 상장일 (예: 2026-05-13). 이 날 **이후** "
                        "상장이 표본 밖. R-4 판정일을 쓰는 것이 관례다")
    p.add_argument("--window", default="",
                   help="재진입 창(상장 후 일수) 스윕, 쉼표 구분. 비우면 스펙 기본(3일)")
    p.add_argument("--tp", default="none",
                   help=f"익절 스윕, 쉼표 구분 %%. 예: {TP_SWEEP_DEFAULT}. "
                        "'none' 은 익절 없음(현행)")
    a = p.parse_args()

    listings = json.load(open(LISTINGS))
    from app.db.session import engine

    tps = [x.strip() for x in a.tp.split(",") if x.strip()]
    wins = [int(x) for x in a.window.split(",") if x.strip()] or [None]
    log.info("익절 스윕: %s · 재진입 창: %s", tps,
             [("스펙기본(3)" if w is None else f"{w}일") for w in wins])
    rows, skipped, failed = [], 0, []
    with engine.connect() as conn:
        items = sorted(listings.items())
        for i, (sym, meta) in enumerate(items, 1):
            od = meta.get("onboard_date")
            if not od:
                continue
            ld = datetime.strptime(od, "%Y-%m-%d").date()
            dl = daily_bars(conn, sym, ld, ld + timedelta(days=WINDOW_DAYS))
            if len(dl) < MIN_DAILY_BARS:
                skipped += 1
                continue

            rec = {"symbol": sym, "listing": str(ld)}
            ok = True
            for name, hold, early, pv in VARIANTS:
              for tp in tps:
               for w in wins:
                key = name if tp == "none" else f"{name}@tp{tp}"
                if w is not None:
                    key += f"/w{w}"
                try:
                    trades = run_one(sym, ld, name, hold, early, pv, None, dl, tp, w)
                except Exception as exc:
                    failed.append(f"{sym}/{key}: {type(exc).__name__}: {exc}")
                    ok = False
                    break
                if trades is None:      # bearskip 레짐 미상 — 이 사건은 표본 밖
                    rec[f"{key}_n"] = None
                    rec[f"{key}"] = None
                    rec[f"{key}_reason"] = "regime_unknown"
                    continue
                # 진입 1회가 패러다임이다. 2회 이상이면 재진입 — 기록해 둔다.
                rec[f"{key}_n"] = len(trades)
                # 거래 0건은 두 가지다: bearskip 이 BEAR 로 억제했거나(정상),
                # 신호가 아예 없었거나. 억제는 **수익률 0** 이 아니라 표본 밖이다.
                rec[f"{key}"] = (float(trades[0].return_pct) * 100
                                 if trades else None)
                rec[f"{key}_reason"] = (trades[0].exit_reason if trades
                                        else "no_entry")
                # **모든** 거래를 남긴다. 익절을 켜면 재진입이 폭증하는데
                # (실측: 익절 없음 35건 → tp5 217건) 첫 거래만 세면 그 손익이
                # 통째로 빠진다 — 익절 비교에서 가장 큰 구멍이었다.
                rec[f"{key}_rets"] = [float(t.return_pct) * 100 for t in trades]
                rec[f"{key}_reasons"] = [t.exit_reason for t in trades]
            if ok:
                rows.append(rec)
            if a.limit and len(rows) >= a.limit:
                break
            if i % 50 == 0:
                log.info("%d/%d (사용 %d)", i, len(items), len(rows))

    out = {"cohort": len(rows), "skipped": skipped, "tp_sweep": tps,
           "engine": "canon_kernel", "variants": {}}
    split = a.split.strip()
    if split:
        log.info("표본 분할 %s — 이후 상장이 표본 밖", split)

    def subset(rs):
        if not split:
            return {"all": rs}
        return {"IS": [r for r in rs if r["listing"] < split],
                "OOS": [r for r in rs if r["listing"] >= split]}

    keys = [((n if tp == "none" else f"{n}@tp{tp}")
             + ("" if w is None else f"/w{w}"))
            for n, _, _, _ in VARIANTS for tp in tps for w in wins]
    def agg(name, rs):
        # (1) 사건 기준 — 첫 거래만. 익절 없음 실행과 직접 비교된다.
        first = np.array([r[name] for r in rs if r.get(name) is not None])
        # (2) 거래 기준 — 재진입 포함 **전부**. 실제로 계좌가 겪는 것이다.
        allr = np.array([x for r in rs for x in (r.get(f"{name}_rets") or [])])
        st_first, st_all = stats(first), stats(allr)
        reasons = [x for r in rs for x in (r.get(f"{name}_reasons") or [])]
        return {
            **st_all,                                   # n/mean/med/win/t = 거래 기준
            "n_events": int(len(first)),
            "n_trades": int(len(allr)),
            # 총수익 = 거래당 수익률의 합(%p). 각 거래가 같은 명목을 쓴다는
            # 가정 아래 "이 설정이 코호트 전체에서 몇 %p 를 걷었나"를 답한다.
            # 복리가 아니다 — 복리는 사이징에 좌우되고 그건 포트폴리오 시뮬의 몫이다.
            "total_ret": float(allr.sum()) if len(allr) else 0.0,
            "first_mean": st_first.get("mean"),
            "first_t": st_first.get("t"),
            # 위험 — 개정 정의는 "리스크를 줄이고 수익을 극대화"다. 총수익만
            # 보면 거래를 늘려 부풀릴 수 있으므로 최악 거래와 산포를 함께 낸다.
            "worst": float(allr.min()) if len(allr) else None,
            "std": float(allr.std(ddof=1)) if len(allr) > 1 else None,
            "tp_exits": sum(1 for x in reasons if x == "tp"),
            "sl_exits": sum(1 for x in reasons if x == "sl"),
            "reentry_events": sum(1 for r in rows if (r.get(f"{name}_n") or 0) > 1),
            "excluded": sum(1 for r in rs if r.get(name) is None),
        }

    for name in keys:
        parts = subset(rows)
        if split:
            out["variants"][name] = {k: agg(name, v) for k, v in parts.items()}
            out["variants"][name].update(agg(name, rows))   # 전체도 함께
        else:
            out["variants"][name] = agg(name, rows)
    out["rows"] = rows
    out["failed"] = failed[:20]

    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=2))

    print("=" * 78)
    print(f"정본 커널 백테스트 — 코호트 {len(rows)} (제외 {skipped}, 실패 {len(failed)})")
    print("=" * 78)
    if split:
        print(f"  {'변형':<26}" + f"{'IS 사건':>7}{'IS 거래':>7}{'IS 총%p':>9}{'IS t':>7}"
              + f"{'OOS 사건':>8}{'OOS 거래':>8}{'OOS 총%p':>10}{'OOS 평균':>9}{'OOS t':>7}")
        for name in keys:
            v = out["variants"][name]
            i, o = v.get("IS", {}), v.get("OOS", {})
            print(f"  {name:<26}{i.get('n_events',0):>7}{i.get('n_trades',0):>7}"
                  f"{i.get('total_ret',0):>9.0f}{(i.get('t') or 0):>7.2f}"
                  f"{o.get('n_events',0):>8}{o.get('n_trades',0):>8}"
                  f"{o.get('total_ret',0):>10.1f}{(o.get('mean') or 0):>9.2f}"
                  f"{(o.get('t') or 0):>7.2f}")
        print("-" * 78)
        print(f"  표본 분할 {split} — 이후 상장이 표본 밖")
        print("=" * 78)
        print(f"  → {a.out}")
        return 0

    print(f"  {'변형':<26}{'사건':>5}{'거래':>6}{'총수익%p':>10}{'평균%':>9}"
          f"{'승률%':>7}{'t':>7}{'최악%':>8}{'익절':>6}{'손절':>6}{'재진입':>7}")
    for name in keys:
        s = out["variants"][name]
        if "mean" not in s:
            print(f"  {name:<26}{s.get('n_events', 0):>5}{s.get('n_trades', 0):>6}"
                  f"   (표본 부족)")
            continue
        print(f"  {name:<26}{s['n_events']:>5}{s['n_trades']:>6}"
              f"{s['total_ret']:>10.1f}{s['mean']:>9.2f}"
              f"{s['win']:>7.1f}{s['t']:>7.2f}{(s['worst'] or 0):>8.1f}"
              f"{s['tp_exits']:>6}{s['sl_exits']:>6}{s['reentry_events']:>7}")
    if failed:
        print("-" * 78)
        for f in failed[:5]:
            print(f"  실패: {f}")
    print("=" * 78)
    print("-" * 78)
    print("  사건=상장 건수(첫 거래 기준) · 거래=재진입 포함 전부")
    print("  총수익%p = 거래별 수익률의 합. 복리 아님 — 복리는 사이징에 좌우되고")
    print("             그건 포트폴리오 시뮬의 몫이다")
    print("  평균/승률/t/최악 은 **거래 기준**이다 (중앙값·first_* 는 JSON 참조)")
    print("  /wN = 재진입 창 N일. 없으면 스펙 기본(3일)")
    print("=" * 78)
    print(f"  → {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
