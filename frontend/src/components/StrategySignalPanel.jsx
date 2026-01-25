import React from 'react';
import { Activity, Clock, Crosshair, Target, Zap, AlertTriangle, ShieldCheck, TrendingUp, TrendingDown } from 'lucide-react';

const StrategySignalPanel = ({ strategyState }) => {
    // Default values / Loading state handling
    const isLoading = !strategyState;

    const {
        symbol = "-",
        reference_price = 0,
        current_price = 0,
        current_level = 0,
        max_levels = 4,
        trailing_active = false,
        is_hodl = false,
        dip_percent = 0,
        profit_percent = 0,
        target_dip = 0,
        target_profit = 0,
        start_time = "--:--",
        strategy_id = "" // Need to know which strategy it is
    } = strategyState || {};

    // Helper for Percentage display
    const fmtPct = (val) => typeof val === 'number' ? `${(val * 100).toFixed(2)}%` : '-';
    const fmtPrice = (val) => val ? val.toLocaleString() : '-';

    // Status Badge Helper
    const StatusBadge = ({ active, label, icon: Icon, color = "green" }) => (
        <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-bold transition-all ${active
            ? `bg-${color}-500/10 border-${color}-500/50 text-${color}-400 shadow-[0_0_10px_rgba(var(--tw-color-${color}-500-rgb),0.1)]`
            : 'bg-gray-800/50 border-gray-700 text-gray-500 opacity-60'
            }`}>
            <Icon size={12} className={active ? `text-${color}-400 animate-pulse` : ""} />
            {label}
        </div>
    );

    // Render Logic for Time Momentum (Legacy/Default)
    const renderTimeMomentum = () => {
        const targetVal = strategyState.direction === 'fall' ? -strategyState.target_percent : strategyState.target_percent;
        const progress = Math.min(100, Math.max(0, (strategyState.change_percent / (targetVal || 1)) * 100));

        return (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 animate-fade-in">
                <div className="space-y-3">
                    <div className="text-xs text-gray-500 font-bold uppercase tracking-wider mb-2">Entry Conditions</div>
                    <div className="flex flex-wrap gap-2">
                        <StatusBadge active={reference_price > 0} label="Reference Set" icon={Target} color="blue" />
                        <StatusBadge active={strategyState.is_delay_passed} label="Delay Passed" icon={Clock} color="blue" />
                        <StatusBadge active={strategyState.checked_today} label="Check Triggered" icon={Zap} color="yellow" />
                        <StatusBadge active={strategyState.has_bought} label="Position Active" icon={ShieldCheck} color="green" />
                    </div>
                </div>
                <div className="flex flex-col justify-center">
                    <div className="flex justify-between text-xs mb-1">
                        <span className="text-gray-400 font-bold">Momentum Target</span>
                        <div className="flex gap-2">
                            <span className={`${strategyState.change_percent >= 0 ? 'text-green-400' : 'text-red-400'} font-mono`}>{fmtPct(strategyState.change_percent)}</span>
                            <span className="text-gray-600">/</span>
                            <span className="text-blue-400 font-mono">{fmtPct(targetVal)}</span>
                        </div>
                    </div>
                    <div className="h-3 w-full bg-gray-800 rounded-full overflow-hidden relative border border-white/5">
                        <div className={`h-full transition-all duration-500 ease-out ${progress >= 100 ? 'bg-green-500 shadow-[0_0_15px_rgba(34,197,94,0.5)]' : 'bg-blue-600'}`} style={{ width: `${progress}%` }} />
                    </div>
                </div>
            </div>
        );
    };

    // Render Logic for Dip Martingale
    const renderDipMartingale = () => {
        const progress = Math.min(100, Math.max(0, (dip_percent / (target_dip || 0.01)) * 100));

        return (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 animate-fade-in">
                <div className="space-y-3">
                    <div className="text-xs text-gray-500 font-bold uppercase tracking-wider mb-2">Strategy Pipeline</div>
                    <div className="flex flex-wrap gap-2">
                        <StatusBadge active={reference_price > 0} label="Cycle Started" icon={Activity} color="indigo" />
                        <StatusBadge active={current_level >= 1} label="Initial Entry" icon={Zap} color="blue" />
                        <StatusBadge active={trailing_active} label="Trailing Stop" icon={ShieldCheck} color="green" />
                        <StatusBadge active={is_hodl} label="HODL Guard" icon={AlertTriangle} color="red" />
                    </div>
                </div>
                <div className="flex flex-col justify-center">
                    <div className="flex justify-between text-xs mb-1">
                        <span className="text-gray-400 font-bold">Initial Dip Depth</span>
                        <div className="flex gap-2">
                            <span className="text-indigo-400 font-mono">{fmtPct(dip_percent)}</span>
                            <span className="text-gray-600">/</span>
                            <span className="text-gray-400 font-mono">{fmtPct(target_dip)}</span>
                        </div>
                    </div>
                    <div className="h-3 w-full bg-gray-800 rounded-full overflow-hidden relative border border-white/5">
                        <div className={`h-full transition-all duration-500 ease-out ${progress >= 100 ? 'bg-indigo-500 shadow-[0_0_15px_rgba(99,102,241,0.5)]' : 'bg-slate-600'}`} style={{ width: `${progress}%` }} />
                    </div>
                    <div className="flex justify-between text-[10px] text-gray-500 mt-1 font-mono uppercase">
                        <span>Waiting</span>
                        <span>Entry Signal</span>
                    </div>
                </div>
            </div>
        );
    };

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
                    <span>Ref: <span className="text-white">{fmtPrice(reference_price)}</span></span>
                    {start_time !== "--:--" && <span>Start: <span className="text-white">{start_time}</span></span>}
                </div>
            </div>

            {isLoading ? (
                <div className="flex-1 flex flex-col items-center justify-center text-gray-600 gap-2 py-4">
                    <Activity className="animate-pulse opacity-30" size={32} />
                    <span className="text-xs">Waiting for strategy data...</span>
                </div>
            ) : (
                strategy_id === 'dip_martingale' ? renderDipMartingale() : renderTimeMomentum()
            )}
        </div>
    );
};

export default StrategySignalPanel;
