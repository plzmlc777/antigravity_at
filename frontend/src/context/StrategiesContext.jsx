/**
 * StrategiesContext
 *
 * Centralized state management for Strategies page functionality.
 * Provides single source of truth for:
 * - Selected strategy (with DB persistence)
 * - Effective account ID (real account priority auto-selection)
 *
 * Shared data (accounts, strategies) is consumed from LiveTradingContext
 * to avoid duplicate API calls.
 */

import React, { createContext, useContext, useState, useEffect, useMemo } from 'react';
import { getAccountPreferences, updateLastSelectedStrategy } from '../api/client';
import { STORAGE_KEYS } from '../constants/strategies';
import { useLiveTrading } from './LiveTradingContext';

const StrategiesContext = createContext(null);

export const StrategiesProvider = ({ children }) => {
    // ==========================================
    // Shared Data from LiveTradingContext (single source of truth)
    // Avoids duplicate getAccounts() and strategies/list API calls
    // ==========================================
    const {
        accounts,
        strategies,
        strategiesLoading,
        loadStrategies,
        loadAccounts,
    } = useLiveTrading();

    // ==========================================
    // Active account ID is no longer used (is_active removed).
    // effectiveAccountId is auto-selected below based on priority.
    // ==========================================

    // ==========================================
    // Selected Strategy (persisted to DB + localStorage)
    // This is separate from LiveTradingContext's selectedStrategy
    // (which is derived from active live session)
    // ==========================================
    const [selectedStrategy, setSelectedStrategy] = useState(null);
    const strategiesRestoredRef = React.useRef(false);

    // ==========================================
    // Effective Account ID (real account priority auto-selection)
    // ==========================================
    const [effectiveAccountId, setEffectiveAccountId] = useState(null);

    // ==========================================
    // Restore last selected strategy when strategies load
    // ==========================================
    useEffect(() => {
        if (strategiesRestoredRef.current || strategies.length === 0 || selectedStrategy) {
            return;
        }

        const restoreSelectedStrategy = async () => {
            try {
                const preferences = await getAccountPreferences();
                const savedId = preferences?.last_selected_strategy_id;

                if (savedId) {
                    const target = strategies.find(s => s.id === savedId);
                    if (target) {
                        setSelectedStrategy(target);
                        strategiesRestoredRef.current = true;
                        return;
                    }
                }

                // Fallback to localStorage (migration period)
                const localStorageId = localStorage.getItem(STORAGE_KEYS.LAST_STRATEGY_ID);
                if (localStorageId) {
                    const target = strategies.find(s => s.id === localStorageId);
                    if (target) {
                        setSelectedStrategy(target);
                        // Migrate to DB
                        updateLastSelectedStrategy(localStorageId).catch(e =>
                            console.warn('Failed to migrate strategy to DB:', e)
                        );
                    }
                }
            } catch (e) {
                console.warn('Failed to load account preferences:', e);
                const localStorageId = localStorage.getItem(STORAGE_KEYS.LAST_STRATEGY_ID);
                if (localStorageId) {
                    const target = strategies.find(s => s.id === localStorageId);
                    if (target) {
                        setSelectedStrategy(target);
                    }
                }
            }
            strategiesRestoredRef.current = true;
        };

        restoreSelectedStrategy();
    }, [strategies, selectedStrategy]);

    // ==========================================
    // Auto-select effective account ID from accounts
    // Priority: real > virtual/paper > any non-disabled
    // ==========================================
    useEffect(() => {
        if (accounts.length === 0) return;

        // Real account priority (environment === 'real')
        const realAccount = accounts.find(a => a.environment === 'real' && !a.is_disabled);
        if (realAccount) {
            setEffectiveAccountId(realAccount.id);
            return;
        }

        // Virtual/paper account fallback
        const virtualAccount = accounts.find(a =>
            (a.environment === 'virtual' || a.environment === 'paper') && !a.is_disabled
        );
        if (virtualAccount) {
            setEffectiveAccountId(virtualAccount.id);
            return;
        }

        // Last fallback: first non-disabled account
        const anyAccount = accounts.find(a => !a.is_disabled);
        if (anyAccount) {
            setEffectiveAccountId(anyAccount.id);
        }
    }, [accounts]);

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
    // Context Value
    // ==========================================
    const value = useMemo(() => ({
        // Shared data (from LiveTradingContext)
        strategies,
        strategiesLoading,
        loadStrategies,
        accounts,
        loadAccounts,

        // Strategies-page specific
        selectedStrategy,
        setSelectedStrategy,
        effectiveAccountId,
    }), [strategies, strategiesLoading, loadStrategies, accounts, loadAccounts,
         selectedStrategy, effectiveAccountId]);

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
