import React from 'react';

const ParallelSessionsGrid = ({
    parallelSessions,
    sessionDataList,
    configList,
    savedSymbols,
    currentRankIndex,
    onRankSelect,
    strategyName,
    executionMode = 'parallel',
}) => {
    if (!configList || configList.length === 0) return null;

    // Build a lookup: symbol -> session data
    const sessionBySymbol = {};
    (sessionDataList || []).forEach(s => {
        sessionBySymbol[s.symbol] = s;
    });

    // Build ranks: active configs with optional session data
    const ranks = [];
    configList.forEach((cfg, idx) => {
        if (!cfg.is_active) return;
        const sid = parallelSessions[idx];
        const session = sessionBySymbol[cfg.symbol] || null;
        const isRunning = !!(sid && session?.is_running);
        ranks.push({ idx, cfg, session, sid, isRunning });
    });

    if (ranks.length === 0) return null;

    const isExclusive = executionMode === 'exclusive';

    return (
        <div className="w-full mb-4">
            <div className="flex items-center gap-2 mb-3">
                <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
                    {isExclusive ? 'Rank Overview' : 'Parallel Sessions'}
                </span>
                <span className="text-[10px] text-gray-600">
                    ({ranks.filter(r => r.isRunning).length}/{ranks.length} active)
                </span>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-3">
                {ranks.map(({ idx, cfg, session, isRunning }) => {
                    const isSelected = idx === currentRankIndex;
                    const symbolMatch = savedSymbols?.find(s => s.code === cfg.symbol);
                    const symbolName = symbolMatch ? symbolMatch.name : cfg.symbol;
                    const hasData = !!session;
                    const state = session?.strategy_state || {};
                    const price = session?.current_price || 0;
                    const pnl = session?.pnl || 0;
                    const isPaper = session?.is_paper ?? true;
                    const tradeStats = session?.trade_stats || {};

                    return (
                        <div
                            key={idx}
                            onClick={() => onRankSelect(idx)}
                            className={`
                                relative p-3 rounded-lg cursor-pointer transition-all duration-200
                                ${isSelected
                                    ? 'bg-indigo-500/10 border border-indigo-500/50 shadow-lg shadow-indigo-500/10'
                                    : isRunning
                                        ? 'bg-black/30 border border-white/5 hover:border-white/20 hover:bg-black/40'
                                        : 'bg-black/20 border border-white/[0.03] hover:border-white/10 opacity-50'
                                }
                            `}
                        >
                            {/* Header: Rank badge + Symbol + Mode badge */}
                            <div className="flex items-center justify-between mb-2">
                                <div className="flex items-center gap-1.5">
                                    <span className={`
                                        text-[10px] font-bold px-1.5 py-0.5 rounded
                                        ${isSelected ? 'bg-indigo-500/30 text-indigo-300' : 'bg-gray-700/50 text-gray-400'}
                                    `}>
                                        R{idx + 1}
                                    </span>
                                    <span className={`text-xs font-medium truncate max-w-[80px] ${isRunning ? 'text-white' : 'text-gray-500'}`}>
                                        {symbolName}
                                    </span>
                                    {hasData && (
                                        <span className={`text-[8px] font-bold px-1 py-0.5 rounded ${
                                            isPaper
                                                ? 'bg-yellow-500/20 text-yellow-400'
                                                : 'bg-red-500/20 text-red-400'
                                        }`}>
                                            {isPaper ? 'P' : 'R'}
                                        </span>
                                    )}
                                </div>
                                <div className={`w-1.5 h-1.5 rounded-full ${isRunning ? 'bg-green-400 animate-pulse' : 'bg-gray-600'}`} />
                            </div>

                            {hasData ? (
                                <>
                                    {/* Price */}
                                    <div className={`text-sm font-mono font-semibold mb-1 ${isRunning ? 'text-white' : 'text-gray-500'}`}>
                                        {price.toLocaleString()}
                                    </div>

                                    {/* PnL */}
                                    <div className={`text-[11px] font-mono ${
                                        !isRunning ? 'text-gray-600' : pnl >= 0 ? 'text-green-400' : 'text-red-400'
                                    }`}>
                                        {pnl >= 0 ? '+' : ''}{pnl.toLocaleString()}
                                    </div>

                                    {/* Strategy-specific: Dip Martingale */}
                                    {strategyName === 'dip_martingale' && state.strategy_id === 'dip_martingale' && (
                                        <DipMartingaleMini state={state} price={price} pnl={pnl} dimmed={!isRunning} isPaper={isPaper} tradeStats={tradeStats} />
                                    )}
                                </>
                            ) : (
                                <div className="text-[11px] text-gray-600 font-mono">
                                    {isExclusive ? 'Inactive' : 'No data'}
                                </div>
                            )}
                        </div>
                    );
                })}
            </div>
        </div>
    );
};

