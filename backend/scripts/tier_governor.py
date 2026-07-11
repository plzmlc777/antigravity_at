"""Tier governor — 2군(System-2 paper pool) 자동 승격/강등 집행기.

day30_decision_protocol.md 결정 트리를 매일 기계 집행한다 (2026-07-11 대표님
"2군 3군 승격 강등 시스템 완전 자동화" 지시).

Scope
-----
- 대상: runs/paper_sessions/* 중 active + Binance 심볼 (KR 6-digit 제외,
  lifecycle* 제외 — lifecycle 변형은 1군 룰 교체 트랙이라 별도 수동 판정)
- 판정 시계: valid_from = max(첫 equity ts, VALID_FROM_FLOOR). 2026-07-01
  이전 구간은 엔진 1-bar/run 평가 버그로 무효 (project_vb_127_128_substrate_stall_fix)
- 체크포인트: age ≥ 30d부터 30d 간격 (Day-30/60/90…), state.json으로 중복 방지

Actions (자동 집행 vs 통보)
---------------------------
- TERMINATE  → paper_session_cli terminate 자동 실행 + Telegram
- CONTINUE   → 로그만 (다음 체크포인트 재판정)
- PROMOTE    → Telegram 통보만. 1군 진입은 어떤 경우에도 자동 실행 금지
               (feedback_binance_tier_taxonomy — 대표님 수동 승인)
- RESEED     → Telegram 통보만 (파라미터 완화는 architect 재설계 필요)

Protocol 대비 단순화 (문서화된 의도적 편차)
------------------------------------------
- INSUFFICIENT_SAMPLE(trades<5)의 trade_rate ratio 분기는 백테스트 기간 정보가
  CSV에 없어 직접 계산 불가 → alpha ≤ 0이면 TERMINATE, alpha > 0이면 RESEED 통보
- capital_util 미계산 (포지션 노셔널 이력 필요) → PROMOTE 후보 통보에 N/A 표기,
  수동 승인 단계에서 확인
- baseline(paper_spec_backtest.csv) 미존재 세션: 절대 기준만 적용
  (alpha < 0 → TERMINATE, 그 외 CONTINUE) + NEEDS_BASELINE 1회 통보

Slot cap
--------
MAX_PARADIGMS = 8 (2026-07-11 권고 확정). paradigm-architect가 R-5 시드 전
occupancy를 확인한다 (runs/tier_governor/state.json 의 slots 필드).

Usage: PYTHONPATH=. python3 scripts/tier_governor.py [--dry-run]
"""
import argparse
import csv
import glob
import json
import logging
import os
import statistics as st
import subprocess
import sys
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("tier_governor")

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SESS_DIR = os.path.join(BACKEND, "runs", "paper_sessions")
STATE_DIR = os.path.join(BACKEND, "runs", "tier_governor")
STATE_PATH = os.path.join(STATE_DIR, "state.json")
BASELINE_CSV = os.path.join(BACKEND, "runs", "paper_spec_backtest.csv")

VALID_FROM_FLOOR = datetime(2026, 7, 1)   # engine 1-bar/run bug fixed on Mint 2026-07-01
CHECKPOINT_DAYS = 30
MAX_PARADIGMS = 8
REAL_ACCOUNT_ID = 8  # telegram destination


def notify(msg: str, dry: bool) -> None:
    logger.info("[NOTIFY] %s", msg.replace("\n", " | "))
    if dry:
        return
    try:
        from scripts.binance.lifecycle_live_signal_driver import _telegram_notify
        _telegram_notify(REAL_ACCOUNT_ID, msg)
    except Exception as exc:  # never let telegram kill the governor
        logger.error("telegram send failed: %s", exc)


def load_state() -> dict:
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as f:
            return json.load(f)
    return {"sessions": {}, "slots": {}}


def save_state(state: dict, dry: bool) -> None:
    if dry:
        return
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=1, ensure_ascii=False)


def load_baselines() -> dict:
    out = {}
    if not os.path.exists(BASELINE_CSV):
        return out
    with open(BASELINE_CSV) as f:
        for row in csv.DictReader(f):
            out[row["spec"]] = row
    return out


def is_governed(meta: dict) -> bool:
    name = meta.get("name", "")
    sym = meta.get("symbol", "")
    if meta.get("status") != "active":
        return False
    if name.startswith("lifecycle") or "lifecycle" in name:
        return False
    if sym.isdigit():  # KR
        return False
    return True


def paradigm_key(meta: dict) -> str:
    name, sym = meta["name"], meta["symbol"]
    key = name[len(sym) + 1:] if name.startswith(sym + "_") else name
    return key.removesuffix("_paper_seed")


