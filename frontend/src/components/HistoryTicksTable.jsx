import React from 'react';
import { Clock, TrendingUp, TrendingDown } from 'lucide-react';

const HistoryTicksTable = ({ ticks = [], onRowClick }) => {
    // Reverse to show newest first
    const reversedTicks = [...ticks].reverse();

    return (
        <div className="flex flex-col h-full overflow-hidden">
            <div className="overflow-auto scrollbar-thin scrollbar-thumb-gray-700">
                <table className="w-full text-xs text-left">
                    <thead className="sticky top-0 bg-[#1e1e24] text-gray-400 font-medium">
                        <tr>
                            <th className="px-4 py-2">Time</th>
                            <th className="px-4 py-2 text-right">Price</th>
                            <th className="px-4 py-2 text-right">Change</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-white/5">
                        {reversedTicks.length === 0 ? (
                            <tr>
                                <td colSpan="3" className="px-4 py-8 text-center text-gray-600 italic">
                                    No tick history available
                                </td>
                            </tr>
                        ) : (
                            reversedTicks.map((tick, i) => {
                                const prevTick = reversedTicks[i + 1];
                                const change = prevTick ? tick.price - prevTick.price : 0;
                                const isPositive = change > 0;
                                const isNegative = change < 0;

                                return (
                                    <tr
                                        key={i}
                                        className={`transition-colors ${onRowClick ? 'cursor-pointer hover:bg-white/10' : 'hover:bg-white/5'}`}
                                        onClick={() => onRowClick && onRowClick(tick)}
                                    >
                                        <td className="px-4 py-2 font-mono text-gray-400">
                                            {tick.time}
                                        </td>
                                        <td className={`px-4 py-2 text-right font-mono ${isPositive ? 'text-red-400' : isNegative ? 'text-blue-400' : 'text-gray-300'}`}>
                                            {tick.price.toLocaleString()}
                                        </td>
                                        <td className="px-4 py-2 text-right">
                                            <div className="flex items-center justify-end gap-1">
                                                {isPositive && <TrendingUp size={10} className="text-red-400" />}
                                                {isNegative && <TrendingDown size={10} className="text-blue-400" />}
                                                <span className={`${isPositive ? 'text-red-400' : isNegative ? 'text-blue-400' : 'text-gray-500'}`}>
                                                    {change !== 0 ? (change > 0 ? `+${change}` : change) : '-'}
                                                </span>
                                            </div>
                                        </td>
                                    </tr>
                                );
                            })
                        )}
                    </tbody>
                </table>
            </div>
        </div>
    );
};

export default HistoryTicksTable;
