# -*- coding: utf-8 -*-
"""분위기 점검 + **판정 원장·사후 채점** (2026-09-14).

대표님 지시 이력:
  14:06 "다음 재개 시작은 수동으로. 30분마다 분위기를 체크해서 다시 상향의
         흐름이라고 파악되면 재개를 건의해줘."
  14:38 "지나간 재개 건의 내용과 그 결과를 항상 지속적으로 분석해서 다음
         재개 건의때 참고하도록 해."

그래서 이 도구는 두 가지를 한다.
  ㄱ. **지금 판정** — 미리 못 박은 다섯 기준으로 건의/보류를 정한다
  ㄴ. **지난 판정 채점** — 매 판정을 원장에 남기고, 그 뒤 실제로 어떻게
      됐는지를 이어 붙여 **기준에 구별력이 있는지** 스스로 검증한다

⚠ 채점의 요점은 "맞췄나"가 아니라 **"🟢 뒤가 🛑 뒤보다 나았나"**다.
  둘이 같으면 이 기준은 장식이다 — 그러면 그렇게 보고해야 한다.
⚠ 기준은 결과를 보고 바꾸지 않는다(교훈#95). 맹점을 찾으면 **다음 주기부터**
  적용하고, 그 판정이 어느 판본으로 내려졌는지 원장에 함께 남긴다.
⚠ 이건 예측이 아니라 관측이다 — 거래당 손익의 자기상관은 +0.011 이다.
  "오를 것"이 아니라 "지금 이 규칙이 먹히고 있나"만 본다.
"""
import json
import pathlib
import numpy as np
import pandas as pd

ROOT = pathlib.Path("/home/mint/auto_trading/backend")
PAPER = ROOT / "runs" / "kinematics_paper"
STATE = ROOT / "runs" / "regime_streak.json"
LOG = ROOT / "runs" / "regime_log.jsonl"          # 판정 원장

CRITERIA_VERSION = "v2 (①②③④⑤ · ⑤는 2026-09-14 14:40 추가)"
# ⚠ 2026-09-15 09:12/09:20 규칙 교체에 맞춰 갱신했다. 라이브가 바뀌면
#   여기도 같이 바꿔야 한다 — 안 바꾸면 **없는 규칙을 보고 판정한다**
#   (09-15 10:05 에 실제로 옛 쌍으로 "정지 유지"를 내고 있었다).
TWINS = {"s6both_h240": "계좌15 쌍 s6양다리",
         "s3short_anti": "계좌8 쌍 역확인3"}
SHORTS = {
    "s3short_h4": "충격240", "s3short_h4ec": "충격240냉", "s3short_h1": "충격60",
    "s3short_imp": "충격숏3", "s3short_impns": "무손숏3", "s3short_dir": "방향숏3",
    "s3short_conf": "확인숏3", "s3short_anti": "역확인3",
}
NEED_PLUS_RATIO, NEED_STOP_MAX, NEED_STREAK, NEED_PLUS6 = 0.60, 25.0, 2, 0.50
FWD_HOURS = (2, 6, 12)


def load(tag):
    p = PAPER / tag / "trades.csv"
    if not p.exists():
        return None
    d = pd.read_csv(p)
    for c in ("entry_ts", "closed_ts"):
        d[c] = pd.to_datetime(d[c], utc=True, format="mixed")
    return d


# ⚠ **TWINS 도 반드시 포함한다.** 2026-09-15 15:25 교체에서 TWINS 만
#   `s6both_h240` 으로 바꾸고 여기를 안 고쳐 `KeyError` 로 판정이 통째로 죽었다.
#   교체 점검표의 "네 곳"은 **파일 단위**이지 줄 단위가 아니다 —
#   한 파일 안에 참조가 둘 이상일 수 있다(교훈#88).
LED = {t: load(t) for t in {**SHORTS, **TWINS}}
now = pd.Timestamp.now(tz="UTC")

# ── ㄱ. 지금 판정 ───────────────────────────────────────────────
print("■ 분위기 점검 — %s KST · 기준 %s"
      % (now.tz_convert("Asia/Seoul").strftime("%m-%d %H:%M"), CRITERIA_VERSION))
print("\n  창별 페이퍼 성적 (청산 기준)")
print("   %-12s" % "갈래" + "".join(" %16s" % ("최근 %dh" % h) for h in (6, 12, 24)))
stat24, stat6 = {}, {}
for tag, nm in SHORTS.items():
    d = LED[tag]
    if d is None:
        continue
    line = "   %-12s" % nm
    for h in (6, 12, 24):
        m = d[d.closed_ts >= now - pd.Timedelta(hours=h)]
        if len(m) == 0:
            line += " %16s" % "-"
            continue
        line += " %7.3f%%(%2d건)" % (m.net_pct.mean(), len(m))
        if h == 24:
            stat24[tag] = (m.net_pct.mean(), len(m), 100 * m.stopped.mean())
        if h == 6:
            stat6[tag] = (m.net_pct.mean(), len(m))
    print(line)

print("\n  판정 기준 (미리 못 박은 값)")
ok1 = all(stat24.get(t, (-1, 0, 100))[0] > 0 for t in TWINS)
for t, nm in TWINS.items():
    v = stat24.get(t)
    print("   ① %-18s 최근24h 거래당 %s → %s"
          % (nm, ("%+.3f%% (%d건)" % (v[0], v[1])) if v else "거래 없음",
             "✅" if v and v[0] > 0 else "❌"))
