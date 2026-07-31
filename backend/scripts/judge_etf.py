"""Daily rule-based directional judgment for KOSPI200 ETFs, from dashboard indicators.
- Live mode: computes today's pre-market judgment ONLY on trading days (휴장 -> skip, mark 휴장).
- Backfill: `judge_etf.py --date YYYY-MM-DD` computes that date's 08:00 pre-market judgment
  using data strictly BEFORE that date (prior close). Stored in SQLite keyed by for_date.
Writes: today_market.json (current status, always) + etf_judgment.json (latest judgment)
        + judgment_dates.json + judgments.db. NOT financial advice (algorithmic reference).
"""
import urllib.request, json, os, sqlite3, sys
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
import pandas as pd

OUTDIR = os.environ.get("DASH_OUTDIR", "/home/hcpark/antigravity/backend/runs/fx")
UA = {"User-Agent": "Mozilla/5.0"}
KST = ZoneInfo("Asia/Seoul")
_WD = ["월", "화", "수", "목", "금", "토", "일"]

# 신호 기본 가중치 (signal_weights.json으로 외부화/튜닝 가능)
BASE_WEIGHTS = {"trend": 1.0, "mom": 1.5, "sox": 1.5, "krsemi": 1.0, "usd": 1.0,
                "deposit": 0.7, "cover": 0.7, "copper": 0.7, "credit": 0.5}
# 가중치 key -> 신호 표시명(signals_review와 조인용)
SIG_KEYS = [("trend", "KODEX200 추세(20일선)"), ("mom", "KODEX200 모멘텀(5일)"),
            ("sox", "반도체 SOX(5일)"), ("krsemi", "삼성·하이닉스(5일)"),
            ("usd", "원/달러(5일)"), ("deposit", "투자자예탁금(5일)"),
            ("cover", "반대매매비중(5일Δ)"), ("copper", "구리(5일)"), ("credit", "신용융자(5일)")]
NAME2KEY = {n: k for k, n in SIG_KEYS}


def load_weight_cfg():
    path = os.path.join(OUTDIR, "signal_weights.json")
    cfg = {"weights": dict(BASE_WEIGHTS), "auto_tune": True, "min_samples": 15, "shrink": 0.5}
    try:
        with open(path, encoding="utf-8") as f:
            user = json.load(f)
        cfg.update({k: v for k, v in user.items() if k in cfg})
        cfg["weights"] = {**BASE_WEIGHTS, **user.get("weights", {})}
    except Exception:
        pass
    return cfg


def signal_hit_rates(results):
    """result 이력에서 신호별 적중/빗나감 집계 -> {표시명: {aligned, missed, n, rate}}."""
    agg = {}
    for r in results:
        for s in r.get("signals_review", []):
            a = agg.setdefault(s["name"], {"aligned": 0, "missed": 0})
            if s["mark"] == "적중":
                a["aligned"] += 1
            elif s["mark"] == "빗나감":
                a["missed"] += 1
    for n, a in agg.items():
        a["n"] = a["aligned"] + a["missed"]
        a["rate"] = round(a["aligned"] / a["n"] * 100, 1) if a["n"] else None
    return agg


def effective_weights(cfg, results):
    """auto_tune 시 신호별 적중률로 가중치 조정(표본 min_samples 이상, shrink로 완충)."""
    base = cfg["weights"]
    rates = signal_hit_rates(results)
    eff = dict(base)
    if cfg.get("auto_tune"):
        for key, name in SIG_KEYS:
            r = rates.get(name)
            if r and r["n"] >= cfg.get("min_samples", 15) and r["rate"] is not None:
                factor = 1 + cfg.get("shrink", 0.5) * (2 * (r["rate"] / 100) - 1)
                eff[key] = round(base[key] * max(0.4, min(1.6, factor)), 3)
    return eff, rates


def is_holiday(d):
    """(is_trading_day, reason) for a date d."""
    wd = d.weekday()
    if wd >= 5:
        return False, "주말"
    try:
        import holidays
        kr = holidays.SouthKorea(years=d.year)
        if d in kr:
            return False, str(kr.get(d))
    except Exception:
        pass
    if (d.month, d.day) == (5, 1):
        return False, "근로자의날"
    if (d.month, d.day) == (12, 31):
        return False, "연말 휴장"
    return True, ""


