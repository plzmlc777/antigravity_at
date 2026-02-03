import React from 'react';
import { STAT_COLUMNS, formatStatValue, getStatColor, shouldShowConditional } from '../config/statsConfig';

/**
 * PerformanceStatsGrid - Performance Stats card grid.
 *
 * Renders stat cards from STAT_COLUMNS config (statsConfig.js).
 * Used by BOTH individual rank tab (Overview) and integrated tab (Overview).
 * Adding a new stat in statsConfig.js automatically adds it here.
 *
 * @param {Object} stats - The backtestResult object containing all metrics
 */
const PerformanceStatsGrid = ({ stats }) => {
    if (!stats) return null;

    return (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {STAT_COLUMNS.map(col => {
                // Skip conditional columns if condition not met
                if (col.conditional && !shouldShowConditional(stats, col.conditional)) {
                    return null;
                }

                const value = stats[col.key];
                const colorClass = getStatColor(value, col);
                const formatted = formatStatValue(value, col);
                const label = col.gridLabel || col.label;

                // Sign prefix
                const prefix = col.signed && typeof value === 'number' && value > 0 ? '+' : '';

                // Layout classes
                const widthClass = col.fullWidth ? 'col-span-2 md:col-span-4' : '';
                const paddingClass = col.fullWidth
                    ? 'p-4 flex flex-col justify-center min-h-[5rem]'
                    : 'p-3';

                // Highlight border for profit_factor
                const borderClass = col.highlight
                    ? 'border border-purple-500/30 bg-purple-500/10'
                    : 'bg-white/5';
                const labelClass = col.highlight
                    ? 'text-xs text-purple-300 font-semibold'
                    : 'text-xs text-gray-400';

                return (
                    <div
                        key={col.key}
                        className={`rounded-lg ${borderClass} ${widthClass} ${paddingClass}`}
                    >
                        <div className={`${labelClass} ${col.fullWidth ? 'mb-1' : ''}`}>
                            {label}
                        </div>
                        <div className={`${col.fullWidth ? 'text-lg md:text-xl' : 'text-xl'} font-bold ${colorClass} ${col.fullWidth ? 'break-words leading-tight' : ''}`}>
                            {prefix}{formatted}
                            {col.showDays && stats.total_days && (
                                <span className="text-sm font-normal text-gray-500 ml-2">
                                    ({stats.total_days} days)
                                </span>
                            )}
                        </div>
                    </div>
                );
            })}
        </div>
    );
};

export default PerformanceStatsGrid;
