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
SLOTS, HOLD, STEP = 10, 120, 5
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


def cycle(syms: list[str], st: State, ledger: Path, now: datetime) -> dict:
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
        if (sig["live"] >= MIN_LIVE_TR and Z_LO <= sig["z_vel"] <= Z_HI
                and sig["z_acc"] < ACC_MAX):
            cands.append({"symbol": s, **sig})

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
            net = ret - FEE_PCT
            st.equity += p["stake"] * net / 100.0
            st.n_trades += 1
            row = {**p, "exit_px": px, "ret_pct": ret, "net_pct": net,
                   "closed_ts": str(now), "equity_after": st.equity}
            closed.append(row)
            pd.DataFrame([row]).to_csv(
                ledger, mode="a", header=not ledger.exists(), index=False)
        else:
            keep.append(p)
    st.positions = keep

    # ── 빈 슬롯 채움 — z_vel 낮은 순, 중복 금지
    held = {p["symbol"] for p in st.positions}
    free = SLOTS - len(st.positions)
    opened = []
    if free > 0 and cands:
        c = sorted([x for x in cands if x["symbol"] not in held],
                   key=lambda x: x["z_vel"])[:free]
        stake = st.equity / SLOTS
        for x in c:
            p = {"symbol": x["symbol"], "entry_ts": str(now),
                 "entry_px": x["px"], "z_vel": x["z_vel"], "z_acc": x["z_acc"],
                 "exit_ts": str(now + timedelta(minutes=HOLD)), "stake": stake}
            st.positions.append(p)
            opened.append(p)
    return {"cands": len(cands), "opened": len(opened), "closed": len(closed),
            "held": len(st.positions)}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--universe", default="configs/rsi_live_universe.txt")
    p.add_argument("--once", action="store_true")
    p.add_argument("--state", default="")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    signal.signal(signal.SIGTERM, _sig)
    signal.signal(signal.SIGINT, _sig)

    syms = [s.strip().upper() for s in
            (ROOT / a.universe).read_text().split() if s.strip()]
    OUT.mkdir(parents=True, exist_ok=True)
    state_p = Path(a.state) if a.state else OUT / "state.json"
    ledger = OUT / "trades.csv"
    st = load_state(state_p)
    log.info("운동학 페이퍼 — %d종목 · 슬롯 %d · 보유 %d분 · 밴드 %.2f~%.2f "
             "· z_acc<%.1f", len(syms), SLOTS, HOLD, Z_LO, Z_HI, ACC_MAX)
    log.info("상태 — 자본 %.4f · 보유 %d · 누적거래 %d",
             st.equity, len(st.positions), st.n_trades)

    while not _stop:
        now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        now -= timedelta(minutes=now.minute % STEP)
        t0 = time.time()
        try:
            r = cycle(syms, st, ledger, now)
            save_state(state_p, st)
            log.info("%s · 후보 %d · 진입 %d · 청산 %d · 보유 %d/%d · "
                     "자본 %.4f(%+.2f%%) · 누적 %d · %.0f초",
                     now.strftime("%m-%d %H:%M"), r["cands"], r["opened"],
                     r["closed"], r["held"], SLOTS, st.equity,
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
