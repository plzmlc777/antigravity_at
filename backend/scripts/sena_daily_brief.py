"""세나테크놀로지(061090) 일일 브리프 — 장전(08:30 KST) / 장후(16:30 KST).

데이터 소스:
- 시세/메타: m.stock.naver.com/api/stock/{code}/integration
- 뉴스: m.stock.naver.com/api/news/stock/{code}
- 토론방: stock.naver.com/api/community/discussion/posts/by-item
- 공시: OpenDART list.json (corp_code 01010615)

텔레그램 인증: 환경변수 TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID (caller가 eval로 export).
            또는 load_telegram_creds.py 폴백.

사용:
    python3 backend/scripts/sena_daily_brief.py --mode pre   # 장전 (08:30 KST)
    python3 backend/scripts/sena_daily_brief.py --mode post  # 장후 (16:30 KST)
    python3 backend/scripts/sena_daily_brief.py --mode post --dry-run  # 미발송
"""
import argparse
import os
import sys
import json
import re
import urllib.request
import urllib.parse
from datetime import datetime, timedelta, timezone
from html import unescape

# .env 로드 (backend/.env)
HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(HERE)
sys.path.insert(0, BACKEND_DIR)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(BACKEND_DIR, ".env"))
except Exception:
    pass

SYMBOL = "061090"
SYMBOL_NAME = "세나테크놀로지"
CORP_CODE = "01010615"
KST = timezone(timedelta(hours=9))


def now_kst() -> datetime:
    return datetime.now(KST)


def http_get_json(url: str, headers: dict, timeout: int = 12):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


NAVER_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://m.stock.naver.com/",
}
NAVER_DISC_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://stock.naver.com/",
}


def fetch_quote() -> dict:
    url = f"https://m.stock.naver.com/api/stock/{SYMBOL}/integration"
    d = http_get_json(url, NAVER_HEADERS)
    info = {t["key"]: t["value"] for t in d.get("totalInfos", [])}
    info["_stockName"] = d.get("stockName", SYMBOL_NAME)
    return info


def fetch_news(since_hours: int = 24) -> list:
    url = f"https://m.stock.naver.com/api/news/stock/{SYMBOL}?pageSize=30"
    raw = http_get_json(url, NAVER_HEADERS)
    items = []
    for grp in raw:
        items.extend(grp.get("items", []))
    cutoff = (now_kst() - timedelta(hours=since_hours)).strftime("%Y%m%d%H%M")
    items = [it for it in items if it.get("datetime", "") >= cutoff]
    items.sort(key=lambda x: x.get("datetime", ""), reverse=True)
    return items


def fetch_market_news(category: str = "KOSDAQ", limit: int = 5) -> list:
    url = f"https://m.stock.naver.com/api/news/stock/{category}?pageSize=15"
    raw = http_get_json(url, NAVER_HEADERS)
    items = []
    for grp in raw:
        items.extend(grp.get("items", []))
    items.sort(key=lambda x: x.get("datetime", ""), reverse=True)
    return items[:limit]


def fetch_discussion_today() -> list:
    base = "https://stock.naver.com/api/community/discussion/posts/by-item"
    today_kst = now_kst().strftime("%Y-%m-%d")
    yesterday_kst = (now_kst() - timedelta(days=1)).strftime("%Y-%m-%d")
    posts = []
    offset = None
    for _ in range(6):
        params = {
            "discussionType": "domesticStock",
            "itemCode": SYMBOL,
            "isHolderOnly": "false",
            "excludesItemNews": "false",
            "isItemNewsOnly": "false",
            "isCleanbotPassedOnly": "false",
            "pageSize": "100",
        }
        if offset is not None:
            params["offset"] = str(offset)
        url = base + "?" + urllib.parse.urlencode(params)
        d = http_get_json(url, NAVER_DISC_HEADERS)
        page_posts = d.get("posts", [])
        if not page_posts:
            break
        posts.extend(page_posts)
        offset = d.get("lastOffset")
        last_date = page_posts[-1].get("writtenAt", "")[:10]
        if last_date < yesterday_kst:
            break
    return [p for p in posts if p.get("writtenAt", "").startswith(today_kst)]


