"""세나테크놀로지(061090) 일일 브리프 — 장 시작 전(08:30 KST) 단일 발송.

세나 단일 종목에 집중한 소형주 분석 브리프. KOSDAQ 시장 헤드라인 등
종목과 무관한 노이즈는 제외하고, 거래량/거래대금/수급/변동성 등
소형주 특성과 토론방의 생생한 분위기에 초점을 맞춘다.

데이터 소스:
- 시세/밸류에이션/수급: m.stock.naver.com/api/stock/{code}/integration
    (totalInfos = 밸류에이션 스냅샷, dealTrendInfos = 일자별 종가/거래량/외인·기관·개인 순매수)
- 뉴스: m.stock.naver.com/api/news/stock/{code}
- 토론방: stock.naver.com/api/community/discussion/posts/by-item (postType=normal만)
- 공시: OpenDART list.json (corp_code 01010615)

저장: symbol_briefs 테이블에 누적 (전송 성공 여부 포함). 과거 30 row 로드해
      시계열 인사이트(분위기/뉴스/공시) 산출.

사용:
    python3 backend/scripts/sena_daily_brief.py --mode pre
    python3 backend/scripts/sena_daily_brief.py --mode pre --dry-run
"""
import argparse
import os
import sys
import json
import re
import math
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

SENTIMENT_EMOJI = {"bullish": "🟢", "bearish": "🔴", "suspicious": "🟡", "neutral": "⚪"}


def now_kst() -> datetime:
    return datetime.now(KST)


def http_get_json(url: str, headers: dict, timeout: int = 12):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


# ── 데이터 수집 ───────────────────────────────────────────────────────────

def fetch_integration() -> tuple:
    """integration 1회 호출 → (quote dict, deal_trend list).
    quote = totalInfos 밸류에이션 스냅샷. deal_trend = 일자별 종가/거래량/수급 (최신순)."""
    url = f"https://m.stock.naver.com/api/stock/{SYMBOL}/integration"
    d = http_get_json(url, NAVER_HEADERS)
    quote = {t["key"]: t["value"] for t in d.get("totalInfos", [])}
    quote["_stockName"] = d.get("stockName", SYMBOL_NAME)

    deal_trend = []
    for it in d.get("dealTrendInfos", []):
        deal_trend.append({
            "date": it.get("bizdate", ""),
            "close": parse_number(it.get("closePrice")),
            "change": parse_number(it.get("compareToPreviousClosePrice")),
            "dir": (it.get("compareToPreviousPrice") or {}).get("text", ""),
            "vol": parse_number(it.get("accumulatedTradingVolume")),
            "foreign": parse_number(it.get("foreignerPureBuyQuant")),
            "organ": parse_number(it.get("organPureBuyQuant")),
            "indiv": parse_number(it.get("individualPureBuyQuant")),
            "foreign_ratio": it.get("foreignerHoldRatio", ""),
        })
    return quote, deal_trend


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


def fetch_discussion_today() -> list:
    """오늘 작성된 '일반' 토론글만 (postType=normal). itemNewsPrice 자동 시세뉴스 제외."""
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
    return [
        p for p in posts
        if p.get("writtenAt", "").startswith(today) and p.get("postType") == "normal"
    ]


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
    """'57,000'→57000  '+5,689'→5689  '-6,722'→-6722  '15.01배'→15.01
    '49,931백만'→49931000000  '2,748억'→274800000000  '1.04%'→1.04. 실패 시 0."""
    if isinstance(s, (int, float)):
        return float(s)
    if not s:
        return 0.0
    t = str(s).replace(",", "").strip()
    mult = 1
    if t.endswith("백만"):
        t = t[:-2]; mult = 1_000_000
    elif t.endswith("억"):
        t = t[:-1]; mult = 100_000_000
    elif t.endswith("만"):
        t = t[:-1]; mult = 10_000
    elif t.endswith("조"):
        t = t[:-1]; mult = 1_000_000_000_000
    t = re.sub(r"[^\d\.\-]", "", t)
    try:
        return float(t) * mult
    except Exception:
        return 0.0


def fmt_eok(won: float) -> str:
    """원 → '약 14.9억' / '약 1,203억'."""
    eok = won / 1e8
    if eok >= 100:
        return f"약 {eok:,.0f}억"
    return f"약 {eok:.1f}억"


def fmt_qty(q: float) -> str:
    """순매수 수량 → 부호 포함. 만주 이상은 만주 단위."""
    sign = "+" if q > 0 else ("-" if q < 0 else "±")
    a = abs(q)
    if a >= 10000:
        return f"{sign}{a/10000:.1f}만"
    return f"{sign}{int(a):,}"