plus = [t for t, v in stat24.items() if v[0] > 0]
ratio = len(plus) / max(1, len(stat24))
ok2 = ratio >= NEED_PLUS_RATIO
print("   ② 플러스 갈래 비율 %d/%d = %.0f%% (필요 %.0f%%) → %s"
      % (len(plus), len(stat24), 100 * ratio, 100 * NEED_PLUS_RATIO, "✅" if ok2 else "❌"))
tot_n = sum(v[1] for v in stat24.values()) or 1
stop = sum(v[2] * v[1] for v in stat24.values()) / tot_n if stat24 else 100.0
ok3 = stop <= NEED_STOP_MAX
print("   ③ 최근24h 손절율 %.1f%% (필요 ≤%.0f%%) → %s"
      % (stop, NEED_STOP_MAX, "✅" if ok3 else "❌"))
plus6 = [t for t, v in stat6.items() if v[0] > 0]
ratio6 = len(plus6) / max(1, len(stat6))
ok5 = ratio6 >= NEED_PLUS6
print("   ⑤ 최근6h 플러스 갈래 %d/%d = %.0f%% (필요 %.0f%%) → %s"
      % (len(plus6), len(stat6), 100 * ratio6, 100 * NEED_PLUS6, "✅" if ok5 else "❌"))

hit = ok1 and ok2 and ok3 and ok5
try:
    st = json.loads(STATE.read_text())
except Exception:
    st = {"streak": 0}
st["streak"] = st.get("streak", 0) + 1 if hit else 0
st["last"] = now.isoformat()
STATE.write_text(json.dumps(st), encoding="utf-8")
ok4 = st["streak"] >= NEED_STREAK
print("   ④ 연속 충족 %d회 (필요 %d회) → %s" % (st["streak"], NEED_STREAK, "✅" if ok4 else "❌"))

verdict = bool(hit and ok4)
miss = [n for n, o in (("①라이브쌍", ok1), ("②플러스비율", ok2), ("③손절율", ok3),
                       ("④연속2회", ok4), ("⑤최근6h", ok5)) if not o]
print("\n  ▶ 판정: %s" % ("🟢 **재개를 건의한다** — 다섯 기준 모두 충족"
                         if verdict else "🛑 기준 미충족 — 정지된 계좌가 있으면 재개하지 않는다"))
if miss:
    print("     미충족: " + " · ".join(miss))

# ── 판정 원장에 남긴다 ──────────────────────────────────────────
rec = {"ts": now.isoformat(), "verdict": verdict, "version": CRITERIA_VERSION,
       "streak": st["streak"], "miss": miss,
       "twin24": {t: round(stat24[t][0], 4) for t in TWINS if t in stat24},
       "plus24": round(ratio, 3), "plus6": round(ratio6, 3),
       "stop24": round(stop, 2)}
with LOG.open("a", encoding="utf-8") as f:
    f.write(json.dumps(rec, ensure_ascii=False) + "\n")

# ── ㄴ. 지난 판정 채점 ─────────────────────────────────────────
print("\n■ 지난 판정의 사후 성적 — **기준에 구별력이 있나**")
try:
    hist = [json.loads(l) for l in LOG.read_text(encoding="utf-8").splitlines() if l.strip()]
except Exception:
    hist = []
hist = [h for h in hist if h["ts"] != rec["ts"]]        # 방금 것은 아직 채점 불가


def fwd(t0, hours):
    """판정 시각 t0 이후 `hours` 안에 청산된 **라이브 쌍** 거래의 거래당 손익."""
    vals = []
    for tag in TWINS:
        d = LED[tag]
        if d is None:
            continue
        m = d[(d.closed_ts > t0) & (d.closed_ts <= t0 + pd.Timedelta(hours=hours))]
        vals.extend(m.net_pct.tolist())
    return (float(np.mean(vals)), len(vals)) if vals else (None, 0)


if not hist:
    print("   아직 채점할 지난 판정이 없다 — 이번이 첫 기록이다.")
else:
    rows = []
    for h in hist:
        t0 = pd.Timestamp(h["ts"])
        r = {"ts": t0, "verdict": h["verdict"]}
        for H in FWD_HOURS:
            if now - t0 >= pd.Timedelta(hours=H):
                r["f%d" % H], r["n%d" % H] = fwd(t0, H)
            else:
                r["f%d" % H], r["n%d" % H] = None, 0
        rows.append(r)
    R = pd.DataFrame(rows)
    print("   판정 %d건 (🟢 %d · 🛑 %d) · 채점 가능한 것만 아래에 센다"
          % (len(R), int(R.verdict.sum()), int((~R.verdict).sum())))
    print("   %-8s %6s" % ("판정", "건수") + "".join(" %14s" % ("이후 %dh" % H) for H in FWD_HOURS))
    for lab, sel in (("🟢 건의", R.verdict), ("🛑 보류", ~R.verdict)):
        g = R[sel]
        line = "   %-8s %6d" % (lab, len(g))
        for H in FWD_HOURS:
            v = g["f%d" % H].dropna()
            line += " %14s" % ("%+.3f%%(%d)" % (v.mean(), len(v)) if len(v) else "-")
        print(line)
    for H in FWD_HOURS:
        a = R[R.verdict]["f%d" % H].dropna()
        b = R[~R.verdict]["f%d" % H].dropna()
        if len(a) and len(b):
            print("   ▶ 이후 %dh 차이(건의−보류) %+.3f%%p — %s"
                  % (H, a.mean() - b.mean(),
                     "구별력 있음" if a.mean() > b.mean() else "**구별력 없음/역방향**"))
        else:
            print("   ▶ 이후 %dh — 한쪽 표본이 없어 비교 불가" % H)
    print("   ⚠ 표본이 찰 때까지 이 표로 기준을 바꾸지 않는다. **관측만 쌓는다.**")
