import React from 'react';

const ActiveStrategiesPanel = ({ configList, savedSymbols, onEdit }) => {
    // Calculate active count
    const activeCount = configList ? configList.filter(c => c.is_active !== false).length : 0;

    return (
        <div className="bg-white/5 border border-white/10 rounded-xl overflow-hidden mb-6">
            <div className="bg-white/5 px-4 py-3 border-b border-white/10 flex justify-between items-center">
                <h3 className="font-bold text-gray-200 text-sm">Active Strategy Configurations</h3>
                <span className="text-xs text-gray-400">{activeCount} Active</span>
            </div>
            <div className="overflow-x-auto">
                {activeCount === 0 ? (
                    <div className="text-gray-500 italic py-10 text-center text-sm">
                        No Active Strategies Configured. <br />
                        Enable strategies in the Rank tabs to add them here.
                    </div>
                ) : (
                    <table className="w-full text-sm text-left">
                        <thead className="text-xs text-gray-400 bg-white/5 uppercase">
                            <tr>
                                <th className="px-4 py-3">Rank</th>
                                <th className="px-4 py-3">Symbol</th>
                                <th className="px-4 py-3">Interval</th>
                                <th className="px-4 py-3">Direction</th>
                                <th className="px-4 py-3">Delay</th>
                                <th className="px-4 py-3">Target / Stop</th>
                                <th className="px-4 py-3">Trailing</th>
                                {onEdit && <th className="px-4 py-3 text-right">Settings</th>}
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-white/5">
                            {configList.map((cfg, idx) => {
                                if (cfg.is_active === false) return null;
                                const symbolInfo = savedSymbols.find(s => s.code === cfg.symbol);
                                const symbolName = symbolInfo ? symbolInfo.name : cfg.symbol;
                                const isRise = (cfg.direction || 'rise') === 'rise';

                                return (
                                    <tr key={cfg.uuid || idx} className="hover:bg-white/5 transition">
                                        <td className="px-4 py-3">
                                            <span className="bg-blue-500/20 text-blue-400 px-2 py-1 rounded text-xs font-bold">
                                                {cfg.tabName || `Rank ${idx + 1}`}
                                            </span>
                                        </td>
                                        <td className="px-4 py-3 font-medium text-white">
                                            {symbolName} <span className="text-xs text-gray-500 ml-1">({cfg.symbol})</span>
                                        </td>
                                        <td className="px-4 py-3 text-gray-300">
                                            {cfg.interval || "1m"}
                                        </td>
                                        <td className="px-4 py-3">
                                            <span className={`flex items-center gap-1 text-xs px-2 py-1 rounded font-bold ${isRise ? 'bg-red-500/20 text-red-400' : 'bg-blue-500/20 text-blue-400'}`}>
                                                {isRise ? '🚀 Rise' : '📉 Fall'}
                                            </span>
                                        </td>
                                        <td className="px-4 py-3">
                                            <span className="text-yellow-400 font-bold">{cfg.delay_minutes || 0}m</span>
                                        </td>
                                        <td className="px-4 py-3">
                                            <div className="text-xs font-medium">
                                                <span className="text-green-400">{cfg.target_percent}%</span>
                                                <span className="text-gray-500 mx-1">/</span>
                                                <span className="text-red-400">{cfg.safety_stop_percent}%</span>
                                            </div>
                                        </td>
                                        <td className="px-4 py-3">
                                            <div className="text-xs text-blue-400">
                                                {cfg.trailing_start_percent}% / {cfg.trailing_stop_drop}%
                                            </div>
                                        </td>
                                        {onEdit && (
                                            <td className="px-4 py-3 text-right">
                                                <button
                                                    onClick={() => onEdit(idx)}
                                                    className="text-xs bg-gray-700 hover:bg-gray-600 px-2 py-1 rounded text-white transition"
                                                >
                                                    Edit
                                                </button>
                                            </td>
                                        )}
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                )}
            </div>
        </div>
    );
};

export default ActiveStrategiesPanel;