def today_market():
    now = datetime.now(KST)
    d = now.date()
    trading, reason = is_holiday(d)
    nv_status, last_dt = None, None
    try:
        r = json.loads(urllib.request.urlopen(urllib.request.Request(
            "https://m.stock.naver.com/api/index/KOSPI/basic", headers=UA), timeout=15).read())
        nv_status = r.get("marketStatus")
        last_dt = (r.get("localTradedAt") or "")[:10]
    except Exception:
        pass
    if not trading:
        status = "휴장"
    elif now.hour < 9:
        status = "장전"
    elif (now.hour, now.minute) <= (15, 30) or nv_status == "OPEN":
        status = "장중"
    else:
        status = "장마감"
    return {"date": d.strftime("%Y-%m-%d"), "weekday": _WD[d.weekday()],
            "is_trading_day": trading, "status": status, "reason": reason,
            "naver_status": nv_status, "last_trade_date": last_dt}


def yahoo(ticker, rng="3mo"):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range={rng}&interval=1d"
    d = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=25).read())
    r = d["chart"]["result"][0]
    cl = r["indicators"]["quote"][0]["close"]
    idx = [datetime.utcfromtimestamp(t).date() for t in r["timestamp"]]
    return pd.Series(cl, index=pd.to_datetime(idx)).dropna()


def csv(name):
    return pd.read_csv(os.path.join(OUTDIR, name), index_col=0, parse_dates=True).sort_index()


def chg(s, n=5):
    s = s.dropna()
    return float(s.iloc[-1] / s.iloc[-1 - n] - 1) * 100 if len(s) > n else 0.0


def sig(val, up, dn, w):
    return w if val >= up else (-w if val <= dn else 0.0)


