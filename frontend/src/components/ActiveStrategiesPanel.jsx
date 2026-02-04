import React, { useState, useEffect, useCallback, useRef } from 'react';
import { List, ChevronDown, PlayCircle } from 'lucide-react';
import { listParameterVersions } from '../api/client';

/**
 * ActiveStrategiesPanel - Dynamic strategy configuration table with version selection.
 *
 * Renders parameter columns dynamically from parameterSchema.
 * Only fields with show_in_table !== false are displayed as columns.
 * Fixed columns: Rank, Symbol (always shown regardless of schema).
 * VERSION column: Dropdown to select from saved parameter versions.
 *
 * @param {Array} configList - List of strategy configurations
 * @param {Array} savedSymbols - Saved symbol info for name resolution
 * @param {Function} onVersionChange - Version change callback (idx, newParams, versionInfo) => void
 * @param {Object} parameterSchema - Strategy parameter schema from API
 * @param {string} strategyId - Current strategy ID (e.g., "rsi_martingale")
 */
const ActiveStrategiesPanel = ({
    configList,
    savedSymbols,
    onVersionChange,
    parameterSchema,
    strategyId,
    disabled = false,  // When true, version dropdown is read-only (for Live tab)
}) => {
    const activeCount = configList ? configList.filter(c => c.is_active !== false).length : 0;

    // Store versions per symbol: { symbol: { versions: [], loading: bool } }
    const [versionsBySymbol, setVersionsBySymbol] = useState({});

    // Track which configs have been auto-initialized to avoid infinite loops
    const initializedConfigs = useRef(new Set());

    // Extract table-visible fields from schema
    const fields = parameterSchema?.fields || [];
    const tableFields = fields.filter(f => f.show_in_table !== false);

    // Get the actual key from a field (schema may use 'key' or 'name')
    const getFieldKey = (field) => field.key || field.name;

    // Simple hash function for comparing params (similar to backend's MD5)
    const createConfigHash = (params) => {
        if (!params) return null;
        try {
            const str = JSON.stringify(params, Object.keys(params).sort());
            // Simple hash for comparison
            let hash = 0;
            for (let i = 0; i < str.length; i++) {
                const char = str.charCodeAt(i);
                hash = ((hash << 5) - hash) + char;
                hash = hash & hash;
            }
            return Math.abs(hash).toString(16).padStart(8, '0').slice(0, 12);
        } catch {
            return null;
        }
    };

    // Fetch versions for all active symbols
    const fetchVersionsForSymbols = useCallback(async () => {
        if (!strategyId || !configList) return;

        const activeConfigs = configList.filter(c => c.is_active !== false);
        const symbols = [...new Set(activeConfigs.map(c => c.symbol).filter(Boolean))];

        // Fetch versions for each unique symbol
        for (const symbol of symbols) {
            if (versionsBySymbol[symbol]?.versions) continue; // Already fetched

            setVersionsBySymbol(prev => ({
                ...prev,
                [symbol]: { ...prev[symbol], loading: true }
            }));

            try {
                const result = await listParameterVersions(strategyId, symbol);
                setVersionsBySymbol(prev => ({
                    ...prev,
                    [symbol]: {
                        versions: result.data || [],
                        loading: false
                    }
                }));
            } catch (err) {
                console.error(`Failed to fetch versions for ${symbol}:`, err);
                setVersionsBySymbol(prev => ({
                    ...prev,
                    [symbol]: { versions: [], loading: false }
                }));
            }
        }
    }, [strategyId, configList]);

    useEffect(() => {
        fetchVersionsForSymbols();
    }, [fetchVersionsForSymbols]);

    // Auto-select first version for configs without selected_version_id
    useEffect(() => {
        if (!onVersionChange || !configList) return;

        configList.forEach((cfg, idx) => {
            if (cfg.is_active === false) return;

            const configKey = `${idx}_${cfg.symbol}`;
            if (initializedConfigs.current.has(configKey)) return;

            const versions = versionsBySymbol[cfg.symbol]?.versions || [];
            const isLoading = versionsBySymbol[cfg.symbol]?.loading;

            if (isLoading || versions.length === 0) return;

            // Already has a selected version
            if (cfg.selected_version_id) {
                const exists = versions.find(v => v.id === cfg.selected_version_id);
                if (exists) {
                    initializedConfigs.current.add(configKey);
                    return;
                }
            }

            // Try to match by comparing current config params with version params
            // Extract only parameter keys from schema for comparison
            const paramKeys = fields.map(f => f.key || f.name);
            const currentParams = {};
            paramKeys.forEach(key => {
                if (cfg[key] !== undefined) {
                    currentParams[key] = cfg[key];
                }
            });

            // Find matching version by comparing params
            let matchedVersion = null;
            for (const v of versions) {
                if (v.params) {
                    const versionParams = {};
                    paramKeys.forEach(key => {
                        if (v.params[key] !== undefined) {
                            versionParams[key] = v.params[key];
                        }
                    });

                    // Compare JSON strings
                    if (JSON.stringify(currentParams) === JSON.stringify(versionParams)) {
                        matchedVersion = v;
                        break;
                    }
                }
            }

            // If no match, use first version as default
            const versionToUse = matchedVersion || versions[0];

            initializedConfigs.current.add(configKey);

            // Apply the version
            onVersionChange(idx, versionToUse.params, {
                id: versionToUse.id,
                version_name: versionToUse.version_name,
                config_hash: versionToUse.config_hash,
            });
        });
    }, [configList, versionsBySymbol, onVersionChange, fields]);

    // Handle version selection
    const handleVersionSelect = (idx, cfg, versionId) => {
        const symbol = cfg.symbol;
        const versions = versionsBySymbol[symbol]?.versions || [];
        const selectedVersion = versions.find(v => v.id === versionId);

        if (selectedVersion && onVersionChange) {
            onVersionChange(idx, selectedVersion.params, {
                id: selectedVersion.id,
                version_name: selectedVersion.version_name,
                config_hash: selectedVersion.config_hash,
            });
        }
    };

    // Find current version based on selected_version_id
    const findCurrentVersion = (cfg) => {
        const symbol = cfg.symbol;
        const versions = versionsBySymbol[symbol]?.versions || [];

        if (!versions.length) return null;

        // Match by selected_version_id
        if (cfg.selected_version_id) {
            const match = versions.find(v => v.id === cfg.selected_version_id);
            if (match) return match;
        }

        // Fallback: return first version (should have been auto-selected)
        return versions[0];
    };

    const formatValue = (cfg, field) => {
        const key = getFieldKey(field);
        const val = cfg[key];
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
                                <th className="px-4 py-3 text-right">Version</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-white/5">
                            {configList.map((cfg, idx) => {
                                if (cfg.is_active === false) return null;
                                const symbolInfo = savedSymbols.find(s => s.code === cfg.symbol);
                                const symbolName = symbolInfo ? symbolInfo.name : cfg.symbol;
                                const versions = versionsBySymbol[cfg.symbol]?.versions || [];
                                const isLoading = versionsBySymbol[cfg.symbol]?.loading;
                                const currentVersion = findCurrentVersion(cfg);

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
                                            {isLoading ? (
                                                <span className="text-xs text-gray-500">Loading...</span>
                                            ) : versions.length === 0 ? (
                                                <span className="text-xs text-yellow-500 italic">No saved versions</span>
                                            ) : (
                                                <div className="inline-flex items-center gap-1.5">
                                                    <div className="relative">
                                                        <select
                                                            value={currentVersion?.id || versions[0]?.id || ''}
                                                            onChange={(e) => handleVersionSelect(idx, cfg, e.target.value)}
                                                            disabled={disabled}
                                                            className={`appearance-none bg-gray-800 border border-gray-600 text-white text-xs rounded px-2 py-1.5 pr-7 focus:outline-none focus:border-indigo-500 min-w-[140px] ${disabled ? 'opacity-60 cursor-not-allowed' : 'cursor-pointer'}`}
                                                        >
                                                            {versions.map(v => (
                                                                <option key={v.id} value={v.id}>
                                                                    {v.version_name}
                                                                </option>
                                                            ))}
                                                        </select>
                                                        <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-3 h-3 text-gray-400 pointer-events-none" />
                                                    </div>
                                                    {currentVersion?.is_in_use && (
                                                        <PlayCircle className="w-4 h-4 text-green-400 flex-shrink-0" title="Currently running in live session" />
                                                    )}
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
