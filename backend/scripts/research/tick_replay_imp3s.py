"""탄성저울 페이퍼 구간을 **틱으로** 재현한다 — 페이퍼 결과와 대조.

## 왜 (2026-09-08 대표님 지시)

페이퍼 결과는 이미 있다. 같은 구간을 원본 자료로 다시 돌려 **같은 흐름이
나오는지** 보면, 백테스트를 믿을 수 있는지 판정된다.

## 틱을 쓰는 이유 — 페이퍼가 못 보는 것을 본다

페이퍼가 읽는 `runs/bars1m` 에는 **종가(`cl`)만** 있다. 그래서 드라이버의
손절 판정은 `hi10 = 최근 1분봉 종가 10개의 최대` 다 — **분 안의 고가를 못
본다.** 거래소 STOP_MARKET 은 체결 한 건만 닿아도 발동한다.

틱으로 접으면 분 안의 진짜 고·저가 나온다. 두 판정을 나란히 내면
**페이퍼가 손절을 얼마나 놓쳤는지**가 그대로 드러난다(명세 §6 ③).

⚠ 09-01 민트 정지 사고 — 갈래 24개가 각자 521종목 틱을 통째로 풀어 20GB 를
  요구했고 서버가 멈췄다. 여기서는 **종목 하나씩 읽고 접은 뒤 원본을 버린다.**
  최고점은 한 종목·하루치다.

## 규약 (드라이버와 맞춘다 — 안 맞추면 대조가 아니다)

  · imp = (|Δlog cl|/qv).rolling(60).mean() / 그 값의 rolling(1440).median().shift(1)
    → `signal_now()` 의 imp 분기와 **수식이 같다**
  · 생존 `live = ntr.rolling(60).median().shift(1) >= 5.0`
  · 5분 격자 · 슬롯 3 · imp 최저 3 숏 · 보유 480분 · 손절 5% · 마찰 왕복 0.072%
  · 진입가·청산가 = 그 분의 **종가**(드라이버와 같다)

사용:
  python3 -m scripts.research.tick_replay_imp3s --since 2026-09-01 --smoke 30
"""
from __future__ import annotations

import argparse
import glob
import logging
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger("tickreplay")
ROOT = Path(__file__).resolve().parents[2]
TICKS = ROOT / "runs" / "ticks"

MIN_LIVE = 5.0
FEE_RT = 0.072


@dataclass(frozen=True)
class Run:
    since: str = "2026-09-01"
    warm_days: int = 2          # imp 는 1500분 후행이 필요하다
    slots: int = 3
    hold_min: int = 480
    stop_pct: float = 5.0
    step_min: int = 5


