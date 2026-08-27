"""이미 쌓인 틱에서 가짜 체결(가격 0·수량 0)을 걷어낸다 — 한 번만 쓰면 되는 도구.

## 왜 (2026-08-27)

바이낸스 `@trade` 가 `p:"0" q:"0" X:"NA" st:1` 인 메시지를 섞어 보낸다. 수집기가
받은 대로 저장해서 1억 1,948만 건 중 13만 1,362건(0.110%)이 들어갔다.

0 하나가 섞이면 최저가가 0, 로그수익률이 -inf 가 된다. 실측에서 1000BONKUSDT
24시간 변동폭이 **105%** 로 나왔는데 실제는 4% 였다. 봉수·타임스탬프는 멀쩡해
**대조 없이는 안 보인다** — 1분봉 오염 때(2026-08-15)와 같은 모양이다.

수집기는 이제 받는 자리에서 버린다. 이 도구는 **그 전에 쌓인 것**만 처리한다.

⚠ 수집기를 **멈추고** 돌려라. 수집기는 flush 때 그날 파일을 읽어서 다시 쓴다.
  동시에 고치면 그 사이 받은 체결이 사라진다.

⚠ 지운 수를 종목별로 남긴다. 조용히 줄어들면 나중에 "원래 그랬다"가 된다.

사용:
  python3 -m scripts.binance.clean_tick_zeros --dry-run
  python3 -m scripts.binance.clean_tick_zeros --commit
"""
from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
TICKS = ROOT / "runs" / "ticks"

log = logging.getLogger("clean_tick")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--commit", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    commit = a.commit and not a.dry_run

    files = sorted(TICKS.rglob("*.parquet"))
    log.info("파일 %d개 · 모드 %s", len(files), "정리" if commit else "점검만")
    t0 = time.time()
    n_rows = n_bad = n_files = 0
    worst: list[tuple[str, int, int]] = []
    for i, f in enumerate(files, 1):
        d = pd.read_parquet(f)
        bad = int(((d.price <= 0) | (d.qty <= 0)).sum())
        n_rows += len(d)
        if bad:
            n_bad += bad
            n_files += 1
            worst.append((f"{f.parent.name}/{f.stem}", len(d), bad))
            if commit:
                keep = d[(d.price > 0) & (d.qty > 0)]
                # ⚠ 수집기와 **같은 규약**으로 쓴다 — 정렬·압축이 다르면 용량이 튄다
                keep.sort_values("ts_ms").to_parquet(
                    f, compression="zstd", index=False)
        if i % 200 == 0 or i == len(files):
            log.info("[%d/%d] 검사 %s행 · 가짜 %s행 · %.1f분", i, len(files),
                     f"{n_rows:,}", f"{n_bad:,}", (time.time() - t0) / 60)

    log.info("%s — 전체 %s행 중 가짜 %s행(%.4f%%) · 파일 %d/%d",
             "정리 완료" if commit else "점검 완료",
             f"{n_rows:,}", f"{n_bad:,}", 100.0 * n_bad / max(n_rows, 1),
             n_files, len(files))
    worst.sort(key=lambda x: -x[2])
    for k, n, b in worst[:8]:
        log.info("  %-28s %6d / %10s  (%.4f%%)", k, b, f"{n:,}", 100.0 * b / n)
    if not commit:
        log.info("점검만 했다. 실제 정리는 --commit (수집기를 먼저 멈춰라)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
