"""초단타 새 부류 — 이산 사건(펀딩 정산) 전후의 가격 패턴.

배경 (2026-08-10, 이틀간 실측이 좁혀준 자리):
  연속 신호는 두 부류를 다 닫았다.
    자기 종목 주문흐름  gross -1.3 ~ +5.3bp   (283종목 340칸)
    종목 간 lead-lag    gross +1.0 ~ +3.1bp   (280종목 60칸, 셀당 최대 53만건)
  둘 다 시장가 마찰 11~13bp 를 못 넘는다. 서로 무관한 신호에서 같은 크기가 나왔다.

  벽을 넘으려면 gross 가 한 자릿수 배는 커야 하는데, **큰 움직임은 연속 신호가
  아니라 이산 사건에서 나온다.** 그래서 사건 부류를 연다.

무엇을 보는가
  perp 은 하루 세 번(00/08/16 UTC) 펀딩을 정산한다. **예정된 시각**이라 탐지가
  필요 없다. 메커니즘도 분명하다 — 펀딩을 내야 하는 포지션은 정산 전에 닫고,
  받는 포지션은 정산 전에 연다. 그 쏠림이 가격을 움직인다.

대조군을 반드시 같이 잰다
  정산이 없는 나머지 정각(01,02,...23시 중 00/08/16 제외)에서 같은 측정을 한다.
  같은 패턴이 모든 정각에 있다면 그건 펀딩 효과가 아니라 **알고리즘 주문의 정각
  쏠림**이고 해석이 완전히 달라진다. 대조 없이 사건 연구를 하면 달력 착시에 빠진다
  (캠페인에 weekday/monthly seasonality 로 이미 전례가 있다).

방어 조건
  · lookahead: 진입 시각의 **시가**로 체결. 신호는 그 이전 정보만.
  · 겹침 금지: 같은 종목에서 보유 겹치는 거래 없음 (사건 간격이 8시간이라 자동)
  · 마찰: 실측 스프레드 + 테이커 왕복 (방향성이므로 시장가)
  · 표본 1,000건 미만 셀은 판정하지 않는다

사용:
  python3 scripts/research/ultra_event_scan.py --days 60 --min-dvol-usd 3000000
"""
from __future__ import annotations

import argparse
import glob
import json
import logging
import os
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("ultra_event_scan")

TAKER_FEE_BP = 4.0
FUNDING_HOURS = (0, 8, 16)              # UTC 정산 시각 (기본 8h 주기)
FUNDING_HISTORY = str(ROOT / "runs" / "research_track" / "funding_history.json")
# 펀딩률 크기 구간 (절대값 bp). 유인의 크기가 곧 쏠림의 크기여야 한다.
RATE_BUCKETS = ((0.0, 1.0), (1.0, 3.0), (3.0, 10.0), (10.0, 1e9))
# 진입 시점(사건 대비 분). 음수 = 정산 전, 양수 = 정산 후.
OFFSETS = (-60, -30, -15, -5, -1, 1, 5, 15, 30)
HOLDS = (5, 15, 30, 60)
MIN_CELL = 1000


def cell_stats(rows: np.ndarray) -> dict:
    gross, spread = rows[:, 0], rows[:, 1]
    fric = (spread + 2 * TAKER_FEE_BP) / 1e4
    net = gross - fric
    n = len(net)
    sd = net.std(ddof=1) if n > 1 else 0.0
    t = float(net.mean() / (sd / np.sqrt(n))) if n > 2 and sd > 0 else float("nan")
    return {"n": n, "gross_bp": float(gross.mean() * 1e4),
            "fric_bp": float(fric.mean() * 1e4),
            "net_bp": float(net.mean() * 1e4), "t": t}