def compute(for_date, fetched_label, W=None):
    """Build a judgment for `for_date` using data strictly before it (prior close). W=신호 가중치."""
    W = W or dict(BASE_WEIGHTS)
    cut = pd.Timestamp(for_date)
    def clip(s):
        return s[s.index < cut]
    ks = clip(yahoo("069500.KS"))
    semis, fx = csv("semis_5y.csv"), csv("fx_krw_5y.csv")
    funds, credit = csv("market_funds_5y.csv"), csv("market_credit_5y.csv")
    com = csv("commodities_daily_5y.csv")
    semis, fx, funds, credit, com = clip(semis), clip(fx), clip(funds), clip(credit), clip(com)

    ks_5d = chg(ks, 5)
    ma20 = float(ks.tail(20).mean())
    sox5 = chg(semis["SOX"], 5)
    kr_semi5 = (chg(semis["삼성전자"], 5) + chg(semis["SK하이닉스"], 5)) / 2
    usd5 = chg(fx["USD/KRW"], 5)
    dep5 = chg(funds["투자자예탁금"], 5)
    cover_d = float(funds["반대매매비중"].dropna().iloc[-1] - funds["반대매매비중"].dropna().iloc[-6])
    cu5 = chg(com["Copper"], 5)
    cr5 = chg(credit["신용융자"], 5)

    S = []
    def add(name, valstr, score):
        S.append({"name": name, "val": valstr, "dir": ("+" if score > 0 else "-" if score < 0 else "0"), "w": round(score, 2)})
    s_trend = 1.0 if ks.iloc[-1] > ma20 else -1.0
    add("KODEX200 추세(20일선)", f"{'상회' if s_trend>0 else '하회'} ({ks.iloc[-1]:,.0f} vs {ma20:,.0f})", s_trend * W["trend"])
    add("KODEX200 모멘텀(5일)", f"{ks_5d:+.1f}%", sig(ks_5d, 0.5, -0.5, W["mom"]))
    add("반도체 SOX(5일)", f"{sox5:+.1f}%", sig(sox5, 1.0, -1.0, W["sox"]))
    add("삼성·하이닉스(5일)", f"{kr_semi5:+.1f}%", sig(kr_semi5, 1.0, -1.0, W["krsemi"]))
    add("원/달러(5일)", f"{usd5:+.1f}% ({'원화약세' if usd5>0 else '원화강세'})", sig(-usd5, 0.7, -0.7, W["usd"]))
    add("투자자예탁금(5일)", f"{dep5:+.1f}%", sig(dep5, 0.3, -0.3, W["deposit"]))
    add("반대매매비중(5일Δ)", f"{cover_d:+.2f}%p", sig(-cover_d, 0.1, -0.1, W["cover"]))
    add("구리(5일)", f"{cu5:+.1f}%", sig(cu5, 1.0, -1.0, W["copper"]))
    add("신용융자(5일)", f"{cr5:+.1f}%", sig(cr5, 0.5, -0.5, W["credit"]))

    score = round(sum(x["w"] for x in S), 2)
    if score >= 3.0:   regime, rcls = "강세", "sbull"
    elif score >= 1.0: regime, rcls = "강세 우위", "bull"
    elif score > -1.0: regime, rcls = "중립", "neutral"
    elif score > -3.0: regime, rcls = "약세 우위", "bear"
    else:              regime, rcls = "약세", "sbear"

    def verdict(kind):
        if kind == "long":
            return {"sbull": ("매수 우위", "buy"), "bull": ("매수 우위", "buy"), "neutral": ("관망", "hold"),
                    "bear": ("비중축소", "reduce"), "sbear": ("회피", "avoid")}[rcls]
        if kind == "lev":
            return {"sbull": ("매수(고확신)", "buy"), "bull": ("소량·관망", "hold"), "neutral": ("회피", "avoid"),
                    "bear": ("회피", "avoid"), "sbear": ("회피", "avoid")}[rcls]
        return {"sbear": ("매수 우위", "buy"), "bear": ("분할매수·헤지", "buy"), "neutral": ("관망", "hold"),
                "bull": ("회피", "avoid"), "sbull": ("회피", "avoid")}[rcls]
    etfs = [{"name": n, "code": c, "desc": ds, "verdict": verdict(k)[0], "cls": verdict(k)[1]}
            for n, c, k, ds in [("KODEX200", "069500", "long", "KOSPI200 1배"),
                                ("KODEX 레버리지", "122630", "lev", "KOSPI200 2배"),
                                ("KODEX 인버스", "114800", "inv", "KOSPI200 -1배")]]
    pos = sum(1 for x in S if x["w"] > 0); neg = sum(1 for x in S if x["w"] < 0)
    headline = (f"종합 {regime} — 강세 신호 {pos} / 약세 신호 {neg}. KODEX200 {ks.iloc[-1]:,.0f}원(5일 {ks_5d:+.1f}%). "
                f"세 ETF 모두 KOSPI200 방향성에 수렴 — 레버리지는 고확신 국면에서만, 인버스는 하락 국면 헤지 관점.")
    fd = pd.Timestamp(for_date).date()
    return {"for_date": for_date, "for_wd": _WD[fd.weekday()],
            "asof": ks.index[-1].strftime("%Y-%m-%d"), "fetched": fetched_label,
            "score": score, "regime": regime, "rcls": rcls,
            "ks200": round(float(ks.iloc[-1]), 2), "ks200_5d": round(ks_5d, 2),
            "headline": headline, "etfs": etfs, "signals": S}


def store(data):
    db = os.path.join(OUTDIR, "judgments.db")
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE IF NOT EXISTS judgment(date TEXT PRIMARY KEY, json TEXT, created TEXT)")
    con.execute("INSERT INTO judgment(date,json,created) VALUES(?,?,?) "
                "ON CONFLICT(date) DO UPDATE SET json=excluded.json, created=excluded.created",
                (data["for_date"], json.dumps(data, ensure_ascii=False), data["fetched"]))
    con.commit()
    dates = [r[0] for r in con.execute("SELECT date FROM judgment ORDER BY date DESC").fetchall()]
    latest = con.execute("SELECT json FROM judgment ORDER BY date DESC LIMIT 1").fetchone()
    con.close()
    with open(os.path.join(OUTDIR, "judgment_dates.json"), "w") as f:
        json.dump(dates, f)
    if latest:
        with open(os.path.join(OUTDIR, "etf_judgment.json"), "w", encoding="utf-8") as f:
            f.write(latest[0])
    return dates


def _outcome(cls, r):
    """ETF별 판단 성과: (라벨, 색class)."""
    if cls == "buy":
        return ("성공(수익)", "buy") if r > 0 else ("실패(손실)", "avoid")
    if cls in ("avoid", "reduce"):
        return ("성공(하락회피)", "buy") if r < 0 else ("기회손실", "reduce")
    return ("관망", "hold")


