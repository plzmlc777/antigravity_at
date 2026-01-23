import React, { useState, useEffect, useRef } from 'react';
import { Play, Square, Activity, AlertTriangle, Terminal, List, X, Pause, Shield, ShieldOff, ShieldAlert } from 'lucide-react';
// import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { startLiveBot, stopLiveBot, getLiveStatus, getOHLCV, getTradeHistory, getTradeHistoryContext, toggleLiveOrders, liquidateLiveBot, getBalance } from '../api/client';
import IntegratedAnalysis from './IntegratedAnalysis';
import ConfirmModal from './ConfirmModal';
import VisualBacktestChart from './VisualBacktestChart';
import ActiveStrategiesPanel from './ActiveStrategiesPanel';
import StrategySignalPanel from './StrategySignalPanel';

const LiveStrategyPanel = ({ strategyConfig, mode = 'TRADE', configList = [], savedSymbols = [], currentRankIndex, onRankChange }) => {
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
                const found = await checkStatus();
                // Auto-start for Rank 1 if not already running
                if (!found && currentRankIndex === 0 && strategyConfig.symbol) {
                    console.log("[AUTO-START] Triggering auto-start for Rank 1 symbol:", strategyConfig.symbol);
                    addLog("System", `Auto-connecting Rank 1: ${strategyConfig.symbol}`);
                    handleStart();
                }
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



    // Fetch Initial Candles for Real-Time View (Hybrid Pattern: History + Live)
    useEffect(() => {
        // Skip fetch if symbol is missing or we are in STARTING state
        if (!strategyConfig.symbol || status === 'STARTING') return;

        // Deduplication Check: Skip if this specific combination was already fetched
        // We ignore 'status' here because history doesn't care about bot status, only symbol/interval.
        if (lastFetchRef.current.symbol === strategyConfig.symbol &&
            lastFetchRef.current.interval === selectedInterval) {
            console.log(`[DEBUG] Skipping redundant history fetch for ${strategyConfig.symbol} (${selectedInterval})`);
            return;
        }

        // Log status to debug
        console.log(`[DEBUG] History Fetch Effect Triggered. Status: ${status}, Symbol: ${strategyConfig.symbol}, Interval: ${selectedInterval}`);

        // Update Ref immediately to prevent race conditions during async await
        lastFetchRef.current = { symbol: strategyConfig.symbol, interval: selectedInterval, status: status };

        // Clear existing candles immediately to indicate loading/change
        setRealTimeCandles([]);

        (async () => {
            try {
                // 1. Calculate Today's Date in KST (YYYYMMDD)
                const now = new Date();
                const kstOffset = 9 * 60; // KST is UTC+9
                const utc = now.getTime() + (now.getTimezoneOffset() * 60000);
                const kstDate = new Date(utc + (kstOffset * 60000));
                const dateStr = kstDate.toISOString().split('T')[0].replace(/-/g, '');

                addLog("System", `[DEBUG] REQ: ${selectedInterval} | Date: ${dateStr}`);
                console.log(`[DEBUG] Requesting ${selectedInterval} for ${strategyConfig.symbol} on ${dateStr}`);

                // 2. Fetch History (Today's candles)
                const candles = await getOHLCV(strategyConfig.symbol, {
                    date: dateStr,
                    interval: selectedInterval
                });

                console.log("[DEBUG] Response:", candles);

                // 3. Update State
                if (candles && candles.length > 0) {
                    setRealTimeCandles(candles);
                    addLog("System", `[DEBUG] OK: Loaded ${candles.length} candles. Last: ${candles[candles.length - 1].time}`);

                    // Check if we also have current price from liveData
                    if (liveData && liveData.current_price) {
                        // Optional: Append/Update last candle with current price if newer?
                        // Usually WS will handle the next update.
                    }
                } else {
                    // Fallback: If no history (e.g. market just opened or error), try current price
                    addLog("System", `[DEBUG] EMPTY Response for ${selectedInterval} on ${dateStr}`);
                    console.warn("[DEBUG] Empty history response");

                    if (liveData && liveData.current_price) {
                        const nowTs = Math.floor(Date.now() / 1000);
                        setRealTimeCandles([{
                            time: nowTs,
                            open: liveData.current_price,
                            high: liveData.current_price,
                            low: liveData.current_price,
                            close: liveData.current_price,
                            volume: 0
                        }]);
                        addLog("System", "No history found, starting with Current Price.");
                    } else {
                        setRealTimeCandles([]);
                        addLog("System", "No history data. Waiting for stream...");
                    }
                }
            } catch (e) {
                console.error("Init Error", e);
                addLog("Error", "Failed to fetch history");
                // Fallback to empty
                setRealTimeCandles([]);
            }
        })();
    }, [status, strategyConfig.symbol, selectedInterval]); // Removed liveData dependency to prevent re-fetching loop


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

            const payload = {
                symbol: strategyConfig.symbol,
                strategy_name: "time_momentum",
                strategy_config: strategyConfig,
                initial_capital: parseFloat(inputCapital) || 0
            };

            const res = await startLiveBot(payload);
            setSessionId(res.session_id);
            setStatus('RUNNING');
            startPolling();

            addLog("System", `Session Started: ${res.session_id}`);

        } catch (err) {
            setError(err.response?.data?.detail || err.message);
            setStatus('ERROR');
            addLog("Error", err.message);
        }
    };

    const handleToggleOrders = async () => {
        if (!sessionId) return;
        try {
            const newState = !liveData?.orders_enabled;
            await toggleLiveOrders(sessionId, newState);
            setLiveData(prev => ({ ...prev, orders_enabled: newState }));
            addLog("System", `Orders ${newState ? 'Enabled' : 'Disabled'} by User`);
        } catch (err) {
            setError(err.message);
        }
    };

    const handleEmergencyLiquidation = async () => {
        if (!sessionId) return;
        if (!window.confirm("EMERGENCY: Do you want to sell ALL holdings and pause trading?")) return;

        try {
            await liquidateLiveBot(sessionId);
            setLiveData(prev => ({ ...prev, orders_enabled: false }));
            addLog("Emergency", "KILL SWITCH: Liquidating all holdings and pausing orders.");
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
            addLog("System", "Real-time feed connected");
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

                } else if (data.type === 'history' || data.type === 'candle') {
                    // Logic to handle history push if needed
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
                    />
                </div>
            )}

            {/* Modal */}
            <ConfirmModal
                isOpen={isStopModalOpen}
                onClose={() => setIsStopModalOpen(false)}
                onConfirm={async () => {
                    try {
                        await stopLiveBot(sessionId);
                        setStatus('STOPPED');
                        stopPolling();
                        addLog("System", "Session Stopped by User");
                    } catch (err) {
                        setError(err.message);
                    }
                }}
                title="Stop Live Trading?"
                message="Are you sure you want to stop the live trading session? Pending orders might be cancelled."
                confirmText="Stop Session"
                isDanger={true}
            />

            {/* 1. TOP ROW: Live Operation Controls (Combined & Full Width) */}
            <div className="lg:col-span-3 relative">
                <div className="bg-[#1e1e24] border border-white/5 rounded-xl p-6 relative overflow-hidden">
                    {/* Header */}
                    <div className="flex items-center gap-3 mb-6">
                        <Activity className={`w-5 h-5 ${status === 'RUNNING' ? 'text-green-400 animate-pulse' : 'text-gray-500'}`} />
                        <h2 className="font-bold text-lg text-white">Live Operation</h2>
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
                        </div>
                    </div>

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
                                                if (availableBalance !== null && inputCapital > availableBalance) {
                                                    alert("Cannot enable LIVE MODE: Allocated capital exceeds actual account balance. Funds are insufficient for real trading.");
                                                    return;
                                                }
                                                handleToggleOrders();
                                            }}
                                            className={`h-14 flex items-center justify-center gap-2 text-[10px] font-bold tracking-wide rounded-lg border transition-all ${liveData?.orders_enabled
                                                ? 'bg-transparent border-red-500/50 text-red-400 hover:bg-red-500/10'
                                                : (availableBalance !== null && inputCapital > availableBalance)
                                                    ? 'bg-gray-800 border-gray-700 text-gray-500 cursor-not-allowed opacity-50'
                                                    : 'bg-green-600/20 border-green-500 text-green-400 hover:bg-green-600/30'
                                                }`}
                                        >
                                            {liveData?.orders_enabled ? (
                                                <><ShieldOff size={14} /> PAPER MODE</>
                                            ) : (
                                                <><Shield size={14} /> LIVE MODE</>
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
                <StrategySignalPanel strategyState={strategyState} />
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
                                    <select
                                        value={currentRankIndex}
                                        onChange={(e) => onRankChange(parseInt(e.target.value))}
                                        className="bg-gray-900 border border-gray-600 rounded text-[10px] px-2 py-1 text-gray-300 outline-none focus:border-blue-500 hover:bg-gray-800 transition-colors mr-2"
                                    >
                                        {configList.map((cfg, idx) => {
                                            if (!cfg.is_active) return null;
                                            const symbolMatch = savedSymbols.find(s => s.code === cfg.symbol);
                                            const name = symbolMatch ? symbolMatch.name : cfg.symbol;
                                            return (
                                                <option key={idx} value={idx}>
                                                    Rank {idx + 1}: {name}
                                                </option>
                                            );
                                        })}
                                    </select>
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
                                    strategy_id: c.strategy_id || "time_momentum",
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