def main() -> int:
    p = argparse.ArgumentParser(description="펀딩 정산 사건 전후 가격 패턴")
    p.add_argument("--data-dir", default=str(ROOT / "runs" / "aggtrade_1m"))
    p.add_argument("--days", type=int, default=60)
    p.add_argument("--min-dvol-usd", type=float, default=3_000_000)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--by-rate", action="store_true",
                   help="펀딩률 부호·크기로 분해한다. 메커니즘상 부호가 반대면 "
                        "쏠림 방향도 반대여야 하는데, 뭉쳐 재면 상쇄되거나 한쪽이 "
                        "전부 만든 것을 못 본다")
    p.add_argument("--out", default=str(ROOT / "runs" / "research_track" /
                                        "ultra_event_scan.json"))
    args = p.parse_args()

    FR = {}
    if args.by_rate:
        import json as _j
        raw = _j.load(open(FUNDING_HISTORY))
        for sym, rows in raw.items():
            FR[sym] = {int(t) // 60000 * 60000: r for t, r in rows}   # 분 단위 키
        log.info("펀딩률 이력 %d종목 / %d건", len(FR),
                 sum(len(v) for v in FR.values()))

    files = sorted(glob.glob(os.path.join(args.data_dir, "*_agg1m.joblib")))
    if args.limit:
        files = files[:args.limit]

    # (사건종류, 진입오프셋, 보유) → [(gross, spread), ...]
    acc: dict[tuple, list] = {}
    n_used = 0
    for i, f in enumerate(files, 1):
        sym = os.path.basename(f).replace("_agg1m.joblib", "")
        try:
            d = joblib.load(f)
        except Exception:
            continue
        d = d[~d.index.duplicated(keep="last")].sort_index()
        d = d.loc[d.index >= d.index.max() - pd.Timedelta(days=args.days)]
        if len(d) < 20000:
            continue
        dv = d["quote_volume"].resample("1D").sum().median()
        if not np.isfinite(dv) or dv < args.min_dvol_usd:
            continue
        n_used += 1

        idx = d.index
        o = d["px_open"].values
        sp = d["eff_spread_bp_adj"].values
        pos = {ts: k for k, ts in enumerate(idx)}          # 시각 → 위치

        # 정각 목록. 분/초가 0 인 지점만.
        hours = idx[(idx.minute == 0)]
        for hts in hours:
            is_f = hts.hour in FUNDING_HOURS
            if args.by_rate:
                # 교락 검사: 펀딩률이 높다는 건 최근에 올랐다는 뜻이기도 하다.
                # 그러면 "높은 펀딩 → 상승" 이 정산 효과가 아니라 모멘텀일 수 있다.
                # 같은 펀딩률 구간의 종목을 **정산 없는 시각**에도 재서 갈라야 한다.
                # 대조 시각의 펀딩률은 그 직후 정산의 값을 쓴다(그 시점의 유인 크기).
                key = int(hts.timestamp() // 60 * 60 * 1000)
                if not is_f:
                    nxt = ((hts.hour // 8) + 1) * 8
                    nt = (hts.normalize() + pd.Timedelta(hours=nxt))
                    key = int(nt.timestamp() // 60 * 60 * 1000)
                rate = (FR.get(sym) or {}).get(key)
                if rate is None:
                    continue
                bp = abs(rate) * 1e4
                bkt = next((f"{lo:g}~{hi:g}bp" for lo, hi in RATE_BUCKETS
                            if lo <= bp < hi), None)
                if bkt is None:
                    continue
                kind = (("양" if rate > 0 else "음") + " " + bkt
                        + ("" if is_f else " [대조]"))
            else:
                kind = "funding" if is_f else "control"
            h0 = pos.get(hts)
            if h0 is None:
                continue
            for off in OFFSETS:
                ei = h0 + off
                if ei < 0 or ei >= len(idx):
                    continue
                # 진입 시각이 의도한 시점인지 확인 (데이터 결손 방지)
                if abs((idx[ei] - hts).total_seconds() / 60.0 - off) > 0.5:
                    continue
                for hold in HOLDS:
                    xi = ei + hold
                    if xi >= len(idx):
                        continue
                    e, x = o[ei], o[xi]
                    if not (np.isfinite(e) and np.isfinite(x)) or e <= 0:
                        continue
                    g = x / e - 1.0            # 롱 기준. 숏은 부호만 뒤집으면 된다.
                    s_ = sp[ei] if np.isfinite(sp[ei]) else np.nanmedian(sp)
                    acc.setdefault((kind, off, hold), []).append((g, s_))
        if i % 100 == 0:
            log.info("%d/%d (사용 %d)", i, len(files), n_used)

    if not acc:
        log.error("사건 0건")
        return 1
    log.info("사용 %d종목", n_used)

    res = []
    for (kind, off, hold), rows in sorted(acc.items()):
        st = cell_stats(np.array(rows))
        st.update({"kind": kind, "offset_min": off, "hold_min": hold})
        res.append(st)

    if args.by_rate:
        kinds = sorted({r["kind"] for r in res})
        print("\n" + "=" * 104)
        print(f"펀딩률 부호·크기 분해 — {n_used}종목 / 최근 {args.days}일 / 롱 기준")
        print("=" * 104)
        for off in OFFSETS:
            for hold in HOLDS:
                cells = [r for r in res if r["offset_min"] == off
                         and r["hold_min"] == hold and r["n"] >= MIN_CELL]
                if len(cells) < 4:
                    continue
                print(f"\n  진입 {off:+d}분 / 보유 {hold}분")
                for r in sorted(cells, key=lambda x: x["kind"]):
                    print(f"    {r['kind']:<14} gross {r['gross_bp']:>+8.2f}bp  "
                          f"마찰 {r['fric_bp']:>6.2f}  n {r['n']:>7,}")
        print("=" * 104 + "\n")
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        with open(args.out, "w") as fh:
            json.dump({"mode": "by_rate", "n_symbols": n_used, "results": res},
                      fh, indent=2, ensure_ascii=False)
        log.info("저장: %s", args.out)
        return 0

    # 펀딩과 대조군을 같은 (오프셋, 보유) 에서 나란히 본다
    by = {(r["kind"], r["offset_min"], r["hold_min"]): r for r in res}
    print("\n" + "=" * 100)
    print(f"펀딩 정산 사건 — {n_used}종목 / 최근 {args.days}일 / 롱 기준 "
          f"(숏은 부호 반전) / 시장가 왕복 마찰")
    print("=" * 100)
    print(f"{'진입':>7}{'보유':>7} | {'펀딩 gross':>12}{'n':>9} | "
          f"{'대조 gross':>12}{'n':>9} | {'차이(펀딩-대조)':>16}")
    print("-" * 100)
    diffs = []
    for off in OFFSETS:
        for hold in HOLDS:
            fr = by.get(("funding", off, hold))
            cr = by.get(("control", off, hold))
            if not fr or not cr or fr["n"] < MIN_CELL or cr["n"] < MIN_CELL:
                continue
            dv = fr["gross_bp"] - cr["gross_bp"]
            diffs.append((abs(dv), off, hold, fr, cr, dv))
            print(f"{off:>+7}{hold:>7} | {fr['gross_bp']:>+12.2f}{fr['n']:>9,} | "
                  f"{cr['gross_bp']:>+12.2f}{cr['n']:>9,} | {dv:>+16.2f}")
    print("=" * 100)
    if diffs:
        diffs.sort(reverse=True)
        _, off, hold, fr, cr, dv = diffs[0]
        # 방향은 차이의 부호를 따른다 (음수면 숏)
        side = "롱" if dv > 0 else "숏"
        eff_gross = abs(dv)
        fric = fr["fric_bp"]
        print(f"  최대 차이: 진입 {off:+d}분 / 보유 {hold}분 → "
              f"펀딩 {fr['gross_bp']:+.2f} vs 대조 {cr['gross_bp']:+.2f} "
              f"= {dv:+.2f}bp ({side})")
        print(f"  그 크기 대 마찰: {eff_gross:.2f}bp vs {fric:.2f}bp "
              f"→ {'넘음' if eff_gross > fric else '미달'}")
        print(f"  ※ 대조군 대비 차이를 쓰는 이유: 정각 자체의 알고리즘 쏠림을 빼야")
        print(f"     펀딩 고유 효과가 남는다. 원값은 달력 착시를 포함한다.")
    print()

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump({"n_symbols": n_used, "days": args.days, "min_cell": MIN_CELL,
                   "funding_hours_utc": list(FUNDING_HOURS), "results": res},
                  fh, indent=2, ensure_ascii=False)
    log.info("저장: %s", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
