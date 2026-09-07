"""손절 후 **재진입 금지**가 무엇을 바꾸나 — 14개월 패널 · 5분 장부 시늉.

## 왜 (2026-09-07)

실거래에서 AKEUSDT 가 06:45 숏 진입 → 06:50 손절 −5.147% → **같은 사이클에
같은 방향으로 재진입** → 07:35 손절 −4.313%. 합 −9.46%. 중복 배제가
`현재 보유`만 봐서 방금 닫힌 종목이 곧바로 다시 후보가 됐다.

## 왜 새 하네스인가

`stop_loss_test.py` 는 앵커가 **보유 기간(120분) 간격**이다. 그래서 "손절로
슬롯이 일찍 비어 5분 뒤 재진입"이라는 상황 자체가 만들어지지 않는다.
이 축을 재려면 **5분 격자 + 진짜 장부**가 있어야 한다.

## 규약 (앞 하네스와 맞춘다 — 안 맞추면 손절 5% 결정과 비교가 안 된다)

  · 신호·밴드·가속은 `stop_loss_test.feats` 를 그대로 쓴다. 다시 구현하지 않는다
  · 경로는 **1분 종가**로 본다. 이 패널에는 고가·저가가 없다(칸: cl, ntr, …)
  · 손절은 손절가 정확 체결로 본다(지정가 가정). 대표님 지시대로 지정가
    슬리피지는 문제 삼지 않는다
  · 마찰 왕복 0.072% — 앞 하네스와 **같은 값**. 실거래 실측은 0.098% 라
    낙관 쪽이지만, 여기서 재는 것은 **냉각의 증분**이라 두 팔에 같이 걸린다
  · 진입은 5분 격자에서만. 청산 판정도 5분 격자에서만 — 엔진이 그렇게 돈다

## 위약 (교훈#91·#95)

냉각을 켜면 **거래가 줄어든다.** 줄어서 좋아진 것인지, 손절당한 그 종목을
피해서 좋아진 것인지 갈라야 한다. 그래서 대조군을 둔다 —
**무작위 종목을 같은 기간 막는다**(손절당한 종목은 그대로 열어 둔다).
실측이 이 위약을 못 이기면 "재진입 금지"가 아니라 "덜 거래하기"가 번 것이다.

사용:
  python3 -m scripts.research.kine_reentry_test --cooldowns 0,5,15,30,60,120
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.research.stop_loss_test import Cfg, feats

log = logging.getLogger("reentry")
ROOT = Path(__file__).resolve().parents[2]
MICRO = ROOT / "runs" / "micro1m"


@dataclass(frozen=True)
class Run:
    """이 실행의 설정 **전문**. 하네스 규칙 — 즉석 하드코딩 금지."""
    step_min: int = 5           # 엔진 사이클 간격
    hold_min: int = 120
    stop_pct: float = 5.0
    tp_pct: float = 0.0         # 익절 상한(%). 0 이면 끔
    mirror: bool = False        # 방향 반전 대조군 — 롱·숏을 바꿔 뽑는다
    slots: int = 2
    fee_rt: float = 0.072
    min_live: float = 5.0
    z_lo: float = -1.25
    z_hi: float = -0.25
    acc_max: float = 0.5
    seed: int = 20260907

    def dump(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


def simulate(cl, zv, za, live, r: Run, cooldown_min: int,
             placebo_rng: np.random.Generator | None = None):
    """5분 격자 장부 시늉. (거래목록, 손절수) 를 돌려준다.

    거래 = (숏여부, 순수익%, 손절여부).

    ⚠ 냉각과 위약은 **같은 자리**에서 걸린다 — 한쪽만 다른 경로를 타면
      비교가 아니라 다른 실험이 된다.
    """
    n_min, n_sym = cl.shape
    step = r.step_min
    steps = range(0, n_min - r.hold_min - 1, step)
    half = r.slots // 2
    # 보유: 종목 → (진입분, 진입가, 숏여부)
    book: dict[int, tuple[int, float, bool]] = {}
    block: dict[int, int] = {}            # 종목 → 이 분까지 금지
    trades, n_stop, n_tp = [], 0, 0

    for t in steps:
        # ── 청산 (손절 우선, 그다음 만기)
        for j in list(book):
            t0, px0, sh = book[j]
            seg = cl[t0 + 1:t + 1, j]
            seg = seg[np.isfinite(seg)]
            # ⚠ 손절과 익절 중 **먼저 닿은 쪽**으로 나간다. 분 단위로 순서를
            #   알 수 있으니 뭉뚱그리지 않는다. 같은 분에 둘 다면 손절 —
            #   분 안의 순서는 모르므로 보수적으로 본다(동결 규약).
            i_sl = i_tp = -1
            if seg.size:
                if r.stop_pct > 0:
                    m = (seg >= px0 * (1 + r.stop_pct / 100)) if sh \
                        else (seg <= px0 * (1 - r.stop_pct / 100))
                    if m.any():
                        i_sl = int(np.argmax(m))
                if r.tp_pct > 0:
                    m = (seg <= px0 * (1 - r.tp_pct / 100)) if sh \
                        else (seg >= px0 * (1 + r.tp_pct / 100))
                    if m.any():
                        i_tp = int(np.argmax(m))
            hit = i_sl >= 0 and (i_tp < 0 or i_sl <= i_tp)
            took = (not hit) and i_tp >= 0
            expired = (t - t0) >= r.hold_min
            if not (hit or took or expired):
                continue
            if hit:
                ret = -r.stop_pct
                n_stop += 1
            elif took:
                ret = r.tp_pct
                n_tp += 1
            else:
                px = cl[t, j]
                if not np.isfinite(px):
                    continue                      # 시세를 모르면 안 닫는다
                ret = 100.0 * (px / px0 - 1.0)
                if sh:
                    ret = -ret
            trades.append((sh, ret - r.fee_rt, hit))
            del book[j]
            if hit and cooldown_min > 0:
                if placebo_rng is None:
                    block[j] = t + cooldown_min   # 손절당한 그 종목
                else:
                    # 위약 — **다른** 종목을 같은 기간 막는다
                    cand = np.flatnonzero(np.isfinite(cl[t]))
                    cand = cand[(cand != j)]
                    if cand.size:
                        block[int(placebo_rng.choice(cand))] = t + cooldown_min

        block = {k: v for k, v in block.items() if v > t}

        # ── 빈 슬롯 채움 — 실거래와 같은 순서
        nl = sum(1 for v in book.values() if not v[2])
        ns = len(book) - nl
        if nl >= half and ns >= half:
            continue
        z, a_, lv, px = zv[t], za[t], live[t], cl[t]
        ok = (np.isfinite(z) & np.isfinite(a_) & np.isfinite(lv)
              & np.isfinite(px) & (lv >= r.min_live))
        for k in list(book) + list(block):
            ok[k] = False
        L = ok & (z >= r.z_lo) & (z <= r.z_hi) & (a_ < r.acc_max)
        S = ok & (z >= -r.z_hi) & (z <= -r.z_lo) & (a_ > -r.acc_max)
        if r.mirror:
            L, S = S, L          # 대조군 — 뽑는 방향만 뒤집는다
        for mask, sh, need in ((L, False, half - nl), (S, True, half - ns)):
            if need <= 0:
                continue
            i = np.flatnonzero(mask)
            if i.size < need:
                continue
            o = i[np.argsort(z[i] if not sh else -z[i])][:need]
            for j in o:
                book[int(j)] = (t, float(px[j]), sh)
    return trades, n_stop, n_tp


def report(tag: str, trades, n_stop: int, r: Run, n_tp: int = 0) -> dict:
    if not trades:
        return {"tag": tag, "n": 0}
    net = np.array([x[1] for x in trades])
    e = np.cumprod(1 + net / r.slots / 100)
    mdd = 100 * (1 - (e / np.maximum.accumulate(e)).min())
    return {"tag": tag, "n": len(net), "mean": float(net.mean()),
            "win": float(100 * (net > 0).mean()), "worst": float(net.min()),
            "stops": n_stop, "tps": n_tp, "compound": float(100 * (e[-1] - 1)),
            "mdd": float(mdd),
            "t": float(net.mean() / (net.std(ddof=1) / np.sqrt(len(net))))}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cooldowns", default="0,5,15,30,60,120")
    p.add_argument("--stop-pct", type=float, default=5.0)
    p.add_argument("--slots", type=int, default=2)
    p.add_argument("--hold", type=int, default=120)
    p.add_argument("--placebo-reps", type=int, default=5)
    p.add_argument("--tps", default="",
                   help="익절 격자(%%). 주면 익절 검정으로 돈다(냉각은 0 고정)")
    p.add_argument("--mirror", action="store_true",
                   help="방향 반전 대조군을 같이 낸다 — 규칙이 벌면 방향을 "
                        "뒤집어도 버는지 본다(교훈#91)")
    p.add_argument("--smoke", type=int, default=0,
                   help="종목 수를 이만큼으로 줄여 예비비행")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    r = Run(stop_pct=a.stop_pct, slots=a.slots, hold_min=a.hold)
    cds = [int(x) for x in a.cooldowns.split(",")]
    log.info("인자 도달 — 냉각 %s · 손절 %.1f%% · 슬롯 %d · 보유 %d분 · 위약 %d회",
             cds, r.stop_pct, r.slots, r.hold_min, a.placebo_reps)
    log.info("설정 전문 %s", r.dump())

    t0 = time.time()
    c = Cfg(slots=a.slots, hold=a.hold)
    files = sorted(MICRO.glob("*.parquet"))
    if a.smoke:
        files = files[:a.smoke]
    F, names = {}, []
    for f in files:
        try:
            x = feats(f, c)
        except Exception as e:                                # noqa: BLE001
            log.warning("%s %s", f.stem, e)
            x = None
        if x is not None:
            F[f.stem] = x
            names.append(f.stem)
    if not names:
        raise SystemExit("읽힌 종목이 0 — 경로를 확인하라")
    lo = min(x.index.min() for x in F.values())
    hi = max(x.index.max() for x in F.values())
    grid = pd.date_range(lo, hi, freq="1min", tz="UTC")
    log.info("종목 %d · 1분 격자 %d (%s ~ %s) · 적재 %.1f분",
             len(names), len(grid), lo.date(), hi.date(), (time.time() - t0) / 60)

    # ⚠ 경로 판정에 종가가 필요하다. feats 는 zv/za/live 만 주므로 종가를
    #   원본에서 다시 읽는다 — 같은 격자에 맞춘다.
    cl = np.full((len(grid), len(names)), np.nan, np.float32)
    zv = np.full_like(cl, np.nan)
    za = np.full_like(cl, np.nan)
    lv = np.full_like(cl, np.nan)
    for j, s in enumerate(names):
        x = F[s].reindex(grid)
        zv[:, j] = x["zv"].to_numpy(np.float32)
        za[:, j] = x["za"].to_numpy(np.float32)
        lv[:, j] = x["live"].to_numpy(np.float32)
        d = pd.read_parquet(MICRO / f"{s}.parquet").sort_values("ts")
        cl[:, j] = (d.set_index(pd.DatetimeIndex(d.ts)).cl
                    .reindex(grid).ffill().to_numpy(np.float32))
    del F
    log.info("적재 완료 %.1f분 · 배열 %.0f MB",
             (time.time() - t0) / 60, 4 * cl.size * 4 / 1e6)

    rows, plc = [], {}
    if a.tps:
        # ── 익절 격자. 방향 반전 대조군을 **같이** 낸다 —
        #    규칙이 벌면 방향을 뒤집어도 벌 수 있다(교훈#91).
        for tp in [float(x) for x in a.tps.split(",")]:
            for mir in ((False, True) if a.mirror else (False,)):
                rr = Run(stop_pct=a.stop_pct, slots=a.slots, hold_min=a.hold,
                         tp_pct=tp, mirror=mir)
                tr, ns, nt = simulate(cl, zv, za, lv, rr, 0)
                lab = ("익절 없음" if tp <= 0 else f"익절 {tp:.0f}%") + \
                      (" · 거울" if mir else "")
                rows.append(report(lab, tr, ns, rr, nt))
                log.info("%s — 거래 %d · %.1f분", lab, len(tr),
                         (time.time() - t0) / 60)
    else:
        for cd in cds:
            tr, ns, nt = simulate(cl, zv, za, lv, r, cd)
            rows.append(report(f"냉각 {cd}분", tr, ns, r, nt))
            log.info("냉각 %d분 — 거래 %d · %.1f분", cd, len(tr),
                     (time.time() - t0) / 60)
            if cd > 0 and a.placebo_reps > 0:
                got = []
                for k in range(a.placebo_reps):
                    g = np.random.default_rng(r.seed + 1000 * cd + k)
                    t_, s_, nt_ = simulate(cl, zv, za, lv, r, cd, placebo_rng=g)
                    got.append(report(f"위약 {cd}분 #{k}", t_, s_, r, nt_))
                plc[cd] = got

    title = "익절 상한 검정" if a.tps else "손절 후 재진입 금지"
    print(f"\n■ {title} — 종목 {len(names)} · "
          f"{lo.date()}~{hi.date()} · 손절 {r.stop_pct:.0f}% · 슬롯 {r.slots} · "
          f"보유 {r.hold_min}분")
    print(f"  {'설정':>14}{'거래':>8}{'거래당%':>10}{'t':>7}{'승률':>7}"
          f"{'손절':>7}{'익절':>7}{'복리%':>10}{'최대낙폭%':>11}")
    for x in rows:
        if not x["n"]:
            continue
        print(f"  {x['tag']:>14}{x['n']:>8,}{x['mean']:>+10.4f}{x['t']:>+7.2f}"
              f"{x['win']:>6.0f}%{x['stops']:>7,}{x.get('tps', 0):>7,}"
              f"{x['compound']:>+10.2f}{x['mdd']:>11.2f}")
        if a.tps:
            continue
        for y in plc.get(int(x["tag"].split()[1].rstrip("분")), []):
            if y["n"]:
                print(f"    └ {y['tag']:>10}{y['n']:>8,}{y['mean']:>+10.4f}"
                      f"{y['t']:>+7.2f}{y['win']:>6.0f}%{y['stops']:>7,}"
                      f"{y['compound']:>+10.2f}{y['mdd']:>11.2f}")
    if a.tps:
        print("\n  ※ 거울은 뽑는 **방향만** 뒤집은 대조군이다. 익절이 양쪽에서")
        print("     같은 방향으로 움직이면 엣지가 아니라 규칙 효과다(교훈#91).")
    else:
        print("\n  ※ 위약은 **다른 종목**을 같은 기간 막는다. 실측이 위약을 못 이기면")
        print("     '재진입 금지'가 아니라 '덜 거래하기'가 번 것이다(교훈#91).")
    log.info("완료 %.1f분", (time.time() - t0) / 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