def fold(sym: str, days: list[str]) -> pd.DataFrame | None:
    """틱을 1분봉으로 접는다. **한 종목씩 읽고 원본은 버린다.**"""
    parts = []
    for d in days:
        f = TICKS / sym / f"{d}.parquet"
        if not f.exists():
            continue
        try:
            t = pd.read_parquet(f, columns=["ts_ms", "price", "qty"])
        except Exception:                                 # noqa: BLE001
            continue
        if not len(t):
            continue
        m = (t.ts_ms // 60_000) * 60_000
        g = t.groupby(m)
        parts.append(pd.DataFrame({
            "cl": g.price.last(), "hi": g.price.max(), "lo": g.price.min(),
            "qv": (t.price * t.qty).groupby(m).sum(), "ntr": g.price.size()}))
        del t
    if not parts:
        return None
    b = pd.concat(parts).sort_index()
    b = b[~b.index.duplicated(keep="last")]
    return b


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--since", default="2026-09-01")
    p.add_argument("--until", default="")
    p.add_argument("--offsets", default="",
                   help="진입 격자 시작 오프셋(분) 목록. 주면 오프셋 실험으로 돈다")
    p.add_argument("--smoke", type=int, default=0)
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    r = Run(since=a.since)
    t0 = time.time()

    syms = sorted(x.name for x in TICKS.iterdir() if x.is_dir())
    if a.smoke:
        syms = syms[:a.smoke]
    # ⚠ 시간대를 섞지 않는다 — naive 로 통일한다(파일명이 UTC 날짜다)
    d0 = pd.Timestamp(r.since).tz_localize(None) - pd.Timedelta(days=r.warm_days)
    d1 = (pd.Timestamp(a.until).tz_localize(None) if a.until
          else pd.Timestamp.utcnow().tz_localize(None).normalize())
    days = [d.strftime("%Y-%m-%d") for d in pd.date_range(d0, d1, freq="D")]
    log.info("종목 %d · 날 %s ~ %s (워밍업 %d일 포함)",
             len(syms), days[0], days[-1], r.warm_days)

    ser = {}
    for i, s in enumerate(syms, 1):
        b = fold(s, days)
        if b is None or len(b) < 1600:
            continue
        c = b.cl.to_numpy(float)
        qv = b.qv.to_numpy(float)
        ar = np.abs(np.diff(np.log(np.maximum(c, 1e-12)), prepend=np.nan)) * 100.0
        ai = pd.Series(ar / np.maximum(qv, 1e-9)).rolling(60).mean()
        med = ai.rolling(1440, min_periods=360).median().shift(1)
        b["imp"] = (ai / med.where(med > 0)).to_numpy()
        b["live"] = b.ntr.rolling(60).median().shift(1).to_numpy()
        ser[s] = b[["cl", "hi", "lo", "imp", "live"]]
        if i % 100 == 0:
            log.info("  [%d/%d] %.1f분", i, len(syms), (time.time() - t0) / 60)
    if not ser:
        raise SystemExit("접힌 종목이 0")
    names = sorted(ser)
    lo_ms = max(int(min(x.index.min() for x in ser.values())),
                int(pd.Timestamp(r.since).tz_localize("UTC").timestamp() * 1000))
    hi_ms = int(max(x.index.max() for x in ser.values()))
    grid = np.arange((lo_ms // 60_000) * 60_000, hi_ms + 60_000, 60_000)
    n, m = len(grid), len(names)
    C = np.full((n, m), np.nan, np.float32)
    HI = np.full((n, m), np.nan, np.float32)
    I = np.full((n, m), np.nan, np.float32)
    LV = np.full((n, m), np.nan, np.float32)
    for j, s in enumerate(names):
        y = ser[s].reindex(grid)
        C[:, j] = y.cl.to_numpy(np.float32)
        HI[:, j] = y.hi.to_numpy(np.float32)
        I[:, j] = y.imp.to_numpy(np.float32)
        LV[:, j] = y.live.to_numpy(np.float32)
    del ser
    log.info("적재 완료 %.1f분 · 종목 %d · 분 %d · 배열 %.0f MB",
             (time.time() - t0) / 60, m, n, 4 * C.nbytes / 1e6)

    def sim(true_high: bool, off: int = 0):
        """true_high=False 면 드라이버와 같이 **종가 10개의 최대**로 손절 본다.

        `off` 는 진입 격자의 시작 오프셋(분). 규칙은 그대로 두고 **언제
        슬롯이 비는가**만 바꾼다 — 성적이 신호에서 오는지 슬롯 운에서
        오는지 가르는 장치다.
        """
        step = r.step_min
        hb = r.hold_min
        book: dict[int, tuple[int, float]] = {}
        tr = []
        for t in range(off, n - 1, step):
            px = C[t]
            for j in list(book):
                t0_, p0 = book[j]
                a0 = max(t0_ + 1, t - 9)
                seg = (HI[a0:t + 1, j] if true_high else C[a0:t + 1, j])
                seg = seg[np.isfinite(seg)]
                hit = bool(seg.size and seg.max() >= p0 * (1 + r.stop_pct / 100))
                if hit:
                    tr.append((-r.stop_pct - FEE_RT, "stop", names[j],
                               grid[t0_], grid[t]))
                    del book[j]
                elif t - t0_ >= hb:
                    if not np.isfinite(px[j]):
                        continue
                    tr.append((100.0 * (p0 - px[j]) / p0 - FEE_RT, "exp",
                               names[j], grid[t0_], grid[t]))
                    del book[j]
            free = r.slots - len(book)
            if free <= 0:
                continue
            v = I[t].copy()
            bad = ~(np.isfinite(v) & np.isfinite(px) & (LV[t] >= MIN_LIVE))
            for j in book:
                bad[j] = True
            v[bad] = np.inf
            for j in np.argsort(v)[:free]:
                if bad[j]:
                    break
                book[int(j)] = (t, float(px[j]))
        return tr

    print(f"\n■ 탄성저울 틱 재현 — 종목 {m} · "
          f"{pd.Timestamp(grid[0], unit='ms')} ~ {pd.Timestamp(grid[-1], unit='ms')}")
    print(f"  {'손절 판정':>22}{'거래':>7}{'거래당%':>10}{'승률':>7}{'손절':>7}{'자본%':>10}")
    if a.offsets:
        # ── 오프셋 실험 — 규칙은 그대로, 진입 격자만 밀어본다.
        #    같은 일주일에서 성적이 얼마나 흩어지는지가 곧 '슬롯 운'의 크기다.
        offs = [int(x) for x in a.offsets.split(",")]
        rows = []
        for off in offs:
            tr = sim(False, off)
            if not tr:
                continue
            net = np.array([x[0] for x in tr])
            e = np.cumprod(1 + net / r.slots / 100)
            rows.append((off, len(net), net.mean(), 100 * (e[-1] - 1),
                         sum(1 for x in tr if x[1] == "stop"),
                         float(net.max())))
        print(f"\n■ 오프셋 실험 — 종목 {m} · {pd.Timestamp(grid[0], unit='ms')}"
              f" ~ {pd.Timestamp(grid[-1], unit='ms')} · 규칙 동일, 격자만 이동")
        print(f"  {'오프셋(분)':>10}{'거래':>7}{'거래당%':>10}{'자본%':>10}"
              f"{'손절':>7}{'최고거래%':>11}")
        cap = []
        for off, k, mu, capv, st_, mx in rows:
            cap.append(capv)
            print(f"  {off:>10}{k:>7}{mu:>+10.4f}{capv:>+10.2f}{st_:>7}{mx:>+11.2f}")
        cap = np.array(cap)
        print(f"\n  자본% — 중앙 {np.median(cap):+.2f} · 평균 {cap.mean():+.2f} "
              f"· 최저 {cap.min():+.2f} · 최고 {cap.max():+.2f} "
              f"· 표준편차 {cap.std(ddof=1):.2f}")
        print(f"  양수 {int((cap > 0).sum())}/{len(cap)}")
        log.info("완료 %.1f분", (time.time() - t0) / 60)
        return 0

    dumps = {}
    for lab, th in (("분 종가 10개(드라이버)", False), ("틱 진짜 고가", True)):
        tr = sim(th)
        dumps[th] = tr
        if not tr:
            print(f"  {lab:>22}  거래 0")
            continue
        net = np.array([x[0] for x in tr])
        e = np.cumprod(1 + net / r.slots / 100)
        print(f"  {lab:>22}{len(net):>7}{net.mean():>+10.4f}"
              f"{100 * (net > 0).mean():>6.0f}%"
              f"{sum(1 for x in tr if x[1] == 'stop'):>7}"
              f"{100 * (e[-1] - 1):>+10.2f}")
    # ── 거래 목록을 남긴다 — 페이퍼 원장과 **종목·시각 단위**로 대조하려면
    #    합계만으로는 왜 갈렸는지 못 밝힌다.
    out = ROOT / "runs" / "research_track" / "tick_replay_imp3s"
    out.mkdir(parents=True, exist_ok=True)
    for th, tr in dumps.items():
        if not tr:
            continue
        pd.DataFrame(
            [{"net_pct": x[0], "why": x[1], "symbol": x[2],
              "entry_ts": pd.Timestamp(x[3], unit="ms", tz="UTC"),
              "closed_ts": pd.Timestamp(x[4], unit="ms", tz="UTC")} for x in tr]
        ).to_csv(out / f"trades_{'tickhigh' if th else 'driver'}.csv", index=False)
    log.info("거래 목록 저장 → %s", out)
    log.info("완료 %.1f분", (time.time() - t0) / 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
