#!/usr/bin/env python3
"""RSI 1군 **정기 보고** — :00/:30 마다 스스로 보낸다.

왜 만들었나 (2026-08-31)
    대표님이 물으셨다. "왜 자동으로 보고하지 않는 거야?"

    오전에 이상 감시(`rsi_live_sentry.py`)는 자율로 만들었지만, **정기
    보고는 여전히 사람이 쳐야 도는 상태로 뒀다.** 절반만 고친 것이다.
    감시기가 「이상이 있을 때만」 운다면, 이건 「이상이 없어도 30분마다」
    보낸다 — 조용한 것과 멈춘 것을 구분하려면 정기 신호가 있어야 한다.

⚠ 텍스트를 파싱하지 않는다
    3자 비교 수치는 `rsi_three_way.py --json` 에서 **구조화된 채로** 받는다.
    사람이 읽으라고 만든 표를 기계가 되읽으면 서식이 바뀌는 날 조용히 깨진다.

⚠ 아무것도 고치지 않는다. 읽고 보낼 뿐이다.
"""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]          # backend/
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "binance"))

SESS_ROOT = ROOT / "runs" / "paper_sessions" / "rsi_extreme"
LIVE, SHADOW, OLD5M = "30m_rsi12_LIVE", "30m_rsi12_SHADOW", "5m_rsi10"
SEEN = SESS_ROOT / ".report_seen.json"
KST = timezone(timedelta(hours=9))

# 표에 낼 계정 — 0 이 아니면 그 자체로 이야깃거리다
COUNTERS = [("n_reject_order", "주문거절"), ("n_reject_tp", "익절거절"),
            ("n_reject_sl", "손절거절"), ("n_kernelfail", "커널실패"),
            ("n_slipreject", "괴리거부"), ("n_tapmiss", "탭결손"),
            ("n_stalebar", "묵은봉"), ("n_quiet", "침묵")]

log = logging.getLogger("rsi-report")


# ── 폭을 아는 박스 표 ────────────────────────────────────────────
#    ⚠ 한글은 대부분의 고정폭 글꼴에서 두 칸이다. len() 으로 맞추면
#      대표님 화면에서 표가 깨진다 — 2026-08-31 에 실제로 깨뜨렸다.
def _w(s: str) -> int:
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1
               for c in str(s))


def box(header: list, rows: list, aligns: list | None = None) -> str:
    n = len(header)
    aligns = aligns or ["l"] * n
    width = [max([_w(header[i])] + [_w(r[i]) for r in rows]) for i in range(n)]

    def pad(s, i):
        d = width[i] - _w(s)
        return (" " * d + str(s)) if aligns[i] == "r" else (str(s) + " " * d)

    def line(l, m, r):
        return l + m.join("─" * (width[i] + 2) for i in range(n)) + r

    out = [line("┌", "┬", "┐"),
           "│ " + " │ ".join(pad(header[i], i) for i in range(n)) + " │",
           line("├", "┼", "┤")]
    for r in rows:
        out.append("│ " + " │ ".join(pad(r[i], i) for i in range(n)) + " │")
    out.append(line("└", "┴", "┘"))
    return "\n".join(out)


def _state(name: str) -> dict:
    f = SESS_ROOT / name / "state.json"
    if not f.exists():
        return {}
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:                                        # noqa: BLE001
        return {}


def _three_way() -> dict:
    """3자 비교를 **구조화된 채로** 받는다."""
    r = subprocess.run(
        [str(ROOT / "venv" / "bin" / "python3"),
         str(ROOT / "scripts" / "binance" / "rsi_three_way.py"), "--json"],
        cwd=str(ROOT), capture_output=True, text=True, timeout=300)
    for ln in reversed((r.stdout or "").strip().splitlines()):
        if ln.startswith("{"):
            return json.loads(ln)
    raise RuntimeError(f"3자 비교 JSON 을 못 읽었다 (rc={r.returncode}): "
                       f"{(r.stderr or '')[-300:]}")


def _exchange(account: int) -> dict:
    """거래소 원본. ⚠ 못 읽으면 **모른다**고 말한다 (교훈 #106)."""
    try:
        from rsi_live_broker import LiveBroker, _run
        from app.adapters.binance_futures import FAPI_V2
        b = LiveBroker(account_id=account, notional_usd=1.0, dry_run=True)
        b.connect()
        rows = _run(b._adapter._signed_get(f"{FAPI_V2}/positionRisk", {}))
        pos = {r["symbol"]: float(r["positionAmt"]) for r in (rows or [])
               if abs(float(r.get("positionAmt", 0) or 0)) > 0}
        return {"ok": True, "pos": pos, "oo": b.open_orders(),
                "algo": b.open_algo_orders()}
    except Exception as exc:                                 # noqa: BLE001
        return {"ok": False, "err": str(exc)}


