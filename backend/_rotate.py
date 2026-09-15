# -*- coding: utf-8 -*-
"""🔄 동적 전략 교체 — 갈래 순위와 교체 건의 (2026-09-15 대표님 지시).

"이제 시시각각 그때의 국면과 각 전략의 상승세를 파악해서 동적으로 전략을
 적용하는 방식으로 전환된거야. 아주 기민하고 과감하게 생각하고 행동해야 해."

그래서 매 정기 보고마다 **전 갈래를 줄 세우고 교체할지 말지 결론을 낸다.**
관측만 하고 넘기지 않는다.

⚠ 근거는 **최근 창 실측**뿐이다 — 아카이브 6년 검정·최대통계량 귀무는 안 쓴다
  (대표님 지시 09-15 09:08). 국면이 바뀌면 또 갈아타면 된다.
⚠ 두 계좌를 **같은 계열로 채우지 않는다** — 09-13 에 imp 두 계좌가 함께
  무너졌다. 후보와 **상대 계좌** 규칙의 3시간 토막 상관을 본다.
⚠ 한 주기 튐으로 갈아타지 않는다 — 09-14 에 "⑤만 넘으면"·"한 칸 남음"을
  두 번 올렸다가 다음 주기에 뒤집혔다. **연속 2회(=1시간)** 우위를 요구한다.
  그 이상은 기다리지 않는다. 그게 이 체계에서 '기민함'의 값이다.

⚠ 수준(누적)만 보면 **한 토막 대박**으로 1위가 된 갈래에 실자금을 넘긴다.
  09-15 방향숏3 의 24h +10.26% 는 09-15 00:00 한 토막(+12.05)의 잔상이었고,
  그 뒤 세 토막은 하나도 플러스가 아니었다(최대 토막 제외 합 **-3.64**).
  그래서 ⑥ **지속성**을 신설한다(2026-09-15 대표님 승인).
  ⑥ 은 "기울기가 미래 수익을 예측한다"는 주장이 **아니다** — 아카이브 6년
  검정에서 기울기 관문은 이미 기각됐다(43,764거래, p 0.8450, 인계문 §8).
  **한 토막이 수준 지표를 부풀려 실자금을 잘못 옮기는 것을 막는 안전장치**다.

교체 건의 조건 (미리 못 박는다 — 값을 보고 고치지 않는다)
  ① 후보의 12h·24h 자본%가 **둘 다** 현행보다 높다
  ② 후보의 24h 자본% > 0
  ③ 후보와 **상대 계좌** 규칙의 상관 < +0.5
  ④ 후보의 24h 손절율 <= 45%
  ⑤ ①~④ 가 **연속 2회** 유지
  ⑥ 후보의 최근 4토막 중 **플러스 토막 >= 3** 이고 **최대 토막 제외 합 > 0**

경고 (교체 조건이 아니다 — 보고 ①항에 올리기 위한 표식)
  현행 규칙의 최근 4토막 중 플러스 토막 <= 1 이면 ⚠ 를 찍는다.
  대안이 없어 유지하더라도 **대표님이 그 사실을 알고 유지하셔야** 한다.
"""
import json
import pathlib
import numpy as np
import pandas as pd

ROOT = pathlib.Path("/home/mint/auto_trading/backend")
PAPER = ROOT / "runs" / "kinematics_paper"
STREAK = ROOT / "runs" / "rotate_streak.json"
TOLL = 0.1004
CORR_MAX, STOP_MAX, NEED_STREAK = 0.50, 45.0, 2
# ⑥ 지속성 — 최근 PERSIST_W 토막 중 플러스가 PERSIST_MIN 개 이상이고
#   최대 토막을 빼고도 합이 양수여야 한다. WARN_MAX 이하면 현행에 경고.
PERSIST_W, PERSIST_MIN, WARN_MAX = 4, 3, 1
# ⚠ 토막 경계를 1시간만 밀어도 ⑥ 판정이 뒤집힌다(2026-09-15 실측: 역확인3
#   2/4 탈락 → 4/4 통과). 교훈#109 — 슬롯 타이밍 운이 성적을 지배한다.
#   그래서 격자를 PERSIST_OFF 만큼 밀어 여러 번 재고 **중앙값**을 쓴다.
#   '전 격자 통과'(최댓값 대신 최솟값)도 검토했으나, 3슬롯·3시간 토막의
#   잡음에서는 어떤 후보도 못 넘어 교체가 영구히 얼어붙는다.
PERSIST_OFF = (0, 1, 2)

