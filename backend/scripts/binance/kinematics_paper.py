"""위약 승률 운동학 — 전진 페이퍼 (System-2 시뮬레이션).

## 무엇인가

동결 문서(`runs/research_track/tick_placebo_kinematics_frozen.md` 개정 2)의
규칙을 **실시간으로** 돌려 전진 자료를 만든다. 실계좌를 건드리지 않는다.

연구 하네스와 **완전히 같은 경로**를 쓴다 — 같은 틱 파일, 같은 1분봉, 같은
신호식, 같은 체결 규약(봉 종가). 경로가 갈리면 페이퍼가 연구를 검증하지 못한다.

## 규칙 (동결 · 바꾸지 마라)

    지평 60분 · 창 360분 · 간격 180분 · N_eff = 창/지평 = 6
    밴드  -1.25 <= z_vel <= -0.25      상한이 핵심 — 초판은 상한이 없어 -18.8%
    배제  z_acc >= +0.5
    생존  직전 60분 분당 체결 중앙 >= 5
    슬롯 10 · 자본 분할 · 같은 종목 중복 금지
    보유 120분 · 익절·손절 없음 · 롱만
    앵커 벽시계 5분 격자

## 상태를 파일에 남긴다

프로세스가 죽어도 열린 포지션을 잃지 않는다. 재기동 시 상태를 읽고 이어간다.
⚠ 상태를 메모리에만 두면 PM2 재시작 한 번에 원장이 끊긴다.

## 페이퍼가 답하는 것 / 못 하는 것

  답한다   동결 규칙이 **앞으로도** 같은 부호를 내는가
  못 한다  체결 현실(지정가 대기·슬리피지·수수료 등급). 봉 종가 체결 가정이다

사용:
  python3 -m scripts.binance.kinematics_paper --once      # 한 사이클만
  python3 -m scripts.binance.kinematics_paper             # 상주
"""
from __future__ import annotations

import argparse
import json
import logging
import signal
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
TICKS = ROOT / "runs" / "ticks"
OUT = ROOT / "runs" / "kinematics_paper"
log = logging.getLogger("kine_paper")

# ── 동결 파라미터 — 이 블록을 고치면 전진 검정이 아니다
WIN_H, WINDOW, DELTA = 60, 360, 180
Z_LO, Z_HI, ACC_MAX = -1.25, -0.25, 0.5
SLOTS_DEFAULT, HOLD, STEP = 10, 120, 5
# 숏은 밴드가 거울이다. 집단 검정(최근 24h)에서 숏 쪽 초과가 오히려 컸다 —
#   롱 밴드(-1.25~-0.25) 가중 +0.192%p · 숏 밴드(+0.25~+1.25) **+0.257%p**
# ⚠ 그래도 롱과 손익 구조가 다르다: ① 숏 위약이 음수(-0.245% @120분)라 절대
#   손익이 0.42%p 불리 ② 위쪽 꼬리가 무한(오늘 페이퍼 최고 +7.41%) ③ 펀딩비.
#   그래서 펀딩을 원장에 **기록**한다 — 추측으로 두면 영영 모른다.
FUNDING_URL = "https://fapi.binance.com/fapi/v1/premiumIndex"
FUNDING_HOURS = (0, 8, 16)          # UTC 정산 시각
# ⚠ 슬롯 수만 인자로 연다. 나머지 신호·밴드·보유는 동결분이라 손대지 않는다.
#   슬롯마다 상태·원장을 **따로** 둔다 — 한 디렉터리를 공유하면 서로 덮어쓴다.
SLOTS = SLOTS_DEFAULT


def funding_rates() -> dict:
    """전 종목 최근 펀딩률 — 한 번의 호출로 받는다. 실패하면 빈 표."""
    import json as _j
    import urllib.request
    try:
        with urllib.request.urlopen(FUNDING_URL, timeout=15) as r:
            return {x["symbol"]: float(x.get("lastFundingRate") or 0.0)
                    for x in _j.load(r)}
    except Exception as e:                                      # noqa: BLE001
        log.warning("펀딩률 조회 실패(0 으로 둔다): %s", str(e)[:80])
        return {}


