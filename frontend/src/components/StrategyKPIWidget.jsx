import React from 'react';
import { Activity } from 'lucide-react';

/**
 * StrategyKPIWidget - Generic strategy live metrics display
 * Works for any strategy by auto-displaying state key-value pairs.
 */
const StrategyKPIWidget = ({ strategyId, strategyConfig, liveData, strategyState }) => {
    const state = strategyState || {};
    const config = strategyConfig || {};

    // Merge config + state for display (state takes priority)
    const merged = { ...config, ...state };

    // Boolean entries → badges
    const boolEntries = Object.entries(merged)
        .filter(([k, v]) => typeof v === 'boolean' && !HIDDEN_KEYS.has(k));

    // Non-boolean displayable entries
    const dataEntries = Object.entries(merged)
        .filter(([k, v]) => !HIDDEN_KEYS.has(k) && v != null && typeof v !== 'boolean' && typeof v !== 'object')
        .slice(0, 12);

    // Detect progress pair
    const progressInfo = findProgressPair(merged);

    const hasContent = boolEntries.length > 0 || dataEntries.length > 0;
    if (!hasContent && !strategyId) return null;

    return (
        <div className="bg-gradient-to-br from-indigo-900/30 to-slate-900/20 border border-indigo-500/30 rounded-xl p-4 mb-6">
            {/* Header */}
            <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                    <Activity size={18} className="text-indigo-400" />
                    <span className="text-sm font-bold text-white">
                        {formatLabel(strategyId || 'strategy')} Monitor
                    </span>
                </div>
                {boolEntries.length > 0 && (
                    <div className="flex gap-2">
                        {boolEntries.map(([key, val]) => (
                            <span key={key} className={`text-[10px] font-bold px-2 py-0.5 rounded uppercase border ${val
                                ? 'bg-green-500/20 text-green-400 border-green-500/30'
                                : 'bg-gray-500/20 text-gray-500 border-gray-500/30'
                            }`}>
                                {formatLabel(key)}
                            </span>
                        ))}
                    </div>
                )}
            </div>

            {/* Stats Grid */}
            {dataEntries.length > 0 && (
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
                    {dataEntries.slice(0, 8).map(([key, val]) => (
                        <div key={key} className="bg-black/30 rounded-lg p-3 text-center">
                            <div className="text-gray-400 text-[10px] uppercase tracking-wider mb-1">
                                {formatLabel(key)}
                            </div>
                            <div className="text-lg font-mono text-white">
                                {formatStateValue(key, val)}
                            </div>
                        </div>
                    ))}
                </div>
            )}

            {/* Overflow entries (9-12) as compact row */}
            {dataEntries.length > 8 && (
                <div className="grid grid-cols-2 gap-x-4 gap-y-1 mb-4 px-1">
                    {dataEntries.slice(8).map(([key, val]) => (
                        <div key={key} className="flex items-center justify-between">
                            <span className="text-[10px] text-gray-500">{formatLabel(key)}</span>
                            <span className="text-xs font-mono text-white">{formatStateValue(key, val)}</span>
                        </div>
                    ))}
                </div>
            )}

            {/* Progress Bar */}
            {progressInfo && (
                <div className="bg-black/30 rounded-lg p-3">
                    <div className="flex justify-between text-[10px] text-gray-400 mb-2">
                        <span>{formatLabel(progressInfo.currentKey)}</span>
                        <span className="font-bold">{progressInfo.label}</span>
                        <span className="text-indigo-400">
                            Target: {formatStateValue(progressInfo.targetKey, progressInfo.target)}
                        </span>
                    </div>
                    <div className="w-full bg-gray-800 rounded-full h-2 relative">
                        <div
                            className={`h-2 rounded-full transition-all duration-1000 ${
                                progressInfo.percent >= 100
                                    ? 'bg-green-500 shadow-[0_0_15px_rgba(34,197,94,0.5)]'
                                    : 'bg-indigo-500'
                            }`}
                            style={{ width: `${Math.min(100, progressInfo.percent)}%` }}
                        />
                    </div>
                    <div className="text-center mt-1 text-[10px] text-gray-500 font-mono">
                        Current: <span className="text-white">{formatStateValue(progressInfo.currentKey, progressInfo.current)}</span>
                    </div>
                </div>
            )}

            {/* No data fallback */}
            {!hasContent && (
                <div className="text-gray-400 text-sm">
                    {strategyId ? `${strategyId} 전략 실행 중` : '전략 정보 없음'}
                </div>
            )}
        </div>
    );
};

/* ───── Helpers ───── */

const HIDDEN_KEYS = new Set([
    'symbol', 'strategy_id', 'is_paper', 'status', 'current_price',
    'reference_price', 'entries', 'pending_entry', 'pending_exit',
    'current_level', 'max_buy_count', 'total_quantity', 'average_price',
    'profit_percent',
]);

const KEY_LABELS = {
    target_dip: 'Target Dip', dip_percent: 'Dip%', current_rsi: 'RSI',
    trigger_level: 'RSI Trigger', trigger_armed: 'Trigger Armed',
    target_profit_pct: 'Target Profit', target_price: 'Target Price', direction: 'Direction',
    target_percent: 'Target%', change_percent: 'Change%',
    start_time: 'Start', stop_time: 'Stop', delay_minutes: 'Delay(min)',
    is_delay_passed: 'Delay Passed', has_bought: 'Position', checked_today: 'Checked',
    cycle_max_hours: 'Max Hours', trailing_active: 'Trailing', is_hodl: 'HODL',
    rsi_period: 'RSI Period', oversold: 'Oversold', overbought: 'Overbought',
};

const formatLabel = (key) => KEY_LABELS[key] || key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());

const formatStateValue = (key, val) => {
    if (val === true) return 'Yes';
    if (val === false) return 'No';
    if (val == null) return '--';
    if (typeof val === 'number') {
        if (key.endsWith('_pct')) return `${val}%`;
        if (key.includes('percent') || key.includes('pct')) return `${(val * 100).toFixed(2)}%`;
        if (key.includes('price') || val > 1000) return Math.round(val).toLocaleString();
        if (Number.isInteger(val)) return val.toString();
        return val.toFixed(2);
    }
    return String(val);
};

const PROGRESS_PAIRS = [
    { currentKey: 'dip_percent', targetKey: 'target_dip', label: 'Dip Progress' },
    { currentKey: 'change_percent', targetKey: 'target_percent', label: 'Momentum Target' },
    { currentKey: 'current_rsi', targetKey: 'oversold', label: 'RSI Level' },
];

function findProgressPair(state) {
    if (!state) return null;
    for (const pair of PROGRESS_PAIRS) {
        const current = state[pair.currentKey];
        const target = state[pair.targetKey];
        if (current != null && target != null && target !== 0) {
            const percent = Math.min(100, Math.max(0, Math.abs(current / target) * 100));
            return { ...pair, current, target, percent };
        }
    }
    return null;
}

export default StrategyKPIWidget;
