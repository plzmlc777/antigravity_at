import React from 'react';
import { Activity, Clock, Crosshair, Target, Zap, AlertTriangle, ShieldCheck, TrendingUp, TrendingDown } from 'lucide-react';

const StrategySignalPanel = ({ strategyState }) => {
    // Default values / Loading state handling
    const isLoading = !strategyState;

    const {
        symbol = "-",
        reference_price = 0,
        target_percent = 0.02,
        direction = "rise",
        change_percent = 0,
        is_delay_passed = false,
        has_bought = false,
        trending_active = false,
        safety_stop_percent = 0,
        checked_today = false,
        start_time = "--:--",
        current_price = 0
    } = strategyState || {};

    // Helper for Percentage display
    const fmtPct = (val) => typeof val === 'number' ? `${(val * 100).toFixed(2)}%` : '-';
    const fmtPrice = (val) => val ? val.toLocaleString() : '-';

    // Progress Bar Calculation
    const targetVal = direction === 'fall' ? -target_percent : target_percent;
    const progress = Math.min(100, Math.max(0, (change_percent / (targetVal || 1)) * 100)); // Avoid div by zero

    // Status Badge Helper
    const StatusBadge = ({ active, label, icon: Icon, color = "green" }) => (
        <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-bold transition-all ${active
            ? `bg-${color}-500/10 border-${color}-500/50 text-${color}-400 shadow-[0_0_10px_rgba(34,197,94,0.1)]`
            : 'bg-gray-800/50 border-gray-700 text-gray-500 opacity-60'
            }`}>
            <Icon size={12} className={active ? `text-${color}-400 animate-pulse` : ""} />
            {label}
        </div>
    );

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
                    <span>Base: <span className="text-white">{fmtPrice(reference_price)}</span></span>
                    <span>Start: <span className="text-white">{start_time}</span></span>
                </div>
            </div>

            {isLoading ? (
                // Loading / Empty State Overlay within the frame
                <div className="flex-1 flex flex-col items-center justify-center text-gray-600 gap-2 py-4">
                    <Activity className="animate-pulse opacity-30" size={32} />
                    <span className="text-xs">Waiting for strategy data...</span>
                </div>
            ) : (
                // Main Visuals grid
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6 animate-fade-in">

                    {/* 1. Condition Checklist */}
                    <div className="space-y-3">
                        <div className="text-xs text-gray-500 font-bold uppercase tracking-wider mb-2">Entry Conditions</div>
                        <div className="flex flex-wrap gap-2">
                            <StatusBadge
                                active={reference_price > 0}
                                label="Reference Set"
                                icon={Target}
                                color="blue"
                            />
                            <StatusBadge
                                active={is_delay_passed}
                                label="Delay Passed"
                                icon={Clock}
                                color="blue"
                            />
                            <StatusBadge
                                active={checked_today}
                                label="Check Triggered"
                                icon={Zap}
                                color="yellow"
                            />
                            <StatusBadge
                                active={has_bought}
                                label="Position Active"
                                icon={ShieldCheck}
                                color="green"
                            />
                        </div>
                    </div>

                    {/* 2. Momentum Gauge */}
                    <div className="flex flex-col justify-center">
                        <div className="flex justify-between text-xs mb-1">
                            <span className="text-gray-400 font-bold">Momentum Target</span>
                            <div className="flex gap-2">
                                <span className={`${change_percent >= 0 ? 'text-green-400' : 'text-red-400'} font-mono`}>
                                    {fmtPct(change_percent)}
                                </span>
                                <span className="text-gray-600">/</span>
                                <span className="text-blue-400 font-mono">{fmtPct(targetVal)}</span>
                            </div>
                        </div>

                        {/* Bar Container */}
                        <div className="h-3 w-full bg-gray-800 rounded-full overflow-hidden relative border border-white/5">
                            {/* Target Marker Line (if needed, simplified for now) */}
                            <div
                                className={`h-full transition-all duration-500 ease-out ${progress >= 100 ? 'bg-green-500 shadow-[0_0_15px_rgba(34,197,94,0.5)]' : 'bg-blue-600'
                                    }`}
                                style={{ width: `${progress}%` }}
                            />
                        </div>
                        <div className="flex justify-between text-[10px] text-gray-500 mt-1 font-mono">
                            <span>0%</span>
                            <span>{direction.toUpperCase()} TARGET</span>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default StrategySignalPanel;
