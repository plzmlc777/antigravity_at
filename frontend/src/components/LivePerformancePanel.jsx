import React, { useEffect, useState } from 'react';
import { getSessionStats } from '../api/client';
import { Activity, TrendingUp, TrendingDown, DollarSign } from 'lucide-react';

const EMPTY_STATS = {
    total_return: "0.00%",
    profit_factor: "0.00",
    win_rate: "0.0%",
    sharpe_ratio: "0.00",
    total_trades: 0,
    stability: "0.00",
    profit_accel: "0.00x",
    activity_rate: "0.0%",
    avg_pnl: "0.00%",
    avg_holding: "0m",
    max_profit: "0.00%",
    max_loss: "0.00%",
    max_drawdown: "0.00%"
};

const LivePerformancePanel = ({ sessionId, strategyConfig }) => {
    const [stats, setStats] = useState(EMPTY_STATS);
    const [loading, setLoading] = useState(false);

    // Polling for updates
    useEffect(() => {
        if (!sessionId) {
            setStats(EMPTY_STATS);
            return;
        }

        const fetchData = async () => {
            try {
                const s = await getSessionStats(sessionId);
                if (s) setStats(s);
            } catch (err) {
                console.error("LivePerformance Fetch Error", err);
                // Keep existing or show empty? 
                // Usually better to keep what we have or stick to empty if it was a 404
                if (err.response?.status === 404) setStats(EMPTY_STATS);
            }
        };

        fetchData();
        const interval = setInterval(fetchData, 5000); // Poll every 5s
        return () => clearInterval(interval);
    }, [sessionId]);

    const displayStats = stats || EMPTY_STATS;

    // Define the Grid Layout based on User Request
    // Metric Keys from Backend: 
    // total_return, profit_factor, win_rate, sharpe_ratio
    // total_trades, stability, profit_accel, activity_rate
    // avg_pnl, avg_holding, max_profit, max_loss, max_drawdown

    const metrics = [
        { label: "Total Return", value: displayStats.total_return, highlight: true, color: parseFloat(displayStats.total_return) >= 0 ? "text-green-400" : "text-red-400" },
        { label: "Profit Factor", value: displayStats.profit_factor },
        { label: "Win Rate", value: displayStats.win_rate, color: parseFloat(displayStats.win_rate) >= 50 ? "text-green-400" : "text-red-400" },
        { label: "Sharpe Ratio", value: displayStats.sharpe_ratio, color: parseFloat(displayStats.sharpe_ratio) > 1 ? "text-blue-400" : "text-gray-300" },

        { label: "Total Trades", value: displayStats.total_trades },
        { label: "Stability (R²)", value: displayStats.stability },
        { label: "Profit Accel", value: displayStats.profit_accel },
        { label: "Activity Rate", value: displayStats.activity_rate },

        { label: "Avg PnL", value: displayStats.avg_pnl, color: parseFloat(displayStats.avg_pnl) >= 0 ? "text-green-400" : "text-red-400" },
        { label: "Avg Holding", value: displayStats.avg_holding },
        { label: "Max Profit", value: displayStats.max_profit, color: "text-green-400" },
        { label: "Max Loss", value: displayStats.max_loss, color: "text-red-400" },

        { label: "Max Drawdown", value: displayStats.max_drawdown, color: "text-red-400", fullWidth: true }
    ];

    return (
        <div className="bg-[#1e1e24] border border-white/5 rounded-xl overflow-hidden flex flex-col mb-6">
            <div className="flex border-b border-white/5 bg-black/20 px-4 py-3 justify-between items-center">
                <div className="flex items-center gap-2 text-sm font-bold text-purple-400">
                    <Activity size={16} />
                    Live Performance Analysis
                </div>
                <div className="text-[10px] text-gray-500 font-mono">
                    Session: {sessionId ? (sessionId.split('-')[1] || sessionId.slice(0, 8)) : "NONE"}...
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
