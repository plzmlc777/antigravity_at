import { useState, useEffect, useCallback, useRef } from 'react';
import {
    startHeavyOptimization as apiStartHeavyOpt, getHeavyOptimizationStatus, cancelHeavyOptimization,
    listHeavyOptimizationTasks,
    fetchMarketDataForSymbol,
    saveStrategyResult,
    getHeavyOptDownloadUrl,
} from '../api/strategies';
import { parseValues, buildDynamicDefaultConfig, buildDynamicOptValues,
         getStrategyParamNames as extractParamNames } from '../utils/strategyParamUtils';
import { exportOptResultsToCSV as exportOptCSV } from '../utils/strategyExportImport';
import { DEFAULT_EXCHANGE, getDefaultCapital, getDefaultDays, getOptRangeDefaults } from '../constants/exchanges';
import { DEFAULT_CONFIG, DEFAULT_OPT_VALUES, convertSchemaToParamDefs, getCrossOptUUID } from '../constants/strategies';

/**
 * useOptimization - Custom hook that encapsulates ALL optimization logic
 * extracted from StrategyView.jsx.
 *
 * Manages: heavy (large-scale) optimization,
 * optimization polling, result formatting, CSV export/download,
 * and per-tab optEnabled/optValues handling.
 */
export const useOptimization = ({
    currentConfig, selectedStrategy, configList, setConfigList,
    activeTab, savedSymbols, addLog,
    symbolCompareConfig, setSymbolCompareConfig,
    setIsDirty, setIsSymbolCompareDirty,
    selectedCompareSymbols, selectedProfileId, currentSymbol,
    exchangeName = DEFAULT_EXCHANGE,
}) => {
    // ========================================
    // Optimization State
    // ========================================
    const [isOptimizing, setIsOptimizing] = useState(false);
    const [optResults, setOptResults] = useState(null);
    const [optProgress, setOptProgress] = useState({ current: 0, total: 0 });
    const [optStatusMessage, setOptStatusMessage] = useState("");
    const [optError, setOptError] = useState(null);

    const [currentOptTaskId, setCurrentOptTaskId] = useState(null);
    const [completedOptTaskId, setCompletedOptTaskId] = useState(null); // For CSV download

    // Heavy Optimization State — per-tab map
    // { [tabKey]: { taskId, status, isRunning, results } }
    const [heavyOptByTab, setHeavyOptByTab] = useState({});
    const activeTabRef = useRef(activeTab);
    useEffect(() => { activeTabRef.current = activeTab; }, [activeTab]);

    // Keep savedSymbols ref fresh to avoid stale closures in polling callbacks
    const savedSymbolsRef = useRef(savedSymbols);
    useEffect(() => { savedSymbolsRef.current = savedSymbols; }, [savedSymbols]);

    // Resolve symbol name from latest savedSymbols (avoids stale closure)
    const resolveSymbolName = useCallback((symbolCode) => {
        return savedSymbolsRef.current?.find(s => s.code === symbolCode)?.name || '';
    }, []);

    // Derive current tab's heavy opt state
    const tabKey = String(activeTab);
    const currentTabOpt = heavyOptByTab[tabKey] || {};
    const heavyOptTaskId = currentTabOpt.taskId || null;
    const heavyOptStatus = currentTabOpt.status || null;
    const isHeavyOptRunning = currentTabOpt.isRunning || false;

    // Helper to update a specific tab's heavy opt state
    const updateTabHeavyOpt = useCallback((tab, updates) => {
        setHeavyOptByTab(prev => ({
            ...prev,
            [String(tab)]: { ...(prev[String(tab)] || {}), ...updates }
        }));
    }, []);

    // Sorting State
    const [sortConfig, setSortConfig] = useState({ key: 'rank', direction: 'asc' });

    // Pending opt result (for save/discard flow)
    const [pendingOptResult, setPendingOptResult] = useState(null);

    // Cancellation state
    const [isCancelling, setIsCancelling] = useState(false);

    // Execution mode: "standard" (sequential) or "fast" (parallel ProcessPool)
    const [executionMode, setExecutionMode] = useState("standard");

    // Custom alert modal state (replaces window.alert)
    const [optAlertModal, setOptAlertModal] = useState({ isOpen: false, title: '', message: '', type: 'warning' });

    // ========================================
    // Dynamic helpers (bound to current strategy)
    // ========================================
    const getDynamicDefaultConfig = () => buildDynamicDefaultConfig(selectedStrategy, currentSymbol, DEFAULT_CONFIG, exchangeName);
    const getDynamicOptValues = () => buildDynamicOptValues(selectedStrategy, DEFAULT_OPT_VALUES, getOptRangeDefaults(exchangeName));
    const getStrategyParamNames = () => extractParamNames(selectedStrategy?.parameter_schema);

    // ========================================
    // Sort Handler
    // ========================================
    const handleSort = (key) => {
        setSortConfig(current => ({
            key,
            direction: current.key === key && current.direction === 'asc' ? 'desc' : 'asc'
        }));
    };

    // ========================================
    // Opt Enable / Value Change Handlers
    // ========================================
    const handleOptEnableChange = (key, checked) => {
        const defaults = getDynamicOptValues();

        // Symbol Compare tab: store opt settings in symbolCompareConfig
        if (activeTab === -3) {
            setSymbolCompareConfig(prev => {
                const base = prev || configList[0] || getDynamicDefaultConfig();
                const updatedOptValues = { ...(base.optValues || {}) };
                // Auto-fill default opt range when enabling a parameter
                if (checked && !updatedOptValues[key] && defaults[key]) {
                    updatedOptValues[key] = defaults[key];
                }
                return { ...base, optEnabled: { ...(base.optEnabled || {}), [key]: checked }, optValues: updatedOptValues };
            });
            return;
        }
        if (activeTab === -1 || !configList[activeTab]) return;

        setConfigList(prev => {
            const next = [...prev];
            const currentCfg = next[activeTab];
            const updatedOptValues = { ...(currentCfg.optValues || {}) };
            // Auto-fill default opt range when enabling a parameter
            if (checked && !updatedOptValues[key] && defaults[key]) {
                updatedOptValues[key] = defaults[key];
            }
            next[activeTab] = {
                ...currentCfg,
                optEnabled: { ...(currentCfg.optEnabled || {}), [key]: checked },
                optValues: updatedOptValues
            };
            return next;
        });
    };

    const handleOptValueChange = (key, value) => {
        // Symbol Compare tab: store opt settings in symbolCompareConfig
        if (activeTab === -3) {
            setSymbolCompareConfig(prev => {
                const base = prev || configList[0] || getDynamicDefaultConfig();
                return { ...base, optValues: { ...getDynamicOptValues(), ...(base.optValues || {}), [key]: value } };
            });
            return;
        }
        if (activeTab === -1 || !configList[activeTab]) return;

        setConfigList(prev => {
            const next = [...prev];
            const currentCfg = next[activeTab];
            next[activeTab] = {
                ...currentCfg,
                optValues: { ...getDynamicOptValues(), ...(currentCfg.optValues || {}), [key]: value }
            };
            return next;
        });
    };

    // ========================================
    // Save / Discard Pending Optimization Results
    // ========================================
    const savePendingOptResult = async () => {
        if (!pendingOptResult) {
            addLog('No pending optimization results to save', 'warning');
            return;
        }
        try {
            await saveStrategyResult(pendingOptResult.tabUuid, 'optimization', pendingOptResult.data);
            addLog('\uD83D\uDCBE Optimization results saved to DB', 'info');
            setPendingOptResult(null);
        } catch (err) {
            console.error("Failed to save opt result", err);
            addLog('Failed to save optimization results', 'error');
        }
    };

    const discardPendingOptResult = () => {
        setPendingOptResult(null);
        addLog('\uD83D\uDDD1\uFE0F Optimization results discarded', 'info');
    };

    // ========================================
    // Export Optimization Results to CSV
    // ========================================
    const exportOptResultsToCSV = () => {
        if (!optResults || optResults.length === 0) {
            addLog('No optimization results to export', 'error');
            return;
        }

        const filename = exportOptCSV({
            results: optResults,
            strategy: selectedStrategy,
            currentConfig,
        });

        if (filename) {
            addLog(`Exported ${optResults.length} results to ${filename}`, 'success');
        }
    };

    // Download FULL optimization results from backend (all combinations, not just top 200)
    const downloadFullOptResultsCSV = () => {
        const taskId = heavyOptTaskId || currentConfig?.lastOptTaskId;
        if (!taskId) {
            addLog('No optimization task available for download', 'error');
            return;
        }

        window.open(getHeavyOptDownloadUrl(taskId), '_blank');
        addLog('Downloaded full optimization results (all combinations)', 'success');
    };

    // ========================================
    // Heavy Optimization Functions
    // ========================================
    const startHeavyOptimization = async () => {
        // Clear previous errors
        setOptError(null);

        if (!selectedStrategy) {
            setOptError("Please select a strategy first.");
            return;
        }
        if (activeTab === -1) {
            setOptError("Optimization not available for Integrated Portfolio.");
            return;
        }

        // Determine which tab type and get appropriate config/symbols
        const isSymbolCompareTab = activeTab === -3;
        const isRankTab = activeTab >= 0;

        // Get symbols based on tab type
        let symbols = [];
        if (isSymbolCompareTab) {
            if (selectedCompareSymbols.length === 0) {
                setOptError("Please select symbols for optimization.");
                return;
            }
            symbols = selectedCompareSymbols;
        } else if (isRankTab) {
            const symbol = currentConfig.symbol || currentSymbol;
            if (!symbol) {
                setOptError("No symbol selected.");
                return;
            }
            symbols = [symbol];
        }

        // Get config based on tab type
        const activeConfig = isSymbolCompareTab ? symbolCompareConfig : currentConfig;
        const activeOptEnabled = activeConfig?.optEnabled || {};
        const activeOptValues = { ...getDynamicOptValues(), ...(activeConfig?.optValues || {}) };
        // Filter: only allow keys that are actual strategy parameter names (guard against corrupted data)
        const validParamNames = new Set(getStrategyParamNames());
        const varyingKeys = Object.keys(activeOptEnabled).filter(k => activeOptEnabled[k] && validParamNames.has(k));

        // Warn about invalid keys
        const invalidKeys = Object.keys(activeOptEnabled).filter(k => activeOptEnabled[k] && !validParamNames.has(k));
        if (invalidKeys.length > 0) {
            addLog(`\u26A0\uFE0F Ignored invalid optEnabled keys: [${invalidKeys.join(', ')}] (not in strategy schema)`, 'warning');
        }

        const parameter_ranges = {};
        for (const key of varyingKeys) {
            const values = parseValues(activeOptValues[key]);
            if (values.length === 0) {
                setOptError(`Parameter '${key}' is enabled but has no values.`);
                return;
            }
            parameter_ranges[key] = values;
        }

        // Calculate total combinations
        const totalParams = Object.values(parameter_ranges).reduce((acc, arr) => acc * arr.length, 1);
        const totalCombos = symbols.length * totalParams;

        // Guard: block excessively large optimizations
        const MAX_COMBINATIONS = 100_000;
        if (totalCombos > MAX_COMBINATIONS) {
            setOptAlertModal({
                isOpen: true,
                title: '최적화 조합 수 초과',
                message: `조합 수가 ${totalCombos.toLocaleString()}개로 제한(${MAX_COMBINATIONS.toLocaleString()})을 초과합니다.\n\n심볼 수를 줄이거나 파라미터 범위를 좁혀 주세요.\n(${symbols.length} symbols × ${totalParams.toLocaleString()} params = ${totalCombos.toLocaleString()})`,
                type: 'error'
            });
            return;
        }

        const startTab = activeTab;
        updateTabHeavyOpt(startTab, {
            taskId: null, status: { status: 'initializing', message: 'Updating symbol data...' },
            isRunning: true, results: null
        });
        // Set appropriate dirty flag based on tab
        if (activeTab === -3) {
            setIsSymbolCompareDirty(true);
        } else {
            setIsDirty(true);
        }

        try {
            // Pre-fetch latest data for all symbols (incremental update only)
            const DATA_FETCH_DELAY_MS = 500;
            addLog(`Updating data for ${symbols.length} symbol(s) before optimization...`, 'info');
            for (let i = 0; i < symbols.length; i++) {
                const sym = symbols[i];
                updateTabHeavyOpt(startTab, {
                    status: { status: 'initializing', message: `Updating data (${i + 1}/${symbols.length}): ${sym}...` }
                });
                try {
                    await fetchMarketDataForSymbol(sym, {
                        interval: activeConfig?.interval || "1m",
                        days: activeConfig?.days || getDefaultDays(exchangeName),
                        exchange_name: exchangeName
                    });
                } catch (err) {
                    console.warn(`Failed to update data for ${sym}`, err);
                    addLog(`${sym}: data update failed`, 'warning');
                }
                if (i < symbols.length - 1) {
                    await new Promise(resolve => setTimeout(resolve, DATA_FETCH_DELAY_MS));
                }
            }
            addLog('Data update completed. Starting optimization...', 'info');
            updateTabHeavyOpt(startTab, {
                status: { status: 'initializing', message: 'Starting optimization...' }
            });

            // Build base config
            const base_config = {};
            const paramDefs = convertSchemaToParamDefs(selectedStrategy?.parameter_schema);
            paramDefs.forEach(param => {
                if (param.defaultValue !== undefined) {
                    base_config[param.key] = param.defaultValue;
                }
            });
            Object.keys(activeConfig || {}).forEach(key => {
                if (activeConfig[key] !== undefined && activeConfig[key] !== '') {
                    base_config[key] = activeConfig[key];
                }
            });

            // Determine save target
            const saveTabId = isSymbolCompareTab
                ? getCrossOptUUID(selectedProfileId)
                : (activeConfig?.uuid || null);

            const defaultToDate = new Date(Date.now() - 86400000).toISOString().split('T')[0];
            const payload = {
                symbols: symbols,
                interval: activeConfig?.interval || "1m",
                days: activeConfig?.days || getDefaultDays(exchangeName),
                from_date: activeConfig?.from_date || null,
                to_date: activeConfig?.to_date || defaultToDate,
                initial_capital: activeConfig?.initial_capital || getDefaultCapital(exchangeName),
                parameter_ranges: parameter_ranges,
                base_config: base_config,
                strategy_id: selectedStrategy.id,
                tab_id: saveTabId,  // Auto-save to DB on completion
                tab_key: String(startTab),  // Per-tab tracking
                execution_mode: executionMode,  // "standard" or "fast" (parallel)
                exchange_name: exchangeName  // 프로필 계좌 기반 거래소
            };

            // Log optimization request details
            addLog(`\uD83D\uDCCA Optimization Request:`, 'info');
            addLog(`  - Symbols: ${symbols.length}\uAC1C`, 'info');
            addLog(`  - Parameter Ranges:`, 'info');
            Object.entries(parameter_ranges).forEach(([key, values]) => {
                addLog(`    \u2022 ${key}: [${values.join(', ')}] (${values.length}\uAC1C)`, 'info');
            });
            const paramCombos = Object.values(parameter_ranges).reduce((acc, arr) => acc * arr.length, 1);
            addLog(`  - Total: ${symbols.length} \u00D7 ${paramCombos} = ${symbols.length * paramCombos} combinations`, 'info');

            const heavyOptData = await apiStartHeavyOpt(selectedStrategy.id, payload);

            if (heavyOptData.task_id) {
                const taskId = heavyOptData.task_id;
                updateTabHeavyOpt(startTab, { taskId });
                addLog(`Optimization started: ${heavyOptData.total_combinations} combinations`, 'info');

                // Start polling
                pollHeavyOptStatus(taskId, startTab);
            }
        } catch (error) {
            const msg = error.response?.data?.detail || error.message || "Unknown Error";
            setOptError(`Optimization failed: ${msg}`);
            updateTabHeavyOpt(startTab, { isRunning: false, status: null });
        }
    };

    // ========================================
    // Format heavy opt top_results into display format
    // ========================================
    const formatHeavyOptResults = useCallback((topResults, isPartial = false) => {
        return topResults.map((item, index) => ({
            ...item.config,
            symbol: item.symbol || '',
            symbolName: resolveSymbolName(item.symbol),
            return: item.total_return,
            win_rate: item.win_rate,
            recent_10_win_rate: item.recent_10_win_rate,
            trades: item.total_trades,
            score: item.score,
            full_config: item.config,
            rank: index + 1,
            max_drawdown: item.max_drawdown,
            profit_factor: item.profit_factor,
            sharpe_ratio: item.sharpe_ratio,
            avg_pnl: item.avg_pnl,
            stability_score: item.stability_score,
            acceleration_score: item.acceleration_score,
            activity_rate: item.activity_rate,
            avg_holding_time: item.avg_holding_time,
            max_holding_time: item.max_holding_time,
            min_holding_time: item.min_holding_time,
            max_profit: item.max_profit,
            max_loss: item.max_loss,
            total_days: item.total_days,
            ...(isPartial ? { _isPartial: true } : {})
        }));
    }, [resolveSymbolName]);

    // ========================================
    // Heavy Optimization Polling (per-tab aware)
    // ========================================
    const pollHeavyOptStatus = async (taskId, forTab) => {
        let isComplete = false;

        while (!isComplete) {
            await new Promise(resolve => setTimeout(resolve, 2000)); // Poll every 2s

            try {
                const data = await getHeavyOptimizationStatus(taskId);
                const isCurrentTab = String(forTab) === String(activeTabRef.current);

                // Update per-tab state
                updateTabHeavyOpt(forTab, { status: data });

                // Show partial results during running
                if (data.status === 'running' && data.top_results && data.top_results.length > 0) {
                    const formattedPartial = formatHeavyOptResults(data.top_results, true);
                    updateTabHeavyOpt(forTab, { results: formattedPartial });
                    if (isCurrentTab) setOptResults(formattedPartial);
                }

                if (data.status === 'completed' || data.status === 'cancelled' || data.status === 'failed' || data.status === 'not_found') {
                    isComplete = true;
                    updateTabHeavyOpt(forTab, { isRunning: false });

                    if (data.status === 'completed') {
                        addLog(`Optimization completed! ${data.progress_current} results processed.`, 'info');
                        if (data.top_results && data.top_results.length > 0) {
                            const formattedResults = formatHeavyOptResults(data.top_results);
                            updateTabHeavyOpt(forTab, { results: formattedResults });
                            if (isCurrentTab) setOptResults(formattedResults);
                        }
                        // Persist task_id to config for recalculate after refresh
                        const tabIdx = parseInt(forTab, 10);
                        if (isNaN(tabIdx) || tabIdx < 0) {
                            // Symbol Compare tab (-3)
                            setSymbolCompareConfig(prev => prev ? { ...prev, lastOptTaskId: taskId } : prev);
                        } else {
                            setConfigList(prev => {
                                const next = [...prev];
                                if (next[tabIdx]) {
                                    next[tabIdx] = { ...next[tabIdx], lastOptTaskId: taskId };
                                }
                                return next;
                            });
                        }
                    } else if (data.status === 'cancelled') {
                        addLog('Optimization cancelled.', 'warning');
                    } else if (data.status === 'failed') {
                        setOptError(`Heavy optimization failed: ${data.message}`);
                    } else if (data.status === 'not_found') {
                        setOptError('Optimization task not found (server restarted?)');
                        updateTabHeavyOpt(forTab, { taskId: null });
                    }
                }
            } catch (err) {
                console.warn("Heavy opt polling error", err);
                // Continue polling on network error
            }
        }
    };

    // ========================================
    // Cancel / Download / Clear Heavy Opt
    // ========================================
    const handleCancelHeavyOpt = async () => {
        if (!heavyOptTaskId) return;

        try {
            await cancelHeavyOptimization(heavyOptTaskId);
            addLog('Optimization cancellation requested.', 'info');
        } catch (e) {
            console.error("Heavy opt cancellation failed", e);
            setOptError("Failed to cancel optimization");
        }
    };

    const downloadHeavyOptCSV = () => {
        if (!heavyOptStatus?.csv_file) return;
        window.open(getHeavyOptDownloadUrl(heavyOptTaskId), '_blank');
    };

    const clearHeavyOptTask = () => {
        setHeavyOptByTab(prev => {
            const next = { ...prev };
            delete next[String(activeTab)];
            return next;
        });
    };

    // ========================================
    // Restore heavy opt from server when profile changes
    // ========================================
    useEffect(() => {
        if (!selectedProfileId) return;
        // Skip if any tab already has a running task (started in this session)
        const anyRunning = Object.values(heavyOptByTab).some(t => t.isRunning);
        if (anyRunning) return;

        // Collect all tab UUIDs from configList
        const tabIds = (configList || []).map(c => c.uuid).filter(Boolean);
        if (tabIds.length === 0) return;

        listHeavyOptimizationTasks(tabIds)
            .then(({ tasks }) => {
                // Restore all tasks to their respective tabs
                tasks.forEach(task => {
                    const taskTab = task.tab_key;
                    if (!taskTab) return; // Skip tasks without tab_key (legacy)

                    if (task.status === 'running' || task.status === 'initializing') {
                        updateTabHeavyOpt(taskTab, { taskId: task.task_id, isRunning: true });
                        // Fetch full status and start polling
                        getHeavyOptimizationStatus(task.task_id)
                            .then(data => {
                                updateTabHeavyOpt(taskTab, { status: data });
                                if (String(taskTab) === String(activeTabRef.current) && data.top_results?.length > 0) {
                                    setOptResults(formatHeavyOptResults(data.top_results, true));
                                }
                                pollHeavyOptStatus(task.task_id, taskTab);
                            })
                            .catch(() => {
                                updateTabHeavyOpt(taskTab, { taskId: null, isRunning: false });
                            });
                    } else if (task.status === 'completed') {
                        updateTabHeavyOpt(taskTab, { taskId: task.task_id });
                        getHeavyOptimizationStatus(task.task_id)
                            .then(data => {
                                updateTabHeavyOpt(taskTab, { status: data });
                                if (data.top_results?.length > 0) {
                                    const results = formatHeavyOptResults(data.top_results);
                                    updateTabHeavyOpt(taskTab, { results });
                                    if (String(taskTab) === String(activeTabRef.current)) {
                                        setOptResults(results);
                                    }
                                }
                            })
                            .catch(() => {});
                    }
                });
            })
            .catch(() => {});
    }, [selectedProfileId]);

    // ========================================
    // Swap optResults when switching tabs
    // ========================================
    useEffect(() => {
        const currentOpt = heavyOptByTab[String(activeTab)];
        if (currentOpt?.results) {
            setOptResults(currentOpt.results);
        } else if (currentOpt?.taskId) {
            // Tab has heavy opt but no results yet (initializing)
            setOptResults(null);
        }
        // If no heavy opt on this tab, don't touch optResults (may have regular opt results)
    }, [activeTab]);

    // ========================================
    // Apply Optimization Parameters to Config
    // ========================================
    const applyOptParams = (result) => {
        // Find the active tab's config and update it
        if (activeTab >= 0 && configList[activeTab]) {
            setConfigList(prev => {
                const next = [...prev];
                next[activeTab] = { ...next[activeTab], ...result.full_config };
                return next;
            });
        }
        // Scroll to config
        window.scrollTo({ top: 0, behavior: 'smooth' });
    };

    // ========================================
    // Reset all optimization state (for profile change)
    // ========================================
    const resetOptState = useCallback(() => {
        setOptResults(null);
        setPendingOptResult(null);
        setIsOptimizing(false);
        setOptProgress({ current: 0, total: 0 });
        setOptStatusMessage("");
        setOptError(null);
        setCompletedOptTaskId(null);
        setCurrentOptTaskId(null);
        setIsCancelling(false);
        setHeavyOptByTab({});
    }, []);

    // ========================================
    // Return all state and handlers
    // ========================================
    return {
        // State
        optResults,
        setOptResults,
        optProgress,
        optError,
        setOptError,
        isOptimizing,
        sortConfig,
        heavyOptTaskId,
        heavyOptStatus,
        pendingOptResult,
        setPendingOptResult,
        completedOptTaskId,
        currentOptTaskId,
        isCancelling,
        isHeavyOptRunning,
        optStatusMessage,
        executionMode,
        optAlertModal,
        setOptAlertModal,

        // Handlers
        setExecutionMode,
        startHeavyOptimization,
        handleCancelHeavyOpt,
        handleSort,
        exportOptResultsToCSV,
        downloadFullOptResultsCSV,
        applyOptParams,
        savePendingOptResult,
        discardPendingOptResult,
        downloadHeavyOptCSV,
        clearHeavyOptTask,
        handleOptEnableChange,
        handleOptValueChange,
        resetOptState,
    };
};
