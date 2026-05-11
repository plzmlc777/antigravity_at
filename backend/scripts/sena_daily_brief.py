"""세나테크놀로지(061090) 일일 브리프 — 장전(08:30 KST) / 장후(16:30 KST).

데이터 소스:
- 시세/메타: m.stock.naver.com/api/stock/{code}/integration
- 뉴스: m.stock.naver.com/api/news/stock/{code}
- 토론방: stock.naver.com/api/community/discussion/posts/by-item
- 공시: OpenDART list.json (corp_code 01010615)

저장: 모든 브리프는 symbol_briefs 테이블에 누적 저장됨 (전송 성공 여부와 함께).
참조: 과거 30 row (≈15일치 평일)를 로드해 시계열 인사이트(거래량/가격/분위기/뉴스/공시) 산출.

사용:
    python3 backend/scripts/sena_daily_brief.py --mode pre
    python3 backend/scripts/sena_daily_brief.py --mode post --dry-run
"""
import argparse
import os
import sys
import json
import re
import urllib.request
import urllib.parse
import urllib.error
from collections import Counter
from datetime import datetime, timedelta, timezone
from html import unescape

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

NAVER_HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://m.stock.naver.com/"}
NAVER_DISC_HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://stock.naver.com/"}


def now_kst() -> datetime:
    return datetime.now(KST)


def http_get_json(url: str, headers: dict, timeout: int = 12):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


# ── 데이터 수집 ───────────────────────────────────────────────────────────

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
    today = now_kst().strftime("%Y-%m-%d")
    yesterday = (now_kst() - timedelta(days=1)).strftime("%Y-%m-%d")
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
        if last_date < yesterday:
            break
    return [p for p in posts if p.get("writtenAt", "").startswith(today)]


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


# ── 유틸 ──────────────────────────────────────────────────────────────────

def clean_html(s: str) -> str:
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", unescape(s)).strip()


def parse_number(s) -> float:
    """'57,000' → 57000.0  / '1,002,137' → 1002137.0  / '15.01배' → 15.01  /
    '49,931백만' → 49931000000  / '2,748억' → 274800000000  / '1.04%' → 1.04
    파싱 실패 시 0 반환."""
    if isinstance(s, (int, float)):
        return float(s)
    if not s:
        return 0.0
    t = str(s).replace(",", "").strip()
    # 한국 단위 처리
    mult = 1
    if t.endswith("백만"):
        t = t[:-2]; mult = 1_000_000
    elif t.endswith("억"):
        t = t[:-1]; mult = 100_000_000
    elif t.endswith("만"):
        t = t[:-1]; mult = 10_000
    elif t.endswith("조"):
        t = t[:-1]; mult = 1_000_000_000_000
    # 후행 단위 제거
    t = re.sub(r"[^\d\.\-]", "", t)
    try:
        return float(t) * mult
    except Exception:
        return 0.0


def classify_sentiment(text: str) -> str:
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
        "조작", "장난질", "찌라시",
    ]
    b = sum(1 for k in bullish_kw if k in text)
    s = sum(1 for k in bearish_kw if k in text)
    sp = sum(1 for k in suspicious_kw if k in text)
    if sp >= 2:
        return "suspicious"
    if b > s + 1:
        return "bullish"
    if s > b + 1:
        return "bearish"
    return "neutral"


def compute_sentiment(posts: list) -> dict:
    stats = {"bullish": 0, "bearish": 0, "suspicious": 0, "neutral": 0}
    for p in posts:
        text = clean_html(p.get("title", "")) + " " + clean_html(p.get("contentSwReplaced", ""))
        stats[classify_sentiment(text)] += 1
    stats["total"] = sum(stats.values())
    return stats


def telegram_escape(s: str) -> str:
    for ch in ("*", "_", "`", "["):
        s = s.replace(ch, "\\" + ch)
    return s


# ── DB 저장 / 로드 ────────────────────────────────────────────────────────

def _get_engine():
    from app.db.session import engine
    return engine


