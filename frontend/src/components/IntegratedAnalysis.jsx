import React, { useState, useEffect, useRef } from 'react';
import Card from './common/Card';
import { Play, Pause, FastForward, SkipBack, X } from 'lucide-react';
import VisualBacktestChart from './VisualBacktestChart';

const IntegratedAnalysis = ({ backtestResult }) => {
    // 1. State
    const [isPlaying, setIsPlaying] = useState(false);
    const [currentTradeIndex, setCurrentTradeIndex] = useState(0);
    const [playbackSpeed, setPlaybackSpeed] = useState(1); // 1 = 1 trade/sec
    const [selectedTrade, setSelectedTrade] = useState(null); // For Daily Detail View
    const [dayChartData, setDayChartData] = useState([]); // Selected Day Data

    // Data Source: Use 'matched_trades' if available, otherwise empty
    const trades = backtestResult?.matched_trades || [];
    const totalTrades = trades.length;

    // 2. Playback Logic
    useEffect(() => {
        let interval;
        if (isPlaying && currentTradeIndex < totalTrades - 1) {
            interval = setInterval(() => {
                setCurrentTradeIndex(prev => {
                    if (prev >= totalTrades - 1) {
                        setIsPlaying(false);
                        return prev;
                    }
                    return prev + 1;
                });
            }, 1000 / playbackSpeed);
        }
        return () => clearInterval(interval);
    }, [isPlaying, currentTradeIndex, totalTrades, playbackSpeed]);

    // 3. Handlers
    const handleTradeClick = (trade) => {
        setIsPlaying(false);
        setSelectedTrade(trade);

        // Prepare Daily Chart Data
        // 1. Identify Symbol and Date
        const sym = trade.symbol;
        // Parse time: "2025-01-01T10:30:00" -> string match
        const tradeDateStr = trade.entry_time.split('T')[0];

        // 2. Lookup in multi_ohlcv_data
        const multiData = backtestResult?.multi_ohlcv_data || {};
        const symbolData = multiData[sym] || [];

        // 3. Filter for that day (User Request: Single Day Mode)
        // Convert Unix timestamps to Date String for comparison
        const dayCandles = symbolData.filter(c => {
            const d = new Date(c.time * 1000);
            return d.toISOString().split('T')[0] === tradeDateStr;
        });

        setDayChartData(dayCandles);
    };

    const handleCloseModal = () => {
        setSelectedTrade(null);
        setDayChartData([]);
    };

    // Calculate Dynamic Stats based on currentTradeIndex
    const currentTrade = trades[currentTradeIndex];
    // Cumulative PnL up to current index
    const processedTrades = trades.slice(0, currentTradeIndex + 1);
    const cumulativePnL = processedTrades.reduce((sum, t) => sum + (t.pnl || 0), 0);
    const cumulativeReturn = backtestResult?.initial_capital
        ? (cumulativePnL / backtestResult.initial_capital) * 100
        : 0;

    // 4. Render
    if (!trades || trades.length === 0) {
        return (
            <div className="text-center py-10 text-gray-500">
                <p>No Matched Trades Analysis Available.</p>
                <p className="text-xs mt-2">Try running a backtest with more data or check Debug Info.</p>

                {/* Debug Info */}
                <div className="mt-4 p-4 bg-yellow-900/20 text-yellow-500 text-xs text-left rounded overflow-auto max-h-40">
                    <p>Debug: Raw Trades Count: {backtestResult?.trades?.length || 0}</p>
                    <p>Debug: Matched Trades Count: {backtestResult?.matched_trades?.length || 0}</p>
                    <p>Debug: Multi-OHLCV Data Keys: {Object.keys(backtestResult?.multi_ohlcv_data || {}).join(', ')}</p>
                    <p>Strategy: {backtestResult?.strategy_id}</p>
                    <pre>{JSON.stringify(Object.keys(backtestResult || {}), null, 2)}</pre>
                </div>
            </div>
        );
    }

    return (
        <div className="space-y-4">
            {/* Playback Controls */}
            <div className="flex items-center justify-between bg-black/40 p-3 rounded-lg border border-white/5">
                <div className="flex items-center gap-4">
                    <button
                        onClick={() => setIsPlaying(!isPlaying)}
                        className={`p-2 rounded-full ${isPlaying ? 'bg-yellow-500/20 text-yellow-400' : 'bg-green-500/20 text-green-400'} hover:opacity-80 transition`}
                    >
                        {isPlaying ? <Pause size={20} /> : <Play size={20} />}
                    </button>

                    <button
                        onClick={() => { setIsPlaying(false); setCurrentTradeIndex(0); }}
                        className="p-2 text-gray-400 hover:text-white"
                        title="Reset"
                    >
                        <SkipBack size={18} />
                    </button>

                    <div className="flex flex-col">
                        <span className="text-xs text-gray-400">Speed: {playbackSpeed}x</span>
                        <input
                            type="range" min="1" max="50" step="1"
                            value={playbackSpeed}
                            onChange={(e) => setPlaybackSpeed(parseInt(e.target.value))}
                            className="w-24 h-1 bg-gray-700 rounded-lg appearance-none cursor-pointer"
                        />
                    </div>
                </div>

                <div className="text-right">
                    <div className="text-sm font-bold text-white">
                        {currentTradeIndex + 1} / {totalTrades} Trades
                    </div>
                    <div className={`text-xs ${cumulativePnL >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        Cum PnL: {cumulativePnL.toLocaleString()} KRW ({cumulativeReturn.toFixed(2)}%)
                    </div>
                </div>
            </div>

            {/* Timeline UI (Horizontal Scroll) */}
            <div className="relative h-32 bg-black/20 rounded-lg overflow-hidden border border-white/5">
                <div className="absolute inset-0 overflow-x-auto flex items-center px-4 gap-1 scrollbar-thin scrollbar-thumb-gray-700">
                    {trades.map((trade, idx) => {
                        const isSelected = idx === currentTradeIndex;
                        const isProfitable = trade.pnl > 0;
                        return (
                            <div
                                key={idx}
                                onClick={() => setCurrentTradeIndex(idx)}
                                className={`
                                    flex-shrink-0 w-8 h-20 rounded cursor-pointer transition-all
                                    ${isSelected ? 'border-2 border-white scale-110 z-10' : 'opacity-60 hover:opacity-100'}
                                    ${isProfitable ? 'bg-green-500/30' : 'bg-red-500/30'}
                                `}
                                title={`${trade.symbol} | ${trade.pnl_percent.toFixed(2)}%`}
                            >
                                <div className={`w-full h-full relative`}>
                                    {/* Height relative to PnL magnitude could be cool, but keep simple for now */}
                                    <div className={`absolute bottom-0 w-full ${isProfitable ? 'bg-green-500' : 'bg-red-500'}`} style={{ height: `${Math.min(Math.abs(trade.pnl_percent) * 5, 100)}%` }}></div>
                                </div>
                            </div>
                        )
                    })}
                </div>
            </div>

            {/* Current Trade Detail Card */}
            {currentTrade && (
                <div
                    className="cursor-pointer hover:bg-white/5 transition rounded-lg p-4 border border-white/10"
                    onClick={() => handleTradeClick(currentTrade)}
                >
                    <div className="flex justify-between items-start mb-2">
                        <h3 className="text-lg font-bold text-white">{currentTrade.symbol}</h3>
                        <span className="text-xs text-gray-400">{new Date(currentTrade.exit_time).toLocaleString()}</span>
                    </div>
                    <div className="grid grid-cols-2 gap-4 text-sm">
                        <div>
                            <span className="text-gray-400 block">Entry</span>
                            <span className="text-white">{currentTrade.entry_price.toLocaleString()}</span>
                        </div>
                        <div className="text-right">
                            <span className="text-gray-400 block">Exit</span>
                            <span className="text-white">{currentTrade.exit_price.toLocaleString()}</span>
                        </div>
                        <div>
                            <span className="text-gray-400 block">PnL</span>
                            <span className={`${currentTrade.pnl >= 0 ? 'text-green-400' : 'text-red-400'} font-bold`}>
                                {currentTrade.pnl_percent.toFixed(2)}%
                            </span>
                        </div>
                        <div className="text-right">
                            <span className="text-gray-400 block">Strategy</span>
                            <span className="text-blue-300">{currentTrade.strategy_name}</span>
                        </div>
                    </div>
                    <div className="mt-3 text-center text-xs text-gray-500">
                        Click to view Daily Chart
                    </div>
                </div>
            )}

            {/* Daily Chart Modal */}
            {selectedTrade && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
                    <div className="bg-gray-900 w-full max-w-4xl h-[80vh] rounded-2xl border border-white/10 flex flex-col shadow-2xl">
                        <div className="flex justify-between items-center p-4 border-b border-white/10 bg-black/40 rounded-t-2xl">
                            <div>
                                <h2 className="text-xl font-bold text-white flex items-center gap-3">
                                    {selectedTrade.symbol}
                                    <span className={`text-sm px-2 py-1 rounded ${selectedTrade.pnl > 0 ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>
                                        {selectedTrade.pnl_percent.toFixed(2)}%
                                    </span>
                                </h2>
                                <p className="text-xs text-gray-400 mt-1">
                                    {new Date(selectedTrade.entry_time).toLocaleString()} ~ {new Date(selectedTrade.exit_time).toLocaleString()}
                                </p>
                            </div>
                            <button onClick={handleCloseModal} className="p-2 hover:bg-white/10 rounded-full transition">
                                <X className="text-white" />
                            </button>
                        </div>

                        <div className="flex-1 p-4 overflow-hidden">
                            {dayChartData.length > 0 ? (
                                <VisualBacktestChart
                                    data={dayChartData}
                                    trades={[selectedTrade]} // Only show this specific trade markers
                                />
                            ) : (
                                <div className="h-full flex items-center justify-center text-gray-500 flex-col gap-2">
                                    <p>No Intraday Data Available for {selectedTrade.symbol}</p>
                                    <p className="text-xs">Ensure '1m' interval was used and data exists.</p>
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default IntegratedAnalysis;
