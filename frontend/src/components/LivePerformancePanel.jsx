import React, { useEffect, useState } from 'react';
import { getSessionStats, getLiveStatus, getAggregateStats } from '../api/client';
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

const LivePerformancePanel = ({ configList = [], savedSymbols = [] }) => {
    const [allStats, setAllStats] = useState({}); // { rankIndex: stats }
    const [totalStats, setTotalStats] = useState(EMPTY_STATS);
    const [activeTab, setActiveTab] = useState('total'); // 'total' or rank index (0, 1, 2...)
    const [loading, setLoading] = useState(false);

    // Active Ranks from configList
    const activeRanks = configList
        .map((c, i) => ({ ...c, originalIndex: i }))
        .filter(c => c.is_active !== false);

    // Polling for updates
    useEffect(() => {
        const fetchData = async () => {
            try {
                // 1. Get Live Status to find active sessions
                const sessions = await getLiveStatus();
                const statsMap = {};
                const activeSessionIds = [];

                // 2. Map sessions to ranks and fetch stats
                const fetchPromises = activeRanks.map(async (rank) => {
                    const session = sessions.find(s => s.symbol === rank.symbol && s.is_running);
                    if (session) {
                        activeSessionIds.push(session.session_id);
                        try {
                            const s = await getSessionStats(session.session_id);
                            if (s) statsMap[rank.originalIndex] = s;
                        } catch (e) {
                            console.error(`Error fetching stats for ${rank.symbol}`, e);
                        }
                    }
                });

                await Promise.all(fetchPromises);

                // 3. Fetch Aggregate Stats from Backend (Accurate portfolio calculation)
                if (activeSessionIds.length > 0) {
                    try {
                        const agg = await getAggregateStats(activeSessionIds);
                        if (agg) setTotalStats(agg);
                    } catch (e) {
                        console.error("Aggregation Fetch Error", e);
                    }
                } else {
                    setTotalStats(EMPTY_STATS);
                }

                setAllStats(statsMap);

            } catch (err) {
                console.error("MultiPerformance Fetch Error", err);
            }
        };

        fetchData();
        const interval = setInterval(fetchData, 5000);
        return () => clearInterval(interval);
    }, [configList]);

    const displayStats = activeTab === 'total' ? totalStats : (allStats[activeTab] || EMPTY_STATS);

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
            <div className="flex flex-col border-b border-white/5 bg-black/20">
                {/* Panel Title */}
                <div className="px-4 py-3 flex items-center gap-2 text-sm font-bold text-purple-400 border-b border-white/5">
                    <Activity size={16} />
                    Live Performance Analysis
                </div>

                {/* Tab Bar */}
                <div className="px-4 py-2 flex items-center justify-between overflow-x-auto no-scrollbar">
                    <div className="flex items-center gap-1">
                        <button
                            onClick={() => setActiveTab('total')}
                            className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all whitespace-nowrap ${activeTab === 'total' ? 'bg-purple-500/20 text-purple-400 border border-purple-500/30' : 'text-gray-500 hover:text-gray-300'}`}
                        >
                            TOTAL
                        </button>
                        <div className="w-px h-4 bg-white/5 mx-1" />
                        {activeRanks.map((rank) => (
                            <button
                                key={rank.originalIndex}
                                onClick={() => setActiveTab(rank.originalIndex)}
                                className={`px-3 py-1.5 rounded-lg text-[10px] font-bold transition-all whitespace-nowrap flex items-center gap-2 ${activeTab === rank.originalIndex ? 'bg-blue-500/20 text-blue-400 border border-blue-500/30' : 'text-gray-500 hover:text-gray-300'}`}
                            >
                                RANK {rank.originalIndex + 1}
                                <span className="opacity-50 font-normal">
                                    {savedSymbols.find(s => s.code === rank.symbol)?.name || rank.symbol}
                                </span>
                            </button>
                        ))}
                    </div>
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
