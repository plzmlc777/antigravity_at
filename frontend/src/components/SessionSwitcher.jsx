import React, { useState, useEffect, useCallback, useImperativeHandle, forwardRef } from 'react';
import { Plus, Activity, Building2, RefreshCw, AlertCircle, StopCircle, PauseCircle, PlayCircle, Clock, FileText, Zap, Check, Trash2, AlertTriangle, X } from 'lucide-react';
import { getAllSessions, getAccounts } from '../api/client';

/**
 * SessionSwitcher - Phase 5: Multi-Account Session Navigation
 *
 * Shows individual sessions sorted by recent activity with status indicators.
 * Option B: Cards are for selection/display only. Actions (Resume/Delete) are in Live Operation Panel.
 * - RUNNING: Active session (green)
 * - PAUSED: Temporarily paused (yellow)
 * - STOPPED: Standby/Ready to restart (gray/blue)
 * - ERROR: Has errors (red)
 */

// Status configuration - exported for use in LiveStrategyPanel
export const STATUS_CONFIG = {
    RUNNING: {
        color: 'text-green-400',
        bgColor: 'bg-green-500/20',
        borderColor: 'border-green-500/50',
        icon: PlayCircle,
        label: '실행 중',
        priority: 1,
        canDelete: false,
        canResume: false
    },
    PAUSED: {
        color: 'text-yellow-400',
        bgColor: 'bg-yellow-500/20',
        borderColor: 'border-yellow-500/50',
        icon: PauseCircle,
        label: '일시정지',
        priority: 2,
        canDelete: false,
        canResume: false
    },
    STOPPED: {
        color: 'text-blue-400',
        bgColor: 'bg-blue-500/10',
        borderColor: 'border-blue-500/30',
        icon: StopCircle,
        label: '대기 중',
        priority: 3,
        canDelete: true,
        canResume: true
    },
    ERROR: {
        color: 'text-red-400',
        bgColor: 'bg-red-500/20',
        borderColor: 'border-red-500/50',
        icon: AlertCircle,
        label: '오류',
        priority: 4,
        canDelete: true,
        canResume: true
    }
};

