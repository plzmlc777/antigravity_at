import React from 'react';

const UnifiedSessionCards = ({
    parallelSessions,
    sessionDataList,
    configList,
    savedSymbols,
    currentRankIndex,
    onRankSelect,
    strategyName,
    executionMode = 'parallel',
    strategyState,
    liveData,
    accumulatedStats = {}, // { symbol: { paper: {...}, real: {...} } }
}) => {
    if (!configList || configList.length === 0) return null;

    // Build lookup: symbol -> session data
    const sessionBySymbol = {};
    (sessionDataList || []).forEach(s => {
        sessionBySymbol[s.symbol] = s;
    });

    // Build ranks: active configs with optional session data
    const ranks = [];
    configList.forEach((cfg, idx) => {
        if (!cfg.is_active) return;
        const sid = parallelSessions?.[idx];
        const session = sessionBySymbol[cfg.symbol] || null;
        const isRunning = !!(sid && session?.is_running);
        ranks.push({ idx, cfg, session, sid, isRunning });
    });

    if (ranks.length === 0) return null;

    const isExclusive = executionMode === 'exclusive';

    // Calculate total stats across all running sessions (current session data only)
    const totalStats = (() => {
        let totalCycles = 0;
        let totalPnl = 0;
        let totalWins = 0;
        let allCyclePnls = [];

        ranks.forEach(({ session }) => {
            const sessionStats = session?.trade_stats;
            if (!sessionStats) return;

            // Combine paper + real stats from current session
            ['paper', 'real'].forEach(mode => {
                const s = sessionStats[mode];
                if (!s || !s.cycles) return;
                totalCycles += s.cycles;
                totalPnl += s.realized_pnl || 0;
                totalWins += Math.round((s.win_rate || 0) * s.cycles / 100);
                // Reconstruct cycle PnLs for max/min/avg
                if (s.max_pnl) allCyclePnls.push(s.max_pnl);
                if (s.min_pnl) allCyclePnls.push(s.min_pnl);
            });
        });

        const winRate = totalCycles > 0 ? (totalWins / totalCycles) * 100 : 0;
        const maxPnl = allCyclePnls.length > 0 ? Math.max(...allCyclePnls) : 0;
        const minPnl = allCyclePnls.length > 0 ? Math.min(...allCyclePnls) : 0;
        const avgPnl = totalCycles > 0 ? totalPnl / totalCycles : 0;

        return { totalCycles, totalPnl, winRate, maxPnl, minPnl, avgPnl };
    })();

    const formatPnlCompact = (v) => {
        if (!v) return '0';
        const abs = Math.abs(v);
        const str = abs >= 1000000 ? `${(abs / 1000000).toFixed(1)}M`
            : abs >= 1000 ? `${(abs / 1000).toFixed(0)}K`
            : abs.toLocaleString();
        return (v >= 0 ? '+' : '-') + str;
    };

    return (
        <div className="w-full">
            <div className="flex items-center gap-2 mb-3">
                <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
                    {isExclusive ? 'Rank Overview' : 'Session Overview'}
                </span>
                <span className="text-[10px] text-gray-600">
                    ({ranks.filter(r => r.isRunning).length}/{ranks.length} active)
                </span>
            </div>
            <div className="flex flex-col gap-3">
                {/* Total Summary Row */}
                {totalStats.totalCycles > 0 && (
                    <div className="rounded-xl bg-gradient-to-r from-indigo-900/30 to-purple-900/30 border border-indigo-500/30 px-4 py-3">
                        <div className="flex items-center justify-between">
                            <div className="flex items-center gap-3">
                                <span className="text-xs font-bold text-indigo-300 uppercase tracking-wider">Total</span>
                                <span className="text-xs text-gray-400">
                                    {totalStats.totalCycles} Cycles
                                </span>
                                <span className={`text-xs font-mono font-semibold ${
                                    totalStats.winRate >= 60 ? 'text-green-400' :
                                    totalStats.winRate >= 40 ? 'text-yellow-400' : 'text-red-400'
                                }`}>
                                    Win {totalStats.winRate.toFixed(0)}%
                                </span>
                            </div>
                            <div className="flex items-center gap-4">
                                <span className={`text-sm font-mono font-bold ${totalStats.totalPnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                    {formatPnlCompact(totalStats.totalPnl)}
                                </span>
                                <div className="flex items-center gap-2 text-[10px] font-mono text-gray-500">
                                    <span>Max <span className="text-green-400">{formatPnlCompact(totalStats.maxPnl)}</span></span>
                                    <span>/</span>
                                    <span>Avg <span className="text-white">{formatPnlCompact(totalStats.avgPnl)}</span></span>
                                    <span>/</span>
                                    <span>Min <span className="text-red-400">{formatPnlCompact(totalStats.minPnl)}</span></span>
                                </div>
                            </div>
                        </div>
                    </div>
                )}
                {ranks.map(({ idx, cfg, session, isRunning }) => {
                    const isSelected = idx === currentRankIndex;
                    const symbolMatch = savedSymbols?.find(s => s.code === cfg.symbol);
                    const symbolName = symbolMatch ? symbolMatch.name : cfg.symbol;
                    const hasData = !!session;
                    const state = session?.strategy_state || {};
                    const price = session?.current_price || 0;
                    const pnl = session?.pnl || 0;
                    const isPaper = session?.is_paper ?? true;
                    // Use current session's trade_stats (not accumulated historical data)
                    const sessionStats = session?.trade_stats || {};
                    const accHasTrades = (sessionStats.paper?.trades > 0) || (sessionStats.real?.trades > 0);
                    const tradeStats = sessionStats;
                    const hasAccumulatedData = accHasTrades;

                    // Use strategyState for selected rank (more up-to-date from WebSocket)
                    const activeState = (isSelected && strategyState) ? strategyState : state;
                    const effectiveStrategyId = activeState.strategy_id || strategyName;

                    return (
                        <div
                            key={idx}
                            onClick={() => onRankSelect(idx)}
                            className={`
                                relative rounded-xl cursor-pointer transition-all duration-200 overflow-hidden
                                ${isSelected
                                    ? 'bg-[#1a1a2e]'
                                    : isRunning
                                        ? 'bg-[#1e1e24] border border-white/5 hover:border-white/20'
                                        : 'bg-[#1a1a1f] border border-white/[0.03] hover:border-white/10 opacity-60'
                                }
                            `}
                            style={isSelected ? {
                                border: '2px solid #6366f1',
                                boxShadow: '0 0 12px rgba(99, 102, 241, 0.4)'
                            } : {}}
                        >
                            {/* Header Row */}
                            <div className={`flex items-center justify-between px-4 py-3 ${isSelected ? 'bg-indigo-500/5' : 'bg-black/20'}`}>
                                <div className="flex items-center gap-3">
                                    <span className={`
                                        text-xs font-bold px-2 py-0.5 rounded
                                        ${isSelected ? 'bg-indigo-500/30 text-indigo-300' : 'bg-gray-700/50 text-gray-400'}
                                    `}>
                                        {cfg.tabName?.replace('Rank ', 'R') || `R${cfg.rank ?? (idx + 1)}`}
                                    </span>
                                    <span className={`text-sm font-semibold ${isRunning ? 'text-white' : 'text-gray-500'}`}>
                                        {symbolName}
                                    </span>
                                    <span className="text-xs text-gray-600 font-mono">
                                        {cfg.symbol}
                                    </span>
                                    {hasData && (
                                        <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded ${
                                            isPaper
                                                ? 'bg-yellow-500/20 text-yellow-400'
                                                : 'bg-red-500/20 text-red-400'
                                        }`}>
                                            {isPaper ? 'PAPER' : 'REAL'}
                                        </span>
                                    )}
                                </div>
                                <div className="flex items-center gap-4">
                                    {hasData && (
                                        <>
                                            <span className={`text-base font-mono font-semibold ${isRunning ? 'text-white' : 'text-gray-500'}`}>
                                                {price.toLocaleString()}
                                            </span>
                                            <span className={`text-sm font-mono ${
                                                !isRunning ? 'text-gray-600' : pnl >= 0 ? 'text-green-400' : 'text-red-400'
                                            }`}>
                                                {pnl >= 0 ? '+' : ''}{pnl.toLocaleString()}
                                            </span>
                                        </>
                                    )}
                                    <div className={`w-2 h-2 rounded-full ${isRunning ? 'bg-green-400 animate-pulse' : 'bg-gray-600'}`} />
                                </div>
                            </div>

                            {/* Strategy state card - generic for all strategies */}
                            {(hasData || hasAccumulatedData) && (
                                <GenericStrategyCard
                                    state={activeState}
                                    config={cfg}
                                    price={price}
                                    isPaper={isPaper}
                                    tradeStats={tradeStats}
                                    dimmed={!isRunning}
                                />
                            )}

                            {!hasData && !hasAccumulatedData && (
                                <div className="px-4 py-3 text-sm text-gray-600 font-mono">
                                    {isRunning ? 'Monitoring' : (isExclusive ? 'Inactive rank' : 'No trade history')}
                                </div>
                            )}
                        </div>
                    );
                })}
            </div>
        </div>
    );
};

