import { useState, useCallback, useEffect, useRef } from 'react';
import { getMarketDataStatus, fetchMarketDataForSymbol } from '../api/strategies';
import { DEFAULT_EXCHANGE, getMaxDays } from '../constants/exchanges';

/**
 * useDataFetching - Market data status checking and fetching.
 */
export const useDataFetching = ({
    currentConfig, currentSymbol, configList, setConfigList,
    activeTab, isConfigLoaded, addLog, exchangeName = DEFAULT_EXCHANGE
}) => {
    const [dataStatus, setDataStatus] = useState({ is_fresh: false, count: 0, start_date: null });
    const [isFetchingData, setIsFetchingData] = useState(false);
    const [fetchMessage, setFetchMessage] = useState(null);
    const [isDataUpdated, setIsDataUpdated] = useState(false); // Gate: Update 클릭 완료 후에만 backtest/optimization 허용
    const pollRef = useRef(null);

    const stopPolling = useCallback(() => {
        if (pollRef.current) {
            clearInterval(pollRef.current);
            pollRef.current = null;
        }
    }, []);

    const checkDataStatus = useCallback(async (symbol) => {
        try {
            const data = await getMarketDataStatus(symbol, { interval: "1m" });
            setDataStatus(data);

            // Auto-set Start Date ONLY when from_date is empty (not user-set)
            if (data.start_date && !currentConfig?.from_date) {
                const parts = data.start_date.split('.');
                if (parts.length === 3) {
                    const yyyy = `20${parts[0]}`;
                    const mm = parts[1];
                    const dd = parts[2];
                    let newDate = `${yyyy}-${mm}-${dd}`;
                    const minDate = new Date();
                    minDate.setDate(minDate.getDate() - getMaxDays(exchangeName));
                    if (new Date(newDate) < minDate) {
                        newDate = minDate.toISOString().split('T')[0];
                    }
                    if (activeTab >= 0 && activeTab < configList.length) {
                        const newList = [...configList];
                        newList[activeTab] = { ...newList[activeTab], from_date: newDate };
                        setConfigList(newList);
                    }
                }
            }
            return data;
        } catch (e) {
            console.error("Failed to check data status", e);
            setFetchMessage(`Status Error: ${e.message}`);
            return null;
        }
    }, [currentConfig?.from_date, activeTab, configList, setConfigList, exchangeName]);

    // Auto-check data status on symbol/config change
    useEffect(() => {
        if (!isConfigLoaded) return;
        if (activeTab < 0 && activeTab !== -1 && activeTab !== -3) return;

        const symbolToCheck = currentConfig?.symbol || currentSymbol;
        if (symbolToCheck) {
            checkDataStatus(symbolToCheck);
        }
        setFetchMessage(null);
        setIsDataUpdated(false); // 심볼/탭 변경 시 리셋 → Update 다시 필요
    }, [currentConfig?.symbol, currentSymbol, isConfigLoaded, activeTab]);

    // Cleanup polling on unmount
    useEffect(() => stopPolling, [stopPolling]);

    const handleFetchData = useCallback(async (backfill = false) => {
        setIsFetchingData(true);
        setFetchMessage(backfill ? `Backfilling...` : `Updating...`);
        const symbolToFetch = currentConfig?.symbol || currentSymbol;
        const countBefore = dataStatus.count || 0;

        try {
            const data = await fetchMarketDataForSymbol(symbolToFetch, {
                interval: "1m",
                days: getMaxDays(exchangeName),
                backfill: backfill,
                exchange_name: exchangeName
            });

            // Backend returns added=-1 for background tasks
            if (data.added === -1) {
                // Poll data status every 3 seconds to show progress
                let stableCount = 0;
                let lastCount = countBefore;

                pollRef.current = setInterval(async () => {
                    try {
                        const status = await getMarketDataStatus(symbolToFetch, { interval: "1m" });
                        setDataStatus(status);
                        const added = status.count - countBefore;
                        setFetchMessage(`Fetching... (+${added.toLocaleString()})`);

                        if (status.count === lastCount) {
                            stableCount++;
                        } else {
                            stableCount = 0;
                            lastCount = status.count;
                        }

                        // Stop if count hasn't changed for 4 consecutive polls (~12 seconds)
                        if (stableCount >= 4) {
                            stopPolling();
                            const totalAdded = status.count - countBefore;
                            setFetchMessage(totalAdded > 0 ? `Updated (+${totalAdded.toLocaleString()})` : `Up to date (+0)`);
                            setIsFetchingData(false);
                            setIsDataUpdated(true);
                        }
                    } catch { /* ignore polling errors */ }
                }, 3000);
            } else {
                // Sync response (small fetches that complete quickly)
                const added = data.added;
                const resultMsg = added > 0 ? `Updated (+${added.toLocaleString()})` : `Up to date (+0)`;
                await checkDataStatus(symbolToFetch);
                setFetchMessage(resultMsg);
                setIsFetchingData(false);
                setIsDataUpdated(true);
            }
        } catch (e) {
            setFetchMessage("Failed");
            setTimeout(() => setFetchMessage(null), 3000);
            setIsFetchingData(false);
        }
    }, [currentConfig, currentSymbol, checkDataStatus, exchangeName, dataStatus.count, stopPolling]);

    const handleUpdateAllData = useCallback(async (symbolList = null) => {
        // symbolList: optional array of symbol strings (for Symbol Compare tab)
        // If not provided, uses configList symbols (for Integrated/Rank tabs)
        const symbols = symbolList
            ? symbolList.map(s => ({ symbol: s, label: s }))
            : configList.map((cfg, i) => ({ symbol: cfg.symbol, label: `Rank ${i + 1} (${cfg.symbol})` }));
        const validSymbols = symbols.filter(s => s.symbol);
        if (validSymbols.length === 0) return;

        const total = validSymbols.length;
        setIsFetchingData(true);
        setIsDataUpdated(false);

        try {
            // Phase 1: Get initial counts and queue all fetch requests
            const tracker = {};

            for (let i = 0; i < total; i++) {
                const { symbol, label } = validSymbols[i];
                setFetchMessage(`Queueing ${i + 1}/${total}: ${label}...`);
                try {
                    const status = await getMarketDataStatus(symbol, { interval: "1m" });
                    tracker[symbol] = { last: status.count || 0, stable: 0, done: false };
                    await fetchMarketDataForSymbol(symbol, {
                        interval: "1m",
                        days: getMaxDays(exchangeName),
                        exchange_name: exchangeName
                    });
                } catch (err) {
                    console.error(`Failed to queue ${label}`, err);
                    tracker[symbol] = { last: 0, stable: 0, done: true, failed: true };
                }
            }

            // Phase 2: Poll until all symbols' data stabilizes
            setFetchMessage(`Downloading 0/${total}...`);

            await new Promise((resolve) => {
                let polling = false;
                pollRef.current = setInterval(async () => {
                    if (polling) return;
                    polling = true;

                    let doneCount = 0;
                    for (const { symbol } of validSymbols) {
                        const t = tracker[symbol];
                        if (t.done) { doneCount++; continue; }

                        try {
                            const status = await getMarketDataStatus(symbol, { interval: "1m" });
                            if (status.count === t.last) {
                                t.stable++;
                            } else {
                                t.stable = 0;
                                t.last = status.count;
                            }
                            if (t.stable >= 4) {
                                t.done = true;
                                doneCount++;
                            }
                        } catch {
                            t.stable++;
                            if (t.stable >= 4) { t.done = true; doneCount++; }
                        }
                    }

                    setFetchMessage(`Downloading ${doneCount}/${total}...`);

                    if (doneCount >= total) {
                        stopPolling();
                        resolve();
                    }
                    polling = false;
                }, 3000);
            });

            // Phase 3: Report results
            const failedSymbols = validSymbols.filter(s => tracker[s.symbol]?.failed);
            if (failedSymbols.length > 0) {
                setFetchMessage(`Updated ${total - failedSymbols.length}/${total} (${failedSymbols.map(s => s.symbol).join(', ')} failed)`);
            } else {
                setFetchMessage(`All ${total} symbols updated`);
            }
            setTimeout(() => setFetchMessage(null), 5000);
            setIsDataUpdated(true);
        } catch (e) {
            console.error("Update All Failed", e);
            setFetchMessage("Failed");
            setTimeout(() => setFetchMessage(null), 3000);
        } finally {
            setIsFetchingData(false);
        }
    }, [configList, exchangeName, stopPolling]);

    return {
        dataStatus, isFetchingData, fetchMessage, setFetchMessage,
        isDataUpdated, checkDataStatus, handleFetchData, handleUpdateAllData
    };
};