def build(account: int = 8) -> tuple[str, dict]:
    tw = _three_way()
    live, shadow, old = _state(LIVE), _state(SHADOW), _state(OLD5M)
    ex = _exchange(account)

    # ① 3자 비교 — 텔레그램에서 읽히도록 폭을 줄인다
    #    (주간·월간·연간은 표본 30건 전엔 어차피 '—' 다)
    hdr = tw["hdr"]
    keep = ["", "체결", "총손익%p", "거래당%", "익절비중%", "종목"]
    ix = [hdr.index(k) for k in keep]
    rows = [[r[i] for i in ix] for r in tw["rows"]]
    t1 = box(["", "체결", "총손익%p", "거래당%", "익절%", "종목"], rows,
             ["l", "r", "r", "r", "r", "r"])

    # ② 손익 — 실현과 미실현을 절대 섞지 않는다
    def money(st, name):
        realized = float(st.get("equity", 0) or 0)
        return [name, f"{realized:+.4f}$", f"{len(st.get('pos', [])):d}"]
    t2 = box(["세션", "실현", "보유"],
             [money(live, "실거래"), money(shadow, "그림자"),
              money(old, "구5분봉")], ["l", "r", "r"])

    # ③ 계정 — 0 이 아닌 것만 낸다. 0 을 줄줄이 세면 안 보게 된다.
    acc = [(ko, int(live.get(k, 0)), int(shadow.get(k, 0)))
           for k, ko in COUNTERS
           if int(live.get(k, 0)) or int(shadow.get(k, 0))]
    t3 = (box(["계정", "실거래", "그림자"],
              [[ko, str(a), str(b)] for ko, a, b in acc], ["l", "r", "r"])
          if acc else "")

    now = datetime.now(KST).strftime("%m-%d %H:%M")
    txt = [f"📊 <b>RSI 1군 정기보고</b> · {now} KST", "", f"<pre>{t1}</pre>"]
    n_live = int(tw.get("n_live", 0) or 0)
    if n_live < 30:
        txt.append(f"표본 {n_live}건 — 30건 미만이라 <b>어떤 차이도 잡음</b>이다.")
    if tw.get("fill_cost_pp") is not None:
        txt.append(f"체결 비용(그림자−실거래) = <b>{tw['fill_cost_pp']:+.2f}%p</b>")
    txt += ["", f"<pre>{t2}</pre>"]

    # ④ 보유 — 미실현은 **평가액**이지 실현이 아니다
    held = live.get("pos", []) + shadow.get("pos", [])
    txt.append("1군·그림자 보유 없음 · 미실현 0."
               if not held else
               "보유: " + " · ".join(f"{p['symbol']} @{p['entry_price']:.8g}"
                                     for p in held)
               + "\n(미실현은 평가액이지 실현이 아니다)")

    # ⑤ 거래소 — 장부와 맞는가
    if not ex["ok"]:
        txt.append(f"\n🚨 거래소를 <b>읽지 못했다</b> — {ex['err'][:120]}\n"
                   f"포지션 상태를 <b>모른다</b>. 없다는 뜻이 아니다.")
    else:
        book = {p["symbol"] for p in live.get("pos", [])}
        same = book == set(ex["pos"])
        txt.append(f"\n거래소 {'✔ 장부와 일치' if same else '🚨 <b>불일치</b>'} · "
                   f"포지션 {len(ex['pos'])} · 미체결 {len(ex['oo'])} · "
                   f"조건부 {len(ex['algo'])}")
        if not same:
            txt.append(f"  장부 {sorted(book)} / 거래소 {sorted(ex['pos'])}")
    if t3:
        txt += ["", f"<pre>{t3}</pre>"]

    # ⑥ 변경점 — 직전 보고 대비. 이게 없으면 매번 같은 표를 다시 읽어야 한다.
    cur = {"n_fill_live": int(live.get("n_fill", 0)),
           "n_fill_shadow": int(shadow.get("n_fill", 0)),
           "eq_live": round(float(live.get("equity", 0) or 0), 4),
           "eq_shadow": round(float(shadow.get("equity", 0) or 0), 4)}
    prev = {}
    if SEEN.exists():
        try:
            prev = json.loads(SEEN.read_text(encoding="utf-8"))
        except Exception:                                    # noqa: BLE001
            prev = {}
    if prev:
        d = []
        if cur["n_fill_live"] != prev.get("n_fill_live"):
            d.append(f"실거래 체결 {prev['n_fill_live']}→{cur['n_fill_live']}")
        if cur["n_fill_shadow"] != prev.get("n_fill_shadow"):
            d.append(f"그림자 체결 {prev['n_fill_shadow']}→{cur['n_fill_shadow']}")
        if cur["eq_live"] != prev.get("eq_live"):
            d.append(f"실거래 실현 {prev['eq_live']:+.4f}→{cur['eq_live']:+.4f}$")
        if cur["eq_shadow"] != prev.get("eq_shadow"):
            d.append(f"그림자 실현 {prev['eq_shadow']:+.4f}→{cur['eq_shadow']:+.4f}$")
        txt.append("\n변경: " + (" · ".join(d) if d else "직전 보고 대비 없음"))
    else:
        txt.append("\n변경: (첫 보고 — 비교 대상 없음)")
    return "\n".join(txt), cur


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--account", type=int, default=8)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    text, cur = build(a.account)
    if a.dry_run:
        print(text)
        return 0
    try:
        from scripts.binance.lifecycle_live_signal_driver import _telegram_notify
        _telegram_notify(a.account, text)
        log.info("정기보고 발송 완료 — 계좌 %d · %d자", a.account, len(text))
    except Exception as exc:                                 # noqa: BLE001
        log.critical("정기보고 발송 실패: %s", exc)
        return 2
    # 발송에 성공했을 때만 기준선을 옮긴다 — 실패한 보고의 변경점은 다음에 나가야 한다
    SEEN.parent.mkdir(parents=True, exist_ok=True)
    SEEN.write_text(json.dumps(cur, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
