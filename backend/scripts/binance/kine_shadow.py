"""속도저울 그림자 — **오프라인** 반사실 재구성기.

무엇을 재나
    "모든 주문이 신호가에 즉시 체결됐다면 장부가 어떻게 됐을까."
    실거래와의 차이가 곧 **체결 계층의 비용**이다 — 주문 거절, 지갑 조회
    실패, `-1021` 로 밀린 청산 때문에 슬롯이 막혀 진입이 통째로 사라진 것까지.

왜 프로세스가 아니라 스크립트인가
    민트의 5분 사이클은 24시간 p99 **255초**, 최대 543초다(300초 초과 5건).
    격자를 넘긴 사이클이 바로 2026-09-05 짝 어긋남의 원인이었다. 10번째
    스캐너를 붙이면 **재려는 대상을 키우면서 재게 된다.** 자료원은 실거래가
    이미 남기므로(`--emit-pool`), 읽어서 계산만 하면 된다.

경계 (START)
    후보 풀은 2026-09-07 부터 기록된다. 그 **이전 구간은 재구성하지 않고
    실거래를 그대로 쓴다** — 없는 자료를 지어내지 않는다. 그래서 그림자와
    실거래의 차이는 START 이후에만 생긴다.

⚠ 손절 판정의 자료원이 다르다. 실거래는 틱 봉의 고·저로 보고, 여기서는
  1분봉 고·저로 본다. 같은 구간이라도 완전히 같지는 않다 — 이 스크립트가
  실거래보다 손절을 덜/더 잡을 수 있다. 표에 `손절` 수를 나란히 찍어 두니
  크게 갈리면 그 줄부터 의심하라.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.binance.kinematics_paper import (FEE_PCT, HOLD,  # noqa: E402
                                              STOP_PCT, funding_crossings)

FAPI = "https://fapi.binance.com"


# ── 시세 ────────────────────────────────────────────────────
_KL: dict = {}


def klines_1m(symbol: str, start_ms: int, end_ms: int) -> pd.DataFrame | None:
    """[start, end) 구간의 1분봉. 실패하면 None — **0 으로 뭉개지 않는다.**"""
    key = (symbol, start_ms // 60_000, end_ms // 60_000)
    if key in _KL:
        return _KL[key]
    out = []
    cur = start_ms
    while cur < end_ms:
        q = urllib.parse.urlencode({"symbol": symbol, "interval": "1m",
                                    "startTime": cur, "endTime": end_ms,
                                    "limit": 1000})
        try:
            with urllib.request.urlopen(f"{FAPI}/fapi/v1/klines?{q}",
                                        timeout=20) as r:
                rows = json.load(r)
        except Exception as exc:                              # noqa: BLE001
            print(f"  ⚠ {symbol} 1분봉 조회 실패 — 모른다: {exc}")
            return None
        if not rows:
            break
        out += rows
        nxt = int(rows[-1][0]) + 60_000
        if nxt <= cur:
            break
        cur = nxt
        time.sleep(0.05)
    if not out:
        _KL[key] = None
        return None
    df = pd.DataFrame(out).iloc[:, :5]
    df.columns = ["ot", "open", "high", "low", "close"]
    for c in ("open", "high", "low", "close"):
        df[c] = df[c].astype(float)
    df["ot"] = df["ot"].astype("int64")
    df = df[(df.ot >= start_ms) & (df.ot < end_ms)]
    _KL[key] = df
    return df


# ── 자료 읽기 ───────────────────────────────────────────────
def read_cycles(d: Path) -> list[dict]:
    rows = []
    for f in sorted(d.glob("*/cycles.jsonl")):
        for ln in f.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(ln))
            except Exception:                                 # noqa: BLE001
                continue
    rows.sort(key=lambda r: r["cycle"])
    return rows


def read_live(d: Path) -> pd.DataFrame:
    f = d / "trades.csv"
    if not f.exists():
        raise SystemExit(f"실거래 원장이 없다 — {f}")
    t = pd.read_csv(f, parse_dates=["entry_ts", "exit_ts", "closed_ts"])
    return t.sort_values("closed_ts").reset_index(drop=True)


# ── 재구성 ──────────────────────────────────────────────────
def seed(live: pd.DataFrame, start, state_p: Path):
    """START 시점의 자본과 보유를 **실거래에서 그대로** 물려받는다.

    지나간 구간은 재구성하지 않는다 — 후보 풀이 없어서 못 하고, 지어내면
    그림자가 아니라 다른 전략이 된다. 그래서 START 이전 성적은 정의상 동일하다.
    """
    past = live[live.closed_ts <= start]
    eq = float(past.equity_after.iloc[-1]) if len(past) else 1.0
    # 보유 = 원장에서 START 를 걸치는 거래 + 아직 안 닫혀 원장에 없는 것
    book = []
    _end = live.closed_ts.fillna(live.exit_ts)      # 실제 청산이 우선
    for _, r in live[(live.entry_ts <= start) & (_end > start)].iterrows():
        book.append({"symbol": r.symbol, "entry_ts": r.entry_ts,
                     "entry_px": float(r.entry_px), "short": bool(r.short),
                     "exit_ts": r.exit_ts, "fr": float(r.fr),
                     "stake": float(r.stake)})
    known = {b["symbol"] for b in book}
    try:
        st = json.loads(state_p.read_text())
        for p in st.get("positions") or []:
            ts = pd.Timestamp(p["entry_ts"])
            if ts <= start and p["symbol"] not in known:
                book.append({"symbol": p["symbol"], "entry_ts": ts,
                             "entry_px": float(p["entry_px"]),
                             "short": bool(p.get("short")),
                             "exit_ts": pd.Timestamp(p["exit_ts"]),
                             "fr": float(p.get("fr", 0.0)),
                             "stake": float(p.get("stake", eq / 2))})
    except Exception:                                         # noqa: BLE001
        pass
    return eq, book, len(past)


def simulate(cycles: list[dict], eq: float, book: list, slots: int,
             hold: int, fee_pct: float) -> tuple[float, list]:
    """실거래 `cycle()` 의 청산·선별 규칙을 그대로 옮긴다.

    ⚠ 옮겨 적은 코드다. 원본이 바뀌면 여기도 바뀌어야 한다 — 자기검사
      `--verify` 가 '막히지 않은 사이클에서 실거래와 같은 종목을 골랐나'를
      확인하는 이유다.
    """
    half = slots // 2
    trades = []
    for row in cycles:
        now = pd.Timestamp(row["cycle"])
        keep = []
        for p in book:
            hit, px = False, None
            s_ms = int(p["entry_ts"].timestamp() * 1000)
            e_ms = int(min(now, p["exit_ts"]).timestamp() * 1000)
            df = klines_1m(p["symbol"], s_ms, e_ms + 60_000) if e_ms > s_ms else None
            if df is not None and len(df) and STOP_PCT > 0:
                if p["short"]:
                    hit = float(df.high.max()) >= p["entry_px"] * (1 + STOP_PCT / 100)
                else:
                    hit = float(df.low.min()) <= p["entry_px"] * (1 - STOP_PCT / 100)
            expired = p["exit_ts"] <= now
            if not (hit or expired):
                keep.append(p)
                continue
            if hit:
                ret = -STOP_PCT
                px = p["entry_px"] * ((1 + STOP_PCT / 100) if p["short"]
                                      else (1 - STOP_PCT / 100))
            else:
                if df is None or not len(df):
                    keep.append(p)          # 시세를 모르면 **닫지 않는다**
                    continue
                px = float(df.close.iloc[-1])
                ret = 100.0 * (px / p["entry_px"] - 1.0)
                if p["short"]:
                    ret = -ret
            fnd = (100.0 * p["fr"]
                   * funding_crossings(p["entry_ts"].to_pydatetime(),
                                       now.to_pydatetime())
                   * (1.0 if p["short"] else -1.0))
            net = ret - fee_pct + fnd
            eq += p["stake"] * net / 100.0
            trades.append({**p, "exit_px": px, "ret_pct": ret,
                           "net_pct": net, "stopped": hit,
                           "closed_ts": now, "equity_after": eq})
        book = keep

        # ── 빈 슬롯 채움 — 실거래와 같은 순서
        held = {p["symbol"] for p in book}
        nl = sum(1 for p in book if not p["short"])
        ns = len(book) - nl
        avail = [x for x in row.get("pool") or [] if x["s"] not in held]
        pl = sorted((x for x in avail if not x["sh"]), key=lambda x: x["zv"])
        ps = sorted((x for x in avail if x["sh"]), key=lambda x: -x["zv"])
        stake = eq / slots
        for x in pl[:max(half - nl, 0)] + ps[:max(half - ns, 0)]:
            book.append({"symbol": x["s"], "entry_ts": now,
                         "entry_px": float(x["px"]), "short": bool(x["sh"]),
                         "exit_ts": now + timedelta(minutes=hold),
                         "fr": 0.0, "stake": stake})
    return eq, trades


def verify(cycles: list[dict], live: pd.DataFrame, slots: int,
           state_p: Path) -> None:
    """옮겨 적은 **선별 규칙**이 실거래와 같은 종목을 고르는지 본다.

    책(보유)이 갈리면 고르는 것도 정당하게 갈린다. 그래서 여기서는
    **실거래 자신의 보유**를 그 시각 기준으로 복원해 넣고, 같은 풀에서
    같은 종목이 나오는지만 확인한다 — 규칙 전사(轉寫)만 격리해서 검사한다.

    ⚠ 지갑 실패·주문 거절로 실거래가 못 연 사이클은 **불일치가 정상**이다.
      그게 바로 재려는 값이라서, 그런 사이클은 따로 센다.
    """
    half = slots // 2
    opens = {}
    for _, r in live.iterrows():
        opens.setdefault(pd.Timestamp(r.entry_ts), []).append(
            (r.symbol, bool(r.short)))
    try:
        st = json.loads(state_p.read_text())
        for q in st.get("positions") or []:
            opens.setdefault(pd.Timestamp(q["entry_ts"]), []).append(
                (q["symbol"], bool(q.get("short"))))
    except Exception:                                         # noqa: BLE001
        pass

    def held_at(ts):
        """이 사이클이 **열기 전**의 보유. 경계가 둘 다 열려 있어야 한다.

        ⚠ `entry_ts <= ts` 로 쓰면 **이 사이클이 방금 연 포지션**이 보유로
          잡혀 슬롯이 꽉 찬 것처럼 보인다. 그러면 검사가 조용히 "판정할
          사이클이 없다"만 찍는다 — 한 번도 안 도는 검사는 통과가 아니다
          (2026-09-07 실측, 청산·재진입이 있었는데도 0건이었다).
        """
        out = []
        for _, r in live.iterrows():
            # ⚠ `exit_ts` 는 **예정** 시각이다. 손절로 일찍 닫힌 포지션은
            #   실제로는 없는데 예정 시각까지 보유로 잡힌다 — 2026-09-07
            #   AKEUSDT 가 06:45 진입 · 06:50 손절인데 exit_ts 는 08:45 라
            #   같은 사이클의 재진입이 '설명 안 되는 불일치'로 찍혔다.
            #   실제 청산은 `closed_ts` 다.
            end = pd.Timestamp(r.closed_ts) if pd.notna(r.closed_ts) \
                else pd.Timestamp(r.exit_ts)
            if pd.Timestamp(r.entry_ts) < ts < end:
                out.append((r.symbol, bool(r.short)))
        try:
            st = json.loads(state_p.read_text())
            for q in st.get("positions") or []:
                if (pd.Timestamp(q["entry_ts"]) < ts
                        < pd.Timestamp(q["exit_ts"])):
                    e = (q["symbol"], bool(q.get("short")))
                    if e not in out:
                        out.append(e)
        except Exception:                                     # noqa: BLE001
            pass
        return out

    n = agree = miss = 0
    for row in cycles:
        ts = pd.Timestamp(row["cycle"])
        pool = row.get("pool") or []
        if not pool:
            continue
        bk = held_at(ts)
        hs = {x[0] for x in bk}
        nl = sum(1 for x in bk if not x[1])
        ns = len(bk) - nl
        av = [x for x in pool if x["s"] not in hs]
        pl = sorted((x for x in av if not x["sh"]), key=lambda x: x["zv"])
        ps = sorted((x for x in av if x["sh"]), key=lambda x: -x["zv"])
        pred = {(x["s"], bool(x["sh"]))
                for x in pl[:max(half - nl, 0)] + ps[:max(half - ns, 0)]}
        if not pred:
            continue
        n += 1
        act = set(opens.get(ts, []))
        if pred == act:
            agree += 1
        elif row.get("blocked") or not act:
            miss += 1                     # 실거래가 못 연 사이클 — 정상 불일치
    print()
    print("=== 자체검사 — 선별 규칙 전사 ===")
    if n == 0:
        print("  판정할 사이클이 없다 (빈 슬롯이 있던 사이클이 아직 없음)")
        return
    print(f"  빈 슬롯이 있던 사이클 {n} · 실거래와 **일치 {agree}** "
          f"· 실거래가 못 연 것 {miss} · 설명 안 되는 불일치 {n - agree - miss}")
    if n - agree - miss:
        print("  🚨 **설명 안 되는 불일치가 있다 — 이 결과를 믿지 마라.**")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dir", default="runs/kinematics_live/s2both")
    p.add_argument("--slots", type=int, default=2)
    p.add_argument("--hold-min", type=int, default=HOLD)
    p.add_argument("--fee-pct", type=float, default=-1.0,
                   help="왕복 수수료(%%). 기본 -1 이면 실거래 원장의 **실측 중앙값**을 "
                        "쓴다 — 그래야 차이가 마찰이 아니라 체결 실패에서만 나온다")
    p.add_argument("--verify", action="store_true",
                   help="옮겨 적은 선별 규칙이 실거래와 같은 종목을 고르는지 "
                        "확인한다. 풀이 기록된 구간에서만 된다")
    a = p.parse_args()

    d = ROOT / a.dir if not Path(a.dir).is_absolute() else Path(a.dir)
    cycles = read_cycles(d)
    if not cycles:
        raise SystemExit(f"후보 풀이 없다 — {d}/<날짜>/cycles.jsonl "
                         f"(실거래에 --emit-pool 이 켜져 있나?)")
    live = read_live(d)
    start = pd.Timestamp(cycles[0]["cycle"])
    fee = a.fee_pct
    if fee < 0:
        fee = float(live.fee_pct.median()) if "fee_pct" in live else FEE_PCT

    eq0, book0, n_past = seed(live, start, d / "state.json")
    eq, tr = simulate(cycles, eq0, list(book0), a.slots, a.hold_min, fee)

    lv = live[live.closed_ts > start]
    print("=== 속도저울 그림자 (오프라인 반사실) ===")
    print(f"  경계 START {start}  — 이전 {n_past}거래는 **실거래와 동일**"
          f"(자본 {eq0:.6f}에서 출발)")
    print(f"  사이클 {len(cycles)}개 · 왕복 수수료 {fee:.4f}% 적용")
    print()
    print(f"{'':8}{'거래':>6}{'자본':>12}{'수익률':>10}{'손절':>6}")
    for lab, n, e, s in (("실거래", len(lv), float(live.equity_after.iloc[-1])
                          if len(live) else eq0,
                          int(lv.stopped.fillna(False).astype(bool).sum())
                          if len(lv) else 0),
                         ("그림자", len(tr), eq,
                          sum(1 for t in tr if t["stopped"]))):
        print(f"{lab:8}{n:>6}{e:>12.6f}{(e - 1) * 100:>+9.2f}%{s:>6}")
    gap = (eq - (float(live.equity_after.iloc[-1]) if len(live) else eq0)) * 100
    print()
    print(f"  체결 비용 = 그림자 − 실거래 = **{gap:+.3f}%p**")
    blocked = [r for r in cycles if r.get("blocked")]
    if blocked:
        print(f"  ⚠ 지갑 조회 실패로 진입을 접은 사이클 {len(blocked)}건 "
              f"— 그림자는 이 사이클에도 진입한다")
    if len(tr) < 30:
        print("  ⚠ 표본 30건 미만이다. **어떤 차이도 잡음이다.**")
    if a.verify:
        verify(cycles, live, a.slots, d / "state.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
