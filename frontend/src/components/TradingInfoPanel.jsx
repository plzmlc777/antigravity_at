import React, { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getStatus, getPrice, getBalanceForAccount } from '../api/client';

const MAX_FAILURE_STREAK = 3;
const PRICE_POLL_MS = 15000;
const BALANCE_POLL_MS = 15000;
const STATUS_POLL_MS = 30000;

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

    // Failure streak counters — pause polling after N consecutive failures
    const [priceFailureStreak, setPriceFailureStreak] = useState(0);
    const [balanceFailureStreak, setBalanceFailureStreak] = useState(0);

    // Reset streaks on symbol/account change so user gets a fresh attempt
    useEffect(() => { setPriceFailureStreak(0); }, [currentSymbol]);
    useEffect(() => { setBalanceFailureStreak(0); }, [accountId]);

    // Status Query
    const { data: status } = useQuery({
        queryKey: ['status'],
        queryFn: getStatus,
        refetchInterval: STATUS_POLL_MS,
        retry: 1,
        staleTime: 10000,
    });

    // Price Query
    const priceQuery = useQuery({
        queryKey: ['price', currentSymbol],
        queryFn: () => getPrice(currentSymbol),
        enabled: !!currentSymbol && !!accountId,
        staleTime: 5000,
        retry: 1,
        refetchInterval: priceFailureStreak >= MAX_FAILURE_STREAK ? false : PRICE_POLL_MS,
    });
    const price = priceQuery.data;

    useEffect(() => {
        if (priceQuery.isSuccess) setPriceFailureStreak(0);
    }, [priceQuery.dataUpdatedAt, priceQuery.isSuccess]);

    useEffect(() => {
        if (priceQuery.isError) setPriceFailureStreak(c => c + 1);
    }, [priceQuery.errorUpdatedAt, priceQuery.isError]);

    // Balance Query - per-account
    const balanceQuery = useQuery({
        queryKey: ['balance', 'account', accountId],
        queryFn: () => getBalanceForAccount(accountId),
        enabled: !!accountId,
        staleTime: 5000,
        retry: 1,
        refetchInterval: balanceFailureStreak >= MAX_FAILURE_STREAK ? false : BALANCE_POLL_MS,
    });
    const balance = balanceQuery.data;

    useEffect(() => {
        if (balanceQuery.isSuccess) setBalanceFailureStreak(0);
    }, [balanceQuery.dataUpdatedAt, balanceQuery.isSuccess]);

    useEffect(() => {
        if (balanceQuery.isError) setBalanceFailureStreak(c => c + 1);
    }, [balanceQuery.errorUpdatedAt, balanceQuery.isError]);

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
