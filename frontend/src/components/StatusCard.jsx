import React from 'react';
import { useMarketData } from '../context/MarketDataContext';

const StatusCard = () => {
    // 1. Fetch system status from global context
    const { systemStatus } = useMarketData();
    const status = systemStatus || { exchange: 'Initializing...', status: 'offline', mode: 'UNKNOWN' };

    const colors = {
        neutral: 'bg-white/5 border-white/10',
        success: 'bg-green-500/10 border-green-500/20 text-green-400',
        danger: 'bg-red-500/10 border-red-500/20 text-red-400',
        warning: 'bg-yellow-500/10 border-yellow-500/20 text-yellow-400',
    };

    // 2. Derive UI values
    const title = status.exchange || "Exchange";
    const value = status.status?.toUpperCase() || "OFFLINE";
    const modeType = status.status === 'online' ? 'success' : 'danger';

    return (
        <div className={`border rounded-lg px-3 py-2 min-w-[120px] ${colors[modeType]} flex flex-col justify-center`}>
            <div className="flex items-center justify-between gap-2">
                <h3 className="text-[10px] uppercase tracking-wider text-gray-400 leading-none">{title}</h3>
                {(status?.account_name && status.account_name !== 'Unknown') && (
                    <div className="flex items-center gap-1 bg-black/20 px-1.5 py-0.5 rounded-full">
                        <div className="w-1 h-1 rounded-full bg-green-400 animate-pulse"></div>
                        <span className="text-[9px] font-medium text-gray-300 max-w-[60px] truncate leading-none">
                            {status.account_name}
                        </span>
                    </div>
                )}
            </div>

            <div className="text-sm font-mono font-bold leading-none mt-1">{value}</div>
        </div>
    );
};

export default StatusCard;
