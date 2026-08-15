"""Build a self-contained mobile-optimized FX dashboard (index.html) from fx_krw_5y.csv.
Embeds real data (Naver) + Chart.js from CDN. Dark theme, single-column, responsive.
"""
import pandas as pd, json, os
from datetime import datetime, timedelta

OUTDIR = "/home/hcpark/antigravity/backend/runs/fx"
df = pd.read_csv(os.path.join(OUTDIR, "fx_krw_5y.csv"), index_col=0, parse_dates=True).sort_index()

CURR = [
    ("USD/KRW", "USD/KRW", "미국 달러", "#4ea1ff"),
    ("CNY/KRW", "CNY/KRW", "중국 위안", "#ff5c6c"),
    ("EUR/KRW", "EUR/KRW", "유로", "#4cd07d"),
    ("JPY/KRW (per 100)", "JPY/KRW", "일본 엔(100엔)", "#b892ff"),
]

today = df.index.max()
d1 = today - timedelta(days=365)
d5_start = df.index.min()

def series_payload(sub):
    labels = [d.strftime("%Y-%m-%d") for d in sub.index]
    out = {"labels": labels}
    for col, short, _, _ in CURR:
        out[short] = [round(float(v), 2) for v in sub[col].values]
    return out

full = series_payload(df)
oneY = series_payload(df[df.index >= d1])

# stats per currency for both horizons
def stats(col):
    s = df[col].dropna()
    s1 = s[s.index >= d1]
    return {
        "last": round(float(s.iloc[-1]), 2),
        "chg5y": round((s.iloc[-1] / s.iloc[0] - 1) * 100, 1),
        "chg1y": round((s1.iloc[-1] / s1.iloc[0] - 1) * 100, 1),
    }
ST = {short: stats(col) for col, short, _, _ in CURR}

meta = {
    "asof": today.strftime("%Y-%m-%d"),
    "start5y": d5_start.strftime("%Y-%m-%d"),
    "npts": len(df),
    "built": datetime.now().strftime("%Y-%m-%d %H:%M KST"),
}

DATA = {"full": full, "oneY": oneY, "stats": ST,
        "curr": [{"short": s, "kr": kr, "color": c} for _, s, kr, c in CURR],
        "meta": meta}

html = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<meta name="theme-color" content="#0d1117">
<title>한국 증시 분석 · 환율</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
  :root{ --bg:#0d1117; --card:#161b22; --border:#232a34; --fg:#e6edf3; --sub:#8b949e; --up:#ff5c6c; --dn:#4ea1ff; }
  *{ box-sizing:border-box; -webkit-tap-highlight-color:transparent; }
  body{ margin:0; background:var(--bg); color:var(--fg);
    font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Malgun Gothic",system-ui,sans-serif;
    padding:16px 14px 40px; max-width:720px; margin:0 auto; }
  h1{ font-size:20px; margin:4px 0 2px; letter-spacing:-.3px; }
  .sub{ color:var(--sub); font-size:12px; margin-bottom:14px; }
  .toggle{ display:flex; gap:8px; margin-bottom:16px; }
  .toggle button{ flex:1; padding:10px; border-radius:10px; border:1px solid var(--border);
    background:var(--card); color:var(--sub); font-size:14px; font-weight:600; }
  .toggle button.active{ background:#1f6feb; color:#fff; border-color:#1f6feb; }
  .card{ background:var(--card); border:1px solid var(--border); border-radius:14px;
    padding:14px 14px 8px; margin-bottom:14px; }
  .chead{ display:flex; align-items:baseline; justify-content:space-between; margin-bottom:6px; }
  .cname{ font-size:15px; font-weight:700; }
  .cname small{ color:var(--sub); font-weight:500; font-size:11px; margin-left:5px; }
  .cval{ font-size:18px; font-weight:800; font-variant-numeric:tabular-nums; }
  .badges{ display:flex; gap:6px; margin:2px 0 8px; }
  .badge{ font-size:11px; padding:2px 8px; border-radius:20px; font-weight:700;
    font-variant-numeric:tabular-nums; }
  .badge span{ color:var(--sub); font-weight:600; margin-right:3px; }
  .pos{ background:rgba(255,92,108,.15); color:var(--up); }
  .neg{ background:rgba(78,161,255,.15); color:var(--dn); }
  .cwrap{ position:relative; height:150px; }
  .overlay .cwrap{ height:260px; }
  .insights{ background:var(--card); border:1px solid var(--border); border-radius:14px; padding:16px; }
  .insights h2{ font-size:15px; margin:0 0 10px; }
  .insights li{ font-size:13px; line-height:1.6; color:#c9d1d9; margin-bottom:8px; }
  .foot{ color:var(--sub); font-size:11px; text-align:center; margin-top:20px; line-height:1.6; }
</style>
</head>
<body>
  <h1>🇰🇷 한국 증시 분석 — 환율</h1>
  <div class="sub" id="sub"></div>
  <div class="toggle">
    <button id="b5" class="active" onclick="setH('5Y')">최근 5년</button>
    <button id="b1" onclick="setH('1Y')">최근 1년</button>
  </div>
  <div id="cards"></div>
  <div class="card overlay">
    <div class="cname" style="margin-bottom:8px">상대 비교 <small id="rebl">(시작=100 · 높을수록 원화 약세)</small></div>
    <div class="cwrap"><canvas id="reb"></canvas></div>
  </div>
  <div class="insights">
    <h2>핵심 시사점 (증시 관점)</h2>
    <ul>
      <li><b>원화 전방위 약세(5년):</b> 달러·유로·위안 대비 원화가 약 30% 절하 — 특정 통화 이슈가 아닌 <b>원화 자체의 구조적 약세</b>. 수출주엔 우호적이나 외국인 수급엔 부담.</li>
      <li><b>최근 1년은 위안화가 주도:</b> CNY/KRW가 달러보다 강하게 절상 — 대중 교역·중국 관련주 원가 부담 요인.</li>
      <li><b>엔화만 예외:</b> 5년 기준 원화가 엔 대비 오히려 강세 유지 — 대일 경쟁 수출업종(자동차·철강·기계) 상대적 불리.</li>
      <li><b>USD/KRW 1,500원대 고점권:</b> 환율 부담이 밸류에이션·외국인 순매수의 실질 변수.</li>
    </ul>
  </div>
  <div class="foot" id="foot"></div>

<script>
const D = __DATA__;
let H = '5Y';
const cs = {};
Chart.defaults.color = '#8b949e';
Chart.defaults.font.size = 10;

function ds(labels, vals, maxN){
  // downsample for perf on long horizon
  const n = labels.length; if(n<=maxN) return {labels, vals};
  const step = Math.ceil(n/maxN); const L=[],V=[];
  for(let i=0;i<n;i+=step){ L.push(labels[i]); V.push(vals[i]); }
  if(L[L.length-1]!==labels[n-1]){ L.push(labels[n-1]); V.push(vals[n-1]); }
  return {labels:L, vals:V};
}
function fmt(x){ return x.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2}); }
function badge(v){ const c=v>=0?'pos':'neg'; const s=(v>=0?'+':'')+v.toFixed(1)+'%'; return `<span class="badge ${c}"><span>%L</span>${s}</span>`; }

function buildCards(){
  const wrap = document.getElementById('cards'); wrap.innerHTML='';
  D.curr.forEach(c=>{
    const st = D.stats[c.short];
    const el = document.createElement('div'); el.className='card';
    el.innerHTML = `
      <div class="chead">
        <div class="cname">${c.short}<small>${c.kr}</small></div>
        <div class="cval">${fmt(st.last)}</div>
      </div>
      <div class="badges">
        ${badge(st.chg5y).replace('%L','5Y')}
        ${badge(st.chg1y).replace('%L','1Y')}
      </div>
      <div class="cwrap"><canvas id="cv_${c.short.replace('/','_')}"></canvas></div>`;
    wrap.appendChild(el);
  });
}

function lineCfg(labels, data, color, fill){
  return { type:'line',
    data:{ labels, datasets:[{ data, borderColor:color, borderWidth:1.6,
      pointRadius:0, tension:.15, fill:fill||false,
      backgroundColor: fill? color+'22' : undefined }]},
    options:{ responsive:true, maintainAspectRatio:false, animation:false,
      interaction:{intersect:false, mode:'index'},
      plugins:{ legend:{display:false}, tooltip:{ enabled:true,
        callbacks:{ label:(c)=>' '+fmt(c.parsed.y) } } },
      scales:{ x:{ ticks:{ maxTicksLimit:5, autoSkip:true }, grid:{display:false} },
        y:{ ticks:{ maxTicksLimit:5, callback:v=>Math.round(v).toLocaleString() },
          grid:{ color:'#1c232c' } } } } };
}

function render(){
  const src = H==='5Y' ? D.full : D.oneY;
  const maxN = H==='5Y' ? 400 : 260;
  D.curr.forEach(c=>{
    const id = 'cv_'+c.short.replace('/','_');
    const s = ds(src.labels, src[c.short], maxN);
    if(cs[id]) cs[id].destroy();
    cs[id] = new Chart(document.getElementById(id), lineCfg(s.labels, s.vals, c.color, true));
  });
  // rebased overlay
  const s0 = ds(src.labels, src[D.curr[0].short], maxN);
  const rebCfg = { type:'line', data:{ labels:s0.labels, datasets: D.curr.map(c=>{
      const s = ds(src.labels, src[c.short], maxN);
      const base = s.vals[0];
      return { label:c.short, data:s.vals.map(v=>+(v/base*100).toFixed(2)),
        borderColor:c.color, borderWidth:1.5, pointRadius:0, tension:.15, fill:false };
    })},
    options:{ responsive:true, maintainAspectRatio:false, animation:false,
      interaction:{intersect:false, mode:'index'},
      plugins:{ legend:{display:true, position:'top', labels:{boxWidth:10, font:{size:10}} },
        tooltip:{enabled:true} },
      scales:{ x:{ ticks:{maxTicksLimit:5, autoSkip:true}, grid:{display:false} },
        y:{ ticks:{maxTicksLimit:5}, grid:{color:'#1c232c'} } } } };
  if(cs.reb) cs.reb.destroy();
  cs.reb = new Chart(document.getElementById('reb'), rebCfg);
}

function setH(h){ H=h;
  document.getElementById('b5').classList.toggle('active', h==='5Y');
  document.getElementById('b1').classList.toggle('active', h==='1Y');
  render();
}

document.getElementById('sub').textContent =
  `기준일 ${D.meta.asof} · ${D.meta.start5y}~ 일봉 ${D.meta.npts.toLocaleString()}개 · 출처 네이버`;
document.getElementById('foot').innerHTML =
  `데이터: 네이버 금융 시장지표(원화 대비 종가) · 스냅샷 생성 ${D.meta.built}<br>투자 판단 참고용, 실시간 아님`;
buildCards();
render();
</script>
</body>
</html>
"""

html = html.replace("__DATA__", json.dumps(DATA, ensure_ascii=False))
out = os.path.join(OUTDIR, "index.html")
with open(out, "w", encoding="utf-8") as f:
    f.write(html)
print("wrote", out, f"({len(html)//1024} KB)")