# 페이퍼 갈래 → (이름, 슬롯, 선별 성격)
BR = {
    "s3short_dir":   ("방향숏3",   3, "떨어지는 종목 숏"),
    "s3short_anti":  ("역확인3",   3, "오르는 종목 숏"),
    "s3short_conf":  ("확인숏3",   3, "꺾이는 종목 숏"),
    "s6both_imp":    ("충격스프3", 6, "롱3+숏3 양다리"),
    "s3short_imp":   ("충격숏3",   3, "imp 최저 숏 480분"),
    "s3short_h4":    ("충격240",   3, "imp 최저 숏 240분"),
    "s3short_h4ec":  ("충격240냉", 3, "imp 최저 숏 240분 만기냉각"),
    "s3short_h1":    ("충격60",    3, "imp 최저 숏 60분"),
    "s3short_impns": ("무손숏3",   3, "imp 최저 숏 무손절"),
    # ── 2026-09-15 대표님 승인으로 **후보 풀 확장** ───────────────────
    #
    # ⚠ 이 목록이 곧 후보 풀이다. 여기 없는 갈래는 아무리 좋아도
    #   **순위표에도 교체 판정에도 안 나온다.** 09-15 오후에 s6양다리가
    #   조건 ①~⑥ 을 전부 통과하고 있었는데 목록에 없어서 몇 시간째
    #   "교체 후보 없음" 이 찍혔다 — 조건은 제대로 돌았고 **입력이 빠져 있었다**
    #   (교훈#88 계열: 클래스만 고치지 말고 경로를 검증하라).
    # ⚠ 고를 때 하나만 넣지 마라. 풀 밖 7갈래를 **전부** 넣어 그중 하나만
    #   통과하게 두는 것이 "값을 보고 골랐다"를 피하는 방법이다.
    # ⚠ 이름은 `scripts/binance/paper_ab.py` 의 TRACKS 와 **같은 것을 쓴다.**
    #   두 곳에서 갈리면 보고가 엉뚱한 갈래를 가리킨다.
    "s6both_h240":   ("s6양다리",   6, "운동학 밴드 롱3+숏3 240분"),
    "s2both":        ("s2양다리",   2, "운동학 밴드 롱1+숏1 120분"),
    "s10both":       ("s10양다리",  10, "운동학 밴드 롱5+숏5 120분"),
    "s6both_ac1":    ("체결자기여기", 6, "체결 자기여기 롱3+숏3 480분"),
    "s3short_rmz":   ("최장연속숏",  3, "테이커 최장연속 숏 480분"),
    "s10both_d5_utc01":   ("되돌림UTC1", 10, "1시간 되돌림 UTC1시 진입"),
    "s10both_d5_revcont": ("되돌림연속", 10, "1시간 되돌림 연속 진입 (롱축)"),
}
# 지금 라이브가 쓰는 규칙 — 계좌 → 페이퍼 쌍
LIVE = {"계좌15": "s6both_h240", "계좌8": "s3short_anti"}

now = pd.Timestamp.now(tz="UTC")


def load(tag):
    # ⚠ 갓 띄운 갈래는 청산이 없어 trades.csv 가 아직 없다. 풀을 넓힌 뒤
    #   여기서 죽으면 **순위표가 통째로 안 나온다.** 빈 표로 넘긴다.
    f = PAPER / tag / "trades.csv"
    if not f.exists():
        return pd.DataFrame({"closed_ts": pd.Series(dtype="datetime64[ns, UTC]"),
                             "net_pct": pd.Series(dtype=float),
                             "stopped": pd.Series(dtype=float)})
    d = pd.read_csv(f)
    d["closed_ts"] = pd.to_datetime(d.closed_ts, utc=True, format="mixed")
    return d.sort_values("closed_ts")


D = {t: load(t) for t in BR}
edges = pd.date_range(now - pd.Timedelta(hours=72), now, freq="3h")


def cap(tag, h):
    sl = BR[tag][1]
    m = D[tag][D[tag].closed_ts >= now - pd.Timedelta(hours=h)]
    return m.net_pct.sum() / sl if len(m) else float("nan")


