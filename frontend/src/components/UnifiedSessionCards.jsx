import React from 'react';
import { Activity, Zap, ShieldCheck, AlertTriangle, Clock, TrendingUp, TrendingDown, Timer, Target } from 'lucide-react';

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

    // Calculate total stats across all ranks
    const totalStats = (() => {
        let totalCycles = 0;
        let totalPnl = 0;
        let totalWins = 0;
        let allCyclePnls = [];

        ranks.forEach(({ cfg }) => {
            const symbolStats = accumulatedStats[cfg.symbol];
            if (!symbolStats) return;

            // Combine paper + real stats
            ['paper', 'real'].forEach(mode => {
                const s = symbolStats[mode];
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
                    // Always use accumulated stats from API (filtered by strategy_name)
                    // This includes ALL historical cycles across all sessions with the same strategy
                    const symbolAccStats = accumulatedStats[cfg.symbol] || {};
                    const accHasTrades = (symbolAccStats.paper?.trades > 0) || (symbolAccStats.real?.trades > 0);
                    const tradeStats = symbolAccStats;
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
                                    ? 'bg-[#1a1a2e] border border-indigo-500/50 shadow-lg shadow-indigo-500/10'
                                    : isRunning
                                        ? 'bg-[#1e1e24] border border-white/5 hover:border-white/20'
                                        : 'bg-[#1a1a1f] border border-white/[0.03] hover:border-white/10 opacity-60'
                                }
                            `}
                        >
                            {/* Header Row */}
                            <div className={`flex items-center justify-between px-4 py-3 ${isSelected ? 'bg-indigo-500/5' : 'bg-black/20'}`}>
                                <div className="flex items-center gap-3">
                                    <span className={`
                                        text-xs font-bold px-2 py-0.5 rounded
                                        ${isSelected ? 'bg-indigo-500/30 text-indigo-300' : 'bg-gray-700/50 text-gray-400'}
                                    `}>
                                        R{idx + 1}
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

                            {/* Strategy-specific content - show with live data or accumulated stats */}
                            {(hasData || hasAccumulatedData) && (effectiveStrategyId === 'dip_martingale' || effectiveStrategyId === 'rsi_martingale') && (
                                <DipMartingaleCard
                                    state={activeState}
                                    price={price}
                                    pnl={pnl}
                                    isPaper={isPaper}
                                    tradeStats={tradeStats}
                                    dimmed={!isRunning}
                                    isSelected={isSelected}
                                    strategyId={effectiveStrategyId}
                                />
                            )}

                            {(hasData || hasAccumulatedData) && effectiveStrategyId === 'time_momentum' && (
                                <TimeMomentumCard
                                    state={activeState}
                                    config={cfg}
                                    dimmed={!isRunning}
                                    tradeStats={tradeStats}
                                />
                            )}

                            {!hasData && !hasAccumulatedData && (
                                <div className="px-4 py-3 text-sm text-gray-600 font-mono">
                                    {isExclusive ? 'Inactive rank' : 'No trade history'}
                                </div>
                            )}
                        </div>
                    );
                })}
            </div>
        </div>
    );
};

/* ───── Dip/RSI Martingale Card Body ───── */
const DipMartingaleCard = ({ state, price, pnl = 0, isPaper = true, tradeStats = {}, dimmed = false, isSelected = false, strategyId = 'dip_martingale' }) => {
    const isRSI = strategyId === 'rsi_martingale';
    const currentLevel = state.current_level || 0;
    const maxLevels = state.max_levels || 4;
    const totalQty = state.total_quantity || 0;
    const avgPrice = state.average_price || 0;
    const refPrice = state.reference_price || 0;
    const targetDip = Math.abs(state.target_dip || 0.01);
    const dipPct = Math.abs(state.dip_percent || 0) * 100;
    const targetDipPct = targetDip * 100;
    const dipProgress = Math.min(100, (dipPct / targetDipPct) * 100);
    const profitPct = (state.profit_percent || 0) * 100;
    const isTrailing = state.trailing_active || false;
    const isHodl = state.is_hodl || false;

    // RSI specific
    const currentRSI = state.current_rsi;
    const triggerLevel = state.trigger_level || 30;
    const triggerArmed = state.trigger_armed || false;

    // Trigger price
    const triggerPrice = refPrice > 0 ? Math.round(refPrice * (1 - targetDip)) : 0;

    // Accumulated stats
    const modeStats = isPaper ? (tradeStats?.paper || {}) : (tradeStats?.real || {});
    const accCycles = modeStats.cycles || 0;
    const accPnl = modeStats.realized_pnl || 0;
    const accPnlPct = modeStats.realized_pnl_pct || 0;
    const winRate = modeStats.win_rate || 0;
    const recent10WinRate = modeStats.recent_10_win_rate || 0;
    const maxPnl = modeStats.max_pnl || 0;
    const minPnl = modeStats.min_pnl || 0;
    const avgPnl = modeStats.avg_pnl || 0;

    const dim = dimmed ? 'text-gray-700' : 'text-gray-500';
    const dimBorder = dimmed ? 'border-white/[0.02]' : 'border-white/[0.05]';

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
            {/* Row 1: Level + Qty + Avg Price + Profit */}
            <div className={`flex items-center justify-between py-2 border-b ${dimBorder}`}>
                <div className="flex items-center gap-3">
                    <div className="flex items-center gap-1.5">
                        <span className={`text-xs font-bold ${dimmed ? 'text-gray-600' : 'text-indigo-400'}`}>
                            L{currentLevel}/{maxLevels}
                        </span>
                        {maxLevels <= 10 && (
                            <div className="flex gap-1">
                                {Array.from({ length: maxLevels }, (_, i) => (
                                    <div
                                        key={i}
                                        className={`h-2 w-2 rounded-full transition-all ${
                                            i < currentLevel
                                                ? (dimmed ? 'bg-indigo-700' : 'bg-indigo-400 shadow-[0_0_6px_rgba(99,102,241,0.4)]')
                                                : (dimmed ? 'bg-gray-800' : 'bg-gray-700')
                                        }`}
                                    />
                                ))}
                            </div>
                        )}
                    </div>
                    {totalQty > 0 && (
                        <span className={`text-xs font-mono ${dim}`}>
                            {totalQty} qty
                            {state.entries && state.entries.length > 0 && (
                                <span className="text-gray-600 ml-0.5">
                                    ({state.entries.map(e => e.quantity).join(', ')})
                                </span>
                            )}
                        </span>
                    )}
                    {avgPrice > 0 && (
                        <span className={`text-xs font-mono ${dim}`}>
                            Avg: {Math.round(avgPrice).toLocaleString()}
                        </span>
                    )}
                </div>
                <div className="flex items-center gap-3">
                    {avgPrice > 0 && (
                        <span className={`text-xs font-mono font-semibold ${dimmed ? 'text-gray-700' : profitPct >= 0 ? 'text-red-400' : 'text-blue-400'}`}>
                            {profitPct >= 0 ? '+' : ''}{profitPct.toFixed(2)}%
                        </span>
                    )}
                </div>
            </div>

            {/* Row 2: RSI Info (only for RSI strategy) or Dip Progress */}
            {isRSI && (
                <div className={`flex items-center justify-between py-2 border-b ${dimBorder}`}>
                    <div className="flex items-center gap-3">
                        <span className={`text-xs ${dim}`}>RSI</span>
                        <span className={`text-sm font-mono font-bold ${
                            dimmed ? 'text-gray-600' :
                            currentRSI == null ? 'text-gray-500' :
                            currentRSI <= triggerLevel ? 'text-green-400' :
                            currentRSI >= 70 ? 'text-red-400' : 'text-white'
                        }`}>
                            {currentRSI != null ? currentRSI.toFixed(1) : '--'}
                        </span>
                        <span className={`text-[10px] ${dim}`}>
                            Trigger: {triggerLevel}
                        </span>
                    </div>
                    <span className={`text-[10px] px-2 py-0.5 rounded ${
                        dimmed ? 'bg-gray-800 text-gray-600' :
                        triggerArmed ? 'bg-green-500/20 text-green-400' : 'bg-gray-700/50 text-gray-500'
                    }`}>
                        {triggerArmed ? 'Armed' : 'Waiting'}
                    </span>
                </div>
            )}

            {/* Row 2b: Dip Progress + Trigger */}
            <div className={`flex items-center gap-4 py-2 border-b ${dimBorder}`}>
                <div className="flex-1">
                    <div className="flex items-center justify-between text-[10px] text-gray-500 mb-1">
                        <span>{isRSI ? 'Price Change' : 'Dip Progress'}</span>
                        <span>{dipPct.toFixed(1)}% / {targetDipPct.toFixed(1)}%</span>
                    </div>
                    <div className={`w-full rounded-full h-1.5 ${dimmed ? 'bg-gray-900' : 'bg-gray-800'}`}>
                        <div
                            className={`h-1.5 rounded-full transition-all duration-500 ${
                                dipProgress >= 100
                                    ? (dimmed ? 'bg-indigo-800' : 'bg-indigo-500 shadow-[0_0_10px_rgba(99,102,241,0.4)]')
                                    : (dimmed ? 'bg-indigo-800' : 'bg-indigo-500')
                            }`}
                            style={{ width: `${dipProgress}%` }}
                        />
                    </div>
                </div>
                {triggerPrice > 0 && (
                    <div className={`text-xs font-mono text-right ${dim}`}>
                        <div>Trigger: {triggerPrice.toLocaleString()}</div>
                        <div className={!dimmed && Math.abs(price - triggerPrice) < price * 0.003 ? 'text-yellow-400' : ''}>
                            {price >= triggerPrice ? '-' : '+'}{Math.abs(price - triggerPrice).toLocaleString()}
                        </div>
                    </div>
                )}
            </div>

            {/* Row 3: Pipeline Badges */}
            <div className={`flex items-center gap-2 py-2 border-b ${dimBorder}`}>
                <span className="text-[10px] text-gray-600 font-bold uppercase tracking-wider mr-1">Pipeline</span>
                <PipelineBadge active={refPrice > 0} label="Cycle Started" icon={Activity} color="indigo" dimmed={dimmed} />
                <PipelineBadge active={currentLevel >= 1} label="Initial Entry" icon={Zap} color="blue" dimmed={dimmed} />
                <PipelineBadge active={isTrailing} label="Trailing" icon={ShieldCheck} color="green" dimmed={dimmed} />
                <PipelineBadge active={isHodl} label="HODL" icon={AlertTriangle} color="red" dimmed={dimmed} />
            </div>

            {/* Row 4: Accumulated Stats Summary */}
            <div className={`flex items-center justify-between py-2 ${accCycles > 0 ? `border-b ${dimBorder}` : ''}`}>
                <div className="flex items-center gap-2">
                    <span className={`text-xs font-bold ${dimmed ? 'text-gray-600' : 'text-indigo-400'}`}>
                        #{accCycles + 1}
                    </span>
                    <span className={`text-xs ${dim}`}>
                        Total {accCycles} {accCycles === 1 ? 'Cycle' : 'Cycles'}
                    </span>
                </div>
                <span className={`text-xs font-mono ${pnlColor(accPnl)}`}>
                    {formatPnl(accPnl)}
                    {accPnlPct !== 0 && <span className="text-[10px] opacity-70"> ({accPnlPct >= 0 ? '+' : ''}{accPnlPct.toFixed(1)}%)</span>}
                </span>
            </div>

            {/* Row 5: Detailed Stats (only if has cycles) */}
            {accCycles > 0 && (
                <div className="py-2">
                    <div className="flex items-center justify-between gap-4">
                        {/* Win Rates */}
                        <div className="flex items-center gap-3">
                            <div className="flex items-center gap-1">
                                <span className={`text-[10px] ${dim}`}>Win</span>
                                <span className={`text-xs font-mono font-semibold ${
                                    dimmed ? 'text-gray-600' :
                                    winRate >= 60 ? 'text-green-400' :
                                    winRate >= 40 ? 'text-yellow-400' : 'text-red-400'
                                }`}>
                                    {winRate.toFixed(0)}%
                                </span>
                            </div>
                            <div className="flex items-center gap-1">
                                <span className={`text-[10px] ${dim}`}>R10</span>
                                <span className={`text-xs font-mono font-semibold ${
                                    dimmed ? 'text-gray-600' :
                                    recent10WinRate >= 60 ? 'text-green-400' :
                                    recent10WinRate >= 40 ? 'text-yellow-400' : 'text-red-400'
                                }`}>
                                    {recent10WinRate.toFixed(0)}%
                                </span>
                            </div>
                        </div>
                        {/* PnL Stats: Max / Avg / Min */}
                        <div className="flex items-center gap-2 text-[10px] font-mono">
                            <div className="flex items-center gap-0.5">
                                <span className={dim}>Max</span>
                                <span className={dimmed ? 'text-gray-700' : 'text-green-400 font-semibold'}>
                                    {formatPnl(maxPnl)}
                                </span>
                            </div>
                            <span className={dim}>/</span>
                            <div className="flex items-center gap-0.5">
                                <span className={dim}>Avg</span>
                                <span className={dimmed ? 'text-gray-700' : 'text-white font-semibold'}>
                                    {formatPnl(avgPnl)}
                                </span>
                            </div>
                            <span className={dim}>/</span>
                            <div className="flex items-center gap-0.5">
                                <span className={dim}>Min</span>
                                <span className={dimmed ? 'text-gray-700' : 'text-red-400 font-semibold'}>
                                    {formatPnl(minPnl)}
                                </span>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

/* ───── Pipeline Badge ───── */
const PipelineBadge = ({ active, label, icon: Icon, color = "green", dimmed = false }) => {
    if (dimmed) {
        return (
            <div className="flex items-center gap-1 px-2 py-1 rounded border text-[10px] font-bold bg-gray-800/50 border-gray-700 text-gray-600 opacity-40">
                <Icon size={10} />
                {label}
            </div>
        );
    }
    return (
        <div className={`flex items-center gap-1 px-2 py-1 rounded border text-[10px] font-bold transition-all ${
            active
                ? `bg-${color}-500/10 border-${color}-500/40 text-${color}-400`
                : 'bg-gray-800/50 border-gray-700 text-gray-600 opacity-50'
        }`}>
            <Icon size={10} className={active ? 'animate-pulse' : ''} />
            {label}
        </div>
    );
};

/* ───── Time Momentum Card Body ───── */
const TimeMomentumCard = ({ state, config, dimmed = false, tradeStats = {} }) => {
    const startTime = config?.start_time || state.start_time || '09:00';
    const stopTime = config?.stop_time || state.stop_time || '15:00';
    const direction = config?.direction || state.direction || 'fall';
    const targetPercent = config?.target_percent || state.target_percent || 0.2;
    const changePercent = state.change_percent || 0;
    const refPrice = state.reference_price || 0;
    const hasRef = refPrice > 0;
    const isDelayPassed = state.is_delay_passed || false;
    const hasBought = state.has_bought || false;
    const checkedToday = state.checked_today || false;

    const dim = dimmed ? 'text-gray-700' : 'text-gray-500';
    const dimBorder = dimmed ? 'border-white/[0.02]' : 'border-white/[0.05]';

    const targetVal = direction === 'fall' ? -targetPercent : targetPercent;
    const progress = Math.min(100, Math.max(0, Math.abs(changePercent / (targetVal || 0.01)) * 100));

    // Accumulated stats (combined paper + real for TimeMomentum)
    const paperStats = tradeStats?.paper || {};
    const realStats = tradeStats?.real || {};
    const totalCycles = (paperStats.cycles || 0) + (realStats.cycles || 0);
    const totalPnl = (paperStats.realized_pnl || 0) + (realStats.realized_pnl || 0);
    // Weighted average for win rates, max/min across both
    const paperCycles = paperStats.cycles || 0;
    const realCycles = realStats.cycles || 0;
    const totalWinRate = totalCycles > 0
        ? ((paperStats.win_rate || 0) * paperCycles + (realStats.win_rate || 0) * realCycles) / totalCycles
        : 0;
    const totalRecent10WinRate = totalCycles > 0
        ? ((paperStats.recent_10_win_rate || 0) * paperCycles + (realStats.recent_10_win_rate || 0) * realCycles) / totalCycles
        : 0;
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
            {/* Row 1: Time Window + Direction + Target */}
            <div className={`flex items-center justify-between py-2 border-b ${dimBorder}`}>
                <div className="flex items-center gap-4">
                    <div className="flex items-center gap-1.5">
                        <Timer size={12} className={dimmed ? 'text-gray-700' : 'text-indigo-400'} />
                        <span className={`text-xs font-mono ${dimmed ? 'text-gray-600' : 'text-white'}`}>
                            {startTime} ~ {stopTime}
                        </span>
                    </div>
                    <div className={`flex items-center gap-1 text-xs font-bold ${
                        dimmed ? 'text-gray-700' : direction === 'rise' ? 'text-red-400' : 'text-blue-400'
                    }`}>
                        {direction === 'rise' ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
                        {direction === 'rise' ? 'Rise' : 'Fall'}
                    </div>
                    <span className={`text-xs font-mono ${dimmed ? 'text-gray-700' : 'text-green-400'}`}>
                        Target: {targetPercent}%
                    </span>
                </div>
                {refPrice > 0 && (
                    <span className={`text-xs font-mono ${dim}`}>
                        Ref: {refPrice.toLocaleString()}
                    </span>
                )}
            </div>

            {/* Row 2: Momentum Progress */}
            <div className={`py-2 border-b ${dimBorder}`}>
                <div className="flex items-center justify-between text-[10px] text-gray-500 mb-1">
                    <span>Momentum Progress</span>
                    <span>{(changePercent * 100).toFixed(2)}% / {(targetVal * 100).toFixed(2)}%</span>
                </div>
                <div className={`w-full rounded-full h-1.5 ${dimmed ? 'bg-gray-900' : 'bg-gray-800'}`}>
                    <div
                        className={`h-1.5 rounded-full transition-all duration-500 ${
                            progress >= 100
                                ? 'bg-green-500 shadow-[0_0_10px_rgba(34,197,94,0.4)]'
                                : (dimmed ? 'bg-blue-800' : 'bg-blue-500')
                        }`}
                        style={{ width: `${progress}%` }}
                    />
                </div>
            </div>

            {/* Row 3: Pipeline Badges */}
            <div className={`flex items-center gap-2 py-2 ${totalCycles > 0 ? `border-b ${dimBorder}` : ''}`}>
                <span className="text-[10px] text-gray-600 font-bold uppercase tracking-wider mr-1">Pipeline</span>
                <PipelineBadge active={hasRef} label="Reference Set" icon={Target} color="blue" dimmed={dimmed} />
                <PipelineBadge active={isDelayPassed} label="Delay Passed" icon={Clock} color="blue" dimmed={dimmed} />
                <PipelineBadge active={checkedToday} label="Check Triggered" icon={Zap} color="yellow" dimmed={dimmed} />
                <PipelineBadge active={hasBought} label="Position Active" icon={ShieldCheck} color="green" dimmed={dimmed} />
            </div>

            {/* Row 4: Accumulated Stats Summary (only if has history) */}
            {totalCycles > 0 && (
                <div className={`flex items-center justify-between py-2 border-b ${dimBorder}`}>
                    <span className={`text-xs ${dim}`}>
                        Total {totalCycles} {totalCycles === 1 ? 'Cycle' : 'Cycles'}
                    </span>
                    <span className={`text-xs font-mono ${pnlColor(totalPnl)}`}>
                        {formatPnl(totalPnl)}
                    </span>
                </div>
            )}

            {/* Row 5: Detailed Stats (only if has cycles) */}
            {totalCycles > 0 && (
                <div className="py-2">
                    <div className="flex items-center justify-between gap-4">
                        {/* Win Rates */}
                        <div className="flex items-center gap-3">
                            <div className="flex items-center gap-1">
                                <span className={`text-[10px] ${dim}`}>Win</span>
                                <span className={`text-xs font-mono font-semibold ${
                                    dimmed ? 'text-gray-600' :
                                    totalWinRate >= 60 ? 'text-green-400' :
                                    totalWinRate >= 40 ? 'text-yellow-400' : 'text-red-400'
                                }`}>
                                    {totalWinRate.toFixed(0)}%
                                </span>
                            </div>
                            <div className="flex items-center gap-1">
                                <span className={`text-[10px] ${dim}`}>R10</span>
                                <span className={`text-xs font-mono font-semibold ${
                                    dimmed ? 'text-gray-600' :
                                    totalRecent10WinRate >= 60 ? 'text-green-400' :
                                    totalRecent10WinRate >= 40 ? 'text-yellow-400' : 'text-red-400'
                                }`}>
                                    {totalRecent10WinRate.toFixed(0)}%
                                </span>
                            </div>
                        </div>
                        {/* PnL Stats: Max / Avg / Min */}
                        <div className="flex items-center gap-2 text-[10px] font-mono">
                            <div className="flex items-center gap-0.5">
                                <span className={dim}>Max</span>
                                <span className={dimmed ? 'text-gray-700' : 'text-green-400 font-semibold'}>
                                    {formatPnl(maxPnl)}
                                </span>
                            </div>
                            <span className={dim}>/</span>
                            <div className="flex items-center gap-0.5">
                                <span className={dim}>Avg</span>
                                <span className={dimmed ? 'text-gray-700' : 'text-white font-semibold'}>
                                    {formatPnl(avgPnl)}
                                </span>
                            </div>
                            <span className={dim}>/</span>
                            <div className="flex items-center gap-0.5">
                                <span className={dim}>Min</span>
                                <span className={dimmed ? 'text-gray-700' : 'text-red-400 font-semibold'}>
                                    {formatPnl(minPnl)}
                                </span>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default UnifiedSessionCards;
