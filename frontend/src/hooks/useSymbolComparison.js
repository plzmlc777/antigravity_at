import { useState, useCallback } from 'react';
import { runBacktest as apiRunBacktest, fetchMarketDataForSymbol } from '../api/strategies';
import { exportCompareResultsToCSV } from '../utils/strategyExportImport';

/**
 * useSymbolComparison - Multi-symbol backtest comparison.
 */
export const useSymbolComparison = ({
    symbolCompareConfig, configList, selectedStrategy,
    savedSymbols, setIsSymbolCompareDirty, addLog,
    saveProfile = null, selectedProfileId = null
}) => {
    const [selectedCompareSymbols, setSelectedCompareSymbols] = useState([]);
    const [stockCompareResults, setStockCompareResults] = useState([]);
    const [isStockComparing, setIsStockComparing] = useState(false);
    const [stockCompareProgress, setStockCompareProgress] = useState({ current: 0, total: 0, phase: 'data' });
    const [compareSortConfig, setCompareSortConfig] = useState({ key: 'score', direction: 'desc' });

    const handleStockCompareBacktest = useCallback(async () => {
        if (selectedCompareSymbols.length === 0) {
            addLog('No symbols selected for comparison', 'error');
            return;
        }

        const baseConfig = symbolCompareConfig || configList[0];
        if (!baseConfig) {
            addLog('No configuration available for comparison', 'error');
            return;
        }

        setIsStockComparing(true);
        setStockCompareResults([]);
        const totalSymbols = selectedCompareSymbols.length;
        setStockCompareProgress({ current: 0, total: totalSymbols, phase: 'data' });
        const results = [];

        try {
            // Step 1: Update chart data
            const DATA_FETCH_DELAY_MS = 500;
            addLog(`Updating chart data for ${totalSymbols} symbols...`, 'info');
            let totalDataAdded = 0;
            for (let i = 0; i < totalSymbols; i++) {
                const symbol = selectedCompareSymbols[i];
                setStockCompareProgress({ current: i + 1, total: totalSymbols, phase: 'data' });
                try {
                    const fetchRes = await fetchMarketDataForSymbol(symbol, { interval: "1m", days: 365 });
                    const added = fetchRes?.added || 0;
                    totalDataAdded += added;
                    if (added > 0) {
                        addLog(`${symbol}: +${added} candles updated`, 'info');
                    }
                } catch (err) {
                    console.warn(`Failed to update data for ${symbol}`, err);
                    addLog(`${symbol}: data update failed`, 'warning');
                }
                if (i < totalSymbols - 1) {
                    await new Promise(resolve => setTimeout(resolve, DATA_FETCH_DELAY_MS));
                }
            }
            addLog(`Data update completed: +${totalDataAdded} total candles`, totalDataAdded > 0 ? 'success' : 'info');

            // Step 2: Run backtests
            const BACKTEST_DELAY_MS = 200;
            addLog(`Running backtests for ${totalSymbols} symbols...`, 'info');
            for (let i = 0; i < totalSymbols; i++) {
                const symbol = selectedCompareSymbols[i];
                setStockCompareProgress({ current: i + 1, total: totalSymbols, phase: 'backtest' });

                try {
                    const defaultToDate = new Date(Date.now() - 86400000).toISOString().split('T')[0];
                    const payload = {
                        symbol: symbol,
                        interval: baseConfig.interval || "1m",
                        days: baseConfig.days || 365,
                        from_date: baseConfig.from_date || "",
                        to_date: baseConfig.to_date || defaultToDate,
                        initial_capital: baseConfig.initial_capital || 10000000,
                        config: { ...baseConfig, symbol: symbol }
                    };

                    const data = await apiRunBacktest(selectedStrategy.id, payload);
                    const ret = parseFloat(String(data.total_return || 0).replace('%', '').replace(',', ''));
                    const wr = parseFloat(String(data.win_rate || 0).replace('%', ''));
                    const score = ret * (wr / 100);

                    results.push({
                        symbol, name: savedSymbols?.find(s => s.code === symbol)?.name || '',
                        total_return: data.total_return, profit_factor: data.profit_factor,
                        win_rate: data.win_rate, recent_10_win_rate: data.recent_10_win_rate,
                        sharpe_ratio: data.sharpe_ratio, total_trades: data.total_trades,
                        stability_score: data.stability_score, acceleration_score: data.acceleration_score,
                        activity_rate: data.activity_rate, avg_pnl: data.avg_pnl,
                        avg_holding_time: data.avg_holding_time, max_holding_time: data.max_holding_time,
                        min_holding_time: data.min_holding_time, max_profit: data.max_profit,
                        max_loss: data.max_loss, max_drawdown: data.max_drawdown, score
                    });
                    setStockCompareResults([...results]);
                } catch (err) {
                    console.error(`Backtest failed for ${symbol}`, err);
                    results.push({
                        symbol, name: savedSymbols?.find(s => s.code === symbol)?.name || '',
                        total_return: 'Error', profit_factor: null, win_rate: null,
                        recent_10_win_rate: null, sharpe_ratio: null, total_trades: 0,
                        stability_score: null, acceleration_score: null, activity_rate: null,
                        avg_pnl: null, avg_holding_time: null, max_holding_time: null,
                        min_holding_time: null, max_profit: null, max_loss: null,
                        max_drawdown: null, score: -999
                    });
                    setStockCompareResults([...results]);
                }
                if (i < totalSymbols - 1) {
                    await new Promise(resolve => setTimeout(resolve, BACKTEST_DELAY_MS));
                }
            }

            addLog(`Stock comparison completed: ${results.length} symbols tested`, 'success');
            setIsSymbolCompareDirty(true);

            // Auto-save profile to persist dates alongside results
            if (saveProfile && selectedProfileId) {
                saveProfile().catch(err => console.warn("Auto-save profile after comparison failed:", err));
            }
        } catch (e) {
            console.error("Symbol Comparison Failed", e);
            addLog(`Stock comparison failed: ${e.message}`, 'error');
        } finally {
            setIsStockComparing(false);
            setStockCompareProgress({ current: 0, total: 0, phase: 'data' });
        }
    }, [selectedCompareSymbols, symbolCompareConfig, configList, selectedStrategy, savedSymbols, setIsSymbolCompareDirty, addLog, saveProfile, selectedProfileId]);

    const handleExportCompareResults = useCallback(() => {
        if (stockCompareResults.length === 0) {
            addLog('No results to export', 'warning');
            return;
        }
        const filename = exportCompareResultsToCSV(stockCompareResults);
        if (filename) {
            addLog(`Exported ${stockCompareResults.length} results to CSV`, 'success');
        }
    }, [stockCompareResults, addLog]);

    return {
        selectedCompareSymbols, setSelectedCompareSymbols,
        stockCompareResults, setStockCompareResults,
        isStockComparing, stockCompareProgress,
        isSymbolCompareDirty: false, // managed externally
        compareSortConfig, setCompareSortConfig,
        handleStockCompareBacktest, handleExportCompareResults
    };
};
