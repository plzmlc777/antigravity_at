#!/usr/bin/env python3
"""`X or Y` 폴백 전수 심사 — 0이 유효 기록값인데 다른 값으로 대체되는 곳 찾기.

2026-08-08 조사에서 실자금에 영향을 준 결함 3건이 전부 이 한 줄짜리 관용구에서
나왔다. `or` 는 0.0 과 None 을 구분하지 못하는데 이 코드베이스는 두 값에 다른
의미를 부여한다 — 0은 "기록된 값"(미체결 수량 0, 체결가 미상 0)이고 None은
"미설정"이다.

  live_context: p.executed_price = res.get("price") or p.theoretical_price
      → 거래소가 체결가를 안 주면 이론가로 조용히 대체. 실계좌 23건이 System-2
        바 종가로 기록돼 원장 대비 +0.71 USDT 오차.
  live_context: q = ex.filled_quantity or ex.requested_quantity or 0
      → 미체결(0)을 요청수량으로 바꿔 유령 홀딩 생성. 페이퍼 74건 해당.
  orchestrator: tp_price = action.tp_price or price * 0.90
      → 정책이 "익절 없음"으로 반환한 0.0 을 10% 익절로 바꿔치기. 실자금 43일 오염.

판정:
  X or Y ... or Z 에서 **최종 폴백이 상수 0/0.0 이면 안전**하다 — X가 0일 때
  결과도 0이라 의미가 바뀌지 않는다. 최종 폴백이 그 외의 값이면 위험이다.
  0이 유효한 기록값인 도메인(가격·수량·손익·잔고)에서만 문제가 되므로
  식별자 이름으로 도메인을 좁힌다.

사용:
  python scripts/research/audit_or_fallbacks.py            # 위험 + 검토만
  python scripts/research/audit_or_fallbacks.py --all      # 안전 건까지
  python scripts/research/audit_or_fallbacks.py --json
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SCAN_DIRS = ["app", "scripts"]
# 실거래 자금에 직접 닿는 경로 — 여기의 위험 건이 최우선
CRITICAL_PREFIXES = ("app/core", "app/services", "app/adapters", "scripts/binance")

MONEY_TOKENS = (
    "price", "qty", "quantity", "amount", "notional", "margin", "balance",
    "capital", "cash", "fee", "fees", "pnl", "profit", "leverage", "equity",
    "cost", "proceeds", "size", "value", "commission", "realized",
)
# 도메인은 맞지만 0이 유효값이 아닌 것들 (임계치·비율 설정값 등)
IGNORE_TOKENS = ("pct", "ratio", "threshold", "rate_limit", "precision", "decimals")


def _name_of(node: ast.AST) -> str:
    if isinstance(node, ast.Attribute):
        return f"{_name_of(node.value)}.{node.attr}"
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Call):
        return _name_of(node.func)
    if isinstance(node, ast.Subscript):
        return _name_of(node.value)
    if isinstance(node, ast.Constant):
        return repr(node.value)
    if isinstance(node, ast.BinOp):
        return f"{_name_of(node.left)}<op>{_name_of(node.right)}"
    return type(node).__name__


def _is_zero_const(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) \
        and not isinstance(node.value, bool) and node.value == 0


def _money_related(text: str) -> bool:
    low = text.lower()
    if any(t in low for t in IGNORE_TOKENS):
        return False
    return any(t in low for t in MONEY_TOKENS)


def scan_file(path: Path) -> list[dict]:
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(src)
    except Exception:
        return []
    lines = src.split("\n")
    out = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or)):
            continue
        vals = node.values
        expr = " or ".join(_name_of(v) for v in vals)
        if not _money_related(expr):
            continue
        last = vals[-1]
        safe = _is_zero_const(last)
        code = lines[node.lineno - 1] if node.lineno <= len(lines) else ""
        # 사람이 판정을 끝낸 곳은 `or-audit: safe — 이유` 주석으로 억제한다.
        # 판정 결과가 코드에 남아야 다음 감사에서 새 건만 떠오른다.
        # 마커는 같은 줄이거나 **바로 위 주석 블록 안** 어디든 있으면 된다
        # (직전 한 줄만 보면 여러 줄 근거를 적은 곳을 놓친다).
        reviewed = "or-audit: safe" in code
        i = node.lineno - 2
        while not reviewed and i >= 0:
            s = lines[i].strip()
            if not s.startswith("#"):
                break
            if "or-audit: safe" in s:
                reviewed = True
            i -= 1
        rel = str(path.relative_to(ROOT))
        out.append({
            "file": rel,
            "line": node.lineno,
            "expr": expr,
            "code": code.strip()[:150],
            "verdict": "안전" if safe else ("판정완료" if reviewed else "위험"),
            "critical": rel.startswith(CRITICAL_PREFIXES),
            "fallback": _name_of(last),
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    findings = []
    for d in SCAN_DIRS:
        for p in sorted((ROOT / d).rglob("*.py")):
            if "venv" in p.parts or "__pycache__" in p.parts or p.name.startswith("test_"):
                continue
            findings.extend(scan_file(p))

    risky = [f for f in findings if f["verdict"] == "위험"]
    safe = [f for f in findings if f["verdict"] == "안전"]
    reviewed = [f for f in findings if f["verdict"] == "판정완료"]
    crit = [f for f in risky if f["critical"]]

    if args.json:
        print(json.dumps({"total": len(findings), "risky": risky, "safe_count": len(safe)},
                         indent=2, ensure_ascii=False))
        return 0

    print(f"전체 {len(findings)}건 | 안전 {len(safe)} | 판정완료 {len(reviewed)} "
          f"| 위험 {len(risky)} (그중 실거래 경로 {len(crit)})\n")

    print("=" * 100)
    print("실거래 경로 위험 건 (app/core, app/services, app/adapters, scripts/binance)")
    print("=" * 100)
    for f in sorted(crit, key=lambda x: (x["file"], x["line"])):
        print(f"  {f['file']}:{f['line']}")
        print(f"      {f['code']}")
        print(f"      → 0일 때 '{f['fallback']}' 로 대체됨")
    if not crit:
        print("  없음")

    other = [f for f in risky if not f["critical"]]
    print()
    print("=" * 100)
    print(f"그 외 위험 건 ({len(other)})")
    print("=" * 100)
    for f in sorted(other, key=lambda x: (x["file"], x["line"])):
        print(f"  {f['file']}:{f['line']:<5} {f['code'][:110]}")

    if args.all:
        print()
        print("=" * 100)
        print(f"안전 건 ({len(safe)}) — 최종 폴백이 0이라 의미 불변")
        print("=" * 100)
        for f in sorted(safe, key=lambda x: (x["file"], x["line"])):
            print(f"  {f['file']}:{f['line']:<5} {f['code'][:110]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
