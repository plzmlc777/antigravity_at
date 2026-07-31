"""Build the mobile market dashboard (index.html) with multiple sections.
Section 1: 환율 (FX vs KRW, daily, Naver)
Section 2: 원자재 (Gold/Silver/Copper daily Yahoo futures + Fertilizer/Urea monthly World Bank)
Every series ships 5Y + 1Y views + a rebased(=100) overlay. Self-contained (Chart.js CDN).
"""
import pandas as pd, json, os
from datetime import timedelta

OUTDIR = os.environ.get("DASH_OUTDIR", "/home/hcpark/antigravity/backend/runs/fx")

def load():
    fx = pd.read_csv(os.path.join(OUTDIR, "fx_krw_5y.csv"), index_col=0, parse_dates=True).sort_index()
    metals = pd.read_csv(os.path.join(OUTDIR, "commodities_daily_5y.csv"), index_col=0, parse_dates=True).sort_index()
    fert = pd.read_csv(os.path.join(OUTDIR, "fertilizer_monthly_5y.csv"), index_col=0, parse_dates=True).sort_index()
    funds = pd.read_csv(os.path.join(OUTDIR, "market_funds_5y.csv"), index_col=0, parse_dates=True).sort_index()
    credit = pd.read_csv(os.path.join(OUTDIR, "market_credit_5y.csv"), index_col=0, parse_dates=True).sort_index()
    semis = pd.read_csv(os.path.join(OUTDIR, "semis_5y.csv"), index_col=0, parse_dates=True).sort_index()
    oil = pd.read_csv(os.path.join(OUTDIR, "oil_daily_5y.csv"), index_col=0, parse_dates=True).sort_index()
    dubai = pd.read_csv(os.path.join(OUTDIR, "dubai_monthly_5y.csv"), index_col=0, parse_dates=True).sort_index()
    oil = pd.concat([oil, dubai], axis=1).sort_index()
    freight = pd.read_csv(os.path.join(OUTDIR, "freight_5y.csv"), index_col=0, parse_dates=True).sort_index()
    return fx, metals, fert, funds, credit, semis, oil, freight

def dec_for(v):
    v = abs(v)
    return 0 if v >= 1000 else (1 if v >= 100 else 2)

def series_block(s, color, short, kr, unit, d1):
    s = s.dropna()
    s1 = s[s.index >= d1]
    d = dec_for(s.iloc[-1])
    # 5Y payload downsampled to weekly (keeps last daily point); 1Y stays daily.
    s5 = s.resample("W-FRI").last().dropna()
    if len(s5) and s5.index[-1] != s.index[-1]:
        s5 = pd.concat([s5, s.iloc[[-1]]])
    def payload(x):
        return {"labels": [t.strftime("%Y-%m-%d") for t in x.index],
                "vals": [round(float(v), 4) for v in x.values]}
    return {
        "short": short, "kr": kr, "color": color, "unit": unit, "dec": d,
        "stats": {"last": round(float(s.iloc[-1]), 4),
                   "chg5y": round((s.iloc[-1] / s.iloc[0] - 1) * 100, 1) if s.iloc[0] else 0.0,
                   "chg1y": round((s1.iloc[-1] / s1.iloc[0] - 1) * 100, 1) if s1.iloc[0] else 0.0,
                   "d5": round(float(s.iloc[-1] - s.iloc[0]), 2),
                   "d1": round(float(s1.iloc[-1] - s1.iloc[0]), 2)},
        "full": payload(s5), "oneY": payload(s1),
    }

def rebased(df, cols, colors, shorts, start):
    """Monthly-resampled rebased(=100) overlay from horizon start."""
    m = df[cols].resample("MS").last().dropna(how="all")
    m = m[m.index >= start]
    m = m.ffill().dropna()
    base = m.iloc[0]
    labels = [t.strftime("%Y-%m") for t in m.index]
    sets = []
    for c, col, sh in zip(colors, cols, shorts):
        sets.append({"label": sh, "color": c,
                     "data": [round(float(v / base[col] * 100), 2) for v in m[col].values]})
    return {"labels": labels, "sets": sets}

def raw(df, cols, colors, labels, start):
    """Monthly-resampled ACTUAL-value overlay (for rates etc., no rebasing)."""
    m = df[cols].resample("MS").last().ffill()
    m = m[m.index >= start]
    lab = [t.strftime("%Y-%m") for t in m.index]
    sets = [{"label": sh, "color": c, "data": [round(float(v), 2) for v in m[col].values]}
            for c, col, sh in zip(colors, cols, labels)]
    return {"labels": lab, "sets": sets}


