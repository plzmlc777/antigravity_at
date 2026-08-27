"""틱 지지·저항 — 최근 24시간 체결에서 **되돌아온 가격대**를 찾는다.

## 왜 틱인가

1분봉은 그 분 안의 체결 순서를 모른다. 레벨을 몇 번 건드렸는지는 **경로**의
문제라 봉으로는 한 번 스친 것과 다섯 번 왕복한 것이 같아 보인다.

## "강하다"를 뭐로 재나 — 거래대금만 보면 안 된다

거래대금이 몰린 가격대는 **가격이 오래 머문 곳**일 수도 있다. 횡보하면 저절로
그렇게 된다. 그건 지지·저항이 아니라 그냥 정체다. 그래서 세 가지를 같이 잰다.

    재방문(touches)   레벨 밴드를 벗어났다가 **다시** 들어온 횟수.
                      벗어남은 min_sep 이상 떨어져야 인정한다 —
                      밴드 경계에서 떠는 것을 여러 번으로 세면 안 된다.
    보유율(hold)      들어온 방향으로 도로 튕겨 나갔나. 위에서 내려와 위로
                      나가면 지지가 버틴 것, 아래에서 올라와 아래로 나가면
                      저항이 버틴 것. 뚫고 지나갔으면 안 버틴 것이다.
    거래대금 비중     그 밴드에서 체결된 대금의 몫.

## 위약 — 이게 없으면 변동성 낮은 종목만 뽑힌다

변동성이 낮으면 가격이 좁은 구간에 있으니 재방문이 저절로 많아진다. 그래서
**같은 변동성·같은 체결량인데 레벨 구조만 없는** 경로와 비교한다.

  블록 부트스트랩 — 봉 수익률을 60봉(10분) 블록째로 섞어 경로를 다시 만든다.
  블록으로 섞는 이유: 낱개로 섞으면 변동성 군집이 깨져 위약이 너무 약해지고,
  그러면 뭐든 다 "강한 레벨"로 통과한다.

  ⚠ 위약도 **레벨 탐색을 처음부터 다시** 한다(교훈#95). 관측에서 고른 레벨을
    위약 경로에 그대로 대보면 이미 선택된 칸이라 당연히 진다. 위약마다 자기
    볼륨 프로파일에서 자기 최고 레벨을 찾아 그 최댓값을 귀무분포로 쓴다.

⚠ 이건 **화면 선별**이지 전략이 아니다. "레벨이 있다"와 "그 레벨로 돈을 번다"는
  다른 명제다. 여기서 위로 올라온 종목은 다음 검정의 후보일 뿐이다.

사용:
  python3 -m scripts.research.tick_sr_levels --smoke 5
  python3 -m scripts.research.tick_sr_levels --hours 24 --reps 50
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
TICKS = ROOT / "runs" / "ticks"
OUT = ROOT / "runs" / "research_track" / "tick_sr"

log = logging.getLogger("tick_sr")


@dataclass(frozen=True)
class Cfg:
    """설정은 한 곳에만 둔다 — 즉석 하드코딩 금지(하네스 규칙 2026-08-16)."""
    hours: int = 24            # 되돌아볼 구간
    bar_secs: int = 10         # 경로 해상도
    bin_bp: float = 10.0       # 가격 구간 폭 (VWAP 대비 bp)
    tol_bins: float = 1.0      # 레벨 밴드 = ±(tol_bins × 구간폭)
    min_sep_bp: float = 50.0   # 레벨 간 최소 거리 · 재방문 재무장 거리
    n_levels: int = 3          # 종목당 살펴볼 후보 레벨 수
    min_ticks: int = 2_000     # 이보다 얇으면 판단 안 한다
    min_touches: int = 3       # 이보다 적으면 재방문이라 부르지 않는다
    reps: int = 50             # 위약 반복
    block_bars: int = 60       # 블록 길이(60봉 = 10분)
    seed: int = 20260827


def _bars(t: pd.DataFrame, cfg: Cfg) -> pd.DataFrame:
    """체결 → 고정 간격 경로. 종가와 거래대금만 남긴다."""
    g = t.groupby(t.ts_ms // (cfg.bar_secs * 1000))
    b = pd.DataFrame({"close": g.price.last(), "qv": g.qv.sum()})
    return b.reset_index(drop=True)


def _levels(price: np.ndarray, qv: np.ndarray, binw: float, cfg: Cfg,
            min_sep: float) -> list[tuple[float, float]]:
    """볼륨 프로파일에서 서로 떨어진 상위 레벨 — (레벨가, 대금비중)."""
    idx = np.round(price / binw).astype(np.int64)
    prof = pd.Series(qv).groupby(idx).sum().sort_values(ascending=False)
    tot = float(prof.sum())
    if tot <= 0:
        return []
    out: list[tuple[float, float]] = []
    for i, v in prof.items():
        p = i * binw
        if any(abs(p - q) < min_sep for q, _ in out):
            continue
        out.append((float(p), float(v) / tot))
        if len(out) >= cfg.n_levels:
            break
    return out


def _touches(close: np.ndarray, level: float, tol: float,
             min_sep: float) -> tuple[int, int]:
    """(재방문 횟수, 버틴 횟수).

    상태기계 — 밴드 안에 있으면 armed 를 내린다. 다시 세려면 레벨에서
    min_sep 이상 떨어져야 한다(밴드 경계 떨림을 여러 번으로 세지 않는다).
    """
    touches = holds = 0
    armed = True
    approach = 0.0
    for c in close:
        d = c - level
        if abs(d) <= tol:
            if armed:
                touches += 1
                armed = False
        else:
            if not armed and abs(d) >= min_sep:
                # 들어온 방향으로 도로 나갔으면 버틴 것
                if approach * d > 0:
                    holds += 1
                armed = True
            if abs(d) > tol:
                approach = d
    return touches, holds


# 세 통계량을 각자의 위약과 비교한다 — 하나만 보면 "강하다"의 뜻이 하나로 굳는다
STATS = ("touches", "share", "absorb")


def _absorb(close: np.ndarray, level: float, tol: float) -> tuple[int, int]:
    """(밴드 안 체류 봉수, 관통 횟수).

    흡수력 = 체류 / 관통. 레벨이 진짜 벽이면 근처에 오래 머물면서도 잘 안 뚫린다.
    자유롭게 지나다니면 체류는 짧고 관통은 잦다.
    """
    inside = np.abs(close - level) <= tol
    side = np.sign(close - level)
    side = side[side != 0]
    cross = int((np.diff(side) != 0).sum()) if len(side) > 1 else 0
    return int(inside.sum()), cross


def _best(close: np.ndarray, qv: np.ndarray, binw: float, cfg: Cfg,
          min_sep: float, tol: float) -> tuple[dict, dict | None]:
    """레벨 격자를 훑어 **통계량마다** 최댓값을 낸다.

    ⚠ 통계량별로 따로 최대를 취하는 게 핵심이다(교훈#95). 관측에서 고른 레벨을
      위약에 그대로 대면 이미 선택된 칸이라 당연히 이긴다. 위약도 이 함수를
      그대로 써서 자기 격자에서 자기 최고를 찾는다.
    """
    best = {k: 0.0 for k in STATS}
    top = None
    for lv, share in _levels(close, qv, binw, cfg, min_sep):
        n, h = _touches(close, lv, tol, min_sep)
        dwell, cross = _absorb(close, lv, tol)
        absorb = dwell / max(cross, 1)
        cur = {"touches": float(n), "share": share, "absorb": absorb}
        for k in STATS:
            if cur[k] > best[k]:
                best[k] = cur[k]
        if top is None or n > top["touches"]:
            top = {"level": lv, "share": share, "touches": n, "holds": h,
                   "dwell": dwell, "cross": cross, "absorb": absorb}
    return best, top


def one(sym: str, cfg: Cfg, cut_ms: int, rng: np.random.Generator) -> dict | None:
    d = TICKS / sym
    if not d.is_dir():
        return None
    fs = sorted(d.glob("*.parquet"))[-2:]
    if not fs:
        return None
    t = pd.concat([pd.read_parquet(f, columns=["ts_ms", "price", "qty"])
                   for f in fs], ignore_index=True)
    t = t[t.ts_ms >= cut_ms]
    # ⚠ 가짜 체결 방어 — 수집기가 이미 버리지만 옛 파일이 섞일 수 있다.
    #   0 이 하나만 있어도 최저가가 0, log 가 -inf 가 되어 조용히 다 틀린다.
    n_raw = len(t)
    t = t[(t.price > 0) & (t.qty > 0)]
    if n_raw and len(t) < n_raw:
        log.debug("%s 가짜 체결 %d건 제외", sym, n_raw - len(t))
    if len(t) < cfg.min_ticks:
        return None
    t = t.sort_values("ts_ms")
    t["qv"] = t.price * t.qty

    vwap = float((t.price * t.qty).sum() / t.qty.sum())
    binw = vwap * cfg.bin_bp / 1e4
    min_sep = vwap * cfg.min_sep_bp / 1e4
    tol = binw * cfg.tol_bins

    b = _bars(t, cfg)
    close = b.close.to_numpy(dtype=float)
    qv = b.qv.to_numpy(dtype=float)
    if len(close) < cfg.block_bars * 4:
        return None

    obs_max, obs = _best(close, qv, binw, cfg, min_sep, tol)
    if obs is None or obs["touches"] < cfg.min_touches:
        return None

    # ── 위약: 블록 부트스트랩 경로에서 **레벨을 새로 찾아** 최고를 취한다
    lr = np.diff(np.log(close))
    nb = len(lr) // cfg.block_bars
    if nb < 4:
        return None
    blocks_r = lr[:nb * cfg.block_bars].reshape(nb, cfg.block_bars)
    blocks_v = qv[1:nb * cfg.block_bars + 1].reshape(nb, cfg.block_bars)
    # ⚠ 블록을 **순열**로 섞는다(복원추출 아님) — 그래야 총 표류가 정확히 같아
    #   진다. 시작가·끝가가 관측과 일치하므로 "추세 없는 위약과 비교했다"는
    #   교란이 생기지 않는다.
    null = {k: np.empty(cfg.reps) for k in STATS}
    for r in range(cfg.reps):
        o = rng.permutation(nb)
        path = close[0] * np.exp(np.concatenate(
            [[0.0], blocks_r[o].ravel()]).cumsum())
        vol = np.concatenate([[qv[0]], blocks_v[o].ravel()])
        assert len(vol) == len(path), (len(vol), len(path))
        m, _ = _best(path, vol, binw, cfg, min_sep, tol)
        for k in STATS:
            null[k][r] = m[k]
    last = float(close[-1])
    out = {
        "symbol": sym, "n_ticks": int(len(t)), "n_bars": int(len(close)),
        "vwap": vwap, "last": last,
        "level": obs["level"],
        "side": "지지" if obs["level"] < last else "저항",
        "dist_bp": 1e4 * abs(obs["level"] - last) / last,
        "touches": obs["touches"], "holds": obs["holds"],
        "hold_rate": obs["holds"] / max(obs["touches"], 1),
        "vol_share": obs["share"], "dwell": obs["dwell"], "cross": obs["cross"],
        "absorb": obs["absorb"],
        "range_pct": 100.0 * (close.max() - close.min()) / vwap,
    }
    for k in STATS:
        nl = null[k]
        out[f"{k}_obs"] = obs_max[k]
        out[f"{k}_null"] = float(np.median(nl))
        out[f"{k}_z"] = ((obs_max[k] - nl.mean()) / nl.std()
                         if nl.std() > 0 else 0.0)
        out[f"{k}_p"] = float((nl >= obs_max[k]).mean())
    # 세 통계량을 한 번에 이겨야 한다 — 하나만 통과한 것은 통과가 아니다(교훈#96)
    out["n_pass"] = int(sum(out[f"{k}_p"] <= 0.05 for k in STATS))
    out["p_worst"] = max(out[f"{k}_p"] for k in STATS)
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--universe", default="configs/rsi_live_universe.txt")
    p.add_argument("--symbols", default="")
    p.add_argument("--smoke", type=int, default=0,
                   help="N종목만 — 본실행과 **같은 경로**로 먼저 재라")
    for f, v in [("hours", 24), ("bar-secs", 10), ("reps", 50),
                 ("n-levels", 3), ("min-touches", 3)]:
        p.add_argument(f"--{f}", type=int, default=None)
    for f in ["bin-bp", "tol-bins", "min-sep-bp"]:
        p.add_argument(f"--{f}", type=float, default=None)
    p.add_argument("--out", default="")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    over = {k: v for k, v in vars(a).items()
            if v is not None and k in Cfg.__dataclass_fields__}
    cfg = Cfg(**over)
    # ⚠ 파라미터 도달 증명 — 인자가 설정에 실제로 박혔는지 눈으로 확인한다
    log.info("설정 %s", json.dumps(asdict(cfg), ensure_ascii=False))
    for k, v in over.items():
        assert getattr(cfg, k) == v, f"{k} 가 설정에 도달하지 않았다"

    syms = ([s.strip().upper() for s in a.symbols.split(",") if s.strip()]
            if a.symbols else
            [s.strip().upper() for s in (ROOT / a.universe).read_text().split()
             if s.strip()])
    if a.smoke:
        syms = syms[:a.smoke]
    cut_ms = int((time.time() - cfg.hours * 3600) * 1000)
    log.info("틱 지지·저항 — %d종목 · 최근 %dh · 위약 %d회",
             len(syms), cfg.hours, cfg.reps)

    rng = np.random.default_rng(cfg.seed)
    rows, skipped, t0 = [], 0, time.time()
    for i, s in enumerate(syms, 1):
        try:
            r = one(s, cfg, cut_ms, rng)
        except Exception as e:                                  # noqa: BLE001
            log.warning("%s 실패: %s", s, str(e)[:120])
            r = None
        if r is None:
            skipped += 1
        else:
            rows.append(r)
        if i % 25 == 0 or i == len(syms):
            el = time.time() - t0
            log.info("[%d/%d] 통과 %d · 제외 %d · %.1f분 · 남은 %.1f분",
                     i, len(syms), len(rows), skipped, el / 60,
                     (len(syms) - i) * el / i / 60)

    if not rows:
        raise SystemExit("한 종목도 못 냈다 — 구간·최소체결·최소재방문을 확인하라")
    R = pd.DataFrame(rows).sort_values(
        ["n_pass", "touches_z", "absorb_z"], ascending=False)
    OUT.mkdir(parents=True, exist_ok=True)
    path = Path(a.out) if a.out else OUT / f"tick_sr_{cfg.hours}h.csv"
    R.to_csv(path, index=False)
    (path.with_suffix(".cfg.json")).write_text(
        json.dumps(asdict(cfg), ensure_ascii=False, indent=2))
    log.info("저장 %s — %d종목 · %.1f분", path, len(R), (time.time() - t0) / 60)

    print(f"\n■ 통계량별 위약 통과 (p≤0.05) — {len(R)}종목 중")
    for k in STATS:
        print(f"    {k:<8} {int((R[f'{k}_p'] <= 0.05).sum()):>4}종목")
    print(f"    셋 다     {int((R.n_pass == 3).sum()):>4}종목")
    cols = ["symbol", "side", "dist_bp", "touches", "touches_null", "touches_z",
            "vol_share", "share_z", "absorb", "absorb_null", "absorb_z",
            "n_pass", "p_worst", "range_pct"]
    print()
    print(R.head(20)[cols].to_string(index=False,
          float_format=lambda x: f"{x:.3f}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
