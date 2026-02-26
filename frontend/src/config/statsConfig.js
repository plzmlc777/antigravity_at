/**
 * statsConfig.js - SINGLE SOURCE OF TRUTH for Performance Stats
 *
 * Used by:
 * - PerformanceStatsGrid (Overview card grid)
 * - Rank Details table (columns, TOTAL row, OVERVIEW row)
 * - Optimization Results table (columns, cell rendering)
 *
 * Adding/removing/reordering a stat here automatically applies to ALL views.
 *
 * Backend counterpart: PERFORMANCE_STAT_KEYS in waterfall_engine.py
 */

// --- Color Presets ---
const COLOR = {
    signed:  (v) => v >= 0 ? 'text-green-400' : 'text-red-400',
    white:   () => 'text-white',
    yellow:  () => 'text-yellow-400',
    purple:  () => 'text-purple-400',
    blue:    () => 'text-blue-400',
    green:   () => 'text-green-400',
    red:     () => 'text-red-400',
    gray:    () => 'text-gray-400',
    accel:   (v) => v >= 1 ? 'text-green-400' : 'text-orange-400',
};

// --- Column Definitions ---
// Each entry defines how a stat is displayed, formatted, and aggregated.
export const STAT_COLUMNS = [
    // Row 1: Core Returns
    {
        key: 'total_return',  label: 'Total Return',
        format: 'pct', decimals: 2, color: COLOR.signed,
        bold: true, signed: true,
        agg: 'sum',
        optKey: 'return',     // optimization data uses 'return' instead of 'total_return'
    },
    {
        key: 'profit_factor', label: 'Profit Factor',
        format: 'num', decimals: 2, color: COLOR.white,
        highlight: true,   // purple border in grid view
        agg: 'weighted',
    },
    {
        key: 'win_rate',      label: 'Win Rate',
        format: 'pct', decimals: 1, color: COLOR.yellow,
        bold: true,
        agg: 'weighted',
    },
    {
        key: 'recent_10_win_rate', label: 'Recent 10',
        format: 'pct', decimals: 1, color: COLOR.yellow,
        gridLabel: 'Recent 10 WR',
        agg: 'weighted',
    },
    {
        key: 'sharpe_ratio',  label: 'Sharpe',
        format: 'num', decimals: 2, color: COLOR.yellow,
        gridLabel: 'Sharpe Ratio',
        agg: 'weighted',
    },

    // Row 2: Trading Activity
    {
        key: 'total_cycles',  label: 'Cycles',
        format: 'int', color: COLOR.white,
        gridLabel: 'Total Cycles',
        showDays: true,    // show "(X days)" in grid
        agg: 'sum',
        optKey: 'cycles',     // optimization data uses 'cycles' instead of 'total_cycles'
    },
    {
        key: 'stability_score', label: 'Stability',
        format: 'num', decimals: 2, color: COLOR.purple,
        gridLabel: 'Stability (R\u00B2)',
        agg: 'weighted',
    },
    {
        key: 'acceleration_score', label: 'Accel',
        format: 'suffix', suffix: 'x', decimals: 2, color: COLOR.accel,
        gridLabel: 'Profit Accel',
        agg: 'weighted',
    },
    {
        key: 'activity_rate', label: 'Activity',
        format: 'pct', decimals: 1, color: COLOR.blue,
        gridLabel: 'Activity Rate',
        agg: 'sum',
    },

    // Row 3: PnL Details
    {
        key: 'avg_pnl',      label: 'Avg PnL',
        format: 'pct', decimals: 2, color: COLOR.signed,
        signed: true,
        tableLabel: 'Avg Return',
        agg: 'weighted',
    },
    {
        key: 'avg_holding_time', label: 'Avg Hold',
        format: 'suffix', suffix: 'm', decimals: 0, color: COLOR.gray,
        gridLabel: 'Avg Holding',
        agg: 'weighted_round',
    },
    {
        key: 'max_holding_time', label: 'Max Hold',
        format: 'suffix', suffix: 'm', decimals: 0, color: COLOR.red,
        gridLabel: 'Max Holding',
        agg: 'max_nullable',
    },
    {
        key: 'min_holding_time', label: 'Min Hold',
        format: 'suffix', suffix: 'm', decimals: 0, color: COLOR.green,
        gridLabel: 'Min Holding',
        agg: 'min_nullable',
    },
    {
        key: 'max_profit',    label: 'Max Profit',
        format: 'pct', decimals: 2, color: COLOR.green,
        agg: 'max',
    },
    {
        key: 'max_loss',      label: 'Max Loss',
        format: 'pct', decimals: 2, color: COLOR.red,
        agg: 'min',
    },

    // Row 4: Max Drawdown (full-width in grid view)
    {
        key: 'max_drawdown',  label: 'Max DD',
        format: 'pct', decimals: 2, color: COLOR.red,
        gridLabel: 'Max Drawdown',
        fullWidth: true,      // full-width card in grid view
        lastColumn: true,     // right-aligned in table view
        agg: 'min',
    },
];

