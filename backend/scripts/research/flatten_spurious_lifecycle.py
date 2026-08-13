"""lifecycle 유령 포지션 일괄 청산 (대표님 지시, 2026-08-13).

왜
  73세션 중 52개가 숏을 들고 있는데 대부분이 유령이다. 팩토리가 상장창 인자를
  버려(교훈 #88) 진입 창이 닫히지 않았고, 그래서 상장 90일차 종목에도 새 숏이
  열렸다. 오늘 아침 11:53 사이클(수정 13:29 전)까지 새로 만들었다.

  팩토리 수정은 **새 진입을 막을 뿐 이미 열린 포지션을 풀지 않는다.** 그대로
  두면 앞으로 몇 주에 걸쳐 청산되면서 무효 기록을 계속 만든다.

무엇을 유령으로 보는가 — 패러다임 정의에서 나온다
  패러다임: "상장 Day-1 종가 숏 **한 번**, SL +50% / 조기청산 / Day-30"

  (a) 진입창 밖 진입  — 진입일이 상장 + entry_window_days(3일)을 넘었다
                        → 애초에 있어선 안 될 포지션
  (b) 보유창 초과      — 진입은 정상인데 상장 + max_age_days(30일)를 넘겨 아직 들고 있다
                        → 나갔어야 할 포지션

  DOSUSDT 처럼 Day-1 에 들어가 보유창 안에 있는 것은 **건드리지 않는다.**

어떻게
  · 손으로 JSON 을 고치지 않는다. **정본(Canon)의 close() 를 통과**시킨다.
    회계식이 한 곳에만 있어야 하는데 여기서 손계산하면 그 원칙이 깨진다.
  · 결과 거래는 **즉시 무효 표시**한다. 전략 성과가 아니라 정리 흔적이다.
  · 백업은 세션 트리 **밖**에 만든다. 안에 만들면 세션을 훑는 코드가 살아 있는
    세션으로 센다(2026-08-13 실제 발생: 157 → 158).

사용:
  python3 scripts/research/flatten_spurious_lifecycle.py            # 계획만
  python3 scripts/research/flatten_spurious_lifecycle.py --commit
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if not (ROOT / "app").exists():
    ROOT = Path("/home/mint/auto_trading/backend")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import logging  # noqa: E402
logging.basicConfig(level=logging.ERROR)

import pandas as pd  # noqa: E402

SESS = ROOT / "runs" / "paper_sessions"
BACKUP = ROOT / "runs" / "paper_session_backups"     # ⚠ 세션 트리 **밖**
NAME_RE = re.compile(r"lifecycle_(?:h21|earlyexit_d7|earlyexit_d14|bearskip)?_?(.+?)_(\d{4}-\d{2}-\d{2})$")
REASON_TAG = "manual_flatten_spurious_reentry"


def classify(j: dict) -> tuple[str, str] | None:
    """(사유, 설명) 또는 None(정상이라 건드리지 않음)."""
    if j.get("side") == "flat":
        return None
    m = NAME_RE.match(j.get("name", ""))
    if not m:
        return None
    listing = datetime.strptime(m.group(2), "%Y-%m-%d").date()
    kw = {}
    for s in j.get("pipeline_spec", {}).get("sources", []):
        if "lifecycle" in s.get("type", ""):
            kw = s.get("kwargs", {})
            break
    win = int(kw.get("entry_window_days", 3))
    cap = int(kw.get("max_age_days", 30))

    ets = j.get("entry_ts")
    if not ets:
        return ("no_entry_ts", "진입 시각이 없는데 포지션이 있다")
    entry = datetime.fromisoformat(str(ets)).date()
    d_entry = (entry - listing).days
    if d_entry > win:
        return ("entry_outside_window",
                f"진입 Day-{d_entry} > 진입창 {win}일 — 있어선 안 될 포지션")
    if (date.today() - listing).days > cap:
        return ("held_past_cap",
                f"진입 Day-{d_entry}(정상)인데 상장 {(date.today()-listing).days}일차 — "
                f"보유창 {cap}일을 넘겨 아직 들고 있다")
    return None


def main() -> int:
    commit = "--commit" in sys.argv
    from paper_session_cli import load_1m
    from app.composer_framework.orchestrator import PaperOrchestrator
    from app.composer_framework.paper_session import SessionStore

    targets, keep = [], []
    for d in sorted(os.listdir(SESS)):
        sf = SESS / d / "session.json"
        if not sf.exists():
            continue
        try:
            j = json.loads(sf.read_text())
        except Exception:
            continue
        if "lifecycle" not in j.get("name", ""):
            continue
        c = classify(j)
        if c is None:
            if j.get("side") != "flat":
                keep.append((j["name"], j.get("entry_ts")))
            continue
        targets.append({"dir": d, "name": j["name"], "symbol": j["symbol"],
                        "reason": c[0], "why": c[1], "qty": j.get("qty"),
                        "entry_price": j.get("entry_price"), "entry_ts": j.get("entry_ts")})

    print("\n" + "=" * 104)
    print(f"lifecycle 유령 포지션 일괄 청산 — 대상 {len(targets)} / 유지 {len(keep)}")
    print("=" * 104)
    for k, ts in keep:
        print(f"  유지  {k:<48}진입 {str(ts)[:10]}  (진입창 안 + 보유창 안)")
    print("-" * 104)
    from collections import Counter
    for r, n in Counter(t["reason"] for t in targets).most_common():
        print(f"  {r:<26}{n}건")
    print("-" * 104)

    px_cache: dict[str, float] = {}
    total_pnl = 0.0
    store = SessionStore(str(SESS))
    orch = PaperOrchestrator(store)

    for t in targets:
        sym = t["symbol"]
        if sym not in px_cache:
            df = load_1m(sym, days=30)
            px_cache[sym] = float(df["close"].iloc[-1]) if len(df) else 0.0
        px = px_cache[sym]
        if px <= 0:
            t["skip"] = "가격 없음"
            continue
        qty, ep = float(t["qty"] or 0), float(t["entry_price"] or 0)
        pnl = qty * (ep - px)              # 전부 숏
        t["exit_price"], t["pnl"] = px, pnl
        total_pnl += pnl

    print(f"  {'세션':<48}{'진입가':>10}{'청산가':>10}{'수익률%':>10}  사유")
    for t in sorted(targets, key=lambda x: x["name"])[:50]:
        if t.get("skip"):
            print(f"  {t['name'][:47]:<48}{'—':>10}{'—':>10}{'—':>10}  SKIP {t['skip']}")
            continue
        ep, px = float(t["entry_price"]), t["exit_price"]
        print(f"  {t['name'][:47]:<48}{ep:>10.6g}{px:>10.6g}"
              f"{(ep - px) / ep * 100:>+10.2f}  {t['reason']}")
    print("-" * 104)
    print(f"  실현 손익 합계 (시뮬 자본 기준) {total_pnl:+,.0f}")
    print("  ** 이 거래들은 전략 성과가 아니라 정리 흔적이므로 즉시 무효 표시한다 **")

    if not commit:
        print("\n  (--commit 없음 — 아무것도 바꾸지 않음)")
        print("=" * 104 + "\n")
        return 0

    BACKUP.mkdir(parents=True, exist_ok=True)
    done = 0
    for t in targets:
        if t.get("skip"):
            continue
        sid = t["dir"]
        bak = BACKUP / f"{sid}.bak_batch_flatten_20260813"
        if not bak.exists():
            shutil.copytree(SESS / sid, bak)          # 세션 트리 밖이라 안전
        sess = store.load(sid)
        ts = pd.Timestamp.utcnow().tz_localize(None)
        trade = orch._close_position(sess, t["exit_price"], ts, REASON_TAG, 0.0)
        rec = json.loads(json.dumps(trade.__dict__, default=str))
        rec.update({"invalid": True, "invalidated_on": "2026-08-13",
                    "invalid_reason": "유령 포지션 일괄 청산 — 전략 성과가 아닌 정리 흔적",
                    "invalid_defects": ["batch_cleanup", t["reason"]]})
        with open(SESS / sid / "trades.jsonl", "a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        sess.final_equity = sess.cash
        sess.total_return_pct = (sess.cash - sess.initial_capital) / sess.initial_capital
        store.save(sess)
        done += 1

    print(f"\n  청산 완료 {done}건 / 백업 {BACKUP}")
    print("=" * 104 + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
