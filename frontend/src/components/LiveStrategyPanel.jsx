import React, { useState, useEffect, useRef } from 'react';
import { Play, Square, Activity, AlertTriangle, Terminal, List } from 'lucide-react';
// import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { startLiveBot, stopLiveBot, getLiveStatus, getOHLCV } from '../api/client';
import ConfirmModal from './ConfirmModal';
import VisualBacktestChart from './VisualBacktestChart';
import ActiveStrategiesPanel from './ActiveStrategiesPanel';

const LiveStrategyPanel = ({ strategyConfig, mode = 'TRADE', configList = [], savedSymbols = [] }) => {
    // State
    const [status, setStatus] = useState('IDLE'); // IDLE, RUNNING, STOPPED, ERROR
    const [sessionId, setSessionId] = useState(null);
    const [liveData, setLiveData] = useState(null);
    const [logs, setLogs] = useState([]);
    const [error, setError] = useState(null);
    const [activeTickTab, setActiveTickTab] = useState('realtime'); // 'realtime' | 'history'
    const [tickData, setTickData] = useState([]); // Running list of recent ticks for UI (optional)
    const [isStopModalOpen, setIsStopModalOpen] = useState(false);

    // Real-Time Candles State
    const [realTimeCandles, setRealTimeCandles] = useState([]);
    const [selectedInterval, setSelectedInterval] = useState('1m');

    // History View State
    const [historyViewData, setHistoryViewData] = useState({ data: [], trades: [] });
    const [isHistoryLoading, setIsHistoryLoading] = useState(false);

    // Polling Ref
    const pollInterval = useRef(null);

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
        if (mode === 'TRADE') {
            checkStatus();
            return () => stopPolling();
        } else {
            setStatus('RUNNING');
            addLog("System", `Started watching ${strategyConfig.symbol}`);
        }
    }, [mode, strategyConfig.symbol]);

    // Fetch Initial Candles for Real-Time View
    useEffect(() => {
        if (status === 'RUNNING' && strategyConfig.symbol) {
            (async () => {
                try {
                    const now = new Date();
                    const dateStr = now.toISOString().split('T')[0].replace(/-/g, '');

                    // Clear previous data first explicitly to properly trigger Chart reset
                    setRealTimeCandles([]);

                    const candles = await getOHLCV(strategyConfig.symbol, { date: dateStr, interval: selectedInterval });

                    // Format for Chart
                    const formatted = candles.map(c => ({
                        time: c.time, // Unix TS
                        open: c.open,
                        high: c.high,
                        low: c.low,
                        close: c.close,
                        volume: c.volume
                    }));

                    setRealTimeCandles(formatted);
                } catch (e) {
                    console.error("Failed to load initial candles", e);
                    // Fallback Mock Data for UI Verification if Backend 404
                    const now = Math.floor(Date.now() / 1000);
                    const unit = selectedInterval.slice(-1);
                    const val = parseInt(selectedInterval.slice(0, -1));
                    let step = 60;
                    if (unit === 'm') step = val * 60;
                    else if (unit === 'h') step = val * 3600;
                    else if (unit === 'd') step = val * 86400;

                    const mockFallback = [];
                    for (let i = 0; i < 50; i++) {
                        mockFallback.push({
                            time: now - ((50 - i) * step),
                            open: 70000 + i * 10,
                            high: 70000 + i * 10 + 50,
                            low: 70000 + i * 10 - 50,
                            close: 70000 + i * 10 + 20,
                            volume: 1000
                        });
                    }
                    setRealTimeCandles(mockFallback);
                    addLog("System", `Loaded Mock Data for ${selectedInterval} (Backend Unavailable)`);
                }
            })();
        }
    }, [status, strategyConfig.symbol, selectedInterval]);


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
            } else if (status === 'RUNNING') {
                setStatus('STOPPED');
                stopPolling();
            }
        } catch (err) {
            console.error("Live Status Error", err);
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
                initial_capital: 10000000
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

    // History Tab Fetch Logic (Unchanged)
    useEffect(() => {
        if (activeTickTab === 'history') {
            setIsHistoryLoading(true);
            (async () => {
                try {
                    const now = new Date();
                    const dateStr = now.toISOString().split('T')[0].replace(/-/g, '');
                    let candles = await getOHLCV(strategyConfig.symbol, { date: dateStr, interval: '1m' });

                    // Mock Fallback (Removed or kept minimal)
                    if (!candles || candles.length === 0) {
                        // Optional: Add empty check or mock logic if strict testing needed
                    }

                    // Prepare Trades (Mock or Real) from tickData context if available
                    // For now, just show candles.
                    setHistoryViewData({ data: candles, trades: [] });

                } catch (e) {
                    console.error("History Tab Error", e);
                } finally {
                    setIsHistoryLoading(false);
                }
            })();
        }
    }, [activeTickTab, strategyConfig.symbol]);



    // [TESTING] Inject Mock Data
    useEffect(() => {
        // Mock Ticks for Tick List
        const mockTicks = [
            { time: "09:00:00", price: 72000, type: 'buy', pnl_percent: 0 },
            { time: "09:15:30", price: 72500, type: 'sell', pnl_percent: 0.0069 },
            { time: "10:30:00", price: 71800, type: 'buy', pnl_percent: 0 },
            { time: "11:45:10", price: 73000, type: 'sell', pnl_percent: 0.0167 },
            { time: "13:20:00", price: 72900, type: 'buy', pnl_percent: 0 }
        ];
        setTickData(mockTicks);

        // Mock Candles for Chart (Derived from mock ticks or separate mock)
        // Only inject if realTimeCandles is empty to avoid overwriting real data
        if (realTimeCandles.length === 0) {
            const now = Math.floor(Date.now() / 1000);
            const mockCandles = [
                { time: now - 300, open: 71900, high: 72100, low: 71800, close: 72000, volume: 1000 },
                { time: now - 240, open: 72000, high: 72200, low: 71950, close: 72100, volume: 1500 },
                { time: now - 180, open: 72100, high: 72600, low: 72000, close: 72500, volume: 2000 },
                { time: now - 120, open: 72500, high: 72550, low: 71700, close: 71800, volume: 1200 },
                { time: now - 60, open: 71800, high: 73100, low: 71800, close: 73000, volume: 3000 },
                { time: now, open: 73000, high: 73050, low: 72850, close: 72900, volume: 500 }
            ];
            setRealTimeCandles(mockCandles);
            addLog("System", "Mock Candles Injected for Testing");
        }

        addLog("System", "Mock Data Injected for Testing");
    }, []);



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
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 h-full grid-rows-[auto_1fr]">
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

            {/* 1. TOP ROW LEFT: Controls & Status */}
            <div className="lg:col-span-1 space-y-6">
                {/* Status Card */}
                <div className="bg-[#1e1e24] border border-white/5 rounded-xl p-6 relative overflow-hidden">
                    <div className="flex justify-between items-start mb-4">
                        <div className="flex items-center gap-3">
                            <Activity className={`w-5 h-5 ${status === 'RUNNING' ? 'text-green-400 animate-pulse' : 'text-gray-500'}`} />
                            <h2 className="font-bold text-lg text-white">Live Operation</h2>
                        </div>
                        <span className={`px-3 py-1 rounded-full text-xs font-bold border ${getStatusColor()}`}>
                            {status}
                        </span>
                    </div>

                    {/* Stats Summary */}
                    {liveData && (
                        <div className="grid grid-cols-2 gap-4 mb-6">
                            <div className="bg-black/20 p-3 rounded-lg">
                                <div className="text-gray-400 text-xs">Current Price</div>
                                <div className="text-xl font-mono text-white">
                                    {liveData.current_price?.toLocaleString()}
                                </div>
                            </div>
                            <div className="bg-black/20 p-3 rounded-lg">
                                <div className="text-gray-400 text-xs">Unrealized PnL</div>
                                <div className={`text-xl font-mono ${liveData.pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                    {liveData.pnl > 0 ? '+' : ''}{liveData.pnl?.toLocaleString()}
                                </div>
                            </div>
                        </div>
                    )}

                    {/* Controls */}
                    <div className="flex gap-3">
                        {status !== 'RUNNING' ? (
                            <button
                                onClick={handleStart}
                                disabled={status === 'STARTING'}
                                className="flex-1 flex items-center justify-center gap-2 bg-green-600 hover:bg-green-500 text-white font-bold py-3 rounded-lg transition-all disabled:opacity-50"
                            >
                                <Play size={18} />
                                START LIVE
                            </button>
                        ) : (
                            <button
                                onClick={() => setIsStopModalOpen(true)}
                                className="flex-1 flex items-center justify-center gap-2 bg-red-600 hover:bg-red-500 text-white font-bold py-3 rounded-lg transition-all"
                            >
                                <Square size={18} />
                                STOP
                            </button>
                        )}
                    </div>

                    {error && (
                        <div className="mt-4 p-3 bg-red-500/10 border border-red-500/20 rounded text-red-400 text-xs break-words">
                            <div className="flex items-center gap-2 font-bold mb-1">
                                <AlertTriangle size={12} /> Error
                            </div>
                            {error}
                        </div>
                    )}
                </div>

                {/* Kill Switch (To be implemented fully in Phase 4) */}
                <div className="bg-red-900/10 border border-red-500/20 rounded-xl p-4">
                    <div className="flex items-center gap-2 text-red-400 font-bold mb-2">
                        <AlertTriangle size={16} /> EMERGENCY
                    </div>
                    <button
                        className="w-full bg-red-900/50 hover:bg-red-900 text-red-200 border border-red-500/50 rounded py-2 text-sm font-bold transition-colors"
                        onClick={() => alert("Kill Switch Logic Pending (Phase 4)")}
                    >
                        LIQUIDATE ALL & STOP
                    </button>
                </div>
            </div>

            {/* 2. TOP ROW RIGHT: Logs Console (Moved Here) */}
            <div className="lg:col-span-2 bg-[#1e1e24] border border-white/5 rounded-xl p-4 font-mono text-xs overflow-hidden flex flex-col h-full max-h-[350px]">
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

            {/* 3. BOTTOM ROW: Chart Area (Real-time Tick Chart) - Full Width */}
            <div className="lg:col-span-3 lg:row-span-1 flex-1 bg-[#1e1e24] border border-white/5 rounded-xl flex flex-col min-h-[400px] overflow-hidden">
                {/* Tab Header */}
                <div className="flex border-b border-white/5 bg-black/20">
                    <button
                        onClick={() => setActiveTickTab('realtime')}
                        className={`flex items-center gap-2 px-4 py-3 text-sm font-bold transition-colors border-b-2 ${activeTickTab === 'realtime'
                            ? 'border-purple-500 text-purple-400 bg-purple-500/5'
                            : 'border-transparent text-gray-500 hover:text-gray-300 hover:bg-white/5'
                            }`}
                    >
                        <Activity size={14} />
                        Real-time Ticks {(() => {
                            const match = savedSymbols.find(s => s.code === strategyConfig.symbol);
                            return match && match.name ? `(${match.name})` : `(${strategyConfig.symbol})`;
                        })()}
                        {status === 'RUNNING' && <span className="ml-1 w-2 h-2 rounded-full bg-green-500 animate-pulse" />}
                    </button>
                    <button
                        onClick={() => setActiveTickTab('history')}
                        className={`flex items-center gap-2 px-4 py-3 text-sm font-bold transition-colors border-b-2 ${activeTickTab === 'history'
                            ? 'border-blue-500 text-blue-400 bg-blue-500/5'
                            : 'border-transparent text-gray-500 hover:text-gray-300 hover:bg-white/5'
                            }`}
                    >
                        <List size={14} />
                        History Ticks
                    </button>
                </div>

                {/* Tab Content */}
                <div className="flex-1 p-4 relative min-h-[350px] flex flex-col">
                    {activeTickTab === 'realtime' ? (
                        <>
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
                                />
                            </div>
                        </>
                    ) : (
                        // HISTORY TAB: Direct Visual Chart
                        <div className="flex-1 relative bg-black/10 min-h-[400px]">
                            {isHistoryLoading && (
                                <div className="absolute inset-0 flex items-center justify-center pointer-events-none z-20">
                                    <span className="text-blue-400 font-bold bg-black/80 px-4 py-2 rounded">Loading...</span>
                                </div>
                            )}
                            <VisualBacktestChart
                                data={historyViewData.data}
                                trades={historyViewData.trades}
                                showOnlyPnl={true}
                            />
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};

export default LiveStrategyPanel;
