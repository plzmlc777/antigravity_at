import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar, Cell, ReferenceLine, ComposedChart, LabelList } from 'recharts';
import Card from '../components/common/Card';
import SymbolSelector from '../components/SymbolSelector';
import IntegratedAnalysis from '../components/IntegratedAnalysis';
import VisualBacktestChart from '../components/VisualBacktestChart';
import { saveStrategyResult, getStrategyResults, runIntegratedBacktest } from '../api/client';
import ConfirmModal from '../components/ConfirmModal'; // Custom Modal

const generateUUID = () => {
    if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID();
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
        var r = Math.random() * 16 | 0, v = c == 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
};

// Defined outside component to prevent re-creation
const PARAM_DEFINITIONS = [
    {
        key: 'start_time',
        label: 'Start Time',
        type: 'select',
        options: Array.from({ length: 14 }).map((_, i) => {
            const h = 9 + Math.floor(i / 2);
            const m = i % 2 === 0 ? "00" : "30";
            return `${h.toString().padStart(2, '0')}:${m}`;
        }),
        placeholder: '09:00, 09:30'
    },
    { key: 'delay_minutes', label: 'Delay (min)', type: 'number', placeholder: '5, 10, 15' },
    { key: 'direction', label: 'Direction', type: 'select', options: ['rise', 'fall'], placeholder: 'rise, fall' },
    { key: 'target_percent', label: 'Target (%)', type: 'number', placeholder: '1, 2, 3' },
    { key: 'safety_stop_percent', label: 'Stop Loss (%)', type: 'number', placeholder: '2, 3, 5' },
    { key: 'trailing_start_percent', label: 'Trail Start (%)', type: 'number', placeholder: '3, 5' },
    { key: 'trailing_stop_drop', label: 'Trail Drop (%)', type: 'number', placeholder: '1, 2' },
    {
        key: 'stop_time',
        label: 'Stop Time',
        type: 'select',
        options: Array.from({ length: 48 }).map((_, i) => {
            const h = Math.floor(i / 2);
            const m = i % 2 === 0 ? "00" : "30";
            return `${h.toString().padStart(2, '0')}:${m}`;
        }),
        placeholder: '15:00, 15:20'
    }
];

const DEFAULT_CONFIG = {
    start_time: "09:00",
    delay_minutes: 60,
    direction: "fall",
    target_percent: 0.2,
    safety_stop_percent: 10,
    trailing_start_percent: 1,
    trailing_stop_percent: 0,
    stop_time: "15:00",
    initial_capital: 10000000,
    from_date: "",
    interval: "1m",
    symbol: "233740",
    betting_strategy: "fixed",
    uuid: null // Will be generated
};

// Constant UUID for Integrated View Persistence
const INTEGRATED_UUID = 'integrated-view-persistence-id';