def fetch_disclosures(days: int = 7) -> list:
    key = os.getenv("OPENDART_API_KEY")
    if not key:
        return []
    end = now_kst().strftime("%Y%m%d")
    start = (now_kst() - timedelta(days=days)).strftime("%Y%m%d")
    url = (
        f"https://opendart.fss.or.kr/api/list.json"
        f"?crtfc_key={key}&corp_code={CORP_CODE}"
        f"&bgn_de={start}&end_de={end}&page_count=50"
    )
    try:
        d = http_get_json(url, {"User-Agent": "Mozilla/5.0"})
    except Exception:
        return []
    if d.get("status") != "000":
        return []
    return d.get("list", [])


def clean_html(s: str) -> str:
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", unescape(s)).strip()


def classify_sentiment(text: str) -> str:
    t = text
    bullish_kw = [
        "상한가", "상승", "갑니다", "간다", "매수", "팟팅", "존버", "매집",
        "신고가", "돌파", "대장주", "호재", "급등", "랠리", "유망", "기대",
    ]
    bearish_kw = [
        "손절", "매도", "하락", "폭락", "청산", "탈출", "잡주",
        "물렸", "물림", "지하실", "마이너스", "사기", "환장", "지긋지긋",
    ]
    suspicious_kw = [
        "세력", "작전", "기법", "허매수", "리딩방", "털기", "뻥튀기", "의심",
        "이상", "조작", "장난질", "찌라시",
    ]
    b = sum(1 for k in bullish_kw if k in t)
    s = sum(1 for k in bearish_kw if k in t)
    sp = sum(1 for k in suspicious_kw if k in t)
    if sp >= 2:
        return "suspicious"
    if b > s + 1:
        return "bullish"
    if s > b + 1:
        return "bearish"
    return "neutral"


def telegram_escape(s: str) -> str:
    """Markdown(legacy) 특수문자 최소 escape: * _ ` ["""
    for ch in ("*", "_", "`", "["):
        s = s.replace(ch, "\\" + ch)
    return s


def send_telegram(text: str) -> tuple:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False, "missing credentials"
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": "true",
    }).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            resp = json.loads(r.read())
        return resp.get("ok", False), resp.get("description", "ok")
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read())
            return False, body.get("description", str(e))
        except Exception:
            return False, str(e)
    except Exception as e:
        return False, str(e)