/* ───── Generic Strategy Card Body (works for any strategy) ───── */
const HIDDEN_KEYS = new Set([
    'symbol', 'strategy_id', 'is_paper', 'status', 'current_price',
    'reference_price', 'entries', 'pending_entry', 'pending_exit',
    'current_level', 'max_buy_count', 'total_quantity', 'average_price',
    'profit_percent', 'trailing_active', 'is_hodl',
]);

const KEY_LABELS = {
    target_dip: 'Target Dip', dip_percent: 'Dip%', current_rsi: 'RSI',
    trigger_level: 'RSI Trigger', trigger_armed: 'Trigger Armed',
    target_profit: 'Target Profit', direction: 'Direction',
    target_percent: 'Target%', change_percent: 'Change%',
    start_time: 'Start', stop_time: 'Stop', delay_minutes: 'Delay(min)',
    is_delay_passed: 'Delay Passed', has_bought: 'Position', checked_today: 'Checked',
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

const GenericStrategyCard = ({ state, config = {}, price = 0, isPaper = true, tradeStats = {}, dimmed = false }) => {
    const currentLevel = state.current_level || 0;
    const maxLevels = state.max_buy_count || 0;
    const totalQty = state.total_quantity || 0;
    const avgPrice = state.average_price || 0;
    const profitPct = (state.profit_percent || 0) * 100;
    const isTrailing = state.trailing_active || false;
    const isHodl = state.is_hodl || false;
    const pendingEntry = state.pending_entry || false;
    const pendingExit = state.pending_exit || false;

    const dim = dimmed ? 'text-gray-700' : 'text-gray-500';
    const dimBorder = dimmed ? 'border-white/[0.02]' : 'border-white/[0.05]';

    // Collect displayable state entries
    const displayEntries = Object.entries(state)
        .filter(([k, v]) => !HIDDEN_KEYS.has(k) && v != null && typeof v !== 'object')
        .slice(0, 8);

    // Accumulated stats
    const paperStats = tradeStats?.paper || {};
    const realStats = tradeStats?.real || {};
    const totalCycles = (paperStats.cycles || 0) + (realStats.cycles || 0);
    const totalPnl = (paperStats.realized_pnl || 0) + (realStats.realized_pnl || 0);
    const totalPnlPct = (paperStats.realized_pnl_pct || 0) + (realStats.realized_pnl_pct || 0);
    const paperCycles = paperStats.cycles || 0;
    const realCycles = realStats.cycles || 0;
    const winRate = totalCycles > 0
        ? ((paperStats.win_rate || 0) * paperCycles + (realStats.win_rate || 0) * realCycles) / totalCycles : 0;
    const recent10 = totalCycles > 0
        ? ((paperStats.recent_10_win_rate || 0) * paperCycles + (realStats.recent_10_win_rate || 0) * realCycles) / totalCycles : 0;
    const maxPnl = Math.max(paperStats.max_pnl || 0, realStats.max_pnl || 0);
    const minPnl = Math.min(paperStats.min_pnl || 0, realStats.min_pnl || 0);
    const avgPnl = totalCycles > 0 ? totalPnl / totalCycles : 0;

    const formatPnl = (v) => {
        if (!v) return '0';
        const abs = Math.abs(v);
        const str = abs >= 1000000 ? `${(abs / 1000000).toFixed(1)}M`
            : abs >= 1000 ? `${(abs / 1000).toFixed(0)}K`
            : abs.toLocaleString();
        return (v >= 0 ? '+' : '-') + str;
    };
    const pnlColor = (v) => dimmed ? 'text-gray-700' : (v >= 0 ? 'text-green-400' : 'text-red-400');

    return (
        <div className="px-4 pb-3 pt-1">
            {/* Row 1: Level/Status + Qty + Avg Price + Profit */}
            <div className={`flex items-center justify-between py-2 border-b ${dimBorder}`}>
                <div className="flex items-center gap-3">
                    {maxLevels > 0 && (
                        <div className="flex items-center gap-1.5">
                            <span className={`text-xs font-bold ${dimmed ? 'text-gray-600' : 'text-indigo-400'}`}>
                                L{currentLevel}/{maxLevels}
                            </span>
                            {maxLevels <= 10 && (
                                <div className="flex gap-1">
                                    {Array.from({ length: maxLevels }, (_, i) => (
                                        <div key={i} className={`h-2 w-2 rounded-full transition-all ${
                                            i < currentLevel
                                                ? (dimmed ? 'bg-indigo-700' : 'bg-indigo-400 shadow-[0_0_6px_rgba(99,102,241,0.4)]')
                                                : (dimmed ? 'bg-gray-800' : 'bg-gray-700')
                                        }`} />
                                    ))}
                                </div>
                            )}
                        </div>
                    )}
                    {(pendingEntry || pendingExit) && (
                        <span className="text-[9px] font-bold px-1.5 py-0.5 rounded bg-orange-500/20 text-orange-400 animate-pulse">
                            {pendingEntry ? 'BUY...' : 'SELL...'}
                        </span>
                    )}
                    {isTrailing && (
                        <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded ${dimmed ? 'bg-gray-800 text-gray-600' : 'bg-green-500/20 text-green-400'}`}>
                            TRAILING
                        </span>
                    )}
                    {isHodl && (
                        <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded ${dimmed ? 'bg-gray-800 text-gray-600' : 'bg-red-500/20 text-red-400'}`}>
                            HODL
                        </span>
                    )}
                    {totalQty > 0 && (
                        <span className={`text-xs font-mono ${dim}`}>{totalQty} qty</span>
                    )}
                    {avgPrice > 0 && (
                        <span className={`text-xs font-mono ${dim}`}>Avg: {Math.round(avgPrice).toLocaleString()}</span>
                    )}
                </div>
                {avgPrice > 0 && (
                    <span className={`text-xs font-mono font-semibold ${dimmed ? 'text-gray-700' : profitPct >= 0 ? 'text-red-400' : 'text-blue-400'}`}>
                        {profitPct >= 0 ? '+' : ''}{profitPct.toFixed(2)}%
                    </span>
                )}
            </div>

            {/* Row 2: Dynamic state key-value grid */}
            {displayEntries.length > 0 && (
                <div className={`grid grid-cols-2 gap-x-4 gap-y-1 py-2 border-b ${dimBorder}`}>
                    {displayEntries.map(([key, val]) => (
                        <div key={key} className="flex items-center justify-between">
                            <span className={`text-[10px] ${dim}`}>{formatLabel(key)}</span>
                            <span className={`text-xs font-mono ${dimmed ? 'text-gray-600' : typeof val === 'boolean' ? (val ? 'text-green-400' : 'text-gray-600') : 'text-white'}`}>
                                {formatStateValue(key, val)}
                            </span>
                        </div>
                    ))}
                </div>
            )}

            {/* Row 3: Accumulated Stats */}
            <div className={`flex items-center justify-between py-2 ${totalCycles > 0 ? `border-b ${dimBorder}` : ''}`}>
                <div className="flex items-center gap-2">
                    <span className={`text-xs font-bold ${dimmed ? 'text-gray-600' : 'text-indigo-400'}`}>
                        #{totalCycles + 1}
                    </span>
                    <span className={`text-xs ${dim}`}>
                        Total {totalCycles} {totalCycles === 1 ? 'Cycle' : 'Cycles'}
                    </span>
                </div>
                <span className={`text-xs font-mono ${pnlColor(totalPnl)}`}>
                    {formatPnl(totalPnl)}
                    {totalPnlPct !== 0 && <span className="text-[10px] opacity-70"> ({totalPnlPct >= 0 ? '+' : ''}{totalPnlPct.toFixed(1)}%)</span>}
                </span>
            </div>

            {/* Row 4: Detailed Stats */}
            {totalCycles > 0 && (
                <div className="py-2">
                    <div className="flex items-center justify-between gap-4">
                        <div className="flex items-center gap-3">
                            <div className="flex items-center gap-1">
                                <span className={`text-[10px] ${dim}`}>Win</span>
                                <span className={`text-xs font-mono font-semibold ${
                                    dimmed ? 'text-gray-600' : winRate >= 60 ? 'text-green-400' : winRate >= 40 ? 'text-yellow-400' : 'text-red-400'
                                }`}>{winRate.toFixed(0)}%</span>
                            </div>
                            <div className="flex items-center gap-1">
                                <span className={`text-[10px] ${dim}`}>R10</span>
                                <span className={`text-xs font-mono font-semibold ${
                                    dimmed ? 'text-gray-600' : recent10 >= 60 ? 'text-green-400' : recent10 >= 40 ? 'text-yellow-400' : 'text-red-400'
                                }`}>{recent10.toFixed(0)}%</span>
                            </div>
                        </div>
                        <div className="flex items-center gap-2 text-[10px] font-mono">
                            <span className={dim}>Max</span><span className={dimmed ? 'text-gray-700' : 'text-green-400 font-semibold'}>{formatPnl(maxPnl)}</span>
                            <span className={dim}>/</span>
                            <span className={dim}>Avg</span><span className={dimmed ? 'text-gray-700' : 'text-white font-semibold'}>{formatPnl(avgPnl)}</span>
                            <span className={dim}>/</span>
                            <span className={dim}>Min</span><span className={dimmed ? 'text-gray-700' : 'text-red-400 font-semibold'}>{formatPnl(minPnl)}</span>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default UnifiedSessionCards;
