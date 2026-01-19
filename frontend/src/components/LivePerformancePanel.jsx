import React, { useEffect, useState } from 'react';
import { getSessionStats } from '../api/client';
import { Activity, TrendingUp, TrendingDown, DollarSign } from 'lucide-react';

const LivePerformancePanel = ({ sessionId, strategyConfig }) => {
    const [stats, setStats] = useState(null);
    const [loading, setLoading] = useState(false);

    // Polling for updates
    useEffect(() => {
        if (!sessionId) return;

        const fetchData = async () => {
            try {
                const s = await getSessionStats(sessionId);
                setStats(s);
            } catch (err) {
                console.error("LivePerformance Fetch Error", err);
            }
        };

        fetchData();
        const interval = setInterval(fetchData, 5000); // Poll every 5s
        return () => clearInterval(interval);
    }, [sessionId]);

    if (!sessionId || !stats) return null;

    // Define the Grid Layout based on User Request
    // Metric Keys from Backend: 
    // total_return, profit_factor, win_rate, sharpe_ratio
    // total_trades, stability, profit_accel, activity_rate
    // avg_pnl, avg_holding, max_profit, max_loss, max_drawdown

    const metrics = [
        { label: "Total Return", value: stats.total_return, highlight: true, color: parseFloat(stats.total_return) >= 0 ? "text-green-400" : "text-red-400" },
        { label: "Profit Factor", value: stats.profit_factor },
        { label: "Win Rate", value: stats.win_rate, color: parseFloat(stats.win_rate) >= 50 ? "text-green-400" : "text-red-400" },
        { label: "Sharpe Ratio", value: stats.sharpe_ratio, color: parseFloat(stats.sharpe_ratio) > 1 ? "text-blue-400" : "text-gray-300" },

        { label: "Total Trades", value: stats.total_trades },
        { label: "Stability (R²)", value: stats.stability },
        { label: "Profit Accel", value: stats.profit_accel },
        { label: "Activity Rate", value: stats.activity_rate },

        { label: "Avg PnL", value: stats.avg_pnl, color: parseFloat(stats.avg_pnl) >= 0 ? "text-green-400" : "text-red-400" },
        { label: "Avg Holding", value: stats.avg_holding },
        { label: "Max Profit", value: stats.max_profit, color: "text-green-400" },
        { label: "Max Loss", value: stats.max_loss, color: "text-red-400" },

        { label: "Max Drawdown", value: stats.max_drawdown, color: "text-red-400", fullWidth: true }
    ];

    return (
        <div className="bg-[#1e1e24] border border-white/5 rounded-xl overflow-hidden flex flex-col mb-6">
            <div className="flex border-b border-white/5 bg-black/20 px-4 py-3 justify-between items-center">
                <div className="flex items-center gap-2 text-sm font-bold text-purple-400">
                    <Activity size={16} />
                    Live Performance Analysis
                </div>
                <div className="text-[10px] text-gray-500 font-mono">
                    Session: {sessionId.split('-')[1]}...
                </div>
            </div>

            <div className="p-6 grid grid-cols-2 md:grid-cols-4 gap-y-6 gap-x-4">
                {metrics.map((m, i) => (
                    <div key={i} className={`flex flex-col ${m.fullWidth ? 'col-span-2 md:col-span-4 border-t border-white/5 pt-4 mt-2' : ''}`}>
                        <span className="text-gray-500 text-[10px] uppercase font-bold tracking-wider mb-1">{m.label}</span>
                        <span className={`font-mono font-bold text-xl ${m.color || 'text-white'} ${m.highlight ? 'text-2xl' : ''}`}>
                            {m.value || "-"}
                        </span>
                    </div>
                ))}
            </div>
        </div>
    );
};

export default LivePerformancePanel;
