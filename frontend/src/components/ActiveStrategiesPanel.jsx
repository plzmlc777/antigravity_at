import React, { useState, useEffect, useCallback, useRef } from 'react';
import { List, ChevronDown, Eye, X } from 'lucide-react';
import { convertSchemaToParamDefs } from '../constants/strategies';

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
 * @param {string} groupStatus - 'RUNNING' | 'PAUSED' | 'STOPPED' | 'IDLE'
 * @param {Function} onAiModeChange - (idx, mode) => void
 * @param {string} aiSearchConditions - Shared AI search conditions string
 * @param {Function} onAiSearchConditionsChange - (value) => void
 * @param {Object} aiOptimizeParams - { params: { leverage: [1,5,10], ... } }
 * @param {Function} onAiOptimizeParamsChange - (params) => void
 */
const ActiveStrategiesPanel = ({
    configList,
    savedSymbols,
    onVersionChange,
    parameterSchema,
    strategyId,
    disabled = false,  // When true, preset dropdown is read-only (for Live tab)
    groupStatus,
    onAiModeChange,
    aiSearchConditions,
    onAiSearchConditionsChange,
    aiOptimizeParams,
    onAiOptimizeParamsChange,
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

    // Auto-select preset for configs without selected_preset_id (Profile page only)
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
            const matched = findCurrentPreset(cfg);
            if (matched && matched.id !== '__saved__') {
                initializedConfigs.current.add(configKey);
                onVersionChange(idx, matched.params, {
                    id: matched.id,
                    version_name: matched.name,
                    config_hash: matched.config_hash,
                });
                return;
            }

            // No match — only apply first preset if this is NOT a live session
            if (!disabled && presets[0]) {
                initializedConfigs.current.add(configKey);
                onVersionChange(idx, presets[0].params, {
                    id: presets[0].id,
                    version_name: presets[0].name,
                    config_hash: presets[0].config_hash,
                });
            }
        });
    }, [configList, onVersionChange, fields, disabled]);

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

    // Find current preset by ID or by matching params
    const findCurrentPreset = (cfg) => {
        const presets = cfg.parameter_presets || [];
        if (!presets.length) return null;

        // 1. Direct ID match
        if (cfg.selected_preset_id) {
            const match = presets.find(p => p.id === cfg.selected_preset_id);
            if (match) return match;
        }

        // 2. Fallback: match by comparing current config params with preset params
        // Only compare keys present in BOTH config and preset (skip missing keys)
        const paramKeys = fields.map(f => f.key || f.name);
        let bestMatch = null;
        let bestMatchCount = 0;
        for (const p of presets) {
            if (!p.params) continue;
            let matchCount = 0;
            let mismatch = false;
            for (const key of paramKeys) {
                const cfgVal = cfg[key];
                const presetVal = p.params[key];
                // Skip keys not present in either side
                if (cfgVal == null && presetVal == null) continue;
                if (cfgVal == null || presetVal == null) continue;
                // Both have a value — compare with type coercion
                if (String(cfgVal) === String(presetVal)) {
                    matchCount++;
                } else {
                    mismatch = true;
                    break;
                }
            }
            // Require at least 3 matching keys and no mismatches
            if (!mismatch && matchCount >= 3 && matchCount > bestMatchCount) {
                bestMatch = p;
                bestMatchCount = matchCount;
            }
        }
        if (bestMatch) return bestMatch;

        // 3. No match found — show saved preset name if available
        if (cfg.selected_preset_name) {
            return { id: '__saved__', name: cfg.selected_preset_name };
        }

        return null;
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

    // AI mode editing is disabled when group is RUNNING or PAUSED
    const isAiEditable = groupStatus !== 'RUNNING' && groupStatus !== 'PAUSED';

    // Check if any config has AI mode enabled
    const hasAnyAiMode = configList?.some(c => c.is_active !== false && c.ai_symbol_mode === 'ai');

    // Check if a config's symbol was changed by AI (different from original)
    const isSymbolChanged = (cfg) => {
        return cfg.original_symbol && cfg.original_symbol !== cfg.symbol;
    };

    // Preset detail popup state
    const [presetDetail, setPresetDetail] = useState(null); // { cfg, presetName }

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
                                {onAiModeChange && (
                                    <th className="px-4 py-3 text-center">AI</th>
                                )}
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
                                            {presets.length === 0 || (disabled && !currentPreset) ? (
                                                (currentPreset?.name || cfg.selected_preset_name) ? (
                                                    <span className="inline-flex items-center gap-1.5">
                                                        <span className="text-xs text-gray-400 font-medium">{currentPreset?.name || cfg.selected_preset_name}</span>
                                                        <button
                                                            onClick={() => setPresetDetail({ cfg, presetName: currentPreset?.name || cfg.selected_preset_name })}
                                                            className="p-0.5 hover:bg-white/10 rounded transition-colors text-gray-500 hover:text-gray-300"
                                                            title="파라미터 전체 보기"
                                                        >
                                                            <Eye size={12} />
                                                        </button>
                                                    </span>
                                                ) : (
                                                    <span className="text-xs text-gray-600 italic">-</span>
                                                )
                                            ) : (
                                                <div className="inline-flex items-center gap-1.5">
                                                    <div className="relative">
                                                        <select
                                                            value={currentPreset?.id || ''}
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
                                                    <button
                                                        onClick={() => setPresetDetail({ cfg, presetName: currentPreset?.name || cfg.selected_preset_name })}
                                                        className="p-1 hover:bg-white/10 rounded transition-colors text-gray-500 hover:text-gray-300"
                                                        title="파라미터 전체 보기"
                                                    >
                                                        <Eye size={12} />
                                                    </button>
                                                </div>
                                            )}
                                        </td>
                                        {onAiModeChange && (
                                            <td className="px-4 py-3 text-center">
                                                <select
                                                    value={cfg.ai_symbol_mode || 'static'}
                                                    onChange={(e) => onAiModeChange(idx, e.target.value)}
                                                    disabled={!isAiEditable}
                                                    className={`appearance-none text-xs rounded px-2 py-1.5 pr-6 border focus:outline-none min-w-[80px] ${
                                                        cfg.ai_symbol_mode === 'ai'
                                                            ? 'bg-purple-900/40 border-purple-500/50 text-purple-300 font-bold'
                                                            : cfg.ai_symbol_mode === 'reset'
                                                                ? 'bg-teal-900/40 border-teal-500/50 text-teal-300 font-bold'
                                                                : 'bg-gray-800 border-gray-600 text-gray-300'
                                                    } ${!isAiEditable ? 'opacity-60 cursor-not-allowed' : 'cursor-pointer'}`}
                                                >
                                                    <option value="static">Static</option>
                                                    <option value="ai">AI</option>
                                                    <option value="reset">Reset</option>
                                                </select>
                                                {isSymbolChanged(cfg) && cfg.ai_symbol_mode !== 'reset' && (
                                                    <div className="text-[9px] text-amber-400/70 mt-0.5">
                                                        원래: {cfg.original_symbol}
                                                    </div>
                                                )}
                                                {cfg.ai_symbol_mode === 'reset' && isSymbolChanged(cfg) && (
                                                    <div className="text-[9px] text-teal-400/70 mt-0.5">
                                                        → {cfg.original_symbol}
                                                    </div>
                                                )}
                                            </td>
                                        )}
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                )}
            </div>

            {/* AI Search Conditions (shared, shown when any rank has AI mode) */}
            {onAiModeChange && hasAnyAiMode && (
                <div className="px-4 py-3 border-t border-white/10 bg-purple-900/10">
                    <label className="block text-purple-300 text-[10px] font-bold tracking-wider uppercase mb-2">
                        AI 종목 검색 조건 (공통)
                    </label>
                    <textarea
                        value={aiSearchConditions || ''}
                        onChange={(e) => onAiSearchConditionsChange?.(e.target.value)}
                        disabled={!isAiEditable}
                        placeholder="예: 최근 거래량이 폭증했는데 가격은 별로 오르지 않은 종목"
                        className={`w-full bg-black/40 border border-purple-500/20 rounded-lg px-4 py-2.5 text-white text-sm outline-none focus:border-purple-500/50 transition-all resize-none ${
                            !isAiEditable ? 'opacity-60 cursor-not-allowed' : ''
                        }`}
                        rows={2}
                    />
                    <p className="text-gray-500 text-[9px] mt-1">
                        AI 모드 세션의 사이클 완료 시, 조건에 맞는 종목으로 자동 전환합니다
                    </p>

                    {/* Applied Optimization Params - show when running with optimize params */}
                    {groupStatus === 'RUNNING' && aiOptimizeParams?.params?.length > 0 && (
                        <div className="mt-3 pt-3 border-t border-purple-500/10">
                            <label className="block text-purple-300 text-[10px] font-bold tracking-wider uppercase mb-2">
                                AI 최적화 파라미터 (현재 적용 값)
                            </label>
                            <div className="space-y-1.5">
                                {activeConfigs.map((cfg, ci) => {
                                    const optParamDefs = convertSchemaToParamDefs(parameterSchema);
                                    const selectedParams = aiOptimizeParams.params;
                                    const rankLabel = cfg.tabName || `Rank ${cfg.rank ?? (ci + 1)}`;
                                    return (
                                        <div key={ci} className="flex items-center gap-2 flex-wrap">
                                            <span className="text-[10px] text-gray-500 w-12 shrink-0">{rankLabel}</span>
                                            {selectedParams.map(key => {
                                                const def = optParamDefs.find(p => p.key === key);
                                                const label = def?.label || key;
                                                const val = cfg[key] ?? '-';
                                                return (
                                                    <span key={key} className="inline-flex items-center gap-1 px-2 py-1 rounded bg-purple-900/30 border border-purple-500/20 text-[10px]">
                                                        <span className="text-purple-400 font-medium">{label}</span>
                                                        <span className="text-white font-bold">{String(val)}</span>
                                                    </span>
                                                );
                                            })}
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                    )}

                    {/* Parameter Optimization Section */}
                    {onAiOptimizeParamsChange && (
                        <div className="mt-3 pt-3 border-t border-purple-500/10">
                            <label className="block text-purple-300 text-[10px] font-bold tracking-wider uppercase mb-2">
                                파라미터 최적화 (선택)
                            </label>
                            <p className="text-gray-500 text-[9px] mb-2">
                                체크한 파라미터의 최적화 범위를 AI가 자동 결정하여 그리드 서치합니다
                            </p>
                            <div className="grid grid-cols-2 sm:grid-cols-3 gap-1.5">
                                {(() => {
                                    // params is now a list of parameter names: ["leverage", "position_side"]
                                    const selectedParams = Array.isArray(aiOptimizeParams?.params) ? aiOptimizeParams.params : [];
                                    const optParamDefs = convertSchemaToParamDefs(parameterSchema);
                                    const refConfig = activeConfigs[0] || {};

                                    // Apply visible_when filter
                                    const filteredParams = optParamDefs.filter(param => {
                                        if (!param.visible_when) return true;
                                        try {
                                            const conditionFields = Object.keys(param.visible_when);
                                            if (conditionFields.some(f => selectedParams.includes(f))) return true;
                                            return activeConfigs.some(cfg => {
                                                return Object.entries(param.visible_when).every(([fieldName, ops]) => {
                                                    const val = cfg[fieldName] ?? fields.find(f => (f.key || f.name) === fieldName)?.default;
                                                    const numVal = typeof val === 'string' ? parseFloat(val) : val;
                                                    if (typeof ops !== 'object' || ops === null) return true;
                                                    return Object.entries(ops).every(([op, target]) => {
                                                        switch (op) {
                                                            case 'gt':  return numVal > target;
                                                            case 'gte': return numVal >= target;
                                                            case 'lt':  return numVal < target;
                                                            case 'lte': return numVal <= target;
                                                            case 'eq':  return val == target;
                                                            case 'ne':  return val != target;
                                                            default:    return true;
                                                        }
                                                    });
                                                });
                                            });
                                        } catch { return true; }
                                    });

                                    return filteredParams.map(param => {
                                        const key = param.key;
                                        const isChecked = selectedParams.includes(key);
                                        const currentVal = refConfig[key] ?? param.defaultValue;

                                        return (
                                            <label key={key} className={`flex items-center gap-2 rounded px-2.5 py-1.5 cursor-pointer transition-colors ${
                                                isChecked ? 'bg-purple-900/30 border border-purple-500/30' : 'bg-black/20 border border-transparent'
                                            } ${!isAiEditable ? 'opacity-60 cursor-not-allowed' : 'hover:bg-purple-900/15'}`}>
                                                <input
                                                    type="checkbox"
                                                    checked={isChecked}
                                                    disabled={!isAiEditable}
                                                    onChange={(e) => {
                                                        let next;
                                                        if (e.target.checked) {
                                                            next = [...selectedParams, key];
                                                        } else {
                                                            next = selectedParams.filter(p => p !== key);
                                                        }
                                                        onAiOptimizeParamsChange(
                                                            next.length > 0 ? { params: next } : null
                                                        );
                                                    }}
                                                    className="accent-purple-500"
                                                />
                                                <div className="min-w-0">
                                                    <span className="text-[11px] text-gray-300 font-medium">{param.label}</span>
                                                    <span className="text-gray-500 text-[9px] ml-1">({currentVal ?? '-'})</span>
                                                </div>
                                            </label>
                                        );
                                    });
                                })()}
                            </div>
                            {(() => {
                                const selectedParams = Array.isArray(aiOptimizeParams?.params) ? aiOptimizeParams.params : [];
                                if (selectedParams.length === 0) return null;
                                return (
                                    <div className="mt-2 px-3 py-2 rounded text-[10px] bg-purple-900/20 border border-purple-500/20 text-purple-300">
                                        {selectedParams.length}개 파라미터 선택 — AI가 현재 설정값 기준으로 최적화 범위를 자동 결정합니다
                                    </div>
                                );
                            })()}
                        </div>
                    )}
                </div>
            )}
            {/* Preset Detail Popup */}
            {presetDetail && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
                     onClick={() => setPresetDetail(null)}>
                    <div className="bg-[#1a1a24] border border-white/10 rounded-xl shadow-2xl w-full max-w-md max-h-[80vh] overflow-hidden"
                         onClick={(e) => e.stopPropagation()}>
                        {/* Header */}
                        <div className="flex items-center justify-between px-5 py-3.5 border-b border-white/10 bg-white/5">
                            <div>
                                <h3 className="text-sm font-bold text-white">적용 중인 파라미터</h3>
                                <span className="text-[10px] text-gray-500">{presetDetail.presetName || 'Custom'}</span>
                            </div>
                            <button onClick={() => setPresetDetail(null)}
                                    className="p-1.5 hover:bg-white/10 rounded-lg transition-colors text-gray-400 hover:text-white">
                                <X size={16} />
                            </button>
                        </div>
                        {/* Body */}
                        <div className="overflow-y-auto max-h-[65vh] p-4">
                            <table className="w-full text-xs">
                                <thead>
                                    <tr className="text-gray-500 text-[10px] uppercase">
                                        <th className="text-left pb-2 font-medium">Parameter</th>
                                        <th className="text-right pb-2 font-medium">Value</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-white/5">
                                    {(() => {
                                        const allFields = convertSchemaToParamDefs(parameterSchema);
                                        const cfg = presetDetail.cfg;
                                        const optimizeParams = Array.isArray(aiOptimizeParams?.params) ? aiOptimizeParams.params : [];

                                        // Filter by visible_when
                                        const visibleFields = allFields.filter(f => {
                                            if (!f.visible_when) return true;
                                            try {
                                                return Object.entries(f.visible_when).every(([key, condition]) => {
                                                    const val = cfg[key] ?? allFields.find(ff => ff.key === key)?.defaultValue;
                                                    if (typeof condition === 'object' && condition !== null) {
                                                        if (condition.ne !== undefined) return val !== condition.ne;
                                                        if (condition.gt !== undefined) return val > condition.gt;
                                                        return true;
                                                    }
                                                    return val === condition;
                                                });
                                            } catch { return true; }
                                        });

                                        return visibleFields.map(f => {
                                            const val = cfg[f.key] ?? f.defaultValue;
                                            const isOptParam = optimizeParams.includes(f.key);
                                            const displayVal = val != null ? String(val) : '-';
                                            const hasPercent = (f.label || '').includes('%');

                                            return (
                                                <tr key={f.key} className={isOptParam ? 'bg-purple-900/15' : ''}>
                                                    <td className="py-2 pr-4">
                                                        <span className="text-gray-300">{f.label}</span>
                                                        {isOptParam && (
                                                            <span className="ml-1.5 text-[8px] px-1 py-0.5 rounded bg-purple-500/20 text-purple-400 font-bold">OPT</span>
                                                        )}
                                                    </td>
                                                    <td className={`py-2 text-right font-mono font-medium ${isOptParam ? 'text-purple-300' : 'text-white'}`}>
                                                        {hasPercent ? `${displayVal}%` : displayVal}
                                                    </td>
                                                </tr>
                                            );
                                        });
                                    })()}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default ActiveStrategiesPanel;
