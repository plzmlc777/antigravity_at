import React, { useState, useEffect, useCallback } from 'react';
import { Save, RotateCcw, Trash2, ChevronDown, ChevronUp, Star, Clock, Hash } from 'lucide-react';
import {
    listParameterVersions,
    createParameterVersion,
    deleteParameterVersion,
    restoreParameterVersion,
} from '../api/client';

/**
 * Parameter Version Manager Component
 *
 * Allows users to:
 * - Save current parameters as a named version
 * - View list of saved versions
 * - Restore a previous version
 * - Delete versions
 */
const ParameterVersionManager = ({
    strategyId,
    symbol,
    currentParams,
    onRestore,
    className = '',
}) => {
    const [versions, setVersions] = useState([]);
    const [isExpanded, setIsExpanded] = useState(false);
    const [isLoading, setIsLoading] = useState(false);
    const [showSaveForm, setShowSaveForm] = useState(false);
    const [newVersionName, setNewVersionName] = useState('');
    const [newVersionDesc, setNewVersionDesc] = useState('');
    const [error, setError] = useState(null);

    // Fetch versions when expanded
    const fetchVersions = useCallback(async () => {
        if (!strategyId) return;
        setIsLoading(true);
        setError(null);
        try {
            const result = await listParameterVersions(strategyId, symbol || '');
            setVersions(result.data || []);
        } catch (err) {
            console.error('Failed to fetch versions:', err);
            setError('Failed to load versions');
        } finally {
            setIsLoading(false);
        }
    }, [strategyId, symbol]);

    useEffect(() => {
        if (isExpanded) {
            fetchVersions();
        }
    }, [isExpanded, fetchVersions]);

    // Save current params as new version
    const handleSave = async () => {
        if (!newVersionName.trim()) {
            setError('Version name is required');
            return;
        }

        setIsLoading(true);
        setError(null);
        try {
            await createParameterVersion({
                strategy_id: strategyId,
                symbol: symbol || null,
                version_name: newVersionName.trim(),
                description: newVersionDesc.trim() || null,
                params: currentParams,
                is_default: false,
            });
            setNewVersionName('');
            setNewVersionDesc('');
            setShowSaveForm(false);
            await fetchVersions();
        } catch (err) {
            console.error('Failed to save version:', err);
            setError('Failed to save version');
        } finally {
            setIsLoading(false);
        }
    };

    // Restore a version
    const handleRestore = async (versionId, versionName) => {
        if (!window.confirm(`Restore "${versionName}" parameters?`)) return;

        setIsLoading(true);
        setError(null);
        try {
            const result = await restoreParameterVersion(versionId);
            if (result.data?.params && onRestore) {
                onRestore(result.data.params);
            }
        } catch (err) {
            console.error('Failed to restore version:', err);
            setError('Failed to restore version');
        } finally {
            setIsLoading(false);
        }
    };

    // Delete a version
    const handleDelete = async (versionId, versionName) => {
        if (!window.confirm(`Delete "${versionName}"?`)) return;

        setIsLoading(true);
        setError(null);
        try {
            await deleteParameterVersion(versionId, false);
            await fetchVersions();
        } catch (err) {
            console.error('Failed to delete version:', err);
            setError('Failed to delete version');
        } finally {
            setIsLoading(false);
        }
    };

    // Format date
    const formatDate = (isoString) => {
        if (!isoString) return '';
        const date = new Date(isoString);
        return date.toLocaleDateString('ko-KR', {
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
        });
    };

    return (
        <div className={`bg-gray-900/50 border border-gray-700/50 rounded-lg overflow-hidden ${className}`}>
            {/* Header - Click to expand */}
            <button
                onClick={() => setIsExpanded(!isExpanded)}
                className="w-full flex items-center justify-between px-3 py-2 hover:bg-gray-800/50 transition-colors"
            >
                <div className="flex items-center gap-2">
                    <Save className="w-4 h-4 text-indigo-400" />
                    <span className="text-xs font-medium text-gray-300">Parameter Versions</span>
                    {versions.length > 0 && (
                        <span className="text-[10px] bg-indigo-500/20 text-indigo-300 px-1.5 py-0.5 rounded">
                            {versions.length}
                        </span>
                    )}
                </div>
                {isExpanded ? (
                    <ChevronUp className="w-4 h-4 text-gray-500" />
                ) : (
                    <ChevronDown className="w-4 h-4 text-gray-500" />
                )}
            </button>

            {/* Expanded Content */}
            {isExpanded && (
                <div className="px-3 pb-3 border-t border-gray-700/50">
                    {/* Error Message */}
                    {error && (
                        <div className="mt-2 text-xs text-red-400 bg-red-500/10 px-2 py-1 rounded">
                            {error}
                        </div>
                    )}

                    {/* Save New Version Form */}
                    {showSaveForm ? (
                        <div className="mt-3 space-y-2">
                            <input
                                type="text"
                                placeholder="Version name (e.g., Conservative v1)"
                                value={newVersionName}
                                onChange={(e) => setNewVersionName(e.target.value)}
                                className="w-full bg-gray-800 border border-gray-600 rounded px-2 py-1.5 text-xs text-white placeholder-gray-500 focus:outline-none focus:border-indigo-500"
                                autoFocus
                            />
                            <input
                                type="text"
                                placeholder="Description (optional)"
                                value={newVersionDesc}
                                onChange={(e) => setNewVersionDesc(e.target.value)}
                                className="w-full bg-gray-800 border border-gray-600 rounded px-2 py-1.5 text-xs text-white placeholder-gray-500 focus:outline-none focus:border-indigo-500"
                            />
                            <div className="flex gap-2">
                                <button
                                    onClick={handleSave}
                                    disabled={isLoading}
                                    className="flex-1 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-xs py-1.5 rounded transition-colors"
                                >
                                    {isLoading ? 'Saving...' : 'Save'}
                                </button>
                                <button
                                    onClick={() => {
                                        setShowSaveForm(false);
                                        setNewVersionName('');
                                        setNewVersionDesc('');
                                    }}
                                    className="px-3 bg-gray-700 hover:bg-gray-600 text-gray-300 text-xs py-1.5 rounded transition-colors"
                                >
                                    Cancel
                                </button>
                            </div>
                        </div>
                    ) : (
                        <button
                            onClick={() => setShowSaveForm(true)}
                            className="mt-3 w-full flex items-center justify-center gap-1.5 bg-indigo-600/20 hover:bg-indigo-600/30 border border-indigo-500/30 text-indigo-300 text-xs py-2 rounded transition-colors"
                        >
                            <Save className="w-3.5 h-3.5" />
                            Save Current as Version
                        </button>
                    )}

                    {/* Version List */}
                    {isLoading && versions.length === 0 ? (
                        <div className="mt-3 text-center text-xs text-gray-500 py-4">
                            Loading...
                        </div>
                    ) : versions.length === 0 ? (
                        <div className="mt-3 text-center text-xs text-gray-500 py-4">
                            No saved versions yet
                        </div>
                    ) : (
                        <div className="mt-3 space-y-2 max-h-48 overflow-y-auto">
                            {versions.map((v) => (
                                <div
                                    key={v.id}
                                    className="bg-gray-800/50 border border-gray-700/50 rounded p-2 hover:border-gray-600 transition-colors"
                                >
                                    <div className="flex items-start justify-between gap-2">
                                        <div className="flex-1 min-w-0">
                                            <div className="flex items-center gap-1.5">
                                                {v.is_default && (
                                                    <Star className="w-3 h-3 text-yellow-400 fill-yellow-400" />
                                                )}
                                                <span className="text-xs font-medium text-white truncate">
                                                    {v.version_name}
                                                </span>
                                            </div>
                                            {v.description && (
                                                <p className="text-[10px] text-gray-500 truncate mt-0.5">
                                                    {v.description}
                                                </p>
                                            )}
                                            <div className="flex items-center gap-2 mt-1 text-[10px] text-gray-500">
                                                <span className="flex items-center gap-0.5">
                                                    <Clock className="w-3 h-3" />
                                                    {formatDate(v.created_at)}
                                                </span>
                                                {v.config_hash && (
                                                    <span className="flex items-center gap-0.5 font-mono">
                                                        <Hash className="w-3 h-3" />
                                                        {v.config_hash}
                                                    </span>
                                                )}
                                            </div>
                                            {/* Performance Stats */}
                                            {v.performance_stats?.cycles > 0 && (
                                                <div className="flex items-center gap-2 mt-1 text-[10px]">
                                                    <span className="text-gray-400">
                                                        {v.performance_stats.cycles} cycles
                                                    </span>
                                                    <span className={v.performance_stats.win_rate >= 50 ? 'text-green-400' : 'text-red-400'}>
                                                        {v.performance_stats.win_rate}% win
                                                    </span>
                                                    <span className={v.performance_stats.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}>
                                                        {v.performance_stats.total_pnl >= 0 ? '+' : ''}{v.performance_stats.total_pnl?.toLocaleString()}
                                                    </span>
                                                </div>
                                            )}
                                        </div>
                                        <div className="flex items-center gap-1">
                                            <button
                                                onClick={() => handleRestore(v.id, v.version_name)}
                                                disabled={isLoading}
                                                className="p-1 hover:bg-indigo-500/20 rounded text-indigo-400 hover:text-indigo-300 transition-colors"
                                                title="Restore this version"
                                            >
                                                <RotateCcw className="w-3.5 h-3.5" />
                                            </button>
                                            <button
                                                onClick={() => handleDelete(v.id, v.version_name)}
                                                disabled={isLoading}
                                                className="p-1 hover:bg-red-500/20 rounded text-gray-500 hover:text-red-400 transition-colors"
                                                title="Delete this version"
                                            >
                                                <Trash2 className="w-3.5 h-3.5" />
                                            </button>
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            )}
        </div>
    );
};

export default ParameterVersionManager;