def yahoo_ohlc(ticker, rng="3mo"):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range={rng}&interval=1d"
    d = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=25).read())
    q = d["chart"]["result"][0]["indicators"]["quote"][0]
    idx = [datetime.utcfromtimestamp(t).date() for t in d["chart"]["result"][0]["timestamp"]]
    df = pd.DataFrame({"open": q["open"], "high": q["high"], "low": q["low"], "close": q["close"]},
                      index=pd.to_datetime(idx)).dropna()
    return df


def evaluate(j, ohlc):
    """판단 j를 실제 KODEX200 결과와 상세 비교. ohlc=069500.KS OHLC DataFrame."""
    fd = pd.Timestamp(j["for_date"])
    if fd not in ohlc.index:
        return None
    row = ohlc.loc[fd]
    op, hi, lo, cl = float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])
    prev = float(j["ks200"])
    ret = (cl / prev - 1) * 100
    gap = (op / prev - 1) * 100
    intraday = (cl / op - 1) * 100
    rng_pct = (hi / lo - 1) * 100
    pred = 1 if j["rcls"] in ("sbull", "bull") else (-1 if j["rcls"] in ("sbear", "bear") else 0)
    act = 1 if ret > 0.3 else (-1 if ret < -0.3 else 0)
    if pred == 0:
        hit_label, hcls = ("적중(중립)", "buy") if act == 0 else ("중립예측", "hold")
    elif act == 0:
        hit_label, hcls = "보합", "hold"
    else:
        hit_label, hcls = ("적중", "buy") if pred == act else ("오답", "avoid")

    rets = {"KODEX200": ret, "KODEX 레버리지": 2 * ret, "KODEX 인버스": -ret}
    etfs = []
    for e in j["etfs"]:
        er = round(rets[e["name"]], 2)
        lab, oc = _outcome(e["cls"], er)
        etfs.append({"name": e["name"], "verdict": e["verdict"], "vcls": e["cls"],
                     "ret": er, "outcome": lab, "ocls": oc})

    # 신호 사후검증: 각 신호 방향이 실제 등락과 부합했는지
    review, na, nm = [], 0, 0
    for s in j["signals"]:
        sd = 1 if s["dir"] == "+" else (-1 if s["dir"] == "-" else 0)
        if sd == 0 or act == 0:
            mark, mcls = "—", "z"
        elif sd == act:
            mark, mcls = "적중", "p"; na += 1
        else:
            mark, mcls = "빗나감", "n"; nm += 1
        review.append({"name": s["name"], "val": s["val"], "w": s["w"], "mark": mark, "mcls": mcls})

    # 원인 해설 (내러티브)
    dirtxt = {1: "상승", -1: "하락", 0: "보합"}[act]
    top = sorted(j["signals"], key=lambda x: -abs(x["w"]))[:3]
    top_names = ", ".join(f"{x['name']}({x['val']})" for x in top)
    if hit_label.startswith("적중"):
        analysis = (f"예측 방향이 실제와 부합했습니다. {j['regime']} 판단을 이끈 핵심 신호({top_names})가 "
                    f"실제 {dirtxt}과 일치했고, 전체 {len(review)}개 신호 중 {na}개가 방향을 맞혔습니다. "
                    f"시가 갭 {gap:+.1f}% → 종가 {ret:+.1f}%로 {'장중에도 방향 유지' if (gap*ret)>0 else '시가와 종가 방향 교차'}.")
    elif hit_label == "오답":
        drv = "낙폭과대 기술적 반등·저가매수 유입" if act > 0 else "차익실현·상승 피로 누적"
        analysis = (f"예측({j['regime']})과 반대로 실제 {ret:+.1f}%({dirtxt}). "
                    f"우세했던 신호({top_names})가 모멘텀을 시사했으나, {drv}이 이를 압도했습니다. "
                    f"전체 {len(review)}개 신호 중 {nm}개가 실제와 반대 → 추세추종 신호가 평균회귀 국면에 빗나간 전형적 케이스. "
                    f"시가 {gap:+.1f}% 갭, 장중 {intraday:+.1f}%, 일중 변동폭 {rng_pct:.1f}%.")
    else:
        analysis = (f"실제 {ret:+.1f}%로 방향성이 약했습니다(보합권). 예측 강도 대비 실제 움직임이 작아 "
                    f"뚜렷한 적중/오답으로 보기 어렵습니다. 일중 변동폭 {rng_pct:.1f}%.")

    now = datetime.now(KST)
    return {"date": j["for_date"], "wd": j["for_wd"], "regime": j["regime"], "rcls": j["rcls"],
            "score": j.get("score"), "kodex_return": round(ret, 2), "hit_label": hit_label, "hcls": hcls,
            "ohlc": {"open": round(op, 2), "high": round(hi, 2), "low": round(lo, 2),
                      "close": round(cl, 2), "prev": round(prev, 2),
                      "gap": round(gap, 2), "intraday": round(intraday, 2), "range": round(rng_pct, 2)},
            "etfs": etfs, "signals_review": review,
            "sig_summary": {"aligned": na, "missed": nm, "total": len(review)},
            "analysis": analysis, "close_prev": round(prev, 2), "close_day": round(cl, 2), "asof": j["asof"],
            "summary": f"{j['regime']} 예측 → 실제 KODEX200 {ret:+.2f}%({dirtxt}) · {hit_label}.",
            "created": now.strftime("%Y-%m-%d(%a) %H:%M KST").replace(now.strftime("%a"), _WD[now.weekday()])}


