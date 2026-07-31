# US paradigm 1 graveyard — 미국 ETF 프리마켓 갭 반전 (일봉 스윙)

**Slug**: `us_premarket_gap_reversion_etf_daily`
**Date**: 2026-07-31
**Phase**: R-1 graveyard
**Verdict**: `BROAD_FALSIFIED_NEGATIVE_EDGE_ALL_CELLS`
**Market**: US ETF (신설 트랙 1호)
**Host**: hcp_local (키움 미국 일봉 6.7yr, core 59종 + leveraged 29종)

## Hypothesis recap

키움 미국 일봉의 종가는 오버나이트(Blue Ocean, ET 20:00~익일 04:00)까지 반영한
최종가이고 시가는 정규장 시가(09:30 ET)다. 따라서
`gap = open(D) / close(D-1) - 1` 은 **ET 04:00~09:30 프리마켓 구간의 움직임만**
분리 측정한다 — 통상적 갭(애프터+오버나이트+프리마켓 합산)과 구성이 다르다.

가설: 한국 야간 세션 종료 후 프리마켓에서 형성된 극단 갭(|z|≥2)은 과잉반응이며,
정규장 개장 이후 3~10영업일에 걸쳐 되돌린다.

## R-0 prescreen 결과

- **구조적 타당성 (Lesson #40 계열, `us_r0_structural_feasibility.py`)**:
  core 1일 보유는 `selective_edge +1.78% < 2%` 로 **elite gate 도달 구조적 불가**
  (수수료 왕복 0.502%가 일간 |ret| 평균 0.98%의 절반을 잠식). 3일 이상만 채택.
  leveraged 는 1일부터 도달 가능(+5.76%).
- **Lesson #11 sample density**: 셀당 n=1206~3542 — PASS (≥30)
- **Lesson #28 substrate availability**: 일봉 99,203봉 + 레버리지 46종, 무결성 위반 0,
  `first_valid_date` 적용(IBIT 2024-01-11 상장 이전 구간 배제) — PASS
- **Lesson #20 sign-cond**: 양방향(long/short) 대칭 검증을 단일 배치에 포함 — PASS

## R-1 결과 (2 그룹 × 3 hold × 2 방향 = 12 셀)

| cell | n | net_bp | obs_t | sig_t_excess | perm_p | ci_lower_bp | 3gate |
|---|---|---|---|---|---|---|---|
| core/3d/long | 3542 | -58.8 | — | -1.35 | 0.912 | -71.0 | False |
| core/3d/short | 2284 | -27.9 | — | **+8.36** | 0.000 | **-46.2** | False |
| core/5d/long | 3531 | -52.0 | — | -1.35 | 0.917 | -72.7 | False |
| core/5d/short | 2284 | -49.8 | — | **+5.77** | 0.000 | **-73.3** | False |
| core/10d/long | 3515 | -48.0 | — | -3.09 | 0.999 | -82.6 | False |
| core/10d/short | 2282 | -109.1 | — | +1.23 | 0.124 | -137.6 | False |
| lev/3d/long | 1218 | -76.3 | — | -0.44 | 0.672 | -130.7 | False |
| lev/3d/short | 1277 | -12.4 | — | +2.24 | 0.013 | -60.5 | False |
| lev/5d/long | 1213 | -77.3 | — | -0.41 | 0.657 | -157.6 | False |
| lev/5d/short | 1271 | **+24.4** | — | +2.94 | 0.001 | **-46.2** | False |
| lev/10d/long | 1206 | -159.7 | — | -2.16 | 0.983 | -279.4 | False |
| lev/10d/short | 1262 | -68.6 | — | +0.03 | 0.507 | -189.3 | False |

**0/12 셀 PASS.** 12셀 중 11셀의 net_mean 이 음수. 유일한 양수(lev/5d/short +24.4bp)도
`ci_lower = -46.2bp` 로 0을 포함 → 통계적으로 0과 구분되지 않음.

## 판정 근거

프리마켓 갭 반전은 **양방향 모두 수수료를 넘지 못한다.** 갭 자체에 되돌림 정보가
있더라도 그 크기가 왕복 50.2bp 미만이다. hold 를 늘려도(3→10일) 개선되지 않고
오히려 악화 — 되돌림이 아니라 드리프트 노출만 커진다.

## Lesson 후보 (신규) — long-drift 자산군의 SHORT 방향 t_excess 인플레이션

**관측**: SHORT 방향 6셀 중 5셀에서 `signal_t_excess` 가 크게 양수
(core/3d/short = **+8.36**)인데 `net_mean` 은 음수이고 `ci_lower` 도 음수다.

**원인**: `fee_aware_perm_test` 의 null 은 후보 풀에서 무작위 추출한다. 주식 ETF 는
장기 우상향 드리프트를 가지므로 SHORT 후보 풀(`-fwd`)의 평균이 구조적으로 음수다
→ `null_mean_t` 가 크게 음수 → 관측치가 "덜 나쁘기만" 해도 `t_excess` 가 부풀려진다.

**의미**: `signal_t_excess ≥ 2.0` 은 long-drift 자산군의 SHORT 패러다임에서
**절대 수익의 증거가 되지 못한다.** three-gate 중 `ci_lower > 0` 이 유일한 실질
방어선이다. 암호화폐(무드리프트~약드리프트)에서 보정된 게이트를 주식에 그대로
쓸 때 반드시 걸리는 함정.

**적용 규칙**: US 트랙의 SHORT 방향 R-1 판정은 `ci_lower > 0` 을 필수 선행 조건으로
두고, `signal_t_excess` 는 보조 지표로만 읽는다. (기존 Lesson #76 universe-aggregate
bilateral fee-floor 의 주식시장 변종)

## 산출물

- `backend/scripts/research/us_r0_structural_feasibility.py` → `us_etf_daily_swing_feasibility/r0__metrics.json`
- `backend/scripts/research/us_premarket_gap_reversion_etf_daily_r1.py` → `us_premarket_gap_reversion_etf_daily/r1__metrics.json`

## 후속

가설 자체는 폐기하되 **프리마켓 갭 축은 아직 열려 있다**. 이번엔 "극단 갭 → 반전"만
검증했고, 반대 축(갭 방향 지속) 및 갭×상대강도 조건부는 미검증이다. 다만 net_mean 이
양방향 모두 음수인 점으로 미루어 단독 축으로는 가망이 낮고, 조건부 필터의 한 요소로
재등장하는 편이 현실적이다.
