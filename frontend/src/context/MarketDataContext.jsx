import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { getStatus } from '../api/client';
import { useAuth } from './AuthContext';

const MarketDataContext = createContext({
    systemStatus: { exchange: 'Unknown', status: 'offline', mode: 'UNKNOWN' },
    loading: false,
    error: null,
    refresh: () => { }
});

// Direct 401 check — forces logout when session is kicked
const check401AndKick = (err) => {
    if (err?.response?.status === 401) {
        const detail = err.response.data?.detail || '';
        const isSessionKick = detail.includes('logged in from another device');
        if (isSessionKick) {
            sessionStorage.setItem('logout_reason', 'session_kicked');
        }
        localStorage.removeItem('token');
        sessionStorage.removeItem('token');
        window.location.href = '/login';
        return true;
    }
    return false;
};

export const MarketDataProvider = ({ children }) => {
    const { token } = useAuth();

    const [systemStatus, setSystemStatus] = useState({ exchange: 'Unknown', status: 'offline', mode: 'UNKNOWN' });
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    const fetchData = useCallback(async () => {
        if (!token) return;

        setLoading(true);
        try {
            const status = await getStatus().catch(err => {
                if (check401AndKick(err)) return null;
                console.error("Status fetch error:", err);
                return { exchange: 'Error', status: 'offline', mode: 'UNKNOWN' };
            });

            setSystemStatus(status || { exchange: 'Error', status: 'offline', mode: 'UNKNOWN' });
            setError(null);
        } catch (err) {
            console.error("Market Data Fetch Error:", err);
            setError(err);
        } finally {
            setLoading(false);
        }
    }, [token]);

    useEffect(() => {
        if (token) {
            fetchData();
            const interval = setInterval(fetchData, 30000); // 30s (status only)
            return () => clearInterval(interval);
        } else {
            setSystemStatus({ exchange: 'Unknown', status: 'offline', mode: 'UNKNOWN' });
        }
    }, [token, fetchData]);

    const value = {
        systemStatus,
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
    if (!context) {
        console.warn('useMarketData used outside of MarketDataProvider');
        return {
            systemStatus: { exchange: 'Unknown', status: 'offline', mode: 'UNKNOWN' },
            loading: false,
            error: null,
            refresh: () => { }
        };
    }
    return context;
};
