import React, { useEffect, useState } from 'react';
import { getSessionRealizedTrades, getSessionStats, getSessionEquityCurve } from '../api/client';
import IntegratedAnalysis from './IntegratedAnalysis';
import { Activity, TrendingUp, TrendingDown, DollarSign } from 'lucide-react';

const LivePerformancePanel = ({ sessionId, strategyConfig, liveData }) => {
    const [trades, setTrades] = useState([]);
    const [equityCurve, setEquityCurve] = useState([]);
    const [stats, setStats] = useState(null);
    const [loading, setLoading] = useState(false);

    // Polling for updates
    useEffect(() => {
        if (!sessionId) return;

        const fetchData = async () => {
            try {
                const [t, e, s] = await Promise.all([
                    getSessionRealizedTrades(sessionId),
                    getSessionEquityCurve(sessionId),
                    getSessionStats(sessionId)
                ]);
                setTrades(t);
                setEquityCurve(e);
                setStats(s);
            } catch (err) {
                console.error("LivePerformance Fetch Error", err);
            }
        };

        fetchData();
        const interval = setInterval(fetchData, 5000); // Poll every 5s
        return () => clearInterval(interval);
    }, [sessionId]);

    if (!sessionId) return null;

    // Construct "backtestResult" shape for IntegratedAnalysis
    // It needs: trades, strategies_config, multi_ohlcv_data (for background)
    // For live, we might not have full multi_ohlcv_data readily available in the same format 
    // unless we fetch it or use the real-time candles from parent.
    // For now, let's pass an empty multi_ohlcv_data or minimal one to avoid errors,
    // and let IntegratedAnalysis fallback to just plotting trades on a timeline.

    const mockBacktestResult = {
        trades: trades,
        strategies_config: [strategyConfig],
        multi_ohlcv_data: {}, // We could populate this with equity curve or symbol history if needed
        rank1_start_date: trades.length > 0 ? trades[trades.length - 1].entry_time : new Date().toISOString()
    };

    // We can use the equity curve to show a secondary chart or just overlay?
    // For now, let's just show the Trade Analysis (IntegratedAnalysis)

    return (
        <div className="bg-[#1e1e24] border border-white/5 rounded-xl overflow-hidden flex flex-col min-h-[500px] mb-6">
            <div className="flex border-b border-white/5 bg-black/20 px-4 py-3 justify-between items-center">
                <div className="flex items-center gap-2 text-sm font-bold text-blue-400">
                    <Activity size={16} />
                    Live Performance Analysis
                </div>
                {stats && (
                    <div className="flex gap-4 text-xs font-mono">
                        <span className="flex items-center gap-1">
                            <span className="text-gray-500">Win Rate:</span>
                            <span className={stats.win_rate >= 50 ? "text-green-400" : "text-red-400"}>
                                {stats.win_rate.toFixed(1)}%
                            </span>
                        </span>
                        <span className="flex items-center gap-1">
                            <span className="text-gray-500">PF:</span>
                            <span className="text-white">{stats.profit_factor.toFixed(2)}</span>
                        </span>
                        <span className="flex items-center gap-1">
                            <span className="text-gray-500">Trades:</span>
                            <span className="text-white">{trades.length}</span>
                        </span>
                    </div>
                )}
            </div>

            <div className="flex-1 relative bg-black/20 p-4">
                <IntegratedAnalysis
                    mode="real"
                    trades={trades}
                    backtestResult={mockBacktestResult}
                    strategiesConfig={[strategyConfig]}
                    savedSymbols={[]} // Pass if available
                />
            </div>
        </div>
    );
};

export default LivePerformancePanel;