def buckets(tag):
    sl = BR[tag][1]
    d = D[tag]
    return np.array([d[(d.closed_ts >= edges[i]) & (d.closed_ts < edges[i + 1])]
                     .net_pct.sum() / sl for i in range(len(edges) - 1)])


def _bk_off(tag, off_h, n):
    """격자를 off_h 시간 밀어 최근 n 토막을 낸다."""
    sl = BR[tag][1]
    d = D[tag]
    end = now - pd.Timedelta(hours=off_h)
    e = pd.date_range(end - pd.Timedelta(hours=3 * n), end, freq="3h")
    return np.array([d[(d.closed_ts >= e[i]) & (d.closed_ts < e[i + 1])]
                     .net_pct.sum() / sl for i in range(len(e) - 1)])


def persist(tag):
    """⑥ 지속성 — (플러스 개수, 최대 제외 합, 마지막 토막).

    격자를 PERSIST_OFF 만큼 밀어 여러 번 재고 **중앙값**을 돌려준다.
    한 격자의 운으로 관문이 열리거나 닫히지 않게 하기 위함이다(교훈#109).
    마지막 토막만은 offset 0 의 값 — '지금 지고 있나'는 현재 격자로 읽는다.
    """
    pos, ex = [], []
    for off in PERSIST_OFF:
        b = _bk_off(tag, off, PERSIST_W)
        if not len(b):
            continue
        pos.append(int((b > 0).sum()))
        ex.append(float(b.sum() - b.max()))
    if not pos:
        return 0, 0.0, float("nan")
    b0 = _bk_off(tag, 0, PERSIST_W)
    return int(np.median(pos)), float(np.median(ex)), float(b0[-1])


def quality(tag):
    sl = BR[tag][1]
    m = D[tag][D[tag].closed_ts >= now - pd.Timedelta(hours=24)]
    if len(m) < 3:
        return None
    s = np.sort(m.net_pct.to_numpy())[::-1]
    nx = max(1, int(len(s) * 0.05))
    g = m.net_pct.mean() + TOLL
    return {"n": len(m), "stop": 100 * m.stopped.mean(),
            "win": 100 * (m.net_pct > 0).mean(), "conc": s[nx:].sum() / sl,
            "ero": 100 * TOLL / g if g > 0 else float("nan")}


# ── 공통 성분 (2026-09-15 대표님 승인) ────────────────────────────
#
# 갈래 성적의 상당 부분은 **그 갈래가 아니라 국면**이다. 09-09~09-15 실측에서
# 횡단면 평균이 앞 25토막 +0.542 → 뒤 25토막 -0.136 으로 움직였고, 아홉 중
# **여덟**이 같은 방향으로 나빠졌다. 절대 성적만 보면 "국면이 나쁜 것"과
# "이 갈래가 나쁜 것"을 가를 수 없다.
#
# 공통 성분 = 같은 24h 창에서 **전 갈래 자본%의 중앙값**.
#   평균이 아니라 중앙값을 쓴다 — 충격60(-30%) 같은 한 갈래가 평균을 끌어
#   전 갈래를 실제보다 좋아 보이게 만든다.
# 초과분 = 그 갈래의 24h 자본% - 공통 성분.
COMMON = float(np.median([cap(t, 24) for t in BR
                          if quality(t) is not None
                          and np.isfinite(cap(t, 24))]))

print("■ 🔄 갈래 순위 — 지금 국면 (자본%%, 24h 내림차순)")
print("   공통 성분(전 갈래 24h 중앙값) %+.2f%% — 초과 열은 이것을 뺀 값이다"
      % COMMON)
print("   %-10s %8s %8s %8s %8s %8s %6s %6s %8s %7s %7s %9s %s"
      % ("갈래", "3h", "6h", "12h", "24h", "초과", "손절", "승률", "집중도",
         "잠식", "4토막+", "최대제외", "선별"))
rank = []
for t, (nm, sl, desc) in BR.items():
    q = quality(t)
    if q is None:
        continue
    rank.append((cap(t, 24), t))
    pos, exmax, _ = persist(t)
    print("   %-10s %+8.2f %+8.2f %+8.2f %+8.2f %+8.2f %5.0f%% %5.0f%% %+8.2f %6s "
          "%5d/%d %+9.2f %s"
          % (nm, cap(t, 3), cap(t, 6), cap(t, 12), cap(t, 24),
             cap(t, 24) - COMMON,
             q["stop"], q["win"], q["conc"],
             "%.0f%%" % q["ero"] if np.isfinite(q["ero"]) else "—",
             pos, PERSIST_W, exmax, desc))
