import React, { useState, useEffect, useCallback, useImperativeHandle, forwardRef } from 'react';
import { Plus, Activity, Building2, RefreshCw, AlertCircle, StopCircle, PauseCircle, PlayCircle, Clock, FileText, Zap, Check, Trash2, AlertTriangle, X, EyeOff } from 'lucide-react';
import { getAllSessions } from '../api/client';
import { useLiveTrading } from '../context/LiveTradingContext';
import { STATUS_CONFIG, DEFAULTS } from '../constants/live';

/**
 * SessionSwitcher - Phase 5: Multi-Account Session Navigation
 *
 * Shows individual sessions sorted by recent activity with status indicators.
 * Uses LiveTradingContext for centralized accounts data.
 */

// Re-export for backward compatibility
export { STATUS_CONFIG } from '../constants/live';

// Delete Confirmation Modal - exported for use in LiveStrategyPanel
// Delete Confirmation Modal - supports both single session and session groups
export const DeleteConfirmModal = ({ isOpen, onClose, onConfirm, session, sessions, getSymbolName, isDeleting }) => {
    const [confirmText, setConfirmText] = useState('');

    // Reset confirmText when modal opens
    useEffect(() => {
        if (isOpen) setConfirmText('');
    }, [isOpen]);

    // Support both single session (legacy) and sessions array (group)
    const sessionList = sessions || (session ? [session] : []);
    if (!isOpen || sessionList.length === 0) return null;

    const firstSession = sessionList[0];
    const sessionCount = sessionList.length;
    const isGroup = sessionCount > 1;

    const canConfirm = confirmText === '삭제';
    const symbolName = firstSession.symbol_name || (getSymbolName ? getSymbolName(firstSession.symbol) : firstSession.symbol);

    // Get unique symbols for group display
    const uniqueSymbols = [...new Set(sessionList.map(s => s.symbol))];
    const symbolsDisplay = uniqueSymbols.length === 1
        ? `${symbolName} (${firstSession.symbol})`
        : `${uniqueSymbols.length}개 종목`;

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
            <div className="absolute inset-0 bg-black/80 backdrop-blur-sm" onClick={onClose} />
            <div className="relative bg-[#1a1a2e] border-2 border-red-500/50 rounded-2xl w-full max-w-md mx-4 shadow-2xl">
                {/* Header */}
                <div className="flex items-center gap-3 px-6 py-4 border-b border-red-500/30 bg-red-500/10">
                    <AlertTriangle size={24} className="text-red-500" />
                    <h2 className="text-lg font-bold text-red-400">
                        {isGroup ? '세션 그룹 삭제 경고' : '세션 삭제 경고'}
                    </h2>
                    <button onClick={onClose} className="ml-auto p-1 hover:bg-white/10 rounded">
                        <X size={18} className="text-gray-400" />
                    </button>
                </div>

                {/* Body */}
                <div className="p-6 space-y-4">
                    <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4">
                        <p className="text-red-300 text-sm font-medium mb-2">
                            이 작업은 되돌릴 수 없습니다!
                        </p>
                        <ul className="text-red-200/80 text-xs space-y-1 list-disc list-inside">
                            {isGroup && <li className="font-semibold">{sessionCount}개의 세션이 모두 삭제됩니다</li>}
                            <li>세션 기록이 영구적으로 삭제됩니다</li>
                            <li>관련된 모든 거래 내역이 삭제됩니다</li>
                            <li>통계 데이터가 손실됩니다</li>
                        </ul>
                    </div>

                    <div className="bg-black/30 rounded-xl p-4 space-y-2">
                        <div className="text-sm text-gray-300">
                            <span className="text-gray-500">전략:</span> {firstSession.strategy_name}
                        </div>
                        {isGroup && (
                            <div className="text-sm text-gray-300">
                                <span className="text-gray-500">세션 수:</span>{' '}
                                <span className="text-red-400 font-medium">{sessionCount}개</span>
                            </div>
                        )}
                        <div className="text-sm text-gray-300">
                            <span className="text-gray-500">종목:</span> {symbolsDisplay}
                        </div>
                        <div className="text-sm text-gray-300">
                            <span className="text-gray-500">시작일:</span> {firstSession.started_at ? new Date(firstSession.started_at).toLocaleDateString('ko-KR') : '-'}
                        </div>
                        <div className="text-sm text-gray-300">
                            <span className="text-gray-500">상태:</span> <span className={STATUS_CONFIG[firstSession.status]?.color}>{STATUS_CONFIG[firstSession.status]?.label}</span>
                        </div>
                    </div>

                    <div>
                        <label className="block text-sm text-gray-400 mb-2">
                            확인을 위해 <span className="text-red-400 font-bold">"삭제"</span>를 입력하세요
                        </label>
                        <input
                            type="text"
                            value={confirmText}
                            onChange={(e) => setConfirmText(e.target.value)}
                            placeholder="삭제"
                            className="w-full bg-black/40 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-600 focus:border-red-500/50 outline-none"
                            autoFocus
                        />
                    </div>
                </div>

                {/* Footer */}
                <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-white/10">
                    <button
                        onClick={onClose}
                        className="px-4 py-2 text-gray-400 hover:text-white transition-colors"
                        disabled={isDeleting}
                    >
                        취소
                    </button>
                    <button
                        onClick={onConfirm}
                        disabled={!canConfirm || isDeleting}
                        className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-all ${
                            canConfirm && !isDeleting
                                ? 'bg-red-600 hover:bg-red-500 text-white'
                                : 'bg-gray-700 text-gray-500 cursor-not-allowed'
                        }`}
                    >
                        {isDeleting ? (
                            <>
                                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                                삭제 중...
                            </>
                        ) : (
                            <>
                                <Trash2 size={16} />
                                {isGroup ? `${sessionCount}개 영구 삭제` : '영구 삭제'}
                            </>
                        )}
                    </button>
                </div>
            </div>
        </div>
    );
};

const SessionSwitcher = forwardRef(({
    onSelectSessionGroup,
    onNewSession,
    activeSessionGroup,
    savedSymbols = []
}, ref) => {
    const [sessions, setSessions] = useState([]);
    const [isLoading, setIsLoading] = useState(true);
    const [showAll, setShowAll] = useState(() => {
        const saved = localStorage.getItem('sessionSwitcher_showAll');
        return saved !== null ? JSON.parse(saved) : false;
    });

    // Use centralized accounts from LiveTradingContext
    const { accounts } = useLiveTrading();

    // Fetch sessions only (accounts come from context)
    const fetchSessions = useCallback(async () => {
        try {
            const sessionsData = await getAllSessions({
                allAccounts: true,
                includeStopped: showAll,
                includeArchived: showAll,
                limit: DEFAULTS.SESSION_LIMIT
            });
            setSessions(Array.isArray(sessionsData) ? sessionsData : []);
        } catch (err) {
            console.error('SessionSwitcher: Failed to fetch sessions:', err);
        } finally {
            setIsLoading(false);
        }
    }, [showAll]);

    // Initial load
    useEffect(() => {
        fetchSessions();
    }, [fetchSessions]);

    // Auto-refresh at defined interval
    useEffect(() => {
        const interval = setInterval(fetchSessions, DEFAULTS.POLL_INTERVAL_MS);
        return () => clearInterval(interval);
    }, [fetchSessions]);

    // Auto-select first group if none selected (moved after sessionGroups is computed)

    // Expose refresh method via ref for parent to call after actions
    useImperativeHandle(ref, () => ({
        refresh: fetchSessions,
        getSymbolName
    }), [fetchSessions]);

    // Get account info by ID
    const getAccountInfo = (accountId) => {
        return accounts.find(a => a.id === accountId);
    };

    // Get symbol name from code
    const getSymbolName = (code) => {
        const match = savedSymbols.find(s => s.code === code);
        return match?.name || code;
    };

    // Format relative time
    const formatRelativeTime = (dateString) => {
        if (!dateString) return '';
        const date = new Date(dateString);
        const now = new Date();
        const diffMs = now - date;
        const diffMins = Math.floor(diffMs / 60000);
        const diffHours = Math.floor(diffMins / 60);
        const diffDays = Math.floor(diffHours / 24);

        if (diffMins < 1) return '방금';
        if (diffMins < 60) return `${diffMins}분 전`;
        if (diffHours < 24) return `${diffHours}시간 전`;
        if (diffDays < 7) return `${diffDays}일 전`;
        return date.toLocaleDateString('ko-KR', { month: 'short', day: 'numeric' });
    };

    // Group sessions by group_id (or treat as individual if no group_id)
    const sessionGroups = React.useMemo(() => {
        const groups = new Map();

        for (const session of sessions) {
            // Use group_id if available, otherwise use session_id as unique key
            const groupKey = session.group_id || `solo_${session.session_id}`;

            if (!groups.has(groupKey)) {
                groups.set(groupKey, {
                    groupId: session.group_id,
                    groupKey,
                    sessions: [],
                    // Representative info (from first session)
                    profile_name: session.profile_name,  // 프로필 이름 (타이틀용)
                    strategy_name: session.strategy_name,
                    account_id: session.account_id,
                    is_paper: session.is_paper,
                    started_at: session.started_at,
                    stopped_at: session.stopped_at,
                    // Collect all configs for the group
                    configList: [],
                });
            }
            // Add strategy_config to configList (for LiveStrategyPanel)
            if (session.strategy_config) {
                groups.get(groupKey).configList.push({
                    ...session.strategy_config,
                    symbol: session.symbol,
                    symbol_name: session.symbol_name || session.symbol,
                    session_id: session.session_id,
                    _session_status: session.status,  // Track session status for dedup
                    ai_symbol_mode: session.ai_symbol_mode || 'static',
                    ai_search_conditions: session.ai_search_conditions || '',
                    ai_optimize_params: session.ai_optimize_params || null,
                    original_symbol: session.original_symbol || session.symbol,
                    original_symbol_name: session.original_symbol_name || session.symbol_name || session.symbol,
                });
            }

            groups.get(groupKey).sessions.push(session);
        }

        // Process each group: compute aggregate status and info
        const processedGroups = [];
        for (const [, group] of groups) {
            const sessionList = group.sessions;

            // Deduplicate configList: prefer RUNNING/PAUSED over STOPPED for same rank
            // AI symbol rotation creates STOPPED sessions with the same rank in the same group
            const activeConfigs = group.configList.filter(c => c._session_status === 'RUNNING' || c._session_status === 'PAUSED');
            if (activeConfigs.length > 0) {
                // Use only active session configs
                group.configList = activeConfigs;
            } else {
                // All stopped: keep only one config per rank (latest = first in list since sorted by started_at desc)
                const seenRanks = new Set();
                group.configList = group.configList.filter(c => {
                    const rank = c.rank ?? 0;
                    if (seenRanks.has(rank)) return false;
                    seenRanks.add(rank);
                    return true;
                });
            }

            // Sort configList by rank to ensure consistent display order
            group.configList.sort((a, b) => (a.rank ?? 0) - (b.rank ?? 0));

            // Sync sessions array with deduped configList (prevent capital/display issues)
            const validSessionIds = new Set(group.configList.map(c => c.session_id));
            group.sessions = group.sessions.filter(s => validSessionIds.has(s.session_id));

            // Aggregate status: RUNNING if any running, else PAUSED if any paused, etc.
            const hasRunning = sessionList.some(s => s.status === 'RUNNING');
            const hasPaused = sessionList.some(s => s.status === 'PAUSED');
            const hasError = sessionList.some(s => s.status === 'ERROR');

            let groupStatus = 'STOPPED';
            if (hasRunning) groupStatus = 'RUNNING';
            else if (hasPaused) groupStatus = 'PAUSED';
            else if (hasError) groupStatus = 'ERROR';

            // Aggregate PnL
            const totalPnl = sessionList.reduce((sum, s) => sum + (s.pnl || 0), 0);

            // Get unique symbols
            const symbols = [...new Set(sessionList.map(s => s.symbol))];

            // Latest activity
            const latestActivity = sessionList.reduce((latest, s) => {
                const t = new Date(s.stopped_at || s.started_at || 0).getTime();
                return t > latest ? t : latest;
            }, 0);

            // Check if group is archived (any session in group is archived)
            const isArchived = sessionList.some(s => s.is_archived);

            processedGroups.push({
                ...group,
                status: groupStatus,
                pnl: totalPnl,
                symbols,
                sessionCount: sessionList.length,
                latestActivity: new Date(latestActivity),
                is_archived: isArchived,
            });
        }

        // Sort: RUNNING first, then by latest activity
        return processedGroups.sort((a, b) => {
            if (a.status === 'RUNNING' && b.status !== 'RUNNING') return -1;
            if (b.status === 'RUNNING' && a.status !== 'RUNNING') return 1;
            return b.latestActivity - a.latestActivity;
        });
    }, [sessions]);

    // Auto-select first group if none selected
    useEffect(() => {
        if (!activeSessionGroup && sessionGroups.length > 0 && onSelectSessionGroup) {
            const firstGroup = sessionGroups[0];
            onSelectSessionGroup({
                accountId: firstGroup.account_id,
                strategyName: firstGroup.strategy_name,
                groupId: firstGroup.groupId,
                sessionId: firstGroup.sessions[0]?.session_id,
                sessions: firstGroup.sessions,
                configList: firstGroup.configList || []  // For ActiveStrategiesPanel
            });
        }
    }, [sessionGroups, activeSessionGroup, onSelectSessionGroup]);

    // Update parent with fresh session data when selected session's data changes
    useEffect(() => {
        if (!activeSessionGroup || !onSelectSessionGroup || sessionGroups.length === 0) return;

        // Find the currently selected group in the refreshed data
        const selectedGroup = sessionGroups.find(g => {
            if (activeSessionGroup.groupId && g.groupId === activeSessionGroup.groupId) return true;
            return g.sessions[0]?.session_id === activeSessionGroup.sessionId;
        });

        if (selectedGroup) {
            // Check if sessions data has changed (e.g., status, symbol changed)
            const currentSessionIds = activeSessionGroup.sessions?.map(s => s.session_id).sort().join(',');
            const newSessionIds = selectedGroup.sessions?.map(s => s.session_id).sort().join(',');
            const statusChanged = activeSessionGroup.sessions?.[0]?.status !== selectedGroup.sessions?.[0]?.status;
            const symbolsChanged = activeSessionGroup.sessions?.map(s => s.symbol).join(',') !== selectedGroup.sessions?.map(s => s.symbol).join(',');
            // Compare symbol, AI mode, and key strategy params (leverage, position_side, trigger levels)
            const configFingerprint = (cl) => JSON.stringify(cl?.map(c => ({
                s: c.symbol, ai: c.ai_symbol_mode,
                lev: c.leverage, ps: c.position_side,
                tl: c.trigger_level, stl: c.short_trigger_level,
            })));
            const configChanged = configFingerprint(activeSessionGroup.configList)
                !== configFingerprint(selectedGroup.configList);

            if (currentSessionIds !== newSessionIds || statusChanged || symbolsChanged || configChanged) {
                onSelectSessionGroup({
                    accountId: selectedGroup.account_id,
                    strategyName: selectedGroup.strategy_name,
                    groupId: selectedGroup.groupId,
                    sessionId: selectedGroup.sessions[0]?.session_id,
                    sessions: selectedGroup.sessions,
                    configList: selectedGroup.configList || []  // For ActiveStrategiesPanel
                });
            }
        } else {
            // Selected group no longer exists (deleted or all sessions removed)
            // Auto-select first available group, or clear selection
            if (sessionGroups.length > 0) {
                const firstGroup = sessionGroups[0];
                console.log('[SessionSwitcher] Selected group disappeared, auto-selecting:', firstGroup.groupKey);
                onSelectSessionGroup({
                    accountId: firstGroup.account_id,
                    strategyName: firstGroup.strategy_name,
                    groupId: firstGroup.groupId,
                    sessionId: firstGroup.sessions[0]?.session_id,
                    sessions: firstGroup.sessions,
                    configList: firstGroup.configList || []
                });
            } else {
                console.log('[SessionSwitcher] Selected group disappeared, no groups left - clearing selection');
                onSelectSessionGroup(null);
            }
        }
    }, [sessionGroups, activeSessionGroup]);

    // Check if a group is selected
    const isGroupSelected = (group) => {
        if (!activeSessionGroup) return false;
        // Match by groupId or first session's ID
        if (group.groupId && activeSessionGroup.groupId === group.groupId) return true;
        return activeSessionGroup.sessionId === group.sessions[0]?.session_id;
    };

    // Format PnL
    const formatPnl = (pnl) => {
        if (!pnl || pnl === 0) return '0';
        const absValue = Math.abs(pnl);
        const formatted = absValue >= 1000000
            ? `${(absValue / 1000000).toFixed(1)}M`
            : absValue >= 1000
                ? `${(absValue / 1000).toFixed(0)}K`
                : absValue.toFixed(0);
        return pnl >= 0 ? `+${formatted}` : `-${formatted}`;
    };

    if (isLoading) {
        return (
            <div className="flex items-center gap-2 px-4 py-2 bg-white/5 rounded-xl mb-4">
                <div className="w-4 h-4 border-2 border-indigo-500/30 border-t-indigo-500 rounded-full animate-spin" />
                <span className="text-xs text-gray-400">세션 로딩 중...</span>
            </div>
        );
    }

    // Filter groups - always include the currently selected group
    const visibleGroups = showAll
        ? sessionGroups
        : sessionGroups.filter(g => {
            // Always show RUNNING or PAUSED
            if (g.status === 'RUNNING' || g.status === 'PAUSED') return true;
            // Always show the currently selected group (even if STOPPED/ERROR)
            if (activeSessionGroup) {
                if (g.groupId && g.groupId === activeSessionGroup.groupId) return true;
                if (g.sessions[0]?.session_id === activeSessionGroup.sessionId) return true;
            }
            return false;
        });

    return (
        <>
            <div className="flex flex-col gap-3 mb-4">
                {/* Header Row */}
                <div className="flex items-center justify-between px-1">
                    <div className="flex items-center gap-2 text-sm text-gray-400">
                        <Activity size={14} />
                        <span>세션 그룹 ({visibleGroups.length})</span>
                    </div>
                    <div className="flex items-center gap-2">
                        <button
                            onClick={() => {
                                const next = !showAll;
                                setShowAll(next);
                                localStorage.setItem('sessionSwitcher_showAll', JSON.stringify(next));
                            }}
                            className={`text-xs px-2 py-1 rounded transition-all ${
                                showAll
                                    ? 'text-indigo-400 bg-indigo-500/10'
                                    : 'text-gray-500 hover:text-gray-400'
                            }`}
                        >
                            {showAll ? '전체 보기' : '활성만'}
                        </button>
                        <button
                            onClick={fetchSessions}
                            className="p-1.5 text-gray-400 hover:text-white hover:bg-white/10 rounded transition-colors"
                            title="새로고침"
                        >
                            <RefreshCw size={12} />
                        </button>
                    </div>
                </div>

                {/* Session Group Cards */}
                <div className="flex items-stretch gap-2 px-1 overflow-x-auto pb-1">
                    {visibleGroups.length > 0 ? (
                        visibleGroups.map((group) => {
                            const account = getAccountInfo(group.account_id);
                            const isSelected = isGroupSelected(group);
                            const statusConfig = STATUS_CONFIG[group.status] || STATUS_CONFIG.STOPPED;
                            const StatusIcon = statusConfig.icon;

                            return (
                                <div
                                    key={group.groupKey}
                                    className={`
                                        relative flex-shrink-0 flex flex-col gap-1 p-3 rounded-xl min-w-[150px] max-w-[180px]
                                        transition-all duration-200 text-left cursor-pointer
                                        ${group.is_archived ? 'opacity-50' : ''}
                                        ${isSelected
                                            ? 'bg-indigo-600/40 border-2 border-indigo-400 shadow-lg shadow-indigo-500/30 ring-2 ring-indigo-400/50'
                                            : `${statusConfig.bgColor} border ${statusConfig.borderColor} hover:border-white/40`}
                                    `}
                                    onClick={() => {
                                        console.log('[SessionSwitcher] Selected group configList:', group.configList);
                                        onSelectSessionGroup({
                                            accountId: group.account_id,
                                            strategyName: group.strategy_name,
                                            groupId: group.groupId,
                                            sessionId: group.sessions[0]?.session_id,
                                            sessions: group.sessions,
                                            configList: group.configList || []  // For ActiveStrategiesPanel
                                        });
                                    }}
                                >
                                    {/* Selection Indicator */}
                                    {isSelected && (
                                        <div className="absolute -top-1.5 -right-1.5 w-5 h-5 bg-indigo-500 rounded-full flex items-center justify-center shadow-lg z-10">
                                            <Check size={12} className="text-white" strokeWidth={3} />
                                        </div>
                                    )}

                                    {/* Archived Indicator */}
                                    {group.is_archived && (
                                        <div className="absolute -top-1.5 -left-1.5 w-5 h-5 bg-slate-600 rounded-full flex items-center justify-center shadow-lg z-10">
                                            <EyeOff size={10} className="text-slate-300" />
                                        </div>
                                    )}

                                    {/* Profile Name (Title) - Full display */}
                                    <div className="flex items-center gap-1.5 pr-5">
                                        <StatusIcon
                                            size={12}
                                            className={`flex-shrink-0 ${statusConfig.color} ${group.status === 'RUNNING' ? 'animate-pulse' : ''}`}
                                        />
                                        <span className="text-sm font-semibold text-white">
                                            {group.profile_name || group.strategy_name}
                                        </span>
                                    </div>

                                    {/* Strategy Name */}
                                    <div className="flex items-center gap-1 text-[10px] text-gray-300">
                                        <Zap size={9} className="text-indigo-400/70" />
                                        <span className="truncate">{group.strategy_name}</span>
                                    </div>

                                    {/* Account */}
                                    <div className="flex items-center gap-1 text-[10px] text-gray-500">
                                        <Building2 size={9} />
                                        <span className="truncate">{account?.account_name || 'Unknown'}</span>
                                    </div>

                                    {/* Time + Status/PnL */}
                                    <div className="flex items-center justify-between mt-1 pt-1 border-t border-white/5">
                                        <div className="flex items-center gap-1 text-[9px] text-gray-500">
                                            <Clock size={8} />
                                            <span>{formatRelativeTime(group.latestActivity)}</span>
                                        </div>
                                        <span className={`text-[9px] font-medium ${statusConfig.color}`}>
                                            {group.status === 'RUNNING' && group.pnl !== undefined
                                                ? formatPnl(group.pnl)
                                                : statusConfig.label}
                                        </span>
                                    </div>
                                </div>
                            );
                        })
                    ) : (
                        <div className="flex items-center gap-2 px-4 py-6 text-sm text-gray-500 bg-white/5 rounded-xl w-full justify-center">
                            <FileText size={16} />
                            <span>세션 기록이 없습니다</span>
                        </div>
                    )}

                    {/* New Session Button */}
                    <button
                        onClick={onNewSession}
                        className="flex-shrink-0 flex flex-col items-center justify-center gap-2 p-4 min-w-[100px] bg-green-600/10 hover:bg-green-600/20 border-2 border-dashed border-green-500/30 hover:border-green-500/50 rounded-xl transition-all"
                    >
                        <Plus size={18} className="text-green-400" />
                        <span className="text-xs text-green-400 font-medium">새 세션</span>
                    </button>
                </div>
            </div>
        </>
    );
});

export default SessionSwitcher;
