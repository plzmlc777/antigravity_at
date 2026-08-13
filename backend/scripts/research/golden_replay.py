"""골든 재생 코퍼스 — 통합 실행기 리팩터링의 회귀 기준.

목적 (통합 실행기 계획 1단계)
  `PaperOrchestrator` 를 전 세션에 대해 전 구간 재생하고, 나온 거래 시퀀스를
  파일로 고정한다. 2단계(커널 추출)는 **이 코퍼스를 한 건도 바꾸지 않아야**
  통과다. 리팩터링이 행동을 바꾸지 않았음을 증명하는 장치다.

  파리티 게이트와 역할이 다르다:
    · 파리티 게이트 = 두 실행기가 **서로** 같은가 (교차 방향)
    · 골든 재생     = 오늘의 코드가 **어제와** 같은가 (회귀 방향)

두 가지 함정을 막는다

  1) **바 구간이 매일 자란다.** 새 바가 쌓이면 같은 코드도 다른 결과를 낸다.
     그래서 기준 파일에 `bar_end`(마지막 eval 바 시각)를 적고, 검증 때 바를
     그 시각까지 잘라낸다. 이렇게 해야 며칠 뒤에도 같은 답이 나온다.

  2) **결정적이지 않은 케이스.** 재현되지 않는 케이스는 회귀 기준이 될 수 없다.
     build 는 모든 케이스를 두 번 돌려 자기 자신과 일치하는지 확인한다.
     (이 검사를 빼면 2단계에서 "리팩터링이 깨뜨렸다"와 "원래 안 정해졌다"를
      구분할 수 없다.)

     ⚠ **2회 in-process 검사만으로는 부족하다** (2026-08-12 실측). build 에서
     비결정 0 이었는데 별도 프로세스로 --verify 하니 136건 중 6건이 어긋났다.
     전부 `lgbm` 컴포저다 — `LGBMRegressor` 에 `random_state=42` 는 있지만
     `deterministic` / `force_row_wise` / `num_threads` 가 없어 멀티스레드
     히스토그램 생성이 비트 단위로 재현되지 않는다. 시드만으로는 안 된다.

     그래서 기준 생성 절차는 **build → verify --prune** 2단계다. verify 를
     한 번 돌려 프로세스 경계를 넘겨 봐야 진짜 결정적인 케이스만 남는다.

사용:
  python3 -m scripts.research.golden_replay --build              # 1차 생성
  python3 -m scripts.research.golden_replay --verify --prune     # 비결정 제거 (필수)
  python3 -m scripts.research.golden_replay --verify             # 이후 회귀 검사
  python3 -m scripts.research.golden_replay --verify --ref <경로>

종료코드 0 = 일치, 1 = 불일치. 배포 전 훅으로 쓸 것.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import tempfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if not (ROOT / "app").exists():
    ROOT = Path("/home/mint/auto_trading/backend")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("golden")
for noisy in ("app.composer_framework.orchestrator", "paper_session_cli",
              "app.microstructure.kr_investor_flow", "app"):
    logging.getLogger(noisy).setLevel(logging.ERROR)

from app.composer_framework.orchestrator import PaperOrchestrator  # noqa: E402
from app.composer_framework.paper_session import PaperSession, SessionStore  # noqa: E402

from paper_session_cli import build_runtime_bundle  # noqa: E402
from scripts.research.engine_parity_gate import collect  # noqa: E402

# 운영 로더는 `days=800` 을 **현재 시각 기준**으로 읽어 창 시작이 매일 밀린다.
# 골든은 시작을 절대 시각으로 고정해야 하므로 넉넉히 읽어 둔 뒤 잘라 쓴다.
# 로더는 **운영과 동일하게** 둔다. 넓히면(900·1600일) 45GB ohlcv 가 I/O 로 막혀
# 25분에 20건도 못 끝낸다. 대신 기준 시작점을 창 경계에서 안쪽으로 당겨 잡아
# 여유를 만든다 — 아래 START_MARGIN_DAYS 참조.
START_MARGIN_DAYS = 100

GOLDEN_DIR = ROOT / "tests" / "golden"


def _norm(t: dict) -> list:
    """비교용 정규화. 부동소수 잡음을 없애되 실질 차이는 남긴다."""
    return [str(pd.Timestamp(t["entry_ts"])), str(pd.Timestamp(t["exit_ts"])), t["side"],
            round(float(t["entry_price"]), 10), round(float(t["exit_price"]), 10),
            round(float(t["return_pct"]), 10), t["exit_reason"]]


class _WindowUnavailable(RuntimeError):
    """기준 바 구간을 현재 데이터로 복원할 수 없음."""


def _truncate(bundle, bar_start: str | None, bar_end: str | None):
    """바 구간을 **양끝 절대 시각으로** 고정한다.

    ⚠ 2026-08-13: 처음엔 끝(`bar_end`)만 고정했는데 그것으로는 부족했다.
    운영 로더 `load_1m(symbol, days=800)` 의 조회 창이 **현재 시각 기준**이라
    하루가 지나면 맨 앞 바가 떨어져 나간다:

        2026-08-12 23:40 → 창 시작 2024-06-03
        2026-08-13 09:20 → 창 시작 2024-06-04

    그래서 데이터 시작점에 걸친 세션은 **첫 거래가 사라지고** 골든이 오탐을 냈다
    (DOGE 프리미엄지수 32→31건, AVAX 프리미엄속도 111→110건. 둘 다 첫 거래가
    2024-06-04, 즉 그날의 창 시작 경계였다). 코드 회귀로 오독할 뻔했다.

    시작을 고정하려면 창을 넉넉히 읽어야 하므로 `LOAD_DAYS` 로 넓혀 둔다.
    """
    if bundle.ohlcv_eval is None or not len(bundle.ohlcv_eval):
        return bundle
    avail = bundle.ohlcv_eval.index[0]
    if bar_start:
        lo = pd.Timestamp(bar_start)
    else:
        # 기준 생성 시: 창 경계에 딱 붙이면 다음 날 바로 밖으로 밀려난다.
        # `load_1m` 이 now-800d 부터 읽으므로, 안쪽으로 START_MARGIN_DAYS 만큼
        # 당겨 잡아 두면 그만큼(약 100일) 검증이 유효하다.
        lo = max(avail, bundle.ohlcv_eval.index[-1]
                 - pd.Timedelta(days=800 - START_MARGIN_DAYS))
    hi = pd.Timestamp(bar_end) if bar_end else bundle.ohlcv_eval.index[-1]
    if bar_start and lo < avail:
        # 요구한 시작점이 로드 범위 밖 — 잘라도 기준 구간을 복원할 수 없다.
        # 조용히 짧은 구간으로 돌면 "코드가 바뀌었다"로 오독된다. 명시적으로 실패시킨다.
        raise _WindowUnavailable(
            f"기준 시작 {lo.date()} 이 로드 범위({avail.date()}~) 밖 — LOAD_DAYS 를 늘려라")
    bundle.ohlcv_eval = bundle.ohlcv_eval.loc[lo:hi]
    if bundle.ohlcv_1m is not None and len(bundle.ohlcv_1m):
        bundle.ohlcv_1m = bundle.ohlcv_1m.loc[lo:hi + pd.Timedelta(days=1)]
    return bundle


def replay(symbol: str, spec: dict, cap: float, fee: float,
           bar_end: str | None, bar_start: str | None = None) -> dict:
    """한 케이스를 전 구간 재생하고 거래 시퀀스를 반환."""
    eval_freq = int(spec.get("config", {}).get("eval_freq_minutes", 1440))
    srcs = [s.get("type") for s in (spec.get("sources") or [])]
    try:
        bundle = build_runtime_bundle(symbol, eval_freq, srcs)
    except Exception as exc:
        return {"skipped": f"런타임 구성 실패: {type(exc).__name__}: {exc}"}
    try:
        bundle = _truncate(bundle, bar_start, bar_end)
    except _WindowUnavailable as exc:
        return {"skipped": f"구간 복원 불가: {exc}"}
    df_eval = bundle.ohlcv_eval
    if df_eval is None or len(df_eval) < 5:
        return {"skipped": "eval 바 부족"}

    with tempfile.TemporaryDirectory() as td:
        store = SessionStore(td)
        sess = PaperSession(
            session_id="golden", name=f"golden_{symbol}", symbol=symbol,
            pipeline_spec=spec, initial_capital=cap, fee_rate=fee,
            last_cycle_ts=pd.Timestamp(df_eval.index[0]).isoformat(),
        )
        store.save(sess)
        try:
            PaperOrchestrator(store).run_cycle(sess, bundle)
        except Exception as exc:
            return {"skipped": f"재생 실패: {type(exc).__name__}: {exc}"}
        trades = [_norm(t) for t in store.read_trades("golden")]
    return {"bar_start": str(pd.Timestamp(df_eval.index[0])),
            "bar_end": str(pd.Timestamp(df_eval.index[-1])),
            "n_bars": int(len(df_eval)), "trades": trades,
            "final_equity": round(float(sess.final_equity), 8),
            "side_after": sess.side}


def key_of(symbol: str, spec: dict) -> str:
    """케이스 유일키.

    ⚠ 2026-08-12: 처음엔 (심볼|policy|sources) 만 썼는데, `collect()` 는 스펙
    **전체**로 중복제거하므로 임계값·forward_bars 만 다른 스펙들이 같은 키로
    뭉개져 dict 에서 **조용히 덮어써졌다** (80건 처리 시 9건 소실). 스펙 해시를
    붙여 유일성을 보장한다. 소실은 "전부 덮었다"로 오독되므로 침묵하면 안 된다.
    """
    pol = (spec.get("policy") or {}).get("type", "?")
    srcs = "+".join(sorted(s.get("type", "?") for s in (spec.get("sources") or [])))
    h = hashlib.sha1(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:8]
    return f"{symbol}|{pol}|{srcs}|{h}"


def cmd_build(args) -> int:
    cases = collect(only_lifecycle=False, limit=args.limit)
    log.info("골든 생성: %d 케이스 (각 2회 재생 — 결정성 자체검사)", len(cases))

    entries, nondet, skipped = {}, [], []
    for i, (symbol, spec, cap, fee, pol) in enumerate(cases, 1):
        k = key_of(symbol, spec)
        r1 = replay(symbol, spec, cap, fee, None)
        if r1.get("skipped"):
            skipped.append((k, r1["skipped"]))
            continue
        # 같은 바 구간으로 한 번 더 — 자기 자신과 일치해야 기준이 될 수 있다
        r2 = replay(symbol, spec, cap, fee, r1["bar_end"], r1.get("bar_start"))
        if r2.get("skipped"):
            skipped.append((k, f"2회차 {r2['skipped']}"))
            continue
        if r1["trades"] != r2["trades"] or r1["final_equity"] != r2["final_equity"]:
            nondet.append(k)
            log.warning("%-52s 비결정적 — 기준에서 제외 (거래 %d vs %d)",
                        k[:52], len(r1["trades"]), len(r2["trades"]))
            continue
        if k in entries:                    # 키 충돌 = 케이스 소실. 침묵 금지.
            log.error("키 충돌로 케이스가 덮어써질 뻔했다: %s", k)
            raise SystemExit("골든 키가 유일하지 않다 — key_of 를 고쳐라")
        entries[k] = {"symbol": symbol, "policy": pol, "cap": cap, "fee": fee,
                      "spec": spec, **r2}
        if i % 20 == 0:
            log.info("%d/%d (기준 %d, 비결정 %d, 제외 %d)",
                     i, len(cases), len(entries), len(nondet), len(skipped))

    out = Path(args.out) if args.out else GOLDEN_DIR / "engine_golden.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "n_cases": len(cases), "n_golden": len(entries),
        "nondeterministic": nondet, "skipped": skipped,
        "entries": entries,
    }, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    print("\n" + "=" * 92)
    print(f"골든 재생 코퍼스 생성 — 케이스 {len(cases)}")
    print("=" * 92)
    print(f"  기준으로 채택   {len(entries)}")
    print(f"  비결정적 제외   {len(nondet)}" + (f"  {nondet[:6]}" if nondet else ""))
    print(f"  재생 불가 제외  {len(skipped)}")
    if skipped:
        from collections import Counter
        print(f"     사유: {dict(Counter(s.split(':')[0] for _, s in skipped))}")
    tot = sum(len(e["trades"]) for e in entries.values())
    print(f"  고정된 거래 총수 {tot}")
    # 회계가 맞는지 — 채택 + 비결정 + 제외 = 전체여야 한다. 어긋나면 소실이다.
    acct = len(entries) + len(nondet) + len(skipped)
    if acct != len(cases):
        print(f"  ** 회계 불일치: {acct} != {len(cases)} — {len(cases)-acct}건 소실 **")
    else:
        print("  회계 일치 (채택+비결정+제외 = 전체) — 소실 없음")
    print(f"  저장: {out}")
    print("=" * 92 + "\n")
    return 0


def cmd_verify(args) -> int:
    ref_path = Path(args.ref) if args.ref else GOLDEN_DIR / "engine_golden.json"
    if not ref_path.exists():
        log.error("기준 파일 없음: %s — 먼저 --build 하라", ref_path)
        return 1
    ref = json.loads(ref_path.read_text())
    entries = ref["entries"]

    # 원인 기준 제외 — 증상(관찰된 불일치)으로 거르면 안 되는 경우가 있다.
    # 2026-08-12: lgbm 비결정성은 **간헐적**이라 실행마다 불일치 목록이 바뀐다
    # (1차 6건, 2차 5건, ICPUSDT 는 2차에서 우연히 통과). 두 번 봐서 흔들리는
    # 케이스를 다 잡을 수 없으므로 원인이 되는 컴포저 타입을 통째로 뺀다.
    drop_comp = {c.strip() for c in (args.drop_composers or "").split(",") if c.strip()}
    if drop_comp:
        before = len(entries)
        removed = {k for k, e in entries.items()
                   if (e.get("spec", {}).get("composer", {}) or {}).get("type") in drop_comp}
        entries = {k: v for k, v in entries.items() if k not in removed}
        ref["entries"] = entries
        ref["dropped_composers"] = sorted(drop_comp)
        ref["dropped_by_composer"] = sorted(removed)
        ref["n_golden"] = len(entries)
        ref_path.write_text(json.dumps(ref, ensure_ascii=False, indent=2, default=str),
                            encoding="utf-8")
        log.warning("컴포저 %s 제외: %d → %d건", sorted(drop_comp), before, len(entries))

    log.info("골든 검증: %d 기준 (%s)", len(entries), ref_path)

    ok, bad, gone = 0, [], []
    for k, e in entries.items():
        r = replay(e["symbol"], e["spec"], float(e["cap"]), float(e["fee"]),
                   e["bar_end"], e.get("bar_start"))
        if r.get("skipped"):
            gone.append((k, r["skipped"]))
            continue
        if r["trades"] == e["trades"] and r["final_equity"] == e["final_equity"]:
            ok += 1
            continue
        d = None
        for i in range(max(len(r["trades"]), len(e["trades"]))):
            x = e["trades"][i] if i < len(e["trades"]) else None
            y = r["trades"][i] if i < len(r["trades"]) else None
            if x != y:
                d = {"idx": i, "기준": x, "현재": y}
                break
        bad.append({"key": k, "n_ref": len(e["trades"]), "n_now": len(r["trades"]),
                    "eq_ref": e["final_equity"], "eq_now": r["final_equity"], "first_diff": d})

    print("\n" + "=" * 92)
    print(f"골든 재생 검증 — 기준 {len(entries)}")
    print("=" * 92)
    print(f"  일치 {ok} / 불일치 {len(bad)} / 재생불가 {len(gone)}")
    for b in bad[:12]:
        print(f"\n  ✗ {b['key']}")
        print(f"      거래 {b['n_ref']} → {b['n_now']}   에쿼티 {b['eq_ref']} → {b['eq_now']}")
        if b["first_diff"]:
            print(f"      첫 차이 #{b['first_diff']['idx']}")
            print(f"        기준: {b['first_diff']['기준']}")
            print(f"        현재: {b['first_diff']['현재']}")
    if gone:
        print(f"\n  재생불가 {len(gone)}건: {[g[0] for g in gone[:5]]}")

    if args.prune:
        # 코드가 바뀌지 않은 상태에서의 불일치 = 비결정성이지 회귀가 아니다.
        # 기준 생성 직후에만 쓸 것. 리팩터링 뒤에 쓰면 진짜 회귀를 지운다.
        drop = {b["key"] for b in bad} | {g[0] for g in gone}
        kept = {k: v for k, v in entries.items() if k not in drop}
        ref["entries"] = kept
        ref["pruned_nondeterministic"] = sorted(drop)
        ref["n_golden"] = len(kept)
        ref_path.write_text(json.dumps(ref, ensure_ascii=False, indent=2, default=str),
                            encoding="utf-8")
        print(f"\n  ** prune: {len(drop)}건 제거 → 기준 {len(kept)}건 **")
        print("     (코드 미변경 상태의 불일치이므로 비결정성이다. 리팩터링 뒤에는"
              " --prune 을 쓰지 말 것 — 진짜 회귀를 지운다.)")
        print("=" * 92 + "\n")
        return 0
    print("=" * 92 + "\n")
    return 1 if (bad or gone) else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="골든 재생 코퍼스")
    ap.add_argument("--build", action="store_true", help="기준 생성 (2회 재생 자체검사 포함)")
    ap.add_argument("--verify", action="store_true", help="기준과 대조")
    ap.add_argument("--ref", help="기준 파일 경로")
    ap.add_argument("--out", help="생성 파일 경로")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--prune", action="store_true",
                    help="불일치 케이스를 기준에서 제거 (기준 생성 직후에만! "
                         "리팩터링 뒤에 쓰면 진짜 회귀를 지운다)")
    ap.add_argument("--drop-composers", default="",
                    help="이 컴포저 타입들을 기준에서 통째로 제외 (예: lgbm,xgb). "
                         "증상이 아니라 원인으로 거르는 용도")
    args = ap.parse_args()
    if args.build:
        return cmd_build(args)
    if args.verify:
        return cmd_verify(args)
    ap.error("--build 또는 --verify 필요")
    return 2


if __name__ == "__main__":
    sys.exit(main())
