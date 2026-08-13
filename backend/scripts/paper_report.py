"""Paper-mode weekly/monthly report → Telegram, split by the two categories.

Category A = lifecycle family (paper shadow of the strategy running in real).
Category B = competition pool (everything else, competing for promotion).

Data source: the SessionStore forward-sim paper sessions (runs/paper_sessions/*)
— per-trade trades.jsonl (entry/exit ts, return_pct, pnl_cash). Mirrors the
real_trading_report cadence/format so the user gets paper + real in one style.

A "trade" = a completed round-trip in trades.jsonl whose exit_ts falls in the
period window. Absolute pnl_cash is NOT summed across strategies (mixed capital
bases $10k–$1M); the report uses per-trade return_pct, win rate, and best/worst
strategy by period return.

Usage:
  python -m scripts.paper_report --period week
  python -m scripts.paper_report --period month
  python -m scripts.paper_report --period week --dry
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "runs" / "paper_sessions"
sys.path.insert(0, str(ROOT))

REAL_ACCOUNT_ID = 8  # telegram destination (same REAL alert chats)
_KR = re.compile(r"^\d{6}$")
MIN_TRADES_TO_RANK = 5
ALIAS_PATH = ROOT / "configs" / "strategy_aliases.json"


def _load_alias_file() -> dict:
    try:
        return json.loads(ALIAS_PATH.read_text())
    except Exception:
        return {}


_ALIAS_FILE = _load_alias_file()
ALIASES = _ALIAS_FILE.get("aliases", {})
ALIAS_DESC = _ALIAS_FILE.get("descriptions", {})


def _alias_full(alias: str) -> str:
    """'파도타기(거래량폭발 추세 LONG)' 표기."""
    d = ALIAS_DESC.get(alias)
    return f"{alias}({d})" if d else alias


def _paradigm_key(name: str, sym: str) -> str:
    if "lifecycle" in name:
        return "lifecycle"
    key = name[len(sym) + 1:] if name.startswith(sym + "_") else name
    return key.removesuffix("_paper_seed")


def _alias(name: str, sym: str) -> str:
    return ALIASES.get(_paradigm_key(name, sym), "")


# 누적 기준일. A(신상저격수 페이퍼 미러)는 실거래 개시일과 맞추고,
# B(2군 리그)는 substrate 결함으로 6월까지가 무효라 유효 시계 시작일을 쓴다
# (project_vb_127_128_substrate_stall_fix).
BASE_A = date(2026, 6, 1)
BASE_B = date(2026, 7, 1)


# ── 고정폭 표 (Telegram <pre>) ────────────────────────────────────────────
# 한글은 monospace에서도 2칸이므로 East-Asian width로 패딩해야 열이 맞는다.

def _dwidth(s: str) -> int:
    import unicodedata
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in s)


def _pad(s: str, width: int, right: bool = False) -> str:
    gap = max(0, width - _dwidth(s))
    return (" " * gap + s) if right else (s + " " * gap)


def _table(cols: list[tuple], rows: list[list[str]]) -> list[str]:
    """cols = [(헤더, 폭, 우측정렬)], rows = [[셀...]]"""
    width = sum(c[1] for c in cols) + len(cols) - 1
    head = " ".join(_pad(n, w, r) for n, w, r in cols)
    L = ["<pre>", head, "─" * width]
    for row in rows:
        L.append(" ".join(_pad(c, w, r) for c, (_, w, r) in zip(row, cols)))
    L.append("</pre>")
    return L


def _short_sym(sym: str) -> str:
    return sym[:-4] if sym.endswith("USDT") else sym


def _sess_label(sess: dict) -> str:
    al = _alias(sess["name"], sess["symbol"])
    sym = _short_sym(sess["symbol"])
    return f"{al}·{sym}" if al else sym


def _rank(sessions: list[dict], start: date, end: date, topn: int = 5) -> list[dict]:
    """구간 내 완결 거래 수익률 합으로 세션 순위."""
    s_iso, e_iso = start.isoformat(), end.isoformat()
    rows = []
    for sess in sessions:
        rets = [float(t.get("return_pct", 0)) for t in sess["trades"]
                if s_iso <= str(t.get("exit_ts", ""))[:10] < e_iso]
        if not rets:
            continue
        rows.append({"label": _sess_label(sess), "ret": sum(rets) * 100.0, "n": len(rets)})
    rows.sort(key=lambda r: -r["ret"])
    return rows[:topn]


def _rank_table(title: str, ranked: list[dict]) -> list[str]:
    if not ranked:
        return [f"  {title} — 완결 거래 없음"]
    cols = [("#", 2, False), ("전략·심볼", 14, False), ("수익률", 8, True), ("거래", 4, True)]
    rows = [[str(i), r["label"], f"{r['ret']:+.2f}%", str(r["n"])]
            for i, r in enumerate(ranked, 1)]
    return [f"  <b>{title}</b>"] + _table(cols, rows)


def _summary_table(sessions: list[dict], base: date, today: date) -> list[str]:
    """최근7일 / 최근30일 / 누적 요약."""
    cols = [("기간", 10, False), ("거래", 5, True), ("승률", 5, True), ("평균/거래", 9, True)]
    rows = []
    for label, start in (("최근7일", today - timedelta(days=7)),
                         ("최근30일", today - timedelta(days=30)),
                         (f"누적", base)):
        st = _cat_stats(sessions, start, today + timedelta(days=1))
        rows.append([label, str(st["n_trades"]),
                     f"{st['win_rate']:.0f}%" if st["n_trades"] else "-",
                     f"{st['avg_ret']:+.2f}%" if st["n_trades"] else "-"])
    return _table(cols, rows)


def _month_bounds(y: int, m: int) -> tuple[date, date]:
    start = date(y, m, 1)
    end = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
    return start, end


def _prev_month(y: int, m: int) -> tuple[int, int]:
    return (y - 1, 12) if m == 1 else (y, m - 1)


def _load_sessions() -> list[dict]:
    out = []
    for sj in STORE.glob("*/session.json"):
        try:
            s = json.loads(sj.read_text())
        except Exception:
            continue
        if s.get("status") != "active":
            continue
        sid = sj.parent.name
        name = s.get("name", "")
        sym = s.get("symbol", "")
        if _KR.match(sym):
            # KR 주식 페이퍼(pattern_flow 등)는 바이낸스 리포트 대상 아님
            # (2026-07-11 대표님 지시 — 🅱️ 승격 경쟁은 바이낸스 2군 리그만)
            continue
        cat = "A" if "lifecycle" in name else "B"
        trades = []
        tp = STORE / sid / "trades.jsonl"
        if tp.exists():
            for ln in tp.read_text().splitlines():
                ln = ln.strip()
                if ln:
                    try:
                        _t = json.loads(ln)
                    except Exception:
                        continue
                    if _t.get("invalid"):    # 무효 표시 제외 (INVALID_TRADES.json)
                        continue
                    trades.append(_t)
        out.append({"sid": sid, "symbol": sym, "name": name, "cat": cat, "trades": trades})
    return out


def _cat_stats(sessions: list[dict], start: date, end: date) -> dict:
    """Aggregate stats for one category over [start, end) by trade exit date."""
    s_iso, e_iso = start.isoformat(), end.isoformat()
    n_active = len(sessions)
    all_rets, all_pnl = [], []
    per_sess_ret: dict[str, float] = {}
    per_sess_label: dict[str, str] = {}
    for sess in sessions:
        sret = 0.0
        hit = False
        for t in sess["trades"]:
            ex = str(t.get("exit_ts", ""))[:10]
            if ex and s_iso <= ex < e_iso:
                r = float(t.get("return_pct", 0))
                all_rets.append(r)
                all_pnl.append(float(t.get("pnl_cash", 0)))
                sret += r
                hit = True
        if hit:
            per_sess_ret[sess["sid"]] = sret * 100.0
            al = _alias(sess["name"], sess["symbol"])
            per_sess_label[sess["sid"]] = f"{al}·{sess['symbol']}" if al else sess["symbol"]
    groups: dict[str, dict] = {}
    for sess in sessions:
        al = _alias(sess["name"], sess["symbol"]) or _paradigm_key(sess["name"], sess["symbol"])
        g = groups.setdefault(al, {"n_active": 0, "rets": []})
        g["n_active"] += 1
        for t in sess["trades"]:
            ex = str(t.get("exit_ts", ""))[:10]
            if ex and s_iso <= ex < e_iso:
                g["rets"].append(float(t.get("return_pct", 0)))
    n = len(all_rets)
    wins = [p for p in all_pnl if p > 0]
    best = max(per_sess_ret.items(), key=lambda kv: kv[1]) if per_sess_ret else None
    worst = min(per_sess_ret.items(), key=lambda kv: kv[1]) if per_sess_ret else None
    return {
        "n_active": n_active,
        "n_trades": n,
        "win_rate": (len(wins) / n * 100.0) if n else 0.0,
        "avg_ret": (sum(all_rets) / n * 100.0) if n else 0.0,
        "best": (per_sess_label[best[0]], best[1]) if best else None,
        "worst": (per_sess_label[worst[0]], worst[1]) if worst else None,
        "n_traded_sessions": len(per_sess_ret),
        "groups": {
            k: {"n_active": g["n_active"], "n_trades": len(g["rets"]),
                "avg_ret": (sum(g["rets"]) / len(g["rets"]) * 100.0) if g["rets"] else 0.0}
            for k, g in groups.items()
        },
    }


def _cat_block(title: str, cur: dict, prev: dict, show_groups: bool = False) -> list[str]:
    L = [f"━━ {title} ━━"]
    L.append(f"  활성 {cur['n_active']} · 거래 <b>{cur['n_trades']}</b>회 (전기간 {prev['n_trades']})")
    if cur["n_trades"]:
        L.append(f"  승률 {cur['win_rate']:.0f}% · 평균 <b>{cur['avg_ret']:+.2f}%</b>/거래")
        if cur["best"]:
            L.append(f"  최고 {cur['best'][0]} {cur['best'][1]:+.1f}% · 최저 {cur['worst'][0]} {cur['worst'][1]:+.1f}%")
    else:
        L.append("  이번 기간 완결 거래 없음")
    if show_groups and len(cur.get("groups", {})) > 1:
        for k, g in sorted(cur["groups"].items(), key=lambda kv: -kv[1]["n_active"]):
            if g["n_trades"]:
                L.append(f"    · {_alias_full(k)} {g['n_active']}석 — {g['n_trades']}회, 평균 {g['avg_ret']:+.2f}%")
            else:
                L.append(f"    · {_alias_full(k)} {g['n_active']}석 — 거래 없음")
    return L


def build_message(kind_ko: str, cmp_ko: str, label: str, a_cur, a_prev, b_cur, b_prev,
                  A: list[dict] | None = None, B: list[dict] | None = None) -> str:
    today = datetime.utcnow().date()
    L = [f"📄 <b>페이퍼 {kind_ko} 리포트</b>", f"<b>{label}</b> ({cmp_ko} 대비)", ""]

    # ── 🅰️ 신상저격수 (실거래 병행) ──
    L.append(f"━━ 🅰️ {_alias_full('신상저격수')} ━━")
    L.append(f"  활성 {a_cur['n_active']}석 · 이번 {kind_ko[0]} <b>{a_cur['n_trades']}</b>회 "
             f"({cmp_ko} {a_prev['n_trades']})")
    if A is not None:
        L += _summary_table(A, BASE_A, today)
        L.append(f"  <i>누적 기준일 {BASE_A.isoformat()}</i>")
    L.append("")

    # ── 🅱️ 승격 경쟁 (2군 리그) ──
    L.append("━━ 🅱️ 승격 경쟁 (2군 리그) ━━")
    L.append(f"  활성 {b_cur['n_active']}석 · 이번 {kind_ko[0]} <b>{b_cur['n_trades']}</b>회 "
             f"({cmp_ko} {b_prev['n_trades']})")
    if B is not None:
        L += _summary_table(B, BASE_B, today)
        L.append(f"  <i>누적 기준일 {BASE_B.isoformat()}</i>")
        L.append("")
        L += _rank_table("주간 순위 TOP5 (최근 7일)", _rank(B, today - timedelta(days=7), today + timedelta(days=1)))
        L += _rank_table("월간 순위 TOP5 (최근 30일)", _rank(B, today - timedelta(days=30), today + timedelta(days=1)))
        L += _rank_table(f"누적 순위 TOP5 ({BASE_B.isoformat()}~)", _rank(B, BASE_B, today + timedelta(days=1)))

    # 전략군별 요약 (별칭 기준)
    if len(b_cur.get("groups", {})) > 1:
        L.append("")
        L.append("  <b>전략군별</b>")
        for k, g in sorted(b_cur["groups"].items(), key=lambda kv: -kv[1]["n_active"]):
            if g["n_trades"]:
                L.append(f"    · {_alias_full(k)} {g['n_active']}석 — {g['n_trades']}회, 평균 {g['avg_ret']:+.2f}%")
            else:
                L.append(f"    · {_alias_full(k)} {g['n_active']}석 — 거래 없음")
    return "\n".join(L)


def _windows(period: str):
    if period == "month":
        today = datetime.utcnow().date()
        y, m = _prev_month(today.year, today.month)
        ts, te = _month_bounds(y, m)
        py, pm = _prev_month(y, m)
        ps, pe = _month_bounds(py, pm)
        return "월간", "전월", f"{y}-{m:02d}", (ts, te), (ps, pe)
    end = datetime.utcnow().date()
    ts, te = end - timedelta(days=7), end
    ps, pe = end - timedelta(days=14), end - timedelta(days=7)
    label = f"{ts.isoformat()}~{(end - timedelta(days=1)).isoformat()}"
    return "주간", "전주", label, (ts, te), (ps, pe)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", choices=["week", "month"], default="week")
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()

    kind_ko, cmp_ko, label, (ts, te), (ps, pe) = _windows(args.period)
    sessions = _load_sessions()
    A = [s for s in sessions if s["cat"] == "A"]
    B = [s for s in sessions if s["cat"] == "B"]
    a_cur, a_prev = _cat_stats(A, ts, te), _cat_stats(A, ps, pe)
    b_cur, b_prev = _cat_stats(B, ts, te), _cat_stats(B, ps, pe)
    msg = build_message(kind_ko, cmp_ko, label, a_cur, a_prev, b_cur, b_prev, A=A, B=B)

    print(msg)
    print("\n---")
    if args.dry:
        print("[DRY] not sending")
        return 0
    if a_cur["n_trades"] == 0 and b_cur["n_trades"] == 0 and a_prev["n_trades"] == 0 and b_prev["n_trades"] == 0:
        print("[SKIP] no paper trades in window")
        return 0
    try:
        from scripts.binance.lifecycle_live_signal_driver import _telegram_notify
        _telegram_notify(REAL_ACCOUNT_ID, msg)
        print("[SENT] telegram dispatched")
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] telegram send: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