def read_jsonl(path: str):
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def bh_return_pct(symbol: str, start: datetime, end: datetime):
    """Buy-and-hold return from DB 1m closes (protocol §1 alpha definition)."""
    try:
        from sqlalchemy import text
        from app.db.session import engine
        q = text("""
            SELECT (SELECT close FROM ohlcv WHERE symbol=:s AND time_frame='1m'
                    AND timestamp >= :t0 ORDER BY timestamp LIMIT 1) AS c0,
                   (SELECT close FROM ohlcv WHERE symbol=:s AND time_frame='1m'
                    AND timestamp <= :t1 ORDER BY timestamp DESC LIMIT 1) AS c1
        """)
        with engine.connect() as conn:
            c0, c1 = conn.execute(q, {"s": symbol, "t0": start, "t1": end}).one()
        if c0 and c1:
            return (float(c1) / float(c0) - 1.0) * 100.0
    except Exception as exc:
        logger.warning("BH lookup failed for %s: %s", symbol, exc)
    return None


def measure(sdir: str, meta: dict, now: datetime):
    """Forward metrics over the valid window. Returns None if window not started."""
    eq = list(read_jsonl(os.path.join(sdir, "equity.jsonl")))
    if not eq:
        return None
    first_ts = datetime.fromisoformat(eq[0]["timestamp"])
    valid_from = max(first_ts, VALID_FROM_FLOOR)
    age_days = (now - valid_from).days
    window_eq = [e for e in eq if datetime.fromisoformat(e["timestamp"]) >= valid_from]
    if len(window_eq) < 2:
        return {"valid_from": valid_from, "age_days": age_days, "n_trades": 0,
                "sess_ret_pct": 0.0, "alpha_pct": None, "edge_pct": None,
                "sharpe": None, "trades_per_yr": 0.0, "last_eq_ts": None}
    e0, e1 = window_eq[0]["equity"], window_eq[-1]["equity"]
    sess_ret = (e1 / e0 - 1.0) * 100.0 if e0 else 0.0
    last_eq_ts = datetime.fromisoformat(window_eq[-1]["timestamp"])

    trades = [t for t in read_jsonl(os.path.join(sdir, "trades.jsonl"))
              if datetime.fromisoformat(t["entry_ts"]) >= valid_from]
    rets = [t["return_pct"] for t in trades]
    edge = st.mean(rets) * 100.0 if rets else None
    span_days = max((last_eq_ts - valid_from).days, 1)
    trades_per_yr = len(trades) * 365.0 / span_days

    daily = []
    prev = None
    for e in window_eq:
        if prev and prev > 0:
            daily.append(e["equity"] / prev - 1.0)
        prev = e["equity"]
    sharpe = None
    if len(daily) >= 10 and st.pstdev(daily) > 0:
        sharpe = st.mean(daily) / st.pstdev(daily) * (365 ** 0.5)

    bh = bh_return_pct(meta["symbol"], valid_from, last_eq_ts)
    alpha = sess_ret - bh if bh is not None else None
    return {"valid_from": valid_from, "age_days": age_days, "n_trades": len(trades),
            "sess_ret_pct": round(sess_ret, 3), "bh_pct": None if bh is None else round(bh, 3),
            "alpha_pct": None if alpha is None else round(alpha, 3),
            "edge_pct": None if edge is None else round(edge, 4),
            "sharpe": None if sharpe is None else round(sharpe, 2),
            "trades_per_yr": round(trades_per_yr, 1), "last_eq_ts": last_eq_ts}


