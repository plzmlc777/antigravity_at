import React from 'react';
import {
    ComposedChart,
    Bar,
    Cell,
    CartesianGrid,
    XAxis,
    YAxis,
    Tooltip,
    ReferenceLine,
    ResponsiveContainer
} from 'recharts';

/**
 * Stability Analysis Chart - N-Bucket based stability visualization
 * Used by both StrategyView (Rank Tab) and IntegratedAnalysis (Integrated Tab)
 *
 * @param {Array} bucketStats - N-bucket stats (preferred): [{block: "Q1", date_range: "01/15-02/10", count: 12, win_rate: 60, total_pnl: 5.2}, ...]
 * @param {Array} decileStats - Legacy monthly stats (fallback): [{block: "24-01", count: 12, win_rate: 60, total_pnl: 5.2}, ...]
 * @param {string} title - Chart title
 */
const MonthlyAnalysisChart = ({
    bucketStats,
    decileStats,
    title = "Strategy Stability (N-Bucket Analysis)"
}) => {
    // Use bucketStats if available, otherwise fall back to decileStats
    const stats = (bucketStats && bucketStats.length > 0) ? bucketStats : decileStats;

    if (!stats || stats.length === 0) {
        return null;
    }

    // Get display label: use start date from date_range if available
    const getDisplayLabel = (item) => {
        if (item.date_range && item.date_range.includes('-')) {
            // Format: "01/15-02/10" → "01/15"
            return item.date_range.split('-')[0];
        }
        return item.block; // Fallback to block (Q1, Q2, or 24-01)
    };

    return (
        <div className="mt-4 pt-4 border-t border-white/10">
            <h4 className="text-sm font-bold text-gray-400 mb-2">{title}</h4>
            <div className="h-[200px] w-full bg-black/20 rounded-lg p-2">
                <ResponsiveContainer width="100%" height="100%">
                    <ComposedChart data={stats} margin={{ bottom: 60, left: 0, right: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#333" vertical={false} />
                        <XAxis
                            dataKey="block"
                            stroke="#666"
                            tickLine={false}
                            interval={0}
                            tick={({ x, y, payload, index }) => {
                                const data = stats[index];
                                if (!data) return null;
                                const label = getDisplayLabel(data);
                                return (
                                    <g transform={`translate(${x},${y})`}>
                                        <text x={0} y={10} dy={0} textAnchor="middle" fill="#9ca3af" fontSize={10}>{label}</text>
                                        <text x={0} y={10} dy={12} textAnchor="middle" fill="#60a5fa" fontSize={10} fontWeight="bold">{data.count}</text>
                                        <text x={0} y={10} dy={24} textAnchor="middle" fill="#fbbf24" fontSize={10}>{data.win_rate}%</text>
                                        <text x={0} y={10} dy={36} textAnchor="middle" fill={data.total_pnl >= 0 ? "#4ade80" : "#ef4444"} fontSize={10} fontWeight="bold">{data.total_pnl}%</text>
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
                            labelFormatter={(label, payload) => {
                                if (payload && payload[0]) {
                                    const data = payload[0].payload;
                                    if (data.date_range) {
                                        return `Period: ${data.date_range}`;
                                    }
                                }
                                return `Bucket: ${label}`;
                            }}
                        />
                        <ReferenceLine yAxisId="left" y={0} stroke="#666" />
                        <Bar yAxisId="left" dataKey="total_pnl" radius={[4, 4, 0, 0]}>
                            {stats.map((entry, index) => (
                                <Cell key={`cell-${index}`} fill={entry.total_pnl >= 0 ? '#4ade80' : '#ef4444'} />
                            ))}
                        </Bar>
                    </ComposedChart>
                </ResponsiveContainer>
            </div>
            <div className="flex justify-center gap-4 mt-1 text-[10px] text-gray-500">
                <div className="flex items-center gap-1"><div className="w-2 h-2 bg-green-400 rounded-sm"></div><span>Profit</span></div>
                <div className="flex items-center gap-1"><div className="w-2 h-2 bg-red-400 rounded-sm"></div><span>Loss</span></div>
                <div className="flex items-center gap-1"><span className="text-blue-400 font-bold">12</span><span>= Count</span></div>
                <div className="flex items-center gap-1"><span className="font-bold" style={{ color: '#fbbf24' }}>60%</span><span>= Win Rate</span></div>
                <div className="flex items-center gap-1"><span className="text-green-400 font-bold">5.2%</span><span>= Realized PnL</span></div>
            </div>
        </div>
    );
};

export default MonthlyAnalysisChart;