def build_message(mode: str) -> str:
    ts = now_kst()

    # 데이터 수집 (실패는 무시하고 부분 메시지)
    quote = {}
    try:
        quote = fetch_quote()
    except Exception as e:
        quote = {"_err": str(e)}

    news = []
    try:
        news = fetch_news(since_hours=24)
    except Exception:
        pass

    market_news = []
    try:
        market_news = fetch_market_news("KOSDAQ", limit=5)
    except Exception:
        pass

    posts = []
    try:
        posts = fetch_discussion_today()
    except Exception:
        pass

    disclosures = []
    try:
        disclosures = fetch_disclosures(days=7)
    except Exception:
        pass

    is_pre = (mode == "pre")
    icon = "🌅" if is_pre else "🌆"
    label = "장 시작 전 브리프" if is_pre else "장 마감 브리프"

    lines = []
    lines.append(f"{icon} *{SYMBOL_NAME}({SYMBOL}) {label}*")
    lines.append(f"_{ts.strftime('%Y-%m-%d %H:%M KST')}_")
    lines.append("")

    # ── 시세 ──
    lines.append("📊 *시세*")
    if "_err" in quote:
        lines.append(f"  (조회 실패: {quote['_err'][:60]})")
    else:
        ordered = ["전일", "시가", "고가", "저가", "거래량", "대금", "시총", "외인소진율", "PER", "PBR"]
        for k in ordered:
            if k in quote:
                lines.append(f"  {k}: `{quote[k]}`")
    lines.append("")

    # ── 공시 ──
    if disclosures:
        lines.append(f"📋 *DART 공시 (최근 7일, {len(disclosures)}건)*")
        for d in disclosures[:6]:
            dt = d.get("rcept_dt", "")
            fmt = f"{dt[:4]}-{dt[4:6]}-{dt[6:8]}" if len(dt) == 8 else dt
            nm = telegram_escape(d.get("report_nm", "").strip()[:60])
            lines.append(f"  • {fmt}  {nm}")
        lines.append("")

    # ── 종목 뉴스 ──
    if news:
        lines.append(f"📰 *종목 뉴스 (최근 24h, {len(news)}건)*")
        for n in news[:8]:
            dt = n.get("datetime", "")
            fmt = f"{dt[4:6]}/{dt[6:8]} {dt[8:10]}:{dt[10:12]}" if len(dt) >= 12 else dt
            title = telegram_escape(clean_html(n.get("title", ""))[:60])
            office = telegram_escape(n.get("officeName", "")[:10])
            lines.append(f"  • `{fmt}` ({office}) {title}")
        lines.append("")

    # ── 시장 헤드라인 ──
    if market_news:
        lines.append("🌐 *KOSDAQ 헤드라인 (Top 5)*")
        for n in market_news:
            dt = n.get("datetime", "")
            fmt = f"{dt[8:10]}:{dt[10:12]}" if len(dt) >= 12 else dt
            title = telegram_escape(clean_html(n.get("title", ""))[:55])
            lines.append(f"  • `{fmt}` {title}")
        lines.append("")

    # ── 토론방 분위기 ──
    if posts:
        sentiment = {"bullish": 0, "bearish": 0, "suspicious": 0, "neutral": 0}
        for p in posts:
            txt = clean_html(p.get("title", "")) + " " + clean_html(p.get("contentSwReplaced", ""))
            sentiment[classify_sentiment(txt)] += 1
        total = len(posts)
        lines.append(f"💬 *토론방 분위기 (오늘 {total}건)*")
        emoji_map = [
            ("bullish", "강세 🟢"),
            ("bearish", "약세 🔴"),
            ("suspicious", "작전의심 🟡"),
            ("neutral", "중립 ⚪"),
        ]
        for key, label_kr in emoji_map:
            n = sentiment[key]
            pct = (n / total * 100) if total > 0 else 0
            bars = int(pct / 10)
            bar = "█" * bars + "░" * (10 - bars)
            lines.append(f"  {label_kr}: {n:>3} `{bar}` {pct:>3.0f}%")
        # 추천수 - 비추 차이 큰 글 3개
        top = sorted(
            posts,
            key=lambda p: p.get("recommendCount", 0) - p.get("notRecommendCount", 0),
            reverse=True,
        )[:3]
        if top and any(p.get("recommendCount", 0) > 0 for p in top):
            lines.append("")
            lines.append("  📌 *인기 글*")
            for p in top:
                t = p.get("writtenAt", "")[11:16]
                title = telegram_escape(clean_html(p.get("title", ""))[:40])
                rec = p.get("recommendCount", 0)
                cc = p.get("commentCount", 0)
                lines.append(f"  • `{t}` 👍{rec} 💬{cc} {title}")
        lines.append("")

    lines.append("───────────")
    lines.append("_네이버 금융 + OpenDART API 종합_")

    msg = "\n".join(lines)
    # 텔레그램 한도 4096
    if len(msg) > 4000:
        msg = msg[:3950] + "\n...(잘림)"
    return msg


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["pre", "post"], required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    msg = build_message(args.mode)
    if args.dry_run:
        print(msg)
        return 0

    ok, info = send_telegram(msg)
    print(f"sent={ok} info={info}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
