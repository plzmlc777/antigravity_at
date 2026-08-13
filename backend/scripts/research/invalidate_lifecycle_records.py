"""lifecycle 페이퍼 기록 무효 처리 (대표님 지시, 2026-08-13).

왜
  454거래 중 **354건(78%)이 선언한 적 없는 +10.00% 익절**로 나갔다. 패러다임은
  "상장 Day-1 종가 숏 → SL +50% / 조기청산 / Day-30" 이고 익절은 설계에 없다.
  연구 백테스트 4종에도 TP 언급이 0건이다. 즉 **페이퍼가 백테스트와 다른 전략을
  돌린 기록**이다.

세 결함이 겹쳐 있다

  (1) 팬텀 익절 — orchestrator 가 `action.tp_price or price*0.90` 으로 0.0(명시적
      비활성)과 None(미지정)을 뭉갰다. 2026-08-08 수정. 마지막 tp 청산 08-06.
  (2) 재진입 — `pipeline_spec` 팩토리가 listing_date/entry_window_days 를 통째로
      버려 진입 창이 닫히지 않았다. 2026-08-13 수정(교훈 #88).
      CTRUSDT 7회, OUSDT 4회 등. 패러다임은 상장당 **한 번**이다.
  (3) 숏 수수료 미부과 — 롱 분기에만 fee_rate 가 곱해져 있었다. 2026-08-12 수정.

무엇을 하는가 / 하지 않는가
  · **지우지 않는다.** 기록을 지우면 증거가 사라진다. 각 거래에 `invalid` 와
    적용된 결함 목록을 **덧붙인다**. `read_trades` 는 원시 dict 를 돌려주므로
    필드 추가가 안전하다(dataclass 생성 아님 — 확인함).
  · 중앙 명세서(INVALID_TRADES.json)를 남겨 소비자가 한 곳만 보면 되게 한다.
  · 거래별로 **어떤 결함이 적용됐는지**를 청산 시각으로 판정해 적는다.
    "전부 무효"라고만 하면 나중에 왜 무효인지 알 수 없다.

사용:
  python3 scripts/research/invalidate_lifecycle_records.py            # 계획만
  python3 scripts/research/invalidate_lifecycle_records.py --commit   # 실제 표기
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if not (ROOT / "app").exists():
    ROOT = Path("/home/mint/auto_trading/backend")

SESS = ROOT / "runs" / "paper_sessions"
MANIFEST = SESS / "INVALID_TRADES.json"

# 결함이 고쳐진 날. 청산 시각이 이 날 **이전**이면 그 결함이 적용된 기록이다.
FIX_PHANTOM_TP = date(2026, 8, 8)     # D2 or-conflation
FIX_SHORT_FEE = date(2026, 8, 12)     # 숏 수수료 미부과
FIX_REENTRY = date(2026, 8, 13)       # 팩토리가 상장창 인자를 버림 (교훈 #88)

REASON = ("lifecycle 페이퍼 기록 오염 — 팬텀 익절(D2) / 재진입(교훈#88) / "
          "숏 수수료 미부과. 백테스트와 다른 전략이 돌았다.")


def defects_for(t: dict, idx: int) -> list[str]:
    """이 거래에 실제로 적용된 결함."""
    out = []
    try:
        ex = date.fromisoformat(str(t.get("exit_ts", ""))[:10])
    except Exception:
        ex = None
    if t.get("exit_reason") == "tp":
        out.append("phantom_tp")          # 선언한 적 없는 +10% 익절
    if idx > 0:
        out.append("reentry")             # 패러다임은 상장당 1거래
    if ex is not None:
        if ex < FIX_SHORT_FEE and t.get("side") == "short":
            out.append("short_fee_missing")
        if ex < FIX_PHANTOM_TP:
            out.append("in_phantom_tp_window")
        if ex < FIX_REENTRY:
            out.append("in_reentry_window")
    if t.get("exit_reason") == "manual_flatten_spurious_reentry":
        out.append("manual_cleanup_of_spurious_position")
    return out or ["contaminated_population"]


def main() -> int:
    commit = "--commit" in sys.argv
    sessions, rows = [], []
    reasons, defect_count = Counter(), Counter()

    for d in sorted(os.listdir(SESS)):
        sf, tf = SESS / d / "session.json", SESS / d / "trades.jsonl"
        if not (sf.exists() and tf.exists()):
            continue
        try:
            name = json.loads(sf.read_text()).get("name", "")
        except Exception:
            continue
        if "lifecycle" not in name:
            continue

        lines = [x for x in tf.read_text().splitlines() if x.strip()]
        if not lines:
            continue
        trades, out_lines = [], []
        for idx, line in enumerate(lines):
            t = json.loads(line)
            if t.get("invalid"):                    # 이미 표기됨 — 멱등
                out_lines.append(json.dumps(t, ensure_ascii=False))
                trades.append(t)
                continue
            dfs = defects_for(t, idx)
            t["invalid"] = True
            t["invalid_reason"] = REASON
            t["invalid_defects"] = dfs
            t["invalidated_on"] = "2026-08-13"
            reasons[t.get("exit_reason", "?")] += 1
            for x in dfs:
                defect_count[x] += 1
            out_lines.append(json.dumps(t, ensure_ascii=False))
            trades.append(t)
            rows.append({"session": d[:12], "name": name[:48],
                         "entry": str(t.get("entry_ts"))[:10],
                         "exit": str(t.get("exit_ts"))[:10],
                         "reason": t.get("exit_reason"),
                         "return_pct": t.get("return_pct"), "defects": dfs})
        sessions.append({"dir": d, "name": name, "n": len(trades)})
        if commit:
            # 백업은 **파일**로 만든다. 디렉터리로 만들면 `runs/paper_sessions/`
            # 를 훑는 코드가 그걸 **살아 있는 세션으로 센다**(2026-08-13 실제 발생 —
            # 청산 백업을 copytree 로 세션 트리 안에 만들어 157→158 로 셌다).
            bak = tf.with_suffix(".jsonl.bak_invalidate_20260813")
            if not bak.exists():
                shutil.copy(tf, bak)
            tf.write_text("\n".join(out_lines) + "\n", encoding="utf-8")

    print("\n" + "=" * 92)
    print(f"lifecycle 페이퍼 기록 무효 처리 — 세션 {len(sessions)} / 거래 {len(rows)}")
    print("=" * 92)
    print("  청산 사유별:")
    for k, v in reasons.most_common():
        print(f"    {k:<34}{v}")
    print("  적용된 결함별 (중복 가능):")
    for k, v in defect_count.most_common():
        print(f"    {k:<34}{v}")
    print("-" * 92)
    print("  기록은 **지우지 않는다.** invalid / invalid_defects 를 덧붙인다.")
    if not commit:
        print("\n  (--commit 없음 — 아무것도 바꾸지 않음)")
        print("=" * 92 + "\n")
        return 0

    MANIFEST.write_text(json.dumps({
        "invalidated_on": "2026-08-13",
        "reason": REASON,
        "fix_dates": {"phantom_tp": str(FIX_PHANTOM_TP),
                      "short_fee": str(FIX_SHORT_FEE),
                      "reentry": str(FIX_REENTRY)},
        "note": ("유효 판정일 2026-08-23(VALID_FROM_FLOOR+관측 14일)은 세 수정을 "
                 "모두 지난 시점이라 실무적으로는 자동 배제된다. 이 명세서는 "
                 "그 이전 기록을 성과로 인용하지 못하게 하는 장치다."),
        "n_sessions": len(sessions), "n_trades": len(rows),
        "by_exit_reason": dict(reasons), "by_defect": dict(defect_count),
        "sessions": sessions, "trades": rows,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  명세서: {MANIFEST}")
    print(f"  백업: 각 세션의 trades.jsonl.bak_invalidate_20260813")
    print("=" * 92 + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
