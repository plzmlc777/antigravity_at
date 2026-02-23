/**
 * LiveTradingContext
 *
 * Centralized state management for Live Trading functionality.
 * Provides single source of truth for:
 * - Active session group
 * - Execution mode
 * - Accounts list (cached)
 * - Strategies list (cached)
 */

import React, { createContext, useContext, useState, useCallback, useEffect, useRef } from 'react';
import { getAccounts } from '../api/client';
import axios from 'axios';
import { STORAGE_KEYS, DEFAULTS } from '../constants/live';

const LiveTradingContext = createContext(null);

export const LiveTradingProvider = ({ children }) => {
    // ==========================================
    // Core State
    // ==========================================

    // Active session group (selected in SessionSwitcher)
    const [activeSessionGroup, setActiveSessionGroup] = useState(null);

    // Execution mode (exclusive vs parallel)
    const [executionMode, setExecutionMode] = useState(() => {
        const saved = localStorage.getItem(STORAGE_KEYS.EXECUTION_MODE);
        return saved || DEFAULTS.EXECUTION_MODE;
    });

    // Is live session currently running
    const [isLiveRunning, setIsLiveRunning] = useState(false);

    // ==========================================
    // Cached Data (loaded once, shared across components)
    // ==========================================

    // Accounts list
    const [accounts, setAccounts] = useState([]);
    const [accountsLoading, setAccountsLoading] = useState(false);
    const accountsLoadedRef = useRef(false);

    // Strategies list
    const [strategies, setStrategies] = useState([]);
    const [strategiesLoading, setStrategiesLoading] = useState(false);
    const strategiesLoadedRef = useRef(false);

    // Selected strategy (derived from activeSessionGroup)
    const [selectedStrategy, setSelectedStrategy] = useState(null);

    // ==========================================
    // Persist execution mode to localStorage
    // ==========================================
    useEffect(() => {
        localStorage.setItem(STORAGE_KEYS.EXECUTION_MODE, executionMode);
    }, [executionMode]);

    // ==========================================
    // Sync execution mode from active session group's strategy_config
    // ==========================================
    useEffect(() => {
        if (!activeSessionGroup) return;
        const config = activeSessionGroup.configList?.[0];
        const mode = config?.execution_mode;
        if (mode && (mode === 'parallel' || mode === 'exclusive') && mode !== executionMode) {
            setExecutionMode(mode);
        }
    }, [activeSessionGroup]);

    // ==========================================
    // Load accounts (once, with caching)
    // ==========================================
    const loadAccounts = useCallback(async (force = false) => {
        if (accountsLoadedRef.current && !force) {
            return accounts;
        }

        setAccountsLoading(true);
        try {
            const data = await getAccounts();
            // Sort: enabled first, then by id
            const sorted = [...(data || [])].sort((a, b) => {
                if (a.is_disabled !== b.is_disabled) return a.is_disabled ? 1 : -1;
                return a.id - b.id;
            });
            setAccounts(sorted);
            accountsLoadedRef.current = true;
            return sorted;
        } catch (err) {
            console.error('Failed to load accounts:', err);
            return [];
        } finally {
            setAccountsLoading(false);
        }
    }, [accounts]);

    // ==========================================
    // Load strategies (once, with caching)
    // ==========================================
    const loadStrategies = useCallback(async (force = false) => {
        if (strategiesLoadedRef.current && !force) {
            return strategies;
        }

        setStrategiesLoading(true);
        try {
            const res = await axios.get('/api/v1/strategies/list', { params: { status: 'active' } });
            setStrategies(res.data || []);
            strategiesLoadedRef.current = true;
            return res.data || [];
        } catch (err) {
            console.error('Failed to load strategies:', err);
            return [];
        } finally {
            setStrategiesLoading(false);
        }
    }, [strategies]);

    // ==========================================
    // Auto-update selectedStrategy when session or strategies change
    // ==========================================
    useEffect(() => {
        if (activeSessionGroup?.strategyName && strategies.length > 0) {
            const matching = strategies.find(s => s.id === activeSessionGroup.strategyName);
            if (matching && matching.id !== selectedStrategy?.id) {
                setSelectedStrategy(matching);
            }
        }
    }, [strategies, activeSessionGroup?.strategyName, selectedStrategy?.id]);

    // ==========================================
    // Load initial data on mount
    // ==========================================
    useEffect(() => {
        loadAccounts();
        loadStrategies();
    }, []);

    // ==========================================
    // Helper: Get active account
    // ==========================================
    const getActiveAccount = useCallback(() => {
        return accounts.find(a => !a.is_disabled);
    }, [accounts]);

    // ==========================================
    // Helper: Get account by ID
    // ==========================================
    const getAccountById = useCallback((accountId) => {
        return accounts.find(a => a.id === accountId);
    }, [accounts]);

    // ==========================================
    // Helper: Get strategy by ID
    // ==========================================
    const getStrategyById = useCallback((strategyId) => {
        return strategies.find(s => s.id === strategyId);
    }, [strategies]);

    // ==========================================
    // Context Value
    // ==========================================
    const value = {
        // Core state
        activeSessionGroup,
        setActiveSessionGroup,
        executionMode,
        setExecutionMode,
        isLiveRunning,
        setIsLiveRunning,

        // Cached data
        accounts,
        accountsLoading,
        loadAccounts,
        strategies,
        strategiesLoading,
        loadStrategies,
        selectedStrategy,
        setSelectedStrategy,

        // Helpers
        getActiveAccount,
        getAccountById,
        getStrategyById,
    };

    return (
        <LiveTradingContext.Provider value={value}>
            {children}
        </LiveTradingContext.Provider>
    );
};

// ==========================================
// Hook for consuming context
// ==========================================
export const useLiveTrading = () => {
    const context = useContext(LiveTradingContext);
    if (!context) {
        throw new Error('useLiveTrading must be used within a LiveTradingProvider');
    }
    return context;
};

export default LiveTradingContext;