// --- Format Helpers ---

/**
 * Format a stat value for display.
 * Returns '-' for null/undefined values.
 */
export const formatStatValue = (value, col) => {
    if (value == null || value === undefined) return '-';

    switch (col.format) {
        case 'pct': {
            const num = typeof value === 'number' ? value.toFixed(col.decimals) : value;
            return `${num}%`;
        }
        case 'num':
            return typeof value === 'number' ? value.toFixed(col.decimals) : String(value);
        case 'int':
            return typeof value === 'number' ? String(Math.round(value)) : String(value);
        case 'suffix': {
            // Smart time formatting for minutes ('m' suffix)
            if (col.suffix === 'm' && typeof value === 'number') {
                const mins = Math.round(value);
                if (mins >= 60) {
                    const hours = Math.floor(mins / 60);
                    const remMins = mins % 60;
                    return remMins > 0 ? `${hours}h ${remMins}m` : `${hours}h`;
                }
                return `${mins}m`;
            }
            const num = typeof value === 'number'
                ? (col.decimals > 0 ? value.toFixed(col.decimals) : String(Math.round(value)))
                : String(value);
            return `${num}${col.suffix}`;
        }
        default:
            return String(value);
    }
};

/**
 * Get Tailwind color class for a stat value.
 */
export const getStatColor = (value, col) => {
    return col.color ? col.color(value) : 'text-white';
};

/**
 * Check if conditional stats should be visible.
 * (All stats are now unconditional - cycle metrics removed)
 */
export const shouldShowConditional = (stats, condition) => {
    return true;
};

// --- Aggregation Helper for TOTAL row ---

/**
 * Compute aggregated TOTAL stats from a list of per-rank stat objects.
 * Uses the aggregation type defined in each STAT_COLUMNS entry.
 */
export const computeTotalStats = (statsList) => {
    if (!statsList || statsList.length === 0) return {};

    const totalCycles = statsList.reduce((acc, s) => acc + (s.total_cycles || 0), 0);
    const result = {};

    for (const col of STAT_COLUMNS) {
        const key = col.key;
        const agg = col.agg;
        if (!agg) continue;

        switch (agg) {
            case 'sum':
                result[key] = statsList.reduce((acc, s) => acc + (s[key] || 0), 0);
                break;

            case 'weighted':
                result[key] = totalCycles > 0
                    ? statsList.reduce((acc, s) => acc + ((s[key] || 0) * (s.total_cycles || 0)), 0) / totalCycles
                    : 0;
                break;

            case 'weighted_round':
                result[key] = totalCycles > 0
                    ? Math.round(statsList.reduce((acc, s) => acc + ((s[key] || 0) * (s.total_cycles || 0)), 0) / totalCycles)
                    : 0;
                break;

            case 'max':
                result[key] = statsList.length > 0
                    ? Math.max(...statsList.map(s => s[key] || 0))
                    : 0;
                break;

            case 'min':
                result[key] = statsList.length > 0
                    ? Math.min(...statsList.map(s => s[key] || 0))
                    : 0;
                break;

            case 'max_nullable': {
                const vals = statsList.filter(s => s[key] != null).map(s => s[key]);
                result[key] = vals.length > 0 ? Math.max(...vals) : null;
                break;
            }

            case 'min_nullable': {
                const vals = statsList.filter(s => s[key] != null).map(s => s[key]);
                result[key] = vals.length > 0 ? Math.min(...vals) : null;
                break;
            }

            default:
                break;
        }
    }

    return result;
};

// --- Convenience Exports ---

/**
 * Get only the visible columns (filtering out conditional ones when condition not met).
 */
export const getVisibleColumns = (stats) => {
    return STAT_COLUMNS.filter(col => {
        if (col.conditional) {
            return shouldShowConditional(stats, col.conditional);
        }
        return true;
    });
};

// --- Optimization Table Helpers ---

/**
 * Parse a stat value that may be a string (optimization metrics come as strings).
 * Strips '%' suffix and converts to number for proper formatting.
 */
