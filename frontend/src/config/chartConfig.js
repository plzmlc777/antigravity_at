/**
 * chartConfig.js - SINGLE SOURCE OF TRUTH for Chart Data Keys
 *
 * Centralizes key names used in equity curve chart data.
 * Prevents key mismatch bugs (e.g., "timestamp" vs "date") between
 * backend responses and frontend Recharts dataKey bindings.
 *
 * Backend counterpart: EQUITY_DATE_KEY / EQUITY_VALUE_KEY in data_schemas.py
 *
 * Used by:
 * - StrategyView.jsx (Equity Curve LineChart)
 */

// --- Equity Curve Data Keys ---
// Must match backend data_schemas.py EQUITY_DATE_KEY / EQUITY_VALUE_KEY
export const EQUITY_DATE_KEY = "date";
export const EQUITY_VALUE_KEY = "equity";

// --- 파라미터 스윕 히트맵 (2026-08-14) ---
// 설계: .claude/plans/param_sweep_heatmap_component.md §6
//
// ⚠ 초록↔빨강을 쓰지 않는다. 한국 증시 관례(빨강=상승)와 기존
//   MonthlyAnalysisChart 에 어긋나지만, **적록색각 이상에서 두 극이 붕괴**한다.
//   막대 차트는 위치라는 두 번째 채널이 있어 관례를 유지해도 되지만,
//   히트맵 셀에는 위치 채널이 없다 — 색이 유일한 부호화 채널이다.
//
// 팔레트 출처: ColorBrewer RdBu(발산) / Blues(순차). CVD 검증된 표준 스킴이다.
// (설계가 요구한 dataviz `validate_palette.js` 는 이 머신에 미설치 —
//  검증기를 못 돌렸으므로 임의 색 대신 검증된 기성 스킴을 쓴다)

// 발산: 파랑(음) ↔ 중립 회색(0) ↔ 빨강(양). **0 에 고정**, 양팔 스텝 수 동일
export const SWEEP_DIVERGING = [
  '#2166ac', '#4393c3', '#92c5de', '#d1e5f0',
  '#8a8a8a',
  '#fddbc7', '#f4a582', '#d6604d', '#b2182b',
];

// 순차: 단일 파랑, 밝음 → 어둠. 가장 밝은 스텝 = 0 근처
export const SWEEP_SEQUENTIAL = [
  '#deebf7', '#c6dbef', '#9ecae1', '#6baed6',
  '#4292c6', '#2171b5', '#08519c', '#08306b',
];

export const SWEEP_SURFACE = '#0f111a';      // --t-bg-card (실제 렌더 표면)
export const SWEEP_MISSING = 'transparent';  // 결측은 색이 아니라 빗금으로 그린다
export const SWEEP_SIG_T = 2.0;              // |t| 미만은 후퇴 (§7)
export const SWEEP_FADE = 0.3;               // 유의 미달 셀 불투명도
export const SWEEP_LABEL_MAX = 8;            // 격자가 이보다 크면 숫자 라벨 생략