def classify_sentiment(text: str) -> str:
    bullish_kw = [
        "상한가", "상승", "갑니다", "간다", "매수", "팟팅", "존버", "매집",
        "신고가", "돌파", "대장주", "호재", "급등", "랠리", "유망", "기대",
        "담는다", "담고", "가즈아", "가자", "오른다",
    ]
    bearish_kw = [
        "손절", "매도", "하락", "폭락", "청산", "탈출", "잡주",
        "물렸", "물림", "지하실", "마이너스", "사기", "환장", "지긋지긋",
        "던지", "던짐", "거품", "고평가", "떨어",
    ]
    suspicious_kw = [
        "세력", "작전", "기법", "허매수", "리딩방", "털기", "뻥튀기", "의심",
        "조작", "장난질", "찌라시", "주포", "설거지",
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
                # market_news 컬럼은 수급(deal_trend) 보관용으로 재활용
                "mn": json.dumps(data["deal_trend"], ensure_ascii=False),
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


# ── 소형주 진단 ───────────────────────────────────────────────────────────

def compute_smallcap(quote: dict, deal_trend: list) -> dict:
    """거래대금·거래량 배수·변동성·52주 위치 등 소형주 핵심 지표."""
    diag = {}
    if not deal_trend:
        return diag
    latest = deal_trend[0]
    close = latest["close"]
    vol = latest["vol"]

    # 거래대금 (종가 × 거래량) — 소형주 유동성 핵심
    if close > 0 and vol > 0:
        value = close * vol
        diag["value_won"] = value
        if value < 10e8:
            diag["liq_flag"] = f"🩸 거래대금 빈약 ({fmt_eok(value)}) — 체결 슬리피지·갭 위험 큼"
        elif value < 30e8:
            diag["liq_flag"] = f"⚠️ 거래대금 얕음 ({fmt_eok(value)}) — 대량주문 시 가격충격 주의"
        elif value < 100e8:
            diag["liq_flag"] = f"거래대금 보통 ({fmt_eok(value)})"
        else:
            diag["liq_flag"] = f"🔥 거래대금 활발 ({fmt_eok(value)})"

    # 거래량 배수 — 직전일 vs 이전 10거래일 평균
    prior_vols = [d["vol"] for d in deal_trend[1:11] if d["vol"] > 0]
    if vol > 0 and prior_vols:
        avg = sum(prior_vols) / len(prior_vols)
        if avg > 0:
            diag["vol_ratio"] = vol / avg
            diag["vol_avg"] = avg

    # 일간 변동성 — 최근 일별 종가 등락률 표준편차
    closes = [d["close"] for d in deal_trend if d["close"] > 0]
    rets = []
    for i in range(len(closes) - 1):
        if closes[i + 1] > 0:
            rets.append((closes[i] / closes[i + 1] - 1) * 100)
    if len(rets) >= 3:
        mean = sum(rets) / len(rets)
        var = sum((r - mean) ** 2 for r in rets) / len(rets)
        diag["daily_vol"] = math.sqrt(var)
        diag["vol_days"] = len(rets)

    # 52주 위치
    hi = parse_number(quote.get("52주 최고"))
    lo = parse_number(quote.get("52주 최저"))
    if close > 0 and hi > 0:
        diag["from_high"] = (close / hi - 1) * 100
    if close > 0 and lo > 0:
        diag["from_low"] = (close / lo - 1) * 100
    diag["hi52"] = hi
    diag["lo52"] = lo

    # 최근 5거래일 누적 등락
    if len(closes) >= 2:
        n = min(5, len(closes) - 1)
        if closes[n] > 0:
            diag["ret_5d"] = (closes[0] / closes[n] - 1) * 100
            diag["ret_5d_n"] = n

    diag["latest_close"] = close
    diag["latest_change"] = latest["change"]
    diag["latest_date"] = latest["date"]
    diag["latest_vol"] = vol
    return diag


def _streak(deal_trend: list, key: str) -> tuple:
    """최신일부터 동일 부호 연속 일수 + 누적 수량. (sign, days, cum) 반환."""
    if not deal_trend:
        return (0, 0, 0.0)
    first = deal_trend[0][key]
    sign = 1 if first > 0 else (-1 if first < 0 else 0)
    if sign == 0:
        return (0, 0, 0.0)
    days = 0
    cum = 0.0
    for d in deal_trend:
        v = d[key]
        if (v > 0 and sign > 0) or (v < 0 and sign < 0):
            days += 1
            cum += v
        else:
            break
    return (sign, days, cum)


def compute_supply_insights(deal_trend: list) -> list:
    """수급 스트릭 시그널 (외국인/기관/개인 연속 순매수·순매도)."""
    out = []
    for key, who in (("foreign", "외국인"), ("organ", "기관"), ("indiv", "개인")):
        sign, days, cum = _streak(deal_trend, key)
        if days >= 3:
            verb = "순매수" if sign > 0 else "순매도"
            arrow = "📥" if sign > 0 else "📤"
            out.append(f"{arrow} {who} *{days}일 연속 {verb}* (누적 {fmt_qty(cum)}주)")
    # 외인보유율 추이
    if len(deal_trend) >= 5:
        cur = parse_number(deal_trend[0].get("foreign_ratio"))
        old = parse_number(deal_trend[4].get("foreign_ratio"))
        if cur > 0 and old > 0:
            delta = cur - old
            if abs(delta) >= 0.15:
                arrow = "↗" if delta > 0 else "↘"
                out.append(f"🌐 외인보유율 {arrow} *{old:.2f}% → {cur:.2f}%* (5일 {delta:+.2f}p)")
    return out


# ── 인사이트 산출 (DB 시계열) ─────────────────────────────────────────────

def compute_insights(current: dict, history: list) -> list:
    """과거 brief 대비 분위기/뉴스/공시 시계열 시그널."""
    insights = []
    if not history:
        insights.append("🆕 최초 데이터 수집 — 시계열 비교는 다음 회차부터")
        return insights

    # 토론방 분위기 변화 — 같은 mode 직전 brief 비교
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

    # 토론방 활동량 급증
    cur_disc_n = current["sentiment"].get("total", 0)
    prev_disc_counts = [
        (h.get("discussion_stats") or {}).get("total", 0) for h in history[:5]
    ]
    prev_disc_counts = [c for c in prev_disc_counts if c]
    if cur_disc_n and prev_disc_counts:
        avg = sum(prev_disc_counts) / len(prev_disc_counts)
        if avg > 0 and cur_disc_n >= avg * 2 and cur_disc_n >= 10:
            insights.append(f"🔥 토론방 활동 *{cur_disc_n/avg:.1f}배* 급증 (평소 {avg:.0f}건 → 오늘 {cur_disc_n}건)")

    # 뉴스 발생 빈도
    cur_news_n = len(current["news"])
    prev_news_counts = [len(h.get("news") or []) for h in history[:5]]
    if prev_news_counts:
        prev_avg = sum(prev_news_counts) / len(prev_news_counts)
        if cur_news_n >= prev_avg + 3 and cur_news_n >= 5:
            insights.append(f"📰 뉴스 보도 급증: 평소 {prev_avg:.0f}건 → 오늘 *{cur_news_n}건*")
        elif cur_news_n == 0 and prev_avg >= 2:
            insights.append(f"🔇 오늘 종목 뉴스 0건 (평소 {prev_avg:.0f}건)")

    # 신규 공시 감지
    prev_disc_ids = set()
    if history and history[0].get("disclosures"):
        prev_disc_ids = {d.get("rcept_no") for d in (history[0]["disclosures"] or [])}
    cur_disc = current["disclosures"]
    cur_disc_ids = {d.get("rcept_no") for d in cur_disc}
    new_ids = cur_disc_ids - prev_disc_ids
    if new_ids and prev_disc_ids:
        new_titles = [d.get("report_nm", "")[:40] for d in cur_disc if d.get("rcept_no") in new_ids]
        joined = " | ".join(t.strip() for t in new_titles[:3])
        insights.append(f"📋 *신규 공시 {len(new_ids)}건*: {joined}")

    # 동일 매체 반복 보도
    cur_offices = [n.get("officeName", "") for n in current["news"] if n.get("officeName")]
    if cur_offices:
        c = Counter(cur_offices)
        top = c.most_common(1)[0]
        if top[1] >= 3:
            insights.append(f"🔁 매체 집중: '{top[0]}'에서 *{top[1]}건* (셀-사이드 펌프 패턴 주의)")

    return insights


# ── 메시지 빌드 ───────────────────────────────────────────────────────────

def fetch_all_data(mode: str) -> dict:
    ts = now_kst()
    quote, deal_trend = {}, []
    try:
        quote, deal_trend = fetch_integration()
    except Exception as e:
        quote = {"_err": str(e)}
    news = []
    try:
        news = fetch_news(since_hours=24)
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

    # 대표 글 — 참여도(추천-비추천, 댓글) 우선, 동률이면 최신
    def engagement(p):
        return (
            p.get("recommendCount", 0) - p.get("notRecommendCount", 0),
            p.get("commentCount", 0),
            p.get("writtenAt", ""),
        )
    top_posts_raw = sorted(posts, key=engagement, reverse=True)[:3]
    top_posts = []
    for p in top_posts_raw:
        title = clean_html(p.get("title", ""))
        content = clean_html(p.get("contentSwReplaced", ""))
        top_posts.append({
            "writtenAt": p.get("writtenAt", ""),
            "title": title,
            "content": content,
            "recommendCount": p.get("recommendCount", 0),
            "notRecommendCount": p.get("notRecommendCount", 0),
            "commentCount": p.get("commentCount", 0),
            "holder": bool(p.get("isHolderVerified")),
            "sentiment": classify_sentiment(title + " " + content),
        })

    sentiment = compute_sentiment(posts)
    holder_n = sum(1 for p in posts if p.get("isHolderVerified"))

    return {
        "generated_at": ts,
        "mode": mode,
        "quote": quote,
        "deal_trend": deal_trend,
        "news": news,
        "discussion_count": len(posts),
        "sentiment": sentiment,
        "holder_n": holder_n,
        "top_posts": top_posts,
        "disclosures": disclosures,
        "smallcap": {},
        "insights": [],
    }


def build_message(data: dict) -> str:
    ts = data["generated_at"]
    quote = data["quote"]
    deal_trend = data["deal_trend"]
    diag = data["smallcap"]
    insights = data["insights"]

    lines = []
    lines.append(f"🌅 *{SYMBOL_NAME}({SYMBOL}) 장 시작 전 브리프*")
    lines.append(f"_{ts.strftime('%Y-%m-%d %H:%M KST')}_")
    lines.append("")

    if "_err" in quote:
        lines.append(f"⚠️ 시세 조회 실패: {quote['_err'][:80]}")
        lines.append("")

    # ── 직전 거래일 + 소형주 진단 ──
    if diag:
        d = diag.get("latest_date", "")
        dlabel = f"{d[4:6]}/{d[6:8]}" if len(d) == 8 else d
        close = diag.get("latest_close", 0)
        chg = diag.get("latest_change", 0)
        prev = close - chg
        chg_pct = (chg / prev * 100) if prev else 0
        sign = "🔺" if chg > 0 else ("🔻" if chg < 0 else "➖")
        lines.append(f"📊 *직전 거래일 ({dlabel})*")
        lines.append(f"  종가 `{int(close):,}` {sign} {chg:+,.0f} ({chg_pct:+.1f}%)")
        if "ret_5d" in diag:
            lines.append(f"  최근 {diag['ret_5d_n']}거래일 누적 `{diag['ret_5d']:+.1f}%`")
        lines.append("")

        lines.append("🔬 *세나 거래 진단*")
        if diag.get("liq_flag"):
            vol = diag.get("latest_vol", 0)
            lines.append(f"  • {diag['liq_flag']}")
            lines.append(f"     거래량 {int(vol):,}주")
        if "vol_ratio" in diag:
            r = diag["vol_ratio"]
            tag = "🚨 폭증" if r >= 3 else ("📈 증가" if r >= 1.5 else ("📉 위축" if r <= 0.5 else "보통"))
            lines.append(f"  • 거래량 평소 대비 *{r:.1f}배* {tag} (이전 10일 평균 {diag['vol_avg']/10000:.1f}만주)")
        if "daily_vol" in diag:
            dv = diag["daily_vol"]
            tag = "초고변동" if dv >= 7 else ("고변동" if dv >= 4 else "보통")
            lines.append(f"  • 일간 변동성 *{dv:.1f}%* ({diag['vol_days']}일 표준편차, {tag})")
        if "from_high" in diag:
            extra = f" / 저점 {diag['from_low']:+.0f}%" if "from_low" in diag else ""
            lines.append(f"  • 52주 고점 대비 *{diag['from_high']:+.0f}%*{extra}")
            lines.append(f"     (52주 {int(diag['hi52']):,} ~ {int(diag['lo52']):,})")
        lines.append("")

    # ── 밸류에이션 스냅샷 ──
    if "_err" not in quote and quote:
        snap = []
        for k in ("시총", "PER", "PBR", "외인소진율"):
            if k in quote:
                snap.append(f"{k} `{quote[k]}`")
        if snap:
            lines.append("💵 *밸류에이션* — " + " · ".join(snap))
            lines.append("")

    # ── 수급 (외인/기관/개인) ──
    if deal_trend:
        lines.append("💰 *수급 (외국인/기관/개인 순매수, 주)*")
        for d in deal_trend[:5]:
            dt = d["date"]
            dlabel = f"{dt[4:6]}/{dt[6:8]}" if len(dt) == 8 else dt
            lines.append(
                f"  `{dlabel}` 외 {fmt_qty(d['foreign']):>7} · 기 {fmt_qty(d['organ']):>7} · 개 {fmt_qty(d['indiv']):>7}"
            )
        lines.append("")

    # ── 추이 신호 ──
    if insights:
        lines.append("📈 *추이 신호*")
        for ins in insights:
            lines.append(f"  • {ins}")
        lines.append("")

    # ── DART 공시 ──
    if data["disclosures"]:
        lines.append(f"📋 *DART 공시 (최근 7일, {len(data['disclosures'])}건)*")
        for d in data["disclosures"][:6]:
            dt = d.get("rcept_dt", "")
            fmt = f"{dt[:4]}-{dt[4:6]}-{dt[6:8]}" if len(dt) == 8 else dt
            nm = telegram_escape(d.get("report_nm", "").strip()[:60])
            lines.append(f"  • {fmt}  {nm}")
        lines.append("")

    # ── 종목 뉴스 ──
    if data["news"]:
        lines.append(f"📰 *종목 뉴스 (최근 24h, {len(data['news'])}건)*")
        for n in data["news"][:6]:
            dt = n.get("datetime", "")
            fmt = f"{dt[4:6]}/{dt[6:8]} {dt[8:10]}:{dt[10:12]}" if len(dt) >= 12 else dt
            title = telegram_escape(clean_html(n.get("title", ""))[:55])
            office = telegram_escape(n.get("officeName", "")[:10])
            lines.append(f"  • `{fmt}` ({office}) {title}")
        lines.append("")

    # ── 토론방 (생생하게) ──
    sentiment = data["sentiment"]
    total = sentiment.get("total", 0)
    if total > 0:
        holder_n = data.get("holder_n", 0)
        lines.append(f"💬 *토론방 — 오늘 {total}건* (보유자인증 {holder_n}명)")

        # 한 줄 분위기 요약
        bull = sentiment.get("bullish", 0)
        bear = sentiment.get("bearish", 0)
        susp = sentiment.get("suspicious", 0)
        if bear + susp > bull:
            mood = "🔴 약세·회의론 우세"
        elif bull > bear + susp:
            mood = "🟢 매수심리 우세"
        else:
            mood = "⚪ 관망·혼조"
        if susp >= max(1, int(total * 0.2)):
            mood += " · ⚠️작전/세력 경계감"
        lines.append(f"  {mood}")

        # 분위기 막대
        for key, label_kr in (("bullish", "강세 🟢"), ("bearish", "약세 🔴"),
                              ("suspicious", "작전의심 🟡"), ("neutral", "중립 ⚪")):
            n = sentiment.get(key, 0)
            pct = n / total * 100
            bars = int(pct / 10)
            bar = "█" * bars + "░" * (10 - bars)
            lines.append(f"  {label_kr}: {n:>3} `{bar}` {pct:>3.0f}%")

        # 대표 글 — 본문 인용
        if data["top_posts"]:
            lines.append("")
            lines.append("  🗣 *대표 글*")
            for p in data["top_posts"]:
                t = p["writtenAt"][11:16] if len(p["writtenAt"]) >= 16 else p["writtenAt"]
                emoji = SENTIMENT_EMOJI.get(p["sentiment"], "⚪")
                badge = "✅" if p["holder"] else ""
                react = ""
                if p["recommendCount"] or p["commentCount"]:
                    react = f" 👍{p['recommendCount']} 💬{p['commentCount']}"
                title = telegram_escape(p["title"][:32])
                lines.append(f"  {emoji} `{t}`{badge}{react} *{title}*")
                snippet = telegram_escape(p["content"][:55])
                if snippet:
                    lines.append(f"     “{snippet}…”")
        lines.append("")

    lines.append("───────────")
    lines.append("_네이버 시세·수급·토론방 + OpenDART 공시 분석_")

    msg = "\n".join(lines)
    if len(msg) > 4000:
        msg = msg[:3950] + "\n...(잘림)"
    return msg


def serialize_data_for_db(data: dict) -> dict:
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
    parser.add_argument("--mode", choices=["pre", "post"], default="pre")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-save", action="store_true", help="DB 저장 생략")
    args = parser.parse_args()

    data = fetch_all_data(args.mode)
    data["smallcap"] = compute_smallcap(data["quote"], data["deal_trend"])
    history = load_recent_briefs(limit=30)
    data["insights"] = compute_insights(data, history) + compute_supply_insights(data["deal_trend"])

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
