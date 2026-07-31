"""Send the daily dashboard digest (오늘 판단 + 어제 결과) to Telegram (ATS COIN group).
Reads today_market.json / etf_judgment.json / yesterday_result.json from DASH_OUTDIR,
bot token + chat_id from ~/fx_site/.tg (token line1, chat_id line2, chmod 600).
"""
import os, json, html, sys, urllib.request

# Shared sent-message log (app/core/telegram_sent_log.py) so this digest can be
# bulk-deleted later via scripts/telegram/purge_messages.py. The module is
# stdlib-only, so importing it from this separate venv is safe. Best-effort:
# a missing repo must never block the send.
_BACKEND = "/home/mint/auto_trading/backend"
try:
    if _BACKEND not in sys.path:
        sys.path.insert(0, _BACKEND)
    from app.core.telegram_sent_log import record_sent, extract_message_id
except Exception:  # repo moved / not deployed on this host
    def record_sent(*_a, **_k):
        return None

    def extract_message_id(_r):
        return None

OUTDIR = os.environ.get("DASH_OUTDIR", "/home/hcpark/antigravity/backend/runs/fx")
FXDIR = os.path.join(os.path.expanduser("~"), "fx_site")
TG = os.path.join(FXDIR, ".tg")
AUTH = os.path.join(FXDIR, ".auth")
SITE = "https://fx.n7n.uk"


def site_link():
    """토큰 포함 접근 링크 — 수신자가 클릭하면 쿠키 설정돼 바로 열림."""
    try:
        tok = open(AUTH).read().strip()
        return "%s/?k=%s" % (SITE, tok)
    except Exception:
        return SITE


def load(name):
    with open(os.path.join(OUTDIR, name), encoding="utf-8") as f:
        return json.load(f)


def send(token, chat, text):
    data = json.dumps({"chat_id": chat, "text": text, "parse_mode": "HTML",
                       "disable_web_page_preview": True}).encode()
    req = urllib.request.Request("https://api.telegram.org/bot%s/sendMessage" % token,
                                 data=data, headers={"Content-Type": "application/json"})
    r = json.loads(urllib.request.urlopen(req, timeout=15).read())
    return r.get("ok", False), r.get("description", ""), r


def sgn(v):
    return ("+" if v >= 0 else "") + str(v)


def build():
    tm = load("today_market.json")
    j = load("etf_judgment.json")
    L = []
    L.append("📊 <b>한국증시 ETF 판단</b>  ·  %s(%s)" % (tm["date"], tm["weekday"]))
    L.append("")
    # 오늘 판단
    if tm["is_trading_day"]:
        L.append("<b>■ 오늘 판단 · %s</b> (점수 %s)" % (j["regime"], sgn(j["score"])))
        for e in j["etfs"]:
            L.append("  · %s: <b>%s</b>" % (e["name"], e["verdict"]))
    else:
        L.append("🔴 <b>오늘 휴장</b> · %s — 판단 없음" % tm["reason"])
        L.append("  (최근 거래일 %s 판단: %s)" % (j["for_date"], j["regime"]))
    L.append("")
    # 어제 결과
    try:
        yv = load("yesterday_result.json")
    except Exception:
        yv = {"status": "none"}
    if yv.get("status") == "result":
        r = yv["result"]
        L.append("<b>■ 어제(%s %s) 결과 · %s</b>" % (r["date"], r["wd"], r["hit_label"]))
        L.append("  %s 예측 → 실제 KODEX200 <b>%s%%</b>" % (r["regime"], sgn(r["kodex_return"])))
        ss = r.get("sig_summary", {})
        L.append("  신호 %d적중 / %d빗나감" % (ss.get("aligned", 0), ss.get("missed", 0)))
        st = yv.get("stats", {})
        if st.get("rate") is not None:
            L.append("  누적 적중률 %s%% (%d건)" % (st["rate"], st.get("directional", 0)))
        if r.get("analysis"):
            L.append("  <i>%s</i>" % html.escape(r["analysis"][:180]))
    elif yv.get("status") == "holiday":
        L.append("<b>■ 어제(%s) 휴장</b> — 결과 없음" % yv.get("date", ""))
    else:
        L.append("<b>■ 어제 결과</b> — 기록 없음")
    L.append("")
    L.append('🔗 <a href="%s">대시보드 열기 (전체 분석)</a>' % site_link())
    return "\n".join(L)


def main():
    if not os.path.exists(TG):
        print("telegram skip (~/fx_site/.tg 없음)")
        return
    tok, chat = open(TG).read().strip().split("\n")[:2]
    text = build()
    ok, err, resp = send(tok, chat, text)
    if ok:
        mid = extract_message_id(resp)
        record_sent(chat, mid, text, source="etf_daytrade")
        print("telegram sent (message_id=%s)" % mid)
    else:
        print("telegram FAILED: " + err)


if __name__ == "__main__":
    main()
