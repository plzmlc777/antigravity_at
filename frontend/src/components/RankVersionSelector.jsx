import React, { useState, useEffect, useCallback } from 'react';
import { ChevronDown, Save, PlayCircle } from 'lucide-react';
import { listParameterVersions } from '../api/client';

/**
 * RankVersionSelector - Compact version dropdown for Rank tabs
 * Shows current version and allows quick selection
 */
const RankVersionSelector = ({
    strategyId,
    symbol,
    currentParams,
    selectedVersionId,
    onVersionSelect,
    parameterSchema,
}) => {
    const [versions, setVersions] = useState([]);
    const [isLoading, setIsLoading] = useState(false);
    const [remainingSlots, setRemainingSlots] = useState(10);

    // Fetch versions
    const fetchVersions = useCallback(async () => {
        if (!strategyId || !symbol) return;

        setIsLoading(true);
        try {
            const result = await listParameterVersions(strategyId, symbol);
            setVersions(result.data || []);
            setRemainingSlots(result.remaining_slots ?? 10);
        } catch (err) {
            console.error('Failed to fetch versions:', err);
        } finally {
            setIsLoading(false);
        }
    }, [strategyId, symbol]);

    useEffect(() => {
        fetchVersions();
    }, [fetchVersions]);

    // Find current version by matching params or selectedVersionId
    const findCurrentVersion = () => {
        if (!versions.length) return null;

        // First try to match by selectedVersionId
        if (selectedVersionId) {
            const match = versions.find(v => v.id === selectedVersionId);
            if (match) return match;
        }

        // Try to match by comparing params
        if (currentParams && parameterSchema?.fields) {
            const paramKeys = parameterSchema.fields.map(f => f.key || f.name);

            for (const v of versions) {
                if (v.params) {
                    let isMatch = true;
                    for (const key of paramKeys) {
                        if (currentParams[key] !== v.params[key]) {
                            isMatch = false;
                            break;
                        }
                    }
                    if (isMatch) return v;
                }
            }
        }

        return null;
    };

    const currentVersion = findCurrentVersion();
    const isCustom = !currentVersion && versions.length > 0;

    // Handle version selection
    const handleSelect = (e) => {
        const versionId = e.target.value;
        if (versionId === 'custom') return;

        const selected = versions.find(v => v.id === versionId);
        if (selected && onVersionSelect) {
            onVersionSelect(selected.params, {
                id: selected.id,
                version_name: selected.version_name,
                config_hash: selected.config_hash,
            });
        }
    };

    if (!strategyId || !symbol) {
        return null;
    }

    return (
        <div className="flex items-center gap-2">
            <span className="text-xs text-gray-500">Version:</span>
            {isLoading ? (
                <span className="text-xs text-gray-500">Loading...</span>
            ) : versions.length === 0 ? (
                <span className="text-xs text-yellow-500 italic">No saved versions</span>
            ) : (
                <div className="relative inline-flex items-center gap-1.5">
                    <select
                        value={currentVersion?.id || 'custom'}
                        onChange={handleSelect}
                        className="appearance-none bg-gray-800 border border-gray-600 text-white text-xs rounded px-2 py-1 pr-6 focus:outline-none focus:border-indigo-500 cursor-pointer min-w-[120px]"
                    >
                        {isCustom && (
                            <option value="custom" disabled className="text-gray-400">
                                (Custom)
                            </option>
                        )}
                        {versions.map(v => (
                            <option key={v.id} value={v.id}>
                                {v.version_name}
                            </option>
                        ))}
                    </select>
                    <ChevronDown className="absolute right-1.5 top-1/2 -translate-y-1/2 w-3 h-3 text-gray-400 pointer-events-none" />
                    {currentVersion?.is_in_use && (
                        <PlayCircle className="w-4 h-4 text-green-400 flex-shrink-0" title="Running in live session" />
                    )}
                </div>
            )}
            <span className="text-[10px] text-gray-600">
                ({versions.length}/10)
            </span>
        </div>
    );
};

export default RankVersionSelector;
