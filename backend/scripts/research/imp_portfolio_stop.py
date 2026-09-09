"""버팀저울 보완책 — **계좌 단위 방어선** 검정 (2026-09-09).

## 왜 개별 손절이 아니라 계좌 단위인가

§29·§30 실측: 이 갈래는 **되돌아오는 것이 수익원**이다(역행 0~10% 구간 65건이
평균 +4.1%). 개별 손절은 되돌아오기 전에 자른다 — 어느 문턱을 골라도 그 긴장이
남고, 92건에서 **모든 문턱이 무손절보다 나빴다**(30% 문턱 자본 −20.98%p).

막고 싶은 것은 개별 거래가 아니라 **계좌가 반토막 나는 것**이다. 그러면
방어선도 계좌 단위여야 한다:

    3자리 미실현 합계가 자본의 −X% 를 넘으면 **전량 청산**.

개별 거래는 끝까지 버티게 두되(AKE 는 역행 109% 뒤 +37.30% 로 살아 돌아왔다),
세 자리가 동시에 무너지는 파국만 막는다.

## 기질

`runs/ticks` 만 쓴다. REST 0회 (교훈#111).

## 한계 (정직하게)

1. 방어선이 발동해 자리가 비면 다음 사이클에 **새 진입이 들어온다.** 원장의
   진입 시각은 고정이므로 그 회전 이득은 안 센다 — 낮은 X 가 불리하게 잡힌다.
1-b. ⚠ **슬롯 상한을 반드시 지켜야 한다.** 원장의 `exit_ts` 는 *예정 만기*라
   실제로 일찍 손절된 거래도 무손절 세계에서는 만기까지 산다. 상한을 안 걸면
   같은 종목이 3~4번 겹쳐 열려(2026-09-09 실측 `4USDT` 3다리 · `NOMUSDT` 4다리)
   미실현 합계가 부풀고 방어선이 헛발동한다. **첫 격자가 그래서 무효였다.**
2. 발동 뒤 냉각을 두지 않는다. 실제로는 필요할 수 있다.
3. 자본은 단순 합산(합/슬롯)이다. 복리를 쓰면 숫자가 달라진다.
"""
from __future__ import annotations

import argparse
import logging
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
log = logging.getLogger("pfstop")
KST = "Asia/Seoul"


@dataclass
class Cfg:
    ledger: str = "runs/kinematics_paper/s3short_imp/trades.csv"
    ticks: str = "runs/ticks"
    fee_rt: float = 0.072
    slots: int = 3
    # 계좌 미실현 합계(자본 %)가 이 값 이하로 내려가면 전량 청산. 0 이면 끔.
    lines: tuple = (0.0, 5.0, 8.0, 10.0, 12.0, 15.0, 20.0, 25.0, 30.0)
    # 비교용 개별 손절(자본 아닌 **거래** %). 0 이면 끔.
    leg_stops: tuple = (0.0, 5.0, 30.0)


def minute_px(sym: str, a: pd.Timestamp, b: pd.Timestamp,
              ticks: Path) -> pd.Series | None:
    """[a,b] 구간의 **1분 종가**. 없으면 None."""
    days = pd.date_range(a.tz_convert("UTC").normalize() - pd.Timedelta(days=1),
                         b.tz_convert("UTC").normalize(), freq="D")
    out = []
    for d in days:
        f = ticks / sym / f"{d:%Y-%m-%d}.parquet"
        if f.exists():
            try:
                out.append(pd.read_parquet(f, columns=["ts_ms", "price"]))
            except Exception:                                   # noqa: BLE001
                pass
    if not out:
        return None
    x = pd.concat(out, ignore_index=True)
    t = pd.to_datetime(x.ts_ms, unit="ms", utc=True)
    m = (t >= a) & (t <= b)
    if m.sum() < 50:
        return None
    s = pd.Series(x.loc[m, "price"].to_numpy(float), index=t[m])
    return s.resample("1min").last().ffill()


