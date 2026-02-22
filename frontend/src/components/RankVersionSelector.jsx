import React, { useState, useMemo } from 'react';
import { ChevronDown, Save, Trash2, X, AlertCircle, Pencil } from 'lucide-react';

/**
 * RankVersionSelector - Compact preset dropdown for Rank tabs
 * Reads presets from profile's configList (no API calls).
 * All changes go through callbacks that update configList → isDirty → profile Save.
 */
const RankVersionSelector = ({
    presets = [],           // configList[rank].parameter_presets
    selectedPresetId,       // configList[rank].selected_preset_id
    currentParams,          // configList[rank] (full config)
    parameterSchema,
    disabled = false,       // true when profile is locked (live session in use)
    onSelectPreset,         // (presetId) => void
    onAddPreset,            // (description) => void
    onDeletePreset,         // (presetId) => void
    onRenamePreset,         // (presetId, newName) => void
    onUpdatePreset,         // () => void — overwrite selected preset with current params
    onRevertParams,         // (params) => void — revert to selected preset's params
}) => {
    const [showSaveDialog, setShowSaveDialog] = useState(false);
    const [newPresetDesc, setNewPresetDesc] = useState('');
    const [saveError, setSaveError] = useState(null);
    const [showRenameDialog, setShowRenameDialog] = useState(false);
    const [renameValue, setRenameValue] = useState('');
    const [showOverwriteConfirm, setShowOverwriteConfirm] = useState(false);
    const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

    // Find current preset
    const currentPreset = useMemo(() => {
        if (!presets.length) return null;
        if (selectedPresetId) {
            return presets.find(p => p.id === selectedPresetId) || null;
        }
        return null;
    }, [presets, selectedPresetId]);

    const isCustom = !currentPreset && presets.length > 0;

    // Check if params have been modified from selected preset
    const isModified = useMemo(() => {
        if (!currentPreset || !currentParams || !parameterSchema?.fields) return false;
        const paramKeys = parameterSchema.fields.map(f => f.key || f.name);
        for (const key of paramKeys) {
            if (currentParams[key] !== currentPreset.params?.[key]) return true;
        }
        return false;
    }, [currentPreset, currentParams, parameterSchema]);

    // Handle save new preset
    const handleSavePreset = () => {
        if (!newPresetDesc.trim()) {
            setSaveError('설명을 입력해주세요');
            return;
        }
        if (onAddPreset) {
            onAddPreset(newPresetDesc.trim());
        }
        setShowSaveDialog(false);
        setNewPresetDesc('');
        setSaveError(null);
    };

    // Handle preset selection
    const handleSelect = (e) => {
        const presetId = e.target.value;
        if (presetId === 'custom') return;
        if (onSelectPreset) onSelectPreset(presetId);
    };

    // Handle cancel (revert to selected preset's params)
    const handleCancel = () => {
        if (currentPreset && onRevertParams) {
            onRevertParams(currentPreset.params);
        }
    };

    return (
        <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs text-gray-500">Preset:</span>
            {presets.length === 0 ? (
                <div className="inline-flex items-center gap-2">
                    <span className="text-xs text-yellow-500 italic">No saved presets</span>
                    {!disabled && (
                        <button
                            onClick={() => setShowSaveDialog(true)}
                            className="inline-flex items-center gap-1 px-2 py-0.5 bg-indigo-600/80 hover:bg-indigo-600 text-white text-xs rounded transition-colors"
                            title="현재 파라미터를 첫 프리셋으로 저장"
                        >
                            <Save className="w-3 h-3" />
                            첫 프리셋 저장
                        </button>
                    )}
                </div>
            ) : (
                <div className="relative inline-flex items-center gap-1.5">
                    <select
                        value={currentPreset?.id || 'custom'}
                        onChange={handleSelect}
                        disabled={disabled}
                        className={`appearance-none bg-gray-800 border border-gray-600 text-white text-xs rounded px-2 py-1 pr-6 focus:outline-none focus:border-indigo-500 min-w-[120px] ${disabled ? 'opacity-60 cursor-not-allowed' : 'cursor-pointer'}`}
                    >
                        {isCustom && (
                            <option value="custom" disabled className="text-gray-400">
                                (Custom)
                            </option>
                        )}
                        {presets.map(p => (
                            <option key={p.id} value={p.id}>
                                {p.name}
                            </option>
                        ))}
                    </select>
                    <ChevronDown className="absolute right-1.5 top-1/2 -translate-y-1/2 w-3 h-3 text-gray-400 pointer-events-none" />
                </div>
            )}
            <span className="text-[10px] text-gray-600">
                ({presets.length}/20)
            </span>

            {/* Modified indicator and action buttons */}
            {!disabled && (isModified || isCustom) && (
                <>
                    {isModified && <span className="text-xs text-yellow-400 font-medium">(수정됨)</span>}
                    {isModified && currentPreset && onUpdatePreset && (
                        <button
                            onClick={() => setShowOverwriteConfirm(true)}
                            className="inline-flex items-center gap-1 px-2 py-0.5 bg-emerald-600/80 hover:bg-emerald-600 text-white text-xs rounded transition-colors"
                            title="현재 파라미터를 선택된 프리셋에 덮어쓰기"
                        >
                            <Save className="w-3 h-3" />
                            저장
                        </button>
                    )}
                    <button
                        onClick={() => setShowSaveDialog(true)}
                        className="inline-flex items-center gap-1 px-2 py-0.5 bg-indigo-600/80 hover:bg-indigo-600 text-white text-xs rounded transition-colors"
                        title="현재 파라미터를 새 프리셋으로 저장"
                    >
                        <Save className="w-3 h-3" />
                        새 프리셋 저장
                    </button>
                    {isModified && onRevertParams && (
                        <button
                            onClick={handleCancel}
                            className="inline-flex items-center gap-1 px-2 py-0.5 bg-gray-600/80 hover:bg-gray-600 text-gray-200 text-xs rounded transition-colors"
                            title="선택된 프리셋의 파라미터로 복원"
                        >
                            <X className="w-3 h-3" />
                            취소
                        </button>
                    )}
                </>
            )}

            {/* Edit & Delete buttons for current preset */}
            {!disabled && currentPreset && (
                <>
                    {onRenamePreset && (
                        <button
                            onClick={() => {
                                const match = currentPreset.name?.match(/^\d{3}_(.*)/);
                                setRenameValue(match ? match[1] : currentPreset.name || '');
                                setShowRenameDialog(true);
                            }}
                            className="inline-flex items-center gap-1 px-1.5 py-0.5 text-xs rounded transition-colors hover:bg-blue-600/20 text-gray-500 hover:text-blue-400"
                            title="프리셋 이름 변경"
                        >
                            <Pencil className="w-3 h-3" />
                        </button>
                    )}
                    {onDeletePreset && (
                        <button
                            onClick={() => setShowDeleteConfirm(true)}
                            className="inline-flex items-center gap-1 px-1.5 py-0.5 text-xs rounded transition-colors hover:bg-red-600/20 text-gray-500 hover:text-red-400"
                            title="현재 프리셋 삭제"
                        >
                            <Trash2 className="w-3 h-3" />
                        </button>
                    )}
                </>
            )}

            {/* Save Dialog */}
            {showSaveDialog && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
                    <div className="bg-gray-900 border border-gray-700 rounded-lg p-4 w-80 shadow-xl">
                        <h3 className="text-sm font-bold text-white mb-3">새 프리셋 저장</h3>

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
                            value={newPresetDesc}
                            onChange={(e) => setNewPresetDesc(e.target.value)}
                            className="w-full bg-gray-800 border border-gray-600 rounded px-2 py-1.5 text-xs text-white placeholder-gray-500 focus:outline-none focus:border-indigo-500 mb-3"
                            autoFocus
                            maxLength={30}
                            onKeyDown={(e) => {
                                if (e.key === 'Enter') handleSavePreset();
                                if (e.key === 'Escape') {
                                    setShowSaveDialog(false);
                                    setNewPresetDesc('');
                                    setSaveError(null);
                                }
                            }}
                        />
                        <div className="flex gap-2">
                            <button
                                onClick={handleSavePreset}
                                className="flex-1 bg-indigo-600 hover:bg-indigo-700 text-white text-xs py-1.5 rounded transition-colors"
                            >
                                저장
                            </button>
                            <button
                                onClick={() => {
                                    setShowSaveDialog(false);
                                    setNewPresetDesc('');
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
            {/* Rename Dialog */}
            {showRenameDialog && currentPreset && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
                    <div className="bg-gray-900 border border-gray-700 rounded-lg p-4 w-80 shadow-xl">
                        <h3 className="text-sm font-bold text-white mb-3">프리셋 이름 변경</h3>
                        <div className="text-[10px] text-gray-500 mb-2">
                            현재: <span className="text-indigo-400 font-mono">{currentPreset.name}</span>
                        </div>
                        <input
                            type="text"
                            placeholder="새 설명"
                            value={renameValue}
                            onChange={(e) => setRenameValue(e.target.value)}
                            className="w-full bg-gray-800 border border-gray-600 rounded px-2 py-1.5 text-xs text-white placeholder-gray-500 focus:outline-none focus:border-indigo-500 mb-3"
                            autoFocus
                            maxLength={30}
                            onKeyDown={(e) => {
                                if (e.key === 'Enter') {
                                    if (renameValue.trim() && onRenamePreset) {
                                        // Preserve NNN_ prefix
                                        const match = currentPreset.name?.match(/^(\d{3})_/);
                                        const prefix = match ? match[1] : '001';
                                        const cleanDesc = renameValue.trim().replace(/[^\w\s가-힣-]/g, '').slice(0, 30) || 'unnamed';
                                        onRenamePreset(currentPreset.id, `${prefix}_${cleanDesc}`);
                                        setShowRenameDialog(false);
                                        setRenameValue('');
                                    }
                                }
                                if (e.key === 'Escape') {
                                    setShowRenameDialog(false);
                                    setRenameValue('');
                                }
                            }}
                        />
                        <div className="flex gap-2">
                            <button
                                onClick={() => {
                                    if (renameValue.trim() && onRenamePreset) {
                                        const match = currentPreset.name?.match(/^(\d{3})_/);
                                        const prefix = match ? match[1] : '001';
                                        const cleanDesc = renameValue.trim().replace(/[^\w\s가-힣-]/g, '').slice(0, 30) || 'unnamed';
                                        onRenamePreset(currentPreset.id, `${prefix}_${cleanDesc}`);
                                        setShowRenameDialog(false);
                                        setRenameValue('');
                                    }
                                }}
                                className="flex-1 bg-indigo-600 hover:bg-indigo-700 text-white text-xs py-1.5 rounded transition-colors"
                            >
                                변경
                            </button>
                            <button
                                onClick={() => {
                                    setShowRenameDialog(false);
                                    setRenameValue('');
                                }}
                                className="px-3 bg-gray-700 hover:bg-gray-600 text-gray-300 text-xs py-1.5 rounded transition-colors"
                            >
                                닫기
                            </button>
                        </div>
                    </div>
                </div>
            )}
            {/* Overwrite Confirm Dialog */}
            {showOverwriteConfirm && currentPreset && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
                    <div className="bg-gray-900 border border-gray-700 rounded-lg p-4 w-80 shadow-xl">
                        <h3 className="text-sm font-bold text-white mb-3">프리셋 덮어쓰기</h3>
                        <p className="text-xs text-gray-300 mb-4">
                            프리셋 <span className="text-emerald-400 font-mono">{currentPreset.name}</span>에 현재 파라미터를 덮어쓰시겠습니까?
                        </p>
                        <div className="flex gap-2">
                            <button
                                onClick={() => {
                                    onUpdatePreset();
                                    setShowOverwriteConfirm(false);
                                }}
                                className="flex-1 bg-emerald-600 hover:bg-emerald-700 text-white text-xs py-1.5 rounded transition-colors"
                            >
                                덮어쓰기
                            </button>
                            <button
                                onClick={() => setShowOverwriteConfirm(false)}
                                className="px-3 bg-gray-700 hover:bg-gray-600 text-gray-300 text-xs py-1.5 rounded transition-colors"
                            >
                                닫기
                            </button>
                        </div>
                    </div>
                </div>
            )}
            {/* Delete Confirm Dialog */}
            {showDeleteConfirm && currentPreset && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
                    <div className="bg-gray-900 border border-gray-700 rounded-lg p-4 w-80 shadow-xl">
                        <h3 className="text-sm font-bold text-white mb-3">프리셋 삭제</h3>
                        <p className="text-xs text-gray-300 mb-4">
                            프리셋 <span className="text-red-400 font-mono">{currentPreset.name}</span>을(를) 삭제하시겠습니까?
                        </p>
                        <div className="flex gap-2">
                            <button
                                onClick={() => {
                                    onDeletePreset(currentPreset.id);
                                    setShowDeleteConfirm(false);
                                }}
                                className="flex-1 bg-red-600 hover:bg-red-700 text-white text-xs py-1.5 rounded transition-colors"
                            >
                                삭제
                            </button>
                            <button
                                onClick={() => setShowDeleteConfirm(false)}
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
