import React from 'react';

/**
 * ActiveStrategiesPanel - Dynamic strategy configuration table.
 *
 * Renders parameter columns dynamically from parameterSchema.
 * Only fields with show_in_table !== false are displayed as columns.
 * Fixed columns: Rank, Symbol (always shown regardless of schema).
 *
 * @param {Array} configList - List of strategy configurations
 * @param {Array} savedSymbols - Saved symbol info for name resolution
 * @param {Function} onEdit - Edit callback (idx) => void
 * @param {Object} parameterSchema - Strategy parameter schema from API
 */
const ActiveStrategiesPanel = ({ configList, savedSymbols, onEdit, parameterSchema }) => {
    const activeCount = configList ? configList.filter(c => c.is_active !== false).length : 0;

    // Extract table-visible fields from schema
    const fields = parameterSchema?.fields || [];
    const tableFields = fields.filter(f => f.show_in_table !== false);

    const formatValue = (cfg, field) => {
        const val = cfg[field.name];
        if (val == null || val === undefined) return '-';

        if (field.type === 'select' || field.type === 'time') {
            return String(val);
        }
        // number: append % if label contains (%)
        const hasPercent = (field.label || '').includes('%');
        return hasPercent ? `${val}%` : String(val);
    };

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
                                {tableFields.map(f => (
                                    <th key={f.name} className="px-4 py-3" title={f.description}>
                                        {f.label}
                                    </th>
                                ))}
                                {onEdit && <th className="px-4 py-3 text-right">Settings</th>}
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-white/5">
                            {configList.map((cfg, idx) => {
                                if (cfg.is_active === false) return null;
                                const symbolInfo = savedSymbols.find(s => s.code === cfg.symbol);
                                const symbolName = symbolInfo ? symbolInfo.name : cfg.symbol;

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
                                        {tableFields.map(field => (
                                            <td key={field.name} className="px-4 py-3 text-gray-300 text-xs">
                                                {field.type === 'select' ? (
                                                    <span className={`px-2 py-1 rounded font-bold ${
                                                        field.name === 'direction'
                                                            ? (cfg[field.name] === 'rise' ? 'bg-red-500/20 text-red-400' : 'bg-blue-500/20 text-blue-400')
                                                            : 'bg-purple-500/20 text-purple-300'
                                                    }`}>
                                                        {formatValue(cfg, field)}
                                                    </span>
                                                ) : (
                                                    <span className="text-gray-300 font-medium">
                                                        {formatValue(cfg, field)}
                                                    </span>
                                                )}
                                            </td>
                                        ))}
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
