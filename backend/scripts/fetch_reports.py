"""Fetch daily KR broker stock reports (네이버 금융 리서치 종목분석) -> reports.json.
Each 증권사 종목 리포트 = de-facto 추천/커버리지 종목, with a link to the report.
DAILY snapshot (그날 그날 기준), not a time series. Source is EUC-KR HTML.
Note: Naver research list has no 투자의견/추천제외 field; sell-side coverage is ~all buy-side.
"""
import urllib.request, re, json, os
from datetime import datetime

OUTDIR = os.environ.get("DASH_OUTDIR", "/home/hcpark/antigravity/backend/runs/fx")
BASE = "https://finance.naver.com/research"
UA = {"User-Agent": "Mozilla/5.0"}

def txt(x):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", x)).strip()

def fetch_page(pg):
    url = f"{BASE}/company_list.naver?page={pg}"
    h = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=25).read().decode("euc-kr", "ignore")
    out = []
    for r in re.findall(r"<tr[^>]*>(.*?)</tr>", h, re.S):
        if "company_read" not in r:
            continue
        cells = [txt(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", r, re.S)]
        if len(cells) < 5 or not cells[0]:
            continue
        nid = re.search(r"company_read\.naver\?nid=(\d+)", r)
        date = next((c for c in cells if re.match(r"\d\d\.\d\d\.\d\d", c)), "")
        if not nid or not date:
            continue
        out.append({"stock": cells[0], "title": cells[1][:70], "house": cells[2],
                    "date": "20" + date, "nid": nid.group(1),
                    "url": f"{BASE}/company_read.naver?nid={nid.group(1)}"})
    return out

def main():
    rows = []
    for pg in (1, 2):
        try:
            rows += fetch_page(pg)
        except Exception as e:
            print("  warn page", pg, e)
    # dedup by nid
    seen, uniq = set(), []
    for r in rows:
        if r["nid"] in seen:
            continue
        seen.add(r["nid"]); uniq.append(r)
    if not uniq:
        raise SystemExit("no reports parsed — source may have changed")
    asof = max(r["date"] for r in uniq)
    today = [r for r in uniq if r["date"] == asof]
    data = {"asof": asof, "fetched": datetime.now().strftime("%Y-%m-%d %H:%M KST"),
            "items": today, "n": len(today)}
    with open(os.path.join(OUTDIR, "reports.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    print(f"reports: asof {asof} · {len(today)} 리포트 · {len(set(r['house'] for r in today))} 증권사")

if __name__ == "__main__":
    main()