rank.sort(reverse=True)
print("   ▶ 24h 1위 %s · 2위 %s · 3위 %s"
      % tuple(BR[t][0] for _, t in rank[:3]))

print("\n■ 교체 판정 — 계좌별 (조건 ①12h·24h 둘 다 우위 ②24h>0 "
      "③상대계좌와 상관<%.2f ④손절율<=%.0f%% ⑤연속%d회 "
      "⑥최근%d토막 플러스>=%d 且 최대제외>0 · 격자 %s 중앙값)"
      % (CORR_MAX, STOP_MAX, NEED_STREAK, PERSIST_W, PERSIST_MIN,
         "/".join("-%dh" % o if o else "0" for o in PERSIST_OFF)))
try:
    st = json.loads(STREAK.read_text())
except Exception:
    st = {}
new_st = {}
for acct, cur in LIVE.items():
    other = [v for k, v in LIVE.items() if k != acct][0]
    ob = buckets(other)
    c12, c24 = cap(cur, 12), cap(cur, 24)
    cpos, cex, clast = persist(cur)
    warn = " ⚠ **최근 %d토막 중 플러스 %d개** — 수준 1위가 한 토막의 잔상일 수 있다" \
        % (PERSIST_W, cpos) if cpos <= WARN_MAX else ""
    print("   [%s] 현행 **%s** — 12h %+.2f%% · 24h %+.2f%% (초과 %+.2f%%p) · "
          "최근%d토막 플러스 %d/%d · 최대제외 %+.2f · 마지막토막 %+.2f%s"
          % (acct, BR[cur][0], c12, c24, c24 - COMMON, PERSIST_W, cpos,
             PERSIST_W, cex, clast, warn))
    best = None
    for t, (nm, sl, desc) in BR.items():
        if t == cur or t == other:
            continue
        q = quality(t)
        if q is None:
            continue
        tb = buckets(t)
        r = np.corrcoef(ob, tb)[0, 1] if tb.std() > 0 and ob.std() > 0 else 0.0
        pos, exmax, _ = persist(t)
        lvl = (cap(t, 12) > c12 and cap(t, 24) > c24 and cap(t, 24) > 0
               and r < CORR_MAX and q["stop"] <= STOP_MAX)
        per = pos >= PERSIST_MIN and exmax > 0
        # ①~⑤ 는 넘었는데 ⑥ 에서만 걸린 갈래는 **드러낸다** — 조용히 버리면
        # 다음 주기에 왜 안 올라왔는지 아무도 모른다.
        if lvl and not per:
            print("        · %s — ①~⑤ 통과했으나 **⑥ 탈락** "
                  "(플러스 %d/%d · 최대제외 %+.2f)"
                  % (BR[t][0], pos, PERSIST_W, exmax))
        ok = lvl and per
        if ok:
            gain = (cap(t, 12) - c12) + (cap(t, 24) - c24)
            if best is None or gain > best[0]:
                best = (gain, t, r, q)
    key = "%s→%s" % (acct, best[1]) if best else None
    prev = st.get(acct, {})
    streak = prev.get("streak", 0) + 1 if (key and prev.get("key") == key) else (1 if key else 0)
    new_st[acct] = {"key": key, "streak": streak}
    if best is None:
        print("        ▶ 교체 후보 없음 — 현행 유지")
    else:
        gain, t, r, q = best
        print("        ▶ 후보 **%s** — 12h %+.2f%%(%+.2f) · 24h %+.2f%%(%+.2f) · "
              "상대계좌 상관 %+.3f · 손절율 %.0f%% · 집중도 %+.2f"
              % (BR[t][0], cap(t, 12), cap(t, 12) - c12,
                 cap(t, 24), cap(t, 24) - c24, r, q["stop"], q["conc"]))
        print("        ▶ 연속 %d회 / 필요 %d회 → **%s**"
              % (streak, NEED_STREAK,
                 "🔄 교체를 건의한다" if streak >= NEED_STREAK else "한 주기 더 본다"))
STREAK.write_text(json.dumps(new_st, ensure_ascii=False), encoding="utf-8")
