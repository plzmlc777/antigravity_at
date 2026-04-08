import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchMonitorSessions } from '../api/agentsMeta';

// Navbar status pill — must work without auth (Mission Control is public).
// Uses the no-auth /live/monitor/sessions endpoint instead of the authed client,
// so unauthenticated visitors don't get bounced to /login by the 401 interceptor.
const StatusCard = () => {
    const { data: monitorData } = useQuery({
        queryKey: ['live-status-nav-monitor'],
        queryFn: () => fetchMonitorSessions(),
        refetchInterval: 15000,
        retry: 0,
    });

    const sessions = monitorData?.sessions || [];
    const runningSessions = sessions.filter(s => s.status === 'RUNNING');
    const sessionCount = runningSessions.length;
    const isLive = sessionCount > 0;

    // Show real/paper split as the badge text (no per-account name lookup —
    // monitor endpoint omits account names by design).
    const realCount = runningSessions.filter(s => !s.is_paper).length;
    const paperCount = sessionCount - realCount;

    const colors = {
        success: 'bg-green-500/10 border-green-500/20 text-green-400',
        danger: 'bg-red-500/10 border-red-500/20 text-red-400',
    };

    return (
        <div className={`border rounded-lg px-3 py-2 min-w-[120px] ${colors[isLive ? 'success' : 'danger']} flex flex-col justify-center`}>
            <div className="flex items-center justify-between gap-2">
                <h3 className="text-[10px] uppercase tracking-wider text-gray-400 leading-none">
                    Live Trading
                </h3>
                {sessionCount > 0 && (
                    <div className="flex items-center gap-1 bg-black/20 px-1.5 py-0.5 rounded-full">
                        <div className="w-1 h-1 rounded-full bg-green-400 animate-pulse"></div>
                        <span className="text-[9px] font-medium text-gray-300 leading-none">
                            R{realCount}/P{paperCount}
                        </span>
                    </div>
                )}
            </div>
            <div className="text-sm font-mono font-bold leading-none mt-1">
                {isLive ? `${sessionCount} SESSION${sessionCount > 1 ? 'S' : ''}` : 'IDLE'}
            </div>
        </div>
    );
};

export default StatusCard;