def simulate(trades: list, line: float, leg_stop: float, c: Cfg) -> dict:
    """계좌 방어선 `line`(자본 %) + 개별 손절 `leg_stop`(거래 %) 동시 적용."""
    grid = sorted({t for tr in trades for t in (tr["idx"][0], tr["idx"][-1])})
    tmin = min(tr["idx"][0] for tr in trades)
    tmax = max(tr["idx"][-1] for tr in trades)
    minutes = pd.date_range(tmin, tmax, freq="1min")
    open_, done, realized = [], [], 0.0
    nxt = 0
    order = sorted(trades, key=lambda z: z["entry"])
    n_line = n_leg = n_drop = 0
    for t in minutes:
        while nxt < len(order) and order[nxt]["entry"] <= t:
            # ⚠ 슬롯 상한. 자리가 없으면 그 진입은 **일어나지 않는다.**
            if len(open_) >= c.slots:
                n_drop += 1
            else:
                open_.append(dict(order[nxt], live=True))
            nxt += 1
        if not open_:
            continue
        # 각 다리의 현재 수익(%)
        for p in open_:
            px = p["px"].get(t, np.nan)
            if not np.isfinite(px):
                px = p["last_px"]
            p["last_px"] = px
            e = p["entry_px"]
            p["ret"] = (100 * (e - px) / e) if p["short"] else (100 * (px - e) / e)
        # ① 개별 손절
        if leg_stop > 0:
            for p in list(open_):
                if p["ret"] <= -leg_stop:
                    realized += -leg_stop - c.fee_rt
                    done.append((p["sym"], -leg_stop - c.fee_rt, "leg"))
                    open_.remove(p)
                    n_leg += 1
        if not open_:
            continue
        # ② 계좌 방어선 — 미실현 합계를 **자본 %** 로 환산
        unreal = sum(p["ret"] for p in open_) / c.slots
        if line > 0 and unreal <= -line:
            for p in open_:
                realized += p["ret"] - c.fee_rt
                done.append((p["sym"], p["ret"] - c.fee_rt, "line"))
            n_line += len(open_)
            open_ = []
            continue
        # ③ 만기
        for p in list(open_):
            if t >= p["exit"]:
                realized += p["ret"] - c.fee_rt
                done.append((p["sym"], p["ret"] - c.fee_rt, "exp"))
                open_.remove(p)
    for p in open_:
        realized += p["ret"] - c.fee_rt
        done.append((p["sym"], p["ret"] - c.fee_rt, "eod"))
    r = np.array([x[1] for x in done])
    return {"line": line, "leg": leg_stop, "n": len(done), "버림": n_drop,
            "합%": r.sum(),
            "자본%": r.sum() / c.slots, "평균%": r.mean(),
            "중앙%": float(np.median(r)), "승률": 100 * (r > 0).mean(),
            "최악%": r.min(), "방어선발동": n_line, "개별손절": n_leg}


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    a = ap.parse_args()
    c = Cfg()
    if a.smoke:
        c = Cfg(lines=(0.0, 10.0), leg_stops=(0.0,))
    log.info("설정 — 방어선 %s · 개별손절 %s · 슬롯 %d · 통행료 %.3f%%",
             c.lines, c.leg_stops, c.slots, c.fee_rt)

    d = pd.read_csv(ROOT / c.ledger)
    d["entry"] = pd.to_datetime(d.entry_ts, utc=True)
    d["exit"] = pd.to_datetime(d.exit_ts, utc=True)
    if a.smoke:
        d = d.head(12)
    trades = []
    for _, r in d.iterrows():
        s = minute_px(r.symbol, r.entry, r.exit, ROOT / c.ticks)
        if s is None or len(s) < 10:
            continue
        trades.append({"sym": r.symbol, "entry": r.entry, "exit": r.exit,
                       "entry_px": float(r.entry_px), "short": bool(r["short"]),
                       "px": s, "idx": s.index, "last_px": float(r.entry_px)})
    log.info("경로 확보 %d/%d건", len(trades), len(d))

    rows = [simulate(trades, ln, lg, c) for lg in c.leg_stops for ln in c.lines]
    out = pd.DataFrame(rows)
    print(f"\n■ 계좌 방어선 격자 — {len(trades)}건 (틱 1분 경로)")
    print(f"{'개별손절':>8} {'방어선':>7} {'거래':>4} {'버림':>4} {'합%':>9} {'자본%':>8} "
          f"{'중앙%':>7} {'승률':>6} {'최악%':>8} {'선발동':>6} {'개별발동':>8}")
    for _, r in out.iterrows():
        print(f"{('없음' if r.leg==0 else f'{r.leg:g}%'):>8} "
              f"{('없음' if r.line==0 else f'{r.line:g}%'):>7} {int(r.n):>4} {int(r.버림):>4} "
              f"{r['합%']:>+9.2f} {r['자본%']:>+8.2f} {r['중앙%']:>+7.2f} "
              f"{r['승률']:>5.1f}% {r['최악%']:>+8.2f} {int(r.방어선발동):>6} "
              f"{int(r.개별손절):>8}")
    d0 = out[(out.leg == 0) & (out.line == 0)]["자본%"].iloc[0]
    print(f"\n  기준(둘 다 없음) 자본 {d0:+.2f}%")
    best = out.loc[out["자본%"].idxmax()]
    print(f"  최대 자본 = 개별 {best.leg:g}% · 방어선 {best.line:g}% → {best['자본%']:+.2f}%")
    print("  ⚠ 방어선이 발동해 자리가 비면 새 진입이 들어오는데 이 격자는 그 이득을"
          " 안 센다 — **낮은 X 가 실제보다 불리하게** 잡힌다.")


if __name__ == "__main__":
    main()