def main():
    fx, metals, fert, funds, credit, semis, oil, freight = load()
    rates = pd.read_csv(os.path.join(OUTDIR, "rates_5y.csv"), index_col=0, parse_dates=True).sort_index()
    asof = max(fx.index.max(), metals.index.max())
    d1 = asof - timedelta(days=365)
    d5 = fx.index.min()

    # ---- FX section ----
    fx_def = [("USD/KRW", "USD/KRW", "미국 달러", "#4ea1ff", ""),
              ("CNY/KRW", "CNY/KRW", "중국 위안", "#ff5c6c", ""),
              ("EUR/KRW", "EUR/KRW", "유로", "#4cd07d", ""),
              ("JPY/KRW (per 100)", "JPY/KRW", "일본 엔·100엔", "#b892ff", "")]
    fx_series = [series_block(fx[col], c, sh, kr, u, d1) for col, sh, kr, c, u in fx_def]
    fx_reb = {
        "5Y": rebased(fx, [d[0] for d in fx_def], [d[3] for d in fx_def], [d[1] for d in fx_def], d5),
        "1Y": rebased(fx, [d[0] for d in fx_def], [d[3] for d in fx_def], [d[1] for d in fx_def], d1),
    }

    # ---- Commodity section ----
    fert_u = fert[["Urea"]].rename(columns={"Urea": "Urea"})
    com = pd.concat([metals, fert_u], axis=1).sort_index()
    com_def = [("Gold", "금 Gold", "$/oz", "#ffd23f"),
               ("Silver", "은 Silver", "$/oz", "#c0c6cf"),
               ("Copper", "구리 Copper", "$/lb", "#e08a5b"),
               ("Urea", "비료 Urea", "$/t · 월간", "#7ecb8f")]
    com_series = []
    for col, kr, unit, c in com_def:
        com_series.append(series_block(com[col], c, col, kr, unit, d1))
    com_reb = {
        "5Y": rebased(com, [d[0] for d in com_def], [d[3] for d in com_def], [d[0] for d in com_def], d5),
        "1Y": rebased(com, [d[0] for d in com_def], [d[3] for d in com_def], [d[0] for d in com_def], d1),
    }

    # ---- Market funds section (증시자금, KOFIA) ----
    fund_def = [("투자자예탁금", "고객 예탁금·대기자금", "조", "#4ea1ff"),
                ("장내파생예수금", "파생 거래예수금", "조", "#ffd23f"),
                ("대고객RP매도잔고", "대고객 RP 매도잔고", "조", "#4cd07d"),
                ("반대매매비중", "미수금 대비·시장 스트레스", "%", "#ff5c6c")]
    fund_series = [series_block(funds[col], c, col, kr, u, d1) for col, kr, u, c in fund_def]
    amt = ["투자자예탁금", "장내파생예수금", "대고객RP매도잔고"]
    fund_reb = {"5Y": rebased(funds, amt, ["#4ea1ff", "#ffd23f", "#4cd07d"], amt, d5),
                "1Y": rebased(funds, amt, ["#4ea1ff", "#ffd23f", "#4cd07d"], amt, d1)}

    # ---- Credit / margin loan section (신용융자, KOFIA) ----
    cred_def = [("신용융자", "고객 신용융자잔고(전체)", "조", "#ff5c6c"),
                ("신용융자_코스피", "코스피 신용융자", "조", "#4ea1ff"),
                ("신용융자_코스닥", "코스닥 신용융자", "조", "#ffd23f"),
                ("예탁증권담보융자", "예탁증권 담보융자", "조", "#4cd07d")]
    cred_series = [series_block(credit[col], c, col, kr, u, d1) for col, kr, u, c in cred_def]
    ccols = [d[0] for d in cred_def]
    cred_reb = {"5Y": rebased(credit, ccols, [d[3] for d in cred_def], ccols, d5),
                "1Y": rebased(credit, ccols, [d[3] for d in cred_def], ccols, d1)}

    # ---- Semiconductor section (SOX + KR semi leaders + NVDA) ----
    semi_def = [("SOX", "필라델피아 반도체 지수", "pt", "#4ea1ff"),
                ("삼성전자", "005930 · KR 대장주", "원", "#4cd07d"),
                ("SK하이닉스", "000660 · HBM 리더", "원", "#ffd23f"),
                ("NVIDIA", "NVDA · AI 대장", "$", "#7ecb8f")]
    semi_series = [series_block(semis[col], c, col, kr, u, d1) for col, kr, u, c in semi_def]
    scols = [d[0] for d in semi_def]
    semi_reb = {"5Y": rebased(semis, scols, [d[3] for d in semi_def], scols, d5),
                "1Y": rebased(semis, scols, [d[3] for d in semi_def], scols, d1)}

    # ---- Oil / energy section (WTI/Brent + Dubai + NatGas) ----
    oil_def = [("WTI", "서부텍사스유 (CL=F)", "$/bbl", "#4ea1ff"),
               ("Brent", "브렌트유 (BZ=F)", "$/bbl", "#ff5c6c"),
               ("두바이유", "KR 도입기준·월간", "$/bbl", "#ffd23f"),
               ("천연가스", "Henry Hub (NG=F)", "$/MMBtu", "#4cd07d")]
    oil_series = [series_block(oil[col], c, col, kr, u, d1) for col, kr, u, c in oil_def]
    ocols = [d[0] for d in oil_def]
    oil_reb = {"5Y": rebased(oil, ocols, [d[3] for d in oil_def], ocols, d5),
               "1Y": rebased(oil, ocols, [d[3] for d in oil_def], ocols, d1)}

    # ---- Freight index section (KDCI = KOBC Dry Bulk Index, global freight, gov key-less) ----
    fr_def = [("건화물종합", "KDCI 종합 · 글로벌 건화물 운임", "pt", "#4ea1ff"),
              ("케이프", "Capesize · 철광석·석탄 대형선", "pt", "#ff5c6c"),
              ("파나막스", "Panamax · 곡물·석탄 중형선", "pt", "#4cd07d"),
              ("수프라막스", "Supramax · 중소형 다목적선", "pt", "#ffd23f")]
    fr_series = [series_block(freight[col], c, col, kr, u, d1) for col, kr, u, c in fr_def]
    frcols = [d[0] for d in fr_def]
    fr_reb = {"5Y": rebased(freight, frcols, [d[3] for d in fr_def], frcols, d5),
              "1Y": rebased(freight, frcols, [d[3] for d in fr_def], frcols, d1)}

    # ---- Policy rate section (BIS central bank policy rates) ----
    rate_palette = ["#4ea1ff", "#ff5c6c", "#4cd07d", "#ffd23f", "#b892ff", "#7ecb8f",
                    "#ff8c42", "#45c4b0", "#e06be0", "#f6c445", "#6ea8fe", "#ff9aa2", "#9ad0c2"]
    rate_cols = list(rates.columns)
    rate_series = [series_block(rates[col], rate_palette[i % len(rate_palette)], col, "정책금리", "%", d1)
                   for i, col in enumerate(rate_cols)]
    rate_ov = {"5Y": raw(rates, rate_cols, rate_palette, rate_cols, d5),
               "1Y": raw(rates, rate_cols, rate_palette, rate_cols, d1)}

    def g(series, sh):
        return next(x["stats"] for x in series if x["short"] == sh)
    gS = lambda sh: g(com_series, sh)
    fS = lambda sh: g(fx_series, sh)
    uS = lambda sh: g(fund_series, sh)
    cS = lambda sh: g(cred_series, sh)
    sS = lambda sh: g(semi_series, sh)
    oS = lambda sh: g(oil_series, sh)
    hS = lambda sh: g(fr_series, sh)
    rS = lambda sh: g(rate_series, sh)

    fx_insights = [
        "<b>원화 전방위 약세(5년):</b> 달러·유로·위안 대비 원화가 약 30% 절하 — 특정 통화 이슈가 아닌 <b>원화 자체의 구조적 약세</b>. 수출주엔 우호적이나 외국인 수급엔 부담.",
        "<b>최근 1년은 위안화가 주도:</b> CNY/KRW가 달러보다 강하게 절상 — 대중 교역·중국 관련주 원가 부담 요인.",
        "<b>엔화만 예외:</b> 5년 기준 원화가 엔 대비 오히려 강세 유지 — 대일 경쟁 수출업종(자동차·철강·기계) 상대적 불리.",
        "<b>USD/KRW 1,500원대 고점권:</b> 환율 부담이 밸류에이션·외국인 순매수의 실질 변수.",
    ]
    com_insights = [
        f"<b>금 초강세(+{gS('Gold')['chg5y']:.0f}% 5년, +{gS('Gold')['chg1y']:.0f}% 1년):</b> 안전자산·인플레 헤지·중앙은행 매입 — 위험선호 약화 신호 겸 KR 증시 대체투자 경쟁 요인. 은도 동반 급등(+{gS('Silver')['chg5y']:.0f}% 5년).",
        f"<b>구리 '닥터 코퍼' (+{gS('Copper')['chg5y']:.0f}% 5년):</b> 경기 선행지표. 상승 = 글로벌 제조업·전기화(전선/2차전지) 수요 견조 → KR 산업재·소재·전력설비 수혜 방향.",
        f"<b>비료(Urea) 정상화 후 변동:</b> 2022 에너지·전쟁 급등 → 이후 하향, 최근 재변동(현재 ${gS('Urea')['last']:.0f}/t). 농산물 물가·KR 비료주(롯데정밀화학·남해화학) 마진에 파급.",
        "<b>원화 약세 × 원자재 강세 결합:</b> 수입 원자재 원가가 이중으로 상승 → 소재·화학·정유 등 원가 전가력 약한 업종 마진 압박.",
    ]

    fund_insights = [
        f"<b>투자자예탁금(고객 예탁금) {uS('투자자예탁금')['last']:.0f}조 · 5년 {uS('투자자예탁금')['chg5y']:+.0f}%:</b> 증시 <b>대기성 자금·투자심리</b> 직결 지표. 증가 = 매수 여력 풍부(강세 우호), 감소 = 관망·이탈. 1년 {uS('투자자예탁금')['chg1y']:+.1f}%.",
        f"<b>장내파생 예수금 급증(5년 {uS('장내파생예수금')['chg5y']:+.0f}%):</b> 파생·레버리지 거래 활동 확대 — 변동성 매매 수요 증가 신호.",
        f"<b>반대매매비중 {uS('반대매매비중')['last']:.1f}%:</b> 미수금 대비 강제청산 강도 = 신용 스트레스 게이지. 낮을수록 시장 안정. (출처: 금융투자협회)",
        "<b>탭 결합 해석:</b> 예탁금 풍부(유동성) × 원화 약세 × 원자재 강세 = 자금은 많으나 밸류·환·원가 부담 병존. 예탁금 급감 + 반대매매비중 급등이 동반되면 조정 경보.",
    ]
    cred_insights = [
        f"<b>고객 신용융자잔고 {cS('신용융자')['last']:.0f}조 · 5년 {cS('신용융자')['chg5y']:+.0f}%:</b> <b>빚내서 산 주식(레버리지) 총량</b> = 투자심리 과열·위험 게이지. 증가 = 위험선호↑(과열 경계), 급감 = 디레버리징(반대매매·하락 압력). 1년 {cS('신용융자')['chg1y']:+.1f}%.",
        f"<b>코스피 {cS('신용융자_코스피')['last']:.0f}조 vs 코스닥 {cS('신용융자_코스닥')['last']:.0f}조:</b> 시장별 레버리지 분포. 코스닥 신용융자 비중이 높으면 개인·중소형주 과열 신호(변동성 취약).",
        f"<b>예탁증권 담보융자 {cS('예탁증권담보융자')['last']:.0f}조:</b> 보유 주식 담보 대출 — 또 다른 레버리지 채널. 신용융자와 동반 증가 시 전체 위험 노출 확대.",
        "<b>신용융자 高 + 반대매매비중(증시자금 탭) 급등 = 청산 연쇄 위험.</b> 상승장에선 강세를 증폭하나, 하락 전환 시 강제청산이 낙폭을 키우는 양날의 지표.",
    ]
    semi_insights = [
        f"<b>필라델피아 반도체 지수(SOX) 5년 {sS('SOX')['chg5y']:+.0f}% · 1년 {sS('SOX')['chg1y']:+.0f}%:</b> 글로벌 반도체 경기 <b>대표 선행지표</b>. KR 증시는 반도체 비중이 커 SOX가 코스피 방향성의 핵심 외생 변수 — SOX 꺾이면 KR 반도체·코스피 동반 부담.",
        f"<b>삼성전자 vs SK하이닉스:</b> 5년 삼성 {sS('삼성전자')['chg5y']:+.0f}% / SK하이닉스 {sS('SK하이닉스')['chg5y']:+.0f}%. HBM(고대역폭메모리) 리더십 격차가 상대 강도로 반영 — SK하이닉스가 AI 사이클 직접 수혜.",
        f"<b>NVIDIA 5년 {sS('NVIDIA')['chg5y']:+.0f}%:</b> AI 가속기 수요가 SOX·HBM 사이클을 견인. NVDA→HBM(하이닉스/삼성)→SOX→KR 반도체주로 이어지는 파급 경로.",
        "<b>KR 시사점:</b> 상대 비교 차트(시작=100)에서 KR 대장주가 SOX·NVDA를 <b>따라가는지/뒤처지는지</b>가 외국인 수급·코스피 탄력의 선행 신호. 원화 약세(환율 탭)는 반도체 수출 채산성엔 우호적.",
    ]
    oil_insights = [
        f"<b>WTI ${oS('WTI')['last']:.0f} · Brent ${oS('Brent')['last']:.0f}:</b> 글로벌 원유 벤치마크. KR은 원유 100% 수입 → 유가 상승 = 무역수지·물가·정유/화학 원가에 직접 파급. Brent 5년 {oS('Brent')['chg5y']:+.0f}% / 1년 {oS('Brent')['chg1y']:+.0f}%.",
        f"<b>두바이유 ${oS('두바이유')['last']:.0f}:</b> KR이 실제 도입하는 중동산 원유 기준가. WTI·Brent와 스프레드가 KR 정유사 도입 원가를 좌우 — 국내 정제마진의 핵심 변수.",
        f"<b>천연가스 ${oS('천연가스')['last']:.1f}/MMBtu:</b> KR LNG 수입(KOGAS)·발전·도시가스·석유화학 원가. 5년 {oS('천연가스')['chg5y']:+.0f}% — 에너지 인플레·전력요금 압력과 연동.",
        "<b>유가↑ × 원화 약세(환율 탭) = 수입 원가 이중 부담.</b> 항공·해운·화학은 마진 압박, 반대로 정유주는 정제마진 확대 국면에선 수혜 — 업종별 방향이 갈리는 지표.",
    ]
    fr_insights = [
        f"<b>건화물 운임지수(KDCI) {hS('건화물종합')['last']:,.0f}pt · 5년 {hS('건화물종합')['chg5y']:+.0f}% · 1년 {hS('건화물종합')['chg1y']:+.0f}%:</b> 철광석·석탄·곡물 <b>물동량 = 글로벌 경기·중국 수요 바로미터</b>. 한국해양진흥공사(KOBC)가 산출하는 글로벌 건화물 운임지수(발틱 BDI에 대응, BDI 원본은 유료).",
        f"<b>케이프사이즈 {hS('케이프')['last']:,.0f}pt (5년 {hS('케이프')['chg5y']:+.0f}%):</b> 대형 벌크선 = <b>철광석·석탄</b> 전용. 케이프 급등 = 중국 철강·원자재 수요 강세 신호. 변동성이 가장 큼.",
        f"<b>파나막스 {hS('파나막스')['last']:,.0f} · 수프라막스 {hS('수프라막스')['last']:,.0f}pt:</b> 곡물·석탄(파나막스), 중소형 다목적(수프라막스). 선형별 분화로 어떤 화물 수요가 운임을 끌어올리는지 파악.",
        "<b>KR 시사점:</b> 건화물 운임 = 팬오션·대한해운 등 <b>벌크 해운주 실적</b>, 포스코 등 <b>철광석 수입 원가</b>, 조선 수주 사이클과 연동. 원자재 탭(구리 등)과 함께 보면 글로벌 실물경기 방향 확인.",
    ]
    rate_insights = [
        f"<b>미국 {rS('미국')['last']:.2f}% · 한국 {rS('한국')['last']:.2f}% (한미 금리차 {rS('미국')['last']-rS('한국')['last']:+.2f}%p):</b> 미국이 한국보다 높으면 <b>외국인 자금 유출·원화 약세 압력</b>(환율 탭과 직결). Fed 방향이 KR 통화정책·증시 유동성의 최상위 변수.",
        f"<b>러시아 {rS('러시아')['last']:.2f}% · 브라질 {rS('브라질')['last']:.2f}%:</b> 고인플레·통화방어로 초고금리 유지. 신흥국 고금리 = 캐리·위험선호 자금 흐름의 축, 원자재·환 변동과 연동.",
        f"<b>동남아: 인도네시아 {rS('인도네시아')['last']:.2f}% · 태국 {rS('태국')['last']:.2f}% · 말레이시아 {rS('말레이시아')['last']:.2f}% · 필리핀 {rS('필리핀')['last']:.2f}%:</b> KR 수출·공급망 밀접 지역. 완화 사이클 진입 시 역내 수요·KR 소재/부품 수출에 우호적.",
        "<b>주요국 완화(금리 인하) 동조 = 글로벌 유동성 확대 = 위험자산·증시 우호.</b> 상단 오버레이에서 선진국(미국/유로존/일본)과 신흥국(러/브/동남아) 금리 <b>레벨·방향 차이</b>가 글로벌 자금 이동을 결정.",
    ]

    with open(os.path.join(OUTDIR, "etf_judgment.json"), encoding="utf-8") as _jf:
        judg = json.load(_jf)
    try:
        with open(os.path.join(OUTDIR, "judgment_dates.json"), encoding="utf-8") as _df:
            judg_dates = json.load(_df)
    except Exception:
        judg_dates = [judg["for_date"]]
    try:
        with open(os.path.join(OUTDIR, "today_market.json"), encoding="utf-8") as _tf:
            today_mkt = json.load(_tf)
    except Exception:
        today_mkt = {"date": judg["for_date"], "weekday": judg.get("for_wd", ""),
                     "is_trading_day": True, "status": "장전", "reason": ""}
    try:
        with open(os.path.join(OUTDIR, "stats.json"), encoding="utf-8") as _sf:
            statsj = json.load(_sf)
    except Exception:
        statsj = None
    stats_insights = [
        "판단 이력이 쌓일수록 <b>방향성 적중률·판단추종 수익·신호별 신뢰도</b>가 자동 집계됩니다.",
        "<b>신호 가중치 튜닝:</b> 각 신호의 과거 적중률에 따라 가중치를 자동 조정합니다(표본 15건 이상 시 활성, 완충 적용). 잘 맞는 신호는 ↑, 자주 틀리는 신호는 ↓.",
        "판단추종 누적수익 = 매 거래일 <b>강세→KODEX200 / 약세→인버스 / 중립→현금</b> 로 따랐을 때의 누적(수수료·슬리피지 미반영, 참고용).",
    ]
    try:
        with open(os.path.join(OUTDIR, "yesterday_result.json"), encoding="utf-8") as _yf:
            yresult = json.load(_yf)
    except Exception:
        yresult = {"status": "none", "date": judg["for_date"], "wd": judg.get("for_wd", "")}
    try:
        with open(os.path.join(OUTDIR, "result_dates.json"), encoding="utf-8") as _rd:
            result_dates = json.load(_rd)
    except Exception:
        result_dates = []
    result_insights = [
        "어제 <b>개장 전 판단</b>(방향성)과 그날 <b>실제 KODEX200 등락</b>을 비교한 사후 검증입니다.",
        "적중/오답은 판단의 강세·약세 방향과 실제 등락 부호 일치 여부. ETF별로 그 판단대로 했을 때 <b>수익/손실/기회손실</b>도 표시합니다.",
        "전날이 <b>휴장</b>이라 판단이 없으면 결과 분석 대상이 없어 '휴장일'로 표시됩니다.",
    ]
    verdict_insights = [
        "이 판단은 대시보드 지표를 <b>규칙 기반으로 종합한 알고리즘 참고 신호</b>입니다 — 투자 판단·책임은 본인에게 있습니다.",
        "전일 종가·해외 지표 기준 <b>개장 전 방향성 bias</b>이며, 장중 급변·뉴스는 반영하지 않습니다(실시간 아님).",
        "세 ETF 모두 KOSPI200 기반 — <b>레버리지(2배)는 고확신 강세</b>에서만, <b>인버스(-1배)는 하락 국면 헤지</b> 관점.",
    ]

    with open(os.path.join(OUTDIR, "reports.json"), encoding="utf-8") as _rf:
        rj = json.load(_rf)
    reports_insights = [
        "각 항목을 누르면 해당 <b>증권사 리포트 원문</b>(네이버 금융)으로 이동합니다. 매일 오전 자동 갱신 — 그날 기준 최신 종목분석 리포트입니다.",
        "증권사 종목분석 리포트는 대부분 <b>매수·긍정 커버리지</b>(sell-side 특성)라, 사실상 '추천/관심 종목' 리스트로 볼 수 있습니다.",
        "<b>추천제외(추천 포트폴리오 편출) 종목</b>은 증권사별 데일리에만 있고 무료 공개 구조 피드가 없어 이번엔 미포함입니다. 특정 포털/형식으로 보시는 게 있으면 그 소스로 붙여드리겠습니다.",
    ]

    DATA = {
        "meta": {"asof": asof.strftime("%Y-%m-%d"), "start5y": d5.strftime("%Y-%m-%d"),
                  "built": "__BUILT__"},
        "sections": [
            {"id": "verdict", "title": "오늘판단", "verdict": True, "j": judg, "dates": judg_dates,
             "today": today_mkt,
             "sub": f"KOSPI200 ETF 당일 방향성 판단 · 알고리즘 참고 신호",
             "insights": verdict_insights},
            {"id": "result", "title": "어제결과", "result": True, "yv": yresult, "dates": result_dates,
             "sub": "어제 판단 vs 실제 결과 (사후 검증) · KODEX200 기준",
             "insights": result_insights},
            {"id": "stats", "title": "적중률통계", "statsview": True, "s": statsj,
             "sub": "판단 적중률·신호 신뢰도·가중치 튜닝",
             "insights": stats_insights},
            {"id": "fx", "title": "환율", "sub": "원화 대비 종가 · 일봉 · 출처 네이버",
             "series": fx_series, "rebased": fx_reb, "insights": fx_insights,
             "reblabel": "시작=100 · 높을수록 원화 약세"},
            {"id": "com", "title": "원자재", "sub": "금·은·구리 일봉(Yahoo 선물) + 비료 월간(World Bank)",
             "series": com_series, "rebased": com_reb, "insights": com_insights,
             "reblabel": "시작=100 · 월간 기준 상대 비교"},
            {"id": "fund", "title": "증시자금", "sub": "투자자예탁금 등 · 일별 · 출처 금융투자협회",
             "series": fund_series, "rebased": fund_reb, "insights": fund_insights,
             "reblabel": "시작=100 · 월간 기준 · 예탁금/파생/RP"},
            {"id": "credit", "title": "신용융자", "sub": "고객 신용융자잔고 등 · 일별 · 출처 금융투자협회",
             "series": cred_series, "rebased": cred_reb, "insights": cred_insights,
             "reblabel": "시작=100 · 월간 기준 · 전체/코스피/코스닥/담보"},
            {"id": "semi", "title": "반도체", "sub": "필라델피아 반도체지수 + KR 반도체 대장주 · 일봉 · Yahoo",
             "series": semi_series, "rebased": semi_reb, "insights": semi_insights,
             "reblabel": "시작=100 · 월간 기준 · SOX·삼성·하이닉스·NVDA"},
            {"id": "oil", "title": "유가", "sub": "WTI·Brent·두바이유·천연가스 · Yahoo 선물 + World Bank",
             "series": oil_series, "rebased": oil_reb, "insights": oil_insights,
             "reblabel": "시작=100 · 월간 기준 · WTI/Brent/두바이/가스"},
            {"id": "freight", "title": "운임지수", "sub": "건화물 운임지수(KDCI) 선형별 · 일별 · 출처 한국해양진흥공사(KOBC)",
             "series": fr_series, "rebased": fr_reb, "insights": fr_insights,
             "reblabel": "시작=100 · 월간 기준 · 종합/케이프/파나막스/수프라막스"},
            {"id": "rate", "title": "기준금리", "rate": True,
             "sub": "주요국 중앙은행 정책금리 · 일별 · 출처 BIS(국제결제은행)",
             "series": rate_series, "rebased": rate_ov, "insights": rate_insights,
             "reblabel": "실제 정책금리(%) · 월말 기준"},
            {"id": "reports", "title": "증권사리포트", "list": True,
             "sub": f"오늘의 증권사 종목 리포트 · {rj['asof']} 기준 · 출처 네이버 금융 리서치",
             "asof": rj["asof"], "items": rj["items"], "insights": reports_insights},
        ],
    }
    return DATA, asof