def decide(m: dict, baseline: dict | None):
    """day30_decision_protocol.md §0 decision tree → (action, reason)."""
    alpha = m["alpha_pct"]
    a = alpha if alpha is not None else m["sess_ret_pct"]  # fallback: absolute return

    if m["n_trades"] < 5:
        if a <= 0:
            return "TERMINATE", f"INSUFFICIENT_SAMPLE trades={m['n_trades']} & alpha {a:.2f} <= 0"
        return "RESEED", f"INSUFFICIENT_SAMPLE trades={m['n_trades']} but alpha {a:.2f} > 0 — 파라미터 완화 검토"

    if a < 0:
        return "TERMINATE", f"forward alpha {a:.2f} < 0 (결정적 FAIL)"

    if baseline is not None:
        try:
            base_alpha = float(baseline["alpha_pct"])
        except (KeyError, ValueError):
            base_alpha = None
        if base_alpha is not None:
            if base_alpha <= 0:
                return "TERMINATE", f"INVALID_BASELINE base_alpha {base_alpha:.2f} <= 0"
            ratio = a / base_alpha
            if ratio < 0.20:
                return "TERMINATE", f"재현율 {ratio:.0%} < 20% (broad decay)"
            if ratio < 0.80:
                return "CONTINUE", f"감쇠 모드 재현율 {ratio:.0%} — Day-{m['age_days'] + 30} 재평가"

    # reproduction OK (or no baseline & alpha > 0) → life-changing 4-dim promote check
    dims_pass = (m["trades_per_yr"] >= 12
                 and m["edge_pct"] is not None and m["edge_pct"] >= 2.0
                 and m["sharpe"] is not None and m["sharpe"] >= 1.0)
    if dims_pass:
        return "PROMOTE", (f"4-dim 후보 (util 수동확인 필요): trades/yr {m['trades_per_yr']}, "
                           f"edge {m['edge_pct']:.2f}%, sharpe {m['sharpe']}")
    return "CONTINUE", (f"alpha 재현 OK but 4-dim 미달 (edge {m['edge_pct']}%, "
                        f"t/yr {m['trades_per_yr']}, sharpe {m['sharpe']})")


def terminate_session(session_id: str, dry: bool) -> bool:
    if dry:
        return True
    r = subprocess.run(
        [sys.executable, os.path.join(BACKEND, "scripts", "paper_session_cli.py"),
         "terminate", "--id", session_id],
        cwd=BACKEND, env={**os.environ, "PYTHONPATH": "."},
        capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        logger.error("terminate failed %s: %s", session_id, r.stderr[-300:])
    return r.returncode == 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    dry = args.dry_run
    now = datetime.utcnow()

    state = load_state()
    baselines = load_baselines()
    actions, paradigms = [], {}

    for sdir in sorted(glob.glob(os.path.join(SESS_DIR, "*"))):
        sj = os.path.join(sdir, "session.json")
        if not os.path.exists(sj):
            continue
        meta = json.load(open(sj))
        if not is_governed(meta):
            continue
        sid, name = meta["session_id"], meta["name"]
        pkey = paradigm_key(meta)
        paradigms.setdefault(pkey, []).append(sid)

        m = measure(sdir, meta, now)
        if m is None or m["age_days"] < CHECKPOINT_DAYS:
            continue
        sstate = state["sessions"].setdefault(sid, {})
        last_age = sstate.get("last_judged_age", 0)
        if m["age_days"] - last_age < CHECKPOINT_DAYS:
            continue  # already judged this checkpoint

        baseline = baselines.get(name) or baselines.get(name.removesuffix("_paper_seed"))
        if baseline is None and not sstate.get("needs_baseline_notified"):
            sstate["needs_baseline_notified"] = True
            logger.warning("NEEDS_BASELINE %s — 절대 기준만 적용", name)

        action, reason = decide(m, baseline)
        sstate.update({"last_judged_age": m["age_days"], "last_action": action,
                       "last_reason": reason, "judged_at": now.isoformat(timespec="seconds"),
                       "metrics": {k: (v.isoformat() if isinstance(v, datetime) else v)
                                   for k, v in m.items()}})
        logger.info("[%s] Day-%d %s — %s", action, m["age_days"], name, reason)

        if action == "TERMINATE":
            ok = terminate_session(sid, dry)
            actions.append(f"🔴 TERMINATE {name} (Day-{m['age_days']}): {reason}"
                           + ("" if ok else " [집행실패!]"))
        elif action == "PROMOTE":
            actions.append(f"🟢 PROMOTE 후보 {name} (Day-{m['age_days']}): {reason}\n"
                           f"   → 1군 진입은 대표님 수동 승인 대기")
        elif action == "RESEED":
            actions.append(f"⚫ RESEED 검토 {name} (Day-{m['age_days']}): {reason}")
        # CONTINUE: log only

    used = len(paradigms)
    state["slots"] = {"max": MAX_PARADIGMS, "used": used,
                      "paradigms": {k: len(v) for k, v in paradigms.items()},
                      "updated_at": now.isoformat(timespec="seconds")}
    save_state(state, dry)

    logger.info("slots %d/%d — %s", used, MAX_PARADIGMS, ", ".join(sorted(paradigms)))
    if actions:
        notify("🏛 Tier Governor (2군 자동 판정)\n" + "\n".join(actions)
               + f"\n\nslots: {used}/{MAX_PARADIGMS}", dry)
    print(json.dumps({"judged_actions": len(actions), "slots_used": used,
                      "slots_max": MAX_PARADIGMS, "dry_run": dry}))


if __name__ == "__main__":
    main()
