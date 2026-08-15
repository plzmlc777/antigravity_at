"""모멘텀 요인 — 파라미터 격자 × **다중 분할**.

왜 둘을 함께 보나
    2026-08-15 첫 측정: 정렬 14일 / 보유 7일에서 표본 안 연 +62.2%(t 2.24)인데
    표본 밖(26기간)이 연 **-47.2%** 였다. 그런데 그 구간이 하필 시장 +90% 인
    **강반등장**이고, 그건 모멘텀 붕괴가 나타나는 전형적 국면이다.

    표본 밖 하나로 요인을 기각하면 "한 국면에서 졌다고 버리는 것"이고,
    받아들이면 어제 네 번 밟은 함정을 다섯 번째로 밟는 것이다.

    가르는 법은 **분할일을 옮겨가며 여러 국면에서 보는 것**이다.
      · 모든 분할에서 표본 밖이 음수     → 요인이 죽었다
      · 특정 국면에서만 음수             → 국면 의존. 그 국면을 식별해야 한다
      · 파라미터를 바꾸면 살아난다면     → 과최적화 의심(고원인지 확인)

⚠ 베타 중립화는 무의미했다
    첫 측정에서 표본 안 베타 **+0.023** · 시장 상관 +0.033 이었다. 롱·숏 종목
    수가 같으면(달러 중립) 공통 움직임이 이미 상쇄된다. 그래서 이 격자는
    총수익 대신 **순수익(마찰 차감)** 만 본다.

⚠ 마찰은 병목이 아니다
    회전율 46% · 연환산 마찰 2.41% · **마찰/총수익 4.4%**. 논문들이 회피한
    지점인데 주간 리밸런싱에서는 여유가 있다. 그래서 격자를 넓게 볼 수 있다.

사용:
  python3 -m scripts.research.momentum_factor_grid
"""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from itertools import product
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("mom_grid")

OUT = ROOT / "runs" / "research_track" / "momentum_factor_grid.json"
TMP = "/tmp/_mom_cell.json"


def run_cell(lookback: int, hold: int, split: str, fee_bp: float) -> dict | None:
    cmd = [sys.executable, "-W", "ignore", "-m",
           "scripts.research.crypto_momentum_factor",
           "--split", split, "--lookback", str(lookback), "--hold", str(hold),
           "--fee-bp", str(fee_bp), "--out", TMP]
    r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                       env={**__import__("os").environ,
                            "PYTHONPATH": f".:{ROOT / 'scripts'}"}, timeout=900)
    if r.returncode != 0:
        log.warning("실패 lb=%s hold=%s split=%s: %s", lookback, hold, split,
                    r.stderr[-200:])
        return None
    try:
        return json.loads(Path(TMP).read_text())
    except Exception:
        return None


def main() -> int:
    p = argparse.ArgumentParser(description="모멘텀 요인 격자 × 다중 분할")
    p.add_argument("--lookbacks", default="7,14,30,60")
    p.add_argument("--holds", default="7,14,30")
    p.add_argument("--splits", default="2025-08-01,2025-11-01,2026-02-01,2026-05-01")
    p.add_argument("--fee-bp", type=float, default=5.0)
    p.add_argument("--out", default=str(OUT))
    a = p.parse_args()

    lbs = [int(x) for x in a.lookbacks.split(",") if x.strip()]
    hds = [int(x) for x in a.holds.split(",") if x.strip()]
    sps = [x.strip() for x in a.splits.split(",") if x.strip()]
    log.info("격자 %d × %d · 분할 %d개 = 총 %d회 실행",
             len(lbs), len(hds), len(sps), len(lbs) * len(hds) * len(sps))

    cells = []
    for lb, hd in product(lbs, hds):
        for sp in sps:
            d = run_cell(lb, hd, sp, a.fee_bp)
            if not d:
                continue
            r = d["results"]
            cells.append({
                "lookback": lb, "hold": hd, "split": sp,
                "periods_per_year": d["periods_per_year"],
                "is_n": r.get("IS/net", {}).get("n"),
                "is_net": r.get("IS/net", {}).get("mean"),
                "is_t": r.get("IS/net", {}).get("t"),
                "oos_n": r.get("OOS/net", {}).get("n"),
                "oos_net": r.get("OOS/net", {}).get("mean"),
                "oos_t": r.get("OOS/net", {}).get("t"),
                "turnover": r.get("IS/turnover", {}).get("mean"),
                "friction": r.get("IS/friction", {}).get("mean"),
                "mkt_oos": r.get("OOS/mkt", {}).get("mean"),
            })
            log.info("lb=%-3d hold=%-3d split=%s → IS %+.3f (t %+.2f) · "
                     "OOS %+.3f (t %+.2f, n=%s)", lb, hd, sp,
                     cells[-1]["is_net"] or 0, cells[-1]["is_t"] or 0,
                     cells[-1]["oos_net"] or 0, cells[-1]["oos_t"] or 0,
                     cells[-1]["oos_n"])

    Path(a.out).write_text(json.dumps({"cells": cells}, ensure_ascii=False,
                                      indent=2))

    print("=" * 100)
    print(f"모멘텀 요인 격자 — {len(cells)}칸 (정렬 {lbs} × 보유 {hds} × 분할 {len(sps)})")
    print("=" * 100)
    print(f"  {'정렬':>5}{'보유':>5}{'분할':>13}{'IS n':>6}{'IS 순%':>9}{'IS t':>7}"
          f"{'OOS n':>7}{'OOS 순%':>10}{'OOS t':>7}{'OOS 시장%':>11}")
    for c in cells:
        print(f"  {c['lookback']:>5}{c['hold']:>5}{c['split']:>13}{c['is_n'] or 0:>6}"
              f"{(c['is_net'] or 0):>9.3f}{(c['is_t'] or 0):>7.2f}"
              f"{c['oos_n'] or 0:>7}{(c['oos_net'] or 0):>10.3f}"
              f"{(c['oos_t'] or 0):>7.2f}{(c['mkt_oos'] or 0):>11.3f}")

    print("-" * 100)
    # ── 판정 ──
    by_split: dict[str, list] = {}
    for c in cells:
        by_split.setdefault(c["split"], []).append(c["oos_net"] or 0)
    print("  **분할별 표본 밖 순수익 — 국면 의존인가 요인 사망인가**")
    for sp in sps:
        v = np.array(by_split.get(sp, []))
        if not len(v):
            continue
        print(f"     {sp}   평균 {v.mean():+.3f}%/기간 · "
              f"양수 칸 {int((v > 0).sum())}/{len(v)}")
    allv = np.array([c["oos_net"] or 0 for c in cells])
    pos = int((allv > 0).sum())
    print(f"     전체    양수 칸 **{pos}/{len(allv)}**")
    if pos == 0:
        print("     → 모든 분할·모든 파라미터에서 표본 밖이 음수. **요인이 죽었다**")
    elif pos < len(allv) * 0.3:
        print("     → 대부분 음수. 살아난 칸은 우연일 가능성이 높다")
    else:
        print("     → 국면 의존으로 보인다. 어느 국면에서 죽는지 식별해야 한다")
    print("=" * 100)
    print(f"  → {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