def load_recent_briefs(limit: int = 30) -> list:
    """최신순. 실패 시 [] 반환."""
    try:
        from sqlalchemy import text
        engine = _get_engine()
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT generated_at, mode, quote, news, market_news,
                       discussion_stats, discussion_top, disclosures, insights
                FROM symbol_briefs
                WHERE symbol = :s
                ORDER BY generated_at DESC
                LIMIT :n
            """), {"s": SYMBOL, "n": limit}).fetchall()
        return [dict(r._mapping) for r in rows]
    except Exception as e:
        sys.stderr.write(f"[WARN] load_recent_briefs: {type(e).__name__}: {e}\n")
        return []


def save_brief(data: dict, message: str, sent: bool) -> bool:
    try:
        from sqlalchemy import text
        engine = _get_engine()
        with engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO symbol_briefs (
                    generated_at, mode, symbol,
                    quote, news, market_news,
                    discussion_stats, discussion_top, disclosures, insights,
                    raw_message, telegram_sent
                ) VALUES (
                    :gen_at, :mode, :symbol,
                    CAST(:quote AS jsonb), CAST(:news AS jsonb), CAST(:mn AS jsonb),
                    CAST(:ds AS jsonb), CAST(:dt AS jsonb), CAST(:dc AS jsonb), CAST(:ins AS jsonb),
                    :msg, :sent
                )
            """), {
                "gen_at": data["generated_at"],
                "mode": data["mode"],
                "symbol": SYMBOL,
                "quote": json.dumps(data["quote"], ensure_ascii=False),
                "news": json.dumps(data["news"], ensure_ascii=False),
                "mn": json.dumps(data["market_news"], ensure_ascii=False),
                "ds": json.dumps(data["sentiment"], ensure_ascii=False),
                "dt": json.dumps(data["top_posts"], ensure_ascii=False),
                "dc": json.dumps(data["disclosures"], ensure_ascii=False),
                "ins": json.dumps(data["insights"], ensure_ascii=False),
                "msg": message,
                "sent": sent,
            })
            conn.commit()
        return True
    except Exception as e:
        sys.stderr.write(f"[WARN] save_brief: {type(e).__name__}: {e}\n")
        return False


# ── 인사이트 산출 ─────────────────────────────────────────────────────────

