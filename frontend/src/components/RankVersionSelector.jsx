import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { ChevronDown, Save, PlayCircle, X, AlertCircle } from 'lucide-react';
import { listParameterVersions, createParameterVersion } from '../api/client';

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
    onRevertParams,  // Callback to revert params to selected version
    parameterSchema,
}) => {
    const [versions, setVersions] = useState([]);
    const [isLoading, setIsLoading] = useState(false);
    const [remainingSlots, setRemainingSlots] = useState(10);
    const [showSaveDialog, setShowSaveDialog] = useState(false);
    const [newVersionDesc, setNewVersionDesc] = useState('');
    const [isSaving, setIsSaving] = useState(false);
    const [saveError, setSaveError] = useState(null);

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

    // Check if params have been modified from selected version
    const isModified = useMemo(() => {
        if (!currentVersion || !currentParams || !parameterSchema?.fields) {
            return false;
        }
        const paramKeys = parameterSchema.fields.map(f => f.key || f.name);
        for (const key of paramKeys) {
            if (currentParams[key] !== currentVersion.params?.[key]) {
                return true;
            }
        }
        return false;
    }, [currentVersion, currentParams, parameterSchema]);

    // Handle save new version
    const handleSaveNewVersion = async () => {
        if (!newVersionDesc.trim()) {
            setSaveError('설명을 입력해주세요');
            return;
        }
        if (remainingSlots <= 0) {
            setSaveError('버전 슬롯이 가득 찼습니다. 기존 버전을 삭제해주세요.');
            return;
        }

        // Extract only strategy parameters (exclude metadata like uuid, symbol, etc.)
        const paramKeys = parameterSchema?.fields?.map(f => f.key || f.name) || [];
        const filteredParams = {};
        paramKeys.forEach(key => {
            if (currentParams[key] !== undefined) {
                filteredParams[key] = currentParams[key];
            }
        });

        setIsSaving(true);
        setSaveError(null);
        try {
            const result = await createParameterVersion({
                strategy_id: strategyId,
                symbol: symbol || null,
                description: newVersionDesc.trim(),
                params: filteredParams,
                is_default: false,
            });
            setShowSaveDialog(false);
            setNewVersionDesc('');
            await fetchVersions();  // Refresh versions list

            // Auto-select the newly saved version
            if (result?.data && onVersionSelect) {
                onVersionSelect(filteredParams, {
                    id: result.data.id,
                    version_name: result.data.version_name,
                    config_hash: result.data.config_hash,
                });
            }
        } catch (err) {
            console.error('Failed to save version:', err);
            const detail = err.response?.data?.detail || '버전 저장 실패';
            setSaveError(detail);
        } finally {
            setIsSaving(false);
        }
    };

    // Handle cancel (revert to selected version's params)
    const handleCancel = () => {
        if (currentVersion && onRevertParams) {
            onRevertParams(currentVersion.params);
        }
    };

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
        <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs text-gray-500">Version:</span>
            {isLoading ? (
                <span className="text-xs text-gray-500">Loading...</span>
            ) : versions.length === 0 ? (
                <div className="inline-flex items-center gap-2">
                    <span className="text-xs text-yellow-500 italic">No saved versions</span>
                    <button
                        onClick={() => setShowSaveDialog(true)}
                        className="inline-flex items-center gap-1 px-2 py-0.5 bg-indigo-600/80 hover:bg-indigo-600 text-white text-xs rounded transition-colors"
                        title="현재 파라미터를 첫 버전으로 저장"
                    >
                        <Save className="w-3 h-3" />
                        첫 버전 저장
                    </button>
                </div>
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

            {/* Modified indicator and action buttons */}
            {isModified && (
                <>
                    <span className="text-xs text-yellow-400 font-medium">(수정됨)</span>
                    <button
                        onClick={() => setShowSaveDialog(true)}
                        className="inline-flex items-center gap-1 px-2 py-0.5 bg-indigo-600/80 hover:bg-indigo-600 text-white text-xs rounded transition-colors"
                        title="현재 파라미터를 새 버전으로 저장"
                    >
                        <Save className="w-3 h-3" />
                        새 버전 저장
                    </button>
                    {onRevertParams && (
                        <button
                            onClick={handleCancel}
                            className="inline-flex items-center gap-1 px-2 py-0.5 bg-gray-600/80 hover:bg-gray-600 text-gray-200 text-xs rounded transition-colors"
                            title="선택된 버전의 파라미터로 복원"
                        >
                            <X className="w-3 h-3" />
                            취소
                        </button>
                    )}
                </>
            )}

            {/* Save Dialog */}
            {showSaveDialog && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
                    <div className="bg-gray-900 border border-gray-700 rounded-lg p-4 w-80 shadow-xl">
                        <h3 className="text-sm font-bold text-white mb-3">새 버전 저장</h3>

                        {saveError && (
                            <div className="flex items-center gap-1.5 text-xs text-red-400 bg-red-500/10 px-2 py-1.5 rounded mb-3">
                                <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />
                                {saveError}
                            </div>
                        )}

                        <div className="text-[10px] text-gray-500 mb-2">
                            자동 번호 포맷: <span className="text-indigo-400 font-mono">001_설명</span>
                        </div>
                        <input
                            type="text"
                            placeholder="설명 (예: 보수적, 공격적)"
                            value={newVersionDesc}
                            onChange={(e) => setNewVersionDesc(e.target.value)}
                            className="w-full bg-gray-800 border border-gray-600 rounded px-2 py-1.5 text-xs text-white placeholder-gray-500 focus:outline-none focus:border-indigo-500 mb-3"
                            autoFocus
                            maxLength={30}
                            onKeyDown={(e) => {
                                if (e.key === 'Enter') handleSaveNewVersion();
                                if (e.key === 'Escape') {
                                    setShowSaveDialog(false);
                                    setNewVersionDesc('');
                                    setSaveError(null);
                                }
                            }}
                        />
                        <div className="flex gap-2">
                            <button
                                onClick={handleSaveNewVersion}
                                disabled={isSaving || remainingSlots <= 0}
                                className="flex-1 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-xs py-1.5 rounded transition-colors"
                            >
                                {isSaving ? '저장 중...' : '저장'}
                            </button>
                            <button
                                onClick={() => {
                                    setShowSaveDialog(false);
                                    setNewVersionDesc('');
                                    setSaveError(null);
                                }}
                                className="px-3 bg-gray-700 hover:bg-gray-600 text-gray-300 text-xs py-1.5 rounded transition-colors"
                            >
                                닫기
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default RankVersionSelector;