def eval_results():
    """DB의 완료된 판단들을 실제 결과와 비교 저장 + 어제 결과 뷰 파일 작성."""
    today = datetime.now(KST).date()
    con = sqlite3.connect(os.path.join(OUTDIR, "judgments.db"))
    con.execute("CREATE TABLE IF NOT EXISTS result(date TEXT PRIMARY KEY, json TEXT, created TEXT)")
    judgs = con.execute("SELECT date,json FROM judgment").fetchall()
    have = {r[0] for r in con.execute("SELECT date FROM result").fetchall()}
    todo = [(d, jj) for d, jj in judgs if d not in have and pd.Timestamp(d).date() < today]
    if todo:
        ohlc = yahoo_ohlc("069500.KS")
        for d, jj in todo:
            res = evaluate(json.loads(jj), ohlc)
            if res:
                con.execute("INSERT OR REPLACE INTO result(date,json,created) VALUES(?,?,?)",
                            (d, json.dumps(res, ensure_ascii=False), res["created"]))
        con.commit()
    allres = [json.loads(r[0]) for r in con.execute("SELECT json FROM result ORDER BY date DESC").fetchall()]
    rdates = [r["date"] for r in allres]
    # 누적 적중률 (보합/중립 제외한 방향성 판단 기준)
    directional = [r for r in allres if r["hit_label"] in ("적중", "오답")]
    hit = sum(1 for r in directional if r["hit_label"] == "적중")
    stats = {"total": len(allres), "directional": len(directional), "hit": hit,
             "rate": round(hit / len(directional) * 100, 1) if directional else None}
    # 어제(전날) 결과 뷰
    y = today - timedelta(days=1)
    ys = y.strftime("%Y-%m-%d")
    row = con.execute("SELECT json FROM result WHERE date=?", (ys,)).fetchone()
    con.close()
    yv = {"date": ys, "wd": _WD[y.weekday()], "stats": stats}
    if row:
        yv["status"], yv["result"] = "result", json.loads(row[0])
    else:
        trading, reason = is_holiday(y)
        yv["status"] = "holiday" if not trading else "none"
        yv["reason"] = reason if not trading else "판단 기록 없음"
    with open(os.path.join(OUTDIR, "yesterday_result.json"), "w", encoding="utf-8") as f:
        json.dump(yv, f, ensure_ascii=False)
    with open(os.path.join(OUTDIR, "result_dates.json"), "w") as f:
        json.dump(rdates, f)
    return rdates, yv


def load_results(before=None):
    con = sqlite3.connect(os.path.join(OUTDIR, "judgments.db"))
    con.execute("CREATE TABLE IF NOT EXISTS result(date TEXT PRIMARY KEY, json TEXT, created TEXT)")
    if before:
        rows = con.execute("SELECT json FROM result WHERE date < ? ORDER BY date DESC", (before,)).fetchall()
    else:
        rows = con.execute("SELECT json FROM result ORDER BY date DESC").fetchall()
    con.close()
    return [json.loads(r[0]) for r in rows]


