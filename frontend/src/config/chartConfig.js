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
