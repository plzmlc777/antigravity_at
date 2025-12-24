import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { getBalance, getStatus, getPrice } from '../api/client';
import { useAuth } from './AuthContext';

const MarketDataContext = createContext({
    balanceData: { cash: { KRW: 0 }, holdings: {} },
    systemStatus: { exchange: 'Unknown', status: 'offline', mode: 'UNKNOWN' },
    holdingsDetails: [],
    totalAssets: 0,
    totalInvested: 0,
    loading: false,
    error: null,
    refresh: () => { }
});

export const MarketDataProvider = ({ children }) => {
    const { token } = useAuth();

    // Global State with safe initial values
    const [balanceData, setBalanceData] = useState({ cash: { KRW: 0 }, holdings: {} });
    const [systemStatus, setSystemStatus] = useState({ exchange: 'Unknown', status: 'offline', mode: 'UNKNOWN' });
    const [holdingsDetails, setHoldingsDetails] = useState([]);
    const [totalAssets, setTotalAssets] = useState(0);
    const [totalInvested, setTotalInvested] = useState(0);

    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    const fetchData = useCallback(async () => {
        if (!token) return;

        setLoading(true);
        try {
            // Parallel Fetch with individual error handling
            const [balance, status] = await Promise.all([
                getBalance().catch(err => {
                    console.error("Balance fetch error:", err);
                    return { cash: { KRW: 0 }, holdings: {} };
                }),
                getStatus().catch(err => {
                    console.error("Status fetch error:", err);
                    return { exchange: 'Error', status: 'offline', mode: 'UNKNOWN' };
                })
            ]);

            setBalanceData(balance || { cash: { KRW: 0 }, holdings: {} });
            setSystemStatus(status || { exchange: 'Error', status: 'offline', mode: 'UNKNOWN' });

            // Fetch Prices
            const holdings = balance?.holdings || {};
            const cash = balance?.cash?.KRW || 0;
            const symbols = Object.keys(holdings);

            const details = [];
            let investedSum = 0;

            if (symbols.length > 0) {
                const results = await Promise.all(
                    symbols.map(symbol => getPrice(symbol).catch(() => ({ symbol, price: 0, name: symbol })))
                );

                results.forEach((priceInfo, index) => {
                    const symbol = symbols[index];
                    const holdingData = holdings[symbol];
                    if (!holdingData) return;

                    const qty = typeof holdingData === 'object' ? (holdingData.quantity || 0) : holdingData;
                    const avgPrice = typeof holdingData === 'object' ? (holdingData.avg_price || 0) : 0;
                    const profitRate = typeof holdingData === 'object' ? (holdingData.profit_rate || 0) : 0;
                    const profitAmount = typeof holdingData === 'object' ? (holdingData.profit_amount || 0) : 0;

                    const currentPrice = priceInfo.price || 0;
                    const valuation = currentPrice * qty;

                    investedSum += valuation;
                    details.push({
                        symbol,
                        name: priceInfo.name || symbol,
                        quantity: qty,
                        price: currentPrice,
                        valuation: valuation,
                        avgPrice,
                        profitRate,
                        profitAmount
                    });
                });
            }

            setHoldingsDetails(details);
            setTotalInvested(investedSum);
            setTotalAssets(cash + investedSum);
            setError(null);

        } catch (err) {
            console.error("Critical Market Data Fetch Error:", err);
            setError(err);
        } finally {
            setLoading(false);
        }
    }, [token]);

    useEffect(() => {
        if (token) {
            fetchData();
            const interval = setInterval(fetchData, 5000);
            return () => clearInterval(interval);
        } else {
            // Reset if no token
            setBalanceData({ cash: { KRW: 0 }, holdings: {} });
            setSystemStatus({ exchange: 'Unknown', status: 'offline', mode: 'UNKNOWN' });
        }
    }, [token, fetchData]);

    const value = {
        balanceData,
        systemStatus,
        holdingsDetails,
        totalAssets,
        totalInvested,
        loading,
        error,
        refresh: fetchData
    };

    return (
        <MarketDataContext.Provider value={value}>
            {children}
        </MarketDataContext.Provider>
    );
};

export const useMarketData = () => {
    const context = useContext(MarketDataContext);
    // Allow usage without provider (returns default context) to prevent crashes,
    // although it should typically be wrapped.
    if (!context) {
        console.warn('useMarketData used outside of MarketDataProvider');
        return {
            balanceData: { cash: { KRW: 0 }, holdings: {} },
            systemStatus: { exchange: 'Unknown', status: 'offline', mode: 'UNKNOWN' },
            holdingsDetails: [],
            totalAssets: 0,
            totalInvested: 0,
            loading: false,
            error: null,
            refresh: () => { }
        };
    }
    return context;
};