def funding_crossings(a: datetime, b: datetime) -> int:
    """보유 구간이 정산 시각을 몇 번 지나나."""
    n, t = 0, a
    while t < b:
        t += timedelta(hours=1)
        if t.hour in FUNDING_HOURS and t.minute == 0:
            if a < t <= b:
                n += 1
    return n
MIN_LIVE_TR, FEE_PCT = 5.0, 0.036

_stop = False


def _sig(*_):
    global _stop
    _stop = True
    log.info("정지 신호 — 상태를 저장하고 끝낸다")


@dataclass
class State:
    equity: float = 1.0
    positions: list = None          # [{symbol, entry_ts, entry_px, exit_ts, stake}]
    n_trades: int = 0

    def __post_init__(self):
        if self.positions is None:
            self.positions = []


def load_state(p: Path) -> State:
    if not p.exists():
        return State()
    d = json.loads(p.read_text())
    return State(equity=d["equity"], positions=d["positions"],
                 n_trades=d.get("n_trades", 0))


def save_state(p: Path, s: State) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(s), ensure_ascii=False, indent=1))
    tmp.replace(p)                  # 원자적 교체 — 쓰다 죽어도 원장이 안 깨진다


def bars(sym: str, since_ms: int) -> pd.DataFrame | None:
    """최근 구간의 1분봉. 필요한 만큼만 읽는다."""
    d = TICKS / sym
    fs = sorted(d.glob("*.parquet"))[-2:]
    if not fs:
        return None
    try:
        t = pd.concat([pd.read_parquet(f, columns=["ts_ms", "price", "qty"])
                       for f in fs], ignore_index=True)
    except Exception:                                          # noqa: BLE001
        return None
    t = t[(t.ts_ms >= since_ms) & (t.price > 0) & (t.qty > 0)]
    if len(t) < 500:
        return None
    g = t.sort_values("ts_ms").groupby(t.ts_ms // 60_000)
    b = pd.DataFrame({"cl": g.price.last(), "ntr": g.price.size()})
    b.index = pd.to_datetime(b.index * 60_000, unit="ms", utc=True)
    b = b.reindex(pd.date_range(b.index.min(), b.index.max(), freq="1min",
                                tz="UTC"))
    b["cl"] = b.cl.ffill(); b["ntr"] = b.ntr.fillna(0.0)
    return b


def signal_now(b: pd.DataFrame) -> dict | None:
    """지금 시점의 z_vel · z_acc · 생존 · 현재가. **후행만** 쓴다."""
    need = WIN_H + WINDOW + 2 * DELTA + 10
    if len(b) < need:
        return None
    cl = b.cl
    n = len(cl)
    fw = np.full(n, np.nan)
    c = cl.to_numpy(float)
    fw[:n - WIN_H] = c[WIN_H:] / c[:n - WIN_H] - 1.0
    win = pd.Series(np.where(np.isfinite(fw), (fw > 0).astype(float), np.nan))
    # ⚠ shift(WIN_H) — 승부가 끝난 앵커만 쓴다. 빼먹으면 미래참조다.
    rate = win.rolling(WINDOW, min_periods=WINDOW // 2).mean().shift(WIN_H)
    vel = rate - rate.shift(DELTA)
    acc = vel - vel.shift(DELTA)
    neff = max(WINDOW / WIN_H, 1.0)
    p = rate.clip(0.01, 0.99)
    se = np.sqrt(p * (1 - p) / neff)
    zv = (vel / (se * np.sqrt(2))).iloc[-1]
    za = (acc / (se * 2.0)).iloc[-1]
    live = b.ntr.rolling(60).median().shift(1).iloc[-1]
    if not (np.isfinite(zv) and np.isfinite(za) and np.isfinite(live)):
        return None
    return {"z_vel": float(zv), "z_acc": float(za), "live": float(live),
            "px": float(c[-1]), "ts": b.index[-1]}


def cycle(syms: list[str], st: State, ledger: Path, now: datetime,
          slots: int, short: bool, fr: dict, both: bool = False) -> dict:
    since = int((now - timedelta(minutes=WIN_H + WINDOW + 2 * DELTA + 60))
                .timestamp() * 1000)
    px_cache: dict[str, float] = {}
    cands = []
    for s in syms:
        b = bars(s, since)
        if b is None:
            continue
        sig = signal_now(b)
        if sig is None:
            continue
        px_cache[s] = sig["px"]
        # 숏은 밴드·가속 조건이 거울이다
        ok_l = (Z_LO <= sig["z_vel"] <= Z_HI and sig["z_acc"] < ACC_MAX)
        ok_s = (-Z_HI <= sig["z_vel"] <= -Z_LO and sig["z_acc"] > -ACC_MAX)
        if sig["live"] < MIN_LIVE_TR:
            continue
        if both:
            if ok_l:
                cands.append({"symbol": s, "side_short": False, **sig})
            elif ok_s:
                cands.append({"symbol": s, "side_short": True, **sig})
        elif (ok_s if short else ok_l):
            cands.append({"symbol": s, "side_short": short, **sig})

    # ── 만기 청산
    closed = []
    keep = []
    for p in st.positions:
        if pd.Timestamp(p["exit_ts"]) <= pd.Timestamp(now):
            px = px_cache.get(p["symbol"])
            if px is None:
                keep.append(p)                 # 시세 없으면 다음 사이클로 미룬다
                continue
            ret = 100.0 * (px / p["entry_px"] - 1.0)
            if p.get("short"):
                ret = -ret
            # 펀딩 — 양수 펀딩률이면 롱이 내고 숏이 받는다
            fnd = (100.0 * p.get("fr", 0.0)
                   * funding_crossings(pd.Timestamp(p["entry_ts"]).to_pydatetime(),
                                       now)
                   * (1.0 if p.get("short") else -1.0))
            net = ret - FEE_PCT + fnd
            st.equity += p["stake"] * net / 100.0
            st.n_trades += 1
            row = {**p, "exit_px": px, "ret_pct": ret, "funding_pct": fnd,
                   "net_pct": net, "closed_ts": str(now),
                   "equity_after": st.equity}
            closed.append(row)
            # ⚠ 덧붙이기 원장에 **필드를 늘리면 깨진다**. 펀딩 컬럼을 추가하며
            #   12칸 파일에 13칸 행을 붙여 통째로 못 읽게 됐다(2026-08-29).
            #   헤더가 다르면 전체를 읽어 합집합 스키마로 다시 쓴다.
            nr = pd.DataFrame([row])
            if ledger.exists():
                try:
                    old_df = pd.read_csv(ledger)
                except Exception:                              # noqa: BLE001
                    old_df = pd.read_csv(ledger, on_bad_lines="skip")
                if list(old_df.columns) != list(nr.columns):
                    pd.concat([old_df, nr], ignore_index=True).to_csv(
                        ledger, index=False)
                else:
                    nr.to_csv(ledger, mode="a", header=False, index=False)
            else:
                nr.to_csv(ledger, index=False)
        else:
            keep.append(p)
    st.positions = keep

    # ── 빈 슬롯 채움 — z_vel 낮은 순, 중복 금지
    held = {p["symbol"] for p in st.positions}
    free = slots - len(st.positions)
    opened = []
    if free > 0 and cands:
        avail = [x for x in cands if x["symbol"] not in held]
        if both:
            # ⚠ 롱·숏 슬롯을 **따로** 채운다. 한쪽만 채우면 시장 중립이 깨진다.
            half = slots // 2
            nl = sum(1 for p in st.positions if not p.get("short"))
            ns = len(st.positions) - nl
            L = sorted([x for x in avail if not x["side_short"]],
                       key=lambda x: x["z_vel"])[:max(half - nl, 0)]
            S2 = sorted([x for x in avail if x["side_short"]],
                        key=lambda x: -x["z_vel"])[:max(half - ns, 0)]
            c = L + S2
        else:
            # 롱은 z_vel 낮은 순, 숏은 **높은 순** — 밴드 끝에서 먼 쪽부터
            c = sorted(avail,
                       key=lambda x: -x["z_vel"] if short else x["z_vel"])[:free]
        stake = st.equity / slots
        for x in c:
            p = {"symbol": x["symbol"], "entry_ts": str(now),
                 "entry_px": x["px"], "z_vel": x["z_vel"], "z_acc": x["z_acc"],
                 "exit_ts": str(now + timedelta(minutes=HOLD)), "stake": stake,
                 "short": bool(x.get("side_short", short)),
                 "fr": float(fr.get(x["symbol"], 0.0))}
            st.positions.append(p)
            opened.append(p)
    return {"cands": len(cands), "opened": len(opened), "closed": len(closed),
            "held": len(st.positions)}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--universe", default="configs/rsi_live_universe.txt")
    p.add_argument("--once", action="store_true")
    p.add_argument("--slots", type=int, default=SLOTS_DEFAULT)
    p.add_argument("--short", action="store_true",
                   help="숏 방향. 밴드·가속·선별이 전부 거울이 된다")
    p.add_argument("--both", action="store_true",
                   help="롱·숏 **동시 보유**. 슬롯을 반씩 나눠 시장 노출을 상쇄한다")
    p.add_argument("--dir", default="",
                   help="상태·원장 디렉터리. 비우면 runs/kinematics_paper/s{슬롯}")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    signal.signal(signal.SIGTERM, _sig)
    signal.signal(signal.SIGINT, _sig)

    syms = [s.strip().upper() for s in
            (ROOT / a.universe).read_text().split() if s.strip()]
    tag = f"s{a.slots}" + ("both" if a.both else "short" if a.short else "")
    d = Path(a.dir) if a.dir else OUT / tag
    d.mkdir(parents=True, exist_ok=True)
    state_p, ledger = d / "state.json", d / "trades.csv"
    st = load_state(state_p)
    side = "롱숏동시" if a.both else ("숏" if a.short else "롱")
    log.info("운동학 페이퍼 — %d종목 · %s · 슬롯 %d(%s) · 보유 %d분 · 경로 %s",
             len(syms), side, a.slots,
             f"롱{a.slots//2}+숏{a.slots//2}" if a.both else side, HOLD, d)
    log.info("상태 — 자본 %.4f · 보유 %d · 누적거래 %d",
             st.equity, len(st.positions), st.n_trades)

    while not _stop:
        now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        now -= timedelta(minutes=now.minute % STEP)
        t0 = time.time()
        try:
            fr = funding_rates() if a.short or True else {}
            r = cycle(syms, st, ledger, now, a.slots, a.short, fr,
                      a.both)
            save_state(state_p, st)
            log.info("%s · 후보 %d · 진입 %d · 청산 %d · 보유 %d/%d · "
                     "자본 %.4f(%+.2f%%) · 누적 %d · %.0f초",
                     now.strftime("%m-%d %H:%M"), r["cands"], r["opened"],
                     r["closed"], r["held"], a.slots, st.equity,
                     (st.equity - 1) * 100, st.n_trades, time.time() - t0)
        except Exception as e:                                  # noqa: BLE001
            log.exception("사이클 실패: %s", e)
        if a.once:
            break
        # 다음 5분 격자까지 대기
        nxt = now + timedelta(minutes=STEP)
        while not _stop and datetime.now(timezone.utc) < nxt:
            time.sleep(2)
    save_state(state_p, st)
    log.info("종료 — 자본 %.4f · 보유 %d · 누적거래 %d",
             st.equity, len(st.positions), st.n_trades)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
