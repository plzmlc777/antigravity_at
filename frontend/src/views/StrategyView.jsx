import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import Card from '../components/common/Card';

const StrategyView = () => {
    const [strategies, setStrategies] = useState([]);
    const [selectedStrategy, setSelectedStrategy] = useState(null);
    const [backtestResult, setBacktestResult] = useState(null);
    const [isGenerating, setIsGenerating] = useState(false);
    const [aiPrompt, setAiPrompt] = useState("");
    const [isLoading, setIsLoading] = useState(false);

    useEffect(() => {
        fetchStrategies();
    }, []);

    const fetchStrategies = async () => {
        try {
            const res = await axios.get('/api/v1/strategies/list');
            setStrategies(res.data);
            if (res.data.length > 0 && !selectedStrategy) {
                setSelectedStrategy(res.data[0]);
            }
        } catch (e) {
            console.error(e);
        }
    };

    const runBacktest = async (strategyId) => {
        setIsLoading(true);
        try {
            const res = await axios.post(`/api/v1/strategies/${strategyId}/backtest`);
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

    return (
        <div className="flex flex-col lg:flex-row gap-6 h-[calc(100vh-100px)]">
            {/* Sidebar: Strategy List */}
            <div className="w-full lg:w-1/4 space-y-4">
                <Card title="My Strategies" className="h-full flex flex-col">
                    <div className="flex-1 overflow-y-auto space-y-2 pr-2 custom-scrollbar">
                        {strategies.map(strat => (
                            <div
                                key={strat.id}
                                onClick={() => { setSelectedStrategy(strat); setBacktestResult(null); }}
                                className={`p-4 rounded-lg cursor-pointer transition-all border ${selectedStrategy?.id === strat.id
                                    ? 'bg-blue-500/20 border-blue-500 text-white'
                                    : 'bg-white/5 border-transparent hover:bg-white/10 text-gray-400'
                                    }`}
                            >
                                <div className="font-bold">{strat.name}</div>
                                <div className="text-xs mt-1 opacity-70 truncate">{strat.description}</div>
                                <div className="flex gap-1 mt-2 flex-wrap">
                                    {strat.tags.map(tag => (
                                        <span key={tag} className="text-[10px] bg-black/30 px-2 py-0.5 rounded text-gray-300">
                                            #{tag}
                                        </span>
                                    ))}
                                </div>
                            </div>
                        ))}
                    </div>
                </Card>
            </div>

            {/* Main Content */}
            <div className="flex-1 flex flex-col gap-6 overflow-y-auto pr-2 custom-scrollbar">
                {selectedStrategy ? (
                    <>
                        {/* Top: Info & Actions */}
                        <Card>
                            <div className="flex justify-between items-start">
                                <div>
                                    <h2 className="text-2xl font-bold bg-gradient-to-r from-blue-400 to-purple-400 bg-clip-text text-transparent">
                                        {selectedStrategy.name}
                                    </h2>
                                    <p className="text-gray-400 mt-1">{selectedStrategy.description}</p>
                                </div>
                                <div className="flex gap-3">
                                    <button
                                        onClick={() => runBacktest(selectedStrategy.id)}
                                        disabled={isLoading}
                                        className="bg-blue-600 hover:bg-blue-500 text-white px-6 py-2 rounded-lg font-bold transition-all shadow-lg hover:shadow-blue-500/30 flex items-center gap-2"
                                    >
                                        {isLoading ? 'Running...' : 'Run Backtest'}
                                    </button>
                                    <button className="bg-gray-700 hover:bg-gray-600 text-white px-4 py-2 rounded-lg font-bold transition-all">
                                        Edit Code
                                    </button>
                                </div>
                            </div>
                        </Card>

                        {/* Middle: Backtest Results */}
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
                            <div className="flex-1 flex items-center justify-center border-2 border-dashed border-white/10 rounded-xl h-[400px]">
                                <div className="text-center text-gray-500">
                                    <p className="text-lg">No backtest data available</p>
                                    <p className="text-sm mt-2">Click 'Run Backtest' to simulate performance</p>
                                </div>
                            </div>
                        )}

                        {/* Bottom: Code Review (Read Only) */}
                        <Card title="Strategy Code">
                            <pre className="bg-black/50 p-4 rounded-lg text-sm font-mono text-gray-300 overflow-x-auto border border-white/5">
                                {selectedStrategy.code}
                            </pre>
                        </Card>
                    </>
                ) : (
                    <div className="flex items-center justify-center h-full text-gray-500">
                        Select a strategy to view details
                    </div>
                )}

                {/* AI Generator Input */}
                <Card className="mt-auto border-t border-white/10 bg-gradient-to-b from-[#1a1c23] to-[#111]">
                    <div className="flex gap-4">
                        <input
                            type="text"
                            className="flex-1 bg-black/40 border border-white/10 rounded-lg p-4 text-white focus:border-purple-500 focus:ring-1 focus:ring-purple-500 outline-none placeholder-gray-600"
                            placeholder="Describe a strategy... (e.g., 'Buy when RSI < 30 and price is above 200MA')"
                            value={aiPrompt}
                            onChange={(e) => setAiPrompt(e.target.value)}
                            onKeyPress={(e) => e.key === 'Enter' && handleAiGenerate()}
                        />
                        <button
                            onClick={handleAiGenerate}
                            disabled={isGenerating || !aiPrompt}
                            className={`px-8 rounded-lg font-bold transition-all flex items-center gap-2 ${isGenerating ? 'bg-purple-900 text-purple-300' : 'bg-purple-600 hover:bg-purple-500 text-white shadow-lg hover:shadow-purple-500/30'
                                }`}
                        >
                            {isGenerating ? 'Generatin...' : 'Ask AI'}
                        </button>
                    </div>
                </Card>
            </div>
        </div>
    );
};

export default StrategyView;
