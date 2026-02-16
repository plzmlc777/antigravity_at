import { useState, useCallback, useEffect } from 'react';
import { getMarketDataStatus, fetchMarketDataForSymbol } from '../api/strategies';

/**
 * useDataFetching - Market data status checking and fetching.
 */
export const useDataFetching = ({
    currentConfig, currentSymbol, configList, setConfigList,
    activeTab, isConfigLoaded, addLog
}) => {
    const [dataStatus, setDataStatus] = useState({ is_fresh: false, count: 0, start_date: null });
    const [isFetchingData, setIsFetchingData] = useState(false);
    const [fetchMessage, setFetchMessage] = useState(null);

    const checkDataStatus = useCallback(async (symbol) => {
        try {
            const data = await getMarketDataStatus(symbol, { interval: "1m" });
            setDataStatus(data);

            // Auto-set Start Date ONLY when from_date is empty (not user-set)
            // If the user/profile already has a from_date, respect it.
            if (data.start_date && !currentConfig?.from_date) {
                const parts = data.start_date.split('.');
                if (parts.length === 3) {
                    const yyyy = `20${parts[0]}`;
                    const mm = parts[1];
                    const dd = parts[2];
                    let newDate = `${yyyy}-${mm}-${dd}`;
                    const minDate = new Date();
                    minDate.setDate(minDate.getDate() - 365);
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
        } catch (e) {
            console.error("Failed to check data status", e);
            setFetchMessage(`Status Error: ${e.message}`);
        }
    }, [currentConfig?.from_date, activeTab, configList, setConfigList]);

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

    const handleFetchData = useCallback(async (backfill = false) => {
        setIsFetchingData(true);
        setFetchMessage(backfill ? `Backfilling...` : `Updating...`);
        const symbolToFetch = currentConfig?.symbol || currentSymbol;
        try {
            const data = await fetchMarketDataForSymbol(symbolToFetch, {
                interval: "1m",
                days: 365,
                backfill: backfill
            });
            const added = data.added;
            setFetchMessage(null);

            const resultMsg = added > 0 ? `Updated (+${added})` : `Up to date (+0)`;
            await checkDataStatus(symbolToFetch);
            setFetchMessage(resultMsg);
        } catch (e) {
            setFetchMessage("Failed");
            setTimeout(() => setFetchMessage(null), 3000);
        } finally {
            setIsFetchingData(false);
        }
    }, [currentConfig, currentSymbol, checkDataStatus]);

    const handleUpdateAllData = useCallback(async () => {
        if (configList.length === 0) return;
        setIsFetchingData(true);
        setFetchMessage("Queueing...");
        try {
            let totalAdded = 0;
            let updatedCount = 0;

            for (let i = 0; i < configList.length; i++) {
                const cfg = configList[i];
                if (!cfg.symbol) continue;

                setFetchMessage(`Updating Rank ${i + 1} (${cfg.symbol})...`);
                try {
                    const fetchResult = await fetchMarketDataForSymbol(cfg.symbol, {
                        interval: "1m",
                        days: 365
                    });
                    totalAdded += (fetchResult.added || 0);
                    updatedCount++;
                } catch (err) {
                    console.error(`Failed to update Rank ${i + 1}`, err);
                }
            }

            setFetchMessage(`All Active (${updatedCount}) Updated (+${totalAdded})`);
            setTimeout(() => setFetchMessage(null), 3000);
        } catch (e) {
            console.error("Update All Failed", e);
            setFetchMessage("Failed");
            setTimeout(() => setFetchMessage(null), 3000);
        } finally {
            setIsFetchingData(false);
        }
    }, [configList]);

    return {
        dataStatus, isFetchingData, fetchMessage, setFetchMessage,
        checkDataStatus, handleFetchData, handleUpdateAllData
    };
};
