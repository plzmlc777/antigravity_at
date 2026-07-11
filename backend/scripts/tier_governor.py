"""Tier governor — 2군(System-2 paper pool) 승격/강등 리그 자동 집행기.

유럽 축구 리그 모델 (2026-07-11 대표님 확정):
- 2군 좌석 = 세션 24석 고정
- 매달 1일 (KST): 순위표 하위 3석 강등 + 승격 큐에서 상위 3석 승격
- 공석(1군 승격·절대-FAIL 퇴출 등)은 월중이라도 다음 daily run에서 즉시 큐 충원
- 순위 지표: 직전 30일(유효구간 교집합) 수익률
- 3군 R-4 PASS 배출이 부족해 큐가 비면 그 달은 가능한 만큼만 승격 (좌석 일시 공석,
  elite gate를 낮춰 미달 후보를 올리지 않음)

절대 안전선 (리그와 병행, day30_decision_protocol.md):
- Day-30/60/90 체크포인트에서 forward alpha<0 / 재현율<20% → 월중 즉시 TERMINATE
- PROMOTE(1군 후보) → Telegram 통보만. 1군 진입은 대표님 수동 승인 (자동 실행 금지)
- RESEED → Telegram 통보 (파라미터 완화는 architect 재설계)

판정 시계: valid_from = max(첫 equity ts, 2026-07-01 floor — 1-bar/run 평가 버그
무효구간 제외, project_vb_127_128_substrate_stall_fix).

승격 큐: backend/configs/tier_promotion_queue.json
  {"queue": [{"name", "spec", "paradigm", "symbol", "gate_score", "enqueued_at"}]}
paradigm-architect가 R-4 PASS 시 top 심볼별 spec을 enqueue → governor가 시드.

Usage:
  PYTHONPATH=. python3 scripts/tier_governor.py            # daily (cron)
  PYTHONPATH=. python3 scripts/tier_governor.py --trim     # 좌석 초과분 즉시 정리(일회성)
  PYTHONPATH=. python3 scripts/tier_governor.py --league-now  # 월례 리그 라운드 강제 실행
  PYTHONPATH=. python3 scripts/tier_governor.py --dry-run
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
QUEUE_PATH = os.path.join(BACKEND, "configs", "tier_promotion_queue.json")

VALID_FROM_FLOOR = datetime(2026, 7, 1)
SEATS = 24
LEAGUE_DEMOTE = 3
LEAGUE_PROMOTE = 3
CHECKPOINT_DAYS = 30
LEAGUE_WINDOW_DAYS = 30
REAL_ACCOUNT_ID = 8  # telegram destination
KST_OFFSET = timedelta(hours=9)


def notify(msg: str, dry: bool) -> None:
    logger.info("[NOTIFY] %s", msg.replace("\n", " | "))
    if dry:
        return
    try:
        from scripts.binance.lifecycle_live_signal_driver import _telegram_notify
        _telegram_notify(REAL_ACCOUNT_ID, msg)
    except Exception as exc:
        logger.error("telegram send failed: %s", exc)


def load_json(path: str, default):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default


def save_json(path: str, data, dry: bool) -> None:
    if dry:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=1, ensure_ascii=False, default=str)


def load_baselines() -> dict:
    out = {}
    if not os.path.exists(BASELINE_CSV):
        return out
    with open(BASELINE_CSV) as f:
        for row in csv.DictReader(f):
            out[row["spec"]] = row
    return out


def is_governed(meta: dict) -> bool:
    if meta.get("status") != "active":
        return False
    if "lifecycle" in meta.get("name", ""):
        return False
    if meta.get("symbol", "").isdigit():  # KR
        return False
    return True


def read_jsonl(path: str):
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def bh_return_pct(symbol: str, start: datetime, end: datetime):
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
    eq = list(read_jsonl(os.path.join(sdir, "equity.jsonl")))
    if not eq:
        return None
    first_ts = datetime.fromisoformat(eq[0]["timestamp"])
    valid_from = max(first_ts, VALID_FROM_FLOOR)
    age_days = (now - valid_from).days
    league_from = max(valid_from, now - timedelta(days=LEAGUE_WINDOW_DAYS))

    def window_ret(t0):
        w = [e for e in eq if datetime.fromisoformat(e["timestamp"]) >= t0]
        if len(w) < 2 or not w[0]["equity"]:
            return 0.0, None
        return (w[-1]["equity"] / w[0]["equity"] - 1.0) * 100.0, \
            datetime.fromisoformat(w[-1]["timestamp"])

    sess_ret, last_eq_ts = window_ret(valid_from)
    league_ret, _ = window_ret(league_from)

    trades = [t for t in read_jsonl(os.path.join(sdir, "trades.jsonl"))
              if datetime.fromisoformat(t["entry_ts"]) >= valid_from]
    rets = [t["return_pct"] for t in trades]
    edge = st.mean(rets) * 100.0 if rets else None
    span_days = max((last_eq_ts - valid_from).days, 1) if last_eq_ts else 1
    trades_per_yr = len(trades) * 365.0 / span_days

    daily, prev = [], None
    for e in eq:
        if datetime.fromisoformat(e["timestamp"]) < valid_from:
            continue
        if prev and prev > 0:
            daily.append(e["equity"] / prev - 1.0)
        prev = e["equity"]
    sharpe = None
    if len(daily) >= 10 and st.pstdev(daily) > 0:
        sharpe = st.mean(daily) / st.pstdev(daily) * (365 ** 0.5)

    bh = bh_return_pct(meta["symbol"], valid_from, last_eq_ts) if last_eq_ts else None
    alpha = sess_ret - bh if bh is not None else None
    return {"valid_from": valid_from, "age_days": age_days, "n_trades": len(trades),
            "sess_ret_pct": round(sess_ret, 3), "league_ret_pct": round(league_ret, 3),
            "bh_pct": None if bh is None else round(bh, 3),
            "alpha_pct": None if alpha is None else round(alpha, 3),
            "edge_pct": None if edge is None else round(edge, 4),
            "sharpe": None if sharpe is None else round(sharpe, 2),
            "trades_per_yr": round(trades_per_yr, 1)}


def decide(m: dict, baseline):
    """절대 안전선 판정 (day30_decision_protocol §0)."""
    alpha = m["alpha_pct"]
    a = alpha if alpha is not None else m["sess_ret_pct"]

    if m["n_trades"] < 5:
        if a <= 0:
            return "TERMINATE", f"INSUFFICIENT_SAMPLE trades={m['n_trades']} & alpha {a:.2f} <= 0"
        return "RESEED", f"INSUFFICIENT_SAMPLE trades={m['n_trades']} but alpha {a:.2f} > 0"
    if a < 0:
        return "TERMINATE", f"forward alpha {a:.2f} < 0"
    if baseline is not None:
        try:
            base_alpha = float(baseline["alpha_pct"])
        except (KeyError, ValueError):
            base_alpha = None
        if base_alpha is not None:
            if base_alpha <= 0:
                return "TERMINATE", f"INVALID_BASELINE base_alpha {base_alpha:.2f}"
            ratio = a / base_alpha
            if ratio < 0.20:
                return "TERMINATE", f"재현율 {ratio:.0%} < 20%"
            if ratio < 0.80:
                return "CONTINUE", f"감쇠 재현율 {ratio:.0%} — Day-{m['age_days'] + 30} 재평가"
    dims = (m["trades_per_yr"] >= 12 and m["edge_pct"] is not None
            and m["edge_pct"] >= 2.0 and m["sharpe"] is not None and m["sharpe"] >= 1.0)
    if dims:
        return "PROMOTE", (f"4-dim 후보 (util 수동확인): t/yr {m['trades_per_yr']}, "
                           f"edge {m['edge_pct']:.2f}%, sharpe {m['sharpe']}")
    return "CONTINUE", (f"alpha OK but 4-dim 미달 (edge {m['edge_pct']}%, "
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


def promote_from_queue(n: int, dry: bool):
    """승격 큐 상위 n개 시드. Returns list of promoted names."""
    qdata = load_json(QUEUE_PATH, {"queue": []})
    queue = qdata.get("queue", [])
    if not queue:
        return []
    queue.sort(key=lambda e: -float(e.get("gate_score", 0)))
    promoted = []
    remain = []
    for entry in queue:
        if len(promoted) >= n:
            remain.append(entry)
            continue
        spec = entry.get("spec")
        if not spec or not os.path.exists(os.path.join(BACKEND, spec)):
            logger.error("queue entry missing spec: %s", entry.get("name"))
            remain.append(entry)
            continue
        if dry:
            promoted.append(entry["name"])
            continue
        r = subprocess.run(
            [sys.executable, os.path.join(BACKEND, "scripts", "paper_session_cli.py"),
             "create", "--spec", spec],
            cwd=BACKEND, env={**os.environ, "PYTHONPATH": "."},
            capture_output=True, text=True, timeout=180)
        if r.returncode == 0:
            promoted.append(entry["name"])
        else:
            logger.error("promote failed %s: %s", entry["name"], r.stderr[-300:])
            remain.append(entry)
    qdata["queue"] = remain
    save_json(QUEUE_PATH, qdata, dry)
    return promoted


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--trim", action="store_true",
                    help="좌석 초과분(seats-24) 하위부터 즉시 강등 (일회성 정리)")
    ap.add_argument("--league-now", action="store_true",
                    help="월례 리그 라운드(3↓/3↑) 강제 실행")
    args = ap.parse_args()
    dry = args.dry_run
    now = datetime.utcnow()
    kst = now + KST_OFFSET

    state = load_json(STATE_PATH, {"sessions": {}, "league": {}})
    baselines = load_baselines()
    actions = []

    # ── 1. measure all governed sessions ────────────────────────────────
    seated = []  # (session_id, name, metrics)
    for sdir in sorted(glob.glob(os.path.join(SESS_DIR, "*"))):
        sj = os.path.join(sdir, "session.json")
        if not os.path.exists(sj):
            continue
        meta = json.load(open(sj))
        if not is_governed(meta):
            continue
        m = measure(sdir, meta, now)
        if m is None:
            continue
        seated.append({"sid": meta["session_id"], "name": meta["name"], "m": m})

    # ── 2. 절대 안전선 체크포인트 판정 (Day-30 간격) ─────────────────────
    terminated_ids = set()
    for s in seated:
        m = s["m"]
        if m["age_days"] < CHECKPOINT_DAYS:
            continue
        sstate = state["sessions"].setdefault(s["sid"], {})
        if m["age_days"] - sstate.get("last_judged_age", 0) < CHECKPOINT_DAYS:
            continue
        baseline = baselines.get(s["name"]) or baselines.get(s["name"].removesuffix("_paper_seed"))
        action, reason = decide(m, baseline)
        sstate.update({"last_judged_age": m["age_days"], "last_action": action,
                       "last_reason": reason, "judged_at": now.isoformat(timespec="seconds")})
        logger.info("[%s] Day-%d %s — %s", action, m["age_days"], s["name"], reason)
        if action == "TERMINATE":
            if terminate_session(s["sid"], dry):
                terminated_ids.add(s["sid"])
            actions.append(f"🔴 TERMINATE {s['name']} (Day-{m['age_days']}): {reason}")
        elif action == "PROMOTE":
            actions.append(f"🟢 PROMOTE 후보 {s['name']} (Day-{m['age_days']}): {reason}\n"
                           f"   → 기록만 함. 1군 승격은 대표님이 자금 사정 고려해 요청하실 때 진행")
        elif action == "RESEED":
            actions.append(f"⚫ RESEED 검토 {s['name']} (Day-{m['age_days']}): {reason}")
    seated = [s for s in seated if s["sid"] not in terminated_ids]

    # ── 3. 리그 라운드 (매달 1일 KST, 또는 --league-now / --trim) ────────
    ym = kst.strftime("%Y-%m")
    monthly_due = kst.day == 1 and state["league"].get("last_round_ym") != ym
    demote_n = 0
    if args.trim and len(seated) > SEATS:
        demote_n = len(seated) - SEATS
    elif monthly_due or args.league_now:
        demote_n = LEAGUE_DEMOTE

    if demote_n > 0:
        table = sorted(seated, key=lambda s: (s["m"]["league_ret_pct"], s["m"]["n_trades"]))
        drop = table[:demote_n]
        for s in drop:
            if terminate_session(s["sid"], dry):
                terminated_ids.add(s["sid"])
            actions.append(f"⬇️ 리그 강등 {s['name']} (30d {s['m']['league_ret_pct']:+.2f}%, "
                           f"trades {s['m']['n_trades']})")
        seated = [s for s in seated if s["sid"] not in terminated_ids]
        if monthly_due or args.league_now:
            state["league"]["last_round_ym"] = ym
        state["league"].setdefault("rounds", []).append({
            "at": now.isoformat(timespec="seconds"), "type": "trim" if args.trim else "monthly",
            "demoted": [s["name"] for s in drop]})

    # ── 4. 공석 충원 (승격 큐 → 좌석 24 유지; 월례는 최대 3, 공석 backfill 무제한) ──
    vacancy = SEATS - len(seated)
    cap = LEAGUE_PROMOTE if (monthly_due or args.league_now) else max(vacancy, 0)
    if vacancy > 0:
        promoted = promote_from_queue(min(vacancy, cap) if cap else vacancy, dry)
        for name in promoted:
            actions.append(f"⬆️ 리그 승격 {name} (3군 R-4 PASS → 2군 시드)")
        seated_count = len(seated) + len(promoted)
    else:
        seated_count = len(seated)

    queue_len = len(load_json(QUEUE_PATH, {"queue": []}).get("queue", []))
    state["seats"] = {"max": SEATS, "used": seated_count, "queue": queue_len,
                      "updated_at": now.isoformat(timespec="seconds")}
    save_json(STATE_PATH, state, dry)

    logger.info("seats %d/%d, queue %d", seated_count, SEATS, queue_len)
    if actions:
        notify("🏟 Tier Governor 리그 (2군)\n" + "\n".join(actions)
               + f"\n\n좌석 {seated_count}/{SEATS} | 승격 큐 {queue_len}", dry)
    print(json.dumps({"actions": len(actions), "seats_used": seated_count,
                      "seats_max": SEATS, "queue": queue_len, "dry_run": dry}))


if __name__ == "__main__":
    main()
