import React, { useEffect, useState } from 'react';
import { getHistorySessions } from '../api/client';

const LiveHistoryList = ({ onSelect }) => {
    const [sessions, setSessions] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        fetchSessions();
    }, []);

    const fetchSessions = async () => {
        try {
            const data = await getHistorySessions();
            setSessions(data);
        } catch (error) {
            console.error("Failed to fetch history:", error);
        } finally {
            setLoading(false);
        }
    };

    if (loading) return <div className="p-4 text-gray-400">Loading history...</div>;

    if (sessions.length === 0) {
        return <div className="p-4 text-gray-500">No trading history found.</div>;
    }

    return (
        <div className="overflow-x-auto">
            <table className="min-w-full text-sm text-left text-gray-400">
                <thead className="text-xs text-gray-500 uppercase bg-gray-800">
                    <tr>
                        <th className="px-4 py-3">Date</th>
                        <th className="px-4 py-3">Symbol</th>
                        <th className="px-4 py-3">Strategy</th>
                        <th className="px-4 py-3 text-right">PnL</th>
                        <th className="px-4 py-3">Status</th>
                    </tr>
                </thead>
                <tbody>
                    {sessions.map((s) => {
                        const start = new Date(s.started_at);
                        const pnl = s.current_capital - s.initial_capital;
                        const isProfit = pnl >= 0;

                        return (
                            <tr
                                key={s.id}
                                onClick={() => onSelect(s.id)}
                                className="border-b border-gray-800 hover:bg-gray-800 cursor-pointer transition-colors"
                            >
                                <td className="px-4 py-3">
                                    {start.toLocaleDateString()} <span className="text-gray-600 text-xs">{start.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                                </td>
                                <td className="px-4 py-3 font-medium text-white">{s.symbol}</td>
                                <td className="px-4 py-3">{s.strategy_name}</td>
                                <td className={`px-4 py-3 text-right font-medium ${isProfit ? 'text-red-400' : 'text-blue-400'}`}>
                                    {pnl.toLocaleString()} KRW
                                </td>
                                <td className="px-4 py-3">
                                    <span className={`px-2 py-1 rounded text-xs ${s.status === 'STOPPED' ? 'bg-gray-700 text-gray-300' :
                                            s.status === 'ERROR' ? 'bg-red-900 text-red-200' :
                                                'bg-green-900 text-green-200'
                                        }`}>
                                        {s.status}
                                    </span>
                                </td>
                            </tr>
                        );
                    })}
                </tbody>
            </table>
        </div>
    );
};

export default LiveHistoryList;
