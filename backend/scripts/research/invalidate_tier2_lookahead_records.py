"""2군 리그 페이퍼 기록 무효 처리 — lookahead 구간 (대표님 지시, 2026-08-14).

왜
  volume_burst 소스는 1분 트리거를 **트리거를 포함하는 봉**에 부착하고 있었다.
  실행기는 봉 **시가**에 체결하므로, 트리거보다 과거인 가격에 들어갔다.

  소스 주석에 남은 실측(2026-08-08, FILUSDT 43건):
    · 트리거의 **67.4%가 봉 시작 이후** 발생 → 평균 1.47분 과거 가격에 체결
    · 편향 제거 시 거래당 엣지 **0.7203% → 0.0175%**, 승률 **88.4% → 41.9%**
    · **성과 전량이 이 한 줄에서 나왔다**

  수정은 2026-08-08(`cd0ca27f`)에 들어갔고 VB 좌석 6석은 **2026-05-21 생성**이다.
  좌석 수명의 대부분이 수정 이전이다.

무엇이 문제였나 — 표시가 없어서 전부 유효로 세고 있었다
  8/13 무효 처리는 lifecycle 498건만 했다. 2군은 손대지 않아 `invalid` 표시가
  **0건**이었고, DB 질의·일일 리포트·보고가 전부 오염 거래를 유효로 셌다.
  실측: 리그 136건 중 **133건이 FLOOR 이전 청산**이다.

기준선
  `tier_governor.VALID_FROM_FLOOR = 2026-08-09` — 수정 다음 날. 그 이전에
  **청산된** 거래를 무효로 본다. 진입이 아니라 청산 기준인 이유는 체결가
  편향이 진입·청산 양쪽에 걸리고, 청산이 끝나야 거래가 확정되기 때문이다.

무엇을 하는가 / 하지 않는가
  · **지우지 않는다.** `invalid` 와 결함 목록을 덧붙인다 — lifecycle 때와 같다.
  · 원본은 파일이다. `trades.jsonl` 에 쓰고 DB 는 재적재로 따라온다.
  · 백업을 남긴다.

사용:
  python3 -m scripts.research.invalidate_tier2_lookahead_records            # 계획만
  python3 -m scripts.research.invalidate_tier2_lookahead_records --commit   # 실제
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

SESS = ROOT / "runs" / "paper_sessions"
MANIFEST = SESS / "INVALID_TRADES_TIER2.json"
BAK_SUFFIX = ".jsonl.bak_invalidate_tier2_20260814"

FLOOR = datetime(2026, 8, 9)
DEFECT = "volume_burst_trigger_lookahead"
REASON = ("volume_burst 트리거가 자기 봉 시가에 체결돼 평균 1.47분 과거 가격에 "
          "들어갔다. 편향 제거 시 거래당 엣지 0.7203% → 0.0175%, 승률 88.4% → "
          "41.9%. 수정 cd0ca27f (2026-08-08), 기준선 VALID_FROM_FLOOR 2026-08-09")


def league_sessions() -> list[dict]:
    """리그 좌석 — `tier_governor.is_governed` 하나로만 정한다."""
    import glob
    import os
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
            out.append({"dir": Path(d), "meta": meta})
    return out


def _dt(v):
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description="2군 lookahead 구간 무효 처리")
    ap.add_argument("--commit", action="store_true", help="실제로 표기 (기본은 계획만)")
    a = ap.parse_args()

    seats = league_sessions()
    print("=" * 78)
    print(f"2군 리그 lookahead 무효 처리{'' if a.commit else ' (계획만)'}")
    print(f"기준선 VALID_FROM_FLOOR = {FLOOR:%Y-%m-%d} · 이 시각 **이전 청산**을 무효로")
    print("=" * 78)

    total = marked = already = kept = 0
    per_symbol: Counter = Counter()
    touched = []

    for s in seats:
        tf = s["dir"] / "trades.jsonl"
        if not tf.exists():
            continue
        sym = s["meta"].get("symbol", "?")
        lines = [ln for ln in tf.read_text().splitlines() if ln.strip()]
        if not lines:
            continue
        out_lines, changed = [], 0
        for ln in lines:
            try:
                t = json.loads(ln)
            except Exception:
                out_lines.append(ln)
                continue
            total += 1
            xts = _dt(t.get("exit_ts"))
            if t.get("invalid"):
                already += 1
                out_lines.append(json.dumps(t, ensure_ascii=False))
                continue
            if xts is None or xts >= FLOOR:
                kept += 1
                out_lines.append(json.dumps(t, ensure_ascii=False))
                continue
            t["invalid"] = True
            t["invalid_reason"] = REASON
            t["invalid_defects"] = [DEFECT]
            t["invalidated_on"] = "2026-08-14"
            marked += 1
            changed += 1
            per_symbol[sym] += 1
            out_lines.append(json.dumps(t, ensure_ascii=False))

        if changed:
            touched.append((sym, s["meta"].get("session_id"), changed))
            if a.commit:
                bak = tf.with_suffix(BAK_SUFFIX)
                if not bak.exists():
                    shutil.copy2(tf, bak)
                tf.write_text("\n".join(out_lines) + "\n")

    print(f"  좌석 {len(seats)}석 · 거래 {total}건")
    print(f"  무효 표기 {marked}건 · 기존 표기 {already}건 · 유지 {kept}건")
    print("-" * 78)
    for sym, sid, n in sorted(touched):
        print(f"  {sym:<10} {n:>4}건   {sid}")
    print("-" * 78)
    print("  ⚠ 기록은 **지우지 않는다.** invalid / invalid_defects 를 덧붙인다.")

    if a.commit:
        MANIFEST.write_text(json.dumps({
            "invalidated_on": "2026-08-14",
            "floor": FLOOR.strftime("%Y-%m-%d"),
            "defect": DEFECT,
            "reason": REASON,
            "fix_commit": "cd0ca27f",
            "n_marked": marked,
            "per_symbol": dict(per_symbol),
            "note": ("VB 좌석 6석은 2026-05-21 생성이라 수명 대부분이 수정 이전이다. "
                     "남는 유효 거래로는 판정할 수 없다 — 최초 유효 판정 2026-08-23."),
        }, ensure_ascii=False, indent=2))
        print(f"  명세서: {MANIFEST}")
        print(f"  백업:   각 세션의 trades{BAK_SUFFIX}")
        print("  다음: python3 -m scripts.ingest_tier_results --trades  (DB 반영)")
    else:
        print("  --commit 없이 실행 — 아무것도 쓰지 않았다")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
