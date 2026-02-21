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
        if (activeTab < 0 && activeTab !== -3) return;

        const symbolToCheck = currentConfig?.symbol || currentSymbol;
        if (symbolToCheck) {
            checkDataStatus(symbolToCheck);
        }
        setFetchMessage(null);
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
            }
        } catch (e) {
            setFetchMessage("Failed");
            setTimeout(() => setFetchMessage(null), 3000);
            setIsFetchingData(false);
        }
    }, [currentConfig, currentSymbol, checkDataStatus, exchangeName, dataStatus.count, stopPolling]);

    const handleUpdateAllData = useCallback(async () => {
        if (configList.length === 0) return;
        setIsFetchingData(true);
        setFetchMessage("Queueing...");
        try {
            let updatedCount = 0;

            for (let i = 0; i < configList.length; i++) {
                const cfg = configList[i];
                if (!cfg.symbol) continue;

                setFetchMessage(`Updating Rank ${i + 1} (${cfg.symbol})...`);
                try {
                    await fetchMarketDataForSymbol(cfg.symbol, {
                        interval: "1m",
                        days: getMaxDays(exchangeName),
                        exchange_name: exchangeName
                    });
                    updatedCount++;
                } catch (err) {
                    console.error(`Failed to update Rank ${i + 1}`, err);
                }
            }

            setFetchMessage(`All ${updatedCount} symbols queued`);
            setTimeout(() => setFetchMessage(null), 3000);
        } catch (e) {
            console.error("Update All Failed", e);
            setFetchMessage("Failed");
            setTimeout(() => setFetchMessage(null), 3000);
        } finally {
            setIsFetchingData(false);
        }
    }, [configList, exchangeName]);

    return {
        dataStatus, isFetchingData, fetchMessage, setFetchMessage,
        checkDataStatus, handleFetchData, handleUpdateAllData
    };
};