def compute_insights(current: dict, history: list) -> list:
    """current/history 비교 → 의미있는 시그널 문자열 리스트."""
    insights = []
    if not history:
        insights.append("🆕 최초 데이터 수집 — 시계열 비교는 다음 회차부터")
        return insights

    quote = current["quote"]
    cur_vol = parse_number(quote.get("거래량"))
    cur_open = parse_number(quote.get("시가"))
    cur_high = parse_number(quote.get("고가"))
    cur_low = parse_number(quote.get("저가"))
    cur_prev_close = parse_number(quote.get("전일"))

    # 거래량 추이 — 최근 10 row 평균 대비
    hist_vols = []
    for h in history[:10]:
        q = h.get("quote") or {}
        v = parse_number(q.get("거래량"))
        if v > 0:
            hist_vols.append(v)
    if cur_vol > 0 and hist_vols:
        avg = sum(hist_vols) / len(hist_vols)
        if avg > 0:
            ratio = cur_vol / avg
            if ratio >= 3:
                insights.append(f"📈 거래량 *{ratio:.1f}배* 폭증 (vs 최근 {len(hist_vols)}회 평균 {avg/10000:.1f}만주)")
            elif ratio <= 0.3:
                insights.append(f"📉 거래량 *{ratio*100:.0f}%* 급감 (평소 {avg/10000:.1f}만주 → 오늘 {cur_vol/10000:.1f}만주)")

    # 가격 갭 — 시가 vs 전일 종가
    if cur_open > 0 and cur_prev_close > 0:
        gap_pct = (cur_open / cur_prev_close - 1) * 100
        if abs(gap_pct) >= 3:
            arrow = "↑" if gap_pct > 0 else "↓"
            insights.append(f"🎯 갭{arrow} *{gap_pct:+.1f}%* (전일 {int(cur_prev_close):,} → 시가 {int(cur_open):,})")

    # 장중 변동폭
    if cur_high > 0 and cur_low > 0 and cur_prev_close > 0:
        range_pct = (cur_high - cur_low) / cur_prev_close * 100
        if range_pct >= 8:
            insights.append(f"🌪 일중 변동폭 *{range_pct:.1f}%* (저 {int(cur_low):,} ~ 고 {int(cur_high):,})")

    # 토론방 분위기 변화 — 같은 mode의 직전 brief 비교
    cur_stats = current["sentiment"]
    cur_total = cur_stats.get("total", 0) or 1
    prev_same_mode = next((h for h in history if h["mode"] == current["mode"]), None)
    if prev_same_mode:
        prev_stats = prev_same_mode.get("discussion_stats") or {}
        prev_total = prev_stats.get("total", 0) or 1
        for key, label_kr in (("bullish", "강세"), ("bearish", "약세"), ("suspicious", "작전의심")):
            cur_pct = cur_stats.get(key, 0) / cur_total * 100
            prev_pct = prev_stats.get(key, 0) / prev_total * 100
            delta = cur_pct - prev_pct
            if abs(delta) >= 15:
                arrow = "↗" if delta > 0 else "↘"
                insights.append(f"💬 {label_kr} 비율 {arrow} *{prev_pct:.0f}% → {cur_pct:.0f}%* ({delta:+.0f}p)")

    # 뉴스 발생 빈도
    cur_news_n = len(current["news"])
    prev_news_counts = [len(h.get("news") or []) for h in history[:5]]
    if prev_news_counts:
        prev_avg = sum(prev_news_counts) / len(prev_news_counts)
        if cur_news_n >= prev_avg + 3 and cur_news_n >= 5:
            insights.append(f"📰 뉴스 보도 급증: 평소 {prev_avg:.0f}건 → 오늘 *{cur_news_n}건*")
        elif cur_news_n == 0 and prev_avg >= 2:
            insights.append(f"🔇 오늘 종목 뉴스 0건 (평소 {prev_avg:.0f}건)")

    # 신규 공시 감지 — 직전 brief의 공시 ID와 비교
    prev_disc_ids = set()
    if history and history[0].get("disclosures"):
        prev_disc_ids = {d.get("rcept_no") for d in (history[0]["disclosures"] or [])}
    cur_disc = current["disclosures"]
    cur_disc_ids = {d.get("rcept_no") for d in cur_disc}
    new_ids = cur_disc_ids - prev_disc_ids
    if new_ids and prev_disc_ids:
        new_disc_titles = [d.get("report_nm", "")[:40] for d in cur_disc if d.get("rcept_no") in new_ids]
        joined = " | ".join(t.strip() for t in new_disc_titles[:3])
        insights.append(f"📋 *신규 공시 {len(new_ids)}건*: {joined}")

    # 동일 매체 반복 보도 패턴
    cur_offices = [n.get("officeName", "") for n in current["news"] if n.get("officeName")]
    if cur_offices:
        c = Counter(cur_offices)
        top = c.most_common(1)[0]
        if top[1] >= 3:
            insights.append(f"🔁 매체 집중: '{top[0]}'에서 *{top[1]}건* (셀-사이드 펌프 패턴 주의)")

    if not insights:
        insights.append("➖ 평소와 큰 차이 없음")
    return insights


# ── 메시지 빌드 ───────────────────────────────────────────────────────────

def fetch_all_data(mode: str) -> dict:
    ts = now_kst()
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

    # 토론방 추천수 정렬해서 인기 글 3
    top_posts_raw = sorted(
        posts,
        key=lambda p: p.get("recommendCount", 0) - p.get("notRecommendCount", 0),
        reverse=True,
    )[:3]
    top_posts = [{
        "writtenAt": p.get("writtenAt", ""),
        "nickname": (p.get("writer") or {}).get("nickname", ""),
        "title": clean_html(p.get("title", "")),
        "recommendCount": p.get("recommendCount", 0),
        "commentCount": p.get("commentCount", 0),
    } for p in top_posts_raw]

    sentiment = compute_sentiment(posts)

    return {
        "generated_at": ts,
        "mode": mode,
        "quote": quote,
        "news": news,
        "market_news": market_news,
        "discussion_count": len(posts),
        "sentiment": sentiment,
        "top_posts": top_posts,
        "disclosures": disclosures,
        "insights": [],  # 채워질 자리
    }