const DipMartingaleMini = ({ state, price, pnl = 0, dimmed = false, isPaper = true, tradeStats = {} }) => {
    const currentLevel = state.current_level || 0;
    const maxLevels = state.max_levels || 4;
    const paperCycle = state.paper_cycle_id ?? state.cycle_id ?? 0;
    const realCycle = state.real_cycle_id ?? 0;
    const cycleNum = isPaper ? paperCycle : realCycle;
    const totalQty = state.total_quantity || 0;
    const avgPrice = state.average_price || 0;
    const refPrice = state.reference_price || 0;
    const targetDip = Math.abs(state.target_dip || 0.01);
    const dipPct = Math.abs(state.dip_percent || 0) * 100;
    const targetDipPct = targetDip * 100;
    const dipProgress = Math.min(100, (dipPct / targetDipPct) * 100);

    // Trigger price
    const triggerPrice = refPrice > 0 ? Math.round(refPrice * (1 - targetDip)) : 0;

    // Current cycle unrealized PnL (from session pnl)
    const curPnl = pnl || 0;
    const curPnlPct = (avgPrice > 0 && totalQty > 0)
        ? ((price - avgPrice) / avgPrice * 100)
        : 0;

    // Accumulated stats
    const modeStats = isPaper ? (tradeStats?.paper || {}) : (tradeStats?.real || {});
    const accCycles = modeStats.cycles || 0;
    const accPnl = modeStats.realized_pnl || 0;
    const accPnlPct = modeStats.realized_pnl_pct || 0;

    const dim = dimmed ? 'text-gray-700' : 'text-gray-500';

    const formatPnl = (v) => {
        if (!v) return '0';
        const abs = Math.abs(v);
        const str = abs >= 1000000 ? `${(abs / 1000000).toFixed(1)}M`
            : abs >= 1000 ? `${(abs / 1000).toFixed(0)}K`
            : abs.toLocaleString();
        return (v >= 0 ? '+' : '-') + str;
    };

    const pnlColor = (v) => dimmed ? '' : (v >= 0 ? 'text-green-400' : 'text-red-400');

    return (
        <div className={`mt-2 pt-2 border-t ${dimmed ? 'border-white/[0.03]' : 'border-white/5'}`}>
            {/* Row 1: #cycle L{level} dots + qty */}
            <div className="flex items-center justify-between mb-1.5">
                <div className="flex items-center gap-1.5">
                    <span className={`text-[9px] font-bold ${dimmed ? 'text-gray-600' : 'text-indigo-400'}`}>
                        #{accCycles + 1}
                    </span>
                    <span className={`text-[9px] ${dim}`}>
                        L{currentLevel}
                    </span>
                    <div className="flex gap-0.5">
                        {Array.from({ length: maxLevels }, (_, i) => (
                            <div
                                key={i}
                                className={`h-1.5 w-1.5 rounded-full ${
                                    i < currentLevel
                                        ? (dimmed ? 'bg-indigo-700' : 'bg-indigo-400')
                                        : (dimmed ? 'bg-gray-800' : 'bg-gray-700')
                                }`}
                            />
                        ))}
                    </div>
                </div>
                {totalQty > 0 && (
                    <span className={`text-[9px] ${dim}`}>{totalQty}qty</span>
                )}
            </div>

            {/* Row 2: Dip progress bar */}
            <div className="flex items-center gap-2 mb-1.5">
                <div className={`flex-1 rounded-full h-1.5 ${dimmed ? 'bg-gray-900' : 'bg-gray-800'}`}>
                    <div
                        className={`h-1.5 rounded-full transition-all duration-500 ${dimmed ? 'bg-indigo-800' : 'bg-indigo-500'}`}
                        style={{ width: `${dipProgress}%` }}
                    />
                </div>
                <span className={`text-[9px] w-10 text-right ${dim}`}>
                    {dipPct.toFixed(1)}%
                </span>
            </div>

            {/* Row 3: Trigger price & distance (price unit) */}
            {triggerPrice > 0 && (
                <div className={`flex items-center justify-between text-[9px] mb-1.5 ${dim}`}>
                    <span>Trig: {triggerPrice.toLocaleString()}</span>
                    <span className={!dimmed && Math.abs(price - triggerPrice) < price * 0.003 ? 'text-yellow-400' : ''}>
                        {price >= triggerPrice ? '-' : '+'}{Math.abs(price - triggerPrice).toLocaleString()}
                    </span>
                </div>
            )}

            {/* Row 4: Accumulated PnL */}
            <div className={`pt-1.5 border-t ${dimmed ? 'border-white/[0.02]' : 'border-white/[0.04]'}`}>
                <div className="flex items-center justify-between text-[9px]">
                    <span className={dim}>Total {accCycles} {accCycles === 1 ? 'Cycle' : 'Cycles'}</span>
                    <span className={pnlColor(accPnl)}>
                        {formatPnl(accPnl)}
                        {accPnlPct !== 0 && <span className="text-[8px] opacity-70"> ({accPnlPct >= 0 ? '+' : ''}{accPnlPct.toFixed(1)}%)</span>}
                    </span>
                </div>
            </div>
        </div>
    );
};

export default ParallelSessionsGrid;
