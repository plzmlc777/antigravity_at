import React, { useState, useEffect, useRef, useMemo } from 'react';
import { Play, Square, Activity, AlertTriangle, Terminal, List, X, Pause, Shield, ShieldOff, ShieldAlert, Radio, BarChart3, History, ChevronLeft, Clock, Download, Wifi, WifiOff, Check, RotateCcw, Trash2, Settings } from 'lucide-react';
// import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { startLiveBot, stopLiveBot, getLiveStatus, getOHLCV, getTradeHistoryList, fetchMarketData, toggleLiveOrders, toggleLiveMode, liquidateLiveBot, getBalance, getBalanceForAccount, getAccumulatedStats, checkLivePosition, resumeSession, deleteSession, updateSessionSettings, listAnalysisSchedules, createAnalysisSchedule, updateAnalysisSchedule, deleteAnalysisSchedule, runAnalysisAllSessions, listAllAnalysisReports, getAnalysisReportDetail } from '../api/client';
import { Wallet, TrendingUp, DollarSign, RefreshCw } from 'lucide-react';
import ConfirmModal from './ConfirmModal';
import AlertModal from './AlertModal';
import VisualBacktestChart from './VisualBacktestChart';
import ActiveStrategiesPanel from './ActiveStrategiesPanel';
import UnifiedSessionCards from './UnifiedSessionCards';
import { STATUS_CONFIG, DeleteConfirmModal } from './SessionSwitcher';
import { useLiveTrading } from '../context/LiveTradingContext';
import { DEFAULTS } from '../constants/live';

