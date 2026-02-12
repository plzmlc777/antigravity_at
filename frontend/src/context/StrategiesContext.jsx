/**
 * StrategiesContext
 *
 * Centralized state management for Strategies page functionality.
 * Provides single source of truth for:
 * - Strategy list (cached, loaded once)
 * - Selected strategy (with DB persistence)
 * - Accounts list & effective account ID (real account priority)
 */

import React, { createContext, useContext, useState, useCallback, useEffect, useRef } from 'react';
import axios from 'axios';
import { getAccounts, getAccountPreferences, updateLastSelectedStrategy } from '../api/client';
import { STORAGE_KEYS } from '../constants/strategies';
import { useMarketData } from './MarketDataContext';

const StrategiesContext = createContext(null);

export const StrategiesProvider = ({ children }) => {
    // ==========================================
    // MarketData Context (for active account)
    // ==========================================
    const { systemStatus } = useMarketData();
    const activeAccountId = systemStatus?.account_id || null;

    // ==========================================
    // Strategy List (loaded once, cached)
    // ==========================================
    const [strategies, setStrategies] = useState([]);
    const [strategiesLoading, setStrategiesLoading] = useState(false);
    const strategiesLoadedRef = useRef(false);

    // ==========================================
    // Selected Strategy (persisted to DB + localStorage)
    // ==========================================
    const [selectedStrategy, setSelectedStrategy] = useState(null);

    // ==========================================
    // Accounts & Effective Account ID
    // ==========================================
    const [accounts, setAccounts] = useState([]);
    const [effectiveAccountId, setEffectiveAccountId] = useState(null);
    const accountsLoadedRef = useRef(false);

    // ==========================================
    // Load Strategies (once, with last-selected restore)
    // ==========================================
    const loadStrategies = useCallback(async (force = false) => {
        if (strategiesLoadedRef.current && !force) {
            return strategies;
        }

        setStrategiesLoading(true);
        try {
            const res = await axios.get('/api/v1/strategies/list');
            const strategyList = res.data || [];
            setStrategies(strategyList);
            strategiesLoadedRef.current = true;

            // Restore last selected strategy (only on first load)
            if (!force && strategyList.length > 0 && !selectedStrategy) {
                try {
                    const preferences = await getAccountPreferences();
                    const savedId = preferences?.last_selected_strategy_id;

                    if (savedId) {
                        const target = strategyList.find(s => s.id === savedId);
                        if (target) {
                            setSelectedStrategy(target);
                        }
                    } else {
                        // Fallback to localStorage (migration period)
                        const localStorageId = localStorage.getItem(STORAGE_KEYS.LAST_STRATEGY_ID);
                        if (localStorageId) {
                            const target = strategyList.find(s => s.id === localStorageId);
                            if (target) {
                                setSelectedStrategy(target);
                                // Migrate to DB
                                updateLastSelectedStrategy(localStorageId).catch(e =>
                                    console.warn('Failed to migrate strategy to DB:', e)
                                );
                            }
                        }
                    }
                } catch (e) {
                    console.warn('Failed to load account preferences:', e);
                    // Fallback to localStorage
                    const localStorageId = localStorage.getItem(STORAGE_KEYS.LAST_STRATEGY_ID);
                    if (localStorageId) {
                        const target = strategyList.find(s => s.id === localStorageId);
                        if (target) {
                            setSelectedStrategy(target);
                        }
                    }
                }
            }

            return strategyList;
        } catch (e) {
            console.error('Failed to load strategies:', e);
            return [];
        } finally {
            setStrategiesLoading(false);
        }
    }, [strategies, selectedStrategy]);

    // ==========================================
    // Load Accounts (once, with auto-selection)
    // ==========================================
    const loadAccounts = useCallback(async (force = false) => {
        if (accountsLoadedRef.current && !force) {
            return accounts;
        }

        try {
            const accountList = await getAccounts();
            setAccounts(accountList || []);
            accountsLoadedRef.current = true;

            // Auto-select effective account
            if (activeAccountId) {
                setEffectiveAccountId(activeAccountId);
                return accountList;
            }

            // Real account priority (environment === 'real')
            const realAccount = accountList?.find(a => a.environment === 'real' && !a.is_disabled);
            if (realAccount) {
                setEffectiveAccountId(realAccount.id);
                console.log('[StrategiesContext] Auto-selected real account:', realAccount.account_name);
                return accountList;
            }

            // Virtual/paper account fallback
            const virtualAccount = accountList?.find(a =>
                (a.environment === 'virtual' || a.environment === 'paper') && !a.is_disabled
            );
            if (virtualAccount) {
                setEffectiveAccountId(virtualAccount.id);
                console.log('[StrategiesContext] Auto-selected virtual account:', virtualAccount.account_name);
                return accountList;
            }

            // Last fallback: first non-disabled account
            const anyAccount = accountList?.find(a => !a.is_disabled);
            if (anyAccount) {
                setEffectiveAccountId(anyAccount.id);
                console.log('[StrategiesContext] Auto-selected first available account:', anyAccount.account_name);
            }

            return accountList;
        } catch (e) {
            console.error('[StrategiesContext] Failed to load accounts:', e);
            return [];
        }
    }, [accounts, activeAccountId]);

    // ==========================================
    // Update effectiveAccountId when activeAccountId changes
    // ==========================================
    useEffect(() => {
        if (activeAccountId) {
            setEffectiveAccountId(activeAccountId);
        }
    }, [activeAccountId]);

    // ==========================================
    // Persist selected strategy to DB + localStorage
    // ==========================================
    useEffect(() => {
        if (selectedStrategy) {
            updateLastSelectedStrategy(selectedStrategy.id).catch(e => {
                console.warn('Failed to save strategy preference to DB:', e);
            });
            localStorage.setItem(STORAGE_KEYS.LAST_STRATEGY_ID, selectedStrategy.id);
        }
    }, [selectedStrategy]);

    // ==========================================
    // Load initial data on mount
    // ==========================================
    useEffect(() => {
        loadStrategies();
        loadAccounts();
    }, []);

    // ==========================================
    // Reload accounts when activeAccountId changes
    // ==========================================
    useEffect(() => {
        if (activeAccountId && !accountsLoadedRef.current) {
            loadAccounts();
        }
    }, [activeAccountId]);

    // ==========================================
    // Context Value
    // ==========================================
    const value = {
        // Strategy list
        strategies,
        strategiesLoading,
        loadStrategies,

        // Selected strategy
        selectedStrategy,
        setSelectedStrategy,

        // Account management
        accounts,
        effectiveAccountId,
        loadAccounts,
    };

    return (
        <StrategiesContext.Provider value={value}>
            {children}
        </StrategiesContext.Provider>
    );
};

// ==========================================
// Hook for consuming context
// ==========================================
export const useStrategies = () => {
    const context = useContext(StrategiesContext);
    if (!context) {
        throw new Error('useStrategies must be used within a StrategiesProvider');
    }
    return context;
};

export default StrategiesContext;