export const parseStatValue = (value) => {
    if (value == null || value === undefined || value === '-') return null;
    if (typeof value === 'number') return value;
    if (typeof value === 'string') {
        const stripped = value.replace('%', '').replace('m', '').trim();
        const num = parseFloat(stripped);
        return isNaN(num) ? null : num;
    }
    return null;
};

/**
 * Get a stat value from optimization result data.
 * Uses optKey (alias) if defined, falls back to key.
 */
export const getOptValue = (data, col) => {
    const key = col.optKey || col.key;
    return data[key];
};

/**
 * Get visible columns for optimization table.
 * (All columns are now unconditional - cycle metrics removed)
 */
export const getOptVisibleColumns = (results) => {
    return STAT_COLUMNS;
};

// --- Normalization Helper ---

/**
 * Normalize stats from any backend format to consistent numeric types.
 * Handles multiple data locations: top-level fields, metrics dict, stats dict.
 *
 * @param {Object} raw - Raw result from backend (backtest or optimization)
 * @returns {Object} - Normalized stats with consistent numeric types
 *
 * Usage:
 *   const normalized = normalizeStats(rawResult);
 *   // Now normalized.total_return is always a number
 *   // normalized.recent_10_win_rate is number or null
 */
export const normalizeStats = (raw) => {
    if (!raw) return {};

    // Helper: extract value from multiple possible locations
    const getValue = (key) => {
        // Priority: top-level > stats > metrics
        if (raw[key] !== undefined) return raw[key];
        if (raw.stats?.[key] !== undefined) return raw.stats[key];
        if (raw.metrics?.[key] !== undefined) return raw.metrics[key];
        // Backward compat: total_trades → total_cycles
        if (key === 'total_cycles') {
            return raw['total_trades'] ?? raw.stats?.['total_trades'] ?? raw.metrics?.['total_trades'];
        }
        return undefined;
    };

    // Helper: convert to float with fallback
    const toFloat = (value, defaultVal = 0) => {
        if (value == null || value === '-' || value === '') return defaultVal;
        if (typeof value === 'number') return value;
        if (typeof value === 'string') {
            const cleaned = value.replace('%', '').replace(',', '').trim();
            if (cleaned === '-' || cleaned === '') return defaultVal;
            const num = parseFloat(cleaned);
            return isNaN(num) ? defaultVal : num;
        }
        return defaultVal;
    };

    // Helper: convert to int with nullable support
    const toInt = (value, nullable = false) => {
        if (value == null || value === '-' || value === '') return nullable ? null : 0;
        if (typeof value === 'number') return Math.round(value);
        if (typeof value === 'string') {
            const cleaned = value.replace(',', '').replace('m', '').trim();
            if (cleaned === '-' || cleaned === '') return nullable ? null : 0;
            const num = parseInt(cleaned, 10);
            return isNaN(num) ? (nullable ? null : 0) : num;
        }
        return nullable ? null : 0;
    };

    // Helper: convert to nullable float
    const toFloatNullable = (value) => {
        if (value == null || value === '-' || value === '') return null;
        return toFloat(value, null);
    };

    return {
        // Core Performance
        total_return: toFloat(getValue('total_return')),
        win_rate: toFloat(getValue('win_rate')),
        recent_10_win_rate: toFloatNullable(getValue('recent_10_win_rate')),
        total_cycles: toInt(getValue('total_cycles')),
        total_days: toInt(getValue('total_days')),

        // Risk Metrics
        max_drawdown: toFloat(getValue('max_drawdown')),
        sharpe_ratio: toFloat(getValue('sharpe_ratio')),
        profit_factor: toFloat(getValue('profit_factor')),

        // PnL Details
        avg_pnl: toFloat(getValue('avg_pnl')),
        max_profit: toFloat(getValue('max_profit')),
        max_loss: toFloat(getValue('max_loss')),

        // Time Metrics (nullable ints)
        avg_holding_time: toInt(getValue('avg_holding_time'), true),
        max_holding_time: toInt(getValue('max_holding_time'), true),
        min_holding_time: toInt(getValue('min_holding_time'), true),

        // Quality Scores
        stability_score: toFloat(getValue('stability_score')),
        acceleration_score: toFloat(getValue('acceleration_score')),
        activity_rate: toFloat(getValue('activity_rate')),

        // Cycle Metrics (nullable)
        cycle_count: toInt(getValue('cycle_count'), true),
        cycle_avg_pnl: toFloatNullable(getValue('cycle_avg_pnl')),
        cycle_avg_hold: toInt(getValue('cycle_avg_hold'), true),
        cycle_max_hold: toInt(getValue('cycle_max_hold'), true),
        cycle_min_hold: toInt(getValue('cycle_min_hold'), true),
    };
};
