"""바뀐 판정이 **회귀를 여전히 잡는지** 증명한다. 실제 파일은 건드리지 않는다."""
import sys
sys.path.insert(0, "/home/mint/auto_trading/backend")
sys.path.insert(0, "/home/mint/auto_trading/backend/scripts")
from scripts.research.golden_replay import _case_same

FLAT = {"trades": [["a"]], "final_equity": 1_000_000.0, "side_after": "flat"}
OPEN = {"trades": [["a"]], "final_equity": 1_000_000.0, "side_after": "short"}

def chk(name, ref, now, want_same, want_skip):
    same, skip = _case_same(ref, now)
    ok = (same == want_same and skip == want_skip)
    print(f"  {'✔' if ok else '✗'} {name:<52} 일치={same} 평가액제외={skip}")
    return ok

allok = True
allok &= chk("청산·동일 → 통과", FLAT, dict(FLAT), True, False)
allok &= chk("청산·평가액만 다름 → **잡는다**", FLAT,
             {**FLAT, "final_equity": 1_000_100.0}, False, False)
allok &= chk("미청산·평가액만 다름 → 통과(의도)", OPEN,
             {**OPEN, "final_equity": 1_000_100.0}, True, True)
allok &= chk("미청산·거래가 다름 → **잡는다**", OPEN,
             {**OPEN, "trades": [["b"]]}, False, False)
allok &= chk("미청산·종료 방향이 다름 → **잡는다**", OPEN,
             {**OPEN, "side_after": "long"}, False, False)
allok &= chk("미청산 → 청산으로 바뀜 → **잡는다**", OPEN,
             {**OPEN, "side_after": "flat"}, False, False)
allok &= chk("청산·8번째 소수 차이 → 통과(배정밀도)", FLAT,
             {**FLAT, "final_equity": 1_000_000.0 + 1e-7}, True, False)
print("\n결과:", "전부 의도대로" if allok else "**어긋남 있음**")
raise SystemExit(0 if allok else 1)
