"""숏 수수료 결함 수정 — 숏 계열 전량 재백테스트.

왜 정확식으로 재는가 (2026-08-12)
  수수료는 **거래 타이밍을 바꾸지 않는다.** `PolicyContext` 에 현금 필드가 없어
  (prediction / 가격 / in_position / side / entry_price / bars_held 뿐) 정책 판단이
  자본에 의존하지 않고, 강제청산(SL/TP)도 진입가에서 파생된다.

  실제 시뮬레이션으로 검증했다 — 합성 4,000바 / 485거래에서
    · 거래 시퀀스(시각·가격·사유) 완전 일치
    · 숏 수익률 차이가 이론식과 최대오차 2.45e-17 로 일치
    · 롱 수익률 변화 없음
  따라서 재시뮬레이션과 정확식 적용은 **같은 결과**다. 45GB ohlcv 를 다시 긁는
  것(심볼당 COUNT 만 57~114초)은 같은 답을 몇 시간 걸려 얻는 일일 뿐이다.

정확식
  기존 숏 수익률 r = (entry - exit) / entry   (수수료 0)
  수정 후            r' = r - fee * (2 - r)
  유도: 수수료 = qty*entry*fee + qty*exit*fee, 분모 = qty*entry
        → 감소분 = fee * (1 + exit/entry) = fee * (2 - r)

무엇이 영향받고 무엇이 안 받나
  · **영향받음** — 엔진(GenericBacktester / PaperOrchestrator)이 낸 모든 숏 성과.
    페이퍼 세션 기록, tier3_gate_validate, backtest_paper_specs.
  · **영향 안 받음** — 독립 연구 스크립트(R-1/R-2). 이들은 FRIC_BP 를 손으로
    더한다(lifecycle_variant_backtest.py 의 FRIC_BP=10.0 등).

사용:
  python3 scripts/research/short_fee_rebacktest.py
  python3 scripts/research/short_fee_rebacktest.py --fee 0.0005   # 바이낸스 테이커 실비
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if not (ROOT / "app").exists():
    ROOT = Path("/home/mint/auto_trading/backend")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("short_fee_rebt")

SESS = ROOT / "runs" / "paper_sessions"


def family_of(name: str, spec: dict) -> str:
    srcs = [s.get("type", "") for s in spec.get("sources", [])]
    for s in srcs:
        if "lifecycle" in s:
            return "lifecycle (신상저격수)"
        if "volume_burst_neg" in s:
            return "alt_volume_burst_neg (되치기)"
        if "premium" in s:
            return "premium 계열"
        if "oi_" in s or "taker" in s or "smart_money" in s:
            return "OI/테이커/스마트머니"
    pol = spec.get("policy", {}).get("type", "?")
    return f"기타 ({pol})"


def tstat(a: np.ndarray) -> float:
    if len(a) < 2:
        return float("nan")
    sd = a.std(ddof=1)
    return float(a.mean() / (sd / math.sqrt(len(a)))) if sd > 0 else float("nan")


def main() -> int:
    ap = argparse.ArgumentParser(description="숏 수수료 수정 후 재백테스트")
    ap.add_argument("--fee", type=float, default=None,
                    help="편도 요율 강제 (기본: 세션 선언 fee_rate)")
    ap.add_argument("--since", default=None,
                    help="이 진입일 이후 거래만 (예: 2026-08-09 = lookahead 수정 이후 유효구간)")
    ap.add_argument("--out", default=str(ROOT / "runs" / "research_track" /
                                         "short_fee_rebacktest.json"))
    args = ap.parse_args()

    per_sess, fam_tr = [], defaultdict(list)
    for d in sorted(os.listdir(SESS)):
        sf, tf = SESS / d / "session.json", SESS / d / "trades.jsonl"
        if not (sf.exists() and tf.exists()):
            continue
        j = json.loads(sf.read_text())
        fee = float(args.fee if args.fee is not None else j.get("fee_rate", 0.0004))
        shorts = []
        for line in tf.read_text().splitlines():
            try:
                t = json.loads(line)
            except Exception:
                continue
            if t.get("side") != "short":
                continue
            if args.since and str(t.get("entry_ts", ""))[:10] < args.since:
                continue
            shorts.append(float(t["return_pct"]))
        if not shorts:
            continue
        old = np.array(shorts, dtype=float)
        new = old - fee * (2.0 - old)          # 정확식
        fam = family_of(j.get("name", ""), j.get("pipeline_spec", {}))
        fam_tr[fam].append((old, new))
        # 순차 단일포지션 복리 (size_pct 0.95)
        eq_o = float(np.prod(1 + 0.95 * old) - 1) * 100
        eq_n = float(np.prod(1 + 0.95 * new) - 1) * 100
        per_sess.append({
            "session": d[:12], "name": j.get("name", "")[:46], "family": fam,
            "fee_bp": fee * 1e4, "n": len(old),
            "mean_o_bp": float(old.mean()) * 1e4, "mean_n_bp": float(new.mean()) * 1e4,
            "t_o": tstat(old), "t_n": tstat(new),
            "eq_o": eq_o, "eq_n": eq_n,
            "flipped": bool(old.mean() > 0 >= new.mean()),
        })

    if not per_sess:
        log.error("숏 거래를 가진 세션 없음")
        return 1

    lbl = f"{args.fee*1e4:.1f}bp(강제)" if args.fee is not None else "세션 선언값"
    print("\n" + "=" * 114)
    print(f"숏 수수료 결함 수정 — 재백테스트 (정확식, 거래 타이밍 불변 검증됨)   요율 {lbl}")
    print("=" * 114)

    print("  ** 계열별 **")
    print(f"  {'계열':<28}{'세션':>5}{'숏거래':>8}{'거래당 전':>12}{'거래당 후':>12}"
          f"{'감소bp':>9}{'잠식%':>9}{'t 전':>8}{'t 후':>8}")
    print("-" * 114)
    fam_rows = []
    for fam, lst in sorted(fam_tr.items(), key=lambda x: -sum(len(o) for o, _ in x[1])):
        o = np.concatenate([a for a, _ in lst])
        n = np.concatenate([b for _, b in lst])
        mo, mn = o.mean() * 1e4, n.mean() * 1e4
        er = abs(mo - mn) / abs(mo) * 100 if mo else float("nan")
        print(f"  {fam:<28}{len(lst):>5}{len(o):>8}{mo:>+12.1f}{mn:>+12.1f}"
              f"{mn-mo:>9.1f}{er:>8.1f}%{tstat(o):>+8.2f}{tstat(n):>+8.2f}")
        fam_rows.append({"family": fam, "n_sess": len(lst), "n": int(len(o)),
                         "mean_o_bp": mo, "mean_n_bp": mn, "erode_pct": er,
                         "t_o": tstat(o), "t_n": tstat(n)})

    allo = np.concatenate([a for lst in fam_tr.values() for a, _ in lst])
    alln = np.concatenate([b for lst in fam_tr.values() for _, b in lst])
    print("-" * 114)
    print(f"  {'전체':<28}{len(per_sess):>5}{len(allo):>8}"
          f"{allo.mean()*1e4:>+12.1f}{alln.mean()*1e4:>+12.1f}"
          f"{(alln.mean()-allo.mean())*1e4:>9.1f}"
          f"{abs(allo.mean()-alln.mean())/abs(allo.mean())*100:>8.1f}%"
          f"{tstat(allo):>+8.2f}{tstat(alln):>+8.2f}")

    flip = [r for r in per_sess if r["flipped"]]
    print("-" * 114)
    print(f"  ** 거래당 평균이 양수 → 음수로 뒤집힌 세션: {len(flip)}/{len(per_sess)} **")
    for r in sorted(flip, key=lambda x: -x["n"])[:15]:
        print(f"     {r['name']:<48}숏{r['n']:>4}건  {r['mean_o_bp']:>+8.1f}bp → "
              f"{r['mean_n_bp']:>+8.1f}bp   t {r['t_o']:>+5.2f} → {r['t_n']:>+5.2f}")

    print("-" * 114)
    print("  ** 감소폭이 큰 세션 (거래 잦은 순) **")
    print(f"  {'세션':<48}{'숏':>5}{'거래당전':>10}{'거래당후':>10}{'복리전%':>10}{'복리후%':>10}")
    for r in sorted(per_sess, key=lambda x: -x["n"])[:12]:
        print(f"  {r['name']:<48}{r['n']:>5}{r['mean_o_bp']:>+10.1f}{r['mean_n_bp']:>+10.1f}"
              f"{r['eq_o']:>+10.1f}{r['eq_n']:>+10.1f}")
    print("=" * 114 + "\n")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    json.dump({"fee_mode": lbl, "families": fam_rows, "sessions": per_sess,
               "total": {"n": int(len(allo)),
                         "mean_o_bp": float(allo.mean() * 1e4),
                         "mean_n_bp": float(alln.mean() * 1e4),
                         "t_o": tstat(allo), "t_n": tstat(alln),
                         "n_flipped": len(flip)}},
              open(args.out, "w"), ensure_ascii=False, indent=2)
    log.info("저장: %s", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
