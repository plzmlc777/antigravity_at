import React, { useState, useEffect, useRef } from 'react';
import { Play, Square, Activity, AlertTriangle, Terminal, List, X, Pause, Shield, ShieldOff, ShieldAlert } from 'lucide-react';
// import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { startLiveBot, stopLiveBot, getLiveStatus, getOHLCV, getTradeHistory, getTradeHistoryContext, toggleLiveOrders, toggleLiveMode, liquidateLiveBot, getBalance } from '../api/client';
import IntegratedAnalysis from './IntegratedAnalysis';
import ConfirmModal from './ConfirmModal';
import VisualBacktestChart from './VisualBacktestChart';
import ActiveStrategiesPanel from './ActiveStrategiesPanel';
import StrategySignalPanel from './StrategySignalPanel';
import StrategyKPIWidget from './StrategyKPIWidget';

const LiveStrategyPanel = ({ strategyConfig, strategyName, mode = 'TRADE', configList = [], savedSymbols = [], currentRankIndex, onRankChange, executionMode = 'exclusive', onExecutionModeChange, parameterSchema }) => {
    // State
    const [status, setStatus] = useState('IDLE'); // IDLE, RUNNING, STOPPED, ERROR
    const [sessionId, setSessionId] = useState(null);
    const [liveData, setLiveData] = useState(null);
    const [logs, setLogs] = useState([]);
    const [error, setError] = useState(null);
    const [availableBalance, setAvailableBalance] = useState(null);
    const [inputCapital, setInputCapital] = useState(10000000); // 10M default

    const [tickData, setTickData] = useState([]); // Running list of recent ticks for UI (optional)
    const [isStopModalOpen, setIsStopModalOpen] = useState(false);

    // Parallel mode: track multiple sessions {rankIndex: sessionId}
    const [parallelSessions, setParallelSessions] = useState({});

    // Parallel mode: per-rank capital allocation weights (%) {rankIndex: percent}
    const [rankWeights, setRankWeights] = useState({});

    // Real-Time Candles State
    const [realTimeCandles, setRealTimeCandles] = useState([]);
    const [selectedInterval, setSelectedInterval] = useState('1m');

    // Transaction History View State
    const [showHistoryView, setShowHistoryView] = useState(false);
    const [historyData, setHistoryData] = useState(null);
    const [isHistoryLoading, setIsHistoryLoading] = useState(false);

    // New: Strategy Internal State
    const [strategyState, setStrategyState] = useState(null);


    // Polling Ref
    const pollInterval = useRef(null);
    const lastFetchRef = useRef({ symbol: null, interval: null, status: null });

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

        // Deduplication Check: Skip if this specific combination was already fetched
        if (lastFetchRef.current.symbol === strategyConfig.symbol &&
            lastFetchRef.current.interval === selectedInterval) {
            console.log(`[DEBUG] Skipping redundant history fetch for ${strategyConfig.symbol} (${selectedInterval})`);
            return;
        }

        console.log(`[DEBUG] History Fetch Effect Triggered. Status: ${status}, Symbol: ${strategyConfig.symbol}, Interval: ${selectedInterval}`);
        lastFetchRef.current = { symbol: strategyConfig.symbol, interval: selectedInterval, status: status };
        setRealTimeCandles([]);

        (async () => {
            try {
                const now = new Date();
                const kstOffset = 9 * 60;
                const utc = now.getTime() + (now.getTimezoneOffset() * 60000);
                const kstDate = new Date(utc + (kstOffset * 60000));
                const dateStr = kstDate.toISOString().split('T')[0].replace(/-/g, '');

                addLog("System", `Fetching ${selectedInterval} candles...`);

                const candles = await getOHLCV(strategyConfig.symbol, {
                    date: dateStr,
                    interval: selectedInterval
                });

                // Only set if WS history hasn't arrived yet
                if (!wsHistoryReceived.current) {
                    if (candles && candles.length > 0) {
                        setRealTimeCandles(candles);
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
                setRealTimeCandles([]);
            }
        })();
    }, [status, strategyConfig.symbol, selectedInterval, mode, sessionId]);


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
            const sessions = await getLiveStatus();

            if (executionMode === 'parallel') {
                // Parallel: detect sessions for all active ranks
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
                // Exclusive: single session by symbol
                const currentSymbol = strategyConfig.symbol;
                const mySession = sessions.find(s => s.symbol === currentSymbol && s.is_running);

                if (mySession) {
                    setStatus('RUNNING');
                    setSessionId(mySession.session_id);
                    setLiveData(mySession);
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

    const handleStart = async () => {
        if (!strategyConfig.symbol) {
            alert("Symbol not selected");
            return;
        }

        try {
            setError(null);
            setStatus('STARTING');

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

                const newSessions = {};
                for (let i = 0; i < configList.length; i++) {
                    const cfg = configList[i];
                    if (!cfg.is_active) continue;

                    const weight = rankWeights[i] || 0;
                    const rankCapital = totalWeight > 0
                        ? Math.floor(totalCapital * weight / totalWeight)
                        : Math.floor(totalCapital / activeConfigs.length);

                    const payload = {
                        symbol: cfg.symbol,
                        strategy_name: strategyName || "time_momentum",
                        strategy_config: cfg,
                        initial_capital: rankCapital
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
                // Exclusive: single session
                const payload = {
                    symbol: strategyConfig.symbol,
                    strategy_name: strategyName || "time_momentum",
                    strategy_config: strategyConfig,
                    initial_capital: parseFloat(inputCapital) || 0
                };

                const res = await startLiveBot(payload);
                setSessionId(res.session_id);
                setStatus('RUNNING');
                startPolling();

                addLog("System", `Session Started: ${res.session_id}`);
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

    const handleEmergencyLiquidation = async () => {
        if (!window.confirm("EMERGENCY: Do you want to sell ALL holdings and pause trading?")) return;

        try {
            if (executionMode === 'parallel' && Object.keys(parallelSessions).length > 0) {
                for (const sid of Object.values(parallelSessions)) {
                    await liquidateLiveBot(sid);
                }
                addLog("Emergency", `KILL SWITCH: Liquidating all ${Object.keys(parallelSessions).length} parallel sessions.`);
            } else if (sessionId) {
                await liquidateLiveBot(sessionId);
                addLog("Emergency", "KILL SWITCH: Liquidating all holdings and pausing orders.");
            }
            setLiveData(prev => ({ ...prev, orders_enabled: false }));
            alert("Emergency Liquidation Initiated. Orders have been paused.");
        } catch (err) {
            setError(err.message);
            addLog("Error", `Liquidation failed: ${err.message}`);
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
            addLog("System", `WS connected to: ${wsUrl}`);
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

                    // 2. Aggregate to Candle
                    setRealTimeCandles(prevCandles => {
                        const newPrice = data.price;
                        let tickTime = new Date();
                        if (data.time) {
                            const t = new Date(data.time);
                            if (!isNaN(t.getTime())) tickTime = t;
                        }

                        // Normalize to Selected Interval
                        const ms = 1000;
                        const min = 60 * ms;
                        const hour = 60 * min;
                        const day = 24 * hour;

                        let intervalMs = min; // Default 1m

                        const unit = selectedInterval.slice(-1);
                        const value = parseInt(selectedInterval.slice(0, -1));

                        if (unit === 'm') intervalMs = value * min;
                        else if (unit === 'h') intervalMs = value * hour;
                        else if (unit === 'd') intervalMs = value * day;

                        // Calculate Candle Start Time
                        // Note: Simple math floor works for consistent intervals from Unix Epic,
                        // but for daily/4h aligned to market/local time, Date manipulation is safer.
                        // However, for simplicity and typical crypto/global usage, timestamp math is often used.
                        // Let's use simple timestamp flooring for < 1d, and Date for >= 1d if needed.
                        // Actually, to align with Chart, we should use similar logic.

                        // Using Date math for better alignment with local hours
                        const year = tickTime.getFullYear();
                        const month = tickTime.getMonth();
                        const date = tickTime.getDate();
                        const hours = tickTime.getHours();
                        const minutes = tickTime.getMinutes();

                        // Reset base
                        tickTime.setSeconds(0, 0);

                        if (selectedInterval === '1d') {
                            tickTime.setHours(0, 0, 0, 0);
                        } else if (unit === 'h') {
                            const h = Math.floor(hours / value) * value;
                            tickTime.setHours(h, 0, 0, 0);
                        } else if (unit === 'm') {
                            const m = Math.floor(minutes / value) * value;
                            tickTime.setMinutes(m, 0, 0);
                        }

                        const candleTime = tickTime.getTime() / 1000;

                        const lastCandle = prevCandles[prevCandles.length - 1];

                        if (lastCandle && lastCandle.time === candleTime) {
                            // Update existing candle
                            return [...prevCandles.slice(0, -1), {
                                ...lastCandle,
                                high: Math.max(lastCandle.high, newPrice),
                                low: Math.min(lastCandle.low, newPrice),
                                close: newPrice,
                                volume: (lastCandle.volume || 0) + (data.volume || 1)
                            }];
                        } else if (lastCandle && lastCandle.time > candleTime) {
                            // Received old tick? Ignore or re-sort? Mostly ignore for simple live view.
                            return prevCandles;
                        } else {
                            // New Candle
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
                        setRealTimeCandles(historyCandles);
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
                        setRealTimeCandles(prev => {
                            // Replace if same time, append if new
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
            addLog("System", "Real-time feed disconnected");
        };

        return () => {
            wsHistoryReceived.current = false;
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
                        onIntervalChange={setSelectedInterval}
                    />
                </div>
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
                    />
                </div>
            )}

            {/* Modal */}
            <ConfirmModal
                isOpen={isStopModalOpen}
                onClose={() => setIsStopModalOpen(false)}
                onConfirm={async () => {
                    try {
                        if (executionMode === 'parallel' && Object.keys(parallelSessions).length > 0) {
                            for (const sid of Object.values(parallelSessions)) {
                                await stopLiveBot(sid);
                            }
                            setParallelSessions({});
                            addLog("System", `All ${Object.keys(parallelSessions).length} parallel sessions stopped`);
                        } else {
                            await stopLiveBot(sessionId);
                            addLog("System", "Session Stopped by User");
                        }
                        setStatus('STOPPED');
                        stopPolling();
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

            {/* 1. TOP ROW: Live Operation Controls (Combined & Full Width) */}
            <div className="lg:col-span-3 relative">
                <div className={`bg-[#1e1e24] border border-white/5 rounded-xl p-6 relative overflow-hidden ${status === 'RUNNING' ? 'glow-pulse-green' : ''}`}>
                    {/* Header */}
                    <div className="flex items-center gap-3 mb-6">
                        <Activity className={`w-5 h-5 ${status === 'RUNNING' ? 'text-green-400 animate-pulse' : 'text-gray-500'}`} />
                        <h2 className="font-bold text-lg text-white">Live Operation</h2>
                        <span className={`ml-2 px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${executionMode === 'parallel' ? 'bg-blue-500/20 text-blue-400 border border-blue-500/30' : 'bg-gray-500/20 text-gray-400 border border-gray-500/30'}`}>
                            {executionMode === 'parallel' ? 'Parallel' : 'Exclusive'}
                        </span>
                        {executionMode === 'parallel' && Object.keys(parallelSessions).length > 0 && (
                            <span className="text-xs text-blue-400">
                                ({Object.keys(parallelSessions).length} ranks active)
                            </span>
                        )}
                    </div>

                    {/* Section 1: Dashboard Stats (Status | PnL | Balance | Target) */}
                    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4 mb-6">
                        {/* Status */}
                        <div className="bg-black/20 border border-white/5 rounded-lg p-4 flex flex-col justify-center items-center">
                            <span className="text-gray-400 text-xs font-bold tracking-wider uppercase mb-1">Session Status</span>
                            <span className={`px-4 py-1 rounded-full text-sm font-bold border tracking-wide ${getStatusColor()}`}>
                                {status}
                            </span>
                        </div>

                        {/* PnL */}
                        <div className="bg-black/20 border border-white/5 rounded-lg p-4 flex flex-col justify-center items-center">
                            <span className="text-gray-400 text-xs font-bold tracking-wider uppercase mb-1">Unrealized PnL</span>
                            {liveData ? (
                                <div className={`text-2xl font-mono tracking-tight ${liveData.pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                    {liveData.pnl > 0 ? '+' : ''}{liveData.pnl?.toLocaleString()}
                                </div>
                            ) : (
                                <span className="text-gray-600 text-sm">-</span>
                            )}
                        </div>

                        {/* Account Balance (Total Available Cash) */}
                        <div className="bg-black/20 border border-white/5 rounded-lg p-4 flex flex-col justify-center items-center">
                            <span className="text-gray-400 text-xs font-bold tracking-wider uppercase mb-1">Total Account Cash</span>
                            <div className="text-xl font-mono text-blue-400 tracking-tight">
                                {availableBalance !== null ? `${availableBalance.toLocaleString()} KRW` : 'Fetching...'}
                            </div>
                        </div>

                        {/* Target Capital (Allocated for this bot) */}
                        <div className="bg-black/20 border border-white/5 rounded-lg p-4 flex flex-col justify-center items-center">
                            <span className="text-gray-400 text-xs font-bold tracking-wider uppercase mb-1">Target Capital</span>
                            <div className="text-xl font-mono text-purple-400 tracking-tight">
                                {inputCapital ? `${(parseFloat(inputCapital)).toLocaleString()} KRW` : '0 KRW'}
                            </div>
                            {executionMode === 'parallel' && configList.filter(c => c.is_active).length > 1 && (() => {
                                const activeWeights = Object.entries(rankWeights).filter(([idx]) => configList[idx]?.is_active);
                                const isEqual = activeWeights.length > 0 && activeWeights.every(([, w]) => w === activeWeights[0][1]);
                                return (
                                    <div className="text-[10px] text-gray-500 mt-1">
                                        {isEqual
                                            ? `÷ ${activeWeights.length} ranks (Equal)`
                                            : `Custom: ${activeWeights.length} ranks`}
                                    </div>
                                );
                            })()}
                        </div>
                    </div>

                    {/* Section 1.5: Strategy-specific KPI Widget */}
                    <StrategyKPIWidget
                        strategyId={strategyName || strategyConfig?.strategy_id || 'time_momentum'}
                        strategyConfig={strategyConfig}
                        liveData={liveData}
                        strategyState={strategyState}
                    />

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
                                        onChange={(e) => setInputCapital(e.target.value)}
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

                            {/* Execution Mode Selector */}
                            <div className="w-full md:w-48">
                                <label className="block text-gray-400 text-[10px] font-bold tracking-wider uppercase mb-2">
                                    Execution Mode
                                </label>
                                <select
                                    value={executionMode}
                                    onChange={(e) => onExecutionModeChange?.(e.target.value)}
                                    disabled={status === 'RUNNING' || status === 'STARTING'}
                                    className="w-full bg-black/60 border border-white/10 rounded-lg px-3 py-3 text-white text-sm font-bold outline-none focus:border-blue-500/50 transition-all disabled:opacity-50 disabled:cursor-not-allowed appearance-none cursor-pointer"
                                >
                                    <option value="exclusive">Exclusive</option>
                                    <option value="parallel">Parallel</option>
                                </select>
                                <p className="text-gray-500 text-[9px] mt-1.5">
                                    {executionMode === 'exclusive'
                                        ? 'Waterfall: Rank 1 → 2 → 3'
                                        : `${configList.filter(c => c.is_active).length} ranks (custom %)`}
                                </p>
                            </div>

                            {/* Main Action Buttons */}
                            <div className="flex-[0.5] w-full flex flex-col gap-2">
                                {status !== 'RUNNING' ? (
                                    <button
                                        onClick={handleStart}
                                        disabled={status === 'STARTING'}
                                        className="w-full h-14 flex items-center justify-center gap-2 bg-green-600 hover:bg-green-500 text-white text-base font-bold tracking-wide rounded-lg transition-all disabled:opacity-50 shadow-lg shadow-green-900/20"
                                    >
                                        <Play size={20} />
                                        START LIVE BOT
                                    </button>
                                ) : (
                                    <div className="grid grid-cols-2 gap-2">
                                        <button
                                            onClick={() => {
                                                if (liveData?.is_paper !== false) { // Moving from Paper to Real
                                                    if (availableBalance !== null && inputCapital > availableBalance) {
                                                        alert("Cannot enable REAL MODE: Allocated capital exceeds actual account balance. Funds are insufficient for real trading.");
                                                        return;
                                                    }
                                                    if (!window.confirm("Switch to REAL MODE? This will send actual orders to the exchange.")) return;
                                                }
                                                handleToggleMode();
                                            }}
                                            className={`h-14 flex items-center justify-center gap-2 text-[10px] font-bold tracking-wide rounded-lg border transition-all ${liveData?.is_paper === false
                                                ? 'bg-red-900/40 border-red-500 text-red-500 hover:bg-red-900/60'
                                                : (availableBalance !== null && inputCapital > availableBalance)
                                                    ? 'bg-gray-800 border-gray-700 text-gray-500 cursor-not-allowed opacity-50'
                                                    : 'bg-green-600/20 border-green-500 text-green-400 hover:bg-green-600/30'
                                                }`}
                                        >
                                            {liveData?.is_paper === false ? (
                                                <><ShieldOff size={14} /> REAL MODE (ON)</>
                                            ) : (
                                                <><Shield size={14} /> PAPER MODE (ACTIVE)</>
                                            )}
                                        </button>

                                        <button
                                            onClick={() => setIsStopModalOpen(true)}
                                            className="h-14 flex items-center justify-center gap-2 bg-gray-700 hover:bg-gray-600 text-white text-[10px] font-bold tracking-wide rounded-lg transition-all border border-gray-600"
                                        >
                                            <Square size={14} />
                                            STOP
                                        </button>
                                    </div>
                                )}
                            </div>
                        </div>

                        {/* Parallel Mode: Per-Rank Capital Allocation */}
                        {executionMode === 'parallel' && configList.filter(c => c.is_active).length > 1 && (
                            <div className="mt-4 p-3 bg-blue-900/10 border border-blue-500/20 rounded-lg">
                                <div className="flex items-center justify-between mb-2">
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
                                <div className="space-y-1.5">
                                    {configList.map((cfg, idx) => {
                                        if (!cfg.is_active) return null;
                                        const weight = rankWeights[idx] || 0;
                                        const capital = Math.floor((parseFloat(inputCapital) || 0) * weight / 100);
                                        return (
                                            <div key={idx} className="flex items-center gap-2">
                                                <span className="text-gray-500 text-[10px] w-20 truncate font-mono">R{idx + 1} {cfg.symbol?.slice(0, 6)}</span>
                                                <input
                                                    type="number"
                                                    min={0}
                                                    max={100}
                                                    value={weight}
                                                    onChange={(e) => {
                                                        const v = Math.max(0, Math.min(100, parseInt(e.target.value) || 0));
                                                        setRankWeights(prev => ({ ...prev, [idx]: v }));
                                                    }}
                                                    disabled={status === 'RUNNING' || status === 'STARTING'}
                                                    className="w-14 bg-black/60 border border-white/10 rounded px-2 py-1 text-white text-xs font-mono text-center outline-none focus:border-blue-500/50 disabled:opacity-50 disabled:cursor-not-allowed"
                                                />
                                                <span className="text-gray-600 text-[10px]">%</span>
                                                <div className="flex-1 bg-white/5 rounded-full h-1.5 overflow-hidden">
                                                    <div className="bg-blue-500/60 h-full rounded-full transition-all" style={{ width: `${Math.min(weight, 100)}%` }} />
                                                </div>
                                                <span className="text-gray-500 text-[10px] font-mono w-24 text-right">{capital.toLocaleString()}</span>
                                            </div>
                                        );
                                    })}
                                </div>
                                {(() => {
                                    const total = Object.values(rankWeights).reduce((s, w) => s + w, 0);
                                    return (
                                        <div className={`flex items-center justify-between mt-2 pt-2 border-t border-white/5 text-[10px] ${total !== 100 ? 'text-yellow-400' : 'text-gray-500'}`}>
                                            <span>Total: {total}%</span>
                                            {total !== 100 && (
                                                <span className="flex items-center gap-1">
                                                    <AlertTriangle size={10} /> Must be 100%
                                                </span>
                                            )}
                                        </div>
                                    );
                                })()}
                            </div>
                        )}

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

                        {/* Emergency Exit - Independent row for visibility */}
                        {status === 'RUNNING' && (
                            <button
                                className="w-full mt-4 h-12 bg-red-900/40 hover:bg-red-600 text-red-100 border border-red-500/50 rounded-lg text-xs font-bold tracking-wide transition-all flex items-center justify-center gap-2"
                                onClick={handleEmergencyLiquidation}
                            >
                                <AlertTriangle size={14} />
                                EMERGENCY LIQUIDATION & KILL SWITCH
                            </button>
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

            {/* NEW: Strategy Signal Panel (Row 2) - Full Width */}
            <div className="lg:col-span-3">
                <StrategySignalPanel strategyState={strategyState} strategyName={strategyName} />
            </div>

            {/* 3. BOTTOM ROW: Chart Area (Real-time Tick Chart) - Full Width */}
            <div className="lg:col-span-3 lg:row-span-1 flex-1 bg-[#1e1e24] border border-white/5 rounded-xl flex flex-col min-h-[400px] overflow-hidden">
                {/* Tab Header */}
                <div className="flex border-b border-white/5 bg-black/20">
                    <div
                        className="flex items-center gap-2 px-4 py-3 text-sm font-bold transition-colors border-b-2 border-purple-500 text-purple-400 bg-purple-500/5"
                    >
                        <Activity size={14} />
                        Real-time Ticks {(() => {
                            const match = savedSymbols.find(s => s.code === strategyConfig.symbol);
                            return match && match.name ? `(${match.name})` : `(${strategyConfig.symbol})`;
                        })()}
                        {status === 'RUNNING' && <span className="ml-1 w-2 h-2 rounded-full bg-green-500 animate-pulse" />}
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
                            onIntervalChange={setSelectedInterval}
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

            {/* 4. TRANSACTION HISTORY SECTION (Inline) */}
            <div className="lg:col-span-3 mt-4">
                {!showHistoryView ? (
                    <div className="flex justify-center">
                        <button
                            className="w-full py-4 border-2 border-dashed border-gray-700 hover:border-blue-500/50 hover:bg-blue-500/5 rounded-xl text-gray-400 hover:text-blue-400 font-bold transition-all flex flex-col items-center gap-2"
                            onClick={() => {
                                setShowHistoryView(true);
                                setIsHistoryLoading(true);

                                // Construct Payload for Context-Aware History
                                const contextConfigs = configList.map(c => ({
                                    id: c.id || "temp_id",
                                    rank: c.rank,
                                    strategy_id: c.strategy_id || strategyName || "time_momentum",
                                    symbol: c.symbol,
                                    config: c.config_json || {}
                                }));

                                const payload = {
                                    configs: contextConfigs,
                                    symbol: strategyConfig.symbol || "KRW-BTC",
                                    interval: "30m", // Default
                                    days: 365,
                                    limit: 1000
                                };

                                getTradeHistoryContext(payload).then(data => {
                                    setHistoryData(data);
                                    setIsHistoryLoading(false);
                                }).catch(err => {
                                    console.error("Failed to load history:", err);
                                    setIsHistoryLoading(false);
                                });
                            }}
                        >
                            <List size={24} />
                            <span>Load Transaction History & Visual Analysis</span>
                            <span className="text-xs font-normal opacity-70">Fetches trade history with context-aware market data</span>
                        </button>
                    </div>
                ) : (
                    <div className="bg-[#1e1e24] border border-white/5 rounded-xl overflow-hidden flex flex-col min-h-[600px]">
                        <div className="px-6 py-4 border-b border-gray-800 bg-[#1f2937] flex justify-between items-center">
                            <h2 className="text-xl font-bold text-white flex items-center gap-2">
                                <List className="text-blue-400" />
                                Transaction History & Visual Context
                            </h2>
                            <button
                                onClick={() => {
                                    setShowHistoryView(false);
                                    setHistoryData(null); // Optional: Clear data to save memory
                                }}
                                className="text-gray-400 hover:text-red-400 text-sm font-bold flex items-center gap-1"
                            >
                                <X size={16} /> Close View
                            </button>
                        </div>

                        <div className="flex-1 relative min-h-[550px] bg-[#111827]">
                            {isHistoryLoading ? (
                                <div className="absolute inset-0 flex items-center justify-center">
                                    <div className="flex flex-col items-center gap-4">
                                        <Activity className="w-12 h-12 text-blue-500 animate-pulse" />
                                        <span className="text-gray-400 text-lg">Loading System Context...</span>
                                    </div>
                                </div>
                            ) : historyData ? (
                                <IntegratedAnalysis
                                    mode="real"
                                    trades={historyData.trades}
                                    backtestResult={historyData}
                                    strategiesConfig={configList}
                                    savedSymbols={savedSymbols}
                                />
                            ) : (
                                <div className="flex items-center justify-center h-full text-red-400">
                                    Failed to load data.
                                </div>
                            )}
                        </div>
                    </div>
                )}
            </div>

            {/* 5. EXECUTION LOGS (Moved to Bottom) */}
            <div className="lg:col-span-3 bg-[#1e1e24] border border-white/5 rounded-xl p-4 font-mono text-xs overflow-hidden flex flex-col min-h-[200px] max-h-[400px]">
                <div className="flex items-center gap-2 text-gray-400 mb-2 border-b border-white/5 pb-2">
                    <Terminal size={12} />
                    <span>Execution Logs</span>
                </div>
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
    );
};

export default LiveStrategyPanel;
