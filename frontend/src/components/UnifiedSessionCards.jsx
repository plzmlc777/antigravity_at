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
        let totalR10Wins = 0;
        let totalR10Total = 0;
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
                totalWins += s.wins ?? Math.round((s.win_rate || 0) * s.cycles / 100);
                totalR10Wins += s.recent_10_wins || 0;
                totalR10Total += s.recent_10_total || 0;
                // Reconstruct cycle PnLs for max/min/avg
                if (s.max_pnl) allCyclePnls.push(s.max_pnl);
                if (s.min_pnl) allCyclePnls.push(s.min_pnl);
            });
        });

        const winRate = totalCycles > 0 ? (totalWins / totalCycles) * 100 : 0;
        const maxPnl = allCyclePnls.length > 0 ? Math.max(...allCyclePnls) : 0;
        const minPnl = allCyclePnls.length > 0 ? Math.min(...allCyclePnls) : 0;
        const avgPnl = totalCycles > 0 ? totalPnl / totalCycles : 0;

        return { totalCycles, totalPnl, totalWins, winRate, maxPnl, minPnl, avgPnl };
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
                                    {totalStats.totalCycles > 0 && (
                                        <span className="text-[9px] text-gray-400 font-normal ml-1">({totalStats.totalWins}/{totalStats.totalCycles})</span>
                                    )}
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
                    const symbolName = cfg.symbol_name || savedSymbols?.find(s => s.code === cfg.symbol)?.name || cfg.symbol;
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
                                <div className="flex items-center gap-3">
                                    {hasData && (
                                        <>
                                            <span className={`text-base font-mono font-semibold ${isRunning ? 'text-white' : 'text-gray-500'}`}>
                                                {price.toLocaleString()}
                                            </span>
                                            {(() => {
                                                const profitPct = (activeState.profit_percent || 0) * 100;
                                                const hasPosition = (activeState.current_level || 0) > 0;
                                                if (!hasPosition) return null;
                                                return (
                                                    <span className={`text-sm font-mono font-bold ${
                                                        !isRunning ? 'text-gray-600'
                                                        : profitPct >= 0 ? 'text-red-400' : 'text-blue-400'
                                                    }`}>
                                                        {profitPct >= 0 ? '+' : ''}{profitPct.toFixed(2)}%
                                                    </span>
                                                );
                                            })()}
                                        </>
                                    )}
                                    <div className={`w-2 h-2 rounded-full ${isRunning ? 'bg-green-400 animate-pulse' : 'bg-gray-600'}`} />
                                </div>
                            </div>

                            {/* Compact Summary + Full Strategy Detail for ALL ranks */}
                            {(hasData || hasAccumulatedData) && (
                                <>
                                    <CompactSummary
                                        state={activeState}
                                        tradeStats={tradeStats}
                                        dimmed={!isRunning}
                                    />
                                    <GenericStrategyCard
                                        state={activeState}
                                        config={cfg}
                                        price={price}
                                        isPaper={isPaper}
                                        tradeStats={tradeStats}
                                        dimmed={!isRunning}
                                    />
                                </>
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

/* ───── Trigger Info (compact entry condition display) ───── */
const TriggerInfo = ({ state, dimmed = false }) => {
    const dim = dimmed ? 'text-gray-700' : 'text-gray-500';
    const items = [];

    // RSI Martingale: current_rsi + trigger_level + armed state
    if (state.current_rsi !== undefined && state.current_rsi !== null) {
        const rsi = state.current_rsi;
        const rsiColor = dimmed ? 'text-gray-700'
            : rsi <= 30 ? 'text-blue-400' : rsi >= 70 ? 'text-red-400' : 'text-yellow-400';
        items.push(
            <span key="rsi" className={`font-semibold ${rsiColor}`}>
                RSI {rsi.toFixed(1)}
            </span>
        );
        if (state.trigger_level) {
            const armed = state.long_trigger_armed;
            items.push(
                <span key="rsi-trig" className={dim}>
                    L:{state.trigger_level}{armed ? <span className={dimmed ? '' : 'text-green-500'}> &#x2713;</span> : ''}
                </span>
            );
        }
        if (state.short_trigger_level) {
            const armed = state.short_trigger_armed;
            items.push(
                <span key="rsi-short" className={dim}>
                    S:{state.short_trigger_level}{armed ? <span className={dimmed ? '' : 'text-green-500'}> &#x2713;</span> : ''}
                </span>
            );
        }
    }

    // US Market Follow: us_index + change + threshold
    if (state.us_index !== undefined) {
        const change = state.us_change_today;
        const threshold = state.us_change_threshold;
        const met = state.trigger_met;
        const changeColor = dimmed ? 'text-gray-700'
            : change == null ? 'text-gray-500'
            : change >= 0 ? 'text-red-400' : 'text-blue-400';
        items.push(
            <span key="us-idx" className={dim}>{state.us_index}</span>
        );
        items.push(
            <span key="us-chg" className={changeColor}>
                {change != null ? `${change >= 0 ? '+' : ''}${change.toFixed(2)}%` : 'waiting'}
            </span>
        );
        if (threshold) {
            items.push(
                <span key="us-th" className={dim}>
                    th:{threshold}%{met ? <span className={dimmed ? '' : 'text-green-500'}> &#x2713;</span> : ''}
                </span>
            );
        }
    }

    // Chart Pattern: entry/exit pattern labels
    if (state.entry_pattern_label) {
        items.push(
            <span key="cp-entry" className={dimmed ? 'text-gray-700' : 'text-cyan-400'}>
                {state.entry_pattern_label}
            </span>
        );
    }
    if (state.exit_pattern_label) {
        items.push(
            <span key="cp-exit" className={dimmed ? 'text-gray-700' : 'text-orange-400'}>
                Exit:{state.exit_pattern_label}
            </span>
        );
    }

    // Dip Martingale: target_dip + dip_percent
    if (state.target_dip !== undefined && state.dip_percent !== undefined) {
        const dipColor = dimmed ? 'text-gray-700'
            : Math.abs(state.dip_percent) >= Math.abs(state.target_dip) ? 'text-blue-400' : 'text-gray-400';
        items.push(
            <span key="dip" className={dipColor}>
                Dip {state.dip_percent?.toFixed(1)}%/{state.target_dip}%
            </span>
        );
    }

    if (items.length === 0) return null;

    return (
        <div className={`px-4 pb-1 flex items-center gap-2 flex-wrap ${dimmed ? 'opacity-30' : ''}`}>
            <span className={`text-[9px] ${dim}`}>Trigger:</span>
            {items.map((item, i) => (
                <span key={i} className="text-[10px] font-mono">{item}</span>
            ))}
        </div>
    );
};

/* ───── Position Progress Bar ───── */
const PositionProgressBar = ({ state, dimmed = false }) => {
    const currentLevel = state.current_level || 0;
    const avgPrice = state.average_price || 0;
    const curPrice = state.current_price || 0;
    const targetPrice = state.target_price || 0;
    const stopLossPrice = state.stop_loss_price || 0;
    const trailingActive = state.trailing_active || false;
    const peakPrice = state.peak_price || 0;
    const trailingExitPrice = state.trailing_exit_price || 0;
    const isShort = state.position_side === 'short';

    if (!avgPrice || currentLevel <= 0 || !curPrice) return null;

    // Determine bar range endpoints
    const leftPrice = stopLossPrice > 0 ? stopLossPrice : avgPrice * (isShort ? 1.1 : 0.9);
    let rightPrice = targetPrice > 0 ? targetPrice : avgPrice * (isShort ? 0.9 : 1.1);

    // Extend right boundary when trailing is active to include peak
    if (trailingActive && peakPrice > 0) {
        if (isShort) {
            rightPrice = Math.min(rightPrice, peakPrice * 0.995);
        } else {
            rightPrice = Math.max(rightPrice, peakPrice * 1.005);
        }
    }

    // For SHORT: leftPrice > rightPrice (higher price = loss), so normalize
    const rangeMin = Math.min(leftPrice, rightPrice);
    const rangeMax = Math.max(leftPrice, rightPrice);
    const range = rangeMax - rangeMin || 1;

    // Calculate positions as percentages (0-100)
    const clampPct = (price) => Math.max(0, Math.min(100, ((price - rangeMin) / range) * 100));

    const avgPct = clampPct(avgPrice);
    const curPct = clampPct(curPrice);
    const peakPct = trailingActive && peakPrice > 0 ? clampPct(peakPrice) : null;
    const exitPct = trailingActive && trailingExitPrice > 0 ? clampPct(trailingExitPrice) : null;
    const targetPct = targetPrice > 0 ? clampPct(targetPrice) : null;

    // Determine if current price is in profit zone
    const inProfit = isShort ? curPrice < avgPrice : curPrice > avgPrice;

    // For SHORT: loss is right of avg, profit is left. For LONG: loss is left, profit is right.
    // The fill goes from avg to current price position
    const fillLeft = Math.min(avgPct, curPct);
    const fillWidth = Math.abs(curPct - avgPct);

    const opacity = dimmed ? 'opacity-30' : '';

    return (
        <div className={`px-4 pb-2 ${opacity}`}>
            {/* Labels */}
            <div className="flex justify-between items-center mb-1">
                <span className="text-[9px] font-mono text-red-400">
                    SL {Math.round(leftPrice).toLocaleString()}
                </span>
                {trailingActive && trailingExitPrice > 0 && (
                    <span className="text-[9px] font-mono text-yellow-400">
                        Exit {Math.round(trailingExitPrice).toLocaleString()}
                    </span>
                )}
                <span className="text-[9px] font-mono text-green-400">
                    TP {Math.round(rightPrice).toLocaleString()}
                </span>
            </div>
            {/* Bar */}
            <div className="relative w-full h-2.5 rounded-full bg-gray-700/60 border border-gray-600/40">
                {/* Fill: avg → current */}
                <div
                    className={`absolute top-0 h-full rounded-full ${inProfit ? 'bg-green-500/80' : 'bg-red-500/80'}`}
                    style={{ left: `${fillLeft}%`, width: `${Math.max(fillWidth, 0.5)}%` }}
                />
                {/* Avg price marker (thin line) */}
                <div
                    className="absolute top-0 h-full w-0.5 bg-white/60"
                    style={{ left: `${avgPct}%` }}
                />
                {/* Target price marker */}
                {targetPct !== null && (
                    <div
                        className="absolute top-0 h-full w-0.5 bg-green-400/50"
                        style={{ left: `${targetPct}%` }}
                    />
                )}
                {/* Peak price marker (when trailing active) */}
                {peakPct !== null && (
                    <div
                        className="absolute -top-0.5 w-1.5 h-3.5 rounded-sm bg-green-400/70"
                        style={{ left: `${peakPct}%`, transform: 'translateX(-50%)' }}
                    />
                )}
                {/* Trailing exit marker */}
                {exitPct !== null && (
                    <div
                        className="absolute top-0 h-full w-1 bg-yellow-400/70"
                        style={{ left: `${exitPct}%` }}
                    />
                )}
                {/* Current price dot */}
                <div
                    className={`absolute -top-1 w-2.5 h-[18px] rounded-full border-2 ${
                        inProfit ? 'bg-green-400 border-green-300' : 'bg-red-400 border-red-300'
                    } shadow-md shadow-black/50`}
                    style={{ left: `${curPct}%`, transform: 'translateX(-50%)' }}
                />
            </div>
        </div>
    );
};

/* ───── Compact Summary (shown for ALL ranks) ───── */
const CompactSummary = ({ state, tradeStats = {}, dimmed = false }) => {
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

    // Accumulated stats
    const paperStats = tradeStats?.paper || {};
    const realStats = tradeStats?.real || {};
    const totalCycles = (paperStats.cycles || 0) + (realStats.cycles || 0);
    const totalPnl = (paperStats.realized_pnl || 0) + (realStats.realized_pnl || 0);
    const totalPnlPct = (paperStats.realized_pnl_pct || 0) + (realStats.realized_pnl_pct || 0);

    const formatPnl = (v) => {
        if (!v) return '0';
        const abs = Math.abs(v);
        const str = abs >= 1000000 ? `${(abs / 1000000).toFixed(1)}M`
            : abs >= 1000 ? `${(abs / 1000).toFixed(0)}K`
            : abs.toLocaleString();
        return (v >= 0 ? '+' : '-') + str;
    };
    const pnlColor = (v) => dimmed ? 'text-gray-700' : (v >= 0 ? 'text-green-400' : 'text-red-400');

    const hasLevelInfo = maxLevels > 0;
    const hasSummary = hasLevelInfo || totalQty > 0 || isTrailing || isHodl || pendingEntry || pendingExit || totalCycles > 0;
    if (!hasSummary) return null;

    return (
        <div>
            <div className="px-4 py-2 flex items-center justify-between flex-wrap gap-y-1">
                {/* Left: Level + Badges + Qty + Avg */}
                <div className="flex items-center gap-2 flex-wrap">
                    {hasLevelInfo && (
                        <div className="flex items-center gap-1.5">
                            <span className={`text-xs font-bold ${dimmed ? 'text-gray-600' : 'text-indigo-400'}`}>
                                L{currentLevel}/{maxLevels}
                            </span>
                            {maxLevels <= 10 && (
                                <div className="flex gap-0.5">
                                    {Array.from({ length: maxLevels }, (_, i) => (
                                        <div key={i} className={`h-1.5 w-1.5 rounded-full ${
                                            i < currentLevel
                                                ? (dimmed ? 'bg-indigo-700' : 'bg-indigo-400')
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
                        <span className={`text-[8px] font-bold px-1 py-0.5 rounded ${dimmed ? 'bg-gray-800 text-gray-600' : 'bg-green-500/20 text-green-400'}`}>T</span>
                    )}
                    {isHodl && (
                        <span className={`text-[8px] font-bold px-1 py-0.5 rounded ${dimmed ? 'bg-gray-800 text-gray-600' : 'bg-red-500/20 text-red-400'}`}>H</span>
                    )}
                    {totalQty > 0 && (
                        <span className={`text-[11px] font-mono ${dim}`}>{totalQty}qty</span>
                    )}
                    {avgPrice > 0 && (
                        <span className={`text-[11px] font-mono ${dim}`}>Avg:{Math.round(avgPrice).toLocaleString()}</span>
                    )}
                    {avgPrice > 0 && (
                        <span className={`text-[11px] font-mono font-semibold ${dimmed ? 'text-gray-700' : profitPct >= 0 ? 'text-red-400' : 'text-blue-400'}`}>
                            {profitPct >= 0 ? '+' : ''}{profitPct.toFixed(2)}%
                        </span>
                    )}
                </div>
                {/* Right: Accumulated Stats */}
                <div className="flex items-center gap-2">
                    {totalCycles > 0 && (
                        <>
                            <span className={`text-[10px] font-bold ${dimmed ? 'text-gray-600' : 'text-indigo-400'}`}>
                                #{totalCycles + 1}
                            </span>
                            <span className={`text-[10px] ${dim}`}>
                                {totalCycles}C
                            </span>
                            <span className={`text-[11px] font-mono ${pnlColor(totalPnl)}`}>
                                {formatPnl(totalPnl)}
                                {totalPnlPct !== 0 && <span className="text-[9px] opacity-70"> ({totalPnlPct >= 0 ? '+' : ''}{totalPnlPct.toFixed(1)}%)</span>}
                            </span>
                        </>
                    )}
                </div>
            </div>
            <TriggerInfo state={state} dimmed={dimmed} />
            <PositionProgressBar state={state} dimmed={dimmed} />
        </div>
    );
};

/* ───── Generic Strategy Card Body (full detail, only for selected rank) ───── */
const HIDDEN_KEYS = new Set([
    'symbol', 'strategy_id', 'is_paper', 'status', 'current_price',
    'reference_price', 'entries', 'pending_entry', 'pending_exit',
    'current_level', 'max_buy_count', 'total_quantity', 'average_price',
    'profit_percent', 'trailing_active', 'is_hodl',
    'max_loss_pct', 'trailing_stop_pct', 'stop_loss_price', 'trailing_exit_price',
    'current_rsi', 'trigger_level', 'long_trigger_armed', 'short_trigger_armed',
    'short_trigger_level', 'reset_level', 'short_reset_level',
    'us_index', 'us_change_today', 'us_change_threshold', 'trigger_met', 'checked_today',
    'entry_pattern_label', 'exit_pattern_label',
    'target_dip', 'dip_percent',
]);

const KEY_LABELS = {
    target_dip: 'Target Dip', dip_percent: 'Dip%', current_rsi: 'RSI',
    trigger_level: 'RSI Trigger', trigger_armed: 'Trigger Armed',
    target_profit_pct: 'Target Profit', target_price: 'Target Price', direction: 'Direction',
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
        // _pct suffix: already in percentage units (e.g., 20 = 20%)
        if (key.endsWith('_pct')) return `${val}%`;
        if (key.includes('percent') || key.includes('pct')) return `${(val * 100).toFixed(2)}%`;
        if (key.includes('price') || val > 1000) return Math.round(val).toLocaleString();
        if (Number.isInteger(val)) return val.toString();
        return val.toFixed(2);
    }
    return String(val);
};

const GenericStrategyCard = ({ state, config = {}, price = 0, isPaper = true, tradeStats = {}, dimmed = false }) => {
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
    // Use raw wins count if available, otherwise compute from win_rate
    const paperWins = paperStats.wins ?? Math.round((paperStats.win_rate || 0) * paperCycles / 100);
    const realWins = realStats.wins ?? Math.round((realStats.win_rate || 0) * realCycles / 100);
    const totalWins = paperWins + realWins;
    const winRate = totalCycles > 0 ? (totalWins / totalCycles) * 100 : 0;
    const recent10Wins = (paperStats.recent_10_wins ?? 0) + (realStats.recent_10_wins ?? 0);
    const recent10Total = (paperStats.recent_10_total ?? 0) + (realStats.recent_10_total ?? 0);
    const recent10 = recent10Total > 0 ? (recent10Wins / recent10Total) * 100 : 0;
    // Fallback R10 from win_rate if raw counts not available
    const recent10Fallback = recent10Total === 0 && totalCycles > 0;
    const recent10Display = recent10Fallback
        ? ((paperStats.recent_10_win_rate || 0) * paperCycles + (realStats.recent_10_win_rate || 0) * realCycles) / totalCycles
        : recent10;
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

    const hasDisplayEntries = displayEntries.length > 0;
    const hasStats = totalCycles > 0;

    if (!hasDisplayEntries && !hasStats) return null;

    return (
        <div className={`px-4 pb-3 border-t ${dimBorder}`}>
            {/* Row 1: Dynamic state key-value grid */}
            {hasDisplayEntries && (
                <div className={`grid grid-cols-2 gap-x-4 gap-y-1 py-2 ${hasStats ? `border-b ${dimBorder}` : ''}`}>
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

            {/* Row 2: Detailed Stats */}
            {hasStats && (
                <div className="py-2">
                    <div className="flex items-center justify-between gap-4">
                        <div className="flex items-center gap-3">
                            <div className="flex items-center gap-1">
                                <span className={`text-[10px] ${dim}`}>Win</span>
                                <span className={`text-xs font-mono font-semibold ${
                                    dimmed ? 'text-gray-600' : winRate >= 60 ? 'text-green-400' : winRate >= 40 ? 'text-yellow-400' : 'text-red-400'
                                }`}>{winRate.toFixed(0)}%</span>
                                {totalCycles > 0 && (
                                    <span className={`text-[9px] font-mono ${dim}`}>({totalWins}/{totalCycles})</span>
                                )}
                            </div>
                            <div className="flex items-center gap-1">
                                <span className={`text-[10px] ${dim}`}>R10</span>
                                <span className={`text-xs font-mono font-semibold ${
                                    dimmed ? 'text-gray-600' : recent10Display >= 60 ? 'text-green-400' : recent10Display >= 40 ? 'text-yellow-400' : 'text-red-400'
                                }`}>{recent10Display.toFixed(0)}%</span>
                                {recent10Total > 0 && (
                                    <span className={`text-[9px] font-mono ${dim}`}>({recent10Wins}/{recent10Total})</span>
                                )}
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
