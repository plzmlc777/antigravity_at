import React, { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import StatusCard from './StatusCard';
import { getStatus, getPrice, getBalance } from '../api/client';

const TradingInfoPanel = ({ currentSymbol, setSavedSymbols }) => {

    // Status Query
    const { data: status } = useQuery({
        queryKey: ['status'],
        queryFn: getStatus,
        refetchInterval: 30000 // 30s
    });

    // Price Query
    const { data: price } = useQuery({
        queryKey: ['price', currentSymbol],
        queryFn: () => getPrice(currentSymbol),
        refetchInterval: 5000 // 5s
    });

    // Balance Query
    const { data: balance } = useQuery({
        queryKey: ['balance'],
        queryFn: getBalance,
        refetchInterval: 10000 // 10s
    });

    // Auto-update name in saved list if fetched from API and setSavedSymbols is provided
    useEffect(() => {
        if (price?.symbol && price?.name && setSavedSymbols) {
            setSavedSymbols(prev => prev.map(item => {
                if (item.code === price.symbol && !item.name) {
                    return { ...item, name: price.name };
                }
                return item;
            }));
        }
    }, [price, setSavedSymbols]);

    return (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <StatusCard
                title="System Status"
                value={status?.status === 'online' ? 'ONLINE' : 'OFFLINE'}
                subtext={`Exchange: ${status?.exchange || '-'}`}
                type={status?.status === 'online' ? 'success' : 'danger'}
            />
            <StatusCard
                title={`Price (${price?.name || currentSymbol})`}
                value={price?.price ? `${price.price.toLocaleString()} KRW` : '-'}
                subtext={price?.name ? `${currentSymbol} | Real-time` : "Real-time Price"}
                type="neutral"
            />
            <StatusCard
                title="Cash Balance"
                value={balance?.cash?.KRW ? `${balance.cash.KRW.toLocaleString()} KRW` : '0 KRW'}
                subtext="Available for Trade"
                type="warning"
            />
        </div>
    );
};

export default TradingInfoPanel;
