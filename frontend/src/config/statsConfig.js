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
        key: 'sharpe_ratio',  label: 'Sharpe',
        format: 'num', decimals: 2, color: COLOR.yellow,
        gridLabel: 'Sharpe Ratio',
        agg: 'weighted',
    },

    // Row 2: Trading Activity
    {
        key: 'total_trades',  label: 'Trades',
        format: 'int', color: COLOR.white,
        gridLabel: 'Total Trades',
        showDays: true,    // show "(X days)" in grid
        agg: 'sum',
        optKey: 'trades',     // optimization data uses 'trades' instead of 'total_trades'
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
        key: 'max_profit',    label: 'Max Profit',
        format: 'pct', decimals: 2, color: COLOR.green,
        agg: 'max',
    },
    {
        key: 'max_loss',      label: 'Max Loss',
        format: 'pct', decimals: 2, color: COLOR.red,
        agg: 'min',
    },

    // Row 4: Cycle Metrics (conditional - only shown when cycles exist)
    // All cycle-related keys use "cycle_" prefix
    {
        key: 'cycle_count',   label: 'Cycle Count',
        format: 'int', color: COLOR.white,
        conditional: 'cycles',
        agg: 'sum_nullable',
    },
    {
        key: 'cycle_avg_pnl', label: 'Cycle Avg PnL',
        format: 'pct', decimals: 2, color: COLOR.signed,
        conditional: 'cycles',
        agg: 'cycle_weighted',
    },
    {
        key: 'cycle_avg_hold', label: 'Cycle Avg Hold',
        format: 'suffix', suffix: 'm', decimals: 0, color: COLOR.gray,
        conditional: 'cycles',
        agg: 'cycle_weighted_round',
    },
    {
        key: 'cycle_max_hold', label: 'Cycle Max Hold',
        format: 'suffix', suffix: 'm', decimals: 0, color: COLOR.red,
        conditional: 'cycles',
        agg: 'max_nullable',
    },
    {
        key: 'cycle_min_hold', label: 'Cycle Min Hold',
        format: 'suffix', suffix: 'm', decimals: 0, color: COLOR.green,
        conditional: 'cycles',
        agg: 'min_nullable',
    },

    // Row 5: Max Drawdown (full-width in grid view)
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
                if (mins >= 1440) { // >= 1 day
                    const days = Math.floor(mins / 1440);
                    const hours = Math.floor((mins % 1440) / 60);
                    return hours > 0 ? `${days}d ${hours}h` : `${days}d`;
                }
                if (mins >= 60) { // >= 1 hour
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
 */
export const shouldShowConditional = (stats, condition) => {
    if (condition === 'cycles') {
        return stats?.cycle_count != null && stats.cycle_count > 0;
    }
    return true;
};

// --- Aggregation Helper for TOTAL row ---

/**
 * Compute aggregated TOTAL stats from a list of per-rank stat objects.
 * Uses the aggregation type defined in each STAT_COLUMNS entry.
 */
export const computeTotalStats = (statsList) => {
    if (!statsList || statsList.length === 0) return {};

    const totalTrades = statsList.reduce((acc, s) => acc + (s.total_trades || 0), 0);
    const totalCycles = statsList.reduce((acc, s) => acc + (s.cycle_count || 0), 0);
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
                result[key] = totalTrades > 0
                    ? statsList.reduce((acc, s) => acc + ((s[key] || 0) * (s.total_trades || 0)), 0) / totalTrades
                    : 0;
                break;

            case 'weighted_round':
                result[key] = totalTrades > 0
                    ? Math.round(statsList.reduce((acc, s) => acc + ((s[key] || 0) * (s.total_trades || 0)), 0) / totalTrades)
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

            case 'sum_nullable': {
                const vals = statsList.filter(s => s[key] != null);
                result[key] = vals.length > 0
                    ? vals.reduce((acc, s) => acc + (s[key] || 0), 0)
                    : null;
                break;
            }

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

            case 'cycle_weighted': {
                const totalPnl = statsList.reduce((acc, s) => acc + ((s[key] || 0) * (s.cycle_count || 0)), 0);
                result[key] = totalCycles > 0 ? totalPnl / totalCycles : null;
                break;
            }

            case 'cycle_weighted_round': {
                const totalHold = statsList.reduce((acc, s) => acc + ((s[key] || 0) * (s.cycle_count || 0)), 0);
                result[key] = totalCycles > 0 ? Math.round(totalHold / totalCycles) : null;
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
 * Checks cycle visibility using first result row as reference.
 */
export const getOptVisibleColumns = (results) => {
    if (!results || results.length === 0) return STAT_COLUMNS;
    // Check if ANY result has cycle data
    const hasCycles = results.some(r => {
        const count = r.cycle_count;
        return count != null && count > 0;
    });
    return STAT_COLUMNS.filter(col => {
        if (col.conditional === 'cycles') return hasCycles;
        return true;
    });
};
