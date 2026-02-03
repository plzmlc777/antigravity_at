import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import { getAccountPreferences, updateWatchlist } from '../api/client';
import { useAuth } from './AuthContext';

const WatchlistContext = createContext(null);

// Default symbols
const DEFAULT_SYMBOLS = [
    { code: '005930', name: '삼성전자' },
    { code: '000660', name: 'SK하이닉스' }
];

export const WatchlistProvider = ({ children }) => {
    const { token } = useAuth();
    const [currentSymbol, setCurrentSymbolState] = useState('005930');
    const [savedSymbols, setSavedSymbolsState] = useState(DEFAULT_SYMBOLS);
    const [isLoaded, setIsLoaded] = useState(false);

    // Debounce timer ref
    const saveTimerRef = useRef(null);

    // Load from DB on mount (when logged in)
    useEffect(() => {
        if (!token) {
            // Not logged in - use localStorage fallback
            const localSymbol = localStorage.getItem('lastSymbol') || '005930';
            const localSaved = localStorage.getItem('savedSymbols');
            setCurrentSymbolState(localSymbol);
            if (localSaved) {
                try {
                    const parsed = JSON.parse(localSaved);
                    setSavedSymbolsState(parsed.map(item =>
                        typeof item === 'string' ? { code: item, name: '' } : item
                    ));
                } catch (e) {
                    setSavedSymbolsState(DEFAULT_SYMBOLS);
                }
            }
            setIsLoaded(true);
            return;
        }

        // Logged in - load from DB
        const loadFromDB = async () => {
            try {
                const prefs = await getAccountPreferences();

                // Check if DB has data
                const dbHasSymbol = prefs.last_symbol;
                const dbHasSavedSymbols = prefs.saved_symbols && Array.isArray(prefs.saved_symbols) && prefs.saved_symbols.length > 0;

                // Load from localStorage
                const localSymbol = localStorage.getItem('lastSymbol');
                const localSavedRaw = localStorage.getItem('savedSymbols');
                let localSaved = null;
                if (localSavedRaw) {
                    try {
                        const parsed = JSON.parse(localSavedRaw);
                        localSaved = parsed.map(item =>
                            typeof item === 'string' ? { code: item, name: '' } : item
                        );
                    } catch (e) {
                        localSaved = null;
                    }
                }

                // Use DB data if available, otherwise fallback to localStorage
                const finalSymbol = dbHasSymbol ? prefs.last_symbol : (localSymbol || '005930');
                const finalSavedSymbols = dbHasSavedSymbols ? prefs.saved_symbols : (localSaved || DEFAULT_SYMBOLS);

                setCurrentSymbolState(finalSymbol);
                setSavedSymbolsState(finalSavedSymbols);
                setIsLoaded(true);

                // If DB was empty but localStorage had data, sync to DB
                if ((!dbHasSymbol || !dbHasSavedSymbols) && (localSymbol || localSaved)) {
                    console.log('Migrating localStorage watchlist to DB...');
                    try {
                        await updateWatchlist(finalSymbol, finalSavedSymbols);
                    } catch (e) {
                        console.warn('Failed to migrate watchlist to DB:', e);
                    }
                }
            } catch (e) {
                console.warn('Failed to load watchlist from DB, using localStorage fallback:', e);
                // Fallback to localStorage
                const localSymbol = localStorage.getItem('lastSymbol') || '005930';
                const localSaved = localStorage.getItem('savedSymbols');
                setCurrentSymbolState(localSymbol);
                if (localSaved) {
                    try {
                        const parsed = JSON.parse(localSaved);
                        setSavedSymbolsState(parsed.map(item =>
                            typeof item === 'string' ? { code: item, name: '' } : item
                        ));
                    } catch (e) {
                        setSavedSymbolsState(DEFAULT_SYMBOLS);
                    }
                }
                setIsLoaded(true);
            }
        };

        loadFromDB();
    }, [token]);

    // Save to DB with debounce
    const saveToDB = useCallback(async (symbol, symbols) => {
        if (!token) {
            // Not logged in - save to localStorage only
            localStorage.setItem('lastSymbol', symbol);
            localStorage.setItem('savedSymbols', JSON.stringify(symbols));
            return;
        }

        // Clear existing timer
        if (saveTimerRef.current) {
            clearTimeout(saveTimerRef.current);
        }

        // Save to localStorage immediately (cache)
        localStorage.setItem('lastSymbol', symbol);
        localStorage.setItem('savedSymbols', JSON.stringify(symbols));

        // Debounce DB save (1 second)
        saveTimerRef.current = setTimeout(async () => {
            try {
                await updateWatchlist(symbol, symbols);
            } catch (e) {
                console.warn('Failed to save watchlist to DB:', e);
            }
        }, 1000);
    }, [token]);

    // Set current symbol
    const setCurrentSymbol = useCallback((symbol) => {
        setCurrentSymbolState(symbol);
        saveToDB(symbol, savedSymbols);
    }, [savedSymbols, saveToDB]);

    // Set saved symbols
    const setSavedSymbols = useCallback((symbols) => {
        // Handle both array and function updater
        setSavedSymbolsState(prev => {
            const newSymbols = typeof symbols === 'function' ? symbols(prev) : symbols;
            saveToDB(currentSymbol, newSymbols);
            return newSymbols;
        });
    }, [currentSymbol, saveToDB]);

    // Add symbol to watchlist
    const addSymbol = useCallback((code, name = '') => {
        setSavedSymbols(prev => {
            const exists = prev.some(s => s.code === code);
            if (exists) return prev;
            return [...prev, { code, name }];
        });
    }, [setSavedSymbols]);

    // Remove symbol from watchlist
    const removeSymbol = useCallback((code) => {
        setSavedSymbols(prev => prev.filter(s => s.code !== code));
    }, [setSavedSymbols]);

    return (
        <WatchlistContext.Provider value={{
            currentSymbol,
            setCurrentSymbol,
            savedSymbols,
            setSavedSymbols,
            addSymbol,
            removeSymbol,
            isLoaded
        }}>
            {children}
        </WatchlistContext.Provider>
    );
};

export const useWatchlist = () => {
    const context = useContext(WatchlistContext);
    if (!context) {
        throw new Error('useWatchlist must be used within a WatchlistProvider');
    }
    return context;
};
