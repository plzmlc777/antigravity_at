import React, { useState, useEffect, useRef } from 'react';
import { Play, Square, Activity, AlertTriangle, Terminal, List } from 'lucide-react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { startLiveBot, stopLiveBot, getLiveStatus, getOHLCV } from '../api/client';
import ConfirmModal from './ConfirmModal';
import VisualBacktestChart from './VisualBacktestChart';

const LiveStrategyPanel = ({ strategyConfig, mode = 'TRADE' }) => {
    // State
    const [status, setStatus] = useState('IDLE'); // IDLE, RUNNING, STOPPED, ERROR
    const [sessionId, setSessionId] = useState(null);
    const [liveData, setLiveData] = useState(null);
    const [logs, setLogs] = useState([]);
    const [error, setError] = useState(null);
    const [activeTickTab, setActiveTickTab] = useState('realtime'); // 'realtime' | 'history'
    const [tickData, setTickData] = useState([]);
    const [isStopModalOpen, setIsStopModalOpen] = useState(false);

    // History View State
    const [historyViewData, setHistoryViewData] = useState({ data: [], trades: [] });
    const [isHistoryLoading, setIsHistoryLoading] = useState(false);

    // Polling Ref
    const pollInterval = useRef(null);

    // Initial Load checks if already running (TRADE only)
    useEffect(() => {
        if (mode === 'TRADE') {
            checkStatus();
            return () => stopPolling();
        } else {
            // Watch Mode: Set Running immediately to trigger WS
            setStatus('RUNNING');
            addLog("System", `Started watching ${strategyConfig.symbol}`);
        }
    }, [mode, strategyConfig.symbol]);

    const startPolling = () => {
        if (pollInterval.current) return;
        pollInterval.current = setInterval(checkStatus, 3000); // Poll every 3s
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

    // Helper: Logs
    const addLog = (source, msg) => {
        setLogs(prev => [{
            time: new Date().toLocaleTimeString(),
            source,
            msg
        }, ...prev].slice(0, 100));
    };

    // WebSocket for Real-time Data
    useEffect(() => {
        // Condition to connect logic
        if (status !== 'RUNNING') return;
        if (mode === 'TRADE' && !sessionId) return;

        console.log(`Connecting WS (${mode}) for`, strategyConfig.symbol);
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';

        let wsUrl;
        if (mode === 'WATCH') {
            wsUrl = `${wsProtocol}//${window.location.hostname}:8001/api/v1/live/ws/watch/${strategyConfig.symbol}`;
        } else {
            wsUrl = `${wsProtocol}//${window.location.hostname}:8001/api/v1/live/ws/${sessionId}`;
        }

        // Note: Using 8001 which is the default backend port. In prod, configure dynamically.

        let ws = new WebSocket(wsUrl);
        const MAX_TICKS = 100;

        ws.onopen = () => {
            addLog("System", "Real-time feed connected");
        };

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);

                if (data.type === 'tick') {
                    setLiveData(prev => ({
                        ...prev,
                        current_price: data.price
                    }));

                    setTickData(prev => {
                        // Safe tick time parsing
                        let timeStr = data.time;
                        if (data.time && data.time.includes('T')) {
                            timeStr = data.time.split('T')[1].split('.')[0];
                        }
                        const newTick = { time: timeStr, price: data.price };
                        const newData = [...prev, newTick];
                        if (newData.length > MAX_TICKS) return newData.slice(newData.length - MAX_TICKS);
                        return newData;
                    });

                } else if (data.type === 'history') {
                    const historyPoints = data.data.map(candle => {
                        const ts = String(candle.timestamp);
                        const timeStr = ts.length === 14
                            ? `${ts.substring(8, 10)}:${ts.substring(10, 12)}:${ts.substring(12, 14)}`
                            : ts;
                        return {
                            time: timeStr,
                            price: candle.close
                        };
                    });

                    setTickData(historyPoints.slice(-MAX_TICKS));
                    addLog("System", `Loaded ${historyPoints.length} historical candles.`);

                } else if (data.type === 'candle') {
                    addLog("Engine", `Candle Closed: ${data.data.close} @ ${data.data.timestamp}`);
                }
            } catch (err) {
                console.error("WS Parse Error", err);
            }
        };

        ws.onerror = (err) => {
            console.error("WS Error", err);
            addLog("Error", "WebSocket Connection Failed");
        };

        ws.onclose = () => {
            addLog("System", "Real-time feed disconnected");
        };

        return () => {
            if (ws) ws.close();
        };
    }, [sessionId, status, mode, strategyConfig.symbol]);

    // Fetch History Data when Tab changes to 'history'
    useEffect(() => {
        if (activeTickTab === 'history') {
            setIsHistoryLoading(true);
            (async () => {
                try {
                    const now = new Date();
                    const dateStr = now.toISOString().split('T')[0].replace(/-/g, '');

                    // Fetch Candles
                    let candles = await getOHLCV(strategyConfig.symbol, {
                        date: dateStr,
                        interval: '1m'
                    });

                    // Mock Fallback
                    if (!candles || candles.length === 0) {
                        const mockC = [];
                        let price = 72000;
                        const startTs = new Date(now);
                        startTs.setHours(9, 0, 0, 0);

                        for (let i = 0; i < 300; i++) {
                            price = price + (Math.random() - 0.5) * 100;
                            mockC.push({ time: (startTs.getTime() + i * 60000) / 1000, open: price, high: price + 50, low: price - 50, close: price, volume: 100 });
                        }
                        candles = mockC;
                    }

                    // Format Trades from live tick info
                    const formattedTrades = tickData.map(t => {
                        // Avoid crash if time format is unexpected
                        if (!t.time || typeof t.time !== 'string') return null;

                        const parts = t.time.split(':');
                        if (parts.length < 3) return null;

                        const [h, m, s] = parts.map(Number);
                        const tDate = new Date(now);
                        tDate.setHours(h, m, s, 0);
                        return {
                            ...t,
                            time: tDate.getTime() / 1000,
                            price: t.price,
                            type: t.type,
                            pnl_percent: t.pnl_percent
                        };
                    }).filter(Boolean).sort((a, b) => a.time - b.time);

                    setHistoryViewData({
                        data: candles,
                        trades: formattedTrades
                    });

                } catch (e) {
                    console.error("History Tab Fetch Error", e);
                } finally {
                    setIsHistoryLoading(false);
                }
            })();
        }
    }, [activeTickTab, tickData, strategyConfig.symbol]);



    // [TESTING] Inject Mock Data
    useEffect(() => {
        const mockTicks = [
            { time: "09:00:00", price: 72000, type: 'buy', pnl_percent: 0 },
            { time: "09:15:30", price: 72500, type: 'sell', pnl_percent: 0.0069 },
            { time: "10:30:00", price: 71800, type: 'buy', pnl_percent: 0 },
            { time: "11:45:10", price: 73000, type: 'sell', pnl_percent: 0.0167 },
            { time: "13:20:00", price: 72900, type: 'buy', pnl_percent: 0 }
        ];
        setTickData(mockTicks);
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

                <div className="flex-1 w-full min-h-[200px] relative">
                    <ResponsiveContainer width="100%" height="100%">
                        <AreaChart data={tickData.length > 0 ? tickData : [{ time: '', price: 0 }]}>
                            <defs>
                                <linearGradient id="colorPriceWatch" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                                    <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                                </linearGradient>
                            </defs>
                            <CartesianGrid strokeDasharray="3 3" stroke="#333" vertical={false} />
                            <XAxis dataKey="time" stroke="#555" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
                            <YAxis domain={['auto', 'auto']} stroke="#555" tick={{ fontSize: 10 }} width={60} tickFormatter={(val) => val.toLocaleString()} />
                            <Tooltip contentStyle={{ backgroundColor: '#111', border: '1px solid #333' }} itemStyle={{ color: '#fff' }} />
                            <Area type="monotone" dataKey="price" stroke="#3b82f6" fillOpacity={1} fill="url(#colorPriceWatch)" isAnimationActive={false} />
                        </AreaChart>
                    </ResponsiveContainer>
                </div>
            </div>
        );
    }

    return (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 h-full">
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

            {/* Left Col: Controls & Status */}
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

            {/* Right Col: Visualization & Logs */}
            <div className="lg:col-span-2 flex flex-col gap-6">
                {/* Chart Area (Real-time Tick Chart) */}
                <div className="flex-1 bg-[#1e1e24] border border-white/5 rounded-xl flex flex-col min-h-[300px] overflow-hidden">
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
                            Real-time Ticks
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
                    <div className="flex-1 p-4 relative min-h-[250px] flex flex-col">
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

                                <div className="flex-1 w-full h-full min-h-[250px]">
                                    <ResponsiveContainer width="100%" height="100%">
                                        <AreaChart data={tickData.length > 0 ? tickData : [{ time: '', price: 0 }]}>
                                            <defs>
                                                <linearGradient id="colorPrice" x1="0" y1="0" x2="0" y2="1">
                                                    <stop offset="5%" stopColor="#8884d8" stopOpacity={0.3} />
                                                    <stop offset="95%" stopColor="#8884d8" stopOpacity={0} />
                                                </linearGradient>
                                            </defs>
                                            <CartesianGrid strokeDasharray="3 3" stroke="#333" vertical={false} />
                                            <XAxis
                                                dataKey="time"
                                                stroke="#555"
                                                tick={{ fontSize: 10 }}
                                                interval="preserveStartEnd"
                                            />
                                            <YAxis
                                                domain={['auto', 'auto']}
                                                stroke="#555"
                                                tick={{ fontSize: 10 }}
                                                width={60}
                                                tickFormatter={(val) => val.toLocaleString()}
                                            />
                                            <Tooltip
                                                contentStyle={{ backgroundColor: '#111', border: '1px solid #333' }}
                                                itemStyle={{ color: '#fff' }}
                                            />
                                            <Area
                                                type="monotone"
                                                dataKey="price"
                                                stroke="#8884d8"
                                                fillOpacity={1}
                                                fill="url(#colorPrice)"
                                                isAnimationActive={false}
                                            />
                                        </AreaChart>
                                    </ResponsiveContainer>
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

                {/* Logs Console */}
                <div className="h-[200px] bg-black/40 border border-white/10 rounded-xl p-4 font-mono text-xs overflow-hidden flex flex-col">
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
        </div>
    );
};

export default LiveStrategyPanel;
