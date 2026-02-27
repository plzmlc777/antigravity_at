import React, { useState, useEffect, useCallback, useRef } from 'react';
import { List, ChevronDown } from 'lucide-react';

/**
 * ActiveStrategiesPanel - Dynamic strategy configuration table with preset selection.
 *
 * Reads presets from configList's parameter_presets (no API calls).
 * Renders parameter columns dynamically from parameterSchema.
 * Only fields with show_in_table !== false are displayed as columns.
 * Fixed columns: Rank, Symbol (always shown regardless of schema).
 *
 * @param {Array} configList - List of strategy configurations (each may have parameter_presets)
 * @param {Array} savedSymbols - Saved symbol info for name resolution
 * @param {Function} onVersionChange - Preset change callback (idx, newParams, presetInfo) => void
 * @param {Object} parameterSchema - Strategy parameter schema from API
 * @param {string} strategyId - Current strategy ID (e.g., "rsi_martingale")
 */
const ActiveStrategiesPanel = ({
    configList,
    savedSymbols,
    onVersionChange,
    parameterSchema,
    strategyId,
    disabled = false,  // When true, preset dropdown is read-only (for Live tab)
}) => {
    const activeCount = configList ? configList.filter(c => c.is_active !== false).length : 0;

    // Parse schema fields for table columns
    const getFieldKey = (field) => field.key || field.name;
    const fields = parameterSchema?.fields || [];

    // Filter table fields: show_in_table AND visible_when condition met by at least one active config
    const activeConfigs = configList ? configList.filter(c => c.is_active !== false) : [];
    const tableFields = fields.filter(f => {
        if (f.show_in_table === false) return false;
        if (!f.visible_when) return true;
        // Check if at least one active config satisfies visible_when
        return activeConfigs.some(cfg => {
            return Object.entries(f.visible_when).every(([key, condition]) => {
                const val = cfg[key] ?? fields.find(ff => (ff.key || ff.name) === key)?.default;
                if (typeof condition === 'object' && condition.ne !== undefined) {
                    return val !== condition.ne;
                }
                return val === condition;
            });
        });
    });

    // Auto-select first preset for configs without selected_preset_id
    const initializedConfigs = useRef(new Set());

    useEffect(() => {
        if (!onVersionChange || !configList) return;

        configList.forEach((cfg, idx) => {
            if (cfg.is_active === false) return;

            const configKey = `${idx}_${cfg.symbol}`;
            if (initializedConfigs.current.has(configKey)) return;

            const presets = cfg.parameter_presets || [];
            if (presets.length === 0) return;

            // Already has a selected preset
            if (cfg.selected_preset_id) {
                const exists = presets.find(p => p.id === cfg.selected_preset_id);
                if (exists) {
                    initializedConfigs.current.add(configKey);
                    return;
                }
            }

            // Try to match by comparing current config params with preset params
            const paramKeys = fields.map(f => f.key || f.name);
            const currentParams = {};
            paramKeys.forEach(key => {
                if (cfg[key] !== undefined) currentParams[key] = cfg[key];
            });

            let matchedPreset = null;
            for (const p of presets) {
                if (p.params) {
                    const presetParams = {};
                    paramKeys.forEach(key => {
                        if (p.params[key] !== undefined) presetParams[key] = p.params[key];
                    });
                    if (JSON.stringify(currentParams) === JSON.stringify(presetParams)) {
                        matchedPreset = p;
                        break;
                    }
                }
            }

            const presetToUse = matchedPreset || presets[0];
            initializedConfigs.current.add(configKey);

            onVersionChange(idx, presetToUse.params, {
                id: presetToUse.id,
                version_name: presetToUse.name,
                config_hash: presetToUse.config_hash,
            });
        });
    }, [configList, onVersionChange, fields]);

    // Handle preset selection
    const handlePresetSelect = (idx, cfg, presetId) => {
        const presets = cfg.parameter_presets || [];
        const selected = presets.find(p => p.id === presetId);

        if (selected && onVersionChange) {
            onVersionChange(idx, selected.params, {
                id: selected.id,
                version_name: selected.name,
                config_hash: selected.config_hash,
            });
        }
    };

    // Find current preset
    const findCurrentPreset = (cfg) => {
        const presets = cfg.parameter_presets || [];
        if (!presets.length) return null;

        if (cfg.selected_preset_id) {
            const match = presets.find(p => p.id === cfg.selected_preset_id);
            if (match) return match;
        }

        return presets[0];
    };

    const formatValue = (cfg, field) => {
        const key = getFieldKey(field);
        let val = cfg[key];
        // Fall back to field default if not set
        if (val == null || val === undefined) {
            val = field.default;
        }
        if (val == null || val === undefined) return '-';

        if (field.type === 'select' || field.type === 'time') {
            return String(val);
        }
        const hasPercent = (field.label || '').includes('%');
        return hasPercent ? `${val}%` : String(val);
    };

    return (
        <div className="bg-white/5 border border-white/10 rounded-xl overflow-hidden mb-6">
            <div className="bg-white/5 px-4 py-3 border-b border-white/10 flex justify-between items-center">
                <h3 className="font-bold text-gray-200 text-sm flex items-center gap-2">
                    <List size={14} className="text-gray-400" /> Active Strategy Configurations
                </h3>
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
                                    <th key={getFieldKey(f)} className="px-4 py-3" title={f.description}>
                                        {f.label}
                                    </th>
                                ))}
                                <th className="px-4 py-3 text-right">Preset</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-white/5">
                            {configList.map((cfg, idx) => {
                                if (cfg.is_active === false) return null;
                                const symbolName = cfg.symbol_name || savedSymbols.find(s => s.code === cfg.symbol)?.name || cfg.symbol;
                                const presets = cfg.parameter_presets || [];
                                const currentPreset = findCurrentPreset(cfg);

                                return (
                                    <tr key={cfg.uuid || idx} className="hover:bg-white/5 transition">
                                        <td className="px-4 py-3">
                                            <span className="bg-blue-500/20 text-blue-400 px-2 py-1 rounded text-xs font-bold">
                                                {cfg.tabName || `Rank ${cfg.rank ?? (idx + 1)}`}
                                            </span>
                                        </td>
                                        <td className="px-4 py-3 font-medium text-white">
                                            {symbolName} <span className="text-xs text-gray-500 ml-1">({cfg.symbol})</span>
                                        </td>
                                        {tableFields.map(field => {
                                            const fieldKey = getFieldKey(field);
                                            return (
                                                <td key={fieldKey} className="px-4 py-3 text-gray-300 text-xs">
                                                    {field.type === 'select' ? (
                                                        <span className={`px-2 py-1 rounded font-bold ${
                                                            fieldKey === 'direction'
                                                                ? (cfg[fieldKey] === 'rise' ? 'bg-red-500/20 text-red-400' : 'bg-blue-500/20 text-blue-400')
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
                                            );
                                        })}
                                        <td className="px-4 py-3 text-right">
                                            {presets.length === 0 ? (
                                                cfg.selected_preset_name ? (
                                                    <span className="text-xs text-gray-400 font-medium">{cfg.selected_preset_name}</span>
                                                ) : (
                                                    <span className="text-xs text-gray-600 italic">-</span>
                                                )
                                            ) : (
                                                <div className="inline-flex items-center gap-1.5">
                                                    <div className="relative">
                                                        <select
                                                            value={currentPreset?.id || presets[0]?.id || ''}
                                                            onChange={(e) => handlePresetSelect(idx, cfg, e.target.value)}
                                                            disabled={disabled}
                                                            className={`appearance-none bg-gray-800 border border-gray-600 text-white text-xs rounded px-2 py-1.5 pr-7 focus:outline-none focus:border-indigo-500 min-w-[140px] ${disabled ? 'opacity-60 cursor-not-allowed' : 'cursor-pointer'}`}
                                                        >
                                                            {presets.map(p => (
                                                                <option key={p.id} value={p.id}>
                                                                    {p.name}
                                                                </option>
                                                            ))}
                                                        </select>
                                                        <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-3 h-3 text-gray-400 pointer-events-none" />
                                                    </div>
                                                </div>
                                            )}
                                        </td>
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