def build_message(data: dict) -> str:
    ts = data["generated_at"]
    mode = data["mode"]
    quote = data["quote"]
    insights = data["insights"]
    is_pre = (mode == "pre")
    icon = "🌅" if is_pre else "🌆"
    label = "장 시작 전 브리프" if is_pre else "장 마감 브리프"

    lines = []
    lines.append(f"{icon} *{SYMBOL_NAME}({SYMBOL}) {label}*")
    lines.append(f"_{ts.strftime('%Y-%m-%d %H:%M KST')}_")
    lines.append("")

    # 추이 신호 (인사이트) — 가장 위에 배치
    if insights:
        lines.append("📈 *추이 신호*")
        for ins in insights:
            lines.append(f"  • {ins}")
        lines.append("")

    # 시세
    lines.append("📊 *시세*")
    if "_err" in quote:
        lines.append(f"  (조회 실패: {quote['_err'][:60]})")
    else:
        for k in ("전일", "시가", "고가", "저가", "거래량", "대금", "시총", "외인소진율", "PER", "PBR"):
            if k in quote:
                lines.append(f"  {k}: `{quote[k]}`")
    lines.append("")

    # 공시
    if data["disclosures"]:
        lines.append(f"📋 *DART 공시 (최근 7일, {len(data['disclosures'])}건)*")
        for d in data["disclosures"][:6]:
            dt = d.get("rcept_dt", "")
            fmt = f"{dt[:4]}-{dt[4:6]}-{dt[6:8]}" if len(dt) == 8 else dt
            nm = telegram_escape(d.get("report_nm", "").strip()[:60])
            lines.append(f"  • {fmt}  {nm}")
        lines.append("")

    # 종목 뉴스
    if data["news"]:
        lines.append(f"📰 *종목 뉴스 (최근 24h, {len(data['news'])}건)*")
        for n in data["news"][:8]:
            dt = n.get("datetime", "")
            fmt = f"{dt[4:6]}/{dt[6:8]} {dt[8:10]}:{dt[10:12]}" if len(dt) >= 12 else dt
            title = telegram_escape(clean_html(n.get("title", ""))[:60])
            office = telegram_escape(n.get("officeName", "")[:10])
            lines.append(f"  • `{fmt}` ({office}) {title}")
        lines.append("")

    # 시장 헤드라인
    if data["market_news"]:
        lines.append("🌐 *KOSDAQ 헤드라인 (Top 5)*")
        for n in data["market_news"]:
            dt = n.get("datetime", "")
            fmt = f"{dt[8:10]}:{dt[10:12]}" if len(dt) >= 12 else dt
            title = telegram_escape(clean_html(n.get("title", ""))[:55])
            lines.append(f"  • `{fmt}` {title}")
        lines.append("")

    # 토론방 분위기
    sentiment = data["sentiment"]
    total = sentiment.get("total", 0)
    if total > 0:
        lines.append(f"💬 *토론방 분위기 (오늘 {total}건)*")
        for key, label_kr in (
            ("bullish", "강세 🟢"),
            ("bearish", "약세 🔴"),
            ("suspicious", "작전의심 🟡"),
            ("neutral", "중립 ⚪"),
        ):
            n = sentiment.get(key, 0)
            pct = n / total * 100
            bars = int(pct / 10)
            bar = "█" * bars + "░" * (10 - bars)
            lines.append(f"  {label_kr}: {n:>3} `{bar}` {pct:>3.0f}%")
        if data["top_posts"] and any(p["recommendCount"] > 0 for p in data["top_posts"]):
            lines.append("")
            lines.append("  📌 *인기 글*")
            for p in data["top_posts"]:
                t = p["writtenAt"][11:16] if len(p["writtenAt"]) >= 16 else p["writtenAt"]
                title = telegram_escape(p["title"][:40])
                lines.append(f"  • `{t}` 👍{p['recommendCount']} 💬{p['commentCount']} {title}")
        lines.append("")

    lines.append("───────────")
    lines.append("_네이버 + OpenDART + 누적 시계열 분석_")

    msg = "\n".join(lines)
    if len(msg) > 4000:
        msg = msg[:3950] + "\n...(잘림)"
    return msg


def serialize_data_for_db(data: dict) -> dict:
    """generated_at은 ISO 문자열, datetime → str."""
    out = dict(data)
    out["generated_at"] = data["generated_at"].isoformat()
    return out


def send_telegram(text: str):
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["pre", "post"], required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-save", action="store_true", help="DB 저장 생략")
    args = parser.parse_args()

    data = fetch_all_data(args.mode)
    history = load_recent_briefs(limit=30)
    data["insights"] = compute_insights(data, history)

    msg = build_message(data)

    if args.dry_run:
        print(msg)
        return 0

    ok, info = send_telegram(msg)
    saved = False
    if not args.no_save:
        saved = save_brief(serialize_data_for_db(data), msg, ok)

    print(f"sent={ok} info={info} saved={saved} insights={len(data['insights'])}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
