import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import Card from '../components/common/Card';
import SymbolSelector from '../components/SymbolSelector'; // Import

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

    // Dynamic Config State
    const [config, setConfig] = useState({});

    // Save to LocalStorage
    useEffect(() => {
        localStorage.setItem('lastSymbol', currentSymbol);
    }, [currentSymbol]);

    useEffect(() => {
        localStorage.setItem('savedSymbols', JSON.stringify(savedSymbols));
    }, [savedSymbols]);

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

    const runBacktest = async (strategyId) => {
        setIsLoading(true);
        try {
            const payload = {
                symbol: currentSymbol,
                ...config
            };
            const res = await axios.post(`/api/v1/strategies/${strategyId}/backtest`, payload);
            setBacktestResult(res.data);
        } catch (e) {
            alert("Backtest failed");
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

    // 5. Data Management & Persistence State
    const [dataStatus, setDataStatus] = useState({ is_fresh: false, last_updated: null, count: 0 });
    const [isFetchingData, setIsFetchingData] = useState(false);
    const [currentInterval, setCurrentInterval] = useState(() => localStorage.getItem('lastInterval') || "1m");
    const [fetchMessage, setFetchMessage] = useState(null);

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
                days: 365
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
        <div className="flex flex-col gap-6 h-[calc(100vh-100px)]">
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

                    {/* Row 2: All Buttons (Data + Actions) */}
                    <div className="flex flex-col md:flex-row justify-between items-center gap-4 w-full border-t border-white/5 pt-4">
                        {/* Left: Data Status & Interval */}
                        <div className="flex items-center gap-4">
                            {/* Interval Selector */}
                            <div className="relative w-24">
                                <label className="text-[10px] text-gray-500 absolute -top-1.5 left-2 bg-[#1e2029] px-1">Interval</label>
                                <select
                                    value={currentInterval}
                                    onChange={(e) => setCurrentInterval(e.target.value)}
                                    className="w-full bg-black/40 border border-white/10 rounded px-2 py-1.5 text-sm text-white focus:border-blue-500 outline-none appearance-none cursor-pointer"
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

                            {/* Data Status & Update Button (Side by Side) */}
                            <div className="flex items-center gap-3">
                                {/* Status Badge */}
                                {!dataStatus.is_fresh ? (
                                    <span className="text-amber-500 text-xs font-bold px-2 py-1 bg-amber-500/10 rounded border border-amber-500/20 whitespace-nowrap">
                                        Data Stale ({dataStatus.count})
                                    </span>
                                ) : (
                                    <span className="text-green-500 text-xs font-bold px-2 py-1 bg-green-500/10 rounded border border-green-500/20 whitespace-nowrap">
                                        Data Fresh ({dataStatus.count})
                                    </span>
                                )}

                                {/* Update Button - Always Visible */}
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

                        {/* Right: Actions */}
                        <div className="flex gap-3">
                            <button
                                onClick={() => runBacktest(selectedStrategy?.id)}
                                disabled={isLoading || !selectedStrategy || !dataStatus.is_fresh}
                                className="bg-blue-600 hover:bg-blue-500 text-white px-6 py-2 rounded-lg font-bold transition-all shadow-lg hover:shadow-blue-500/30 flex items-center gap-2 whitespace-nowrap disabled:opacity-50 disabled:cursor-not-allowed disabled:bg-gray-700"
                            >
                                {isLoading ? 'Running...' : 'Run Backtest'}
                            </button>
                            <button className="bg-gray-700 hover:bg-gray-600 text-white px-4 py-2 rounded-lg font-bold transition-all whitespace-nowrap">
                                Edit Code
                            </button>
                        </div>
                    </div>
                </div>
            </Card>

            {/* Main Scrollable Area */}
            <div className="flex-1 overflow-y-auto space-y-6 pr-2 custom-scrollbar pb-20">
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
                                                    <label className="text-xs text-gray-500 mb-1 block">Start Hour (0-23)</label>
                                                    <input
                                                        type="number"
                                                        className="w-full bg-black/40 border border-white/10 rounded px-3 py-2 text-sm text-white focus:border-blue-500 outline-none transition-colors"
                                                        value={config.start_hour || 9}
                                                        onChange={(e) => handleConfigChange('start_hour', parseInt(e.target.value))}
                                                    />
                                                </div>
                                                <div>
                                                    <label className="text-xs text-gray-500 mb-1 block">Delay (Minutes)</label>
                                                    <input
                                                        type="number"
                                                        className="w-full bg-black/40 border border-white/10 rounded px-3 py-2 text-sm text-white focus:border-blue-500 outline-none transition-colors"
                                                        value={config.delay_minutes || 10}
                                                        onChange={(e) => handleConfigChange('delay_minutes', parseInt(e.target.value))}
                                                    />
                                                </div>
                                                <div>
                                                    <label className="text-xs text-gray-500 mb-1 block">Target Pump % (e.g. 0.02)</label>
                                                    <input
                                                        type="number" step="0.01"
                                                        className="w-full bg-black/40 border border-white/10 rounded px-3 py-2 text-sm text-white focus:border-blue-500 outline-none transition-colors"
                                                        value={config.target_percent || 0.02}
                                                        onChange={(e) => handleConfigChange('target_percent', parseFloat(e.target.value))}
                                                    />
                                                </div>
                                                <div>
                                                    <label className="text-xs text-gray-500 mb-1 block">Stop Loss % (e.g. -0.03)</label>
                                                    <input
                                                        type="number" step="0.01"
                                                        className="w-full bg-black/40 border border-white/10 rounded px-3 py-2 text-sm text-white focus:border-blue-500 outline-none transition-colors"
                                                        value={config.safety_stop_percent || -0.03}
                                                        onChange={(e) => handleConfigChange('safety_stop_percent', parseFloat(e.target.value))}
                                                    />
                                                </div>
                                            </div>
                                        ) : (
                                            <div className="text-gray-500 text-sm text-center py-4">No configurable parameters for this strategy</div>
                                        )}
                                    </div>
                                </div>
                            </div>
                        </Card>

                        {/* Backtest Results */}
                        {backtestResult ? (
                            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                                <Card className="lg:col-span-2" title="Equity Curve">
                                    <div className="h-[300px] w-full">
                                        <ResponsiveContainer width="100%" height="100%">
                                            <LineChart data={backtestResult.chart_data}>
                                                <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                                                <XAxis dataKey="date" stroke="#666" />
                                                <YAxis stroke="#666" domain={['auto', 'auto']} />
                                                <Tooltip
                                                    contentStyle={{ backgroundColor: '#111', border: '1px solid #333' }}
                                                    itemStyle={{ color: '#fff' }}
                                                />
                                                <Line type="monotone" dataKey="equity" stroke="#8884d8" strokeWidth={2} dot={false} />
                                            </LineChart>
                                        </ResponsiveContainer>
                                    </div>
                                </Card>
                                <div className="space-y-6">
                                    <Card title="Performance Stats">
                                        <div className="space-y-4">
                                            <div className="flex justify-between border-b border-white/5 pb-2">
                                                <span className="text-gray-400">Total Return</span>
                                                <span className="text-green-400 font-bold text-xl">{backtestResult.total_return}</span>
                                            </div>
                                            <div className="flex justify-between border-b border-white/5 pb-2">
                                                <span className="text-gray-400">Win Rate</span>
                                                <span className="text-blue-400 font-bold text-xl">{backtestResult.win_rate}</span>
                                            </div>
                                            <div className="flex justify-between border-b border-white/5 pb-2">
                                                <span className="text-gray-400">Max Drawdown</span>
                                                <span className="text-red-400 font-bold text-xl">{backtestResult.max_drawdown}</span>
                                            </div>
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
                                    <p className="text-lg">Ready to Backtest</p>
                                    <p className="text-sm mt-2">Configure parameters above and click Run Backtest</p>
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
        </div>
    );
};

export default StrategyView;