HTML = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<meta name="theme-color" content="#0d1117">
<title>한국 증시 분석</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
  :root{ --bg:#0d1117; --card:#161b22; --border:#232a34; --fg:#e6edf3; --sub:#8b949e; --up:#ff5c6c; --dn:#4ea1ff; }
  *{ box-sizing:border-box; -webkit-tap-highlight-color:transparent; }
  body{ margin:0; background:var(--bg); color:var(--fg);
    font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Malgun Gothic",system-ui,sans-serif;
    padding:16px 14px 40px; max-width:720px; margin:0 auto; }
  h1{ font-size:20px; margin:4px 0 2px; letter-spacing:-.3px; }
  .sub{ color:var(--sub); font-size:12px; margin-bottom:12px; }
  .tabs{ display:flex; gap:8px; margin-bottom:10px; }
  .tabs button{ flex:1; padding:11px; border-radius:11px; border:1px solid var(--border);
    background:var(--card); color:var(--sub); font-size:15px; font-weight:700; }
  .tabs button.active{ background:#238636; color:#fff; border-color:#238636; }
  .toggle{ display:flex; gap:8px; margin-bottom:16px; }
  .toggle button{ flex:1; padding:9px; border-radius:10px; border:1px solid var(--border);
    background:var(--card); color:var(--sub); font-size:13px; font-weight:600; }
  .toggle button.active{ background:#1f6feb; color:#fff; border-color:#1f6feb; }
  .card{ background:var(--card); border:1px solid var(--border); border-radius:14px;
    padding:14px 14px 8px; margin-bottom:14px; }
  .chead{ display:flex; align-items:baseline; justify-content:space-between; margin-bottom:6px; }
  .cname{ font-size:15px; font-weight:700; }
  .cname small{ color:var(--sub); font-weight:500; font-size:11px; margin-left:5px; }
  .cval{ font-size:18px; font-weight:800; font-variant-numeric:tabular-nums; }
  .cval small{ font-size:10px; color:var(--sub); font-weight:600; margin-left:3px; }
  .badges{ display:flex; gap:6px; margin:2px 0 8px; }
  .badge{ font-size:11px; padding:2px 8px; border-radius:20px; font-weight:700; font-variant-numeric:tabular-nums; }
  .badge span{ color:var(--sub); font-weight:600; margin-right:3px; }
  .pos{ background:rgba(255,92,108,.15); color:var(--up); }
  .neg{ background:rgba(78,161,255,.15); color:var(--dn); }
  .cwrap{ position:relative; height:150px; }
  .overlay .cwrap{ height:260px; }
  .insights{ background:var(--card); border:1px solid var(--border); border-radius:14px; padding:16px; }
  .insights h2{ font-size:15px; margin:0 0 10px; }
  .insights li{ font-size:13px; line-height:1.6; color:#c9d1d9; margin-bottom:8px; }
  .ohlc{ display:grid; grid-template-columns:1fr 1fr 1fr 1fr; gap:6px; margin:6px 0; }
  .ohlc div{ background:#0d1117; border:1px solid var(--border); border-radius:8px; padding:7px 4px; text-align:center; }
  .ohlc b{ display:block; font-size:14px; font-variant-numeric:tabular-nums; margin-top:2px; }
  .ohlc small{ color:var(--sub); font-size:10px; }
  .mk{ font-size:11px; font-weight:800; padding:1px 7px; border-radius:6px; min-width:44px; text-align:center; }
  .mk.ok{ background:rgba(63,185,80,.18); color:#3fb950; } .mk.no{ background:rgba(248,81,73,.18); color:#f85149; } .mk.na{ background:#1c2230; color:#6b7280; }
  .dpick{ font-size:14px; font-weight:700; color:var(--fg); display:flex; align-items:center; gap:8px; }
  .dpick select{ flex:1; background:#0d1117; color:var(--fg); border:1px solid var(--border); border-radius:9px; padding:9px 10px; font-size:14px; font-weight:600; }
  .mkt{ display:inline-block; font-size:12px; font-weight:800; padding:4px 11px; border-radius:20px; margin-bottom:9px; }
  .mkt.open{ background:rgba(63,185,80,.18); color:#3fb950; }
  .mkt.closed{ background:rgba(248,81,73,.18); color:#f85149; }
  .vhead{ font-size:22px; font-weight:900; letter-spacing:-.5px; }
  .vhead.sbull,.vhead.bull{ color:#ff5c6c; } .vhead.bear,.vhead.sbear{ color:#4ea1ff; } .vhead.neutral{ color:#c9d1d9; }
  .vscore{ color:var(--sub); font-size:12px; margin:4px 0 10px; }
  .vsub{ font-size:13px; line-height:1.6; color:#c9d1d9; }
  .etfrow{ display:flex; align-items:center; justify-content:space-between; padding:12px 4px; border-bottom:1px solid var(--border); }
  .etfrow:last-child{ border-bottom:none; }
  .etfrow b{ font-size:15px; } .etfrow small{ color:var(--sub); font-size:11px; margin-left:6px; font-weight:600; }
  .vbadge{ font-size:13px; font-weight:800; padding:5px 12px; border-radius:9px; white-space:nowrap; }
  .vbadge.buy{ background:rgba(63,185,80,.18); color:#3fb950; } .vbadge.hold{ background:#1c2230; color:#9aa4b2; }
  .vbadge.reduce{ background:rgba(210,153,34,.18); color:#d29922; } .vbadge.avoid{ background:rgba(248,81,73,.18); color:#f85149; }
  .sigrow{ display:flex; align-items:center; gap:8px; padding:7px 2px; font-size:12.5px; border-bottom:1px solid #1a2029; }
  .sigrow:last-child{ border-bottom:none; }
  .sdir{ width:16px; text-align:center; font-weight:900; } .sdir.p{ color:#ff5c6c; } .sdir.n{ color:#4ea1ff; } .sdir.z{ color:#6b7280; }
  .sname{ flex:1; color:#e6edf3; } .sval{ color:var(--sub); font-variant-numeric:tabular-nums; }
  .rmeta{ color:var(--sub); font-size:12px; margin:2px 2px 12px; }
  .ghouse{ font-size:15px; font-weight:800; color:#58a6ff; margin:0 0 6px; display:flex; align-items:center; gap:7px; }
  .ghouse span{ font-size:11px; font-weight:700; color:var(--sub); background:#1c2230; border-radius:20px; padding:1px 8px; }
  .rpt{ display:block; padding:11px 6px; border-bottom:1px solid var(--border); text-decoration:none; color:var(--fg); }
  .rpt:last-child{ border-bottom:none; }
  .rpt:active{ background:#1c2230; }
  .rmain{ font-size:14px; font-weight:700; }
  .rtitle{ font-size:12px; color:#9aa4b2; margin-top:3px; line-height:1.4; padding-right:14px; }
  .rpt::after{ content:"›"; float:right; color:var(--sub); font-size:16px; margin-top:-18px; }
  .foot{ color:var(--sub); font-size:11px; text-align:center; margin-top:20px; line-height:1.6; }
</style>
</head>
<body>
  <h1>🇰🇷 한국 증시 분석</h1>
  <div class="sub" id="sub"></div>
  <div class="tabs" id="tabs"></div>
  <div class="toggle">
    <button id="b5" class="active" onclick="setH('5Y')">최근 5년</button>
    <button id="b1" onclick="setH('1Y')">최근 1년</button>
  </div>
  <div id="cards"></div>
  <div class="card overlay">
    <div class="cname" style="margin-bottom:8px">상대 비교 <small id="rebl"></small></div>
    <div class="cwrap"><canvas id="reb"></canvas></div>
  </div>
  <div class="insights"><h2 id="inh">핵심 시사점</h2><ul id="ins"></ul></div>
  <div class="foot" id="foot"></div>
<script>
const D = __DATA__;
let H='5Y', SEC=0;
const cs={};
Chart.defaults.color='#8b949e'; Chart.defaults.font.size=10;

function ds(labels, vals, maxN){
  const n=labels.length; if(n<=maxN) return {labels,vals};
  const step=Math.ceil(n/maxN); const L=[],V=[];
  for(let i=0;i<n;i+=step){ L.push(labels[i]); V.push(vals[i]); }
  if(L[L.length-1]!==labels[n-1]){ L.push(labels[n-1]); V.push(vals[n-1]); }
  return {labels:L, vals:V};
}
function fmt(x, dec){ return x.toLocaleString('en-US',{minimumFractionDigits:dec,maximumFractionDigits:dec}); }
function badge(v, lbl){ const c=v>=0?'pos':'neg'; const s=(v>=0?'+':'')+v.toFixed(1)+'%';
  return `<span class="badge ${c}"><span>${lbl}</span>${s}</span>`; }
function badgePP(v, lbl){ const c=v>=0?'pos':'neg'; const s=(v>=0?'+':'')+v.toFixed(2)+'%p';
  return `<span class="badge ${c}"><span>${lbl}</span>${s}</span>`; }

function lineCfg(labels,data,color,dec){
  return { type:'line', data:{labels,datasets:[{data,borderColor:color,borderWidth:1.6,
      pointRadius:0,tension:.15,fill:true,backgroundColor:color+'22'}]},
    options:{responsive:true,maintainAspectRatio:false,animation:false,
      interaction:{intersect:false,mode:'index'},
      plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>' '+fmt(c.parsed.y,dec)}}},
      scales:{x:{ticks:{maxTicksLimit:5,autoSkip:true},grid:{display:false}},
        y:{ticks:{maxTicksLimit:5,callback:v=>fmt(v, v>=1000?0:(v>=100?0:2))},grid:{color:'#1c232c'}}}} };
}

function render(){
  const sec=D.sections[SEC];
  const wrap=document.getElementById('cards'); wrap.innerHTML='';
  const tg=document.querySelector('.toggle'), ov=document.querySelector('.overlay');
  if(sec.verdict){
    tg.style.display='none'; ov.style.display='none';
    const arrow=d=>d==='+'?'▲':d==='-'?'▼':'–', dcls=d=>d==='+'?'p':d==='-'?'n':'z';
    function vHTML(j){
      return `<div class="card"><div class="vscore">📌 판단 기준일 ${j.for_date}(${j.for_wd}) · 데이터 ${j.asof} 종가 · 🕒 ${j.fetched}</div>`
        +`<div class="vhead ${j.rcls}">판단 · ${j.regime}</div>`
        +`<div class="vscore" style="margin-top:-4px">종합점수 ${j.score>=0?'+':''}${j.score} · KODEX200 ${j.ks200.toLocaleString()}원 (5일 ${j.ks200_5d>=0?'+':''}${j.ks200_5d}%)</div>`
        +`<div class="vsub">${j.headline}</div></div>`
        +`<div class="card"><div class="cname" style="margin-bottom:4px">ETF별 판단</div>`
        +j.etfs.map(e=>`<div class="etfrow"><div><b>${e.name}</b><small>${e.code} · ${e.desc}</small></div><span class="vbadge ${e.cls}">${e.verdict}</span></div>`).join('')+`</div>`
        +`<div class="card"><div class="cname" style="margin-bottom:6px">신호 근거</div>`
        +j.signals.map(s=>`<div class="sigrow"><span class="sdir ${dcls(s.dir)}">${arrow(s.dir)}</span><span class="sname">${s.name}</span><span class="sval">${s.val}</span></div>`).join('')+`</div>`;
    }
    const t=sec.today;
    const topBadge=`<div class="card"><div class="mkt ${t.is_trading_day?'open':'closed'}">${t.is_trading_day?'🟢 오늘 개장':'🔴 오늘 휴장'} · ${t.date}(${t.weekday}) · ${t.is_trading_day?t.status:t.reason}</div>`
      +(t.is_trading_day?'':`<div class="vsub" style="margin-top:5px">오늘은 휴장 — 아래는 <b>최근 거래일</b> 판단입니다.</div>`)+`</div>`;
    const opts=sec.dates.map(d=>`<option value="${d}">${d}${d===sec.j.for_date?(d===t.date?' (오늘)':' (최근 거래일)'):''}</option>`).join('');
    wrap.innerHTML=topBadge+`<div class="card"><label class="dpick">📅 판단 날짜 <select id="jdate">${opts}</select></label></div><div id="vbody">${vHTML(sec.j)}</div>`;
    const sel=document.getElementById('jdate');
    sel.onchange=async()=>{
      const d=sel.value, body=document.getElementById('vbody');
      if(d===sec.j.for_date){ body.innerHTML=vHTML(sec.j); return; }
      body.innerHTML='<div class="card" style="color:#8b949e">불러오는 중…</div>';
      try{ const r=await fetch('/j/'+d+'.json',{credentials:'same-origin'}); if(!r.ok) throw 0;
        body.innerHTML=vHTML(await r.json()); }
      catch(e){ body.innerHTML='<div class="card" style="color:#f85149">해당 날짜 판단을 불러오지 못했습니다.</div>'; }
    };
    document.getElementById('inh').textContent='유의사항';
    document.getElementById('ins').innerHTML=sec.insights.map(t=>`<li>${t}</li>`).join('');
    document.getElementById('sub').textContent=sec.sub;
    return;
  }
  if(sec.result){
    tg.style.display='none'; ov.style.display='none';
    const rcol=v=>v>=0?'#ff5c6c':'#4ea1ff', sgn=v=>(v>=0?'+':'')+v+'%';
    const mkcls=m=>m==='적중'?'ok':(m==='빗나감'?'no':'na');
    function ohlcHTML(o){
      if(!o) return '';
      return `<div class="card"><div class="cname">실제 등락 상세</div>`
        +`<div class="ohlc"><div><small>시가</small><b>${o.open.toLocaleString()}</b></div><div><small>고가</small><b style="color:#ff5c6c">${o.high.toLocaleString()}</b></div><div><small>저가</small><b style="color:#4ea1ff">${o.low.toLocaleString()}</b></div><div><small>종가</small><b>${o.close.toLocaleString()}</b></div></div>`
        +`<div class="vscore">시가 갭 ${sgn(o.gap)} · 장중(시가→종가) ${sgn(o.intraday)} · 일중 변동폭 ${o.range}% · 전일 ${o.prev.toLocaleString()}</div></div>`;
    }
    function rHTML(r){
      let h=`<div class="card"><div class="vscore">📌 판단일 ${r.date}(${r.wd}) · ${r.asof} 종가 대비 그날 등락${r.score!=null?' · 판단점수 '+(r.score>=0?'+':'')+r.score:''}</div>`
        +`<div style="display:flex;align-items:center;gap:10px;margin:6px 0 8px"><span class="vhead ${r.rcls}" style="font-size:18px">${r.regime} 예측</span><span class="vbadge ${r.hcls}" style="font-size:14px">${r.hit_label}</span></div>`
        +`<div class="vscore" style="font-size:15px;color:${rcol(r.kodex_return)};font-weight:800">실제 KODEX200 ${sgn(r.kodex_return)} (${r.close_prev.toLocaleString()}→${r.close_day.toLocaleString()})</div>`
        +`<div class="vsub" style="margin-top:6px">${r.summary}</div></div>`;
      h+=ohlcHTML(r.ohlc);
      h+=`<div class="card"><div class="cname" style="margin-bottom:4px">ETF별 판단 vs 실제</div>`
        +r.etfs.map(e=>`<div class="etfrow"><div><b>${e.name}</b><small>판단: ${e.verdict}</small></div><div style="text-align:right;line-height:1.3"><div style="font-weight:800;color:${rcol(e.ret)}">${sgn(e.ret)}</div><span class="vbadge ${e.ocls}" style="font-size:10px;padding:2px 7px">${e.outcome}</span></div></div>`).join('')+`</div>`;
      if(r.signals_review){ const ss=r.sig_summary||{};
        h+=`<div class="card"><div class="cname" style="margin-bottom:6px">신호 사후검증 — 적중 ${ss.aligned||0} / 빗나감 ${ss.missed||0}</div>`
          +r.signals_review.map(s=>`<div class="sigrow"><span class="mk ${mkcls(s.mark)}">${s.mark}</span><span class="sname">${s.name}</span><span class="sval">${s.val}</span></div>`).join('')+`</div>`; }
      if(r.analysis) h+=`<div class="card"><div class="cname" style="margin-bottom:4px">원인 해설</div><div class="vsub">${r.analysis}</div></div>`;
      return h;
    }
    function msg(v){ const hol=v.status==='holiday';
      return `<div class="card"><div class="mkt closed">🔴 ${v.date}(${v.wd}) ${hol?'휴장일':'기록 없음'}</div>`
        +`<div class="vsub" style="margin-top:6px">${hol?('전날이 휴장('+(v.reason||'')+')이라 판단이 없어 분석할 결과가 없습니다.'):'해당 날짜의 판단 기록이 없습니다.'}</div></div>`; }
    const hasP=sec.dates.length>0;
    const opts=sec.dates.map(d=>`<option value="${d}">${d}${d===sec.yv.date?' (어제)':''}</option>`).join('');
    const st=sec.yv.stats||{};
    const statsHTML=st.total?`<div class="card"><div class="cname" style="margin-bottom:4px">누적 판단 적중률</div><div class="vscore" style="font-size:14px;color:${st.rate>=50?'#3fb950':(st.rate==null?'#8b949e':'#f85149')};font-weight:800">${st.rate==null?'집계 대기(보합만)':('방향성 '+st.directional+'건 중 적중 '+st.hit+'건 = '+st.rate+'%')}</div><div class="vscore">전체 결과 기록 ${st.total}건 · 거래일 누적</div></div>`:'';
    wrap.innerHTML=statsHTML+(hasP?`<div class="card"><label class="dpick">📅 결과 날짜 <select id="rdate">${opts}</select></label></div>`:'')+`<div id="rbody"></div>`;
    const body=document.getElementById('rbody');
    if(sec.yv.status==='result'){ body.innerHTML=rHTML(sec.yv.result); if(hasP) document.getElementById('rdate').value=sec.yv.date; }
    else body.innerHTML=msg(sec.yv);
    if(hasP) document.getElementById('rdate').onchange=async(ev)=>{
      const d=ev.target.value;
      if(sec.yv.status==='result' && d===sec.yv.date){ body.innerHTML=rHTML(sec.yv.result); return; }
      body.innerHTML='<div class="card" style="color:#8b949e">불러오는 중…</div>';
      try{ const rr=await fetch('/r/'+d+'.json',{credentials:'same-origin'}); if(!rr.ok) throw 0; body.innerHTML=rHTML(await rr.json()); }
      catch(e){ body.innerHTML='<div class="card" style="color:#f85149">결과를 불러오지 못했습니다.</div>'; }
    };
    document.getElementById('inh').textContent='유의사항';
    document.getElementById('ins').innerHTML=sec.insights.map(t=>`<li>${t}</li>`).join('');
    document.getElementById('sub').textContent=sec.sub;
    return;
  }
  if(sec.statsview){
    tg.style.display='none'; ov.style.display='none';
    const s=sec.s;
    if(!s){ wrap.innerHTML='<div class="card" style="color:#8b949e">통계 데이터가 아직 없습니다. 거래일 판단이 쌓이면 표시됩니다.</div>'; document.getElementById('inh').textContent='유의사항'; document.getElementById('ins').innerHTML=sec.insights.map(t=>`<li>${t}</li>`).join(''); document.getElementById('sub').textContent=sec.sub; return; }
    const O=s.overall, rg=s.regime, fr=s.follow_return;
    const rpct=(h,n)=>n?Math.round(h/n*100)+'% ('+h+'/'+n+')':'—';
    let h=`<div class="card"><div class="cname">종합 적중률</div><div class="vhead ${O.rate==null?'neutral':(O.rate>=50?'bull':'bear')}" style="font-size:26px">${O.rate==null?'—':O.rate+'%'}</div><div class="vscore">방향성 판단 ${O.directional}건 중 적중 ${O.hit}건 · 전체 기록 ${O.total}건</div></div>`;
    h+=`<div class="card"><div class="cname" style="margin-bottom:6px">예측 방향별 적중률</div><div class="sigrow"><span class="sname">강세 예측</span><span class="sval">${rpct(rg.bull.hit,rg.bull.n)}</span></div><div class="sigrow"><span class="sname">약세 예측</span><span class="sval">${rpct(rg.bear.hit,rg.bear.n)}</span></div><div class="sigrow"><span class="sname">중립 예측</span><span class="sval">${rg.neutral.n||0}건</span></div></div>`;
    h+=`<div class="card"><div class="cname">판단추종 누적수익</div><div class="vhead ${fr>=0?'bull':'bear'}" style="font-size:22px">${fr>=0?'+':''}${fr}%</div><div class="vscore">${s.follow_n}거래일 · 강세→KODEX200 / 약세→인버스 / 중립→현금 (수수료 미반영)</div></div>`;
    const tb=s.tune.active?'<span class="vbadge buy" style="font-size:10px;padding:2px 7px">튜닝 ON</span>':`<span class="vbadge hold" style="font-size:10px;padding:2px 7px">튜닝 대기(${s.tune.min_samples}건↑)</span>`;
    h+=`<div class="card"><div class="cname" style="margin-bottom:6px;display:flex;justify-content:space-between;align-items:center">신호별 신뢰도 & 가중치 ${tb}</div>`
      +s.signals.map(sg=>`<div class="sigrow"><span class="sname">${sg.name}</span><span class="sval">적중 ${sg.rate==null?'—':sg.rate+'%'} · <b style="color:${sg.eff>sg.base?'#3fb950':(sg.eff<sg.base?'#f85149':'#8b949e')}">${sg.base}${sg.eff!==sg.base?'→'+sg.eff:''}</b></span></div>`).join('')+`</div>`;
    if(s.recent && s.recent.length){
      h+=`<div class="card"><div class="cname" style="margin-bottom:6px">최근 판단 이력</div>`
        +s.recent.map(r=>`<div class="sigrow"><span class="sname">${r.date}(${r.wd}) ${r.regime}</span><span class="vbadge ${r.hit_label==='적중'?'buy':(r.hit_label==='오답'?'avoid':'hold')}" style="font-size:10px;padding:2px 7px">${r.hit_label} ${r.kodex_return>=0?'+':''}${r.kodex_return}%</span></div>`).join('')+`</div>`;
    }
    wrap.innerHTML=h;
    document.getElementById('inh').textContent='유의사항';
    document.getElementById('ins').innerHTML=sec.insights.map(t=>`<li>${t}</li>`).join('');
    document.getElementById('sub').textContent=sec.sub+(s.updated?' · '+s.updated+' 갱신':'');
    return;
  }
  if(sec.list){
    tg.style.display='none'; ov.style.display='none';
    const groups={};
    sec.items.forEach(it=>{ (groups[it.house]=groups[it.house]||[]).push(it); });
    const houses=Object.keys(groups).sort((a,b)=>groups[b].length-groups[a].length||a.localeCompare(b,'ko'));
    wrap.innerHTML='<div class="rmeta">'+sec.items.length+'개 리포트 · '+houses.length+'개 증권사 · '+sec.asof+'</div>'
      +houses.map(hn=>'<div class="card"><div class="ghouse">'+hn+'<span>'+groups[hn].length+'</span></div>'
        +groups[hn].map(it=>`<a class="rpt" href="${it.url}" target="_blank" rel="noopener"><div class="rmain">${it.stock}</div><div class="rtitle">${it.title}</div></a>`).join('')
        +'</div>').join('');
    document.getElementById('inh').textContent='참고 — '+sec.title;
    document.getElementById('ins').innerHTML=sec.insights.map(t=>`<li>${t}</li>`).join('');
    document.getElementById('sub').textContent=sec.sub;
    return;
  }
  tg.style.display='flex'; ov.style.display='block';
  sec.series.forEach((s,i)=>{
    const el=document.createElement('div'); el.className='card';
    el.innerHTML=`<div class="chead">
        <div class="cname">${s.short}<small>${s.kr}</small></div>
        <div class="cval">${fmt(s.stats.last,s.dec)}<small>${s.unit||''}</small></div></div>
      <div class="badges">${sec.rate?badgePP(s.stats.d5,'5Y')+badgePP(s.stats.d1,'1Y'):badge(s.stats.chg5y,'5Y')+badge(s.stats.chg1y,'1Y')}</div>
      <div class="cwrap"><canvas id="cv_${SEC}_${i}"></canvas></div>`;
    wrap.appendChild(el);
  });
  const maxN = H==='5Y'?400:300;
  sec.series.forEach((s,i)=>{
    const id='cv_'+SEC+'_'+i;
    const src = H==='5Y'?s.full:s.oneY;
    const d=ds(src.labels,src.vals,maxN);
    if(cs[id]) cs[id].destroy();
    cs[id]=new Chart(document.getElementById(id), lineCfg(d.labels,d.vals,s.color,s.dec));
  });
  const rb=sec.rebased[H];
  const rebCfg={type:'line', data:{labels:rb.labels, datasets:rb.sets.map(x=>({
      label:x.label,data:x.data,borderColor:x.color,borderWidth:1.5,pointRadius:0,tension:.15,fill:false}))},
    options:{responsive:true,maintainAspectRatio:false,animation:false,
      interaction:{intersect:false,mode:'index'},
      plugins:{legend:{display:true,position:'top',labels:{boxWidth:10,font:{size:10}}}},
      scales:{x:{ticks:{maxTicksLimit:5,autoSkip:true},grid:{display:false}},
        y:{ticks:{maxTicksLimit:5},grid:{color:'#1c232c'}}}} };
  if(cs.reb) cs.reb.destroy();
  cs.reb=new Chart(document.getElementById('reb'), rebCfg);
  document.getElementById('rebl').textContent='('+sec.reblabel+')';
  document.getElementById('inh').textContent='핵심 시사점 — '+sec.title;
  document.getElementById('ins').innerHTML=sec.insights.map(t=>`<li>${t}</li>`).join('');
  document.getElementById('sub').textContent=sec.sub+' · 기준 '+D.meta.asof;
}
function setH(h){ H=h;
  document.getElementById('b5').classList.toggle('active',h==='5Y');
  document.getElementById('b1').classList.toggle('active',h==='1Y'); render(); }
function setSec(i){ SEC=i;
  [...document.querySelectorAll('#tabs button')].forEach((b,j)=>b.classList.toggle('active',j===i));
  render(); }

const tb=document.getElementById('tabs');
D.sections.forEach((s,i)=>{ const b=document.createElement('button');
  b.textContent=s.title; b.onclick=()=>setSec(i); if(i===0)b.className='active'; tb.appendChild(b); });
document.getElementById('foot').innerHTML=
  `데이터 출처: 네이버 금융 · Yahoo Finance(선물·지수) · World Bank Pink Sheet · 금융투자협회 · 한국해양진흥공사(KOBC) · BIS(국제결제은행) · 스냅샷 ${D.meta.built}<br>투자 판단 참고용, 실시간 아님`;
render();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    from datetime import datetime
    DATA, asof = main()
    built = datetime.now().strftime("%Y-%m-%d %H:%M KST")
    html = HTML.replace("__DATA__", json.dumps(DATA, ensure_ascii=False)).replace("__BUILT__", built)
    out = os.environ.get("DASH_SITE", os.path.join(OUTDIR, "index.html"))
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print("wrote", out, f"({len(html)//1024} KB) asof {asof.date()}")