def compute_stats(cfg, eff, rates):
    allres = load_results()
    directional = [r for r in allres if r["hit_label"] in ("적중", "오답")]
    hit = sum(1 for r in directional if r["hit_label"] == "적중")
    overall = {"total": len(allres), "directional": len(directional), "hit": hit,
               "rate": round(hit / len(directional) * 100, 1) if directional else None}
    reg = {"bull": {"n": 0, "hit": 0}, "bear": {"n": 0, "hit": 0}, "neutral": {"n": 0, "hit": 0}}
    for r in directional:
        side = "bull" if r["rcls"] in ("sbull", "bull") else ("bear" if r["rcls"] in ("sbear", "bear") else "neutral")
        reg[side]["n"] += 1
        if r["hit_label"] == "적중":
            reg[side]["hit"] += 1
    # 판단 추종 누적수익 (강세→KODEX200, 약세→인버스, 중립→현금)
    equity = 100.0
    for r in sorted(allres, key=lambda x: x["date"]):
        ret = r["kodex_return"]
        pred = 1 if r["rcls"] in ("sbull", "bull") else (-1 if r["rcls"] in ("sbear", "bear") else 0)
        sr = ret if pred > 0 else (-ret if pred < 0 else 0.0)
        equity *= (1 + sr / 100)
    signals = []
    for key, name in SIG_KEYS:
        rr = rates.get(name, {})
        signals.append({"name": name, "base": cfg["weights"][key], "eff": eff[key],
                        "aligned": rr.get("aligned", 0), "missed": rr.get("missed", 0),
                        "n": rr.get("n", 0), "rate": rr.get("rate")})
    recent = [{"date": r["date"], "wd": r["wd"], "regime": r["regime"], "rcls": r["rcls"],
               "hit_label": r["hit_label"], "kodex_return": r["kodex_return"]} for r in allres[:15]]
    now = datetime.now(KST)
    return {"overall": overall, "regime": reg,
            "follow_return": round(equity - 100, 2), "follow_n": len(allres),
            "signals": signals, "recent": recent,
            "tune": {"auto": cfg.get("auto_tune"), "min_samples": cfg.get("min_samples"),
                     "active": any(s["eff"] != s["base"] for s in signals)},
            "updated": now.strftime("%Y-%m-%d %H:%M KST")}


def main():
    argdate = None
    for i, a in enumerate(sys.argv):
        if a == "--date" and i + 1 < len(sys.argv):
            argdate = sys.argv[i + 1]

    tm = today_market()
    with open(os.path.join(OUTDIR, "today_market.json"), "w", encoding="utf-8") as f:
        json.dump(tm, f, ensure_ascii=False)

    cfg = load_weight_cfg()
    for_date = argdate or tm["date"]
    eff, rates = effective_weights(cfg, load_results(before=for_date))

    if argdate:
        d = pd.Timestamp(argdate).date()
        label = f"{argdate}({_WD[d.weekday()]}) 07:00 KST"
        data = compute(argdate, label, eff)
        dates = store(data)
        print(f"[backfill {argdate}] {data['regime']} (score {data['score']:+.1f}) · DB {len(dates)}건")
    elif tm["is_trading_day"]:
        now = datetime.now(KST)
        label = now.strftime("%Y-%m-%d(%a) %H:%M KST").replace(now.strftime("%a"), _WD[now.weekday()])
        data = compute(tm["date"], label, eff)
        dates = store(data)
        print(f"[live {tm['date']}] {data['regime']} (score {data['score']:+.1f}) · {tm['status']} · "
              + " / ".join(f"{e['name']}:{e['verdict']}" for e in data["etfs"]))
    else:
        print(f"[live] {tm['date']}({tm['weekday']}) 휴장({tm['reason']}) — 판단 미갱신")

    rdates, yv = eval_results()
    # 통계 + 유효 가중치(전체 이력 기준) 산출·저장
    eff_all, rates_all = effective_weights(cfg, load_results())
    stats = compute_stats(cfg, eff_all, rates_all)
    with open(os.path.join(OUTDIR, "stats.json"), "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False)
    with open(os.path.join(OUTDIR, "signal_weights.json"), "w", encoding="utf-8") as f:
        json.dump({"weights": cfg["weights"], "effective": eff_all, "auto_tune": cfg.get("auto_tune"),
                   "min_samples": cfg.get("min_samples"), "shrink": cfg.get("shrink")}, f, ensure_ascii=False)
    ov = stats["overall"]
    print(f"results: {len(rdates)}건 · 어제({yv['date']}) {yv['status']}"
          + (f" {yv['result']['hit_label']}" if yv["status"] == "result" else "")
          + f" · 누적적중률 {ov['rate']}% · 튜닝 {'ON' if stats['tune']['active'] else '대기'}")


if __name__ == "__main__":
    main()
