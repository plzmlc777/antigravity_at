import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar, Cell, ReferenceLine, ComposedChart, LabelList } from 'recharts';
import Card from '../components/common/Card';
import SymbolSelector from '../components/SymbolSelector'; // Import
import VisualBacktestChart from '../components/VisualBacktestChart';

const StrategyView = () => {
    // Symbol State
    const [currentSymbol, setCurrentSymbol] = useState(() => localStorage.getItem('lastSymbol') || '005930');
    const [savedSymbols, setSavedSymbols] = useState(() => {
        const saved = localStorage.getItem('savedSymbols');
        if (!saved) return [{ code: '005930', name: '삼성전자' }, { code: '000660', name: 'SK하이닉스' }];
        try {
            return JSON.parse(saved);
        } catch {
            return [{ code: '005930', name: '삼성전자' }, { code: '000660', name: 'SK하이닉스' }];
        }
    });

    const [strategies, setStrategies] = useState([]);
    const [selectedStrategy, setSelectedStrategy] = useState(null);
    const [backtestResult, setBacktestResult] = useState(null);
    const [isGenerating, setIsGenerating] = useState(false);
    const [aiPrompt, setAiPrompt] = useState("");
    const [isLoading, setIsLoading] = useState(false);
    const [showChart, setShowChart] = useState(false); // Toggle for Visual Chart

    // Dynamic Config State
    const [config, setConfig] = useState({});

    // Backtest Settings
    const [fromDate, setFromDate] = useState(""); // YYYY-MM-DD
    const [initialCapital, setInitialCapital] = useState(() => {
        const saved = localStorage.getItem('initialCapital');
        return saved ? parseInt(saved, 10) : 10000000;
    });

    // Save to LocalStorage
    useEffect(() => {
        localStorage.setItem('lastSymbol', currentSymbol);
    }, [currentSymbol]);

    useEffect(() => {
        localStorage.setItem('savedSymbols', JSON.stringify(savedSymbols));
    }, [savedSymbols]);

    useEffect(() => {
        localStorage.setItem('initialCapital', initialCapital.toString());
    }, [initialCapital]);

    // Load Strategy Config on Selection
    useEffect(() => {
        if (selectedStrategy) {
            const savedConfig = localStorage.getItem(`strategyConfig_${selectedStrategy.id}`);
            if (savedConfig) {
                try {
                    setConfig(JSON.parse(savedConfig));
                } catch {
                    setConfig({});
                }
            } else {
                setConfig({});
            }
        }
    }, [selectedStrategy]);

    // Save Strategy Config on Change
    useEffect(() => {
        if (selectedStrategy && Object.keys(config).length > 0) {
            localStorage.setItem(`strategyConfig_${selectedStrategy.id}`, JSON.stringify(config));
        }
    }, [config, selectedStrategy]);

    const handleConfigChange = (key, value) => {
        setConfig(prev => ({ ...prev, [key]: value }));
    };

    // 4. Persistence & Initialization
    useEffect(() => {
        fetchStrategies();
    }, []);

    const fetchStrategies = async () => {
        try {
            const res = await axios.get('/api/v1/strategies/list');
            setStrategies(res.data);

            if (res.data.length > 0) {
                // Try to restore last selected strategy
                const savedId = localStorage.getItem('lastStrategyId');
                let target = null;

                if (savedId) {
                    target = res.data.find(s => s.id === savedId);
                }

                // Fallback to first if saved not found or not set
                if (!target) {
                    target = res.data[0];
                }

                setSelectedStrategy(target);
            }
        } catch (e) {
            console.error(e);
        }
    };

    const [backtestStatus, setBacktestStatus] = useState({ status: 'idle', message: 'Ready to Backtest' });

    const runBacktest = async (strategyId) => {
        setIsLoading(true);
        setBacktestStatus({ status: 'running', message: 'Initializing Strategy...' });
        setBacktestResult(null); // Clear previous results
        setShowChart(false);

        try {
            const payload = {
                symbol: currentSymbol,
                from_date: fromDate,
                initial_capital: initialCapital,
                interval: currentInterval,
                config: config
            };

            setBacktestStatus({ status: 'running', message: `Running Backtest on ${currentSymbol}...` });

            const res = await axios.post(`/api/v1/strategies/${strategyId}/backtest`, payload);
            setBacktestResult(res.data);
            setBacktestStatus({ status: 'success', message: 'Backtest Completed' });

        } catch (e) {
            console.error(e);
            let errorMsg = "Backtest Failed";
            if (e.response && e.response.data && e.response.data.detail) {
                errorMsg = `Error: ${e.response.data.detail}`;
            } else if (e.message) {
                errorMsg = `Error: ${e.message}`;
            }
            setBacktestStatus({ status: 'error', message: errorMsg });
        } finally {
            setIsLoading(false);
        }
    };

    const handleAiGenerate = async () => {
        if (!aiPrompt) return;
        setIsGenerating(true);
        try {
            const res = await axios.post('/api/v1/strategies/generate', { prompt: aiPrompt });
            setStrategies([...strategies, res.data]);
            setSelectedStrategy(res.data);
            setAiPrompt("");
        } catch (e) {
            alert("Generation failed");
        } finally {
            setIsGenerating(false);
        }
    };

    // ... (Data Management logic stays here) ...
    // Note: Implicitly preserving the gap where lines 106-175 were, but current ReplaceFileContent needs context.
    // The previous block ended at handleAiGenerate (around line 103). 
    // I need to be careful not to overwrite the data management hooks if I use a large range.
    // So I will only replace runBacktest and the render part separately? 
    // No, I can replace runBacktest first, then the render part.

    // WAIT, I need to insert the state definition too. 
    // It's safer to do 2 chunks: one for state+function, one for render.
    // Let's split this tool call into 2 chunks.


    // 5. Data Management & Persistence State
    const [dataStatus, setDataStatus] = useState({ is_fresh: false, last_updated: null, count: 0 });
    const [isFetchingData, setIsFetchingData] = useState(false);
    const [currentInterval, setCurrentInterval] = useState(() => localStorage.getItem('lastInterval') || "1m");
    const [fetchMessage, setFetchMessage] = useState(null);
    // fromDate state moved to top


    // Persistence Effects
    useEffect(() => {
        localStorage.setItem('lastInterval', currentInterval);
    }, [currentInterval]);

    useEffect(() => {
        if (selectedStrategy) {
            localStorage.setItem('lastStrategyId', selectedStrategy.id);
        }
    }, [selectedStrategy]);

    // Check Data Status
    useEffect(() => {
        checkDataStatus();
        setFetchMessage(null);
    }, [currentSymbol, currentInterval]);

    const checkDataStatus = async () => {
        try {
            const res = await axios.get(`/api/v1/market-data/status/${currentSymbol}`, {
                params: { interval: currentInterval }
            });
            setDataStatus(res.data);

            // Auto-set Start Date to Data Start
            if (res.data.start_date) {
                // Server returns YY.MM.DD -> Convert to YYYY-MM-DD for input type="date"
                const parts = res.data.start_date.split('.');
                if (parts.length === 3) {
                    const yyyy = `20${parts[0]}`;
                    const mm = parts[1];
                    const dd = parts[2];
                    setFromDate(`${yyyy}-${mm}-${dd}`);
                }
            }
        } catch (e) {
            console.error("Failed to check data status", e);
        }
    };

    const handleFetchData = async () => {
        setIsFetchingData(true);
        setFetchMessage(`Updating...`);
        try {
            const res = await axios.post(`/api/v1/market-data/fetch/${currentSymbol}`, {
                interval: currentInterval,
                days: 3650 // Request ~10 years to hit 10k limit
            });

            const added = res.data.added;
            setFetchMessage(null);

            const resultMsg = added > 0 ? `Updated (+${added})` : `Up to date (+0)`;

            await checkDataStatus();
            setFetchMessage(resultMsg);

        } catch (e) {
            setFetchMessage("Failed");
            setTimeout(() => setFetchMessage(null), 3000);
        } finally {
            setIsFetchingData(false);
        }
    };

    return (
        <div className="flex flex-col gap-6 pb-10">
            {/* Top Bar: Selector & Actions */}
            <Card className="shrink-0 z-20">
                <div className="flex flex-col gap-4">
                    {/* Row 1: Strategy Selection */}
                    <div className="flex flex-col md:flex-row items-center gap-4 w-full">
                        <div className="relative w-full md:max-w-md">
                            <label className="text-xs text-gray-400 absolute -top-2 left-2 bg-[#0f111a] px-1">Select Strategy</label>
                            <select
                                value={selectedStrategy?.id || ''}
                                onChange={(e) => {
                                    const strat = strategies.find(s => s.id === e.target.value);
                                    setSelectedStrategy(strat);
                                    setBacktestResult(null);
                                }}
                                className="w-full bg-black/40 border border-white/20 rounded-lg px-4 py-3 text-white appearance-none focus:border-blue-500 outline-none cursor-pointer"
                            >
                                {strategies.map(strat => (
                                    <option key={strat.id} value={strat.id} className="bg-slate-900 text-white">
                                        {strat.name}
                                    </option>
                                ))}
                            </select>
                            <div className="absolute right-4 top-1/2 -translate-y-1/2 pointer-events-none text-gray-400">
                                ▼
                            </div>
                        </div>
                        {selectedStrategy && (
                            <div className="hidden md:block text-sm text-gray-400 border-l border-white/10 pl-4 h-10 flex items-center flex-1">
                                {selectedStrategy.description}
                            </div>
                        )}
                    </div>


                </div>
            </Card>

            {/* Main Content Area (No Scroll Container) */}
            <div className="space-y-6 pb-20">
                {selectedStrategy ? (
                    <>
                        {/* Configuration Panel - Full Width & Prominent */}
                        <Card title="Strategy Configuration" className="border border-purple-500/50 shadow-lg shadow-purple-900/20">
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                                {/* 1. Target Data */}
                                <div>
                                    <h4 className="text-sm font-bold text-gray-300 mb-3 flex items-center gap-2">
                                        <div className="w-6 h-6 rounded bg-blue-500/20 text-blue-400 flex items-center justify-center text-xs">1</div>
                                        Target Asset
                                    </h4>
                                    <div className="bg-black/20 p-4 rounded-lg border border-white/5 h-full">
                                        <SymbolSelector
                                            currentSymbol={currentSymbol}
                                            setCurrentSymbol={setCurrentSymbol}
                                            savedSymbols={savedSymbols}
                                            setSavedSymbols={setSavedSymbols}
                                        />
                                    </div>
                                </div>

                                {/* 2. Parameters */}
                                <div>
                                    <h4 className="text-sm font-bold text-gray-300 mb-3 flex items-center gap-2">
                                        <div className="w-6 h-6 rounded bg-purple-500/20 text-purple-400 flex items-center justify-center text-xs">2</div>
                                        Parameters
                                    </h4>
                                    <div className="bg-black/20 p-4 rounded-lg border border-white/5">
                                        {selectedStrategy.id === 'time_momentum' ? (
                                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                                                <div>
                                                    <label className="text-xs text-gray-500 mb-1 block">Start Time</label>
                                                    <select
                                                        className="w-full bg-black/40 border border-white/10 rounded px-3 py-2 text-sm text-white focus:border-blue-500 outline-none transition-colors appearance-none cursor-pointer"
                                                        value={config.start_time || "09:00"}
                                                        onChange={(e) => handleConfigChange('start_time', e.target.value)}
                                                    >
                                                        {Array.from({ length: 48 }).map((_, i) => {
                                                            const h = Math.floor(i / 2);
                                                            const m = i % 2 === 0 ? "00" : "30";
                                                            const timeStr = `${h.toString().padStart(2, '0')}:${m}`;
                                                            return <option key={timeStr} value={timeStr} className="bg-slate-900">{timeStr}</option>;
                                                        })}
                                                    </select>
                                                </div>
                                                <div>
                                                    <label className="text-xs text-gray-500 mb-1 block">Delay (Minutes)</label>
                                                    <input
                                                        type="number"
                                                        className="w-full bg-black/40 border border-white/10 rounded px-3 py-2 text-sm text-white focus:border-blue-500 outline-none transition-colors appearance-none [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
                                                        value={config.delay_minutes || 10}
                                                        onChange={(e) => handleConfigChange('delay_minutes', parseInt(e.target.value))}
                                                    />
                                                </div>
                                                <div>
                                                    <label className="text-xs text-gray-500 mb-1 block">Direction</label>
                                                    <select
                                                        className="w-full bg-black/40 border border-white/10 rounded px-3 py-2 text-sm text-white focus:border-blue-500 outline-none transition-colors appearance-none cursor-pointer"
                                                        value={config.direction || "rise"}
                                                        onChange={(e) => handleConfigChange('direction', e.target.value)}
                                                    >
                                                        <option value="rise" className="bg-slate-900">Rise (Momentum)</option>
                                                        <option value="fall" className="bg-slate-900">Fall (Dip Buying)</option>
                                                    </select>
                                                </div>
                                                <div>
                                                    <label className="text-xs text-gray-500 mb-1 block">Target Pump/Dip (%)</label>
                                                    <input
                                                        type="number" step="0.1" min="0"
                                                        className="w-full bg-black/40 border border-white/10 rounded px-3 py-2 text-sm text-white focus:border-blue-500 outline-none transition-colors appearance-none [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
                                                        value={Math.abs(config.target_percent || 2)}
                                                        onChange={(e) => handleConfigChange('target_percent', parseFloat(e.target.value))}
                                                    />
                                                </div>
                                                <div>
                                                    <label className="text-xs text-gray-500 mb-1 block">Stop Loss (%)</label>
                                                    <input
                                                        type="number" step="0.1" min="0"
                                                        className="w-full bg-black/40 border border-white/10 rounded px-3 py-2 text-sm text-white focus:border-blue-500 outline-none transition-colors appearance-none [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
                                                        value={Math.abs(config.safety_stop_percent || 3)}
                                                        onChange={(e) => handleConfigChange('safety_stop_percent', parseFloat(e.target.value))}
                                                    />
                                                </div>
                                                <div>
                                                    <label className="text-xs text-gray-500 mb-1 block">Trailing Start (%)</label>
                                                    <input
                                                        type="number" step="0.1"
                                                        className="w-full bg-black/40 border border-white/10 rounded px-3 py-2 text-sm text-white focus:border-blue-500 outline-none transition-colors appearance-none [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
                                                        value={config.trailing_start_percent || 5}
                                                        onChange={(e) => handleConfigChange('trailing_start_percent', parseFloat(e.target.value))}
                                                    />
                                                </div>
                                                <div>
                                                    <label className="text-xs text-gray-500 mb-1 block">Trailing Drop (%)</label>
                                                    <input
                                                        type="number" step="0.1"
                                                        className="w-full bg-black/40 border border-white/10 rounded px-3 py-2 text-sm text-white focus:border-blue-500 outline-none transition-colors appearance-none [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
                                                        value={config.trailing_stop_drop || 2}
                                                        onChange={(e) => handleConfigChange('trailing_stop_drop', parseFloat(e.target.value))}
                                                    />
                                                </div>
                                                <div>
                                                    <label className="text-xs text-gray-500 mb-1 block">Stop Time</label>
                                                    <select
                                                        className="w-full bg-black/40 border border-white/10 rounded px-3 py-2 text-sm text-white focus:border-blue-500 outline-none transition-colors appearance-none cursor-pointer"
                                                        value={config.stop_time || "15:00"}
                                                        onChange={(e) => handleConfigChange('stop_time', e.target.value)}
                                                    >
                                                        {Array.from({ length: 48 }).map((_, i) => {
                                                            const h = Math.floor(i / 2);
                                                            const m = i % 2 === 0 ? "00" : "30";
                                                            const timeStr = `${h.toString().padStart(2, '0')}:${m}`;
                                                            return <option key={timeStr} value={timeStr} className="bg-slate-900">{timeStr}</option>;
                                                        })}
                                                    </select>
                                                </div>
                                            </div>
                                        ) : (
                                            <div className="text-gray-500 text-sm text-center py-4">No configurable parameters for this strategy</div>
                                        )}
                                    </div>
                                </div>
                            </div>
                        </Card>

                        {/* Backtest Controls (Relocated) */}
                        <Card title="Backtest Settings & Execution" className="border-t-4 border-t-blue-500">
                            <div className="flex flex-col gap-4">
                                {/* Row 1: Data Interval & Status */}
                                <div className="flex flex-col md:flex-row justify-between items-center gap-4 w-full">
                                    <div className="flex items-center gap-4 w-full md:w-auto">
                                        <div className="relative w-32">
                                            <label className="text-[10px] text-gray-500 absolute -top-1.5 left-2 bg-[#1e2029] px-1">Interval</label>
                                            <select
                                                value={currentInterval}
                                                onChange={(e) => setCurrentInterval(e.target.value)}
                                                className="w-full bg-black/40 border border-white/10 rounded px-3 py-2 text-sm text-white focus:border-blue-500 outline-none appearance-none cursor-pointer"
                                            >
                                                <option value="1m">1 Min</option>
                                                <option value="3m">3 Min</option>
                                                <option value="5m">5 Min</option>
                                                <option value="10m">10 Min</option>
                                                <option value="15m">15 Min</option>
                                                <option value="30m">30 Min</option>
                                                <option value="60m">1 Hour</option>
                                                <option value="1d">1 Day</option>
                                                <option value="1w">1 Week</option>
                                            </select>
                                        </div>

                                        <div className="flex items-center gap-3">
                                            {!dataStatus.is_fresh ? (
                                                <span className="text-amber-500 text-xs font-bold px-2 py-1 bg-amber-500/10 rounded border border-amber-500/20 whitespace-nowrap">
                                                    Data Stale ({dataStatus.count}{dataStatus.start_date ? `, ${dataStatus.start_date}~` : ''})
                                                </span>
                                            ) : (
                                                <span className="text-green-500 text-xs font-bold px-2 py-1 bg-green-500/10 rounded border border-green-500/20 whitespace-nowrap">
                                                    Data Fresh ({dataStatus.count}{dataStatus.start_date ? `, ${dataStatus.start_date}~` : ''})
                                                </span>
                                            )}
                                            <button
                                                onClick={handleFetchData}
                                                disabled={isFetchingData}
                                                className={`px-3 py-1 rounded text-sm font-bold transition-all shadow-lg flex items-center gap-2 whitespace-nowrap disabled:opacity-50 ${fetchMessage && fetchMessage.includes("Updated") ? "bg-green-600 text-white" :
                                                    fetchMessage && fetchMessage.includes("Up to date") ? "bg-blue-600 text-white" :
                                                        "bg-amber-600 hover:bg-amber-500 text-white hover:shadow-amber-500/30"
                                                    }`}
                                            >
                                                {isFetchingData ? 'Fetching...' :
                                                    fetchMessage ? fetchMessage : 'Update Data'}
                                            </button>
                                        </div>
                                    </div>
                                </div>

                                {/* Row 2: Capital & Date & Strategy */}
                                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 border-t border-white/5 pt-4">
                                    <div className="relative">
                                        <label className="text-[10px] text-gray-500 absolute -top-1.5 left-2 bg-[#1e2029] px-1">Initial Capital</label>
                                        <input
                                            type="text"
                                            value={initialCapital.toLocaleString()}
                                            onChange={(e) => {
                                                const rawValue = e.target.value.replace(/[^0-9]/g, '');
                                                setInitialCapital(rawValue === '' ? 0 : parseInt(rawValue, 10));
                                            }}
                                            className="w-full bg-black/40 border border-white/10 rounded px-3 py-2 text-sm text-white focus:border-blue-500 outline-none"
                                        />
                                    </div>

                                    <div className="relative">
                                        <label className="text-[10px] text-gray-500 absolute -top-1.5 left-2 bg-[#1e2029] px-1">Start Date</label>
                                        <input
                                            type="date"
                                            value={fromDate}
                                            onChange={(e) => setFromDate(e.target.value)}
                                            className="w-full bg-black/40 border border-white/10 rounded px-3 py-2 text-sm text-white focus:border-blue-500 outline-none"
                                        />
                                    </div>

                                    <div className="relative">
                                        <label className="text-[10px] text-gray-500 absolute -top-1.5 left-2 bg-[#1e2029] px-1">Betting Logic</label>
                                        <select
                                            value={config.betting_strategy || "fixed"}
                                            onChange={(e) => handleConfigChange('betting_strategy', e.target.value)}
                                            className="w-full bg-black/40 border border-white/10 rounded px-3 py-2 text-sm text-white focus:border-blue-500 outline-none appearance-none cursor-pointer"
                                        >
                                            <option value="fixed">Fixed Amount</option>
                                            <option value="compound">Compound Interest</option>
                                        </select>
                                    </div>
                                </div>

                                {/* Row 3: Action Buttons */}
                                <div className="grid grid-cols-2 gap-4 pt-2">
                                    <button
                                        onClick={() => setShowChart(!showChart)}
                                        disabled={!backtestResult}
                                        className={`px-4 py-4 rounded-xl font-bold transition-all shadow-lg flex items-center justify-center gap-2 ${!backtestResult
                                            ? 'bg-gray-800 text-gray-600 cursor-not-allowed opacity-50'
                                            : showChart
                                                ? 'bg-purple-600 text-white hover:bg-purple-500 shadow-purple-500/30'
                                                : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                                            }`}
                                    >
                                        {showChart ? "🙈 Hide Visual Chart" : "📊 Visual Analysis"}
                                    </button>
                                    <button
                                        onClick={() => runBacktest(selectedStrategy?.id)}
                                        disabled={isLoading || !selectedStrategy || !dataStatus.count}
                                        className="bg-blue-600 hover:bg-blue-500 text-white px-4 py-4 rounded-xl font-bold transition-all shadow-lg hover:shadow-blue-500/30 flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed disabled:bg-gray-700"
                                    >
                                        {isLoading ? (
                                            <>
                                                <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                                                Running...
                                            </>
                                        ) : (
                                            <>🚀 Run Backtest</>
                                        )}
                                    </button>
                                </div>
                            </div>
                        </Card>

                        {/* VISUAL CHART SECTION (Dedicated) */}
                        {showChart && backtestResult && (
                            <div className="mb-6 animate-fade-in-down">
                                <Card title="Visual Backtest Analysis">
                                    {backtestResult.ohlcv_data ? (
                                        <VisualBacktestChart
                                            data={backtestResult.ohlcv_data}
                                            trades={backtestResult.trades}
                                        />
                                    ) : (
                                        <div className="h-[200px] flex items-center justify-center text-gray-500">
                                            No visual data available.
                                        </div>
                                    )}
                                </Card>
                            </div>
                        )}

                        {/* Backtest Results */}
                        {backtestResult ? (
                            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                                <Card
                                    className="lg:col-span-2"
                                    title="Equity Curve"
                                >
                                    <div className="h-[500px] w-full bg-black/20 rounded-lg p-2 overflow-hidden">
                                        <ResponsiveContainer width="100%" height="100%">
                                            <LineChart data={backtestResult.chart_data}>
                                                <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                                                <XAxis
                                                    dataKey="date"
                                                    stroke="#666"
                                                    height={50}
                                                    ticks={(() => {
                                                        // Generate ticks only for month changes
                                                        if (!backtestResult.chart_data) return [];
                                                        const ticks = [];
                                                        let lastMonth = -1;
                                                        backtestResult.chart_data.forEach(d => {
                                                            const date = new Date(d.date);
                                                            const month = date.getMonth();
                                                            if (month !== lastMonth) {
                                                                ticks.push(d.date);
                                                                lastMonth = month;
                                                            }
                                                        });
                                                        return ticks;
                                                    })()}
                                                    interval={0} // Force show all passed ticks (recharts might still hide if overlapping, but usually fine for monthly)
                                                    tick={({ x, y, payload, index }) => {
                                                        const dateStr = payload.value;
                                                        if (!dateStr) return null;
                                                        const date = new Date(dateStr);
                                                        const monthStr = `${date.getMonth() + 1}월`; // Show Month only (e.g., "1월")
                                                        const year = date.getFullYear();

                                                        // Show Year if it's Jan (Month 0) OR it's the very first tick
                                                        const isJan = date.getMonth() === 0;
                                                        const showYear = index === 0 || isJan;

                                                        return (
                                                            <g transform={`translate(${x},${y})`}>
                                                                <text x={0} y={0} dy={16} textAnchor="middle" fill="#666" fontSize={12}>
                                                                    {monthStr}
                                                                </text>
                                                                {showYear && (
                                                                    <text x={0} y={0} dy={32} textAnchor="middle" fill="#444" fontSize={10} fontWeight="bold">
                                                                        {year}
                                                                    </text>
                                                                )}
                                                            </g>
                                                        );
                                                    }}
                                                />
                                                <YAxis
                                                    stroke="#666"
                                                    domain={['auto', 'auto']}
                                                    tickFormatter={(value) => {
                                                        if (value >= 100000000) return `${(value / 100000000).toFixed(1)}억`;
                                                        if (value >= 1000000) return `${(value / 1000000).toFixed(1)}M`;
                                                        if (value >= 1000) return `${(value / 1000).toFixed(1)}k`;
                                                        return value;
                                                    }}
                                                    width={60}
                                                />
                                                <Tooltip
                                                    contentStyle={{ backgroundColor: '#111', border: '1px solid #333' }}
                                                    itemStyle={{ color: '#fff' }}
                                                    formatter={(value) => new Intl.NumberFormat('ko-KR', { style: 'currency', currency: 'KRW' }).format(value)}
                                                />
                                                <Line type="monotone" dataKey="equity" stroke="#8884d8" strokeWidth={2} dot={false} />
                                            </LineChart>
                                        </ResponsiveContainer>
                                    </div>
                                </Card>
                                <div className="space-y-6">
                                    <Card title="Performance Stats">
                                        <div className="space-y-4">
                                            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                                                <div className="p-3 bg-white/5 rounded-lg">
                                                    <div className="text-xs text-gray-400">Total Return</div>
                                                    <div className={`text-xl font-bold ${parseFloat(backtestResult.total_return) >= 0 ? "text-green-400" : "text-red-400"}`}>
                                                        {backtestResult.total_return}
                                                    </div>
                                                </div>
                                                <div className="p-3 bg-white/5 rounded-lg border border-purple-500/30 bg-purple-500/10">
                                                    <div className="text-xs text-purple-300 font-semibold">Profit Factor</div>
                                                    <div className="text-xl font-bold text-white">{backtestResult.profit_factor || "0.00"}</div>
                                                </div>
                                                <div className="p-3 bg-white/5 rounded-lg">
                                                    <div className="text-xs text-gray-400">Win Rate</div>
                                                    <div className="text-xl font-bold text-white">{backtestResult.win_rate}</div>
                                                </div>
                                                <div className="p-3 bg-white/5 rounded-lg">
                                                    <div className="text-xs text-gray-400">Sharpe Ratio</div>
                                                    <div className="text-xl font-bold text-yellow-400">{backtestResult.sharpe_ratio || "0.00"}</div>
                                                </div>

                                                <div className="p-3 bg-white/5 rounded-lg">
                                                    <div className="text-xs text-gray-400">Total Trades</div>
                                                    <div className="text-xl font-bold text-white">{backtestResult.total_trades}</div>
                                                </div>
                                                <div className="p-3 bg-white/5 rounded-lg">
                                                    <div className="text-xs text-gray-400">Stability (R²)</div>
                                                    <div className="text-xl font-bold text-purple-400">{backtestResult.stability_score || "0.00"}</div>
                                                </div>
                                                <div className="p-3 bg-white/5 rounded-lg">
                                                    <div className="text-xs text-gray-400">Profit Accel</div>
                                                    <div className={`text-xl font-bold ${parseFloat(backtestResult.acceleration_score) >= 1 ? 'text-green-400' : 'text-orange-400'}`}>
                                                        {backtestResult.acceleration_score ? `${backtestResult.acceleration_score}x` : "0.00x"}
                                                    </div>
                                                </div>
                                                <div className="p-3 bg-white/5 rounded-lg">
                                                    <div className="text-xs text-gray-400">Activity Rate</div>
                                                    <div className="text-xl font-bold text-blue-400">{backtestResult.activity_rate || "0%"}</div>
                                                </div>
                                                <div className="p-3 bg-white/5 rounded-lg">
                                                    <div className="text-xs text-gray-400">Avg PnL</div>
                                                    <div className={`text-xl font-bold ${parseFloat(backtestResult.avg_pnl) >= 0 ? "text-green-400" : "text-red-400"}`}>
                                                        {backtestResult.avg_pnl}
                                                    </div>
                                                </div>
                                                <div className="p-3 bg-white/5 rounded-lg">
                                                    <div className="text-xs text-gray-400">Avg Holding</div>
                                                    <div className="text-xl font-bold text-white">{backtestResult.avg_holding_time || "0m"}</div>
                                                </div>

                                                <div className="p-3 bg-white/5 rounded-lg">
                                                    <div className="text-xs text-gray-400">Max Profit</div>
                                                    <div className="text-xl font-bold text-green-400">{backtestResult.max_profit}</div>
                                                </div>
                                                <div className="p-3 bg-white/5 rounded-lg">
                                                    <div className="text-xs text-gray-400">Max Loss</div>
                                                    <div className="text-xl font-bold text-red-400">{backtestResult.max_loss}</div>
                                                </div>
                                                <div className="col-span-2 p-3 bg-white/5 rounded-lg">
                                                    <div className="text-xs text-gray-400">Max Drawdown</div>
                                                    <div className="text-xl font-bold text-red-400">{backtestResult.max_drawdown}</div>
                                                </div>
                                            </div>

                                            {/* Monthly Analysis Chart */}
                                            {backtestResult.decile_stats && backtestResult.decile_stats.length > 0 && (
                                                <div className="mt-4 pt-4 border-t border-white/10">
                                                    <h4 className="text-sm font-bold text-gray-400 mb-2">Strategy Stability (Monthly Analysis)</h4>
                                                    <div className="h-[200px] w-full bg-black/20 rounded-lg p-2">
                                                        <ResponsiveContainer width="100%" height="100%">
                                                            <ComposedChart data={backtestResult.decile_stats} margin={{ bottom: 60, left: 0, right: 0 }}>
                                                                <CartesianGrid strokeDasharray="3 3" stroke="#333" vertical={false} />

                                                                {/* Custom X-Axis with Multi-Row Data */}
                                                                <XAxis
                                                                    dataKey="block"
                                                                    stroke="#666"
                                                                    tickLine={false}
                                                                    interval={0}
                                                                    tick={({ x, y, payload, index }) => {
                                                                        const data = backtestResult.decile_stats[index];
                                                                        return (
                                                                            <g transform={`translate(${x},${y})`}>
                                                                                {/* Row 1: Month */}
                                                                                <text x={0} y={10} dy={0} textAnchor="middle" fill="#9ca3af" fontSize={10}>
                                                                                    {payload.value}
                                                                                </text>
                                                                                {/* Row 2: Trade Count */}
                                                                                <text x={0} y={10} dy={12} textAnchor="middle" fill="#60a5fa" fontSize={10} fontWeight="bold">
                                                                                    {data.count}
                                                                                </text>
                                                                                {/* Row 3: Win Rate */}
                                                                                <text x={0} y={10} dy={24} textAnchor="middle" fill="#fbbf24" fontSize={10}>
                                                                                    {data.win_rate}%
                                                                                </text>
                                                                                {/* Row 4: Realized PnL */}
                                                                                <text x={0} y={10} dy={36} textAnchor="middle" fill={data.total_pnl >= 0 ? "#4ade80" : "#ef4444"} fontSize={10} fontWeight="bold">
                                                                                    {data.total_pnl}%
                                                                                </text>
                                                                            </g>
                                                                        );
                                                                    }}
                                                                />

                                                                <YAxis yAxisId="left" stroke="#666" tick={{ fontSize: 10 }} tickFormatter={(val) => `${val}%`} />
                                                                <YAxis yAxisId="right" orientation="right" hide domain={[0, 100]} />

                                                                <Tooltip
                                                                    contentStyle={{ backgroundColor: '#1f2937', border: 'none', borderRadius: '8px' }}
                                                                    itemStyle={{ color: '#fff' }}
                                                                    formatter={(value, name) => {
                                                                        if (name === "total_pnl") return [`${value}%`, 'Realized PnL'];
                                                                        return [value, name];
                                                                    }}
                                                                    labelFormatter={(label) => `Month: ${label}`}
                                                                />
                                                                <ReferenceLine yAxisId="left" y={0} stroke="#666" />

                                                                <Bar yAxisId="left" dataKey="total_pnl" radius={[4, 4, 0, 0]}>
                                                                    {backtestResult.decile_stats.map((entry, index) => (
                                                                        <Cell key={`cell-${index}`} fill={entry.total_pnl >= 0 ? '#4ade80' : '#ef4444'} />
                                                                    ))}
                                                                </Bar>
                                                            </ComposedChart>
                                                        </ResponsiveContainer>
                                                    </div>
                                                    <div className="flex justify-center gap-4 mt-1 text-[10px] text-gray-500">
                                                        <div className="flex items-center gap-1">
                                                            <div className="w-2 h-2 bg-green-400 rounded-sm"></div>
                                                            <span>Profit</span>
                                                        </div>
                                                        <div className="flex items-center gap-1">
                                                            <div className="w-2 h-2 bg-red-400 rounded-sm"></div>
                                                            <span>Loss</span>
                                                        </div>
                                                        <div className="flex items-center gap-1">
                                                            <span className="text-blue-400 font-bold">12</span>
                                                            <span>= Count</span>
                                                        </div>
                                                        <div className="flex items-center gap-1">
                                                            <span className="font-bold" style={{ color: '#fbbf24' }}>60%</span>
                                                            <span>= Win Rate</span>
                                                        </div>
                                                        <div className="flex items-center gap-1">
                                                            <span className="text-green-400 font-bold">5.2%</span>
                                                            <span>= Realized PnL</span>
                                                        </div>
                                                    </div>
                                                </div>
                                            )}

                                            {/* Logs Preview */}
                                            {backtestResult.logs && (
                                                <div className="mt-4 pt-4 border-t border-white/10">
                                                    <h4 className="text-sm font-bold text-gray-400 mb-2">Execution Logs</h4>
                                                    <div className="h-[200px] overflow-y-auto bg-black/40 p-2 rounded text-xs font-mono space-y-1">
                                                        {backtestResult.logs.map((log, i) => (
                                                            <div key={i} className={log.includes("EXECUTED") ? "text-green-400" : "text-gray-500"}>
                                                                {log}
                                                            </div>
                                                        ))}
                                                    </div>
                                                </div>
                                            )}
                                        </div>
                                    </Card>
                                    <button className="w-full bg-gradient-to-r from-green-600 to-emerald-600 py-4 rounded-xl font-bold text-lg shadow-xl hover:scale-[1.02] transition-transform">
                                        Deploy Strategy to Live
                                    </button>
                                </div>
                            </div>
                        ) : (
                            <div className="flex items-center justify-center border-2 border-dashed border-white/10 rounded-xl h-[200px] bg-black/20">
                                <div className="text-center text-gray-500">
                                    {backtestStatus.status === 'running' ? (
                                        <div className="flex flex-col items-center gap-3">
                                            <div className="w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin"></div>
                                            <p className="text-lg text-blue-400 font-bold">{backtestStatus.message}</p>
                                        </div>
                                    ) : backtestStatus.status === 'error' ? (
                                        <div className="flex flex-col items-center gap-3">
                                            <div className="text-4xl">⚠️</div>
                                            <p className="text-lg text-red-500 font-bold">{backtestStatus.message}</p>
                                            <p className="text-sm">Check logs or try a different date range.</p>
                                        </div>
                                    ) : (
                                        <>
                                            <p className="text-lg">Ready to Backtest</p>
                                            <p className="text-sm mt-2">Configure parameters above and click Run Backtest</p>
                                        </>
                                    )}
                                </div>
                            </div>
                        )}

                        {/* Code View */}
                        <Card title="Strategy Logic">
                            <pre className="bg-black/50 p-4 rounded-lg text-sm font-mono text-gray-300 overflow-x-auto border border-white/5 max-h-[300px]">
                                {selectedStrategy.code}
                            </pre>
                        </Card>
                    </>
                ) : (
                    <div className="flex flex-col items-center justify-center h-[50vh] text-gray-500">
                        <div className="text-6xl mb-4 opacity-20">⚡</div>
                        <p className="text-xl">Select a strategy to begin</p>
                    </div>
                )}
            </div>

            {/* AI Generator Input - Fixed Bottom */}
            <Card className="shrink-0 mt-auto border-t border-white/10 bg-gradient-to-b from-[#1a1c23] to-[#111]">
                <div className="flex gap-4">
                    <input
                        type="text"
                        className="flex-1 bg-black/40 border border-white/10 rounded-lg p-4 text-white focus:border-purple-500 focus:ring-1 focus:ring-purple-500 outline-none placeholder-gray-600"
                        placeholder="Describe a new strategy... (e.g., 'Buy when RSI < 30 and price is above 200MA')"
                        value={aiPrompt}
                        onChange={(e) => setAiPrompt(e.target.value)}
                        onKeyPress={(e) => e.key === 'Enter' && handleAiGenerate()}
                    />
                    <button
                        onClick={handleAiGenerate}
                        disabled={isGenerating || !aiPrompt}
                        className={`px-8 rounded-lg font-bold transition-all flex items-center gap-2 whitespace-nowrap ${isGenerating ? 'bg-purple-900 text-purple-300' : 'bg-purple-600 hover:bg-purple-500 text-white shadow-lg hover:shadow-purple-500/30'
                            }`}
                    >
                        {isGenerating ? 'Generatin...' : 'Ask AI'}
                    </button>
                </div>
            </Card>
        </div >
    );
};

export default StrategyView;
