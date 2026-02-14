import React from 'react';
import { Activity, Crosshair } from 'lucide-react';

const StrategySignalPanel = ({ strategyState, strategyName }) => {
    const isLoading = !strategyState;

    const {
        symbol = "-",
        reference_price = 0,
        start_time = "--:--",
    } = strategyState || {};

    const fmtPrice = (val) => val ? val.toLocaleString() : '-';

    // Collect boolean state keys for badges
    const boolEntries = strategyState
        ? Object.entries(strategyState).filter(([k, v]) => typeof v === 'boolean' && !BADGE_HIDDEN.has(k))
        : [];

    // Collect numeric/string state keys for grid display
    const dataEntries = strategyState
        ? Object.entries(strategyState).filter(([k, v]) =>
            !GRID_HIDDEN.has(k) && v != null && typeof v !== 'boolean' && typeof v !== 'object'
        ).slice(0, 10)
        : [];

    // Find a progress-like pair (xxx_percent vs target_xxx or similar)
    const progressInfo = findProgressPair(strategyState);

    return (
        <div className="bg-[#1e1e24] border border-white/5 rounded-xl p-4 flex flex-col gap-4 min-h-[160px]">
            {/* Header */}
            <div className="flex justify-between items-center border-b border-white/5 pb-2">
                <div className="flex items-center gap-2">
                    <Crosshair size={16} className="text-purple-400" />
                    <span className="text-sm font-bold text-gray-200">Strategy Signal Monitor</span>
                    <span className="text-xs text-gray-500 bg-black/30 px-2 py-0.5 rounded border border-white/5">
                        {isLoading ? <span className="animate-pulse">Loading...</span> : symbol}
                    </span>
                </div>
                <div className="text-xs font-mono text-gray-400 flex gap-3">
                    {reference_price > 0 && <span>Ref: <span className="text-white">{fmtPrice(reference_price)}</span></span>}
                    {start_time !== "--:--" && <span>Start: <span className="text-white">{start_time}</span></span>}
                </div>
            </div>

            {isLoading ? (
                <div className="flex-1 flex flex-col items-center justify-center text-gray-600 gap-2 py-4">
                    <Activity className="animate-pulse opacity-30" size={32} />
                    <span className="text-xs">Waiting for strategy data...</span>
                </div>
            ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6 animate-fade-in">
                    {/* Left: Status Badges */}
                    <div className="space-y-3">
                        <div className="text-xs text-gray-500 font-bold uppercase tracking-wider mb-2">Strategy Pipeline</div>
                        {boolEntries.length > 0 ? (
                            <div className="flex flex-wrap gap-2">
                                {boolEntries.map(([key, val]) => (
                                    <div key={key} className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-bold transition-all ${val
                                        ? 'bg-green-500/10 border-green-500/50 text-green-400'
                                        : 'bg-gray-800/50 border-gray-700 text-gray-500 opacity-60'
                                    }`}>
                                        <div className={`w-1.5 h-1.5 rounded-full ${val ? 'bg-green-400' : 'bg-gray-600'}`} />
                                        {formatLabel(key)}
                                    </div>
                                ))}
                            </div>
                        ) : (
                            <div className="text-xs text-gray-600">No pipeline stages</div>
                        )}

                        {/* Data grid (non-boolean values) */}
                        {dataEntries.length > 0 && (
                            <div className="grid grid-cols-2 gap-x-4 gap-y-1 mt-3">
                                {dataEntries.map(([key, val]) => (
                                    <div key={key} className="flex items-center justify-between">
                                        <span className="text-[10px] text-gray-500">{formatLabel(key)}</span>
                                        <span className="text-xs font-mono text-white">{formatStateValue(key, val)}</span>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>

                    {/* Right: Progress bar (if applicable) */}
                    {progressInfo && (
                        <div className="flex flex-col justify-center">
                            <div className="flex justify-between text-xs mb-1">
                                <span className="text-gray-400 font-bold">{progressInfo.label}</span>
                                <div className="flex gap-2">
                                    <span className="text-indigo-400 font-mono">{formatStateValue(progressInfo.currentKey, progressInfo.current)}</span>
                                    <span className="text-gray-600">/</span>
                                    <span className="text-gray-400 font-mono">{formatStateValue(progressInfo.targetKey, progressInfo.target)}</span>
                                </div>
                            </div>
                            <div className="h-3 w-full bg-gray-800 rounded-full overflow-hidden relative border border-white/5">
                                <div
                                    className={`h-full transition-all duration-500 ease-out ${progressInfo.percent >= 100
                                        ? 'bg-green-500 shadow-[0_0_15px_rgba(34,197,94,0.5)]'
                                        : 'bg-indigo-600'
                                    }`}
                                    style={{ width: `${Math.min(100, progressInfo.percent)}%` }}
                                />
                            </div>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
};

/* ───── Helpers ───── */

const BADGE_HIDDEN = new Set(['is_paper', 'is_hodl']);
const GRID_HIDDEN = new Set([
    'symbol', 'strategy_id', 'is_paper', 'status', 'current_price',
    'reference_price', 'entries', 'pending_entry', 'pending_exit',
    'current_level', 'max_buy_count', 'total_quantity', 'average_price',
    'profit_percent', 'trailing_active', 'is_hodl', 'start_time',
]);

const KEY_LABELS = {
    target_dip: 'Target Dip', dip_percent: 'Dip%', current_rsi: 'RSI',
    trigger_level: 'RSI Trigger', trigger_armed: 'Trigger Armed',
    target_profit: 'Target Profit', direction: 'Direction',
    target_percent: 'Target%', change_percent: 'Change%',
    delay_minutes: 'Delay(min)', is_delay_passed: 'Delay Passed',
    has_bought: 'Position', checked_today: 'Checked',
    cycle_max_hours: 'Max Hours',
};

const formatLabel = (key) => KEY_LABELS[key] || key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());

const formatStateValue = (key, val) => {
    if (val === true) return 'Yes';
    if (val === false) return 'No';
    if (val == null) return '--';
    if (typeof val === 'number') {
        if (key.includes('percent') || key.includes('pct')) return `${(val * 100).toFixed(2)}%`;
        if (key.includes('price') || val > 1000) return Math.round(val).toLocaleString();
        if (Number.isInteger(val)) return val.toString();
        return val.toFixed(2);
    }
    return String(val);
};

// Detect progress pair: e.g. dip_percent + target_dip, or change_percent + target_percent
const PROGRESS_PAIRS = [
    { currentKey: 'dip_percent', targetKey: 'target_dip', label: 'Dip Progress' },
    { currentKey: 'change_percent', targetKey: 'target_percent', label: 'Momentum Target' },
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

export default StrategySignalPanel;