const LiveStrategyPanel = ({ strategyConfig, strategyName, mode = 'TRADE', configList = [], savedSymbols = [], currentRankIndex, onRankChange, executionMode = 'exclusive', onExecutionModeChange, parameterSchema, onStatusChange, onCapitalChange, activeSessionGroup, onSessionAction }) => {
    // State
    const [status, setStatus] = useState('IDLE'); // IDLE, RUNNING, STOPPED, ERROR
    const [sessionId, setSessionId] = useState(null);
    const [liveData, setLiveData] = useState(null);
    const [logs, setLogs] = useState([]);
    const [error, setError] = useState(null);
    const [availableBalance, setAvailableBalance] = useState(null);
    // Initialize from strategyConfig, fallback to 10M default
    const [inputCapital, setInputCapital] = useState(strategyConfig?.initial_capital || 10000000);

    const [tickData, setTickData] = useState([]); // Running list of recent ticks for UI (optional)
    const [isStopModalOpen, setIsStopModalOpen] = useState(false);
    const [isLiquidateModalOpen, setIsLiquidateModalOpen] = useState(false);
    const [isPositionWarningOpen, setIsPositionWarningOpen] = useState(false);
    const [positionWarningMessage, setPositionWarningMessage] = useState('');

    // Session Actions State (Option B: actions in panel, not on cards)
    const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
    const [isResuming, setIsResuming] = useState(false);
    const [isDeleting, setIsDeleting] = useState(false);

    // Custom Alert Modal State (replaces system alert())
    const [alertModal, setAlertModal] = useState({ isOpen: false, title: '', message: '', type: 'info' });
    const showAlert = (message, type = 'error', title = '') => {
        setAlertModal({ isOpen: true, title, message, type });
    };

    // Parallel mode: track multiple sessions {rankIndex: sessionId}
    const [parallelSessions, setParallelSessions] = useState({});

    // Parallel mode: per-rank capital allocation weights (%) {rankIndex: percent}
    const [rankWeights, setRankWeights] = useState({});

    // Real-Time Candles State
    const [rawCandles, setRawCandles] = useState([]); // Always 1m candles (source of truth)
    const [realTimeCandles, setRealTimeCandles] = useState([]); // Aggregated to selectedInterval
    const [selectedInterval, setSelectedInterval] = useState(() => localStorage.getItem('live_tick_interval') || '1m');
    const handleIntervalChange = (val) => { localStorage.setItem('live_tick_interval', val); setSelectedInterval(val); };

    // WebSocket Connection State
    const [wsConnected, setWsConnected] = useState(false);

    // Transaction History View State (2-step architecture)
    const [showHistoryView, setShowHistoryView] = useState(false);
    const [historyData, setHistoryData] = useState(null); // { cycles, open_cycles, total_cycles, ... }
    const [isHistoryLoading, setIsHistoryLoading] = useState(false);
    const [historyMode, setHistoryMode] = useState('paper'); // 'paper' | 'real' | 'all'
    // Step 2: Selected cycle chart
    const [selectedCycle, setSelectedCycle] = useState(null);
    const [cycleChartData, setCycleChartData] = useState(null);
    const [isCycleChartLoading, setIsCycleChartLoading] = useState(false);

    // Accumulated stats for symbols (fetched from DB, persists even when session stops)
    const [accumulatedStats, setAccumulatedStats] = useState({}); // { symbol: { paper: {...}, real: {...} } }

    // AI Analysis (Periodic) State
    const [showAiAnalysisPanel, setShowAiAnalysisPanel] = useState(false);
    const [analysisSchedule, setAnalysisSchedule] = useState(null); // Current schedule
    const [analysisReports, setAnalysisReports] = useState([]); // Report list
    const [selectedReport, setSelectedReport] = useState(null); // Report detail
    const [isAnalysisRunning, setIsAnalysisRunning] = useState(false);
    const [analysisProgress, setAnalysisProgress] = useState([]); // [{symbol, status, grade}]
    const [scheduleForm, setScheduleForm] = useState({
        schedule_type: 'daily',
        schedule_time: '15:40',
        schedule_day: 1,
        enabled: true,
    });

    // Multi-Account State (Phase 5) - Use centralized accounts from context
    const { accounts, getActiveAccount } = useLiveTrading();
    const [selectedAccountId, setSelectedAccountId] = useState(null); // Selected account for session
    const [isPaperMode, setIsPaperMode] = useState(DEFAULTS.IS_PAPER_MODE); // Paper mode by default for safety
    const [modeSwitchConfirm, setModeSwitchConfirm] = useState({ isOpen: false, toReal: false, isRunningSession: false }); // Mode switch confirmation

    // Apply Changes State (track original session values for dirty detection)
    const [originalSessionSettings, setOriginalSessionSettings] = useState(null); // { capital, isPaper, accountId }
    const [isApplying, setIsApplying] = useState(false);
    const [applyStatus, setApplyStatus] = useState(null); // 'success' | 'error' | null

    // Session Account Balance State (for displaying connected account's balance)
    const [sessionBalance, setSessionBalance] = useState(null); // { cash, holdings, totalAssets, totalInvested }
    const [isBalanceLoading, setIsBalanceLoading] = useState(false);

    // Notify parent of status changes (for strategy change lock)
    useEffect(() => {
        if (onStatusChange) {
            onStatusChange(status);
        }
    }, [status, onStatusChange]);

    // Sync inputCapital when strategyConfig.initial_capital changes (only when no session is selected)
    // When a session is selected, the session's capital takes precedence
    useEffect(() => {
        // Only sync from strategyConfig if no active session is selected
        if (!activeSessionGroup && strategyConfig?.initial_capital !== undefined && strategyConfig.initial_capital !== null) {
            setInputCapital(strategyConfig.initial_capital);
        }
    }, [strategyConfig?.initial_capital, activeSessionGroup]);

    // Fetch accumulated stats on mount and when configList/strategyName changes
    // This aggregates ALL historical cycles across all sessions with matching (symbol, strategy)
    useEffect(() => {
        const fetchAccumulatedStats = async () => {
            if (!configList || configList.length === 0) return;
            const symbols = configList.map(c => c.symbol).filter(Boolean);
            if (symbols.length === 0) return;
            try {
                // Pass strategyName to filter by strategy (aggregates all historical sessions)
                const stats = await getAccumulatedStats(symbols, strategyName);
                setAccumulatedStats(stats || {});
            } catch (err) {
                console.error('Failed to fetch accumulated stats:', err);
            }
        };
        fetchAccumulatedStats();
    }, [configList, strategyName]);

    // Set default account selection when accounts are loaded from context
    useEffect(() => {
        if (accounts.length > 0 && !selectedAccountId) {
            const activeAccount = getActiveAccount();
            if (activeAccount) {
                setSelectedAccountId(activeAccount.id);
            }
        }
    }, [accounts, selectedAccountId, getActiveAccount]);

    // Sync panel state when activeSessionGroup changes (Phase 5: Session Selection)
    // Note: Only depends on activeSessionGroup, not strategyConfig - user's capital edits should persist
    useEffect(() => {
        const selectedSession = activeSessionGroup?.sessions?.[0];

        // Reset to default values when no session is selected
        if (!selectedSession) {
            setSessionId(null);
            // Don't reset inputCapital here - let the other useEffect handle it
            // or keep user's current input
            setStatus('IDLE');
            setError(null);
            setLiveData(null);
            setLogs([]);
            // Keep account selection to the active account (don't reset selectedAccountId)
            // isPaperMode keeps its current state for new session creation
            // Reset apply state
            setOriginalSessionSettings(null);
            setApplyStatus(null);
            console.log('[LiveStrategyPanel] No session selected - reset to defaults');
            return;
        }

        // Update session ID
        setSessionId(selectedSession.session_id);

        // Update capital from session (only when session changes, not on every render)
        if (selectedSession.initial_capital) {
            setInputCapital(selectedSession.initial_capital);
        }

        // Update account selection
        if (selectedSession.account_id) {
            setSelectedAccountId(selectedSession.account_id);
        }

        // Update paper mode from session
        const sessionIsPaper = selectedSession.is_paper !== false;
        setIsPaperMode(sessionIsPaper);

        // Load rankWeights from session's strategy_config (parallel mode)
        const sessionRankWeights = selectedSession.strategy_config?.rank_weights || {};
        setRankWeights(sessionRankWeights);

        // Save original settings for dirty detection (only for non-running sessions)
        if (selectedSession.status !== 'RUNNING') {
            setOriginalSessionSettings({
                capital: selectedSession.initial_capital || 0,
                isPaper: sessionIsPaper,
                accountId: selectedSession.account_id,
                rankWeights: sessionRankWeights
            });
        } else {
            setOriginalSessionSettings(null);
        }
        setApplyStatus(null);

        // Update status based on session status
        if (selectedSession.status === 'RUNNING') {
            setStatus('RUNNING');
            // Polling will be started by checkLiveStatus
        } else if (selectedSession.status === 'STOPPED') {
            setStatus('STOPPED');
        } else if (selectedSession.status === 'ERROR') {
            setStatus('ERROR');
            if (selectedSession.error_log) {
                setError(selectedSession.error_log);
            }
        } else if (selectedSession.status === 'PAUSED') {
            setStatus('PAUSED');
        } else {
            setStatus('IDLE');
        }

        console.log('[LiveStrategyPanel] Session selected:', selectedSession.session_id, selectedSession.status);
    }, [activeSessionGroup]);

    // Fetch balance for the selected session's account
    useEffect(() => {
        const fetchSessionBalance = async () => {
            const accountId = activeSessionGroup?.sessions?.[0]?.account_id;
            if (!accountId) {
                setSessionBalance(null);
                return;
            }

            setIsBalanceLoading(true);
            try {
                const balanceData = await getBalanceForAccount(accountId);

                // Calculate totals
                const cash = balanceData?.cash?.KRW || 0;
                const holdings = balanceData?.holdings || {};

                let totalInvested = 0;
                Object.values(holdings).forEach(h => {
                    totalInvested += (h.quantity || 0) * (h.currentPrice || h.avgPrice || 0);
                });

                const totalAssets = cash + totalInvested;

                setSessionBalance({
                    cash,
                    holdings,
                    totalAssets,
                    totalInvested,
                    raw: balanceData
                });
            } catch (err) {
                console.error('Failed to fetch session balance:', err);
                setSessionBalance(null);
            } finally {
                setIsBalanceLoading(false);
            }
        };

        fetchSessionBalance();

        // Refresh balance periodically (every 10 seconds when session is active)
        const accountId = activeSessionGroup?.sessions?.[0]?.account_id;
        if (accountId && status === 'RUNNING') {
            const interval = setInterval(fetchSessionBalance, 10000);
            return () => clearInterval(interval);
        }
    }, [activeSessionGroup?.sessions?.[0]?.account_id, status]);

    // Manual refresh balance
    const refreshSessionBalance = async () => {
        const accountId = activeSessionGroup?.sessions?.[0]?.account_id;
        if (!accountId) return;

        setIsBalanceLoading(true);
        try {
            const balanceData = await getBalanceForAccount(accountId);
            const cash = balanceData?.cash?.KRW || 0;
            const holdings = balanceData?.holdings || {};

            let totalInvested = 0;
            Object.values(holdings).forEach(h => {
                totalInvested += (h.quantity || 0) * (h.currentPrice || h.avgPrice || 0);
            });

            setSessionBalance({
                cash,
                holdings,
                totalAssets: cash + totalInvested,
                totalInvested,
                raw: balanceData
            });
        } catch (err) {
            console.error('Failed to refresh balance:', err);
        } finally {
            setIsBalanceLoading(false);
        }
    };

    // Derive selected session info for display (Phase 5)
    const selectedSessionInfo = useMemo(() => {
        const session = activeSessionGroup?.sessions?.[0];
        if (!session) return null;

        // Get symbol name
        const symbolMatch = savedSymbols.find(s => s.code === session.symbol);
        const symbolName = symbolMatch?.name || session.symbol;

        // Get account name
        const account = accounts.find(a => a.id === session.account_id);
        const accountName = account?.account_name || `Account ${session.account_id}`;

        // Get profile name (group name) - prioritize profile_name from session
        const profileName = session.profile_name || activeSessionGroup?.profile_name;

        // Count sessions in group
        const sessionCount = activeSessionGroup?.sessions?.length || 1;

        return {
            sessionId: session.session_id,
            symbol: session.symbol,
            symbolName,
            strategyName: session.strategy_name,
            strategyConfig: session.strategy_config || {},
            initialCapital: session.initial_capital || 0,
            isPaper: session.is_paper,
            status: session.status,
            accountId: session.account_id,
            accountName,
            startedAt: session.started_at,
            stoppedAt: session.stopped_at,
            pnl: session.pnl || 0,
            errorLog: session.error_log,
            profileName,  // Profile/Group name for display
            sessionCount, // Number of sessions in this group
        };
    }, [activeSessionGroup, savedSymbols, accounts]);

    // Check if settings have changed from original (dirty state)
    const hasUnsavedChanges = useMemo(() => {
        if (!originalSessionSettings) return false;
        if (status === 'RUNNING') return false;

        const capitalChanged = parseFloat(inputCapital) !== originalSessionSettings.capital;
        const modeChanged = isPaperMode !== originalSessionSettings.isPaper;
        const accountChanged = selectedAccountId !== originalSessionSettings.accountId;

        // Compare rankWeights (deep comparison)
        const originalWeights = originalSessionSettings.rankWeights || {};
        const rankWeightsChanged = JSON.stringify(rankWeights) !== JSON.stringify(originalWeights);

        return capitalChanged || modeChanged || accountChanged || rankWeightsChanged;
    }, [originalSessionSettings, inputCapital, isPaperMode, selectedAccountId, rankWeights, status]);

    // Handle Apply Settings to backend
    const handleApplySettings = async () => {
        if (!sessionId || !hasUnsavedChanges) return;

        setIsApplying(true);
        setApplyStatus(null);

        try {
            const settings = {};

            // Send all changed values including account_id and rankWeights
            if (parseFloat(inputCapital) !== originalSessionSettings.capital) {
                settings.initial_capital = parseFloat(inputCapital);
            }
            if (isPaperMode !== originalSessionSettings.isPaper) {
                settings.is_paper = isPaperMode;
            }
            if (selectedAccountId !== originalSessionSettings.accountId) {
                settings.account_id = selectedAccountId;
            }

            // Check rankWeights change
            const originalWeights = originalSessionSettings.rankWeights || {};
            if (JSON.stringify(rankWeights) !== JSON.stringify(originalWeights)) {
                settings.rank_weights = rankWeights;
            }

            // If nothing changed, nothing to save
            if (Object.keys(settings).length === 0) {
                setApplyStatus('success');
                setTimeout(() => setApplyStatus(null), 2000);
                return;
            }

            const result = await updateSessionSettings(sessionId, settings);
            console.log('[LiveStrategyPanel] Settings applied:', result);

            // Update original settings to new values
            setOriginalSessionSettings({
                capital: parseFloat(inputCapital),
                isPaper: isPaperMode,
                accountId: selectedAccountId,
                rankWeights: { ...rankWeights }
            });

            setApplyStatus('success');

            // Clear success status after 3 seconds
            setTimeout(() => setApplyStatus(null), 3000);

        } catch (err) {
            console.error('[LiveStrategyPanel] Failed to apply settings:', err);
            setApplyStatus('error');
            showAlert(
                err.response?.data?.detail || 'Failed to save settings',
                'error',
                '설정 저장 실패'
            );
        } finally {
            setIsApplying(false);
        }
    };

    // Handle Discard Changes - reset to original values
    const handleDiscardChanges = () => {
        if (!originalSessionSettings) return;

        setInputCapital(originalSessionSettings.capital);
        setIsPaperMode(originalSessionSettings.isPaper);
        setSelectedAccountId(originalSessionSettings.accountId);
        setRankWeights(originalSessionSettings.rankWeights || {});
        setApplyStatus(null);
    };

    // Overview Chart: Transform historyData cycles → rank-based chart (like IntegratedAnalysis)
    const { overviewChartData, overviewTrades, overviewRankFormatter, overviewPriceScaleOptions, overviewSymbolRanks } = useMemo(() => {
        const empty = { overviewChartData: [], overviewTrades: [], overviewRankFormatter: () => '', overviewPriceScaleOptions: {}, overviewSymbolRanks: null };
        if (!historyData) return empty;

        const allCycles = [...(historyData.open_cycles || []), ...(historyData.cycles || [])];
        if (allCycles.length === 0) return empty;

        // 1. Build symbol → rank mapping (configList order first, then extras from history)
        const symbols = [];
        const symbolSet = new Set();
        (configList || []).forEach(cfg => {
            if (cfg.symbol && !symbolSet.has(cfg.symbol)) {
                symbols.push(cfg.symbol);
                symbolSet.add(cfg.symbol);
            }
        });
        allCycles.forEach(c => {
            if (c.symbol && !symbolSet.has(c.symbol)) {
                symbols.push(c.symbol);
                symbolSet.add(c.symbol);
            }
        });

        const symbolRankMap = {};
        symbols.forEach((sym, i) => { symbolRankMap[sym] = i + 1; });
        const maxRank = symbols.length;

        // 2. Build trade markers with Y = inverted rank
        const trades = [];
        const cycleLookupMap = {};

        allCycles.forEach(cycle => {
            const rank = symbolRankMap[cycle.symbol] || 1;
            const yVal = (maxRank + 1) - rank;

            if (cycle.buys) {
                cycle.buys.forEach(buy => {
                    const timeUnix = Math.floor(new Date(buy.signal_timestamp).getTime() / 1000);
                    trades.push({
                        time: buy.signal_timestamp,
                        price: yVal,
                        original_price: buy.executed_price,
                        type: 'buy',
                        symbol: cycle.symbol,
                        metadata: buy.trade_metadata || {},
                    });
                    const timeMin = Math.floor(timeUnix / 60);
                    cycleLookupMap[`${timeMin}_${Math.round(yVal)}`] = cycle;
                });
            }

            if (cycle.sell) {
                const avgEntry = cycle.avg_entry_price || 0;
                const sellPrice = cycle.sell.executed_price || 0;
                const pnlPct = avgEntry > 0 ? (sellPrice - avgEntry) / avgEntry : 0;
                const timeUnix = Math.floor(new Date(cycle.sell.signal_timestamp).getTime() / 1000);
                trades.push({
                    time: cycle.sell.signal_timestamp,
                    price: yVal,
                    original_price: cycle.sell.executed_price,
                    type: 'sell',
                    pnl_percent: pnlPct,
                    symbol: cycle.symbol,
                    metadata: cycle.sell.trade_metadata || {},
                });
                const timeMin = Math.floor(timeUnix / 60);
                cycleLookupMap[`${timeMin}_${Math.round(yVal)}`] = cycle;
            }
        });

        trades.sort((a, b) => new Date(a.time) - new Date(b.time));

        // 3. Build synthetic OHLCV (candle at rank Y position for each trade time)
        const uniqueTimeMap = new Map();
        trades.forEach(t => {
            const timeNum = Math.floor(new Date(t.time).getTime() / 1000);
            const yVal = t.price;
            const existing = uniqueTimeMap.get(timeNum);
            if (existing) {
                uniqueTimeMap.set(timeNum, {
                    time: timeNum,
                    open: existing.open,
                    high: Math.max(existing.high, yVal),
                    low: Math.min(existing.low, yVal),
                    close: yVal,
                });
            } else {
                uniqueTimeMap.set(timeNum, { time: timeNum, open: yVal, high: yVal, low: yVal, close: yVal });
            }
        });

        // Anchors for timeline range
        if (trades.length > 0) {
            const firstTime = Math.floor(new Date(trades[0].time).getTime() / 1000) - 86400;
            const lastTime = Math.floor(Date.now() / 1000);
            if (!uniqueTimeMap.has(firstTime)) uniqueTimeMap.set(firstTime, { time: firstTime, open: 0, high: 0, low: 0, close: 0 });
            if (!uniqueTimeMap.has(lastTime)) uniqueTimeMap.set(lastTime, { time: lastTime, open: 0, high: 0, low: 0, close: 0 });
        }

        const chartData = Array.from(uniqueTimeMap.values()).sort((a, b) => a.time - b.time);

        // 4. Rank formatter (Y-axis labels)
        const formatter = (price) => {
            const yVal = Math.round(price);
            if (Math.abs(price - yVal) < 0.1) {
                const rank = (maxRank + 1) - yVal;
                if (rank > 0 && rank <= maxRank) {
                    const sym = symbols[rank - 1];
                    const match = (savedSymbols || []).find(s => s.code === sym);
                    const name = match ? match.name : sym;
                    const cycleCount = allCycles.filter(c => c.symbol === sym).length;
                    return `R${rank}: ${name} (${cycleCount})`;
                }
            }
            return '';
        };

        const scaleOptions = {
            fixedYRange: { min: 0.5, max: maxRank + 0.5 },
            autoScale: false,
            minimumWidth: 120,
        };

        return {
            overviewChartData: chartData,
            overviewTrades: trades,
            overviewRankFormatter: formatter,
            overviewPriceScaleOptions: scaleOptions,
            overviewSymbolRanks: { symbolRankMap, symbols, maxRank, cycleLookupMap, allCycles },
        };
    }, [historyData, configList, savedSymbols]);

    // New: Strategy Internal State
    const [strategyState, setStrategyState] = useState(null);

    // Helper: Aggregate 1m candles to target interval
    const aggregateCandles = (candles1m, interval) => {
        if (!candles1m || candles1m.length === 0) return [];
        if (interval === '1m') return candles1m;

        const ms = 1000;
        const min = 60 * ms;
        const hour = 60 * min;
        const day = 24 * hour;

        const unit = interval.slice(-1);
        const value = parseInt(interval.slice(0, -1));

        let intervalMs = min;
        if (unit === 'm') intervalMs = value * min;
        else if (unit === 'h') intervalMs = value * hour;
        else if (unit === 'd') intervalMs = value * day;

        const aggregated = [];
        let currentCandle = null;

        candles1m.forEach(c => {
            const candleTime = c.time * 1000; // Convert to ms
            const bucketTime = Math.floor(candleTime / intervalMs) * intervalMs / 1000; // Back to seconds

            if (!currentCandle || currentCandle.time !== bucketTime) {
                if (currentCandle) aggregated.push(currentCandle);
                currentCandle = {
                    time: bucketTime,
                    open: c.open,
                    high: c.high,
                    low: c.low,
                    close: c.close,
                    volume: c.volume || 0
                };
            } else {
                currentCandle.high = Math.max(currentCandle.high, c.high);
                currentCandle.low = Math.min(currentCandle.low, c.low);
                currentCandle.close = c.close;
                currentCandle.volume = (currentCandle.volume || 0) + (c.volume || 0);
            }
        });

        if (currentCandle) aggregated.push(currentCandle);
        return aggregated;
    };

    // Effect: Re-aggregate when interval changes
    useEffect(() => {
        if (rawCandles.length > 0) {
            const aggregated = aggregateCandles(rawCandles, selectedInterval);
            setRealTimeCandles(aggregated);
        }
    }, [selectedInterval, rawCandles]);

    // Polling Ref
    const pollInterval = useRef(null);
    const lastFetchRef = useRef({ symbol: null, status: null });  // Always fetch 1m, no interval tracking

    // Handler: Cycle Click → Fetch 1m OHLCV and show chart
    const handleCycleClick = async (cycle) => {
        setSelectedCycle(cycle);
        setIsCycleChartLoading(true);
        setCycleChartData(null);

        try {
            const symbol = cycle.symbol;

            // Step 1: Trigger incremental 1m data fetch → save to DB
            await fetchMarketData(symbol, { interval: '1m', days: 365, backfill: false });

            // Step 2: Determine date range for chart (entry - 1 day buffer to exit + 1 day buffer)
            const entryDate = new Date(cycle.entry_time);
            const exitDate = cycle.exit_time ? new Date(cycle.exit_time) : new Date();

            // Add buffer: 1 day before entry, 1 day after exit
            const startDate = new Date(entryDate);
            startDate.setDate(startDate.getDate() - 1);
            const endDate = new Date(exitDate);
            endDate.setDate(endDate.getDate() + 1);

            // Step 3: Fetch 1m candles from DB for the date range
            // We'll fetch day by day and merge
            const allCandles = [];
            const current = new Date(startDate);
            while (current <= endDate) {
                const dateStr = current.toISOString().slice(0, 10).replace(/-/g, '');
                try {
                    const dayCandles = await getOHLCV(symbol, { interval: '1m', date: dateStr });
                    if (Array.isArray(dayCandles)) {
                        allCandles.push(...dayCandles);
                    }
                } catch (e) {
                    // Some days may have no data (weekends/holidays)
                }
                current.setDate(current.getDate() + 1);
            }

            // Step 4: Build trade markers from cycle data (matching VisualBacktestChart format)
            const trades = [];
            if (cycle.buys) {
                for (const buy of cycle.buys) {
                    trades.push({
                        time: Math.floor(new Date(buy.signal_timestamp).getTime() / 1000),
                        price: buy.executed_price,
                        original_price: buy.executed_price,
                        type: 'buy',
                        metadata: buy.trade_metadata || {},
                    });
                }
            }
            if (cycle.sell) {
                const avgEntry = cycle.avg_entry_price || 0;
                const sellPrice = cycle.sell.executed_price || 0;
                const pnlPct = avgEntry > 0 ? (sellPrice - avgEntry) / avgEntry : 0;
                trades.push({
                    time: Math.floor(new Date(cycle.sell.signal_timestamp).getTime() / 1000),
                    price: cycle.sell.executed_price,
                    original_price: cycle.sell.executed_price,
                    type: 'sell',
                    pnl_percent: pnlPct,
                    metadata: cycle.sell.trade_metadata || {},
                });
            }

            // Deduplicate candles by time
            const seen = new Set();
            const deduped = allCandles.filter(c => {
                if (seen.has(c.time)) return false;
                seen.add(c.time);
                return true;
            }).sort((a, b) => a.time - b.time);

            setCycleChartData({ candles: deduped, trades });
        } catch (err) {
            console.error("Failed to load cycle chart:", err);
            addLog('Error', `Cycle chart load failed: ${err?.response?.status || ''} ${err?.response?.data?.detail || err.message}`);
            setCycleChartData(null);
        } finally {
            setIsCycleChartLoading(false);
        }
    };

    // Handler: Overview chart click → find cycle → drill down to detail chart
    const handleOverviewChartClick = (param) => {
        if (!param || !param.time || param.price === undefined || !overviewSymbolRanks) return;

        const { symbolRankMap, symbols, maxRank, cycleLookupMap, allCycles } = overviewSymbolRanks;

        // Try exact lookup (minute-level key)
        const clickTimeMin = Math.floor(param.time / 60);
        const clickY = Math.round(param.price);
        const key = `${clickTimeMin}_${clickY}`;
        let cycle = cycleLookupMap[key];

        if (!cycle) {
            // Fallback: derive rank from Y, find symbol, find nearest cycle
            const rank = (maxRank + 1) - clickY;
            if (rank > 0 && rank <= maxRank) {
                const targetSymbol = symbols[rank - 1];
                const clickTime = param.time;

                const symbolCycles = allCycles.filter(c => c.symbol === targetSymbol);
                let bestCycle = null;
                let bestDist = Infinity;

                for (const c of symbolCycles) {
                    const entryUnix = new Date(c.entry_time).getTime() / 1000;
                    const exitUnix = c.exit_time ? new Date(c.exit_time).getTime() / 1000 : Date.now() / 1000;

                    // Click within cycle range
                    if (clickTime >= entryUnix && clickTime <= exitUnix) {
                        bestCycle = c;
                        break;
                    }
                    // Otherwise find nearest
                    const dist = Math.min(Math.abs(clickTime - entryUnix), Math.abs(clickTime - exitUnix));
                    if (dist < bestDist) {
                        bestDist = dist;
                        bestCycle = c;
                    }
                }

                cycle = bestCycle;
            }
        }

        if (cycle) {
            handleCycleClick(cycle);
        }
    };

    // Helper: Export trade history as CSV
    const exportHistoryCSV = () => {
        if (!historyData) return;

        const allCycles = [
            ...(historyData.open_cycles || []).map(c => ({ ...c, _status: 'Open' })),
            ...(historyData.cycles || []).map(c => ({ ...c, _status: 'Closed' })),
        ];

        if (allCycles.length === 0) return;

        const headers = ['Status', 'Symbol', 'Strategy', 'Entry Time', 'Exit Time', 'Num Entries', 'Total Buy Qty', 'Avg Entry Price', 'Sell Price', 'Realized PnL', 'Return %', 'Mode', 'Config Snapshot'];
        const rows = allCycles.map(c => [
            c._status,
            c.symbol,
            c.strategy_name || '',
            c.entry_time || '',
            c.exit_time || '',
            c.num_entries || 0,
            c.total_buy_qty || 0,
            c.avg_entry_price || 0,
            c.sell_price || 0,
            c.realized_pnl || 0,
            c.return_pct != null ? c.return_pct.toFixed(2) : '',
            c.is_paper ? 'Paper' : 'Real',
            c.config_snapshot ? JSON.stringify(c.config_snapshot) : '',
        ]);

        const csvContent = [headers, ...rows]
            .map(row => row.map(v => `"${String(v).replace(/"/g, '""')}"`).join(','))
            .join('\n');

        const BOM = '\uFEFF';
        const blob = new Blob([BOM + csvContent], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        const now = new Date();
        const dateStr = `${now.getFullYear()}${String(now.getMonth()+1).padStart(2,'0')}${String(now.getDate()).padStart(2,'0')}`;
        a.download = `trade_history_${historyMode}_${dateStr}.csv`;
        a.click();
        URL.revokeObjectURL(url);
        addLog('Export', `CSV exported: ${allCycles.length} cycles`);
    };

    // Helper: Logs
    const addLog = (source, msg) => {
        setLogs(prev => [{
            time: new Date().toLocaleTimeString(),
            source,
            msg
        }, ...prev].slice(0, 100));
    };

    // Initial Load & Status Management
    useEffect(() => {
        const init = async () => {
            if (mode === 'TRADE') {
                await checkStatus();
                // NOTE: Auto-start removed in v0.9.7.3 - users must manually click Start
            } else {
                setStatus('RUNNING');
                addLog("System", `Started watching ${strategyConfig.symbol}`);
            }
        };
        init();
        return () => stopPolling();
    }, [mode, strategyConfig.symbol, currentRankIndex]); // Added currentRankIndex to dependencies

    // Fetch Account Balance when IDLE to show user how much they can allocate
    useEffect(() => {
        if (status === 'IDLE') {
            const fetchBal = async () => {
                try {
                    const bal = await getBalance();
                    if (bal && bal.cash) {
                        setAvailableBalance(bal.cash.KRW);
                    }
                } catch (e) {
                    console.error("Failed to fetch balance", e);
                }
            };
            fetchBal();
        }
    }, [status]);

    // Auto-initialize rank weights when configList or executionMode changes
    useEffect(() => {
        if (executionMode !== 'parallel') return;
        const activeIndices = configList.map((c, i) => c.is_active ? i : -1).filter(i => i >= 0);
        if (activeIndices.length === 0) return;
        const equalWeight = Math.floor(100 / activeIndices.length);
        const remainder = 100 - (equalWeight * activeIndices.length);
        const newWeights = {};
        activeIndices.forEach((idx, pos) => {
            newWeights[idx] = equalWeight + (pos === 0 ? remainder : 0);
        });
        setRankWeights(newWeights);
    }, [executionMode, configList.length, configList.map(c => c.is_active).join(',')]);

    // Fetch Initial Candles for Real-Time View (Hybrid Pattern: History + Live)
    // When RUNNING with a live session, WebSocket sends the most up-to-date history
    // (including new candles from the aggregator). We use HTTP API only as fallback
    // when WebSocket is not available (e.g. WATCH mode, or session not started yet).
    const wsHistoryReceived = useRef(false);

    useEffect(() => {
        // Skip fetch if symbol is missing or we are in STARTING state
        if (!strategyConfig.symbol || status === 'STARTING') return;

        // If we're in TRADE mode with a session, WebSocket will provide history.
        // Skip HTTP fetch to avoid overwriting WS data with stale REST API data.
        if (mode === 'TRADE' && sessionId && status === 'RUNNING') {
            console.log(`[DEBUG] Skipping HTTP fetch - WebSocket will provide history for session ${sessionId}`);
            return;
        }

        // Deduplication Check: Skip if this symbol was already fetched (always fetch 1m)
        if (lastFetchRef.current.symbol === strategyConfig.symbol) {
            console.log(`[DEBUG] Skipping redundant history fetch for ${strategyConfig.symbol}`);
            return;
        }

        console.log(`[DEBUG] History Fetch Effect Triggered. Status: ${status}, Symbol: ${strategyConfig.symbol}`);
        lastFetchRef.current = { symbol: strategyConfig.symbol, status: status };
        setRawCandles([]);
        setRealTimeCandles([]);

        (async () => {
            try {
                const now = new Date();
                const kstOffset = 9 * 60;
                const utc = now.getTime() + (now.getTimezoneOffset() * 60000);
                const kstDate = new Date(utc + (kstOffset * 60000));
                const dateStr = kstDate.toISOString().split('T')[0].replace(/-/g, '');

                addLog("System", `Fetching 1m candles...`);

                // Always fetch 1m data - client-side aggregation handles interval
                const candles = await getOHLCV(strategyConfig.symbol, {
                    date: dateStr,
                    interval: '1m'
                });

                // Only set if WS history hasn't arrived yet
                if (!wsHistoryReceived.current) {
                    if (candles && candles.length > 0) {
                        setRawCandles(candles);
                        // realTimeCandles will be set by the aggregation useEffect
                        addLog("System", `Loaded ${candles.length} candles (HTTP). Last: ${candles[candles.length - 1].time}`);
                    } else {
                        addLog("System", "No history data. Waiting for stream...");
                    }
                } else {
                    console.log("[DEBUG] HTTP fetch completed but WS history already received, skipping.");
                }
            } catch (e) {
                console.error("Init Error", e);
                addLog("Error", "Failed to fetch history");
                setRawCandles([]);
                setRealTimeCandles([]);
            }
        })();
    }, [status, strategyConfig.symbol, mode, sessionId]);


    const startPolling = () => {
        if (pollInterval.current) return;
        pollInterval.current = setInterval(checkStatus, 3000);
    };

    const stopPolling = () => {
        if (pollInterval.current) {
            clearInterval(pollInterval.current);
            pollInterval.current = null;
        }
    };

    const checkStatus = async () => {
        try {
            const allSessions = await getLiveStatus({ allAccounts: true });

            // Filter to only sessions belonging to the selected group
            const groupSessionIds = new Set(
                (activeSessionGroup?.sessions || []).map(s => s.session_id)
            );
            const sessions = groupSessionIds.size > 0
                ? allSessions.filter(s => groupSessionIds.has(s.session_id))
                : allSessions;

            if (executionMode === 'parallel' || Object.keys(parallelSessions).length > 1) {
                // Multi-session: detect sessions for all active ranks (parallel & exclusive)
                const activeSessions = {};
                let anyRunning = false;
                configList.forEach((cfg, idx) => {
                    if (!cfg.is_active) return;
                    const match = sessions.find(s => s.symbol === cfg.symbol && s.is_running);
                    if (match) {
                        activeSessions[idx] = match.session_id;
                        anyRunning = true;
                    }
                });
                setParallelSessions(activeSessions);
                if (anyRunning) {
                    setStatus('RUNNING');
                    const primarySid = activeSessions[currentRankIndex] || Object.values(activeSessions)[0];
                    if (primarySid) setSessionId(primarySid);
                    // Aggregate PnL/trades from all parallel sessions
                    const allSessionIds = Object.values(activeSessions);
                    const allSessionData = sessions.filter(s => allSessionIds.includes(s.session_id));
                    const aggregatedPnl = allSessionData.reduce((sum, s) => sum + (s.pnl || 0), 0);
                    const aggregatedTrades = allSessionData.reduce((sum, s) => sum + (s.trades_count || 0), 0);
                    const primaryData = sessions.find(s => s.session_id === primarySid);
                    setLiveData(primaryData ? {
                        ...primaryData,
                        pnl: aggregatedPnl,
                        trades_count: aggregatedTrades,
                        _parallel_sessions: allSessionData
                    } : null);
                    startPolling();
                    return true;
                } else {
                    if (status === 'RUNNING') {
                        setStatus('STOPPED');
                        stopPolling();
                    }
                    return false;
                }
            } else {
                // Exclusive: single session by symbol, but show all configured symbols in overview
                const currentSymbol = strategyConfig.symbol;
                const mySession = sessions.find(s => s.symbol === currentSymbol && s.is_running);

                if (mySession) {
                    setStatus('RUNNING');
                    setSessionId(mySession.session_id);
                    // Include all session data for configured symbols in _parallel_sessions
                    const allConfiguredSessions = sessions.filter(s => s.is_running);
                    // Track which rank index has active session
                    const activeSessions = {};
                    configList.forEach((cfg, idx) => {
                        const match = sessions.find(s => s.symbol === cfg.symbol && s.is_running);
                        if (match) activeSessions[idx] = match.session_id;
                    });
                    setParallelSessions(activeSessions);
                    setLiveData({
                        ...mySession,
                        _parallel_sessions: allConfiguredSessions.length > 0 ? allConfiguredSessions : [mySession]
                    });
                    startPolling();
                    return true;
                } else {
                    if (status === 'RUNNING') {
                        setStatus('STOPPED');
                        stopPolling();
                    }
                    return false;
                }
            }
        } catch (err) {
            console.error("Live Status Error", err);
            return false;
        }
    };

    // Session Actions: Resume ALL sessions in the group (Option B - actions in panel)
    const handleResumeSession = async () => {
        const sessions = activeSessionGroup?.sessions;
        if (!sessions || sessions.length === 0) return;

        setIsResuming(true);
        try {
            // Resume all sessions in the group
            const results = await Promise.allSettled(
                sessions.map(s => resumeSession(s.session_id))
            );

            const succeeded = results.filter(r => r.status === 'fulfilled').length;
            const failed = results.filter(r => r.status === 'rejected').length;

            if (failed > 0) {
                addLog("Warning", `Group resumed: ${succeeded}/${sessions.length} succeeded, ${failed} failed`);
            } else {
                addLog("System", `Group resumed: ${succeeded} session(s) (${sessions[0].strategy_name})`);
            }

            // Notify parent to refresh session list
            if (onSessionAction) onSessionAction('resume', sessions[0]);
        } catch (err) {
            console.error('Failed to resume sessions:', err);
            showAlert(`재시작 실패: ${err.response?.data?.detail || err.message}`, 'error', '세션 재시작 오류');
        } finally {
            setIsResuming(false);
        }
    };

    // Session Actions: Delete ALL sessions in the group (Option B - actions in panel)
    const handleDeleteSession = async () => {
        const sessions = activeSessionGroup?.sessions;
        if (!sessions || sessions.length === 0) return;

        setIsDeleting(true);
        try {
            // Delete all sessions in the group
            const results = await Promise.allSettled(
                sessions.map(s => deleteSession(s.session_id))
            );

            const succeeded = results.filter(r => r.status === 'fulfilled').length;
            const failed = results.filter(r => r.status === 'rejected').length;

            if (failed > 0) {
                addLog("Warning", `Group deleted: ${succeeded}/${sessions.length} succeeded, ${failed} failed`);
            } else {
                addLog("System", `Group deleted: ${succeeded} session(s) (${sessions[0].strategy_name})`);
            }

            setIsDeleteModalOpen(false);
            // Notify parent to refresh session list and clear selection
            if (onSessionAction) onSessionAction('delete', sessions[0]);
        } catch (err) {
            console.error('Failed to delete sessions:', err);
            showAlert(`삭제 실패: ${err.response?.data?.detail || err.message}`, 'error', '세션 삭제 오류');
        } finally {
            setIsDeleting(false);
        }
    };

    // Get symbol name helper for delete modal
    const getSymbolName = (code) => {
        const match = savedSymbols.find(s => s.code === code);
        return match?.name || code;
    };

    const handleStart = async () => {
        if (!strategyConfig.symbol) {
            showAlert("종목을 선택해주세요", 'warning', '종목 미선택');
            return;
        }

        // Phase 5: Validate account selection
        if (!selectedAccountId) {
            showAlert("계좌를 선택해주세요", 'warning', '계좌 미선택');
            return;
        }

        try {
            setError(null);
            setStatus('STARTING');

            // Stop only the selected group's running sessions before starting new ones
            // (don't touch other groups' sessions)
            try {
                const groupSessions = activeSessionGroup?.sessions || [];
                const runningIds = groupSessions
                    .filter(s => s.status === 'RUNNING' || s.status === 'PAUSED')
                    .map(s => s.session_id);
                if (runningIds.length > 0) {
                    const results = await Promise.allSettled(
                        runningIds.map(sid => stopLiveBot(sid))
                    );
                    const succeeded = results.filter(r => r.status === 'fulfilled').length;
                    if (succeeded > 0) {
                        addLog("System", `Stopped ${succeeded} existing session(s) in group before starting new ones`);
                    }
                }
            } catch (stopErr) {
                console.warn("Failed to stop existing group sessions:", stopErr);
                // Continue anyway - the sessions might not exist
            }

            if (executionMode === 'parallel') {
                // Validate weights sum to 100%
                const weightSum = Object.entries(rankWeights)
                    .filter(([idx]) => configList[idx]?.is_active)
                    .reduce((s, [, w]) => s + w, 0);
                if (weightSum !== 100) {
                    setError(`Rank allocation must total 100% (currently ${weightSum}%)`);
                    setStatus('IDLE');
                    return;
                }

                // Parallel: start sessions for all active ranks
                const activeConfigs = configList.filter(c => c.is_active);
                if (activeConfigs.length === 0) {
                    setError("No active ranks to start");
                    setStatus('ERROR');
                    return;
                }
                const totalCapital = parseFloat(inputCapital) || 0;
                const totalWeight = Object.entries(rankWeights)
                    .filter(([idx]) => configList[idx]?.is_active)
                    .reduce((s, [, w]) => s + w, 0);

                // Generate group_id for all sessions in this batch
                const groupId = crypto.randomUUID();

                const newSessions = {};
                for (let i = 0; i < configList.length; i++) {
                    const cfg = configList[i];
                    if (!cfg.is_active) continue;

                    const weight = rankWeights[i] || 0;
                    const rankCapital = totalWeight > 0
                        ? Math.floor(totalCapital * weight / totalWeight)
                        : Math.floor(totalCapital / activeConfigs.length);

                    // Resolve preset name for live session tracking
                    const presetName = cfg.parameter_presets?.find(p => p.id === cfg.selected_preset_id)?.name || null;
                    const payload = {
                        symbol: cfg.symbol,
                        strategy_name: strategyName || "time_momentum",
                        strategy_config: { ...cfg, selected_preset_name: presetName },
                        initial_capital: rankCapital,
                        is_paper: isPaperMode,  // Phase 5: Paper/Real mode selection
                        account_id: selectedAccountId,  // Phase 5: Explicit account selection
                        group_id: groupId  // Phase 5: Session grouping for multi-rank
                    };
                    try {
                        const res = await startLiveBot(payload);
                        newSessions[i] = res.session_id;
                        addLog("System", `Rank ${i + 1} Started: ${res.session_id} (${cfg.symbol}, Capital: ${rankCapital.toLocaleString()} [${weight}%])`);
                    } catch (rankErr) {
                        addLog("Error", `Rank ${i + 1} Failed: ${rankErr.response?.data?.detail || rankErr.message}`);
                    }
                }
                setParallelSessions(newSessions);
                if (Object.keys(newSessions).length > 0) {
                    setSessionId(Object.values(newSessions)[0]);
                    setStatus('RUNNING');
                    startPolling();
                    addLog("System", `Parallel Mode: ${Object.keys(newSessions).length} sessions started`);
                } else {
                    setStatus('ERROR');
                    setError("No sessions started");
                }
            } else {
                // Exclusive: start ALL active ranks competing for one lock
                const activeConfigs = configList.filter(c => c.is_active);
                if (activeConfigs.length === 0) {
                    setError("No active ranks to start");
                    setStatus('ERROR');
                    return;
                }
                const totalCapital = parseFloat(inputCapital) || 0;

                // Generate group_id for all sessions in this batch
                const groupId = crypto.randomUUID();

                const newSessions = {};
                for (let i = 0; i < configList.length; i++) {
                    const cfg = configList[i];
                    if (!cfg.is_active) continue;

                    // Resolve preset name for live session tracking
                    const presetNameExcl = cfg.parameter_presets?.find(p => p.id === cfg.selected_preset_id)?.name || null;
                    const payload = {
                        symbol: cfg.symbol,
                        strategy_name: strategyName || "time_momentum",
                        strategy_config: { ...cfg, execution_mode: 'exclusive', selected_preset_name: presetNameExcl },
                        initial_capital: totalCapital,  // Full capital (only one trades at a time)
                        is_paper: isPaperMode,  // Phase 5: Paper/Real mode selection
                        account_id: selectedAccountId,  // Phase 5: Explicit account selection
                        group_id: groupId  // Phase 5: Session grouping for multi-rank
                    };
                    try {
                        const res = await startLiveBot(payload);
                        newSessions[i] = res.session_id;
                        addLog("System", `Rank ${i + 1} Started: ${res.session_id} (${cfg.symbol}, Exclusive)`);
                    } catch (rankErr) {
                        addLog("Error", `Rank ${i + 1} Failed: ${rankErr.response?.data?.detail || rankErr.message}`);
                    }
                }
                setParallelSessions(newSessions);
                if (Object.keys(newSessions).length > 0) {
                    setSessionId(Object.values(newSessions)[0]);
                    setStatus('RUNNING');
                    startPolling();
                    addLog("System", `Exclusive Mode: ${Object.keys(newSessions).length} ranks competing`);
                } else {
                    setStatus('ERROR');
                    setError("No sessions started");
                }
            }

        } catch (err) {
            setError(err.response?.data?.detail || err.message);
            setStatus('ERROR');
            addLog("Error", err.message);
        }
    };

    const handleToggleMode = async () => {
        if (!sessionId) return;
        try {
            const currentMode = liveData?.is_paper !== false; // Default to paper if undefined
            const nextIsPaper = !currentMode;

            await toggleLiveMode(sessionId, nextIsPaper);
            setLiveData(prev => ({ ...prev, is_paper: nextIsPaper }));
            addLog("System", `Mode switched to ${nextIsPaper ? 'PAPER' : 'REAL'} by User`);
        } catch (err) {
            setError(err.message);
        }
    };

    const handleForceClosePosition = async () => {
        try {
            // Force close positions only (no session stop) — sessions keep running
            const sessionIds = Object.values(parallelSessions);
            if (sessionIds.length > 0) {
                for (const sid of sessionIds) {
                    await liquidateLiveBot(sid, { autoStop: false });
                }
                addLog("System", `Force-closed positions for ${sessionIds.length} session(s). Sessions still running.`);
            } else if (sessionId) {
                await liquidateLiveBot(sessionId, { autoStop: false });
                addLog("System", "Force-closed all positions. Session still running.");
            }
            // Notify parent to refresh session list
            if (onSessionAction) onSessionAction('force_close', activeSessionGroup?.sessions?.[0]);
        } catch (err) {
            setError(err.message);
            addLog("Error", `Force close failed: ${err.message}`);
        }
    };

    const handleToggleOrders = async () => {
        const currentEnabled = liveData?.orders_enabled !== false;
        const newEnabled = !currentEnabled;
        try {
            if (executionMode === 'parallel' && Object.keys(parallelSessions).length > 0) {
                for (const sid of Object.values(parallelSessions)) {
                    await toggleLiveOrders(sid, newEnabled);
                }
            } else if (sessionId) {
                await toggleLiveOrders(sessionId, newEnabled);
            }
            setLiveData(prev => ({ ...prev, orders_enabled: newEnabled }));
            addLog("System", `Orders ${newEnabled ? 'resumed' : 'paused'}.`);
        } catch (err) {
            setError(err.message);
            addLog("Error", `Toggle orders failed: ${err.message}`);
        }
    };

    // WebSocket for Real-time Data
    useEffect(() => {
        if (status !== 'RUNNING') return;
        if (mode === 'TRADE' && !sessionId) return;

        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        let wsUrl;
        if (mode === 'WATCH') {
            wsUrl = `${wsProtocol}//${window.location.hostname}:8001/api/v1/live/ws/watch/${strategyConfig.symbol}`;
        } else {
            wsUrl = `${wsProtocol}//${window.location.hostname}:8001/api/v1/live/ws/${sessionId}`;
        }

        let ws = new WebSocket(wsUrl);

        ws.onopen = () => {
            setWsConnected(true);
            addLog("System", `WS connected to: ${wsUrl}`);
        };

        ws.onerror = (error) => {
            setWsConnected(false);
            addLog("System", `WS error: ${error.message || 'Connection error'}`);
        };

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);

                if (data.type === 'tick') {
                    setLiveData(prev => ({ ...prev, current_price: data.price }));

                    // 1. Update Ticks List (for debug/legacy)
                    setTickData(prev => {
                        let timeStr = data.time;
                        if (data.time && data.time.includes('T')) {
                            timeStr = data.time.split('T')[1].split('.')[0];
                        }
                        return [...prev, { time: timeStr, price: data.price }].slice(-50);
                    });

                    // 2. Aggregate to 1m candle (rawCandles) - aggregation useEffect handles interval
                    setRawCandles(prevCandles => {
                        const newPrice = data.price;
                        let tickTime = new Date();
                        if (data.time) {
                            const t = new Date(data.time);
                            if (!isNaN(t.getTime())) tickTime = t;
                        }

                        // Always aggregate to 1m candles
                        tickTime.setSeconds(0, 0);
                        const candleTime = tickTime.getTime() / 1000;

                        const lastCandle = prevCandles[prevCandles.length - 1];

                        if (lastCandle && lastCandle.time === candleTime) {
                            // Update existing 1m candle
                            return [...prevCandles.slice(0, -1), {
                                ...lastCandle,
                                high: Math.max(lastCandle.high, newPrice),
                                low: Math.min(lastCandle.low, newPrice),
                                close: newPrice,
                                volume: (lastCandle.volume || 0) + (data.volume || 1)
                            }];
                        } else if (lastCandle && lastCandle.time > candleTime) {
                            // Received old tick? Ignore
                            return prevCandles;
                        } else {
                            // New 1m candle
                            return [...prevCandles, {
                                time: candleTime,
                                open: newPrice,
                                high: newPrice,
                                low: newPrice,
                                close: newPrice,
                                volume: (data.volume || 1)
                            }];
                        }
                    });

                } else if (data.type === 'history') {
                    // Backend sends full history on WebSocket connect
                    const rawData = data.data || [];
                    const historyCandles = rawData.map(c => {
                        let t = c.time || c.timestamp;
                        if (typeof t === 'string') {
                            // Handle both ISO "2026-01-28T10:36:00" and Kiwoom "20260128103600" formats
                            if (/^\d{14}$/.test(t)) {
                                // Kiwoom format: YYYYMMDDHHmmss
                                const y = t.slice(0,4), mo = t.slice(4,6), d = t.slice(6,8);
                                const h = t.slice(8,10), mi = t.slice(10,12), s = t.slice(12,14);
                                t = new Date(`${y}-${mo}-${d}T${h}:${mi}:${s}`).getTime() / 1000;
                            } else {
                                t = new Date(t).getTime() / 1000;
                            }
                        }
                        return {
                            time: Number(t),
                            open: Number(c.open),
                            high: Number(c.high),
                            low: Number(c.low),
                            close: Number(c.close),
                            volume: Number(c.volume || 0)
                        };
                    }).filter(c => !isNaN(c.time));

                    if (historyCandles.length > 0) {
                        wsHistoryReceived.current = true;
                        setRawCandles(historyCandles);  // Always store as 1m, aggregation handles interval
                        addLog("System", `WS History: ${historyCandles.length} candles (last: ${new Date(historyCandles[historyCandles.length - 1].time * 1000).toLocaleTimeString()})`);
                    }
                } else if (data.type === 'candle') {
                    // Real-time candle close event from backend
                    const c = data.data || {};
                    addLog("WS-Candle", `New candle: t=${c.time||c.timestamp} O=${c.open} C=${c.close}`);
                    let t = c.time || c.timestamp;
                    if (typeof t === 'string') {
                        t = new Date(t).getTime() / 1000;
                    }
                    const newCandle = {
                        time: Number(t),
                        open: Number(c.open),
                        high: Number(c.high),
                        low: Number(c.low),
                        close: Number(c.close),
                        volume: Number(c.volume || 0)
                    };
                    if (!isNaN(newCandle.time)) {
                        setRawCandles(prev => {
                            // Replace if same time, append if new (1m candles)
                            const existing = prev.findIndex(x => x.time === newCandle.time);
                            if (existing >= 0) {
                                const updated = [...prev];
                                updated[existing] = newCandle;
                                return updated;
                            }
                            return [...prev, newCandle].sort((a, b) => a.time - b.time);
                        });
                    }
                } else if (data.type === 'strategy_status') {
                    setStrategyState(data.data);
                }
            } catch (err) {
                console.error("WS Parse Error", err);
            }
        };

        ws.onclose = () => {
            setWsConnected(false);
            addLog("System", "Real-time feed disconnected");
        };

        return () => {
            wsHistoryReceived.current = false;
            setWsConnected(false);
            if (ws) ws.close();
        };
    }, [sessionId, status, mode, strategyConfig.symbol]);









    // Render Helpers
    const getStatusColor = () => {
        switch (status) {
            case 'RUNNING': return 'text-green-400 border-green-400/30 bg-green-400/10';
            case 'STOPPED': return 'text-gray-400 border-gray-400/30 bg-gray-400/10';
            case 'ERROR': return 'text-red-400 border-red-400/30 bg-red-400/10';
            case 'STARTING': return 'text-blue-400 border-blue-400/30 bg-blue-400/10';
            default: return 'text-gray-500 border-gray-500/30 bg-gray-500/5';
        }
    };

    if (mode === 'WATCH') {
        return (
            <div className="flex flex-col h-full bg-[#1e1e24] border border-white/5 rounded-xl p-4">
                <div className="flex justify-between items-center mb-4">
                    <h3 className="text-sm font-bold text-gray-300 flex items-center gap-2">
                        <Activity size={14} className="text-blue-400 animate-pulse" />
                        Live Monitor: {strategyConfig.symbol}
                    </h3>
                    {liveData?.current_price && (
                        <span className="text-xl font-mono text-white">{liveData.current_price.toLocaleString()}</span>
                    )}
                </div>

                <div className="flex-1 w-full min-h-[200px] relative bg-black/20 rounded-lg overflow-hidden">
                    {/* Use VisualBacktestChart for consistent Candle/Tick visualization */}
                    <VisualBacktestChart
                        data={realTimeCandles}
                        trades={[]}
                        showOnlyPnl={false}
                        priceScaleOptions={{
                            autoScale: true,
                        }}
                        yAxisFormatter={(price) => price.toLocaleString()}
                        selectedInterval={selectedInterval}
                        onIntervalChange={handleIntervalChange}
                    />
                </div>
            </div>
        );
    }

    // Show configuration section even when no session is selected
    // User can set Trading Capital, Account, and Paper/Real mode before creating a session
    if (!activeSessionGroup) {
        return (
            <div className="space-y-6 pb-10">
                {/* Configuration Section - Always visible for session setup */}
                <div className="w-full bg-black/40 border border-white/10 rounded-xl p-5">
                    <h3 className="text-gray-300 font-bold text-sm mb-4 flex items-center gap-2">
                        <Settings size={14} className="text-gray-500" />
                        새 세션 설정
                    </h3>
                    <div className="flex flex-col md:flex-row items-start gap-6">
                        {/* Capital Input */}
                        <div className="flex-1 w-full">
                            <label className="block text-gray-400 text-[10px] font-bold tracking-wider uppercase mb-2">
                                Trading Capital (KRW)
                            </label>
                            <div className="relative group">
                                <input
                                    type="number"
                                    value={inputCapital}
                                    onChange={(e) => {
                                        const newValue = e.target.value;
                                        setInputCapital(newValue);
                                        if (onCapitalChange) {
                                            onCapitalChange(parseFloat(newValue) || 0);
                                        }
                                    }}
                                    className="w-full bg-black/60 border border-white/10 rounded-lg px-4 py-3 text-white font-mono text-xl outline-none focus:border-green-500/50 transition-all"
                                    placeholder="Enter amount..."
                                />
                                <div className="absolute right-4 top-1/2 -translate-y-1/2 text-gray-500 font-bold pointer-events-none">KRW</div>
                            </div>
                        </div>

                        {/* Account Selector */}
                        <div className="w-full md:w-56">
                            <label className="block text-gray-400 text-[10px] font-bold tracking-wider uppercase mb-2">
                                Trading Account
                            </label>
                            <select
                                value={selectedAccountId || ''}
                                onChange={(e) => setSelectedAccountId(e.target.value ? parseInt(e.target.value) : null)}
                                className="w-full bg-black/60 border border-white/10 rounded-lg px-3 py-3 text-white text-sm font-bold outline-none focus:border-blue-500/50 transition-all appearance-none cursor-pointer"
                            >
                                {accounts.filter(acc => !acc.is_disabled).map(acc => (
                                    <option key={acc.id} value={acc.id}>
                                        {acc.account_name} ({acc.environment === 'real' ? '실거래' : acc.environment === 'virtual' ? '모의' : '페이퍼'})
                                                                            </option>
                                ))}
                            </select>
                            <p className="text-gray-500 text-[9px] mt-1.5">
                                {accounts.find(a => a.id === selectedAccountId)?.account_number?.slice(-4)
                                    ? `계좌번호: ****${accounts.find(a => a.id === selectedAccountId)?.account_number?.slice(-4)}`
                                    : '계좌를 선택하세요'}
                            </p>
                        </div>

                        {/* Paper/Real Mode Toggle */}
                        <div className="w-full md:w-40">
                            <label className="block text-gray-400 text-[10px] font-bold tracking-wider uppercase mb-2">
                                Trading Mode
                            </label>
                            <button
                                onClick={() => {
                                    if (isPaperMode) {
                                        setModeSwitchConfirm({ isOpen: true, toReal: true, isRunningSession: false });
                                    } else {
                                        setModeSwitchConfirm({ isOpen: true, toReal: false, isRunningSession: false });
                                    }
                                }}
                                className={`w-full h-[46px] flex items-center justify-center gap-2 text-sm font-bold rounded-lg border transition-all ${
                                    isPaperMode
                                        ? 'bg-green-600/20 border-green-500 text-green-400 hover:bg-green-600/30'
                                        : 'bg-red-900/40 border-red-500 text-red-400 hover:bg-red-900/60'
                                }`}
                            >
                                {isPaperMode ? (
                                    <><Shield size={14} /> Paper</>
                                ) : (
                                    <><ShieldOff size={14} /> Real</>
                                )}
                            </button>
                            <p className="text-gray-500 text-[9px] mt-1.5">
                                {isPaperMode ? '시뮬레이션 모드' : '실제 주문 실행'}
                            </p>
                        </div>
                    </div>
                </div>

                {/* Empty State Message */}
                <div className="flex items-center justify-center min-h-[200px] bg-white/5 border border-white/10 rounded-xl">
                    <div className="text-center">
                        <div className="w-16 h-16 bg-gray-800/50 rounded-full flex items-center justify-center mx-auto mb-4">
                            <Radio size={28} className="text-gray-600" />
                        </div>
                        <h3 className="text-gray-400 font-bold text-base mb-2">세션을 선택하세요</h3>
                        <p className="text-gray-600 text-sm">
                            위 패널에서 세션 그룹을 선택하거나 '+ 새 세션' 버튼으로 세션을 추가하세요
                        </p>
                    </div>
                </div>

                {/* Trading Mode Switch Confirmation Modal */}
                <ConfirmModal
                    isOpen={modeSwitchConfirm.isOpen}
                    onClose={() => setModeSwitchConfirm({ isOpen: false, toReal: false, isRunningSession: false })}
                    onConfirm={() => {
                        setIsPaperMode(!modeSwitchConfirm.toReal);
                        setModeSwitchConfirm({ isOpen: false, toReal: false, isRunningSession: false });
                    }}
                    title={modeSwitchConfirm.toReal ? "🔴 실거래 모드로 전환" : "🟢 페이퍼 모드로 전환"}
                    message={modeSwitchConfirm.toReal
                        ? "실거래 모드로 전환하시겠습니까?\n\n⚠️ 주의: 실제 자금이 사용됩니다!"
                        : "페이퍼(시뮬레이션) 모드로 전환하시겠습니까?\n\n실제 주문이 실행되지 않습니다."}
                    confirmText={modeSwitchConfirm.toReal ? "실거래로 전환" : "페이퍼로 전환"}
                    isDanger={modeSwitchConfirm.toReal}
                />
            </div>
        );
    }

    return (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 min-h-full pb-10">
            {/* Shared Strategy Config Panel */}
            {configList.length > 0 && (
                <div className="lg:col-span-3">
                    <ActiveStrategiesPanel
                        configList={configList}
                        savedSymbols={savedSymbols}
                        parameterSchema={parameterSchema}
                        strategyId={strategyName}
                        disabled={true}
                    />
                </div>
            )}

            {/* Account Balance Panel */}
            {activeSessionGroup && (
                <div className="lg:col-span-3 bg-white/5 border border-white/10 rounded-xl p-4">
                    <div className="flex items-center justify-between mb-4">
                        <h3 className="font-bold text-gray-200 text-sm flex items-center gap-2">
                            <Wallet size={14} className="text-blue-400" />
                            세션 계좌 잔고
                            <span className="text-xs text-gray-500 font-normal ml-2">
                                {selectedSessionInfo?.accountName}
                            </span>
                        </h3>
                        <button
                            onClick={refreshSessionBalance}
                            disabled={isBalanceLoading}
                            className={`p-1.5 rounded-lg hover:bg-white/10 text-gray-400 hover:text-white transition-all ${isBalanceLoading ? 'animate-spin' : ''}`}
                            title="새로고침"
                        >
                            <RefreshCw size={14} />
                        </button>
                    </div>

                    {isBalanceLoading && !sessionBalance ? (
                        <div className="flex items-center justify-center py-4">
                            <div className="animate-pulse text-gray-500 text-sm">잔고 로딩중...</div>
                        </div>
                    ) : sessionBalance ? (
                        <div className="flex flex-wrap items-center gap-6 md:gap-12">
                            <div className="flex items-center gap-3">
                                <div className="p-2 bg-blue-500/20 rounded-lg text-blue-400">
                                    <Wallet size={20} />
                                </div>
                                <div>
                                    <div className="text-xs text-gray-400 font-medium uppercase tracking-wider">Total Assets</div>
                                    <div className="text-lg font-bold text-white">
                                        {new Intl.NumberFormat('ko-KR').format(sessionBalance.totalAssets)}
                                    </div>
                                </div>
                            </div>

                            <div className="flex items-center gap-3">
                                <div className="p-2 bg-emerald-500/20 rounded-lg text-emerald-400">
                                    <TrendingUp size={20} />
                                </div>
                                <div>
                                    <div className="text-xs text-gray-400 font-medium uppercase tracking-wider">Invested</div>
                                    <div className="text-lg font-bold text-white">
                                        {new Intl.NumberFormat('ko-KR').format(sessionBalance.totalInvested)}
                                    </div>
                                </div>
                            </div>

                            <div className="flex items-center gap-3">
                                <div className="p-2 bg-purple-500/20 rounded-lg text-purple-400">
                                    <DollarSign size={20} />
                                </div>
                                <div>
                                    <div className="text-xs text-gray-400 font-medium uppercase tracking-wider">Cash (KRW)</div>
                                    <div className="text-lg font-bold text-white">
                                        {new Intl.NumberFormat('ko-KR').format(sessionBalance.cash)}
                                    </div>
                                </div>
                            </div>
                        </div>
                    ) : (
                        <div className="text-gray-500 text-sm py-2">잔고 정보를 불러올 수 없습니다.</div>
                    )}
                </div>
            )}

            {/* Modal */}
            <ConfirmModal
                isOpen={isStopModalOpen}
                onClose={() => setIsStopModalOpen(false)}
                onConfirm={async () => {
                    try {
                        // Stop only sessions in the selected group
                        const groupSessions = activeSessionGroup?.sessions || [];
                        const runningIds = groupSessions
                            .filter(s => s.status === 'RUNNING' || s.status === 'PAUSED')
                            .map(s => s.session_id);

                        if (runningIds.length > 0) {
                            const results = await Promise.allSettled(
                                runningIds.map(sid => stopLiveBot(sid))
                            );
                            const succeeded = results.filter(r => r.status === 'fulfilled').length;
                            const failed = results.filter(r => r.status === 'rejected').length;
                            if (failed > 0) {
                                const errors = results
                                    .filter(r => r.status === 'rejected')
                                    .map(r => r.reason?.response?.data?.detail || r.reason?.message || 'Unknown')
                                    .join(', ');
                                addLog("Warning", `Stopped ${succeeded}/${runningIds.length} session(s). Errors: ${errors}`);
                                if (succeeded === 0) {
                                    setError(errors);
                                    return;
                                }
                            } else {
                                addLog("System", `Stopped ${succeeded} session(s)`);
                            }
                        } else {
                            addLog("System", "No running sessions to stop");
                        }
                        setStatus('STOPPED');
                        stopPolling();
                        // Notify parent to refresh session list (so SessionSwitcher updates status)
                        if (onSessionAction) onSessionAction('stop', activeSessionGroup?.sessions?.[0]);
                    } catch (err) {
                        setError(err.message);
                    }
                }}
                title="Stop Live Trading?"
                message={executionMode === 'parallel'
                    ? `Are you sure you want to stop ALL ${Object.keys(parallelSessions).length} parallel sessions? Pending orders might be cancelled.`
                    : "Are you sure you want to stop the live trading session? Pending orders might be cancelled."}
                confirmText={executionMode === 'parallel' ? "Stop All Sessions" : "Stop Session"}
                isDanger={true}
            />

            {/* Position Warning Modal */}
            <ConfirmModal
                isOpen={isPositionWarningOpen}
                onClose={() => setIsPositionWarningOpen(false)}
                onConfirm={() => setIsPositionWarningOpen(false)}
                title="세션 종료 불가"
                message={positionWarningMessage}
                confirmText="확인"
                cancelText={null}
            />

            {/* Trading Mode Switch Confirmation Modal */}
            <ConfirmModal
                isOpen={modeSwitchConfirm.isOpen}
                onClose={() => setModeSwitchConfirm({ isOpen: false, toReal: false, isRunningSession: false })}
                onConfirm={() => {
                    if (modeSwitchConfirm.isRunningSession) {
                        // Running session - call API to toggle mode
                        handleToggleMode();
                    } else {
                        // Pre-session - toggle local state
                        setIsPaperMode(!modeSwitchConfirm.toReal);
                    }
                    setModeSwitchConfirm({ isOpen: false, toReal: false, isRunningSession: false });
                }}
                title={modeSwitchConfirm.toReal ? "⚠️ 리얼 모드로 전환" : "📝 페이퍼 모드로 전환"}
                message={modeSwitchConfirm.toReal
                    ? `실제 주문이 체결됩니다!\n\n• 실제 자금으로 거래가 실행됩니다\n• 모든 매수/매도 주문이 실제로 전송됩니다\n• 손실이 발생할 수 있습니다\n\n설정 자본: ${Number(inputCapital).toLocaleString()}원\n계좌 잔고: ${availableBalance !== null ? Number(availableBalance).toLocaleString() + '원' : '확인 중...'}\n\n정말 리얼 모드로 전환하시겠습니까?`
                    : `시뮬레이션 모드로 전환합니다.\n\n• 실제 주문이 전송되지 않습니다\n• 가상의 거래 시뮬레이션만 수행됩니다\n• 실제 손익이 발생하지 않습니다\n\n페이퍼 모드로 전환하시겠습니까?`}
                confirmText={modeSwitchConfirm.toReal ? "리얼 모드 활성화" : "페이퍼 모드 전환"}
                isDanger={modeSwitchConfirm.toReal}
            />

            {/* Force Close Position Modal */}
            <ConfirmModal
                isOpen={isLiquidateModalOpen}
                onClose={() => setIsLiquidateModalOpen(false)}
                onConfirm={() => {
                    setIsLiquidateModalOpen(false);
                    handleForceClosePosition();
                }}
                title="Force Close Position"
                message={executionMode === 'parallel'
                    ? `This will immediately market-sell ALL holdings across ${Object.keys(parallelSessions).length} sessions. Orders will continue running. This action cannot be undone.`
                    : "This will immediately market-sell all holdings in the current session. Orders will continue running. This action cannot be undone."}
                confirmText="Force Close"
                isDanger={true}
            />

            {/* Delete Session Modal (Option B: actions in panel) - supports group deletion */}
            <DeleteConfirmModal
                isOpen={isDeleteModalOpen}
                onClose={() => setIsDeleteModalOpen(false)}
                onConfirm={handleDeleteSession}
                sessions={activeSessionGroup?.sessions}
                getSymbolName={getSymbolName}
                isDeleting={isDeleting}
            />

            {/* Custom Alert Modal (replaces system alert()) */}
            <AlertModal
                isOpen={alertModal.isOpen}
                onClose={() => setAlertModal({ ...alertModal, isOpen: false })}
                title={alertModal.title}
                message={alertModal.message}
                type={alertModal.type}
            />

            {/* 1. TOP ROW: Live Operation Controls (Combined & Full Width) */}
            <div className={`lg:col-span-3 bg-white/5 border border-white/10 rounded-xl overflow-hidden ${status === 'RUNNING' ? 'glow-pulse-green' : ''}`}>
                    <div className="bg-white/5 px-4 py-3 border-b border-white/10 flex items-center justify-between">
                        <div className="flex items-center gap-3">
                            <h3 className="font-bold text-gray-200 text-sm flex items-center gap-2">
                                <Radio size={14} className={status === 'RUNNING' ? 'text-green-400 animate-pulse' : 'text-gray-400'} /> Live Operation
                            </h3>
                            {/* Selected Session Group Info Badge */}
                            {selectedSessionInfo && (
                                <div className="flex items-center gap-2">
                                    <span className="text-gray-500">|</span>
                                    <span className="text-sm font-medium text-indigo-400">
                                        {selectedSessionInfo.profileName || selectedSessionInfo.strategyName}
                                    </span>
                                    {selectedSessionInfo.sessionCount > 1 && (
                                        <span className="text-[9px] px-1 py-0.5 rounded bg-indigo-500/20 text-indigo-300">
                                            x{selectedSessionInfo.sessionCount}
                                        </span>
                                    )}
                                    <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold uppercase ${
                                        selectedSessionInfo.isPaper
                                            ? 'bg-amber-500/20 text-amber-400'
                                            : 'bg-red-500/20 text-red-400'
                                    }`}>
                                        {selectedSessionInfo.isPaper ? 'Paper' : 'Real'}
                                    </span>
                                    <span className="text-[10px] text-gray-500">{selectedSessionInfo.accountName}</span>
                                </div>
                            )}
                        </div>
                        <div className="flex items-center gap-2">
                            <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${executionMode === 'parallel' ? 'bg-blue-500/20 text-blue-400 border border-blue-500/30' : 'bg-gray-500/20 text-gray-400 border border-gray-500/30'}`}>
                                {executionMode === 'parallel' ? 'Parallel' : 'Exclusive'}
                            </span>
                            {executionMode === 'parallel' && Object.keys(parallelSessions).length > 0 && (
                                <span className="text-xs text-blue-400">
                                    ({Object.keys(parallelSessions).length} ranks active)
                                </span>
                            )}
                        </div>
                    </div>
                <div className="px-4 py-4">

                    {/* Section 1: Dashboard Stats */}
                    {(() => {
                        // Capital = Trading Capital input (same for exclusive/parallel)
                        const totalCapital = parseFloat(inputCapital) || 0;

                        // Only include sessions tracked in parallelSessions (currently active)
                        const activeSessionIds = new Set(Object.values(parallelSessions));
                        const allSessions = liveData?._parallel_sessions || (liveData ? [liveData] : []);
                        const runningSessions = allSessions.filter(s =>
                            s?.is_running && activeSessionIds.has(s?.session_id)
                        );
                        const usedCapital = runningSessions.reduce((sum, s) => {
                            const st = s?.strategy_state || {};
                            return sum + ((st.total_quantity || 0) * (st.average_price || 0));
                        }, 0);
                        const availableCapital = totalCapital - usedCapital;
                        const totalPnl = runningSessions.reduce((sum, s) => sum + (s?.pnl || 0), 0);
                        const isPaper = runningSessions.some(s => s?.is_paper);
                        return (
                    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-5 gap-4 mb-6">
                        {/* Status */}
                        <div className="bg-black/20 border border-white/5 rounded-lg p-4 flex flex-col justify-center items-center">
                            <span className="text-gray-400 text-xs font-bold tracking-wider uppercase mb-1">Session Status</span>
                            <span className={`px-4 py-1 rounded-full text-sm font-bold border tracking-wide ${getStatusColor()}`}>
                                {status}
                            </span>
                        </div>

                        {/* PnL */}
                        <div className="bg-black/20 border border-white/5 rounded-lg p-4 flex flex-col justify-center items-center">
                            <span className="text-gray-400 text-xs font-bold tracking-wider uppercase mb-1">
                                Unrealized PnL{isPaper ? ' (Paper)' : ''}
                            </span>
                            {runningSessions.length > 0 ? (
                                isPaper ? (
                                    <span className="text-gray-600 text-sm">Paper Mode</span>
                                ) : (
                                    <div className={`text-2xl font-mono tracking-tight ${totalPnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                        {totalPnl > 0 ? '+' : ''}{totalPnl?.toLocaleString()}
                                    </div>
                                )
                            ) : (
                                <span className="text-gray-600 text-sm">-</span>
                            )}
                        </div>

                        {/* Total Capital */}
                        <div className="bg-black/20 border border-white/5 rounded-lg p-4 flex flex-col justify-center items-center">
                            <span className="text-gray-400 text-xs font-bold tracking-wider uppercase mb-1">Capital</span>
                            <div className="text-xl font-mono text-purple-400 tracking-tight">
                                {totalCapital > 0 ? `${totalCapital.toLocaleString()}` : '0'}
                            </div>
                        </div>

                        {/* Used Capital */}
                        <div className="bg-black/20 border border-white/5 rounded-lg p-4 flex flex-col justify-center items-center">
                            <span className="text-gray-400 text-xs font-bold tracking-wider uppercase mb-1"
                                title={runningSessions.map(s => {
                                    const st = s?.strategy_state || {};
                                    return `${s?.symbol}: ${st.total_quantity || 0}주`;
                                }).join('\n')}
                            >Used</span>
                            <div className="text-xl font-mono text-orange-400 tracking-tight">
                                {usedCapital > 0 ? `${Math.round(usedCapital).toLocaleString()}` : '0'}
                            </div>
                            {totalCapital > 0 && usedCapital > 0 && (
                                <div className="text-[10px] text-gray-500 mt-1">
                                    {((usedCapital / totalCapital) * 100).toFixed(1)}%
                                </div>
                            )}
                        </div>

                        {/* Available Capital */}
                        <div className="bg-black/20 border border-white/5 rounded-lg p-4 flex flex-col justify-center items-center">
                            <span className="text-gray-400 text-xs font-bold tracking-wider uppercase mb-1">Available</span>
                            <div className={`text-xl font-mono tracking-tight ${availableCapital >= 0 ? 'text-blue-400' : 'text-red-400'}`}>
                                {Math.round(availableCapital).toLocaleString()}
                            </div>
                            {totalCapital > 0 && (
                                <div className="text-[10px] text-gray-500 mt-1">
                                    {((availableCapital / totalCapital) * 100).toFixed(1)}%
                                </div>
                            )}
                        </div>
                    </div>
                        );
                    })()}


                    {/* Section 2: Configuration & Controls */}
                    <div className="w-full bg-black/40 border border-white/5 rounded-xl p-5 mb-6">
                        <div className="flex flex-col md:flex-row items-center gap-6">
                            {/* Capital Input - Only editable when NOT running */}
                            <div className="flex-1 w-full">
                                <label className="block text-gray-400 text-[10px] font-bold tracking-wider uppercase mb-2">
                                    Trading Capital (KRW)
                                </label>
                                <div className="relative group">
                                    <input
                                        type="number"
                                        disabled={status === 'RUNNING' || status === 'STARTING'}
                                        value={inputCapital}
                                        onChange={(e) => {
                                            const newValue = e.target.value;
                                            setInputCapital(newValue);
                                            // Notify parent to persist the change
                                            if (onCapitalChange) {
                                                onCapitalChange(parseFloat(newValue) || 0);
                                            }
                                        }}
                                        className="w-full bg-black/60 border border-white/10 rounded-lg px-4 py-3 text-white font-mono text-xl outline-none focus:border-green-500/50 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                                        placeholder="Enter amount..."
                                    />
                                    <div className="absolute right-4 top-1/2 -translate-y-1/2 text-gray-500 font-bold pointer-events-none">KRW</div>
                                </div>
                                {availableBalance !== null && inputCapital > availableBalance && status === 'IDLE' && (
                                    <p className="text-yellow-500/80 text-[10px] mt-2 flex items-center gap-1 animate-pulse">
                                        <AlertTriangle size={10} /> Insufficient account funds
                                    </p>
                                )}
                            </div>

                            {/* Account Selector (Phase 5: Multi-Account Support) */}
                            <div className="w-full md:w-56">
                                <label className="block text-gray-400 text-[10px] font-bold tracking-wider uppercase mb-2">
                                    Trading Account
                                </label>
                                <select
                                    value={selectedAccountId || ''}
                                    onChange={(e) => setSelectedAccountId(e.target.value ? parseInt(e.target.value) : null)}
                                    disabled={status === 'RUNNING' || status === 'STARTING'}
                                    className="w-full bg-black/60 border border-white/10 rounded-lg px-3 py-3 text-white text-sm font-bold outline-none focus:border-blue-500/50 transition-all disabled:opacity-50 disabled:cursor-not-allowed appearance-none cursor-pointer"
                                >
                                    {accounts.filter(acc => !acc.is_disabled).map(acc => (
                                        <option key={acc.id} value={acc.id}>
                                            {acc.account_name} ({acc.environment === 'real' ? '실거래' : acc.environment === 'virtual' ? '모의' : '페이퍼'})
                                                                                    </option>
                                    ))}
                                </select>
                                <p className="text-gray-500 text-[9px] mt-1.5">
                                    {accounts.find(a => a.id === selectedAccountId)?.account_number?.slice(-4)
                                        ? `계좌번호: ****${accounts.find(a => a.id === selectedAccountId)?.account_number?.slice(-4)}`
                                        : '계좌를 선택하세요'}
                                </p>
                            </div>

                            {/* Paper/Real Mode Toggle (Phase 5) */}
                            <div className="w-full md:w-40">
                                <label className="block text-gray-400 text-[10px] font-bold tracking-wider uppercase mb-2">
                                    Trading Mode
                                </label>
                                <button
                                    onClick={() => {
                                        if (status !== 'RUNNING' && status !== 'STARTING') {
                                            if (isPaperMode) {
                                                // Switching to Real - check balance first
                                                if (availableBalance !== null && inputCapital > availableBalance) {
                                                    showAlert(
                                                        `실제 계좌 잔고가 부족합니다.\n\n설정 금액: ${Number(inputCapital).toLocaleString()}원\n계좌 잔고: ${Number(availableBalance).toLocaleString()}원\n\n리얼 모드로 전환하려면 설정 금액을 줄이거나 계좌에 입금해주세요.`,
                                                        'warning',
                                                        '잔고 부족'
                                                    );
                                                    return;
                                                }
                                                // Show confirmation for Paper → Real
                                                setModeSwitchConfirm({ isOpen: true, toReal: true, isRunningSession: false });
                                            } else {
                                                // Show confirmation for Real → Paper
                                                setModeSwitchConfirm({ isOpen: true, toReal: false, isRunningSession: false });
                                            }
                                        }
                                    }}
                                    disabled={status === 'RUNNING' || status === 'STARTING'}
                                    className={`w-full h-[46px] flex items-center justify-center gap-2 text-sm font-bold rounded-lg border transition-all disabled:opacity-50 disabled:cursor-not-allowed ${
                                        isPaperMode
                                            ? 'bg-green-600/20 border-green-500 text-green-400 hover:bg-green-600/30'
                                            : 'bg-red-900/40 border-red-500 text-red-400 hover:bg-red-900/60'
                                    }`}
                                >
                                    {isPaperMode ? (
                                        <><Shield size={14} /> Paper</>
                                    ) : (
                                        <><ShieldOff size={14} /> Real</>
                                    )}
                                </button>
                                <p className="text-gray-500 text-[9px] mt-1.5">
                                    {isPaperMode ? '시뮬레이션 모드' : '실제 주문 실행'}
                                </p>
                            </div>
                        </div>

                        {/* Parallel Mode: Per-Rank Capital Allocation - Slider UI */}
                        {executionMode === 'parallel' && configList.filter(c => c.is_active).length > 1 && (
                            <div className="mt-4 p-3 bg-blue-900/10 border border-blue-500/20 rounded-lg">
                                <div className="flex items-center justify-between mb-3">
                                    <span className="text-gray-400 text-[10px] font-bold tracking-wider uppercase">Capital Allocation per Rank</span>
                                    <button
                                        onClick={() => {
                                            const activeIndices = configList.map((c, i) => c.is_active ? i : -1).filter(i => i >= 0);
                                            const eq = Math.floor(100 / activeIndices.length);
                                            const rem = 100 - (eq * activeIndices.length);
                                            const w = {};
                                            activeIndices.forEach((idx, pos) => { w[idx] = eq + (pos === 0 ? rem : 0); });
                                            setRankWeights(w);
                                        }}
                                        disabled={status === 'RUNNING' || status === 'STARTING'}
                                        className="text-[9px] text-blue-400 hover:text-blue-300 disabled:opacity-40 disabled:cursor-not-allowed"
                                    >
                                        Reset Equal
                                    </button>
                                </div>
                                <div className="space-y-3">
                                    {(() => {
                                        const activeIndices = configList.map((c, i) => c.is_active ? i : -1).filter(i => i >= 0);

                                        // Slider change handler - redistributes remaining to other ranks
                                        const handleSliderChange = (changedIdx, newValue) => {
                                            const otherIndices = activeIndices.filter(i => i !== changedIdx);
                                            const remaining = 100 - newValue;

                                            // Calculate current total of other ranks
                                            const otherTotal = otherIndices.reduce((sum, i) => sum + (rankWeights[i] || 0), 0);

                                            const newWeights = { ...rankWeights, [changedIdx]: newValue };

                                            if (otherTotal === 0) {
                                                // If others are all 0, distribute equally
                                                const each = Math.floor(remaining / otherIndices.length);
                                                const extra = remaining - (each * otherIndices.length);
                                                otherIndices.forEach((i, pos) => {
                                                    newWeights[i] = each + (pos === 0 ? extra : 0);
                                                });
                                            } else {
                                                // Proportional redistribution
                                                let distributed = 0;
                                                otherIndices.forEach((i, pos) => {
                                                    const ratio = (rankWeights[i] || 0) / otherTotal;
                                                    if (pos === otherIndices.length - 1) {
                                                        // Last one gets remainder to ensure exactly 100%
                                                        newWeights[i] = remaining - distributed;
                                                    } else {
                                                        const share = Math.round(remaining * ratio);
                                                        newWeights[i] = share;
                                                        distributed += share;
                                                    }
                                                });
                                            }

                                            setRankWeights(newWeights);
                                        };

                                        return configList.map((cfg, idx) => {
                                            if (!cfg.is_active) return null;
                                            const weight = rankWeights[idx] || 0;
                                            const capital = Math.floor((parseFloat(inputCapital) || 0) * weight / 100);
                                            const isDisabled = status === 'RUNNING' || status === 'STARTING';

                                            return (
                                                <div key={idx} className="flex items-center gap-3">
                                                    <span className="text-gray-400 text-[10px] w-24 truncate font-mono">
                                                        R{idx + 1} {cfg.symbol?.slice(0, 6)}
                                                    </span>
                                                    <div className="flex-1 relative">
                                                        <input
                                                            type="range"
                                                            min={0}
                                                            max={100}
                                                            value={weight}
                                                            onChange={(e) => handleSliderChange(idx, parseInt(e.target.value))}
                                                            disabled={isDisabled}
                                                            className="w-full h-2 bg-white/10 rounded-full appearance-none cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed
                                                                [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:h-4
                                                                [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-blue-500
                                                                [&::-webkit-slider-thumb]:hover:bg-blue-400 [&::-webkit-slider-thumb]:cursor-pointer
                                                                [&::-webkit-slider-thumb]:shadow-lg [&::-webkit-slider-thumb]:shadow-blue-500/30
                                                                [&::-moz-range-thumb]:w-4 [&::-moz-range-thumb]:h-4 [&::-moz-range-thumb]:rounded-full
                                                                [&::-moz-range-thumb]:bg-blue-500 [&::-moz-range-thumb]:border-0 [&::-moz-range-thumb]:cursor-pointer"
                                                            style={{
                                                                background: `linear-gradient(to right, rgb(59, 130, 246) 0%, rgb(59, 130, 246) ${weight}%, rgba(255,255,255,0.1) ${weight}%, rgba(255,255,255,0.1) 100%)`
                                                            }}
                                                        />
                                                    </div>
                                                    <span className="text-white text-xs font-mono w-10 text-right font-bold">
                                                        {weight}%
                                                    </span>
                                                    <span className="text-gray-500 text-[10px] font-mono w-20 text-right">
                                                        ₩{capital.toLocaleString()}
                                                    </span>
                                                </div>
                                            );
                                        });
                                    })()}
                                </div>
                                <div className="flex items-center justify-between mt-3 pt-2 border-t border-white/5 text-[10px] text-green-400">
                                    <span>Total: 100%</span>
                                    <span className="text-gray-500">자동 조정됨</span>
                                </div>
                            </div>
                        )}

                        {/* Apply/Discard Changes - Shows when settings changed */}
                        {hasUnsavedChanges && (
                            <div className="mt-4 pt-4 border-t border-yellow-500/30">
                                <div className="flex items-center gap-3">
                                    <div className="flex-1 text-yellow-400 text-xs">
                                        <span className="animate-pulse">●</span> 변경사항이 있습니다
                                    </div>
                                    <button
                                        onClick={handleDiscardChanges}
                                        disabled={isApplying}
                                        className="h-10 px-4 flex items-center justify-center gap-2 bg-gray-700 hover:bg-gray-600 text-gray-200 text-sm font-bold rounded-lg transition-all disabled:opacity-50"
                                    >
                                        <X size={16} />
                                        Discard
                                    </button>
                                    <button
                                        onClick={handleApplySettings}
                                        disabled={isApplying}
                                        className="h-10 px-6 flex items-center justify-center gap-2 bg-gradient-to-r from-yellow-600 to-amber-500 hover:from-yellow-500 hover:to-amber-400 text-black text-sm font-bold tracking-wide rounded-lg transition-all disabled:opacity-50 shadow-lg shadow-yellow-900/30"
                                    >
                                        {isApplying ? (
                                            <>
                                                <div className="w-4 h-4 border-2 border-black/30 border-t-black rounded-full animate-spin" />
                                                저장 중...
                                            </>
                                        ) : applyStatus === 'success' ? (
                                            <>
                                                <Check size={16} />
                                                저장 완료!
                                            </>
                                        ) : (
                                            <>
                                                <Check size={16} />
                                                Apply
                                            </>
                                        )}
                                    </button>
                                </div>
                            </div>
                        )}

                        {/* Session Action Buttons - Full Width Row */}
                        <div className="mt-4 pt-4 border-t border-white/10">
                            {status !== 'RUNNING' ? (
                                <>
                                    {/* Session action buttons for selected STOPPED/ERROR session */}
                                    {activeSessionGroup?.sessions?.[0] &&
                                     STATUS_CONFIG[activeSessionGroup.sessions[0].status]?.canResume ? (
                                        <div className="grid grid-cols-2 gap-3">
                                            <button
                                                onClick={handleResumeSession}
                                                disabled={isResuming || hasUnsavedChanges}
                                                className="h-14 flex items-center justify-center gap-3 bg-gradient-to-r from-blue-600 to-blue-500 hover:from-blue-500 hover:to-blue-400 text-white text-base font-bold tracking-wide rounded-xl transition-all disabled:opacity-50 shadow-lg shadow-blue-900/30"
                                            >
                                                {isResuming ? (
                                                    <>
                                                        <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                                                        재시작 중...
                                                    </>
                                                ) : hasUnsavedChanges ? (
                                                    <>
                                                        <AlertTriangle size={20} />
                                                        먼저 Apply 하세요
                                                    </>
                                                ) : (
                                                    <>
                                                        <RotateCcw size={20} />
                                                        세션 재시작 (RESUME)
                                                    </>
                                                )}
                                            </button>
                                            <button
                                                onClick={() => setIsDeleteModalOpen(true)}
                                                disabled={isDeleting}
                                                className="h-14 flex items-center justify-center gap-3 bg-red-600/20 hover:bg-red-600/30 text-red-400 text-base font-bold tracking-wide rounded-xl transition-all border-2 border-red-500/50 disabled:opacity-50"
                                            >
                                                <Trash2 size={20} />
                                                세션 삭제 (DELETE)
                                            </button>
                                        </div>
                                    ) : (
                                        <div className="h-14 flex items-center justify-center text-gray-500 text-sm border-2 border-dashed border-gray-700 rounded-xl bg-black/20">
                                            세션을 선택하거나 새 세션을 만드세요
                                        </div>
                                    )}
                                </>
                            ) : (
                                <div className="grid grid-cols-2 gap-3">
                                    <button
                                        onClick={() => {
                                            if (liveData?.is_paper !== false) { // Moving from Paper to Real
                                                if (availableBalance !== null && inputCapital > availableBalance) {
                                                    showAlert(
                                                        `실제 계좌 잔고가 부족하여 리얼 모드를 활성화할 수 없습니다.\n\n설정 금액: ${Number(inputCapital).toLocaleString()}원\n계좌 잔고: ${Number(availableBalance).toLocaleString()}원\n\n리얼 모드로 전환하려면 설정 금액을 줄이거나 계좌에 입금해주세요.`,
                                                        'warning',
                                                        '잔고 부족'
                                                    );
                                                    return;
                                                }
                                                // Show confirmation for Paper → Real (running session)
                                                setModeSwitchConfirm({ isOpen: true, toReal: true, isRunningSession: true });
                                            } else {
                                                // Show confirmation for Real → Paper (running session)
                                                setModeSwitchConfirm({ isOpen: true, toReal: false, isRunningSession: true });
                                            }
                                        }}
                                        className={`h-14 flex items-center justify-center gap-3 text-base font-bold tracking-wide rounded-xl border-2 transition-all ${liveData?.is_paper === false
                                            ? 'bg-red-900/40 border-red-500 text-red-400 hover:bg-red-900/60'
                                            : (availableBalance !== null && inputCapital > availableBalance)
                                                ? 'bg-gray-800 border-gray-700 text-gray-500 cursor-not-allowed opacity-50'
                                                : 'bg-green-600/20 border-green-500 text-green-400 hover:bg-green-600/30'
                                            }`}
                                    >
                                        {liveData?.is_paper === false ? (
                                            <><ShieldOff size={20} /> 리얼 모드 (REAL MODE)</>
                                        ) : (
                                            <><Shield size={20} /> 페이퍼 모드 (PAPER MODE)</>
                                        )}
                                    </button>

                                    <button
                                        onClick={async () => {
                                            try {
                                                // Only check positions for the selected session group
                                                const groupSessionIds = activeSessionGroup?.sessions?.map(s => s.session_id) || [];
                                                const posCheck = await checkLivePosition(groupSessionIds.length > 0 ? groupSessionIds : null);
                                                if (posCheck.has_position) {
                                                    setPositionWarningMessage(`현재 세션 포지션을 보유 중이기 때문에 종료할 수 없습니다.\n(${posCheck.detail})`);
                                                    setIsPositionWarningOpen(true);
                                                } else {
                                                    setIsStopModalOpen(true);
                                                }
                                            } catch (err) {
                                                console.error('Position check failed:', err);
                                                setIsStopModalOpen(true);
                                            }
                                        }}
                                        className="h-14 flex items-center justify-center gap-3 bg-gray-700 hover:bg-gray-600 text-white text-base font-bold tracking-wide rounded-xl transition-all border-2 border-gray-600 shadow-lg"
                                    >
                                        <Square size={20} />
                                        세션 중지 (STOP)
                                    </button>
                                </div>
                            )}
                        </div>

                        {/* Over-allocation Warning & Status */}
                        {availableBalance !== null && inputCapital > availableBalance && (
                            <div className="mt-4 p-3 bg-red-900/20 border border-red-500/50 rounded-lg flex items-center gap-3 animate-pulse">
                                <AlertTriangle className="text-red-500" size={20} />
                                <div className="flex-1">
                                    <p className="text-red-400 text-xs font-bold uppercase tracking-wider">CRITICAL: Insufficient Funds</p>
                                    <p className="text-red-200/70 text-[10px]">Your target capital exceeds available account cash. **Paper Mode forced.** Real trading is disabled to protect against margin errors.</p>
                                </div>
                            </div>
                        )}

                        {/* Force Close & Pause Orders - Independent row */}
                        {status === 'RUNNING' && (
                            <div className="grid grid-cols-2 gap-2 mt-4">
                                <button
                                    className={`h-12 flex items-center justify-center gap-2 text-xs font-bold tracking-wide rounded-lg border transition-all ${
                                        liveData?.orders_enabled === false
                                            ? 'bg-yellow-900/40 border-yellow-500/50 text-yellow-300 hover:bg-yellow-800/60'
                                            : 'bg-gray-700/40 border-gray-500/50 text-gray-300 hover:bg-gray-600/60'
                                    }`}
                                    onClick={handleToggleOrders}
                                >
                                    {liveData?.orders_enabled === false ? (
                                        <><Play size={14} /> RESUME ORDERS</>
                                    ) : (
                                        <><Pause size={14} /> PAUSE ORDERS</>
                                    )}
                                </button>
                                <button
                                    className="h-12 flex items-center justify-center gap-2 bg-red-900/40 hover:bg-red-600 text-red-100 border border-red-500/50 rounded-lg text-xs font-bold tracking-wide transition-all"
                                    onClick={() => setIsLiquidateModalOpen(true)}
                                >
                                    <AlertTriangle size={14} />
                                    FORCE CLOSE
                                </button>
                            </div>
                        )}
                    </div>
                </div>

                {/* Error Display */}
                {error && (
                    <div className="mt-6 p-3 bg-red-500/10 border border-red-500/20 rounded text-red-400 text-xs break-words animate-fade-in">
                        <div className="flex items-center gap-2 font-bold mb-1">
                            <AlertTriangle size={12} /> Error Details
                        </div>
                        {error}
                    </div>
                )}
            </div>

            {/* Unified Session Cards (Row 2) - Full Width */}
            {configList?.length > 0 && (
                <div className="lg:col-span-3">
                    <UnifiedSessionCards
                        parallelSessions={parallelSessions}
                        sessionDataList={liveData?._parallel_sessions || []}
                        configList={configList}
                        savedSymbols={savedSymbols}
                        currentRankIndex={currentRankIndex}
                        onRankSelect={(idx) => onRankChange(idx)}
                        strategyName={strategyName}
                        executionMode={executionMode}
                        strategyState={strategyState}
                        liveData={liveData}
                        accumulatedStats={accumulatedStats}
                    />
                </div>
            )}

            {/* 3. BOTTOM ROW: Chart Area (Real-time Tick Chart) - Full Width */}
            <div className="lg:col-span-3 bg-white/5 border border-white/10 rounded-xl overflow-hidden flex flex-col min-h-[400px]">
                <div className="bg-white/5 px-4 py-3 border-b border-white/10 flex items-center justify-between">
                    <h3 className="font-bold text-gray-200 text-sm flex items-center gap-2">
                        <BarChart3 size={14} className="text-gray-400" />
                        Real-time Ticks {strategyConfig.symbol
                            ? `(${savedSymbols.find(s => s.code === strategyConfig.symbol)?.name || strategyConfig.symbol})`
                            : ''}
                        {status === 'RUNNING' && <span className="ml-1 w-2 h-2 rounded-full bg-green-500 animate-pulse" />}
                    </h3>
                    {/* WebSocket Connection Status Indicator */}
                    <div className={`flex items-center gap-1.5 px-2 py-1 rounded-full text-xs font-medium ${
                        wsConnected
                            ? 'bg-green-500/20 text-green-400 border border-green-500/30'
                            : 'bg-red-500/20 text-red-400 border border-red-500/30'
                    }`}>
                        {wsConnected ? (
                            <>
                                <Wifi size={12} />
                                <span>Connected</span>
                            </>
                        ) : (
                            <>
                                <WifiOff size={12} />
                                <span>Disconnected</span>
                            </>
                        )}
                    </div>
                </div>

                <div className="flex-1 p-4 relative min-h-[350px] flex flex-col">
                    {/* Empty State Overlay */}
                    {tickData.length === 0 && (
                        <div className="absolute inset-0 flex items-center justify-center pointer-events-none z-10">
                            <div className="text-center text-gray-500">
                                <Activity className="w-10 h-10 mx-auto mb-2 opacity-50 animate-pulse" />
                                <p>Waiting for market data...</p>
                                <p className="text-xs mt-1">Market might be closed or history fetch failed.</p>
                            </div>
                        </div>
                    )}

                    <div className="flex-1 w-full h-full min-h-[350px] relative">
                        <VisualBacktestChart
                            data={realTimeCandles}
                            trades={[]} // We can pass real trades here if needed later
                            showOnlyPnl={false}
                            priceScaleOptions={{
                                autoScale: true,
                                scaleMargins: {
                                    top: 0.1,
                                    bottom: 0.1,
                                },
                            }}
                            yAxisFormatter={(price) => price.toLocaleString()}
                            selectedInterval={selectedInterval}
                            onIntervalChange={handleIntervalChange}
                            priceLines={(() => {
                                const lines = [];
                                const avgPrice = strategyState?.average_price || 0;
                                const targetPrice = strategyState?.target_price || 0;
                                if (avgPrice > 0) {
                                    lines.push({
                                        price: avgPrice,
                                        color: '#3b82f6', // blue
                                        title: '평균단가',
                                        lineWidth: 1,
                                        lineStyle: 2, // dashed
                                    });
                                    if (targetPrice > 0) {
                                        lines.push({
                                            price: targetPrice,
                                            color: '#22c55e', // green
                                            title: '트레일시작',
                                            lineWidth: 1,
                                            lineStyle: 2, // dashed
                                        });
                                    }
                                }
                                return lines;
                            })()}
                            customControls={
                                configList && configList.length > 0 && onRankChange ? (
                                    <div className="flex items-center gap-1 mr-2">
                                        {executionMode === 'parallel' && status === 'RUNNING' && (
                                            <span className="text-[9px] text-blue-400 mr-1">Chart:</span>
                                        )}
                                        <select
                                            value={currentRankIndex}
                                            onChange={(e) => onRankChange(parseInt(e.target.value))}
                                            className="bg-gray-900 border border-gray-600 rounded text-[10px] px-2 py-1 text-gray-300 outline-none focus:border-blue-500 hover:bg-gray-800 transition-colors"
                                        >
                                            {configList.map((cfg, idx) => {
                                                if (!cfg.is_active) return null;
                                                const symbolMatch = savedSymbols.find(s => s.code === cfg.symbol);
                                                const name = symbolMatch ? symbolMatch.name : cfg.symbol;
                                                const isRunning = executionMode === 'parallel' && parallelSessions[idx];
                                                return (
                                                    <option key={idx} value={idx}>
                                                        Rank {idx + 1}: {name}{isRunning ? ' ●' : ''}
                                                    </option>
                                                );
                                            })}
                                        </select>
                                    </div>
                                ) : null
                            }
                        />
                    </div>
                </div>
            </div>

            {/* 4. TRANSACTION HISTORY SECTION (2-Step Architecture) */}
            <div className="lg:col-span-3 mt-4">
                {!showHistoryView ? (
                    <div className="space-y-4">
                        {/* All Sessions Summary Panel - Separated by Paper/Real */}
                        {(() => {
                            // Aggregate stats separately for Paper and Real (backtest-compatible format)
                            const stats = {
                                paper: {
                                    cycles: 0, pnl: 0, wins: 0,
                                    // Backtest-compatible (% based)
                                    totalReturn: 0, totalEntryCost: 0,
                                    grossProfit: 0, grossLoss: 0,
                                    pnlPcts: [],  // For sharpe calculation
                                    maxDrawdown: 0,
                                    recent10Wins: 0, recent10Total: 0,
                                    // KRW based
                                    maxPnl: null, minPnl: null,
                                    // Holding time
                                    totalHoldTime: 0, holdCount: 0, maxHold: null, minHold: null,
                                    // Activity
                                    activityRates: [], activityWeights: [],
                                },
                                real: {
                                    cycles: 0, pnl: 0, wins: 0,
                                    totalReturn: 0, totalEntryCost: 0,
                                    grossProfit: 0, grossLoss: 0,
                                    pnlPcts: [],
                                    maxDrawdown: 0,
                                    recent10Wins: 0, recent10Total: 0,
                                    maxPnl: null, minPnl: null,
                                    totalHoldTime: 0, holdCount: 0, maxHold: null, minHold: null,
                                    activityRates: [], activityWeights: [],
                                }
                            };

                            Object.values(accumulatedStats).forEach(symbolStats => {
                                ['paper', 'real'].forEach(mode => {
                                    const s = symbolStats?.[mode];
                                    if (!s || !s.cycles && !s.total_trades) return;
                                    const st = stats[mode];
                                    const cycleCount = s.total_trades || s.cycles || 0;
                                    st.cycles += cycleCount;
                                    st.pnl += s.realized_pnl || 0;
                                    st.wins += Math.round((s.win_rate || 0) * cycleCount / 100);

                                    // Backtest-compatible aggregation
                                    if (s.total_return != null) {
                                        // Weight by cycle count for averaging
                                        st.totalReturn += (s.total_return || 0) * cycleCount;
                                    }
                                    // Gross profit/loss (approximate from avg_pnl * cycles)
                                    const avgPnlKrw = s.avg_pnl_krw || s.avg_pnl || 0;
                                    if (avgPnlKrw > 0) st.grossProfit += avgPnlKrw * cycleCount;
                                    else st.grossLoss += Math.abs(avgPnlKrw) * cycleCount;

                                    // Sharpe requires per-cycle PnL% which we don't have aggregated
                                    // Use weighted average of sharpe ratios
                                    if (s.sharpe_ratio != null) st.pnlPcts.push({ val: s.sharpe_ratio, weight: cycleCount });

                                    // Max drawdown (take worst)
                                    if (s.max_drawdown != null && s.max_drawdown > st.maxDrawdown) {
                                        st.maxDrawdown = s.max_drawdown;
                                    }

                                    // Recent 10 win rate
                                    if (s.recent_10_win_rate != null) {
                                        const r10count = Math.min(cycleCount, 10);
                                        st.recent10Wins += Math.round((s.recent_10_win_rate || 0) * r10count / 100);
                                        st.recent10Total += r10count;
                                    }

                                    // KRW based max/min
                                    const maxPnlVal = s.max_pnl_krw ?? s.max_pnl;
                                    const minPnlVal = s.min_pnl_krw ?? s.min_pnl;
                                    if (maxPnlVal != null) st.maxPnl = st.maxPnl == null ? maxPnlVal : Math.max(st.maxPnl, maxPnlVal);
                                    if (minPnlVal != null) st.minPnl = st.minPnl == null ? minPnlVal : Math.min(st.minPnl, minPnlVal);

                                    // Holding time aggregation (weighted average)
                                    if (s.avg_holding_time != null) {
                                        st.totalHoldTime += s.avg_holding_time * cycleCount;
                                        st.holdCount += cycleCount;
                                    }
                                    if (s.max_holding_time != null) st.maxHold = st.maxHold == null ? s.max_holding_time : Math.max(st.maxHold, s.max_holding_time);
                                    if (s.min_holding_time != null) st.minHold = st.minHold == null ? s.min_holding_time : Math.min(st.minHold, s.min_holding_time);

                                    // Activity rate (weighted average)
                                    if (s.activity_rate != null) {
                                        st.activityRates.push({ val: s.activity_rate, weight: cycleCount });
                                    }
                                });
                            });

                            const hasNoData = stats.paper.cycles === 0 && stats.real.cycles === 0;

                            const formatPnl = (v) => {
                                if (v == null) return '-';
                                const abs = Math.abs(v);
                                const str = abs >= 1000000 ? `${(abs / 1000000).toFixed(1)}M`
                                    : abs >= 1000 ? `${Math.round(abs / 1000)}K`
                                    : Math.round(abs).toLocaleString();
                                return (v >= 0 ? '+' : '-') + str;
                            };

                            // Format minutes to human-readable time (e.g., "2d 5h", "3h 30m", "45m")
                            const formatTime = (mins) => {
                                if (mins == null) return '-';
                                const m = Math.round(mins);
                                if (m >= 1440) { // >= 1 day
                                    const days = Math.floor(m / 1440);
                                    const hours = Math.floor((m % 1440) / 60);
                                    return hours > 0 ? `${days}d ${hours}h` : `${days}d`;
                                }
                                if (m >= 60) { // >= 1 hour
                                    const hours = Math.floor(m / 60);
                                    const remMins = m % 60;
                                    return remMins > 0 ? `${hours}h ${remMins}m` : `${hours}h`;
                                }
                                return `${m}m`;
                            };

                            const renderModeStats = (mode, st, colorClass, bgClass) => {
                                if (st.cycles === 0) return null;
                                const winRate = st.cycles > 0 ? (st.wins / st.cycles) * 100 : 0;
                                const avgPnl = st.cycles > 0 ? st.pnl / st.cycles : 0;
                                const avgHold = st.holdCount > 0 ? st.totalHoldTime / st.holdCount : null;

                                // Backtest-compatible metrics
                                const totalReturnPct = st.cycles > 0 ? st.totalReturn / st.cycles : 0;
                                const profitFactor = st.grossLoss > 0 ? st.grossProfit / st.grossLoss : (st.grossProfit > 0 ? 99.99 : 0);
                                const sharpeRatio = st.pnlPcts.length > 0
                                    ? st.pnlPcts.reduce((acc, p) => acc + p.val * p.weight, 0) / st.pnlPcts.reduce((acc, p) => acc + p.weight, 0)
                                    : 0;
                                const recent10WinRate = st.recent10Total > 0 ? (st.recent10Wins / st.recent10Total) * 100 : winRate;
                                const activityRate = st.activityRates.length > 0
                                    ? st.activityRates.reduce((acc, a) => acc + a.val * a.weight, 0) / st.activityRates.reduce((acc, a) => acc + a.weight, 0)
                                    : 0;

                                return (
                                    <div className={`${bgClass} rounded-lg p-3`}>
                                        <div className="flex items-center gap-2 mb-2">
                                            <span className={`text-xs font-bold px-2 py-0.5 rounded ${colorClass}`}>
                                                {mode === 'paper' ? 'PAPER' : 'REAL'}
                                            </span>
                                            <span className="text-xs text-gray-500">{st.cycles} cycles</span>
                                        </div>
                                        {/* Row 1: Core Stats (backtest-compatible) */}
                                        <div className="grid grid-cols-6 gap-2 text-center mb-2">
                                            <div>
                                                <div className="text-[10px] text-gray-500 uppercase">Return</div>
                                                <div className={`text-sm font-mono font-bold ${totalReturnPct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                                    {totalReturnPct >= 0 ? '+' : ''}{totalReturnPct.toFixed(2)}%
                                                </div>
                                            </div>
                                            <div>
                                                <div className="text-[10px] text-gray-500 uppercase">Win Rate</div>
                                                <div className={`text-sm font-mono font-bold ${winRate >= 50 ? 'text-yellow-400' : 'text-yellow-600'}`}>
                                                    {winRate.toFixed(1)}%
                                                </div>
                                                <div className="text-[9px] text-gray-600">{st.wins}W/{st.cycles - st.wins}L</div>
                                            </div>
                                            <div>
                                                <div className="text-[10px] text-gray-500 uppercase">Recent 10</div>
                                                <div className={`text-sm font-mono ${recent10WinRate >= 50 ? 'text-yellow-400' : 'text-yellow-600'}`}>
                                                    {recent10WinRate.toFixed(1)}%
                                                </div>
                                            </div>
                                            <div>
                                                <div className="text-[10px] text-gray-500 uppercase">PF</div>
                                                <div className="text-sm font-mono text-white">
                                                    {profitFactor.toFixed(2)}
                                                </div>
                                            </div>
                                            <div>
                                                <div className="text-[10px] text-gray-500 uppercase">Sharpe</div>
                                                <div className="text-sm font-mono text-yellow-400">
                                                    {sharpeRatio.toFixed(2)}
                                                </div>
                                            </div>
                                            <div>
                                                <div className="text-[10px] text-gray-500 uppercase">Max DD</div>
                                                <div className="text-sm font-mono text-red-400">
                                                    {st.maxDrawdown > 0 ? `-${st.maxDrawdown.toFixed(1)}%` : '-'}
                                                </div>
                                            </div>
                                        </div>
                                        {/* Row 2: PnL & Holding (live-specific KRW values) */}
                                        <div className="grid grid-cols-4 gap-2 text-center pt-2 border-t border-white/5">
                                            <div>
                                                <div className="text-[10px] text-gray-500 uppercase">Total PnL</div>
                                                <div className={`text-sm font-mono font-bold ${st.pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                                    {formatPnl(st.pnl)}
                                                </div>
                                            </div>
                                            <div>
                                                <div className="text-[10px] text-gray-500 uppercase">Avg/Cycle</div>
                                                <div className={`text-sm font-mono ${avgPnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                                    {formatPnl(avgPnl)}
                                                </div>
                                            </div>
                                            <div>
                                                <div className="text-[10px] text-gray-500 uppercase">Max/Min</div>
                                                <div className="text-[11px] font-mono">
                                                    <span className="text-green-400">{formatPnl(st.maxPnl)}</span>
                                                    <span className="text-gray-600">/</span>
                                                    <span className="text-red-400">{formatPnl(st.minPnl)}</span>
                                                </div>
                                            </div>
                                            <div>
                                                <div className="text-[10px] text-gray-500 uppercase">Holding</div>
                                                <div className="text-sm font-mono text-gray-300">
                                                    {formatTime(avgHold)}
                                                </div>
                                                <div className="text-[9px] font-mono">
                                                    <span className="text-red-400">{formatTime(st.maxHold)}</span>
                                                    <span className="text-gray-600">/</span>
                                                    <span className="text-green-400">{formatTime(st.minHold)}</span>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                );
                            };

                            return (
                                <div className="bg-gradient-to-br from-indigo-500/5 to-purple-500/5 border border-indigo-500/20 rounded-xl p-4">
                                    <div className="flex items-center gap-2 mb-3">
                                        <History size={16} className="text-indigo-400" />
                                        <span className="text-sm font-bold text-gray-200">All Sessions Summary</span>
                                        <span className="text-xs text-gray-500">(Historical)</span>
                                    </div>
                                    {hasNoData ? (
                                        <div className="text-center py-4 text-gray-500 text-sm">
                                            No trading history yet
                                        </div>
                                    ) : (
                                        <div className="space-y-2">
                                            {renderModeStats('paper', stats.paper, 'bg-amber-500/20 text-amber-400', 'bg-amber-500/5 border border-amber-500/10')}
                                            {renderModeStats('real', stats.real, 'bg-red-500/20 text-red-400', 'bg-red-500/5 border border-red-500/10')}
                                        </div>
                                    )}
                                </div>
                            );
                        })()}

                        {/* Load Transaction History Button */}
                        <button
                            className="w-full py-4 border-2 border-dashed border-gray-700 hover:border-blue-500/50 hover:bg-blue-500/5 rounded-xl text-gray-400 hover:text-blue-400 font-bold transition-all flex flex-col items-center gap-2"
                            onClick={() => {
                                setShowHistoryView(true);
                                setIsHistoryLoading(true);
                                setSelectedCycle(null);
                                setCycleChartData(null);

                                const isPaperValue = historyMode === 'paper' ? true : historyMode === 'real' ? false : null;
                                getTradeHistoryList({ is_paper: isPaperValue, limit: 500 }).then(data => {
                                    setHistoryData(data);
                                    setIsHistoryLoading(false);
                                }).catch(err => {
                                    console.error("Failed to load trade list:", err);
                                    addLog('Error', `Trade list load failed: ${err?.response?.status || ''} ${err?.response?.data?.detail || err.message}`);
                                    setIsHistoryLoading(false);
                                });
                            }}
                        >
                            <List size={24} />
                            <span>Load Transaction History</span>
                            <span className="text-xs font-normal opacity-70">View trade cycles — click to load chart</span>
                            <div className="flex items-center gap-1 mt-1" onClick={e => e.stopPropagation()}>
                                {['paper', 'real', 'all'].map(m => (
                                    <button
                                        key={m}
                                        type="button"
                                        onClick={(e) => { e.stopPropagation(); setHistoryMode(m); }}
                                        className={`px-3 py-1 rounded text-[10px] font-bold uppercase tracking-wider border transition-all ${
                                            historyMode === m
                                                ? m === 'paper' ? 'bg-amber-500/20 text-amber-400 border-amber-500/40'
                                                : m === 'real' ? 'bg-red-500/20 text-red-400 border-red-500/40'
                                                : 'bg-blue-500/20 text-blue-400 border-blue-500/40'
                                                : 'bg-white/5 text-gray-500 border-white/10 hover:bg-white/10'
                                        }`}
                                    >
                                        {m === 'paper' ? 'Paper' : m === 'real' ? 'Real' : 'All'}
                                    </button>
                                ))}
                            </div>
                        </button>

                        {/* AI Periodic Analysis Section */}
                        {sessionId && (
                            <div className="mt-4">
                                {!showAiAnalysisPanel ? (
                                    <button
                                        className="w-full py-4 border-2 border-dashed border-cyan-700/50 hover:border-cyan-500/70 hover:bg-cyan-500/5 rounded-xl text-gray-400 hover:text-cyan-400 font-bold transition-all flex flex-col items-center gap-2"
                                        onClick={async () => {
                                            try {
                                                const [schedules, reportsData] = await Promise.all([
                                                    listAnalysisSchedules(),
                                                    listAllAnalysisReports(20)
                                                ]);
                                                if (schedules && schedules.length > 0) {
                                                    setAnalysisSchedule(schedules[0]);
                                                    setScheduleForm({
                                                        schedule_type: schedules[0].schedule_type || 'daily',
                                                        schedule_time: schedules[0].schedule_time || '15:40',
                                                        schedule_day: schedules[0].schedule_day || 1,
                                                        enabled: schedules[0].enabled !== false,
                                                    });
                                                }
                                                setAnalysisReports(reportsData?.reports || []);
                                            } catch (e) { console.error('Failed to load analysis data:', e); }
                                            setShowAiAnalysisPanel(true);
                                        }}
                                    >
                                        <BarChart3 size={24} />
                                        <span className="text-sm">AI Periodic Analysis</span>
                                        <span className="text-xs text-gray-500">Schedule AI-powered trading analysis with news search</span>
                                    </button>
                                ) : (
                                    <div className="bg-gradient-to-br from-cyan-500/5 to-transparent border border-cyan-500/20 rounded-xl overflow-hidden">
                                        {/* Header */}
                                        <div className="px-4 py-3 border-b border-cyan-500/20 flex items-center justify-between">
                                            <h3 className="font-bold text-cyan-400 text-sm flex items-center gap-2">
                                                <BarChart3 size={14} />
                                                AI Periodic Analysis
                                            </h3>
                                            <button onClick={() => { setShowAiAnalysisPanel(false); setSelectedReport(null); }} className="text-gray-500 hover:text-white">
                                                <X size={14} />
                                            </button>
                                        </div>

                                        <div className="p-4 space-y-4">
                                            {/* Schedule Configuration */}
                                            <div className="bg-white/5 rounded-lg p-3 space-y-3">
                                                <div className="text-xs font-bold text-gray-300 uppercase tracking-wider">Schedule Settings</div>

                                                {/* Type Selection */}
                                                <div className="flex items-center gap-2">
                                                    <span className="text-xs text-gray-400 w-12">Type</span>
                                                    <div className="flex gap-1">
                                                        {['daily', 'weekly', 'monthly'].map(t => (
                                                            <button
                                                                key={t}
                                                                onClick={() => setScheduleForm(f => ({ ...f, schedule_type: t }))}
                                                                className={`px-3 py-1 rounded text-xs font-medium transition-all ${
                                                                    scheduleForm.schedule_type === t
                                                                        ? 'bg-cyan-500/30 text-cyan-300 border border-cyan-500/50'
                                                                        : 'bg-white/5 text-gray-500 border border-white/10 hover:bg-white/10'
                                                                }`}
                                                            >
                                                                {scheduleForm.schedule_type === t && <Check size={10} className="inline mr-1" />}
                                                                {t === 'daily' ? 'Daily' : t === 'weekly' ? 'Weekly' : 'Monthly'}
                                                            </button>
                                                        ))}
                                                    </div>
                                                </div>

                                                {/* Time Selection */}
                                                <div className="flex items-center gap-2">
                                                    <span className="text-xs text-gray-400 w-12">Time</span>
                                                    <select
                                                        value={scheduleForm.schedule_time}
                                                        onChange={e => setScheduleForm(f => ({ ...f, schedule_time: e.target.value }))}
                                                        className="bg-white/5 border border-white/10 rounded px-2 py-1 text-xs text-white"
                                                    >
                                                        {Array.from({ length: 24 }, (_, h) => [`${String(h).padStart(2,'0')}:00`, `${String(h).padStart(2,'0')}:30`]).flat().map(t => (
                                                            <option key={t} value={t}>{t} KST</option>
                                                        ))}
                                                    </select>
                                                </div>

                                                {/* Day Selection (weekly/monthly) */}
                                                {scheduleForm.schedule_type === 'weekly' && (
                                                    <div className="flex items-center gap-2">
                                                        <span className="text-xs text-gray-400 w-12">Day</span>
                                                        <div className="flex gap-1">
                                                            {['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].map((d, i) => (
                                                                <button
                                                                    key={d}
                                                                    onClick={() => setScheduleForm(f => ({ ...f, schedule_day: i + 1 }))}
                                                                    className={`px-2 py-1 rounded text-[10px] font-medium transition-all ${
                                                                        scheduleForm.schedule_day === i + 1
                                                                            ? 'bg-cyan-500/30 text-cyan-300 border border-cyan-500/50'
                                                                            : 'bg-white/5 text-gray-500 border border-white/10 hover:bg-white/10'
                                                                    }`}
                                                                >
                                                                    {d}
                                                                </button>
                                                            ))}
                                                        </div>
                                                    </div>
                                                )}
                                                {scheduleForm.schedule_type === 'monthly' && (
                                                    <div className="flex items-center gap-2">
                                                        <span className="text-xs text-gray-400 w-12">Date</span>
                                                        <select
                                                            value={scheduleForm.schedule_day}
                                                            onChange={e => setScheduleForm(f => ({ ...f, schedule_day: parseInt(e.target.value) }))}
                                                            className="bg-white/5 border border-white/10 rounded px-2 py-1 text-xs text-white"
                                                        >
                                                            {Array.from({ length: 28 }, (_, i) => (
                                                                <option key={i + 1} value={i + 1}>{i + 1}th</option>
                                                            ))}
                                                        </select>
                                                    </div>
                                                )}

                                                {/* Actions Row */}
                                                <div className="flex items-center gap-2 pt-1">
                                                    {/* Enable/Disable Toggle */}
                                                    <button
                                                        onClick={() => setScheduleForm(f => ({ ...f, enabled: !f.enabled }))}
                                                        className={`px-3 py-1.5 rounded text-xs font-bold transition-all ${
                                                            scheduleForm.enabled
                                                                ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/40'
                                                                : 'bg-white/5 text-gray-500 border border-white/10'
                                                        }`}
                                                    >
                                                        {scheduleForm.enabled ? 'Enabled' : 'Disabled'}
                                                    </button>

                                                    {/* Save Schedule */}
                                                    <button
                                                        onClick={async () => {
                                                            try {
                                                                if (analysisSchedule) {
                                                                    const res = await updateAnalysisSchedule(analysisSchedule.id, scheduleForm);
                                                                    setAnalysisSchedule({ ...analysisSchedule, ...scheduleForm, next_run_at: res.next_run_at });
                                                                } else {
                                                                    const res = await createAnalysisSchedule({ ...scheduleForm, target_sessions: ['all_running'] });
                                                                    setAnalysisSchedule(res);
                                                                }
                                                            } catch (e) { console.error('Failed to save schedule:', e); }
                                                        }}
                                                        className="px-3 py-1.5 rounded text-xs font-bold bg-cyan-600 hover:bg-cyan-500 text-white transition-all"
                                                    >
                                                        Save
                                                    </button>

                                                    {/* Delete Schedule */}
                                                    {analysisSchedule && (
                                                        <button
                                                            onClick={async () => {
                                                                try {
                                                                    await deleteAnalysisSchedule(analysisSchedule.id);
                                                                    setAnalysisSchedule(null);
                                                                    setScheduleForm({ schedule_type: 'daily', schedule_time: '15:40', schedule_day: 1, enabled: true });
                                                                } catch (e) { console.error('Failed to delete schedule:', e); }
                                                            }}
                                                            className="px-2 py-1.5 rounded text-xs text-red-400 hover:bg-red-500/10 transition-all"
                                                        >
                                                            <Trash2 size={12} />
                                                        </button>
                                                    )}

                                                    <div className="flex-1" />

                                                    {/* Manual Run - All Sessions */}
                                                    <button
                                                        onClick={async () => {
                                                            setIsAnalysisRunning(true);
                                                            setAnalysisProgress([]); // Clear old progress immediately
                                                            try {
                                                                // Record start time to filter current batch reports
                                                                const runStartedAt = new Date().toISOString();

                                                                const res = await runAnalysisAllSessions();
                                                                const sessions = res?.sessions || [];
                                                                const totalSessions = res?.session_count || sessions.length || 4;
                                                                // Build progress: parse "symbol(strategy)" format
                                                                const progress = sessions.map(s => {
                                                                    const match = s.match(/^(\d+)\(/);
                                                                    return { symbol: match ? match[1] : s, status: 'pending', grade: null };
                                                                });
                                                                setAnalysisProgress(progress);

                                                                // Filter reports to only include current batch (created after run started)
                                                                const filterCurrentBatch = (reports) => {
                                                                    const startTime = new Date(runStartedAt).getTime() - 5000; // 5s buffer
                                                                    return reports.filter(r => {
                                                                        const t = new Date(r.created_at + (r.created_at?.endsWith('Z') ? '' : 'Z')).getTime();
                                                                        return t >= startTime;
                                                                    });
                                                                };

                                                                // Poll helper to update progress from reports
                                                                const updateProgress = (reports, prog) => {
                                                                    return prog.map(p => {
                                                                        const report = reports.find(r => r.symbol === p.symbol && r.status !== 'failed');
                                                                        if (!report) {
                                                                            const failed = reports.find(r => r.symbol === p.symbol && r.status === 'failed');
                                                                            if (failed) return { ...p, status: 'failed', grade: null };
                                                                            return p;
                                                                        }
                                                                        return { ...p, status: report.status, grade: report.grade };
                                                                    });
                                                                };

                                                                // Poll function (reusable for initial + interval)
                                                                const doPoll = async () => {
                                                                    const reportsData = await listAllAnalysisReports(totalSessions * 3);
                                                                    const currentBatch = filterCurrentBatch(reportsData?.reports || []);
                                                                    setAnalysisProgress(prev => updateProgress(currentBatch, prev));
                                                                    return { reportsData, currentBatch };
                                                                };

                                                                // Poll for completion (first poll after 5s, then every 8s)
                                                                let polls = 0;
                                                                const maxPolls = 50;
                                                                const firstPollDelay = 5000;
                                                                const pollIntervalMs = 8000;

                                                                const startPolling = () => {
                                                                    return setInterval(async () => {
                                                                        polls++;
                                                                        try {
                                                                            const { reportsData, currentBatch } = await doPoll();
                                                                            const stillRunning = currentBatch.some(r => r.status === 'running');
                                                                            const doneCount = currentBatch.filter(r => r.status === 'completed' || r.status === 'failed').length;
                                                                            const allDone = doneCount >= totalSessions;
                                                                            if ((!stillRunning && allDone) || polls >= maxPolls) {
                                                                                clearInterval(pollInterval);
                                                                                // Final fetch to update Analysis History
                                                                                try {
                                                                                    const finalData = await listAllAnalysisReports(totalSessions * 3);
                                                                                    setAnalysisReports(finalData?.reports || []);
                                                                                } catch {}
                                                                                setIsAnalysisRunning(false);
                                                                            }
                                                                        } catch {
                                                                            clearInterval(pollInterval);
                                                                            setIsAnalysisRunning(false);
                                                                        }
                                                                    }, pollIntervalMs);
                                                                };

                                                                // Initial poll after short delay, then start regular polling
                                                                let pollInterval;
                                                                setTimeout(async () => {
                                                                    try { await doPoll(); } catch {}
                                                                    pollInterval = startPolling();
                                                                }, firstPollDelay);
                                                            } catch (e) {
                                                                console.error('Analysis all failed:', e);
                                                                setIsAnalysisRunning(false);
                                                                setAnalysisProgress([]);
                                                            }
                                                        }}
                                                        disabled={isAnalysisRunning}
                                                        className="px-3 py-1.5 rounded text-xs font-bold bg-cyan-600 text-white hover:bg-cyan-500 transition-all disabled:opacity-50 flex items-center gap-1"
                                                    >
                                                        {isAnalysisRunning ? <RefreshCw size={12} className="animate-spin" /> : <Play size={12} />}
                                                        {isAnalysisRunning ? 'Running...' : 'Run All'}
                                                    </button>
                                                </div>

                                                {/* Progress Circles */}
                                                {analysisProgress.length > 0 && isAnalysisRunning && (
                                                    <div className="flex items-center gap-3 py-2 px-1">
                                                        {analysisProgress.map((p, i) => (
                                                            <div key={p.symbol} className="flex flex-col items-center gap-1">
                                                                <div className={`relative w-10 h-10 rounded-full flex items-center justify-center text-xs font-bold border-2 transition-all duration-500 ${
                                                                    p.status === 'completed' ? 'border-emerald-400 bg-emerald-400/10 text-emerald-400' :
                                                                    p.status === 'running' ? 'border-cyan-400 bg-cyan-400/10 text-cyan-400' :
                                                                    p.status === 'failed' ? 'border-red-400 bg-red-400/10 text-red-400' :
                                                                    'border-white/10 bg-white/5 text-gray-500'
                                                                }`}>
                                                                    {p.status === 'running' && (
                                                                        <div className="absolute inset-0 rounded-full border-2 border-transparent border-t-cyan-400 animate-spin" />
                                                                    )}
                                                                    {p.status === 'completed' ? (
                                                                        <span className={`text-sm font-bold ${
                                                                            p.grade === 'A' ? 'text-emerald-400' :
                                                                            p.grade === 'B' ? 'text-blue-400' :
                                                                            p.grade === 'C' ? 'text-yellow-400' :
                                                                            p.grade === 'D' ? 'text-orange-400' :
                                                                            p.grade === 'F' ? 'text-red-400' : 'text-gray-400'
                                                                        }`}>{p.grade || 'OK'}</span>
                                                                    ) : p.status === 'failed' ? (
                                                                        <AlertTriangle size={14} />
                                                                    ) : p.status === 'running' ? (
                                                                        <span className="text-[10px]">...</span>
                                                                    ) : (
                                                                        <span className="text-[10px]">{i + 1}</span>
                                                                    )}
                                                                </div>
                                                                <span className="text-[9px] text-gray-500 font-mono">{p.symbol}</span>
                                                            </div>
                                                        ))}
                                                        <div className="text-[10px] text-gray-500 ml-1">
                                                            {analysisProgress.filter(p => p.status === 'completed').length}/{analysisProgress.length}
                                                        </div>
                                                    </div>
                                                )}

                                                {/* Completed Progress Summary */}
                                                {analysisProgress.length > 0 && !isAnalysisRunning && (
                                                    <div className="flex items-center gap-3 py-2 px-1">
                                                        {analysisProgress.map((p) => (
                                                            <div key={p.symbol} className="flex flex-col items-center gap-1">
                                                                <div className={`w-10 h-10 rounded-full flex items-center justify-center text-xs font-bold border-2 ${
                                                                    p.status === 'completed' ? 'border-emerald-400 bg-emerald-400/10' :
                                                                    p.status === 'failed' ? 'border-red-400 bg-red-400/10' :
                                                                    'border-white/10 bg-white/5'
                                                                }`}>
                                                                    <span className={`text-sm font-bold ${
                                                                        p.grade === 'A' ? 'text-emerald-400' :
                                                                        p.grade === 'B' ? 'text-blue-400' :
                                                                        p.grade === 'C' ? 'text-yellow-400' :
                                                                        p.grade === 'D' ? 'text-orange-400' :
                                                                        p.grade === 'F' ? 'text-red-400' :
                                                                        p.status === 'failed' ? 'text-red-400' : 'text-gray-400'
                                                                    }`}>{p.grade || (p.status === 'failed' ? '!' : '-')}</span>
                                                                </div>
                                                                <span className="text-[9px] text-gray-500 font-mono">{p.symbol}</span>
                                                            </div>
                                                        ))}
                                                        <div className="text-[10px] text-emerald-400 ml-1">Done</div>
                                                    </div>
                                                )}

                                                {/* Next Run Info */}
                                                {analysisSchedule?.next_run_at && (
                                                    <div className="text-[10px] text-gray-500 flex items-center gap-1">
                                                        <Clock size={10} />
                                                        Next run: {new Date(analysisSchedule.next_run_at + (analysisSchedule.next_run_at.endsWith('Z') ? '' : 'Z')).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' })} KST
                                                    </div>
                                                )}
                                            </div>

                                            {/* Report Detail View */}
                                            {selectedReport && (
                                                <div className="bg-white/5 rounded-lg p-3 space-y-3">
                                                    <div className="flex items-center justify-between">
                                                        <div className="flex items-center gap-2">
                                                            <button onClick={() => setSelectedReport(null)} className="text-gray-400 hover:text-white">
                                                                <ChevronLeft size={14} />
                                                            </button>
                                                            <span className="text-xs font-bold text-gray-300">Report Detail</span>
                                                        </div>
                                                        <span className={`text-2xl font-black ${
                                                            selectedReport.grade === 'A' ? 'text-emerald-400' :
                                                            selectedReport.grade === 'B' ? 'text-blue-400' :
                                                            selectedReport.grade === 'C' ? 'text-yellow-400' :
                                                            selectedReport.grade === 'D' ? 'text-orange-400' : 'text-red-400'
                                                        }`}>{selectedReport.grade || '-'}</span>
                                                    </div>

                                                    {/* Summary */}
                                                    {selectedReport.ai_analysis?.summary && (
                                                        <div className="text-xs text-gray-300 leading-relaxed bg-white/5 rounded p-2">
                                                            {selectedReport.ai_analysis.summary}
                                                        </div>
                                                    )}

                                                    {/* Action & Risk */}
                                                    <div className="flex items-center gap-2">
                                                        {selectedReport.action && (
                                                            <span className={`px-2 py-1 rounded text-[10px] font-bold ${
                                                                selectedReport.action === '유지' ? 'bg-emerald-500/20 text-emerald-400' :
                                                                selectedReport.action === '조정' ? 'bg-yellow-500/20 text-yellow-400' :
                                                                'bg-red-500/20 text-red-400'
                                                            }`}>{selectedReport.action}</span>
                                                        )}
                                                        {selectedReport.risk_level && (
                                                            <span className={`px-2 py-1 rounded text-[10px] font-bold ${
                                                                selectedReport.risk_level === 'low' ? 'bg-emerald-500/20 text-emerald-400' :
                                                                selectedReport.risk_level === 'medium' ? 'bg-yellow-500/20 text-yellow-400' :
                                                                'bg-red-500/20 text-red-400'
                                                            }`}>Risk: {selectedReport.risk_level}</span>
                                                        )}
                                                    </div>

                                                    {/* Performance Analysis */}
                                                    {selectedReport.ai_analysis?.performance_analysis && (
                                                        <div>
                                                            <div className="text-[10px] font-bold text-gray-400 uppercase mb-1">Performance Analysis</div>
                                                            <div className="text-xs text-gray-300 leading-relaxed">{selectedReport.ai_analysis.performance_analysis}</div>
                                                        </div>
                                                    )}

                                                    {/* News Impact */}
                                                    {selectedReport.ai_analysis?.news_impact && (
                                                        <div>
                                                            <div className="text-[10px] font-bold text-gray-400 uppercase mb-1">News Impact</div>
                                                            <div className="text-xs text-gray-300 leading-relaxed">{selectedReport.ai_analysis.news_impact}</div>
                                                        </div>
                                                    )}

                                                    {/* News Articles */}
                                                    {selectedReport.news_data && selectedReport.news_data.length > 0 && (
                                                        <div>
                                                            <div className="text-[10px] font-bold text-gray-400 uppercase mb-1">Related News</div>
                                                            <div className="space-y-1">
                                                                {selectedReport.news_data.map((article, i) => (
                                                                    <div key={i} className="text-[10px] text-gray-400 flex items-start gap-1">
                                                                        <span className={`mt-0.5 w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                                                                            article.relevance === 'high' ? 'bg-cyan-400' :
                                                                            article.relevance === 'medium' ? 'bg-yellow-400' : 'bg-gray-500'
                                                                        }`} />
                                                                        <span>{article.title} <span className="text-gray-600">({article.source})</span></span>
                                                                    </div>
                                                                ))}
                                                            </div>
                                                        </div>
                                                    )}

                                                    {/* Recommendations */}
                                                    {selectedReport.recommendations && selectedReport.recommendations.length > 0 && (
                                                        <div>
                                                            <div className="text-[10px] font-bold text-gray-400 uppercase mb-1">Recommendations</div>
                                                            <div className="space-y-1">
                                                                {selectedReport.recommendations.map((rec, i) => (
                                                                    <div key={i} className="text-xs text-cyan-300 flex items-start gap-1">
                                                                        <span className="text-cyan-500">{i + 1}.</span>
                                                                        <span>{rec}</span>
                                                                    </div>
                                                                ))}
                                                            </div>
                                                        </div>
                                                    )}

                                                    {/* Backtest Comparison */}
                                                    {selectedReport.trade_summary && selectedReport.backtest_comparison && (
                                                        <div>
                                                            <div className="text-[10px] font-bold text-gray-400 uppercase mb-1">Performance Comparison</div>
                                                            <div className="grid grid-cols-3 gap-1 text-[10px]">
                                                                <div className="text-gray-500">Metric</div>
                                                                <div className="text-gray-500 text-center">Live</div>
                                                                <div className="text-gray-500 text-center">Diff</div>

                                                                <div className="text-gray-400">Return</div>
                                                                <div className="text-center text-white">{selectedReport.trade_summary.total_return?.toFixed(2)}%</div>
                                                                <div className={`text-center ${(selectedReport.backtest_comparison.return_diff || 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                                                                    {selectedReport.backtest_comparison.return_diff != null ? `${selectedReport.backtest_comparison.return_diff >= 0 ? '+' : ''}${selectedReport.backtest_comparison.return_diff.toFixed(2)}` : '-'}
                                                                </div>

                                                                <div className="text-gray-400">Win Rate</div>
                                                                <div className="text-center text-white">{selectedReport.trade_summary.win_rate?.toFixed(1)}%</div>
                                                                <div className={`text-center ${(selectedReport.backtest_comparison.win_rate_diff || 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                                                                    {selectedReport.backtest_comparison.win_rate_diff != null ? `${selectedReport.backtest_comparison.win_rate_diff >= 0 ? '+' : ''}${selectedReport.backtest_comparison.win_rate_diff.toFixed(1)}` : '-'}
                                                                </div>

                                                                <div className="text-gray-400">Sharpe</div>
                                                                <div className="text-center text-white">{selectedReport.trade_summary.sharpe_ratio?.toFixed(2)}</div>
                                                                <div className={`text-center ${(selectedReport.backtest_comparison.sharpe_diff || 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                                                                    {selectedReport.backtest_comparison.sharpe_diff != null ? `${selectedReport.backtest_comparison.sharpe_diff >= 0 ? '+' : ''}${selectedReport.backtest_comparison.sharpe_diff.toFixed(2)}` : '-'}
                                                                </div>
                                                            </div>
                                                        </div>
                                                    )}
                                                </div>
                                            )}

                                            {/* Report History List - hidden during analysis run */}
                                            {!selectedReport && !isAnalysisRunning && (
                                                <div>
                                                    <div className="flex items-center justify-between mb-2">
                                                        <div className="text-xs font-bold text-gray-300 uppercase tracking-wider">Analysis History</div>
                                                        <button
                                                            onClick={async () => {
                                                                const reportsData = await listAllAnalysisReports(20);
                                                                setAnalysisReports(reportsData?.reports || []);
                                                            }}
                                                            className="text-gray-500 hover:text-cyan-400 transition-colors"
                                                        >
                                                            <RefreshCw size={12} />
                                                        </button>
                                                    </div>
                                                    {analysisReports.length === 0 ? (
                                                        <div className="text-xs text-gray-500 text-center py-4">
                                                            No analysis reports yet. Click "Run Now" or set up a schedule.
                                                        </div>
                                                    ) : (
                                                        <div className="space-y-2 max-h-72 overflow-y-auto">
                                                            {/* Group reports by batch (within 5min window = same batch) */}
                                                            {(() => {
                                                                const batches = [];
                                                                const sorted = [...analysisReports].sort((a, b) =>
                                                                    new Date(b.created_at || 0) - new Date(a.created_at || 0)
                                                                );
                                                                sorted.forEach(report => {
                                                                    const t = new Date(report.created_at + (report.created_at?.endsWith('Z') ? '' : 'Z')).getTime();
                                                                    const lastBatch = batches[batches.length - 1];
                                                                    if (lastBatch && Math.abs(t - lastBatch.time) < 5 * 60 * 1000) {
                                                                        lastBatch.reports.push(report);
                                                                    } else {
                                                                        batches.push({ time: t, reports: [report] });
                                                                    }
                                                                });
                                                                return batches.map((batch, bi) => {
                                                                    const batchDate = new Date(batch.time);
                                                                    const dateStr = batchDate.toLocaleString('ko-KR', {
                                                                        timeZone: 'Asia/Seoul', month: '2-digit', day: '2-digit',
                                                                        hour: '2-digit', minute: '2-digit', hour12: false
                                                                    });
                                                                    const hasRunning = batch.reports.some(r => r.status === 'running');
                                                                    const hasFailed = batch.reports.some(r => r.status === 'failed');
                                                                    const type = batch.reports[0]?.report_type;
                                                                    return (
                                                                        <div key={bi} className="rounded-lg bg-white/5 border border-white/5 hover:border-cyan-500/20 transition-all">
                                                                            {/* Batch header */}
                                                                            <div className="flex items-center justify-between px-3 py-1.5 border-b border-white/5">
                                                                                <div className="flex items-center gap-2">
                                                                                    <span className="text-[10px] text-gray-500">{dateStr}</span>
                                                                                    <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold uppercase ${
                                                                                        type === 'manual' ? 'bg-cyan-500/20 text-cyan-400' : 'bg-purple-500/20 text-purple-400'
                                                                                    }`}>{type === 'manual' ? 'Manual' : 'Scheduled'}</span>
                                                                                </div>
                                                                                <div className="flex items-center gap-1">
                                                                                    {hasRunning && <RefreshCw size={10} className="text-cyan-400 animate-spin" />}
                                                                                    {hasFailed && <AlertTriangle size={10} className="text-red-400" />}
                                                                                    <span className="text-[10px] text-gray-600">{batch.reports.length} symbols</span>
                                                                                </div>
                                                                            </div>
                                                                            {/* Symbol grade chips */}
                                                                            <div className="flex flex-wrap gap-1.5 px-3 py-2">
                                                                                {batch.reports.map(report => {
                                                                                    const gradeColor = report.grade === 'A' ? 'text-emerald-400 border-emerald-500/30' :
                                                                                        report.grade === 'B' ? 'text-blue-400 border-blue-500/30' :
                                                                                        report.grade === 'C' ? 'text-yellow-400 border-yellow-500/30' :
                                                                                        report.grade === 'D' ? 'text-orange-400 border-orange-500/30' :
                                                                                        report.grade === 'F' ? 'text-red-400 border-red-500/30' :
                                                                                        'text-gray-500 border-gray-600/30';
                                                                                    const gradeBg = report.grade === 'A' ? 'bg-emerald-500/10' :
                                                                                        report.grade === 'B' ? 'bg-blue-500/10' :
                                                                                        report.grade === 'C' ? 'bg-yellow-500/10' :
                                                                                        report.grade === 'D' ? 'bg-orange-500/10' :
                                                                                        report.grade === 'F' ? 'bg-red-500/10' :
                                                                                        'bg-white/5';
                                                                                    return (
                                                                                        <button
                                                                                            key={report.id}
                                                                                            className={`flex items-center gap-1.5 px-2 py-1 rounded-md border ${gradeBg} ${gradeColor} hover:brightness-125 cursor-pointer transition-all`}
                                                                                            onClick={async () => {
                                                                                                try {
                                                                                                    const detail = await getAnalysisReportDetail(report.id);
                                                                                                    setSelectedReport(detail);
                                                                                                } catch (e) { console.error('Failed to load report:', e); }
                                                                                            }}
                                                                                        >
                                                                                            {report.status === 'running' ? (
                                                                                                <RefreshCw size={10} className="text-cyan-400 animate-spin" />
                                                                                            ) : (
                                                                                                <span className="text-sm font-bold">{report.grade || '-'}</span>
                                                                                            )}
                                                                                            <span className="text-[10px] font-mono opacity-80">{report.symbol || '?'}</span>
                                                                                        </button>
                                                                                    );
                                                                                })}
                                                                            </div>
                                                                        </div>
                                                                    );
                                                                });
                                                            })()}
                                                        </div>
                                                    )}
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                )}
                            </div>
                        )}

                    </div>
                ) : (
                    <div className="bg-white/5 border border-white/10 rounded-xl overflow-hidden flex flex-col">
                        <div className="bg-white/5 px-4 py-3 border-b border-white/10 flex items-center justify-between">
                            <h3 className="font-bold text-gray-200 text-sm flex items-center gap-2">
                                {selectedCycle ? (
                                    <>
                                        <button
                                            onClick={() => { setSelectedCycle(null); setCycleChartData(null); }}
                                            className="flex items-center gap-1 px-2 py-1 rounded bg-white/5 border border-white/10 text-gray-300 hover:text-blue-400 hover:bg-blue-500/10 hover:border-blue-500/30 transition-all text-xs font-medium"
                                        >
                                            <ChevronLeft size={14} />
                                            Back
                                        </button>
                                        <History size={14} className="text-gray-400" />
                                        Cycle Chart — {selectedCycle.symbol}
                                    </>
                                ) : (
                                    <>
                                        <History size={14} className="text-gray-400" />
                                        Transaction History
                                    </>
                                )}
                                <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${
                                    historyMode === 'paper' ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
                                    : historyMode === 'real' ? 'bg-red-500/20 text-red-400 border border-red-500/30'
                                    : 'bg-blue-500/20 text-blue-400 border border-blue-500/30'
                                }`}>
                                    {historyMode === 'paper' ? 'Paper' : historyMode === 'real' ? 'Real' : 'All'}
                                </span>
                                {!selectedCycle && historyData && (
                                    <span className="text-xs text-gray-500 font-normal">
                                        ({historyData.total_cycles} cycles, {historyData.total_trades} trades)
                                    </span>
                                )}
                            </h3>
                            <div className="flex items-center gap-2">
                                {!selectedCycle && (
                                    <div className="flex items-center gap-1">
                                        {['paper', 'real', 'all'].map(m => (
                                            <button
                                                key={m}
                                                onClick={() => {
                                                    setHistoryMode(m);
                                                    setIsHistoryLoading(true);
                                                    const isPaperValue = m === 'paper' ? true : m === 'real' ? false : null;
                                                    getTradeHistoryList({ is_paper: isPaperValue, limit: 500 }).then(data => {
                                                        setHistoryData(data);
                                                        setIsHistoryLoading(false);
                                                    }).catch(err => {
                                                        console.error("Failed to load trade list:", err);
                                                        setIsHistoryLoading(false);
                                                    });
                                                }}
                                                className={`px-2 py-1 rounded text-[10px] font-bold uppercase tracking-wider border transition-all ${
                                                    historyMode === m
                                                        ? m === 'paper' ? 'bg-amber-500/20 text-amber-400 border-amber-500/40'
                                                        : m === 'real' ? 'bg-red-500/20 text-red-400 border-red-500/40'
                                                        : 'bg-blue-500/20 text-blue-400 border-blue-500/40'
                                                        : 'bg-white/5 text-gray-500 border-white/10 hover:bg-white/10'
                                                }`}
                                            >
                                                {m === 'paper' ? 'Paper' : m === 'real' ? 'Real' : 'All'}
                                            </button>
                                        ))}
                                    </div>
                                )}
                                {!selectedCycle && historyData && (
                                    <button
                                        onClick={exportHistoryCSV}
                                        className="text-gray-400 hover:text-emerald-400 text-xs font-bold flex items-center gap-1"
                                        title="Export as CSV"
                                    >
                                        <Download size={14} /> CSV
                                    </button>
                                )}
                                <button
                                    onClick={() => {
                                        setShowHistoryView(false);
                                        setHistoryData(null);
                                        setSelectedCycle(null);
                                        setCycleChartData(null);
                                    }}
                                    className="text-gray-400 hover:text-red-400 text-xs font-bold flex items-center gap-1"
                                >
                                    <X size={14} /> Close
                                </button>
                            </div>
                        </div>

                        <div className="flex-1 relative">
                            {isHistoryLoading ? (
                                <div className="flex items-center justify-center py-16">
                                    <div className="flex flex-col items-center gap-4">
                                        <Activity className="w-10 h-10 text-blue-500 animate-pulse" />
                                        <span className="text-gray-400">Loading trades...</span>
                                    </div>
                                </div>
                            ) : selectedCycle ? (
                                /* Step 2: Cycle Chart View */
                                <div className="min-h-[500px]">
                                    {isCycleChartLoading ? (
                                        <div className="flex items-center justify-center py-16">
                                            <div className="flex flex-col items-center gap-4">
                                                <Activity className="w-10 h-10 text-blue-500 animate-pulse" />
                                                <span className="text-gray-400">Fetching 1m chart data...</span>
                                                <span className="text-gray-500 text-xs">Incrementally loading from DB</span>
                                            </div>
                                        </div>
                                    ) : cycleChartData ? (
                                        <div>
                                            {/* Cycle Summary Bar */}
                                            <div className="px-4 py-3 border-b border-white/5 bg-white/[0.02] flex items-center gap-4 text-xs flex-wrap">
                                                {selectedCycle.strategy_name && (
                                                    <span className="text-blue-400 font-semibold bg-blue-500/10 px-2 py-0.5 rounded">
                                                        {selectedCycle.strategy_name}
                                                    </span>
                                                )}
                                                <span className="text-gray-400">
                                                    <Clock size={12} className="inline mr-1" />
                                                    {new Date(selectedCycle.entry_time + 'Z').toLocaleDateString('ko-KR', { timeZone: 'Asia/Seoul' })} — {selectedCycle.exit_time ? new Date(selectedCycle.exit_time + 'Z').toLocaleDateString('ko-KR', { timeZone: 'Asia/Seoul' }) : 'Open'}
                                                </span>
                                                <span className="text-gray-400">Entries: <span className="text-white font-bold">{selectedCycle.num_entries}</span></span>
                                                <span className="text-gray-400">Avg Entry: <span className="text-white font-bold">{selectedCycle.avg_entry_price?.toLocaleString()}</span></span>
                                                {selectedCycle.sell && (
                                                    <span className="text-gray-400">Exit: <span className="text-white font-bold">{selectedCycle.sell_price?.toLocaleString()}</span></span>
                                                )}
                                                <span className={selectedCycle.realized_pnl >= 0 ? 'text-emerald-400 font-bold' : 'text-red-400 font-bold'}>
                                                    PnL: {selectedCycle.realized_pnl >= 0 ? '+' : ''}{selectedCycle.realized_pnl?.toLocaleString()} ({selectedCycle.return_pct >= 0 ? '+' : ''}{selectedCycle.return_pct?.toFixed(2)}%)
                                                </span>
                                                {selectedCycle.config_snapshot && (
                                                    <span className="text-gray-500 hover:text-gray-300 cursor-help relative group">
                                                        <span className="underline decoration-dashed">Params</span>
                                                        <div className="absolute bottom-full left-0 mb-2 hidden group-hover:block z-50 bg-gray-900 border border-white/10 rounded-lg p-3 text-xs max-w-sm max-h-48 overflow-auto shadow-xl whitespace-pre-wrap">
                                                            {JSON.stringify(selectedCycle.config_snapshot, null, 2)}
                                                        </div>
                                                    </span>
                                                )}
                                            </div>
                                            <VisualBacktestChart
                                                data={cycleChartData.candles}
                                                trades={cycleChartData.trades}
                                                showOnlyPnl={false}
                                                priceScaleOptions={{ autoScale: true, scaleMargins: { top: 0.1, bottom: 0.1 } }}
                                                yAxisFormatter={(price) => price.toLocaleString()}
                                                selectedInterval="1m"
                                            />
                                        </div>
                                    ) : (
                                        <div className="flex items-center justify-center py-16 text-red-400">
                                            Failed to load chart data.
                                        </div>
                                    )}
                                </div>
                            ) : historyData ? (
                                /* Step 1: Rank-based Overview Chart (like IntegratedAnalysis) */
                                <div className="min-h-[350px]">
                                    {overviewChartData.length > 0 ? (
                                        <VisualBacktestChart
                                            data={overviewChartData}
                                            trades={overviewTrades}
                                            yAxisFormatter={overviewRankFormatter}
                                            priceScaleOptions={overviewPriceScaleOptions}
                                            showOnlyPnl={true}
                                            onChartClick={handleOverviewChartClick}
                                            selectedInterval="1d"
                                        />
                                    ) : (
                                        <div className="flex items-center justify-center py-16 text-gray-500">
                                            No trade cycles to visualize.
                                        </div>
                                    )}
                                    {/* Summary stats below chart */}
                                    {overviewSymbolRanks && (
                                        <div className="px-4 py-3 border-t border-white/5 bg-white/[0.02]">
                                            <div className="flex items-center gap-4 text-xs flex-wrap">
                                                <span className="text-gray-500 font-bold uppercase tracking-wider">Summary</span>
                                                <span className="text-gray-400">
                                                    Closed: <span className="text-white font-bold">{historyData.total_cycles || 0}</span> cycles
                                                </span>
                                                <span className="text-gray-400">
                                                    Open: <span className="text-amber-400 font-bold">{historyData.total_open || 0}</span>
                                                </span>
                                                <span className="text-gray-400">
                                                    Total Trades: <span className="text-white font-bold">{historyData.total_trades || 0}</span>
                                                </span>
                                                {historyData.cycles?.length > 0 && (() => {
                                                    const totalPnl = historyData.cycles.reduce((sum, c) => sum + (c.realized_pnl || 0), 0);
                                                    const winCount = historyData.cycles.filter(c => c.realized_pnl > 0).length;
                                                    const winRate = historyData.cycles.length > 0 ? (winCount / historyData.cycles.length * 100) : 0;
                                                    return (
                                                        <>
                                                            <span className={totalPnl >= 0 ? 'text-emerald-400 font-bold' : 'text-red-400 font-bold'}>
                                                                PnL: {totalPnl >= 0 ? '+' : ''}{totalPnl.toLocaleString()}
                                                            </span>
                                                            <span className="text-gray-400">
                                                                Win Rate: <span className={winRate >= 50 ? 'text-emerald-400 font-bold' : 'text-red-400 font-bold'}>{winRate.toFixed(1)}%</span>
                                                            </span>
                                                        </>
                                                    );
                                                })()}
                                                <span className="text-gray-600 ml-auto text-[10px]">Click chart to drill down</span>
                                            </div>
                                        </div>
                                    )}
                                </div>
                            ) : (
                                <div className="flex items-center justify-center py-16 text-red-400">
                                    Failed to load trade list.
                                </div>
                            )}
                        </div>
                    </div>
                )}
            </div>

            {/* 5. EXECUTION LOGS (Moved to Bottom) */}
            <div className="lg:col-span-3 bg-white/5 border border-white/10 rounded-xl overflow-hidden flex flex-col min-h-[200px] max-h-[400px]">
                <div className="bg-white/5 px-4 py-3 border-b border-white/10">
                    <h3 className="font-bold text-gray-200 text-sm flex items-center gap-2">
                        <Terminal size={14} className="text-gray-400" /> Execution Logs
                    </h3>
                </div>
                <div className="px-4 py-4 flex-1 overflow-hidden flex flex-col font-mono text-xs">
                <div className="flex-1 overflow-y-auto space-y-1 scrollbar-thin scrollbar-thumb-gray-700">
                    {logs.length === 0 && <div className="text-gray-600 italic">No logs yet...</div>}
                    {logs.map((log, i) => (
                        <div key={i} className="flex gap-2">
                            <span className="text-gray-500">[{log.time}]</span>
                            <span className={log.source === 'Error' ? 'text-red-400' : 'text-blue-400'}>{log.source}:</span>
                            <span className="text-gray-300">{log.msg}</span>
                        </div>
                    ))}
                </div>
                </div>
            </div>
        </div>
    );
};

export default LiveStrategyPanel;
