import React, { useEffect, useState } from 'react';
import { ArrowLeft, Activity, TrendingUp, TrendingDown, Clock, Search } from 'lucide-react';
import { ComposedChart, Area, Scatter, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import { getSessionDetails } from '../api/client';

const LiveReplayView = ({ sessionId, onClose }) => {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [chartData, setChartData] = useState([]);
    const [tradePoints, setTradePoints] = useState([]);

    useEffect(() => {
        loadSession();
    }, [sessionId]);

    const loadSession = async () => {
        try {
            setLoading(true);
            const res = await getSessionDetails(sessionId);
            setData(res);

            // Format Chart Data
            // Candles: { timestamp: ISO, close: 12345 }
            const cData = res.candles.map(c => {
                const dt = new Date(c.timestamp);
                return {
                    timeProp: dt.getTime(), // For sorting/axis
                    time: dt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
                    price: c.close,
                    fullDate: c.timestamp
                };
            });
            setChartData(cData);

            // Format Trades for Scatter
            const tPoints = res.executions.map(ex => {
                const dt = new Date(ex.signal_timestamp);
                return {
                    timeProp: dt.getTime(),
                    time: dt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
                    price: ex.theoretical_price,
                    type: ex.signal_type, // BUY or SELL
                    qty: ex.executed_quantity || ex.requested_quantity,
                    status: ex.status
                };
            });
            setTradePoints(tPoints);

        } catch (err) {
            console.error("Failed to load replay:", err);
        } finally {
            setLoading(false);
        }
    };

    if (loading) return <div className="p-8 text-center text-gray-500 animate-pulse">Loading Session Replay...</div>;
    if (!data) return <div className="p-8 text-center text-red-500">Failed to load session data.</div>;

    const { session, executions } = data;
    const pnl = session.current_capital - session.initial_capital;

    // Custom Dot for Trades
    const renderTradeDot = (props) => {
        const { cx, cy, payload } = props;
        if (!cx || !cy) return null;

        const isBuy = payload.type === 'BUY';
        const color = isBuy ? '#4ade80' : '#f87171';

        return (
            <g transform={`translate(${cx},${cy})`}>
                <circle r={5} fill={color} stroke="#fff" strokeWidth={2} />
                {isBuy ? (
                    <path d="M-3,1 L0,-4 L3,1" fill="none" stroke="#fff" strokeWidth={1} />
                ) : (
                    <path d="M-3,-1 L0,4 L3,-1" fill="none" stroke="#fff" strokeWidth={1} />
                )}
            </g>
        );
    };

    return (
        <div className="h-full flex flex-col bg-[#1e1e24] rounded-xl overflow-hidden border border-white/5">
            {/* Header */}
            <div className="bg-gray-900/50 p-4 flex justify-between items-center border-b border-white/5">
                <div className="flex items-center gap-4">
                    <button
                        onClick={onClose}
                        className="p-2 hover:bg-white/10 rounded-full transition-colors text-gray-400 hover:text-white"
                    >
                        <ArrowLeft size={20} />
                    </button>
                    <div>
                        <div className="flex items-center gap-2">
                            <h2 className="text-xl font-bold text-white">{session.symbol}</h2>
                            <span className="text-sm text-gray-400">{session.strategy_name}</span>
                        </div>
                        <div className="text-xs text-gray-500">
                            {new Date(session.started_at).toLocaleString()} ~ {session.stopped_at ? new Date(session.stopped_at).toLocaleTimeString() : 'Running?'}
                        </div>
                    </div>
                </div>

                <div className="flex gap-6 text-right">
                    <div>
                        <div className="text-xs text-gray-500">Net PnL</div>
                        <div className={`text-lg font-mono font-bold ${pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                            {pnl > 0 ? '+' : ''}{pnl.toLocaleString()}
                        </div>
                    </div>
                    <div>
                        <div className="text-xs text-gray-500">Trades</div>
                        <div className="text-lg font-mono font-bold text-white">
                            {executions.length}
                        </div>
                    </div>
                </div>
            </div>

            {/* Content Body */}
            <div className="flex-1 flex overflow-hidden">
                {/* Chart Section */}
                <div className="flex-1 p-4 relative min-w-0">
                    <div className="w-full h-full bg-black/20 rounded-xl p-2">
                        <ResponsiveContainer width="100%" height="100%">
                            <ComposedChart data={chartData}>
                                <defs>
                                    <linearGradient id="replayGradient" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="5%" stopColor="#8884d8" stopOpacity={0.3} />
                                        <stop offset="95%" stopColor="#8884d8" stopOpacity={0} />
                                    </linearGradient>
                                </defs>
                                <CartesianGrid strokeDasharray="3 3" stroke="#333" vertical={false} />
                                <XAxis
                                    dataKey="time"
                                    stroke="#666"
                                    tick={{ fontSize: 11 }}
                                    minTickGap={30}
                                />
                                <YAxis
                                    domain={['auto', 'auto']}
                                    stroke="#666"
                                    tick={{ fontSize: 11 }}
                                    tickFormatter={(v) => v.toLocaleString()}
                                    width={60}
                                />
                                <Tooltip
                                    contentStyle={{ backgroundColor: '#111', borderColor: '#333' }}
                                    itemStyle={{ color: '#ccc' }}
                                    labelStyle={{ color: '#666' }}
                                />
                                {/* Price Line */}
                                <Area
                                    type="monotone"
                                    dataKey="price"
                                    stroke="#8884d8"
                                    fill="url(#replayGradient)"
                                    strokeWidth={2}
                                    dot={false}
                                />
                                {/* Executions Scatter - must map to existing X-Axis timestamps or be clever */}
                                {/* Recharts Scatter requires numerical X usually. Mixing Categorical X (Time Str) is tricky. */}
                                {/* Workaround: Use same data array but add 'tradeType' fields to specific points? 
                                    Better: 'ComposedChart' shares data. If trade happened at 09:01, finding 09:01 data point and adding marker info.
                                */}
                            </ComposedChart>
                        </ResponsiveContainer>

                        {/* Overlay Trades manually if easier, or iterate to merge trade markers into chartData */}
                        {/* Merging trade data into chartData for rendering dots on the Area line */}
                        {/* Since we have tradePoints separate, let's try mapping them. */}
                    </div>

                    {/* Re-render Chart with Merged Data for Markers */}
                    {/* Implementation Detail: Modify 'chartData' above to include 'tradeMarker': 'BUY'/'SELL' */}
                </div>

                {/* Sidebar: Executions */}
                <div className="w-80 bg-gray-900/30 border-l border-white/5 p-4 overflow-y-auto">
                    <h3 className="text-sm font-bold text-gray-400 mb-4 flex items-center gap-2">
                        <Clock size={14} /> Execution Log
                    </h3>
                    <div className="space-y-3">
                        {executions.map((ex) => (
                            <div key={ex.id} className="bg-black/40 p-3 rounded-lg border border-white/5 text-xs">
                                <div className="flex justify-between mb-1">
                                    <span className={`font-bold ${ex.signal_type === 'BUY' ? 'text-green-400' : 'text-red-400'}`}>
                                        {ex.signal_type}
                                    </span>
                                    <span className="text-gray-500">
                                        {new Date(ex.signal_timestamp).toLocaleTimeString()}
                                    </span>
                                </div>
                                <div className="flex justify-between items-end">
                                    <div>
                                        <div className="text-gray-400">Price</div>
                                        <div className="text-white font-mono">{ex.theoretical_price.toLocaleString()}</div>
                                    </div>
                                    <div className="text-right">
                                        <div className="text-gray-400">Qty</div>
                                        <div className="text-white font-mono">{ex.requested_quantity}</div>
                                    </div>
                                </div>
                                <div className="mt-2 pt-2 border-t border-white/5 flex justified-between">
                                    <span className="text-gray-600 uppercase">{ex.status}</span>
                                    {ex.slippage_percent !== 0 && (
                                        <span className="text-orange-400 ml-auto">Slip: {ex.slippage_percent}%</span>
                                    )}
                                </div>
                            </div>
                        ))}
                        {executions.length === 0 && (
                            <div className="text-gray-600 text-center italic mt-10">No executions recorded.</div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
};

export default LiveReplayView;
