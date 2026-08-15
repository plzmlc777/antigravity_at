"""주요국 대원화 환율 수집(네이버) + 5년/1년 그래프.
Currencies: USD, CNY, EUR, JPY (all vs KRW). JPY quoted per 100 JPY by Naver.
Output: /home/hcpark/antigravity/backend/runs/fx/*.png + csv
"""
import json, time, sys, os
from datetime import datetime, timedelta
import urllib.request
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

OUTDIR = "/home/hcpark/antigravity/backend/runs/fx"
os.makedirs(OUTDIR, exist_ok=True)

CODES = {
    "USD/KRW": "FX_USDKRW",
    "CNY/KRW": "FX_CNYKRW",
    "EUR/KRW": "FX_EURKRW",
    "JPY/KRW (per 100)": "FX_JPYKRW",
}
UA = {"User-Agent": "Mozilla/5.0"}
BASE = "https://m.stock.naver.com/front-api/marketIndex/prices?category=exchange&reutersCode={code}&page={page}&pageSize=10"

def fetch_series(code, min_date):
    rows = {}
    page = 1
    while True:
        url = BASE.format(code=code, page=page)
        ok = False
        for attempt in range(4):
            try:
                req = urllib.request.Request(url, headers=UA)
                with urllib.request.urlopen(req, timeout=20) as resp:
                    d = json.loads(resp.read().decode())
                res = d.get("result")
                if not res:
                    return rows
                for r in res:
                    dt = r["localTradedAt"]
                    px = float(r["closePrice"].replace(",", ""))
                    rows[dt] = px
                ok = True
                break
            except Exception as e:
                time.sleep(0.4)
        if not ok:
            print(f"  ! page {page} failed for {code}", file=sys.stderr)
            return rows
        oldest = min(rows.keys())
        if oldest <= min_date:
            return rows
        page += 1
        time.sleep(0.05)

def main():
    today = datetime(2026, 7, 4)
    d5 = (today - timedelta(days=365 * 5 + 5)).strftime("%Y-%m-%d")
    series = {}
    for name, code in CODES.items():
        print(f"fetching {name} ...")
        rows = fetch_series(code, d5)
        s = pd.Series(rows)
        s.index = pd.to_datetime(s.index)
        s = s.sort_index()
        s = s[s.index >= pd.to_datetime(d5)]
        series[name] = s
        print(f"  {name}: {len(s)} pts  {s.index.min().date()} -> {s.index.max().date()}")

    df = pd.DataFrame(series).sort_index()
    df.to_csv(os.path.join(OUTDIR, "fx_krw_5y.csv"))

    d1 = pd.to_datetime((today - timedelta(days=365)).strftime("%Y-%m-%d"))

    for horizon, start in [("5Y", pd.to_datetime(d5)), ("1Y", d1)]:
        sub = df[df.index >= start]
        fig, axes = plt.subplots(2, 2, figsize=(15, 9))
        colors = {"USD/KRW": "#1f77b4", "CNY/KRW": "#d62728",
                  "EUR/KRW": "#2ca02c", "JPY/KRW (per 100)": "#9467bd"}
        for ax, name in zip(axes.flat, CODES.keys()):
            s = sub[name].dropna()
            ax.plot(s.index, s.values, color=colors[name], lw=1.2)
            last = s.iloc[-1]; first = s.iloc[0]
            chg = (last / first - 1) * 100
            ax.set_title(f"{name}   last={last:,.2f}  ({chg:+.1f}% over {horizon})",
                         fontsize=11, fontweight="bold")
            ax.grid(alpha=0.3)
            ax.xaxis.set_major_locator(mdates.AutoDateLocator())
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
            ax.axhline(last, color="gray", ls="--", lw=0.6, alpha=0.6)
            for lbl in ax.get_xticklabels():
                lbl.set_rotation(30); lbl.set_ha("right")
        fig.suptitle(f"KRW Exchange Rates vs Major Currencies — {horizon} "
                     f"(as of {df.index.max().date()}, source: Naver)",
                     fontsize=14, fontweight="bold")
        fig.tight_layout(rect=[0, 0, 1, 0.97])
        out = os.path.join(OUTDIR, f"fx_krw_{horizon}.png")
        fig.savefig(out, dpi=110)
        print("saved", out)

    # normalized overlay (rebased to 100) for both horizons
    for horizon, start in [("5Y", pd.to_datetime(d5)), ("1Y", d1)]:
        sub = df[df.index >= start].dropna()
        norm = sub / sub.iloc[0] * 100
        fig, ax = plt.subplots(figsize=(14, 7))
        for name in CODES.keys():
            ax.plot(norm.index, norm[name], lw=1.4, label=name)
        ax.axhline(100, color="gray", ls="--", lw=0.7)
        ax.set_title(f"KRW FX — Rebased to 100 at start of {horizon} "
                     f"(higher = KRW weaker)", fontsize=13, fontweight="bold")
        ax.legend(); ax.grid(alpha=0.3)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        for lbl in ax.get_xticklabels():
            lbl.set_rotation(30); lbl.set_ha("right")
        fig.tight_layout()
        out = os.path.join(OUTDIR, f"fx_krw_rebased_{horizon}.png")
        fig.savefig(out, dpi=110)
        print("saved", out)

    # print summary table
    print("\n=== Summary (latest) ===")
    print(df.tail(1).T)

if __name__ == "__main__":
    main()
