import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { getLiveStatus } from '../api/client';
import { useLiveTrading } from '../context/LiveTradingContext';

const StatusCard = () => {
    const { getAccountById } = useLiveTrading();

    const { data: liveData } = useQuery({
        queryKey: ['live-status-nav'],
        queryFn: () => getLiveStatus({ allAccounts: true }),
        refetchInterval: 15000,
        retry: 1
    });

    const runningSessions = (liveData || []).filter(s => s.is_running);
    const sessionCount = runningSessions.length;
    const isLive = sessionCount > 0;

    // Collect unique account names from running sessions
    const accountNames = [...new Set(
        runningSessions
            .map(s => {
                const acc = getAccountById(s.account_id);
                return acc?.account_name || acc?.exchange_name;
            })
            .filter(Boolean)
    )];

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
                {accountNames.length > 0 && (
                    <div className="flex items-center gap-1 bg-black/20 px-1.5 py-0.5 rounded-full">
                        <div className="w-1 h-1 rounded-full bg-green-400 animate-pulse"></div>
                        <span className="text-[9px] font-medium text-gray-300 max-w-[80px] truncate leading-none">
                            {accountNames.join(', ')}
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