const StrategyView = () => {
    // Symbol State
    const [currentSymbol, setCurrentSymbol] = useState(() => localStorage.getItem('lastSymbol') || '005930');
    const [savedSymbols, setSavedSymbols] = useState(() => {
        const saved = localStorage.getItem('savedSymbols');
        if (!saved) return [{ code: '005930', name: '삼성전자' }, { code: '000660', name: 'SK하이닉스' }];
        try {
            return JSON.parse(saved);
        } catch {
            return [{ code: '005930', name: '삼성전자' }, { code: '000660', name: 'SK하이닉스' }];
        }
    });

    const [strategies, setStrategies] = useState([]);
    const [selectedStrategy, setSelectedStrategy] = useState(null);
    const [backtestResult, setBacktestResult] = useState(null);
    const [isGenerating, setIsGenerating] = useState(false);
    const [aiPrompt, setAiPrompt] = useState("");
    const [isLoading, setIsLoading] = useState(false);
    const [showChart, setShowChart] = useState(false); // Toggle for Visual Chart
    const [activeDropdown, setActiveDropdown] = useState(null); // Key of the currently open optimization dropdown

    // Integrated Analysis State - Added for v0.8.7
    const [showIntegratedAnalysis, setShowIntegratedAnalysis] = useState(false);
    const [integratedResults, setIntegratedResults] = useState(null);
    const [selectedVisualSymbol, setSelectedVisualSymbol] = useState(null); // For Multi-Symbol Analysis

    // Dynamic Config State
    // Dynamic Config State (Refactored for Multi-Symbol Tabs)
    const [configList, setConfigList] = useState([]); // Array of config objects
    const [activeTab, setActiveTab] = useState(() => {
        const saved = localStorage.getItem('strategyViewActiveTab');
        return saved !== null ? parseInt(saved, 10) : 0;
    });

    useEffect(() => {
        localStorage.setItem('strategyViewActiveTab', activeTab);
    }, [activeTab]);
    const [isConfigLoaded, setIsConfigLoaded] = useState(false);

    // Backtest Settings
    // const [fromDate, setFromDate] = useState(""); // YYYY-MM-DD
    // const [initialCapital, setInitialCapital] = useState(() => {
    //    const saved = localStorage.getItem('initialCapital');
    //    return saved ? parseInt(saved, 10) : 10000000;
    // });


    // Custom Confirmation Modal State
    const [confirmModal, setConfirmModal] = useState({
        isOpen: false,
        title: "",
        message: "",
        onConfirm: null,
        isDanger: false
    });

    const requestConfirm = (title, message, onConfirm, isDanger = false) => {
        setConfirmModal({
            isOpen: true,
            title,
            message,
            onConfirm,
            isDanger
        });
    };

    // Save to LocalStorage
    useEffect(() => {
        localStorage.setItem('lastSymbol', currentSymbol);
    }, [currentSymbol]);

    useEffect(() => {
        localStorage.setItem('savedSymbols', JSON.stringify(savedSymbols));
    }, [savedSymbols]);

    // Persistence logic removed for initialCapital

    // Load Strategy Config List on Selection
    useEffect(() => {
        if (selectedStrategy) {
            const storageKey = `strategyConfig_${selectedStrategy.id}_v2`; // New Key
            const legacyKey = `strategyConfig_${selectedStrategy.id}`; // Old Key

            const savedList = localStorage.getItem(storageKey);

            if (savedList) {
                try {
                    const parsed = JSON.parse(savedList);
                    if (Array.isArray(parsed) && parsed.length > 0) {
                        // Migration: Ensure UUIDs exist and Merge Defaults
                        let needsUpdate = false;
                        const migratedList = parsed.map(cfg => {
                            // Merge with DEFAULT_CONFIG first
                            let mergedCfg = { ...DEFAULT_CONFIG, ...cfg };
                            let hasSanitized = false;

                            // Sanitization: Ensure empty strings don't override defaults for numeric/select fields
                            // Exception: from_date can be empty (uuid handled separately)
                            Object.keys(DEFAULT_CONFIG).forEach(key => {
                                if (key === 'from_date' || key === 'uuid') return; // Allow empty

                                const val = mergedCfg[key];
                                const defaultVal = DEFAULT_CONFIG[key];

                                // If loaded value is empty string or null/undefined, and default is not, revert to default
                                if ((val === "" || val === null || val === undefined) && defaultVal !== "") {
                                    mergedCfg[key] = defaultVal;
                                    hasSanitized = true;
                                }
                            });

                            if (!mergedCfg.uuid) {
                                needsUpdate = true;
                                mergedCfg.uuid = generateUUID();
                            }
                            if (hasSanitized) {
                                needsUpdate = true;
                            }

                            return mergedCfg;
                        });

                        setConfigList(migratedList);

                        if (needsUpdate) {
                            // Immediate save to correct the storage
                            localStorage.setItem(storageKey, JSON.stringify(migratedList));
                            console.log("Sanitized and updated config in localStorage");
                        }
                    } else {
                        // Fallback if parsing failed or empty
                        initDefaultList();
                    }
                } catch {
                    initDefaultList();
                }
            } else {
                // Migration: Check for legacy single config
                const legacy = localStorage.getItem(legacyKey);
                if (legacy) {
                    try {
                        const parsedLegacy = JSON.parse(legacy);

                        // Merge & Sanitize Logic (Duplicate of above for safety)
                        let mergedCfg = { ...DEFAULT_CONFIG, ...parsedLegacy };
                        Object.keys(DEFAULT_CONFIG).forEach(key => {
                            if (key === 'from_date' || key === 'uuid' || key === 'symbol') return;
                            const val = mergedCfg[key];
                            const defaultVal = DEFAULT_CONFIG[key];
                            if ((val === "" || val === null || val === undefined) && defaultVal !== "") {
                                mergedCfg[key] = defaultVal;
                            }
                        });


                        const migrated = [{
                            ...mergedCfg,
                            is_active: true,
                            tabName: "Rank 1",
                            uuid: generateUUID()
                        }];
                        setConfigList(migrated);

                    } catch {
                        initDefaultList();
                    }
                } else {
                    initDefaultList();
                }
            }
            setIsConfigLoaded(true);
        }
    }, [selectedStrategy]);

    const initDefaultList = () => {
        setConfigList([{
            ...DEFAULT_CONFIG,
            is_active: true,
            tabName: "Rank 1",
            uuid: generateUUID(),
            optEnabled: {},
            optValues: { ...DEFAULT_OPT_VALUES }
        }]);

    };

    // Save Strategy Config List on Change
    useEffect(() => {
        if (isConfigLoaded && selectedStrategy && configList.length > 0) {
            localStorage.setItem(`strategyConfig_${selectedStrategy.id}_v2`, JSON.stringify(configList));
        }
    }, [configList, selectedStrategy, isConfigLoaded]);

    const moveRankTab = (index, direction, e) => {
        if (e) e.stopPropagation(); // Prevent tab selection
        if (activeTab === -1) return;

        const targetIndex = index + direction;

        // Boundary Checks
        if (targetIndex < 0 || targetIndex >= configList.length) return;

        // Ensure both are Active (Rank) tabs. Rank tabs are always at the start.
        if (configList[index].is_active === false || configList[targetIndex].is_active === false) return;

        setConfigList(prev => {
            const next = [...prev];
            // Swap objects
            const temp = next[index];
            next[index] = next[targetIndex];
            next[targetIndex] = temp;

            // Regenerate tabNames to keep them consistent with position
            let rankCount = 0;
            let draftCount = 0;
            return next.map(cfg => {
                const newCfg = { ...cfg }; // Clone
                if (newCfg.is_active !== false) {
                    rankCount++;
                    newCfg.tabName = `Rank ${rankCount}`;
                } else {
                    draftCount++;
                    newCfg.tabName = `Draft ${draftCount}`;
                }
                return newCfg;
            });
        });

        // Update Active Tab to follow the moved item
        if (activeTab === index) {
            setActiveTab(targetIndex);
        } else if (activeTab === targetIndex) {
            setActiveTab(index);
        }
    };

    const removeRankTab = (index, e) => {
        if (e) e.stopPropagation();

        if (configList.length <= 1) {
            alert("At least one strategy tab is required.");
            return;
        }

        requestConfirm(
            "Delete Strategy Tab",
            "Are you sure you want to delete this strategy tab? This action cannot be undone and all configuration in this tab will be lost.",
            () => {
                const newList = [...configList];
                newList.splice(index, 1);

                // Re-label Tabs
                let rankCount = 0;
                let draftCount = 0;
                const reLabeledList = newList.map(cfg => {
                    const newCfg = { ...cfg };
                    if (newCfg.is_active !== false) {
                        rankCount++;
                        newCfg.tabName = `Rank ${rankCount}`;
                    } else {
                        draftCount++;
                        newCfg.tabName = `Draft ${draftCount}`;
                    }
                    return newCfg;
                });

                setConfigList(reLabeledList);

                // Adjust Active Tab
                if (activeTab === index) {
                    const newActive = Math.max(0, index - 1);
                    setActiveTab(newActive);
                } else if (activeTab > index) {
                    setActiveTab(activeTab - 1);
                }
            },
            true // isDanger
        );
    };

    const handleConfigChange = (key, value) => {
        if (activeTab === -1) return; // Cannot edit in Integrated View

        const newList = [...configList];
        // Ensure we don't start with partial object if configList[activeTab] is missing
        const currentItem = newList[activeTab] || { ...DEFAULT_CONFIG, is_active: true, tabName: `Rank ${activeTab + 1}` };
        const targetConfig = { ...currentItem, [key]: value };
        newList[activeTab] = targetConfig;

        // Dynamic Sorting if 'is_active' changes
        if (key === 'is_active') {
            // Mark the item to track its new position
            targetConfig._temp_tracking_id = Date.now();

            // Sort: Active First (true or undefined), then Draft (false)
            newList.sort((a, b) => {
                const aActive = a.is_active !== false;
                const bActive = b.is_active !== false;
                if (aActive === bActive) return 0;
                return aActive ? -1 : 1;
            });

            // Re-label Tabs
            let rankCount = 0;
            let draftCount = 0;
            newList.forEach((cfg, idx) => {
                // Clone to avoid mutating state
                const newCfg = { ...cfg };
                newList[idx] = newCfg;

                const isActive = newCfg.is_active !== false;
                if (isActive) {
                    rankCount++;
                    newCfg.tabName = `Rank ${rankCount}`;
                } else {
                    draftCount++;
                    newCfg.tabName = `Draft ${draftCount}`;
                }
            });

            // Update Active Tab Index to follow the item
            const newIndex = newList.findIndex(item => item._temp_tracking_id === targetConfig._temp_tracking_id);
            if (newIndex !== -1) {
                delete newList[newIndex]._temp_tracking_id;
                setActiveTab(newIndex);
            }
        }

        setConfigList(newList);
    };

    // Helper to get current config for UI rendering
    const currentConfig = (activeTab >= 0 && configList[activeTab]) ? configList[activeTab] : DEFAULT_CONFIG;

    // Check Symbol Validity for UI
    const activeSymbol = currentConfig?.symbol || currentSymbol;
    const isSymbolValid = !!activeSymbol && activeSymbol.trim().length > 0;


    // 3. Persistence: Load Results when switching tabs
    useEffect(() => {
        // Reset transient states
        setShowChart(false);
        setIsOptimizing(false);
        setIsCancelling(false);



        // Restore Results on Tab Change

        // If not loaded yet, wait
        if (!isConfigLoaded) return;

        let targetUUID = null;

        if (activeTab === -1) {
            targetUUID = INTEGRATED_UUID;
        } else {
            targetUUID = configList[activeTab]?.uuid;
        }

        if (!targetUUID) {
            // Should not happen for activeTab !== -1 if configList is valid
            // But if it is -1, we use constant.
            if (activeTab !== -1) {
                console.warn('[Persistence] Skipping restore: No UUID for tab', activeTab);
                return;
            }
        }

        const restoreResults = async () => {
            console.log(`[Persistence] Restoring Results for UUID: ${targetUUID} (Tab ${activeTab})`);

            // Clear valid results temporarily to show transition (optional, maybe keep stale?)
            // Clearing is safer to avoid confusion.
            setBacktestResult(null);
            setOptResults(null);
            setBacktestStatus({ status: 'idle', message: 'Restoring history...' });

            try {
                const data = await getStrategyResults(targetUUID);
                console.log('[Persistence] Data Received:', data);

                // Restore Backtest
                if (data.backtest) {
                    console.log('[Persistence] Restoring Backtest Data');
                    setBacktestResult(data.backtest);
                    if (activeTab === -1) {
                        setIntegratedResults(data.backtest);
                    }
                    setBacktestStatus({ status: 'success', message: 'Result Restored' });
                } else {
                    console.log('[Persistence] No Backtest Data found');
                    setBacktestStatus({ status: 'idle', message: 'Ready to Backtest' });
                }

                // Restore Optimization
                if (data.optimization && data.optimization.results) {
                    console.log('[Persistence] Restoring Optimization Data');
                    const formattedResults = data.optimization.results.map(item => ({
                        rank: item.rank,
                        ...(item.config || {}),
                        return: item.total_return,
                        win_rate: item.win_rate,
                        trades: item.total_trades,
                        score: item.score,
                        full_config: item.config || {},
                        ...(item.metrics || {}) // Flatten metrics
                    }));
                    setOptResults(formattedResults);
                } else if (data.optimization) {
                    // Fallback if data structure is unexpected
                    console.warn('[Persistence] Unexpected Opt Data Structure', data.optimization);
                    if (Array.isArray(data.optimization)) {
                        setOptResults(data.optimization);
                    }
                }
            } catch (e) {
                console.error("[Persistence] Failed to restore results", e);
                setBacktestStatus({ status: 'idle', message: 'Ready to Backtest' });
            }
        };

        restoreResults();
    }, [activeTab, isConfigLoaded]); // Only re-run when switching tabs, not editing config

    // 4. Persistence & Initialization
    useEffect(() => {
        fetchStrategies();
    }, []);

    const fetchStrategies = async () => {
        try {
            const res = await axios.get('/api/v1/strategies/list');
            setStrategies(res.data);

            if (res.data.length > 0) {
                // Try to restore last selected strategy
                const savedId = localStorage.getItem('lastStrategyId');
                let target = null;

                if (savedId) {
                    target = res.data.find(s => s.id === savedId);
                }

                // Fallback to first if saved not found or not set
                if (!target) {
                    target = res.data[0];
                }

                setSelectedStrategy(target);
            }
        } catch (e) {
            console.error(e);
        }
    };

    // Auto-Fetch Symbol Name if Missing
    useEffect(() => {
        const target = savedSymbols.find(s => s.code === currentSymbol);
        if (target && !target.name) {
            // Debounce or just fetch
            axios.get(`/api/v1/market-data/info/${currentSymbol}`)
                .then(res => {
                    if (res.data.name && res.data.name !== currentSymbol) {
                        setSavedSymbols(prev => prev.map(s =>
                            s.code === currentSymbol ? { ...s, name: res.data.name } : s
                        ));
                    }
                })
                .catch(err => console.error("Failed to fetch symbol name", err));
        }
    }, [currentSymbol, savedSymbols]);

    const [backtestStatus, setBacktestStatus] = useState({ status: 'idle', message: 'Ready to Backtest' });

    const runBacktest = async (strategyId) => {
        if (!selectedStrategy) return;
        if (activeTab === -1) {
            setBacktestStatus({ status: 'error', message: 'Backtest not available for Integrated Portfolio yet.' });
            return;
        }

        setIsLoading(true);
        setBacktestStatus({ status: 'running', message: 'Initializing Strategy...' });
        setBacktestResult(null); // Clear previous results
        setShowChart(false);

        try {
            // --- Single Symbol Backtest (Legacy) ---
            // Sanitize Config: Replace empty strings with defaults
            const cleanConfig = { ...currentConfig }; // Use currentConfig aka activeTab
            Object.keys(cleanConfig).forEach(key => {
                if (cleanConfig[key] === '' && DEFAULT_CONFIG[key] !== undefined) {
                    cleanConfig[key] = DEFAULT_CONFIG[key];
                }
            });

            const payload = {
                symbol: currentConfig.symbol || currentSymbol, // Use config's symbol if available, else global
                from_date: currentConfig?.from_date || "",
                initial_capital: currentConfig?.initial_capital || 10000000,
                interval: currentConfig?.interval || "1m",
                config: cleanConfig
            };

            setBacktestStatus({ status: 'running', message: `Running Backtest on ${currentConfig.symbol || currentSymbol}...` });

            const res = await axios.post(`/api/v1/strategies/${strategyId}/backtest`, payload);
            setBacktestResult(res.data);
            setBacktestStatus({ status: 'success', message: 'Backtest Completed' });

            // Persistence
            if (currentConfig.uuid) {
                saveStrategyResult(currentConfig.uuid, 'backtest', res.data).catch(err => console.error("Failed to save backtest result", err));
            }

        } catch (e) {
            console.error(e);
            let errorMsg = "Backtest Failed";
            if (e.response && e.response.data && e.response.data.detail) {
                errorMsg = `Error: ${e.response.data.detail}`;
            } else if (e.message) {
                errorMsg = `Error: ${e.message}`;
            }
            setBacktestStatus({ status: 'error', message: errorMsg });
        } finally {
            setIsLoading(false);
        }
    };

    const handleAiGenerate = async () => {
        if (!aiPrompt) return;
        setIsGenerating(true);
        try {
            const res = await axios.post('/api/v1/strategies/generate', { prompt: aiPrompt });
            setStrategies([...strategies, res.data]);
            setSelectedStrategy(res.data);
            setAiPrompt("");
        } catch (e) {
            alert("Generation failed");
        } finally {
            setIsGenerating(false);
        }
    };

    // ... (Data Management logic stays here) ...
    // Note: Implicitly preserving the gap where lines 106-175 were, but current ReplaceFileContent needs context.
    // The previous block ended at handleAiGenerate (around line 103). 
    // I need to be careful not to overwrite the data management hooks if I use a large range.
    // So I will only replace runBacktest and the render part separately? 
    // No, I can replace runBacktest first, then the render part.

    // WAIT, I need to insert the state definition too. 
    // It's safer to do 2 chunks: one for state+function, one for render.
    // Let's split this tool call into 2 chunks.


    // 5. Data Management & Persistence State
    const [dataStatus, setDataStatus] = useState({ is_fresh: false, last_updated: null, count: 0 });
    const [isFetchingData, setIsFetchingData] = useState(false);
    // const [currentInterval, setCurrentInterval] = useState(() => localStorage.getItem('lastInterval') || "1m");
    const [fetchMessage, setFetchMessage] = useState(null);

    // 6. Optimization State

    // 6. Optimization State
    const [isOptimizing, setIsOptimizing] = useState(false);
    const [optResults, setOptResults] = useState(null);
    const [optProgress, setOptProgress] = useState({ current: 0, total: 0 });
    const [optError, setOptError] = useState(null);

    // State for Dynamic Optimization
    // Refactored to Per-Tab Config (Legacy Global State Removed)

    // DEFAULT_OPT_VALUES constant defined below...
    const DEFAULT_OPT_VALUES = {
        start_time: "09:00",
        delay_minutes: "30, 60",
        direction: "fall, rise",
        target_percent: "0, 0.2, 1, 1.5, 3",
        safety_stop_percent: "5, 10",
        trailing_start_percent: "0.5, 1, 2, 4",
        trailing_stop_drop: "0, 0.5, 1, 2",
        stop_time: "15:00"
    };

    const handleOptEnableChange = (key, checked) => {
        if (activeTab === -1 || !configList[activeTab]) return;

        setConfigList(prev => {
            const next = [...prev];
            const currentCfg = next[activeTab];
            next[activeTab] = {
                ...currentCfg,
                optEnabled: { ...(currentCfg.optEnabled || {}), [key]: checked }
            };
            return next;
        });
    };

    const handleOptValueChange = (key, value) => {
        if (activeTab === -1 || !configList[activeTab]) return;

        setConfigList(prev => {
            const next = [...prev];
            const currentCfg = next[activeTab];
            next[activeTab] = {
                ...currentCfg,
                optValues: { ...(currentCfg.optValues || DEFAULT_OPT_VALUES), [key]: value }
            };
            return next;
        });
    };

    const [currentOptTaskId, setCurrentOptTaskId] = useState(null);

    // Sorting State
    const [sortConfig, setSortConfig] = useState({ key: 'rank', direction: 'asc' });

    const handleSort = (key) => {
        setSortConfig(current => ({
            key,
            direction: current.key === key && current.direction === 'asc' ? 'desc' : 'asc'
        }));
    };

    // Helper: Parse parameter string
    const parseValues = (valStr) => {
        if (!valStr) return [];
        return valStr.split(',').map(v => {
            const trimmed = v.trim();
            // Fix: Do not parse as number if it looks like a time string (has colon)
            if (trimmed.includes(':')) return trimmed;

            const num = parseFloat(trimmed);
            return isNaN(num) ? trimmed : num;
        }).filter(v => v !== "");
    };

    const [isCancelling, setIsCancelling] = useState(false);

    const cancelOptimization = async (taskId) => {
        if (!taskId) return;
        setIsCancelling(true);
        try {
            await axios.post(`/api/v1/strategies/optimize/cancel/${taskId}`);
            // UI update handled by polling
        } catch (e) {
            console.error("Cancellation failed", e);
            setOptError("Failed to cancel optimization");
            setIsCancelling(false);
        }
    };

    const runOptimization = async () => {
        if (!selectedStrategy) {
            setOptError("Please select a strategy first.");
            return;
        }
        if (activeTab === -1) {
            setOptError("Optimization not available for Integrated Portfolio yet.");
            return;
        }

        // Validation: Check for empty optimization inputs
        const currentOptEnabled = currentConfig.optEnabled || {};
        const currentOptValues = currentConfig.optValues || DEFAULT_OPT_VALUES;

        const varyingKeys = Object.keys(currentOptEnabled).filter(k => currentOptEnabled[k]);
        if (varyingKeys.length === 0) {
            // If no params, run single backtest or warn?
            // Actually allowed (runs base config 1 time)
        }

        const parameter_ranges = {};
        for (const key of varyingKeys) {
            const values = parseValues(currentOptValues[key]);
            if (values.length === 0) {
                setOptError(`Error: Parameter '${key}' is enabled but has no values. Please enter comma-separated values.`);
                return;
            }
            parameter_ranges[key] = values;
        }

        setIsOptimizing(true);
        setIsCancelling(false);
        setOptResults([]);
        setOptError(null);
        setOptProgress({ current: 0, total: 0 }); // Reset

        try {
            // Sanitize Config for Base
            const base_config = { ...currentConfig }; // Use currentConfig
            Object.keys(base_config).forEach(key => {
                if (base_config[key] === '' && DEFAULT_CONFIG[key] !== undefined) {
                    base_config[key] = DEFAULT_CONFIG[key];
                }
            });

            const payload = {
                symbol: currentConfig.symbol || currentSymbol || "SEC", // Use config's symbol if available, else global
                interval: currentConfig?.interval || "1m", // Sync with Backtest (UI State)
                // days: 365, // Removed to match Backtest default
                from_date: currentConfig?.from_date || "",
                initial_capital: currentConfig?.initial_capital || 10000000,
                parameter_ranges: parameter_ranges,
                base_config: base_config
            };

            const url = `/api/v1/strategies/${selectedStrategy.id}/optimize`;

            // 1. Start Optimization (Async)
            const response = await axios.post(url, payload);

            if (response.data.task_id) {
                const taskId = response.data.task_id;
                const totalCombos = response.data.total_combinations;
                setOptProgress({ current: 0, total: totalCombos });

                // 2. Poll for Status
                let isComplete = false;
                // Store taskId in ref or use local var for cancel button if we want to extract it
                // For now, cancel button needs access to current taskId. 
                // We'll rely on a state for currentTaskId or pass it? 
                // Better: set a state `currentOptTaskId`
                setCurrentOptTaskId(taskId);

                while (!isComplete) {
                    await new Promise(resolve => setTimeout(resolve, 1000)); // Wait 1s

                    try {
                        const statusRes = await axios.get(`/api/v1/strategies/optimize/status/${taskId}`);
                        const statusData = statusRes.data;

                        setOptProgress({
                            current: statusData.progress_current,
                            total: statusData.progress_total
                        });

                        if (statusData.status === 'completed' || statusData.status === 'cancelled') {
                            // Finished (or Cancelled)
                            const resultData = statusData.result;
                            if (resultData && resultData.results && resultData.results.length > 0) {
                                const formattedResults = resultData.results.map(item => ({
                                    rank: item.rank,
                                    ...item.config,
                                    return: item.total_return,
                                    win_rate: item.win_rate,
                                    trades: item.total_trades,
                                    score: item.score,
                                    full_config: item.config,
                                    ...item.metrics // Flatten metrics
                                }));
                                setOptResults(formattedResults);

                                // Persistence
                                if (currentConfig.uuid && statusData.status === 'completed') {
                                    saveStrategyResult(currentConfig.uuid, 'optimization', resultData).catch(err => console.error("Failed to save opt result", err));
                                }

                                if (statusData.status === 'cancelled') {
                                    setOptError("Optimization Cancelled by User (Partial Results Shown Below)");
                                }
                            } else {
                                if (statusData.status === 'cancelled') {
                                    setOptError("Optimization Cancelled by User (No Results)");
                                } else {
                                    const failureMsg = resultData.failures ? resultData.failures.join('\n') : "";
                                    setOptError(`Optimization completed but resulted in 0 valid backtests.\n\nBackend Failures:\n${failureMsg}`);
                                }
                            }
                            isComplete = true;
                        } else if (statusData.status === 'failed') {
                            setOptError(`Optimization Task Failed: ${statusData.message}`);
                            isComplete = true;
                        } else if (statusData.status === 'not_found') {
                            setOptError("Optimization Task Lost (Server Restarted?)");
                            isComplete = true;
                        }
                    } catch (pollErr) {
                        console.warn("Polling failed, retrying...", pollErr);
                        // Continue Polling if network glitch? 
                        // Maybe limit retries, but for now just continue
                    }
                }
            } else {
                // Fallback for synchronous response (if any)
                setOptError("Unexpected Sync Response");
            }

        } catch (error) {
            const msg = error.response?.data?.detail || error.message || "Unknown Error";
            setOptError(`Optimization Request Failed: ${msg}`);
            console.error(error);
        } finally {
            setIsOptimizing(false);
            setIsCancelling(false);
            setCurrentOptTaskId(null);
        }
    };



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
    // fromDate state moved to config


    // Persistence Effects
    // Persistence logic removed for interval

    useEffect(() => {
        if (selectedStrategy) {
            localStorage.setItem('lastStrategyId', selectedStrategy.id);
        }
    }, [selectedStrategy]);

    // Check Data Status
    useEffect(() => {
        if (!isConfigLoaded) return; // Prevent race condition before config loads

        // Use currentConfig.symbol for data status check
        const symbolToCheck = currentConfig.symbol || currentSymbol;
        if (symbolToCheck) {
            checkDataStatus(symbolToCheck);
        }
        setFetchMessage(null);
    }, [currentConfig?.symbol, currentSymbol, currentConfig?.interval, isConfigLoaded]); // Depend on isConfigLoaded

    const checkDataStatus = async (symbol) => {
        try {
            const res = await axios.get(`/api/v1/market-data/status/${symbol}`, {
                params: { interval: currentConfig?.interval || "1m" }
            });
            setDataStatus(res.data);

            // Auto-set Start Date to Data Start
            if (res.data.start_date) {
                // Server returns YY.MM.DD -> Convert to YYYY-MM-DD for input type="date"
                const parts = res.data.start_date.split('.');
                if (parts.length === 3) {
                    const yyyy = `20${parts[0]}`;
                    const mm = parts[1];
                    const dd = parts[2];
                    const newDate = `${yyyy}-${mm}-${dd}`;
                    if (currentConfig?.from_date !== newDate) {
                        handleConfigChange('from_date', newDate);
                    }
                }
            }
        } catch (e) {
            console.error("Failed to check data status", e);
        }
    };

    const handleFetchData = async () => {
        setIsFetchingData(true);
        setFetchMessage(`Updating...`);
        const symbolToFetch = currentConfig.symbol || currentSymbol; // Use config's symbol
        try {
            const res = await axios.post(`/api/v1/market-data/fetch/${symbolToFetch}`, {
                interval: currentConfig?.interval || "1m",
                days: 3650 // Request ~10 years to hit 10k limit
            });

            const added = res.data.added;
            setFetchMessage(null);

            const resultMsg = added > 0 ? `Updated (+${added})` : `Up to date (+0)`;

            await checkDataStatus(symbolToFetch); // Pass symbol to checkDataStatus
            setFetchMessage(resultMsg);

        } catch (e) {
            setFetchMessage("Failed");
            setTimeout(() => setFetchMessage(null), 3000);
        } finally {
            setIsFetchingData(false);
        }
    };

    return (
        <div className="flex flex-col gap-6 pb-10">
            {/* Top Bar: Selector & Actions */}
            <Card className="shrink-0 z-20">
                <div className="flex flex-col gap-4">
                    {/* Row 1: Strategy Selection */}
                    <div className="flex flex-col md:flex-row items-center gap-4 w-full">
                        <div className="relative w-full md:max-w-md">
                            <label className="text-xs text-gray-400 absolute -top-2 left-2 bg-[#0f111a] px-1">Select Strategy</label>
                            <select
                                value={selectedStrategy?.id || ''}
                                onChange={(e) => {
                                    const strat = strategies.find(s => s.id === e.target.value);
                                    setSelectedStrategy(strat);
                                    setBacktestResult(null);
                                }}
                                className="w-full bg-black/40 border border-white/20 rounded-lg px-4 py-3 text-white appearance-none focus:border-blue-500 outline-none cursor-pointer"
                            >
                                {strategies.map(strat => (
                                    <option key={strat.id} value={strat.id} className="bg-slate-900 text-white">
                                        {strat.name}
                                    </option>
                                ))}
                            </select>
                            <div className="absolute right-4 top-1/2 -translate-y-1/2 pointer-events-none text-gray-400">
                                ▼
                            </div>
                        </div>
                        {selectedStrategy && (
                            <div className="hidden md:block text-sm text-gray-400 border-l border-white/10 pl-4 h-10 flex items-center flex-1">
                                {selectedStrategy.description}
                            </div>
                        )}
                    </div>


                </div>
            </Card>

            {/* Main Content Area (No Scroll Container) */}
            <div className="space-y-6 pb-20">
                {selectedStrategy ? (
                    <>

                        {/* SECTION 1: BACKTEST SIMULATION (Config + Execution + Results) */}
                        <div className="space-y-6">
                            <div className="flex items-center gap-4">
                                <div className="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center shadow-lg shadow-blue-900/50">
                                    <span className="text-white font-bold text-lg">1</span>
                                </div>
                                <h2 className="text-2xl font-bold text-white tracking-tight">Backtest Simulation</h2>
                                <div className="h-px bg-gradient-to-r from-white/20 to-transparent flex-1"></div>
                            </div>

                            {/* --- New Tab Bar UI --- */}
                            <div className="flex items-center gap-1 mb-4 overflow-x-auto p-2 scrollbar-hide">
                                {/* Integrated Tab */}
                                <button
                                    onClick={() => setActiveTab(-1)}
                                    className={`px-5 py-2.5 rounded-lg text-sm font-bold transition-all whitespace-nowrap flex items-center gap-2 border ${activeTab === -1
                                        ? 'bg-gradient-to-r from-amber-500 to-orange-600 text-white border-amber-300 shadow-[0_0_15px_rgba(245,158,11,0.4)] scale-105'
                                        : 'bg-gradient-to-r from-gray-800 to-gray-900 text-amber-500 border-amber-500/30 hover:border-amber-500 hover:text-amber-400 hover:shadow-[0_0_10px_rgba(245,158,11,0.2)]'
                                        }`}
                                >
                                    <span className="text-lg">💎</span>
                                    <span>Integrated Portfolio</span>
                                </button>

                                {/* Divider */}
                                <div className="w-px h-6 bg-white/10 mx-2" />

                                {/* Rank/Draft Tabs */}
                                {(() => {
                                    let rankCount = 0;
                                    let draftCount = 0;
                                    return configList.map((cfg, idx) => {
                                        const isSelected = activeTab === idx;
                                        const isActive = cfg.is_active !== false;
                                        let label = "";
                                        if (isActive) {
                                            rankCount++;
                                            label = `Rank ${rankCount}`;
                                        } else {
                                            draftCount++;
                                            label = `Draft ${draftCount}`;
                                        }

                                        const isRank = isActive;
                                        // Check bounds for arrows
                                        // Can move Left if this is rank 2+ (index > 0 is not enough, must check if prev is rank)
                                        // Since ranks are sorted first, index > 0 is sufficient for ranks.
                                        const showLeft = isRank && idx > 0;
                                        // Can move Right if next item is also a Rank
                                        const showRight = isRank && (idx + 1 < configList.length) && configList[idx + 1].is_active !== false;

                                        return (
                                            <button
                                                key={idx}
                                                onClick={() => setActiveTab(idx)}
                                                className={`group px-3 py-2 rounded-lg text-xs font-medium transition-all whitespace-nowrap flex items-center gap-2 ${isSelected
                                                    ? isActive
                                                        ? 'bg-blue-600 text-white shadow-lg shadow-blue-900/30'
                                                        : 'bg-gray-600 text-white shadow-lg'
                                                    : 'bg-white/5 text-gray-400 hover:bg-white/10 hover:text-gray-200'
                                                    }`}
                                            >
                                                <div className={`w-1.5 h-1.5 rounded-full ${isActive ? 'bg-green-400' : 'bg-gray-500'}`} />

                                                {/* Left Arrow */}
                                                {showLeft && (
                                                    <span
                                                        onClick={(e) => moveRankTab(idx, -1, e)}
                                                        className="hover:bg-black/20 rounded px-1 -ml-1 text-white/50 hover:text-white"
                                                    >
                                                        ◀
                                                    </span>
                                                )}

                                                <span>{label}</span>

                                                {/* Right Arrow */}
                                                {showRight && (
                                                    <span
                                                        onClick={(e) => moveRankTab(idx, 1, e)}
                                                        className="hover:bg-black/20 rounded px-1 -mr-1 text-white/50 hover:text-white"
                                                    >
                                                        ▶
                                                    </span>
                                                )}

                                                {/* Delete Button */}
                                                {configList.length > 1 && (
                                                    <span
                                                        onClick={(e) => removeRankTab(idx, e)}
                                                        className="ml-1 w-4 h-4 flex items-center justify-center rounded-full hover:bg-black/40 text-gray-400 hover:text-red-400 transition-colors z-20"
                                                        title="Delete Tab"
                                                    >
                                                        ×
                                                    </span>
                                                )}
                                            </button>
                                        );
                                    });
                                })()}

                                {/* Add Tab Button */}
                                <button
                                    onClick={() => {
                                        const newConfig = {
                                            ...DEFAULT_CONFIG,
                                            is_active: false,
                                            tabName: `Draft ${configList.length + 1}`,
                                            symbol: currentSymbol,
                                            uuid: generateUUID() // Generate UUID for new tab
                                        };
                                        setConfigList([...configList, newConfig]);
                                        setActiveTab(configList.length);
                                    }}
                                    className="px-3 py-2 rounded-lg bg-white/5 text-gray-400 hover:bg-white/10 hover:text-white transition-all"
                                >
                                    +
                                </button>
                            </div>

                            <Card
                                title={
                                    <div className="flex items-center justify-between w-full">
                                        <span>Configuration</span>
                                        {activeTab !== -1 && (
                                            <div className="flex items-center gap-4 ml-4">
                                                <span className={`text-[10px] uppercase font-bold tracking-wider ${currentConfig.is_active !== false ? 'text-green-400' : 'text-gray-500'}`}>
                                                    {currentConfig.is_active !== false ? 'Active Strategy' : 'Draft Mode'}
                                                </span>
                                                <button
                                                    onClick={(e) => {
                                                        e.stopPropagation();
                                                        handleConfigChange('is_active', currentConfig.is_active === false); // Toggle
                                                    }}
                                                    className={`w-8 h-4 rounded-full p-0.5 transition-colors ${currentConfig.is_active !== false ? 'bg-green-500' : 'bg-gray-600'}`}
                                                >
                                                    <div className={`w-3 h-3 bg-white rounded-full shadow-sm transform transition-transform ${currentConfig.is_active !== false ? 'translate-x-4' : 'translate-x-0'}`} />
                                                </button>
                                            </div>
                                        )}
                                    </div>
                                }
                                className="mb-6 border border-purple-500/50 shadow-lg shadow-purple-900/20"
                                variant="major"
                            >
                                {activeTab === -1 ? (
                                    <div className="p-4">
                                        <div className="text-center mb-8">
                                            <h3 className="text-xl font-bold text-white mb-2">🌊 Waterfall Execution Flow</h3>
                                            <p className="text-sm text-gray-400 max-w-lg mx-auto">
                                                Strategies are evaluated sequentially. The first strategy to trigger a BUY signal executes the trade,
                                                and the remaining strategies are skipped for the current interval.
                                            </p>
                                        </div>

                                        <div className="flex flex-col items-center gap-2">
                                            {configList.some(c => c.is_active !== false) ? (
                                                configList.filter(c => c.is_active !== false).map((cfg, idx, arr) => (
                                                    <React.Fragment key={idx}>
                                                        {/* Strategy Node */}
                                                        <div className="w-full max-w-lg bg-black/40 border-2 border-green-500/30 rounded-lg p-4 relative hover:border-green-500/60 transition-colors group">
                                                            {/* Rank Badge */}
                                                            <div className="absolute -left-3 -top-3 w-8 h-8 rounded-full bg-green-600 flex items-center justify-center font-bold text-white shadow-lg border border-black text-sm z-10">
                                                                {idx + 1}
                                                            </div>

                                                            <div className="flex justify-between items-start pl-4">
                                                                <div>
                                                                    <div className="font-bold text-lg text-white group-hover:text-green-400 transition-colors">
                                                                        {cfg.strategy || "Unknown Strategy"}
                                                                    </div>
                                                                    <div className="text-xs text-gray-400 font-mono mt-1">
                                                                        {cfg.symbol} • {cfg.interval}s interval
                                                                    </div>
                                                                </div>

                                                                <div className="text-right">
                                                                    <div className="text-[10px] uppercase tracking-wider text-green-400 font-bold bg-green-900/20 px-2 py-1 rounded">
                                                                        Active
                                                                    </div>
                                                                </div>
                                                            </div>

                                                            {/* Config Preview */}
                                                            <div className="mt-3 pt-3 border-t border-white/5 grid grid-cols-3 gap-2 text-xs text-gray-500">
                                                                {Object.entries(cfg.optEnabled || {}).filter(([_, v]) => v).slice(0, 3).map(([k]) => (
                                                                    <div key={k} className="bg-white/5 rounded px-2 py-1 truncate">
                                                                        {k}: {cfg[k]}
                                                                    </div>
                                                                ))}
                                                                {(Object.keys(cfg.optEnabled || {}).filter(k => cfg.optEnabled[k]).length > 3) && (
                                                                    <div className="px-2 py-1">+ More...</div>
                                                                )}
                                                            </div>
                                                        </div>

                                                        {/* Connector Arrow */}
                                                        {idx < arr.length - 1 && (
                                                            <div className="flex flex-col items-center h-16 justify-center relative">
                                                                <div className="absolute w-0.5 h-full bg-gray-700"></div>
                                                                <div className="bg-[#1e2029] px-3 py-1 text-[10px] text-gray-500 border border-gray-700 rounded-full z-10">
                                                                    No Signal? Next 👇
                                                                </div>
                                                            </div>
                                                        )}

                                                        {/* End Node */}
                                                        {idx === arr.length - 1 && (
                                                            <div className="flex flex-col items-center mt-2 opacity-50">
                                                                <div className="h-8 w-0.5 bg-gray-700 mb-1"></div>
                                                                <div className="px-3 py-1 rounded-full bg-gray-600 text-gray-400 text-xs border border-gray-500">
                                                                    End of Validation (Wait)
                                                                </div>
                                                            </div>
                                                        )}
                                                    </React.Fragment>
                                                ))
                                            ) : (
                                                <div className="text-gray-500 italic py-10">
                                                    No Active Strategies Configured. <br />
                                                    Enable strategies in the Rank tabs to add them here.
                                                </div>
                                            )}
                                        </div>

                                        {/* Strategy Configuration Summary Panel */}
                                        <div className="mt-8 mb-8 bg-white/5 border border-white/10 rounded-xl overflow-hidden">
                                            <div className="bg-white/5 px-4 py-3 border-b border-white/10 flex justify-between items-center">
                                                <h3 className="font-bold text-gray-200 text-sm">Active Strategy Configurations</h3>
                                                <span className="text-xs text-gray-400">{configList.filter(c => c.is_active !== false).length} Active</span>
                                            </div>
                                            <div className="overflow-x-auto">
                                                <table className="w-full text-sm text-left">
                                                    <thead className="text-xs text-gray-400 bg-white/5 uppercase">
                                                        <tr>
                                                            <th className="px-4 py-3">Rank</th>
                                                            <th className="px-4 py-3">Symbol</th>
                                                            <th className="px-4 py-3">Interval</th>
                                                            <th className="px-4 py-3">Direction</th>
                                                            <th className="px-4 py-3">Delay</th>
                                                            <th className="px-4 py-3">Target / Stop</th>
                                                            <th className="px-4 py-3">Trailing</th>
                                                            <th className="px-4 py-3 text-right">Settings</th>
                                                        </tr>
                                                    </thead>
                                                    <tbody className="divide-y divide-white/5">
                                                        {configList.map((cfg, idx) => {
                                                            if (cfg.is_active === false) return null;
                                                            const symbolInfo = savedSymbols.find(s => s.code === cfg.symbol);
                                                            const symbolName = symbolInfo ? symbolInfo.name : cfg.symbol;
                                                            const isRise = (cfg.direction || 'rise') === 'rise';

                                                            return (
                                                                <tr key={cfg.uuid || idx} className="hover:bg-white/5 transition">
                                                                    <td className="px-4 py-3">
                                                                        <span className="bg-blue-500/20 text-blue-400 px-2 py-1 rounded text-xs font-bold">
                                                                            {cfg.tabName || `Rank ${idx + 1}`}
                                                                        </span>
                                                                    </td>
                                                                    <td className="px-4 py-3 font-medium text-white">
                                                                        {symbolName} <span className="text-xs text-gray-500 ml-1">({cfg.symbol})</span>
                                                                    </td>
                                                                    <td className="px-4 py-3 text-gray-300">
                                                                        {cfg.interval || "1m"}
                                                                    </td>
                                                                    <td className="px-4 py-3">
                                                                        <span className={`flex items-center gap-1 text-xs px-2 py-1 rounded font-bold ${isRise ? 'bg-red-500/20 text-red-400' : 'bg-blue-500/20 text-blue-400'}`}>
                                                                            {isRise ? '🚀 Rise' : '📉 Fall'}
                                                                        </span>
                                                                    </td>
                                                                    <td className="px-4 py-3">
                                                                        <span className="text-yellow-400 font-bold">{cfg.delay_minutes || 0}m</span>
                                                                    </td>
                                                                    <td className="px-4 py-3">
                                                                        <div className="flex flex-col text-xs gap-1">
                                                                            <span className="text-green-400">TP: {cfg.target_percent}%</span>
                                                                            <span className="text-red-400">SL: {cfg.safety_stop_percent}%</span>
                                                                        </div>
                                                                    </td>
                                                                    <td className="px-4 py-3">
                                                                        <div className="text-xs text-blue-400">
                                                                            {cfg.trailing_start_percent}% / {cfg.trailing_stop_drop}%
                                                                        </div>
                                                                    </td>
                                                                    <td className="px-4 py-3 text-right">
                                                                        <button
                                                                            onClick={() => setActiveTab(idx)}
                                                                            className="text-xs bg-gray-700 hover:bg-gray-600 px-2 py-1 rounded text-white transition"
                                                                        >
                                                                            Edit
                                                                        </button>
                                                                    </td>
                                                                </tr>
                                                            );
                                                        })}
                                                    </tbody>
                                                </table>
                                            </div>
                                        </div>



                                        {/* Action Button & Settings */}
                                        <div className="mt-12 text-center pb-8 border-t border-white/10 pt-8">
                                            {/* Integrated Settings */}
                                            {/* Integrated Settings */}
                                            {(() => {
                                                const isIntegrated = activeTab === -1;
                                                // If Integrated, inherit from Rank 1 (index 0). Fallback to DEFAULT if empty.
                                                const displayConfig = isIntegrated ? (configList[0] || DEFAULT_CONFIG) : currentConfig;

                                                return (
                                                    <div className="flex justify-center gap-6 mb-8">
                                                        <div className="text-left">
                                                            <label className="text-xs text-gray-400 mb-1 block">
                                                                Initial Capital {isIntegrated && <span className="text-blue-400">(Inherited)</span>}
                                                            </label>
                                                            <input
                                                                type="text"
                                                                value={(displayConfig?.initial_capital || 10000000).toLocaleString()}
                                                                onChange={(e) => {
                                                                    if (isIntegrated) return; // Prevent edit
                                                                    const rawValue = e.target.value.replace(/[^0-9]/g, '');
                                                                    handleConfigChange('initial_capital', rawValue === '' ? 0 : parseInt(rawValue, 10));
                                                                }}
                                                                disabled={isIntegrated}
                                                                className={`bg-black/40 border border-white/20 rounded px-3 py-2 text-white w-40 text-center ${isIntegrated ? 'opacity-50 cursor-not-allowed' : ''}`}
                                                            />
                                                        </div>
                                                        <div className="text-left">
                                                            <label className="text-xs text-gray-400 mb-1 block">
                                                                Start Date {isIntegrated && <span className="text-blue-400">(Inherited)</span>}
                                                            </label>
                                                            <input
                                                                type="date"
                                                                value={displayConfig?.from_date || ""}
                                                                onChange={(e) => {
                                                                    if (isIntegrated) return;
                                                                    handleConfigChange('from_date', e.target.value);
                                                                }}
                                                                disabled={isIntegrated}
                                                                className={`bg-black/40 border border-white/20 rounded px-3 py-2 text-white w-40 text-center ${isIntegrated ? 'opacity-50 cursor-not-allowed' : ''}`}
                                                            />
                                                        </div>
                                                        <div className="text-left">
                                                            <label className="text-xs text-gray-400 mb-1 block">
                                                                Betting Logic {isIntegrated && <span className="text-blue-400">(Inherited)</span>}
                                                            </label>
                                                            <select
                                                                value={displayConfig?.betting_strategy || "fixed"}
                                                                onChange={(e) => {
                                                                    if (isIntegrated) return;
                                                                    // We need to handle betting_strategy in handleConfigChange if it's not already there.
                                                                    // Alternatively, update specific state if it was separate.
                                                                    // But user wants inheritance, so it implies Rank 1 has this property.
                                                                    // Let's assume handleConfigChange handles generic keys.
                                                                    handleConfigChange('betting_strategy', e.target.value);
                                                                }}
                                                                disabled={isIntegrated}
                                                                className={`bg-black/40 border border-white/20 rounded px-3 py-2 text-white w-40 text-center appearance-none cursor-pointer focus:border-blue-500 ${isIntegrated ? 'opacity-50 cursor-not-allowed' : ''}`}
                                                            >
                                                                <option value="fixed">Fixed Amount</option>
                                                                <option value="compound">Compound Interest</option>
                                                            </select>
                                                        </div>
                                                    </div>
                                                );
                                            })()}


                                            <div className="flex gap-4">
                                                <button
                                                    onClick={() => setShowChart(!showChart)}
                                                    disabled={!integratedResults}
                                                    className={`px-6 py-4 rounded-xl font-bold transition-all shadow-lg flex items-center justify-center gap-2 ${!integratedResults
                                                        ? 'bg-gray-800 text-gray-600 cursor-not-allowed opacity-50'
                                                        : 'bg-purple-600 text-white hover:bg-purple-500 shadow-purple-500/30'
                                                        }`}
                                                >
                                                    {showChart ? '📉 Hide Analysis' : '📊 Visual Analysis'}
                                                </button>
                                                <button
                                                    onClick={async () => {
                                                        setIsLoading(true);
                                                        setBacktestStatus({ status: 'running', message: 'Initializing Integrated Simulation...' });
                                                        setBacktestResult(null); // Clear previous
                                                        setIntegratedResults(null);

                                                        try {
                                                            // Collect configurations from active configList
                                                            // Filter only ACTIVE configs, but prioritize Rank Order
                                                            const activeConfigs = configList.filter(c => c.is_active);
                                                            if (activeConfigs.length === 0) {
                                                                throw new Error("No active strategies selected.");
                                                            }

                                                            // Define Leader (Rank 1) for Global Settings
                                                            const leaderConfig = activeConfigs[0];

                                                            // Enforce Global Settings from Leader
                                                            // 1. Betting Logic
                                                            const globalBettingStrategy = leaderConfig.betting_strategy || "fixed";

                                                            // Apply Global Overrides
                                                            const overriddenConfigs = activeConfigs.map(cfg => ({
                                                                ...cfg,
                                                                betting_strategy: globalBettingStrategy
                                                            }));

                                                            // Calculate days based on fromDate
                                                            const startDate = new Date(leaderConfig?.from_date || "");
                                                            const today = new Date();
                                                            const diffTime = Math.abs(today - startDate);
                                                            const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));

                                                            const result = await axios.post('/api/v1/strategies/integrated-backtest', {
                                                                configs: overriddenConfigs,
                                                                symbol: currentSymbol || "KRW-BTC", // Use global or default
                                                                interval: leaderConfig?.interval || "1m", // Use selected interval
                                                                days: diffDays > 0 ? diffDays : 365, // Use calculated days or default
                                                                from_date: leaderConfig?.from_date || "",
                                                                initial_capital: leaderConfig?.initial_capital || 10000000
                                                            });

                                                            // Update Result State and Store for Visualization
                                                            setBacktestResult(result.data);
                                                            setIntegratedResults(result.data); // Store full result for visualization
                                                            setBacktestStatus({ status: 'completed', message: 'Simulation Complete' });

                                                            // Save Result for Persistence
                                                            saveStrategyResult(INTEGRATED_UUID, 'backtest', result.data).catch(err => console.error("Failed to save Integrated Result", err));

                                                        } catch (e) {
                                                            console.error("Integrated Backtest Failed", e);
                                                            setBacktestStatus({ status: 'error', message: "Integrated Backtest Failed: " + (e.message || "Unknown Error") });
                                                        } finally {
                                                            setIsLoading(false);
                                                        }
                                                    }}
                                                    disabled={isLoading}
                                                    className="flex-1 bg-blue-600 hover:bg-blue-500 text-white px-6 py-4 rounded-xl font-bold transition-all shadow-lg hover:shadow-blue-500/30 flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed disabled:bg-gray-700"
                                                >
                                                    {isLoading ? (
                                                        <><div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin"></div> Running Simulation...</>
                                                    ) : (
                                                        <><span className="text-2xl">🧪</span> Run Integrated Backtest</>
                                                    )}
                                                </button>
                                            </div>
                                            <p className="text-xs text-gray-500 mt-4">
                                                * Simulates the Waterfall execution logic (Rank 1 → Rank 2 priority) on historical data.
                                            </p>
                                        </div>

                                        {/* Integrated Analysis Visualization Modal */}

                                    </div>
                                ) : (
                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                                        {/* 1. Target Data */}
                                        <div>
                                            <h4 className="text-sm font-bold text-gray-300 mb-3 flex items-center gap-2">
                                                <div className="w-6 h-6 rounded bg-blue-500/20 text-blue-400 flex items-center justify-center text-xs">1</div>
                                                Target Asset
                                            </h4>
                                            <div className="bg-black/20 p-4 rounded-lg border border-white/5 h-full">
                                                <SymbolSelector
                                                    currentSymbol={currentConfig.symbol || currentSymbol} // Use config's symbol
                                                    setCurrentSymbol={(newSymbol) => handleConfigChange('symbol', newSymbol)} // Update config's symbol
                                                    savedSymbols={savedSymbols}
                                                    setSavedSymbols={setSavedSymbols}
                                                />
                                            </div>
                                        </div>

                                        {/* 2. Parameters */}
                                        <div>
                                            <h4 className="text-sm font-bold text-gray-300 mb-3 flex items-center gap-2">
                                                <div className="w-6 h-6 rounded bg-purple-500/20 text-purple-400 flex items-center justify-center text-xs">2</div>
                                                Parameters
                                            </h4>
                                            <div className="bg-black/20 p-4 rounded-lg border border-white/5">
                                                {selectedStrategy.id === 'time_momentum' ? (
                                                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                                                        <div>
                                                            <label className="text-xs text-gray-500 mb-1 block">Start Time</label>
                                                            <select
                                                                className="w-full bg-black/40 border border-white/10 rounded px-3 py-2 text-sm text-white focus:border-blue-500 outline-none transition-colors appearance-none cursor-pointer"
                                                                value={currentConfig.start_time || "09:00"}
                                                                onChange={(e) => handleConfigChange('start_time', e.target.value)}
                                                            >
                                                                {Array.from({ length: 48 }).map((_, i) => {
                                                                    const h = Math.floor(i / 2);
                                                                    const m = i % 2 === 0 ? "00" : "30";
                                                                    const timeStr = `${h.toString().padStart(2, '0')}:${m}`;
                                                                    return <option key={timeStr} value={timeStr} className="bg-slate-900">{timeStr}</option>;
                                                                })}
                                                            </select>
                                                        </div>
                                                        <div>
                                                            <label className="text-xs text-gray-500 mb-1 block">Delay (Minutes)</label>
                                                            <input
                                                                type="number"
                                                                className="w-full bg-black/40 border border-white/10 rounded px-3 py-2 text-sm text-white focus:border-blue-500 outline-none transition-colors appearance-none [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
                                                                value={currentConfig.delay_minutes ?? ''}
                                                                onChange={(e) => handleConfigChange('delay_minutes', e.target.value === '' ? '' : parseInt(e.target.value))}
                                                            />
                                                        </div>
                                                        <div>
                                                            <label className="text-xs text-gray-500 mb-1 block">Direction</label>
                                                            <select
                                                                className="w-full bg-black/40 border border-white/10 rounded px-3 py-2 text-sm text-white focus:border-blue-500 outline-none transition-colors appearance-none cursor-pointer"
                                                                value={currentConfig.direction || "rise"}
                                                                onChange={(e) => handleConfigChange('direction', e.target.value)}
                                                            >
                                                                <option value="rise" className="bg-slate-900">Rise (Momentum)</option>
                                                                <option value="fall" className="bg-slate-900">Fall (Dip Buying)</option>
                                                            </select>
                                                        </div>
                                                        <div>
                                                            <label className="text-xs text-gray-500 mb-1 block">Target Pump/Dip (%)</label>
                                                            <input
                                                                type="number" step="0.1" min="0"
                                                                className="w-full bg-black/40 border border-white/10 rounded px-3 py-2 text-sm text-white focus:border-blue-500 outline-none transition-colors appearance-none [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
                                                                value={currentConfig.target_percent === '' ? '' : Math.abs(currentConfig.target_percent)}
                                                                onChange={(e) => handleConfigChange('target_percent', e.target.value === '' ? '' : parseFloat(e.target.value))}
                                                            />
                                                        </div>
                                                        <div>
                                                            <label className="text-xs text-gray-500 mb-1 block">Stop Loss (%)</label>
                                                            <input
                                                                type="number" step="0.1" min="0"
                                                                className="w-full bg-black/40 border border-white/10 rounded px-3 py-2 text-sm text-white focus:border-blue-500 outline-none transition-colors appearance-none [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
                                                                value={currentConfig.safety_stop_percent === '' ? '' : Math.abs(currentConfig.safety_stop_percent)}
                                                                onChange={(e) => handleConfigChange('safety_stop_percent', e.target.value === '' ? '' : parseFloat(e.target.value))}
                                                            />
                                                        </div>
                                                        <div>
                                                            <label className="text-xs text-gray-500 mb-1 block">Trailing Start (%)</label>
                                                            <input
                                                                type="number" step="0.1"
                                                                className="w-full bg-black/40 border border-white/10 rounded px-3 py-2 text-sm text-white focus:border-blue-500 outline-none transition-colors appearance-none [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
                                                                value={currentConfig.trailing_start_percent === '' ? '' : currentConfig.trailing_start_percent}
                                                                onChange={(e) => handleConfigChange('trailing_start_percent', e.target.value === '' ? '' : parseFloat(e.target.value))}
                                                            />
                                                        </div>
                                                        <div>
                                                            <label className="text-xs text-gray-500 mb-1 block">Trailing Drop (%)</label>
                                                            <input
                                                                type="number" step="0.1"
                                                                className="w-full bg-black/40 border border-white/10 rounded px-3 py-2 text-sm text-white focus:border-blue-500 outline-none transition-colors appearance-none [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
                                                                value={currentConfig.trailing_stop_drop === '' ? '' : currentConfig.trailing_stop_drop}
                                                                onChange={(e) => handleConfigChange('trailing_stop_drop', e.target.value === '' ? '' : parseFloat(e.target.value))}
                                                            />
                                                        </div>
                                                        <div>
                                                            <label className="text-xs text-gray-500 mb-1 block">Stop Time</label>
                                                            <select
                                                                className="w-full bg-black/40 border border-white/10 rounded px-3 py-2 text-sm text-white focus:border-blue-500 outline-none transition-colors appearance-none cursor-pointer"
                                                                value={currentConfig.stop_time || "15:00"}
                                                                onChange={(e) => handleConfigChange('stop_time', e.target.value)}
                                                            >
                                                                {Array.from({ length: 48 }).map((_, i) => {
                                                                    const h = Math.floor(i / 2);
                                                                    const m = i % 2 === 0 ? "00" : "30";
                                                                    const timeStr = `${h.toString().padStart(2, '0')}:${m}`;
                                                                    return <option key={timeStr} value={timeStr} className="bg-slate-900">{timeStr}</option>;
                                                                })}
                                                            </select>
                                                        </div>
                                                    </div>
                                                ) : (
                                                    <div className="text-gray-500 text-sm text-center py-4">No configurable parameters for this strategy</div>
                                                )}
                                            </div>
                                        </div>
                                    </div>
                                )}
                            </Card>

                            {/* Backtest Controls (Relocated) - Hidden in Integrated View */}
                            {activeTab !== -1 && (
                                <Card title="Backtest Settings & Execution" variant="major" className="border-t-4 border-t-blue-500">
                                    <div className="flex flex-col gap-4">
                                        {/* Row 1: Data Interval & Status */}
                                        <div className="flex flex-col md:flex-row justify-between items-center gap-4 w-full">
                                            <div className="flex items-center gap-4 w-full md:w-auto">
                                                <div className="relative w-32">
                                                    <label className="text-[10px] text-gray-500 absolute -top-1.5 left-2 bg-[#1e2029] px-1">Interval</label>
                                                    <select
                                                        value={currentConfig?.interval || "1m"}
                                                        onChange={(e) => handleConfigChange('interval', e.target.value)}
                                                        className="w-full bg-black/40 border border-white/10 rounded px-3 py-2 text-sm text-white focus:border-blue-500 outline-none appearance-none cursor-pointer"
                                                    >
                                                        <option value="1m">1 Min</option>
                                                        <option value="3m">3 Min</option>
                                                        <option value="5m">5 Min</option>
                                                        <option value="10m">10 Min</option>
                                                        <option value="15m">15 Min</option>
                                                        <option value="30m">30 Min</option>
                                                        <option value="60m">1 Hour</option>
                                                        <option value="1d">1 Day</option>
                                                        <option value="1w">1 Week</option>
                                                    </select>
                                                </div>

                                                <div className="flex items-center gap-3">
                                                    {!dataStatus.is_fresh ? (
                                                        <span className="text-amber-500 text-xs font-bold px-2 py-1 bg-amber-500/10 rounded border border-amber-500/20 whitespace-nowrap">
                                                            Data Stale ({dataStatus.count}{dataStatus.start_date ? `, ${dataStatus.start_date}~` : ''})
                                                        </span>
                                                    ) : (
                                                        <span className="text-green-500 text-xs font-bold px-2 py-1 bg-green-500/10 rounded border border-green-500/20 whitespace-nowrap">
                                                            Data Fresh ({dataStatus.count}{dataStatus.start_date ? `, ${dataStatus.start_date}~` : ''})
                                                        </span>
                                                    )}
                                                    <button
                                                        onClick={handleFetchData}
                                                        disabled={isFetchingData || !isSymbolValid}
                                                        title={!isSymbolValid ? "먼저 종목을 선택해주세요" : "데이터 업데이트"}
                                                        className={`px-3 py-1 rounded text-sm font-bold transition-all shadow-lg flex items-center gap-2 whitespace-nowrap disabled:opacity-50 disabled:cursor-not-allowed ${fetchMessage && fetchMessage.includes("Updated") ? "bg-green-600 text-white" :
                                                            fetchMessage && fetchMessage.includes("Up to date") ? "bg-blue-600 text-white" :
                                                                "bg-amber-600 hover:bg-amber-500 text-white hover:shadow-amber-500/30"
                                                            }`}
                                                    >
                                                        {fetchMessage ? fetchMessage : 'Update Data'}
                                                    </button>
                                                </div>
                                            </div>
                                        </div>

                                        {/* Row 2: Capital & Date & Strategy */}
                                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 border-t border-white/5 pt-4">
                                            <div className="relative">
                                                <label className="text-[10px] text-gray-500 absolute -top-1.5 left-2 bg-[#1e2029] px-1">Initial Capital</label>
                                                <input
                                                    type="text"
                                                    value={(currentConfig?.initial_capital || 10000000).toLocaleString()}
                                                    onChange={(e) => {
                                                        const val = parseInt(e.target.value.replace(/,/g, ''), 10);
                                                        if (!isNaN(val)) handleConfigChange('initial_capital', val);
                                                    }}
                                                    className="w-full bg-black/40 border border-white/10 rounded px-3 py-2 text-sm text-white focus:border-blue-500 outline-none"
                                                />
                                            </div>

                                            <div className="relative">
                                                <label className="text-[10px] text-gray-500 absolute -top-1.5 left-2 bg-[#1e2029] px-1">Start Date</label>
                                                <input
                                                    type="date"
                                                    value={currentConfig?.from_date || ""}
                                                    onChange={(e) => handleConfigChange('from_date', e.target.value)}
                                                    className="w-full bg-black/40 border border-white/10 rounded px-3 py-2 text-sm text-white focus:border-blue-500 outline-none"
                                                />
                                            </div>

                                            <div className="relative">
                                                <label className="text-[10px] text-gray-500 absolute -top-1.5 left-2 bg-[#1e2029] px-1">Betting Logic</label>
                                                <select
                                                    value={currentConfig.betting_strategy || "fixed"}
                                                    onChange={(e) => handleConfigChange('betting_strategy', e.target.value)}
                                                    className="w-full bg-black/40 border border-white/10 rounded px-3 py-2 text-sm text-white focus:border-blue-500 outline-none appearance-none cursor-pointer"
                                                >
                                                    <option value="fixed">Fixed Amount</option>
                                                    <option value="compound">Compound Interest</option>
                                                </select>
                                            </div>
                                        </div>

                                        {/* Row 3: Action Buttons */}
                                        <div className="grid grid-cols-2 gap-4 pt-2">
                                            <button
                                                onClick={() => setShowChart(!showChart)}
                                                disabled={!backtestResult}
                                                className={`px-4 py-4 rounded-xl font-bold transition-all shadow-lg flex items-center justify-center gap-2 ${!backtestResult
                                                    ? 'bg-gray-800 text-gray-600 cursor-not-allowed opacity-50'
                                                    : showChart
                                                        ? 'bg-purple-600 text-white hover:bg-purple-500 shadow-purple-500/30'
                                                        : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                                                    }`}
                                            >
                                                {showChart ? "🙈 Hide Visual Chart" : "📊 Visual Analysis"}
                                            </button>
                                            <button
                                                onClick={() => runBacktest(selectedStrategy?.id)}
                                                disabled={isLoading || !selectedStrategy || !dataStatus.count || activeTab === -1}
                                                className={`bg-blue-600 hover:bg-blue-500 text-white px-4 py-4 rounded-xl font-bold transition-all shadow-lg hover:shadow-blue-500/30 flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed disabled:bg-gray-700 ${activeTab === -1 ? 'opacity-80 cursor-not-allowed' : ''}`}
                                            >
                                                {isLoading ? (
                                                    <>
                                                        <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                                                        Running...
                                                    </>
                                                ) : (
                                                    <>{activeTab === -1 ? 'Coming Soon' : '🚀 Run Backtest'}</>
                                                )}
                                            </button>
                                        </div>


                                    </div>
                                </Card>
                            )}

                            {/* SHARED EXECUTION STATUS FEEDBACK (Visible for both Single and Integrated Modes) */}
                            {(backtestStatus.status !== 'idle' || !backtestResult) && (
                                <Card className="mb-6 border-t-2 border-blue-500/30">
                                    {backtestStatus.status === 'running' ? (
                                        <div className="flex items-center justify-center gap-3 py-8 text-blue-400">
                                            <div className="w-6 h-6 border-2 border-current border-t-transparent rounded-full animate-spin"></div>
                                            <span className="text-lg font-bold animate-pulse">{backtestStatus.message}</span>
                                        </div>
                                    ) : backtestStatus.status === 'error' ? (
                                        <div className="flex items-center justify-center gap-3 py-8 text-red-400">
                                            <span className="text-2xl">⚠️</span>
                                            <span className="text-lg font-bold">{backtestStatus.message}</span>
                                        </div>
                                    ) : !backtestResult && (
                                        <div className="text-center text-gray-500 py-8 text-sm italic">
                                            Select a strategy and click 'Run Backtest' to see results here.
                                        </div>
                                    )}
                                </Card>
                            )}


                            {/* VISUAL CHART SECTION (Dedicated) */}
                            {showChart && backtestResult && (
                                <div className="mb-6 animate-fade-in-down">
                                    <Card title={backtestResult.strategy_id === 'integrated_waterfall' ? "Integrated Replay Analysis" : "Visual Backtest Analysis"}>
                                        {backtestResult.strategy_id === 'integrated_waterfall' ? (
                                            <IntegratedAnalysis
                                                trades={backtestResult.trades || []}
                                                backtestResult={backtestResult}
                                                strategiesConfig={configList}
                                            />
                                        ) : (
                                            backtestResult.ohlcv_data ? (
                                                <VisualBacktestChart
                                                    data={backtestResult.ohlcv_data}
                                                    trades={backtestResult.trades}
                                                />
                                            ) : (
                                                <div className="h-[200px] flex items-center justify-center text-gray-500">
                                                    No visual data available.
                                                </div>
                                            )
                                        )}
                                    </Card>
                                </div>
                            )}

                            {/* Backtest Results */}
                            {backtestResult && (
                                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
                                    <Card
                                        className="lg:col-span-2"
                                        title="Equity Curve"
                                    >
                                        <div className="h-[500px] w-full bg-black/20 rounded-lg p-2 overflow-hidden">
                                            <ResponsiveContainer width="100%" height="100%">
                                                <LineChart data={backtestResult.chart_data}>
                                                    <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                                                    <XAxis
                                                        dataKey="date"
                                                        stroke="#666"
                                                        height={50}
                                                        ticks={(() => {
                                                            // Generate ticks only for month changes
                                                            if (!backtestResult.chart_data) return [];
                                                            const ticks = [];
                                                            let lastMonth = -1;
                                                            backtestResult.chart_data.forEach(d => {
                                                                const date = new Date(d.date);
                                                                const month = date.getMonth();
                                                                if (month !== lastMonth) {
                                                                    ticks.push(d.date);
                                                                    lastMonth = month;
                                                                }
                                                            });
                                                            return ticks;
                                                        })()}
                                                        interval={0} // Force show all passed ticks (recharts might still hide if overlapping, but usually fine for monthly)
                                                        tick={({ x, y, payload, index }) => {
                                                            const dateStr = payload.value;
                                                            if (!dateStr) return null;
                                                            const date = new Date(dateStr);
                                                            const monthStr = `${date.getMonth() + 1}월`; // Show Month only (e.g., "1월")
                                                            const year = date.getFullYear();

                                                            // Show Year if it's Jan (Month 0) OR it's the very first tick
                                                            const isJan = date.getMonth() === 0;
                                                            const showYear = index === 0 || isJan;

                                                            return (
                                                                <g transform={`translate(${x},${y})`}>
                                                                    <text x={0} y={0} dy={16} textAnchor="middle" fill="#666" fontSize={12}>
                                                                        {monthStr}
                                                                    </text>
                                                                    {showYear && (
                                                                        <text x={0} y={0} dy={32} textAnchor="middle" fill="#444" fontSize={10} fontWeight="bold">
                                                                            {year}
                                                                        </text>
                                                                    )}
                                                                </g>
                                                            );
                                                        }}
                                                    />
                                                    <YAxis
                                                        stroke="#666"
                                                        domain={['auto', 'auto']}
                                                        tickFormatter={(value) => {
                                                            if (value >= 100000000) return `${(value / 100000000).toFixed(1)}억`;
                                                            if (value >= 1000000) return `${(value / 1000000).toFixed(1)}M`;
                                                            if (value >= 1000) return `${(value / 1000).toFixed(1)}k`;
                                                            return value;
                                                        }}
                                                        width={60}
                                                    />
                                                    <Tooltip
                                                        contentStyle={{ backgroundColor: '#111', border: '1px solid #333' }}
                                                        itemStyle={{ color: '#fff' }}
                                                        formatter={(value) => new Intl.NumberFormat('ko-KR', { style: 'currency', currency: 'KRW' }).format(value)}
                                                    />
                                                    <Line type="monotone" dataKey="equity" stroke="#8884d8" strokeWidth={2} dot={false} />
                                                </LineChart>
                                            </ResponsiveContainer>
                                        </div>
                                    </Card>
                                    <div className="space-y-6">
                                        <Card title="Performance Stats">
                                            <div className="space-y-4">
                                                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                                                    <div className="p-3 bg-white/5 rounded-lg">
                                                        <div className="text-xs text-gray-400">Total Return</div>
                                                        <div className={`text-xl font-bold ${parseFloat(backtestResult.total_return) >= 0 ? "text-green-400" : "text-red-400"}`}>
                                                            {backtestResult.total_return}
                                                        </div>
                                                    </div>
                                                    <div className="p-3 bg-white/5 rounded-lg border border-purple-500/30 bg-purple-500/10">
                                                        <div className="text-xs text-purple-300 font-semibold">Profit Factor</div>
                                                        <div className="text-xl font-bold text-white">{backtestResult.profit_factor || "0.00"}</div>
                                                    </div>
                                                    <div className="p-3 bg-white/5 rounded-lg">
                                                        <div className="text-xs text-gray-400">Win Rate</div>
                                                        <div className="text-xl font-bold text-white">{backtestResult.win_rate}</div>
                                                    </div>
                                                    <div className="p-3 bg-white/5 rounded-lg">
                                                        <div className="text-xs text-gray-400">Sharpe Ratio</div>
                                                        <div className="text-xl font-bold text-yellow-400">{backtestResult.sharpe_ratio || "0.00"}</div>
                                                    </div>

                                                    <div className="p-3 bg-white/5 rounded-lg">
                                                        <div className="text-xs text-gray-400">Total Trades</div>
                                                        <div className="text-xl font-bold text-white">
                                                            {backtestResult.total_trades}
                                                            <span className="text-sm font-normal text-gray-500 ml-2">
                                                                ({backtestResult.total_days} days)
                                                            </span>
                                                        </div>
                                                    </div>
                                                    <div className="p-3 bg-white/5 rounded-lg">
                                                        <div className="text-xs text-gray-400">Stability (R²)</div>
                                                        <div className="text-xl font-bold text-purple-400">{backtestResult.stability_score || "0.00"}</div>
                                                    </div>
                                                    <div className="p-3 bg-white/5 rounded-lg">
                                                        <div className="text-xs text-gray-400">Profit Accel</div>
                                                        <div className={`text-xl font-bold ${parseFloat(backtestResult.acceleration_score) >= 1 ? 'text-green-400' : 'text-orange-400'}`}>
                                                            {backtestResult.acceleration_score ? `${backtestResult.acceleration_score}x` : "0.00x"}
                                                        </div>
                                                    </div>
                                                    <div className="p-3 bg-white/5 rounded-lg">
                                                        <div className="text-xs text-gray-400">Activity Rate</div>
                                                        <div className="text-xl font-bold text-blue-400">{backtestResult.activity_rate || "0%"}</div>
                                                    </div>
                                                    <div className="p-3 bg-white/5 rounded-lg">
                                                        <div className="text-xs text-gray-400">Avg PnL</div>
                                                        <div className={`text-xl font-bold ${parseFloat(backtestResult.avg_pnl) >= 0 ? "text-green-400" : "text-red-400"}`}>
                                                            {backtestResult.avg_pnl}
                                                        </div>
                                                    </div>
                                                    <div className="p-3 bg-white/5 rounded-lg">
                                                        <div className="text-xs text-gray-400">Avg Holding</div>
                                                        <div className="text-xl font-bold text-white">{backtestResult.avg_holding_time || "0m"}</div>
                                                    </div>

                                                    <div className="p-3 bg-white/5 rounded-lg">
                                                        <div className="text-xs text-gray-400">Max Profit</div>
                                                        <div className="text-xl font-bold text-green-400">{backtestResult.max_profit}</div>
                                                    </div>
                                                    <div className="p-3 bg-white/5 rounded-lg">
                                                        <div className="text-xs text-gray-400">Max Loss</div>
                                                        <div className="text-xl font-bold text-red-400">{backtestResult.max_loss}</div>
                                                    </div>
                                                    <div className="col-span-2 md:col-span-4 p-4 bg-white/5 rounded-lg flex flex-col justify-center min-h-[5rem]">
                                                        <div className="text-xs text-gray-400 mb-1">Max Drawdown</div>
                                                        <div className="text-lg md:text-xl font-bold text-red-400 break-words leading-tight">
                                                            {backtestResult.max_drawdown || "N/A"}
                                                        </div>
                                                    </div>
                                                </div>

                                                {/* Monthly Analysis Chart */}
                                                {backtestResult.decile_stats && backtestResult.decile_stats.length > 0 && (
                                                    <div className="mt-4 pt-4 border-t border-white/10">
                                                        <h4 className="text-sm font-bold text-gray-400 mb-2">Strategy Stability (Monthly Analysis)</h4>
                                                        <div className="h-[200px] w-full bg-black/20 rounded-lg p-2">
                                                            <ResponsiveContainer width="100%" height="100%">
                                                                <ComposedChart data={backtestResult.decile_stats} margin={{ bottom: 60, left: 0, right: 0 }}>
                                                                    <CartesianGrid strokeDasharray="3 3" stroke="#333" vertical={false} />

                                                                    {/* Custom X-Axis with Multi-Row Data */}
                                                                    <XAxis
                                                                        dataKey="block"
                                                                        stroke="#666"
                                                                        tickLine={false}
                                                                        interval={0}
                                                                        tick={({ x, y, payload, index }) => {
                                                                            const data = backtestResult.decile_stats[index];
                                                                            return (
                                                                                <g transform={`translate(${x},${y})`}>
                                                                                    {/* Row 1: Month */}
                                                                                    <text x={0} y={10} dy={0} textAnchor="middle" fill="#9ca3af" fontSize={10}>
                                                                                        {payload.value}
                                                                                    </text>
                                                                                    {/* Row 2: Trade Count */}
                                                                                    <text x={0} y={10} dy={12} textAnchor="middle" fill="#60a5fa" fontSize={10} fontWeight="bold">
                                                                                        {data.count}
                                                                                    </text>
                                                                                    {/* Row 3: Win Rate */}
                                                                                    <text x={0} y={10} dy={24} textAnchor="middle" fill="#fbbf24" fontSize={10}>
                                                                                        {data.win_rate}%
                                                                                    </text>
                                                                                    {/* Row 4: Realized PnL */}
                                                                                    <text x={0} y={10} dy={36} textAnchor="middle" fill={data.total_pnl >= 0 ? "#4ade80" : "#ef4444"} fontSize={10} fontWeight="bold">
                                                                                        {data.total_pnl}%
                                                                                    </text>
                                                                                </g>
                                                                            );
                                                                        }}
                                                                    />

                                                                    <YAxis yAxisId="left" stroke="#666" tick={{ fontSize: 10 }} tickFormatter={(val) => `${val}%`} />
                                                                    <YAxis yAxisId="right" orientation="right" hide domain={[0, 100]} />

                                                                    <Tooltip
                                                                        contentStyle={{ backgroundColor: '#1f2937', border: 'none', borderRadius: '8px' }}
                                                                        itemStyle={{ color: '#fff' }}
                                                                        formatter={(value, name) => {
                                                                            if (name === "total_pnl") return [`${value}%`, 'Realized PnL'];
                                                                            return [value, name];
                                                                        }}
                                                                        labelFormatter={(label) => `Month: ${label}`}
                                                                    />
                                                                    <ReferenceLine yAxisId="left" y={0} stroke="#666" />

                                                                    <Bar yAxisId="left" dataKey="total_pnl" radius={[4, 4, 0, 0]}>
                                                                        {backtestResult.decile_stats.map((entry, index) => (
                                                                            <Cell key={`cell-${index}`} fill={entry.total_pnl >= 0 ? '#4ade80' : '#ef4444'} />
                                                                        ))}
                                                                    </Bar>
                                                                </ComposedChart>
                                                            </ResponsiveContainer>
                                                        </div>
                                                        <div className="flex justify-center gap-4 mt-1 text-[10px] text-gray-500">
                                                            <div className="flex items-center gap-1">
                                                                <div className="w-2 h-2 bg-green-400 rounded-sm"></div>
                                                                <span>Profit</span>
                                                            </div>
                                                            <div className="flex items-center gap-1">
                                                                <div className="w-2 h-2 bg-red-400 rounded-sm"></div>
                                                                <span>Loss</span>
                                                            </div>
                                                            <div className="flex items-center gap-1">
                                                                <span className="text-blue-400 font-bold">12</span>
                                                                <span>= Count</span>
                                                            </div>
                                                            <div className="flex items-center gap-1">
                                                                <span className="font-bold" style={{ color: '#fbbf24' }}>60%</span>
                                                                <span>= Win Rate</span>
                                                            </div>
                                                            <div className="flex items-center gap-1">
                                                                <span className="text-green-400 font-bold">5.2%</span>
                                                                <span>= Realized PnL</span>
                                                            </div>
                                                        </div>
                                                    </div>
                                                )}

                                                {/* Logs Preview */}
                                                {backtestResult.logs && (
                                                    <div className="mt-4 pt-4 border-t border-white/10">
                                                        <h4 className="text-sm font-bold text-gray-400 mb-2">Execution Logs (Debug: {backtestResult.logs ? backtestResult.logs.length : 'N/A'})</h4>
                                                        <div className="h-[200px] overflow-y-auto bg-black/40 p-2 rounded text-xs font-mono space-y-1">
                                                            {backtestResult.logs.map((log, i) => (
                                                                <div key={i} className={log.includes("EXECUTED") ? "text-green-400" : "text-gray-500"}>
                                                                    {log}
                                                                </div>
                                                            ))}
                                                        </div>
                                                    </div>
                                                )}
                                            </div>
                                        </Card>
                                        <button className="w-full bg-gradient-to-r from-green-600 to-emerald-600 py-4 rounded-xl font-bold text-lg shadow-xl hover:scale-[1.02] transition-transform">
                                            Deploy Strategy to Live
                                        </button>
                                    </div>
                                </div>
                            )}
                        </div> {/* End of Backtest Simulation Group */}

                        {/* OPTIMIZATION SECTION */}
                        {activeTab !== -1 && (
                            <div className="space-y-6 pt-10">
                                <div className="flex items-center gap-4">
                                    <div className="w-8 h-8 rounded-lg bg-purple-600 flex items-center justify-center shadow-lg shadow-purple-900/50">
                                        <span className="text-white font-bold text-lg">2</span>
                                    </div>
                                    <h2 className="text-2xl font-bold text-white tracking-tight">Parameter Optimization</h2>
                                    <div className="h-px bg-gradient-to-r from-white/20 to-transparent flex-1"></div>
                                </div>

                                <Card title="Parameter Optimization (Grid Search)" variant="major" className="border-t-4 border-t-purple-500">
                                    <div className="space-y-6">
                                        <div className="space-y-6">
                                            {/* Dynamic Grid Inputs */}
                                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                                                {(() => {
                                                    const currentOptEnabled = currentConfig.optEnabled || {};
                                                    const currentOptValues = currentConfig.optValues || DEFAULT_OPT_VALUES;

                                                    return PARAM_DEFINITIONS.map((param) => (
                                                        <div key={param.key} className={`p-3 rounded-lg border transition-colors ${currentOptEnabled[param.key] ? 'bg-purple-900/20 border-purple-500/50' : 'bg-black/20 border-white/5'}`}>
                                                            <div className="flex items-center gap-2 mb-2">
                                                                <input
                                                                    type="checkbox"
                                                                    id={`opt-${param.key}`}
                                                                    checked={!!currentOptEnabled[param.key]}
                                                                    onChange={(e) => handleOptEnableChange(param.key, e.target.checked)}
                                                                    className="w-4 h-4 rounded border-gray-600 text-purple-600 focus:ring-purple-500 bg-gray-700"
                                                                />
                                                                <label htmlFor={`opt-${param.key}`} className={`text-xs font-bold ${currentOptEnabled[param.key] ? 'text-purple-300' : 'text-gray-500'}`}>
                                                                    {param.label}
                                                                </label>
                                                            </div>
                                                            {param.type === 'select' && currentOptEnabled[param.key] ? (
                                                                <div className="relative">
                                                                    <div
                                                                        onClick={() => setActiveDropdown(activeDropdown === param.key ? null : param.key)}
                                                                        className={`w-full bg-black/40 border rounded px-3 py-2 text-sm text-white cursor-pointer min-h-[38px] flex items-center justify-between ${activeDropdown === param.key ? 'border-purple-500 ring-1 ring-purple-500' : 'border-purple-500/30'
                                                                            }`}
                                                                    >
                                                                        <span className="truncate">
                                                                            {currentOptValues[param.key] || <span className="text-gray-500">Select options...</span>}
                                                                        </span>
                                                                        <span className="text-gray-400 text-xs ml-2">▼</span>
                                                                    </div>

                                                                    {/* Dropdown Menu */}
                                                                    {activeDropdown === param.key && (
                                                                        <div className="absolute z-50 mt-1 w-full bg-[#1a1c23] border border-white/20 rounded-lg shadow-xl max-h-60 overflow-y-auto">
                                                                            {param.options.map(option => {
                                                                                const currentVals = (currentOptValues[param.key] || '').split(',').map(v => v.trim()).filter(Boolean);
                                                                                const isSelected = currentVals.includes(option);

                                                                                return (
                                                                                    <div
                                                                                        key={option}
                                                                                        onClick={() => {
                                                                                            let newVals;
                                                                                            if (isSelected) {
                                                                                                newVals = currentVals.filter(v => v !== option);
                                                                                            } else {
                                                                                                // Sort logic if needed, but append is fine for now
                                                                                                newVals = [...currentVals, option];
                                                                                                // Try to sort times if possible? complex. Just push.
                                                                                            }
                                                                                            handleOptValueChange(param.key, newVals.join(', '));
                                                                                        }}
                                                                                        className={`px-3 py-2 text-sm cursor-pointer hover:bg-white/10 flex items-center justify-between ${isSelected ? 'bg-purple-900/40 text-purple-300' : 'text-gray-300'
                                                                                            }`}
                                                                                    >
                                                                                        <span>{option}</span>
                                                                                        {isSelected && <span>✓</span>}
                                                                                    </div>
                                                                                );
                                                                            })}
                                                                        </div>
                                                                    )}

                                                                    {/* Overlay to close */}
                                                                    {activeDropdown === param.key && (
                                                                        <div
                                                                            className="fixed inset-0 z-40"
                                                                            onClick={(e) => { e.stopPropagation(); setActiveDropdown(null); }}
                                                                        ></div>
                                                                    )}
                                                                </div>
                                                            ) : (
                                                                <input
                                                                    type="text"
                                                                    placeholder={param.placeholder}
                                                                    disabled={!currentOptEnabled[param.key]}
                                                                    className={`w-full bg-black/40 border rounded px-3 py-2 text-sm focus:outline-none transition-colors ${currentOptEnabled[param.key]
                                                                        ? 'border-purple-500/30 text-white focus:border-purple-500'
                                                                        : 'border-white/5 text-gray-400 bg-white/5 cursor-not-allowed opacity-70'}`}
                                                                    value={currentOptEnabled[param.key] ? (currentOptValues[param.key] || "") : (currentConfig[param.key] ?? "")}
                                                                    onChange={(e) => handleOptValueChange(param.key, e.target.value)}
                                                                />
                                                            )}
                                                            {currentOptEnabled[param.key] && (
                                                                <p className="text-[10px] text-gray-500 mt-1 truncate">
                                                                    e.g. {param.placeholder}
                                                                </p>
                                                            )}
                                                        </div>
                                                    ));
                                                })()}
                                            </div>





                                            {/* Action */}
                                            <div className="flex gap-2">
                                                <button
                                                    onClick={runOptimization}
                                                    disabled={isOptimizing || activeTab === -1}
                                                    className={`flex-1 bg-gradient-to-r from-purple-900 to-blue-900 hover:from-purple-800 hover:to-blue-800 py-3 rounded-lg font-bold text-white shadow-lg shadow-purple-900/40 transition-all flex justify-center items-center gap-2 ${(isOptimizing || activeTab === -1) ? 'cursor-not-allowed opacity-80' : ''}`}
                                                >
                                                    {isOptimizing ? (
                                                        <>
                                                            <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                                                            {optProgress.total > 0
                                                                ? `Processing (${optProgress.current}/${optProgress.total})...`
                                                                : "Initializing..."}
                                                        </>
                                                    ) : (
                                                        <>{activeTab === -1 ? 'Optimization Unavailable (Integrated)' : `🧪 Start Optimization Analysis (${Object.values((currentConfig.optEnabled || {})).filter(Boolean).length} Params)`}</>
                                                    )}
                                                </button>

                                                {isOptimizing && (
                                                    <button
                                                        onClick={() => cancelOptimization(currentOptTaskId)}
                                                        disabled={isCancelling}
                                                        className="px-6 rounded-lg font-bold text-white bg-red-600 hover:bg-red-500 shadow-lg shadow-red-900/20 transition-all flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                                                    >
                                                        {isCancelling ? 'Stopping...' : 'Stop'}
                                                    </button>
                                                )}
                                            </div>

                                            {/* Error/Status Display */}
                                            {optError && (
                                                <div className={`mt-4 p-4 rounded-lg animate-fade-in border ${optError.includes("Cancelled")
                                                    ? "bg-gray-800/50 border-gray-600 text-gray-300"
                                                    : "bg-red-900/20 border-red-500/50 text-red-300"
                                                    }`}>
                                                    <div className={`flex items-center gap-2 mb-2 font-bold ${optError.includes("Cancelled") ? "text-gray-300" : "text-red-400"}`}>
                                                        <span className="text-xl">{optError.includes("Cancelled") ? "🛑" : "⚠️"}</span>
                                                        {optError.includes("Cancelled") ? "Optimization Stopped" : "Optimization Error"}
                                                    </div>
                                                    <pre className={`whitespace-pre-wrap text-sm font-mono overflow-auto max-h-40 select-text p-2 rounded border ${optError.includes("Cancelled")
                                                        ? "bg-black/30 border-gray-500/30 text-gray-400"
                                                        : "bg-black/30 border-red-500/10"
                                                        }`}>
                                                        {optError}
                                                    </pre>
                                                    {!optError.includes("Cancelled") && (
                                                        <p className="text-xs text-red-500/70 mt-2">
                                                            Check the error message above. You can copy it for debugging.
                                                        </p>
                                                    )}
                                                </div>
                                            )}

                                            {optResults && optResults.length > 0 && (
                                                <div className="bg-black/40 rounded-lg overflow-hidden border border-white/10 mt-4">
                                                    <div className="overflow-x-auto">
                                                        <table className="w-full text-left border-collapse whitespace-nowrap">
                                                            <thead>
                                                                <tr className="bg-white/5 text-xs font-bold text-gray-400 border-b border-white/10">
                                                                    <th className="p-3 text-center w-16">Active</th>
                                                                    {[
                                                                        { key: 'rank', label: 'Rank' },
                                                                        ...PARAM_DEFINITIONS,
                                                                        { key: 'return', label: 'Return' },
                                                                        { key: 'max_drawdown', label: 'MDD' },
                                                                        { key: 'win_rate', label: 'Win Rate' },
                                                                        { key: 'profit_factor', label: 'P.Factor' },
                                                                        { key: 'sharpe_ratio', label: 'Sharpe' },
                                                                        { key: 'avg_pnl', label: 'Avg PnL' },
                                                                        { key: 'stability_score', label: 'Stability' },
                                                                        { key: 'acceleration_score', label: 'Profit Accel' },
                                                                        { key: 'trades', label: 'Trades' },
                                                                        { key: 'score', label: 'Score' }
                                                                    ].map((col) => (
                                                                        <th
                                                                            key={col.key}
                                                                            onClick={() => handleSort(col.key)}
                                                                            className={`p-3 cursor-pointer hover:text-white transition-colors ${sortConfig.key === col.key ? 'text-purple-300' : ''
                                                                                }`}
                                                                        >
                                                                            <div className="flex items-center gap-1">
                                                                                {col.label}
                                                                                {sortConfig.key === col.key && (
                                                                                    <span>{sortConfig.direction === 'asc' ? '▲' : '▼'}</span>
                                                                                )}
                                                                            </div>
                                                                        </th>
                                                                    ))}
                                                                </tr>
                                                            </thead>
                                                            <tbody>
                                                                {[...optResults]
                                                                    .sort((a, b) => {
                                                                        let valA = a[sortConfig.key];
                                                                        let valB = b[sortConfig.key];

                                                                        // Handle percentage strings if necessary, though backend sends numbers usually
                                                                        // If raw data is mixed, safe check:
                                                                        if (typeof valA === 'string' && valA.includes('%')) valA = parseFloat(valA);
                                                                        if (typeof valB === 'string' && valB.includes('%')) valB = parseFloat(valB);

                                                                        if (valA < valB) return sortConfig.direction === 'asc' ? -1 : 1;
                                                                        if (valA > valB) return sortConfig.direction === 'asc' ? 1 : -1;
                                                                        return 0;
                                                                    })
                                                                    .map((res, idx) => {
                                                                        let isActiveConfig = true;
                                                                        // Check if this result matches current configuration
                                                                        if (currentConfig) {
                                                                            for (const param of PARAM_DEFINITIONS) {
                                                                                const configVal = currentConfig[param.key];
                                                                                const resVal = res[param.key];
                                                                                // Loose equality since API might return number vs string input
                                                                                // eslint-disable-next-line eqeqeq
                                                                                if (configVal != resVal) {
                                                                                    isActiveConfig = false;
                                                                                    break;
                                                                                }
                                                                            }
                                                                        }

                                                                        return (
                                                                            <tr key={idx} className={`text-sm border-b border-white/5 hover:bg-white/5 transition-colors ${isActiveConfig ? 'bg-green-500/20' : (res.rank === 1 ? 'bg-green-500/10' : '')}`}>
                                                                                <td className="p-3 text-center">
                                                                                    <button
                                                                                        disabled={isActiveConfig}
                                                                                        onClick={() => {
                                                                                            requestConfirm(
                                                                                                "Apply Optimization Config?",
                                                                                                `Rank: #${res.rank}\nReturn: ${res.return}%\nScore: ${res.score}\n\nThis will overwrite your current configuration. Continue?`,
                                                                                                () => {
                                                                                                    setConfigList(prev => {
                                                                                                        const next = [...prev];
                                                                                                        const configToApply = res.full_config || {};
                                                                                                        next[activeTab] = {
                                                                                                            ...next[activeTab],
                                                                                                            ...configToApply
                                                                                                        };
                                                                                                        return next;
                                                                                                    });
                                                                                                }
                                                                                            );
                                                                                        }}
                                                                                        className={`text-xs px-3 py-1.5 rounded font-bold transition-all shadow-sm ${isActiveConfig
                                                                                            ? 'bg-green-600/80 text-white cursor-default shadow-green-900/40 relative pl-6 ring-1 ring-green-400'
                                                                                            : 'bg-purple-900/40 hover:bg-purple-800 border border-purple-500/30 text-purple-300 hover:shadow-purple-900/20'
                                                                                            }`}
                                                                                    >
                                                                                        {isActiveConfig && <span className="absolute left-2 top-1.5 text-[9px] leading-3">✓</span>}
                                                                                        {isActiveConfig ? 'Active' : 'Select'}
                                                                                    </button>
                                                                                </td>
                                                                                <td className={`p-3 font-bold ${res.rank === 1 ? 'text-green-400' : 'text-gray-500'}`}>#{res.rank}</td>

                                                                                {/* Render All Params */}
                                                                                {PARAM_DEFINITIONS.map(param => (
                                                                                    <td key={param.key} className="p-3 text-gray-300">
                                                                                        {res[param.key] !== undefined ? res[param.key] : '-'}
                                                                                    </td>
                                                                                ))}

                                                                                <td className={`p-3 ${res.return >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                                                                    {res.return > 0 ? '+' : ''}{res.return}%
                                                                                </td>
                                                                                <td className="p-3 text-red-300">{res.max_drawdown ?? '-'}</td>
                                                                                <td className="p-3 text-white">{res.win_rate}%</td>
                                                                                <td className="p-3 text-white">{res.profit_factor ?? '-'}</td>
                                                                                <td className="p-3 text-white">{res.sharpe_ratio ?? '-'}</td>
                                                                                <td className={`p-3 ${parseFloat(res.avg_pnl) >= 0 ? 'text-green-400' : 'text-red-400'}`}>{res.avg_pnl ?? '-'}</td>
                                                                                <td className="p-3 text-white">{res.stability_score ?? '-'}</td>
                                                                                <td className="p-3 text-white">{res.acceleration_score ?? '-'}</td>
                                                                                <td className="p-3 text-gray-400">{res.trades}</td>
                                                                                <td className="p-3 text-blue-400 font-bold">{res.score}</td>
                                                                            </tr>
                                                                        );
                                                                    })}
                                                            </tbody>
                                                        </table>
                                                    </div>
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                </Card>




                            </div>
                        )}

                        {/* Code View */}
                        <div className="pt-10">
                            <Card title="Strategy Logic">
                                <pre className="bg-black/50 p-4 rounded-lg text-sm font-mono text-gray-300 overflow-x-auto border border-white/5 max-h-[300px]">
                                    {selectedStrategy.code}
                                </pre>
                            </Card>
                        </div>
                    </>
                ) : (
                    <div className="flex flex-col items-center justify-center h-[50vh] text-gray-500">
                        <div className="text-6xl mb-4 opacity-20">⚡</div>
                        <p className="text-xl">Select a strategy to begin</p>
                    </div>
                )
                }
            </div>

            {/* AI Generator Input - Fixed Bottom */}
            <Card className="shrink-0 mt-auto border-t border-white/10 bg-gradient-to-b from-[#1a1c23] to-[#111]">
                <div className="flex gap-4">
                    <input
                        type="text"
                        className="flex-1 bg-black/40 border border-white/10 rounded-lg p-4 text-white focus:border-purple-500 focus:ring-1 focus:ring-purple-500 outline-none placeholder-gray-600"
                        placeholder="Describe a new strategy... (e.g., 'Buy when RSI < 30 and price is above 200MA')"
                        value={aiPrompt}
                        onChange={(e) => setAiPrompt(e.target.value)}
                        onKeyPress={(e) => e.key === 'Enter' && handleAiGenerate()}
                    />
                    <button
                        onClick={handleAiGenerate}
                        disabled={isGenerating || !aiPrompt}
                        className={`px-8 rounded-lg font-bold transition-all flex items-center gap-2 whitespace-nowrap ${isGenerating ? 'bg-purple-900 text-purple-300' : 'bg-purple-600 hover:bg-purple-500 text-white shadow-lg hover:shadow-purple-500/30'
                            }`}
                    >
                        {isGenerating ? 'Generatin...' : 'Ask AI'}
                    </button>
                </div>
            </Card>

            {/* Custom Confirm Modal */}
            <ConfirmModal
                isOpen={confirmModal.isOpen}
                onClose={() => setConfirmModal(prev => ({ ...prev, isOpen: false }))}
                onConfirm={confirmModal.onConfirm}
                title={confirmModal.title}
                message={confirmModal.message}
                isDanger={confirmModal.isDanger}
            />
        </div >
    );
};

export default StrategyView;