// Delete Confirmation Modal - exported for use in LiveStrategyPanel
export const DeleteConfirmModal = ({ isOpen, onClose, onConfirm, session, getSymbolName, isDeleting }) => {
    const [confirmText, setConfirmText] = useState('');

    // Reset confirmText when modal opens
    useEffect(() => {
        if (isOpen) setConfirmText('');
    }, [isOpen]);

    if (!isOpen || !session) return null;

    const canConfirm = confirmText === '삭제';
    const symbolName = getSymbolName ? getSymbolName(session.symbol) : session.symbol;

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
            <div className="absolute inset-0 bg-black/80 backdrop-blur-sm" onClick={onClose} />
            <div className="relative bg-[#1a1a2e] border-2 border-red-500/50 rounded-2xl w-full max-w-md mx-4 shadow-2xl">
                {/* Header */}
                <div className="flex items-center gap-3 px-6 py-4 border-b border-red-500/30 bg-red-500/10">
                    <AlertTriangle size={24} className="text-red-500" />
                    <h2 className="text-lg font-bold text-red-400">세션 삭제 경고</h2>
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
                            <li>세션 기록이 영구적으로 삭제됩니다</li>
                            <li>관련된 모든 거래 내역이 삭제됩니다</li>
                            <li>통계 데이터가 손실됩니다</li>
                        </ul>
                    </div>

                    <div className="bg-black/30 rounded-xl p-4 space-y-2">
                        <div className="text-sm text-gray-300">
                            <span className="text-gray-500">전략:</span> {session.strategy_name}
                        </div>
                        <div className="text-sm text-gray-300">
                            <span className="text-gray-500">종목:</span> {symbolName} ({session.symbol})
                        </div>
                        <div className="text-sm text-gray-300">
                            <span className="text-gray-500">시작일:</span> {session.started_at ? new Date(session.started_at).toLocaleDateString('ko-KR') : '-'}
                        </div>
                        <div className="text-sm text-gray-300">
                            <span className="text-gray-500">상태:</span> <span className={STATUS_CONFIG[session.status]?.color}>{STATUS_CONFIG[session.status]?.label}</span>
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
                                영구 삭제
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
    const [accounts, setAccounts] = useState([]);
    const [isLoading, setIsLoading] = useState(true);
    const [showAll, setShowAll] = useState(true);

    // Fetch all sessions across all accounts
    const fetchSessions = useCallback(async () => {
        try {
            const [sessionsData, accountsData] = await Promise.all([
                getAllSessions({ allAccounts: true, includeStopped: showAll, limit: 100 }),
                getAccounts()
            ]);
            setSessions(Array.isArray(sessionsData) ? sessionsData : []);
            setAccounts(accountsData || []);
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

    // Auto-refresh every 5 seconds
    useEffect(() => {
        const interval = setInterval(fetchSessions, 5000);
        return () => clearInterval(interval);
    }, [fetchSessions]);

    // Auto-select first session if none selected
    useEffect(() => {
        if (!activeSessionGroup && sessions.length > 0 && onSelectSessionGroup) {
            // Sort by activity and select the first
            const sorted = [...sessions].sort((a, b) => {
                // RUNNING first
                if (a.status === 'RUNNING' && b.status !== 'RUNNING') return -1;
                if (b.status === 'RUNNING' && a.status !== 'RUNNING') return 1;
                // Then by time
                const aTime = new Date(a.stopped_at || a.started_at || 0).getTime();
                const bTime = new Date(b.stopped_at || b.started_at || 0).getTime();
                return bTime - aTime;
            });

            if (sorted.length > 0) {
                const first = sorted[0];
                onSelectSessionGroup({
                    accountId: first.account_id,
                    strategyName: first.strategy_name,
                    sessionId: first.session_id,
                    sessions: [first]
                });
            }
        }
    }, [sessions, activeSessionGroup, onSelectSessionGroup]);

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

    // Sort sessions
    const sortedSessions = React.useMemo(() => {
        return [...sessions].sort((a, b) => {
            // RUNNING first
            if (a.status === 'RUNNING' && b.status !== 'RUNNING') return -1;
            if (b.status === 'RUNNING' && a.status !== 'RUNNING') return 1;
            // Then by last activity
            const aTime = new Date(a.stopped_at || a.started_at || 0).getTime();
            const bTime = new Date(b.stopped_at || b.started_at || 0).getTime();
            return bTime - aTime;
        });
    }, [sessions]);

    // Check if a session is selected
    const isSessionSelected = (session) => {
        if (!activeSessionGroup) return false;
        return activeSessionGroup.sessionId === session.session_id;
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

    // Filter sessions
    const visibleSessions = showAll
        ? sortedSessions
        : sortedSessions.filter(s => s.status === 'RUNNING' || s.status === 'PAUSED');

    return (
        <>
            <div className="flex flex-col gap-3 mb-4">
                {/* Header Row */}
                <div className="flex items-center justify-between px-1">
                    <div className="flex items-center gap-2 text-sm text-gray-400">
                        <Activity size={14} />
                        <span>세션 ({visibleSessions.length})</span>
                    </div>
                    <div className="flex items-center gap-2">
                        <button
                            onClick={() => setShowAll(!showAll)}
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

                {/* Session Cards */}
                <div className="flex items-stretch gap-2 px-1 overflow-x-auto pb-1">
                    {visibleSessions.length > 0 ? (
                        visibleSessions.map((session) => {
                            const account = getAccountInfo(session.account_id);
                            const isSelected = isSessionSelected(session);
                            const statusConfig = STATUS_CONFIG[session.status] || STATUS_CONFIG.STOPPED;
                            const StatusIcon = statusConfig.icon;
                            const symbolName = getSymbolName(session.symbol);
                            const lastActivity = session.stopped_at || session.started_at;

                            return (
                                <div
                                    key={session.session_id}
                                    className={`
                                        relative flex-shrink-0 flex flex-col gap-1 p-3 rounded-xl min-w-[150px] max-w-[180px]
                                        transition-all duration-200 text-left cursor-pointer
                                        ${isSelected
                                            ? 'bg-indigo-600/40 border-2 border-indigo-400 shadow-lg shadow-indigo-500/30 ring-2 ring-indigo-400/50'
                                            : `${statusConfig.bgColor} border ${statusConfig.borderColor} hover:border-white/40`}
                                    `}
                                    onClick={() => onSelectSessionGroup({
                                        accountId: session.account_id,
                                        strategyName: session.strategy_name,
                                        sessionId: session.session_id,
                                        sessions: [session]
                                    })}
                                >
                                    {/* Selection Indicator */}
                                    {isSelected && (
                                        <div className="absolute -top-1.5 -right-1.5 w-5 h-5 bg-indigo-500 rounded-full flex items-center justify-center shadow-lg z-10">
                                            <Check size={12} className="text-white" strokeWidth={3} />
                                        </div>
                                    )}

                                    {/* Strategy Name (Title) */}
                                    <div className="flex items-center gap-1.5 pr-5">
                                        <StatusIcon
                                            size={12}
                                            className={`flex-shrink-0 ${statusConfig.color} ${session.status === 'RUNNING' ? 'animate-pulse' : ''}`}
                                        />
                                        <span className="text-sm font-semibold text-white truncate">
                                            {session.strategy_name}
                                        </span>
                                        <span className={`flex-shrink-0 text-[8px] px-1 py-0.5 rounded font-medium ${
                                            session.is_paper
                                                ? 'bg-yellow-500/20 text-yellow-400'
                                                : 'bg-red-500/20 text-red-400'
                                        }`}>
                                            {session.is_paper ? 'P' : 'R'}
                                        </span>
                                    </div>

                                    {/* Symbol Name */}
                                    <div className="flex items-center gap-1 text-[10px] text-gray-300">
                                        <Zap size={9} className="text-yellow-500/70" />
                                        <span className="truncate">{symbolName}</span>
                                    </div>

                                    {/* Account */}
                                    <div className="flex items-center gap-1 text-[10px] text-gray-500">
                                        <Building2 size={9} />
                                        <span className="truncate">{account?.account_name || 'Unknown'}</span>
                                    </div>

                                    {/* Time + Status */}
                                    <div className="flex items-center justify-between mt-1 pt-1 border-t border-white/5">
                                        <div className="flex items-center gap-1 text-[9px] text-gray-500">
                                            <Clock size={8} />
                                            <span>{formatRelativeTime(lastActivity)}</span>
                                        </div>
                                        <span className={`text-[9px] font-medium ${statusConfig.color}`}>
                                            {session.status === 'RUNNING' && session.pnl !== undefined
                                                ? formatPnl(session.pnl)
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
