"""틱 → 1분봉 백필. 수집기가 앞으로 만들 것을 **과거에 대해** 만든다.

## 왜 (2026-09-01)

봉을 읽는 쪽(`kinematics_paper.bars`)을 먼저 바꾸면 과거 봉이 없어 전
종목이 틱으로 되돌아간다 — 고치려던 문제가 그대로다. 그래서 이 도구로
과거를 먼저 채운다.

⚠ 열을 늘렸을 땐 `--rebuild` 로 다시 만들어야 한다. 안 하면 읽는 쪽이
  `KeyError` 를 내거나, 더 나쁘게는 **낡은 열로 조용히 계산한다**.

사용:
  python3 -m scripts.binance.build_bars1m --smoke 5        # 예비비행
  python3 -m scripts.binance.build_bars1m --workers 4
  python3 -m scripts.binance.build_bars1m --rebuild        # 있는 것도 다시
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.binance import tickbars                          # noqa: E402

log = logging.getLogger("bars1m")


def one(job):
    """한 (종목, 날짜) 를 접는다. **날짜 파일 하나만** 본다 — 하루 경계에서
    직전 틱을 못 이어받지만, 그건 하루에 틱 하나 몫이고 수집기 경로와
    **같은 방식**이라 둘이 어긋나지 않는다."""
    sym, f, rebuild = job
    day = f.stem
    out = tickbars.bar_path(sym, day)
    if out.exists() and not rebuild and out.stat().st_mtime >= f.stat().st_mtime:
        return sym, day, 0, True
    try:
        b = tickbars.fold_raw(tickbars.read_chunks([f], 0), min_ticks=1)
    except Exception as e:                                     # noqa: BLE001
        log.warning("%s %s 접기 실패: %s", sym, day, e)
        return sym, day, 0, False
    if b is None:
        return sym, day, 0, False
    return sym, day, tickbars.write_bars(sym, day, b), False


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--workers", type=int, default=3,
                   help="⚠ 실계좌·페이퍼와 같은 서버다. 4를 넘기지 마라")
    p.add_argument("--smoke", type=int, default=0,
                   help="N종목만 — 본실행과 **같은 경로**로 먼저 확인한다")
    p.add_argument("--days", type=int, default=2, help="최근 N일치만")
    p.add_argument("--rebuild", action="store_true",
                   help="이미 있고 최신이어도 다시 만든다(열을 늘렸을 때)")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    syms = sorted(d.name for d in tickbars.TICKS.iterdir() if d.is_dir())
    if a.smoke:
        # 큰 것부터 — 최고점도 시간도 여기서 나온다
        syms = sorted(syms, key=lambda s: -sum(
            f.stat().st_size for f in (tickbars.TICKS / s).glob("*.parquet")
        ))[:a.smoke]
    jobs = []
    for s in syms:
        for f in sorted((tickbars.TICKS / s).glob("*.parquet"))[-a.days:]:
            jobs.append((s, f, a.rebuild))
    log.info("1분봉 백필 — 종목 %d · 파일 %d · 워커 %d · 최근 %d일",
             len(syms), len(jobs), a.workers, a.days)

    t0 = time.time()
    rows = skip = fail = 0
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        for i, (sym, day, n, sk) in enumerate(ex.map(one, jobs), 1):
            if sk:
                skip += 1
            elif n:
                rows += n
            else:
                fail += 1
            if i % 100 == 0 or i == len(jobs):
                el = time.time() - t0
                log.info("[%d/%d] 봉 %s · 건너뜀 %d · 실패 %d · %.1f분 · 남은 %.1f분",
                         i, len(jobs), f"{rows:,}", skip, fail, el / 60,
                         (len(jobs) - i) * el / i / 60)
    sz = sum(f.stat().st_size for f in tickbars.BARS.rglob("*.parquet"))
    log.info("완료 — 봉 %s행 · %.1f분 · 디스크 %.1f MB (틱 %.1f MB 의 %.1f%%)",
             f"{rows:,}", (time.time() - t0) / 60, sz / 1048576,
             sum(f.stat().st_size for f in tickbars.TICKS.rglob("*.parquet")) / 1048576,
             100 * sz / max(sum(f.stat().st_size
                                for f in tickbars.TICKS.rglob("*.parquet")), 1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
