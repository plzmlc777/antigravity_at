import React, { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getStatus, getPrice, getBalanceForAccount } from '../api/client';

const InfoCard = ({ title, value, subtext, type = 'neutral' }) => {
    const colors = {
        neutral: 'bg-white/5 border-white/10',
        success: 'bg-green-500/10 border-green-500/20 text-green-400',
        danger: 'bg-red-500/10 border-red-500/20 text-red-400',
        warning: 'bg-yellow-500/10 border-yellow-500/20 text-yellow-400',
    };

    return (
        <div className={`border rounded-lg px-4 py-3 ${colors[type]} flex flex-col justify-center`}>
            <h3 className="text-[10px] uppercase tracking-wider text-gray-400 leading-none">{title}</h3>
            <div className="text-sm font-mono font-bold leading-none mt-1.5">{value}</div>
            {subtext && <div className="text-[10px] text-gray-500 mt-1">{subtext}</div>}
        </div>
    );
};

const TradingInfoPanel = ({ currentSymbol, setSavedSymbols, accountId }) => {

    // Status Query
    const { data: status } = useQuery({
        queryKey: ['status'],
        queryFn: getStatus,
        refetchInterval: 30000
    });

    // Price Query
    const { data: price } = useQuery({
        queryKey: ['price', currentSymbol],
        queryFn: () => getPrice(currentSymbol),
        refetchInterval: 5000,
        enabled: !!currentSymbol
    });

    // Balance Query - per-account
    const { data: balance } = useQuery({
        queryKey: ['balance', 'account', accountId],
        queryFn: () => getBalanceForAccount(accountId),
        refetchInterval: 10000,
        enabled: !!accountId
    });

    // Auto-update name in saved list once when fetched from API.
    // Dependencies are narrowed to symbol+name (not full price object) so polling
    // re-fetches with identical values don't re-fire the effect. The setter also
    // returns prev unchanged when no name fill-in is needed, which lets the
    // WatchlistContext skip the debounced PUT /watchlist write.
    useEffect(() => {
        if (!price?.symbol || !price?.name || !setSavedSymbols) return;
        setSavedSymbols(prev => {
            const target = prev.find(item => item.code === price.symbol);
            if (!target || target.name) return prev;
            return prev.map(item =>
                item.code === price.symbol && !item.name
                    ? { ...item, name: price.name }
                    : item
            );
        });
    }, [price?.symbol, price?.name, setSavedSymbols]);

    return (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <InfoCard
                title="System Status"
                value={status?.status === 'online' ? 'ONLINE' : 'OFFLINE'}
                subtext={`Exchange: ${status?.exchange || '-'}`}
                type={status?.status === 'online' ? 'success' : 'danger'}
            />
            <InfoCard
                title={`Price (${price?.name || currentSymbol || '-'})`}
                value={price?.price ? `${price.price.toLocaleString()} KRW` : '-'}
                subtext={price?.name ? `${currentSymbol} | Real-time` : 'Real-time Price'}
                type="neutral"
            />
            <InfoCard
                title="Cash Balance"
                value={balance?.cash?.KRW ? `${balance.cash.KRW.toLocaleString()} KRW` : accountId ? '0 KRW' : 'No Account'}
                subtext="Available for Trade"
                type="warning"
            />
        </div>
    );
};

export default TradingInfoPanel;
