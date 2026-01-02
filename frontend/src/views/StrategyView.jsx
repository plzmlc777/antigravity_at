import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar, Cell, ReferenceLine, ComposedChart, LabelList } from 'recharts';
import Card from '../components/common/Card';
import SymbolSelector from '../components/SymbolSelector'; // Import
import VisualBacktestChart from '../components/VisualBacktestChart';

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
    delay_minutes: 10,
    direction: "rise",
    target_percent: 2,
    safety_stop_percent: 3,
    trailing_start_percent: 5,
    trailing_stop_drop: 2,
    stop_time: "15:00",
    is_active: false // Default to Draft mode
};

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

    // State for Config List (Tabs)
    const [activeTab, setActiveTab] = useState(0); // 0 = Rank 1, -1 = Integrated
    // configList: Array of config objects for each rank. Rank N = configList[N-1]
    const [configList, setConfigList] = useState([]);

    const [isConfigLoaded, setIsConfigLoaded] = useState(false);

    // Backtest Settings
    const [fromDate, setFromDate] = useState(""); // YYYY-MM-DD
    const [initialCapital, setInitialCapital] = useState(() => {
        const saved = localStorage.getItem('initialCapital');
        return saved ? parseInt(saved, 10) : 10000000;
    });

    // Save to LocalStorage
    useEffect(() => {
        localStorage.setItem('lastSymbol', currentSymbol);
    }, [currentSymbol]);

    useEffect(() => {
        localStorage.setItem('savedSymbols', JSON.stringify(savedSymbols));
    }, [savedSymbols]);

    useEffect(() => {
        localStorage.setItem('initialCapital', initialCapital.toString());
    }, [initialCapital]);

    // Load Strategy Config List on Selection
    useEffect(() => {
        if (selectedStrategy) {
            // Try load LIST first
            const savedList = localStorage.getItem(`strategyConfigList_${selectedStrategy.id}`);
            if (savedList) {
                try {
                    setConfigList(JSON.parse(savedList));
                } catch {
                    setConfigList([DEFAULT_CONFIG]);
                }
            } else {
                // Fallback: Check for old single config and migrate
                const oldConfig = localStorage.getItem(`strategyConfig_${selectedStrategy.id}`);
                if (oldConfig) {
                    try {
                        setConfigList([JSON.parse(oldConfig)]);
                    } catch {
                        setConfigList([DEFAULT_CONFIG]);
                    }
                } else {
                    setConfigList([DEFAULT_CONFIG]);
                }
            }
            setIsConfigLoaded(true);
        }
    }, [selectedStrategy]);

    // Save Strategy Config List on Change
    useEffect(() => {
        if (isConfigLoaded && selectedStrategy && configList.length > 0) {
            localStorage.setItem(`strategyConfigList_${selectedStrategy.id}`, JSON.stringify(configList));
        }
    }, [configList, selectedStrategy, isConfigLoaded]);

    const handleConfigChange = (key, value) => {
        setConfigList(prev => {
            const newList = [...prev];
            if (activeTab >= 0 && activeTab < newList.length) {
                newList[activeTab] = { ...newList[activeTab], [key]: value };
            }
            return newList;
        });
    };

    const addTab = () => {
        setConfigList(prev => [...prev, { ...DEFAULT_CONFIG }]);
        setActiveTab(prev => prev + 1);
    };

    const removeTab = (index) => {
        if (configList.length <= 1) return; // Prevent removing last tab
        setConfigList(prev => prev.filter((_, i) => i !== index));
        if (activeTab >= index) setActiveTab(Math.max(0, activeTab - 1));
    };

    // Helper to get current config safely
    const currentConfig = (activeTab >= 0 && configList[activeTab]) ? configList[activeTab] : DEFAULT_CONFIG;


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
        setIsLoading(true);
        setBacktestStatus({ status: 'running', message: 'Initializing Strategy...' });
        setBacktestResult(null); // Clear previous results
        setShowChart(false);

        try {
            // Sanitize Config: Replace empty strings with defaults
            const cleanConfig = { ...currentConfig }; // Use currentConfig aka activeTab
            Object.keys(cleanConfig).forEach(key => {
                if (cleanConfig[key] === '' && DEFAULT_CONFIG[key] !== undefined) {
                    cleanConfig[key] = DEFAULT_CONFIG[key];
                }
            });

            // For now, Single Symbol Backtest uses active config
            // If activeTab is -1 (Integrated), we might need different logic later.
            // But for now, user requested Rank 1 (Index 0) to work exactly as before.

            const payload = {
                symbol: currentSymbol,
                from_date: fromDate,
                initial_capital: initialCapital,
                interval: currentInterval,
                config: cleanConfig
            };

            setBacktestStatus({ status: 'running', message: `Running Backtest on ${currentSymbol}...` });

            const res = await axios.post(`/api/v1/strategies/${strategyId}/backtest`, payload);
            setBacktestResult(res.data);
            setBacktestStatus({ status: 'success', message: 'Backtest Completed' });

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

    // 5. Data Management & Persistence State
    const [dataStatus, setDataStatus] = useState({ is_fresh: false, last_updated: null, count: 0 });
    const [isFetchingData, setIsFetchingData] = useState(false);
    const [currentInterval, setCurrentInterval] = useState(() => localStorage.getItem('lastInterval') || "1m");
    const [fetchMessage, setFetchMessage] = useState(null);

    // 6. Optimization State
    const [isOptimizing, setIsOptimizing] = useState(false);
    const [optResults, setOptResults] = useState(null);
    const [optProgress, setOptProgress] = useState({ current: 0, total: 0 });
    const [optError, setOptError] = useState(null);

    // State for Dynamic Optimization
    const [optEnabled, setOptEnabled] = useState(() => {
        const saved = localStorage.getItem('optEnabled');
        return saved ? JSON.parse(saved) : {};
    });

    const [optValues, setOptValues] = useState(() => {
        const saved = localStorage.getItem('optValues');
        return saved ? JSON.parse(saved) : {
            start_time: "09:00, 09:30",
            delay_minutes: "5, 10, 15",
            direction: "rise",
            target_percent: "1, 2, 3, 5",
            safety_stop_percent: "2, 3, 5",
            trailing_start_percent: "3, 5",
            trailing_stop_drop: "1, 2",
            stop_time: "15:00"
        };
    });

    // Save Optimization Config on Change
    useEffect(() => {
        localStorage.setItem('optEnabled', JSON.stringify(optEnabled));
    }, [optEnabled]);

    useEffect(() => {
        localStorage.setItem('optValues', JSON.stringify(optValues));
    }, [optValues]);

    const handleOptEnableChange = (key, checked) => {
        setOptEnabled(prev => ({ ...prev, [key]: checked }));
    };

    const handleOptValueChange = (key, value) => {
        setOptValues(prev => ({ ...prev, [key]: value }));
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

    // Helper: Parse parameter string (if not already defined above? It was defined inside render loop in original? No, helper usually outside. Let's define it here just in case, or check if it exists)
    // Actually `parseValues` was in my viewed snippets. It was stand-alone.
    // I need to make sure I don't duplicate it if it's already there. 
    // In step 5429 I see `runBacktest` but not `parseValues`. It might have been deleted too if it was in that block.
    // I'll add it here to be safe.

    const parseValues = (valStr) => {
        if (!valStr) return [];
        return valStr.split(',').map(v => {
            const trimmed = v.trim();
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

        const varyingKeys = Object.keys(optEnabled).filter(k => optEnabled[k]);

        const parameter_ranges = {};
        for (const key of varyingKeys) {
            const values = parseValues(optValues[key]);
            if (values.length === 0) {
                setOptError(`Error: Parameter '${key}' is enabled but has no values.`);
                return;
            }
            parameter_ranges[key] = values;
        }

        setIsOptimizing(true);
        setIsCancelling(false);
        setOptResults([]);
        setOptError(null);
        setOptProgress({ current: 0, total: 0 });

        try {
            // Sanitize Config for Base using currentConfig
            const base_config = { ...currentConfig };
            Object.keys(base_config).forEach(key => {
                if (base_config[key] === '' && DEFAULT_CONFIG[key] !== undefined) {
                    base_config[key] = DEFAULT_CONFIG[key];
                }
            });

            const payload = {
                symbol: currentSymbol || "SEC",
                interval: currentInterval,
                from_date: fromDate,
                initial_capital: initialCapital,
                parameter_ranges: parameter_ranges,
                base_config: base_config
            };

            const url = `/api/v1/strategies/${selectedStrategy.id}/optimize`;

            const response = await axios.post(url, payload);

            if (response.data.task_id) {
                const taskId = response.data.task_id;
                const totalCombos = response.data.total_combinations;
                setOptProgress({ current: 0, total: totalCombos });
                setCurrentOptTaskId(taskId);

                let isComplete = false;
                while (!isComplete) {
                    await new Promise(resolve => setTimeout(resolve, 1000));

                    try {
                        const statusRes = await axios.get(`/api/v1/strategies/optimize/status/${taskId}`);
                        const statusData = statusRes.data;

                        setOptProgress({
                            current: statusData.progress_current,
                            total: statusData.progress_total
                        });

                        if (statusData.status === 'completed' || statusData.status === 'cancelled') {
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
                                    ...item.metrics
                                }));
                                setOptResults(formattedResults);
                                if (statusData.status === 'cancelled') setOptError("Optimization Cancelled (Partial Results)");
                            } else {
                                if (statusData.status === 'cancelled') setOptError("Optimization Cancelled (No Results)");
                                else {
                                    const failureMsg = resultData.failures ? resultData.failures.join('\n') : "";
                                    setOptError(`Optimization completed with 0 results.\n${failureMsg}`);
                                }
                            }
                            isComplete = true;
                        } else if (statusData.status === 'failed') {
                            setOptError(`Failed: ${statusData.message}`);
                            isComplete = true;
                        } else if (statusData.status === 'not_found') {
                            setOptError("Task Lost");
                            isComplete = true;
                        }
                    } catch (pollErr) { console.warn("Polling error", pollErr); }
                }
            } else {
                setOptError("Unexpected Sync Response");
            }
        } catch (error) {
            const msg = error.response?.data?.detail || error.message || "Unknown Error";
            setOptError(`Request Failed: ${msg}`);
        } finally {
            setIsOptimizing(false);
            setIsCancelling(false);
            setCurrentOptTaskId(null);
        }
    };

    const applyOptParams = (result) => {
        // Update the CONFIG for the ACTIVE TAB
        setConfigList(prev => {
            const newList = [...prev];
            if (activeTab >= 0 && activeTab < newList.length) {
                newList[activeTab] = { ...newList[activeTab], ...result.full_config };
            }
            return newList;
        });
        window.scrollTo({ top: 0, behavior: 'smooth' });
    };

    // Persistence Effects
    useEffect(() => {
        localStorage.setItem('lastInterval', currentInterval);
    }, [currentInterval]);

    useEffect(() => {
        if (selectedStrategy) {
            localStorage.setItem('lastStrategyId', selectedStrategy.id);
        }
    }, [selectedStrategy]);

    // Check Data Status
    useEffect(() => {
        checkDataStatus();
        setFetchMessage(null);
    }, [currentSymbol, currentInterval]);

    const checkDataStatus = async () => {
        try {
            const res = await axios.get(`/api/v1/market-data/status/${currentSymbol}`, {
                params: { interval: currentInterval }
            });
            setDataStatus(res.data);
            if (res.data.start_date) {
                const parts = res.data.start_date.split('.');
                if (parts.length === 3) {
                    setFromDate(`20${parts[0]}-${parts[1]}-${parts[2]}`);
                }
            }
        } catch (e) {
            console.error("Failed to check data status", e);
        }
    };

    const handleFetchData = async () => {
        setIsFetchingData(true);
        setFetchMessage(`Updating...`);
        try {
            const res = await axios.post(`/api/v1/market-data/fetch/${currentSymbol}`, {
                interval: currentInterval,
                days: 3650
            });
            const added = res.data.added;
            setFetchMessage(null);
            const resultMsg = added > 0 ? `Updated (+${added})` : `Up to date (+0)`;
            await checkDataStatus();
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

                            {/* TAB NAVIGATION */}
                            <div className="flex items-center gap-2 overflow-x-auto pb-2 scrollbar-hide">
                                {/* Integrated Tab (Leftmost) */}
                                <button
                                    onClick={() => setActiveTab(-1)}
                                    className={`px-4 py-2 rounded-lg text-sm font-bold whitespace-nowrap transition-all border ${activeTab === -1
                                        ? 'bg-gradient-to-r from-indigo-600 to-purple-600 text-white border-transparent shadow-lg shadow-purple-900/50'
                                        : 'bg-black/40 text-gray-400 border-white/10 hover:bg-white/5 hover:text-white'
                                        }`}
                                >
                                    Integrated Portfolio
                                </button>

                                <div className="w-px h-6 bg-white/10 mx-2"></div>

                                {/* Rank Tabs */}
                                {configList.map((_, index) => (
                                    <div key={index} className="relative group">
                                        <button
                                            onClick={() => setActiveTab(index)}
                                            className={`pl-4 pr-10 py-2 rounded-lg text-sm font-bold whitespace-nowrap transition-all border flex items-center gap-2 ${activeTab === index
                                                ? 'bg-blue-600 text-white border-blue-500 shadow-lg shadow-blue-900/50'
                                                : 'bg-black/40 text-gray-400 border-white/10 hover:bg-white/5 hover:text-white'
                                                }`}
                                        >
                                            <div className={`w-2 h-2 rounded-full ${configList[index].is_active ? 'bg-green-400 shadow-[0_0_8px_rgba(74,222,128,0.6)]' : 'bg-gray-600'}`} />
                                            Rank {index + 1}
                                        </button>
                                        {/* Remove Button (Only if > 1 tabs) */}
                                        {configList.length > 1 && (
                                            <button
                                                onClick={(e) => {
                                                    e.stopPropagation();
                                                    removeTab(index);
                                                }}
                                                className={`absolute right-2 top-1/2 -translate-y-1/2 text-xs w-4 h-4 rounded-full flex items-center justify-center transition-colors ${activeTab === index
                                                    ? 'text-white/50 hover:bg-white/20 hover:text-white'
                                                    : 'text-gray-600 hover:text-red-400'
                                                    }`}
                                            >
                                                ×
                                            </button>
                                        )}
                                    </div>
                                ))}

                                {/* Add Tab Button */}
                                <button
                                    onClick={addTab}
                                    className="w-8 h-8 rounded-lg bg-white/5 border border-white/10 hover:bg-white/10 flex items-center justify-center text-gray-400 hover:text-green-400 transition-all ml-1"
                                    title="Add Rank Slot"
                                >
                                    +
                                </button>
                            </div>


                            {/* Configuration Panel - Full Width & Prominent */}
                            <Card title={activeTab === -1 ? "Integrated Portfolio Configuration" : `Rank ${activeTab + 1} Configuration`} variant="major" className="border border-purple-500/50 shadow-lg shadow-purple-900/20">
                                {activeTab === -1 ? (
                                    <div className="h-[200px] flex flex-col items-center justify-center text-gray-500 space-y-4">
                                        <div className="w-16 h-16 rounded-full bg-white/5 flex items-center justify-center text-3xl opacity-50">
                                            📊
                                        </div>
                                        <p>Integrated Portfolio Analysis requires implementation of multi-symbol simulation engine.</p>
                                        <p className="text-sm opacity-60">Please configure individual Ranks first.</p>
                                    </div>
                                ) : (
                                    <div className="space-y-6">
                                        {/* Activation Toggle Header */}
                                        <div className={`flex justify-between items-center p-4 rounded-lg border transition-all ${currentConfig.is_active
                                            ? 'bg-green-900/10 border-green-500/30'
                                            : 'bg-white/5 border-white/10'
                                            }`}>
                                            <div>
                                                <h3 className={`font-bold flex items-center gap-2 ${currentConfig.is_active ? 'text-green-400' : 'text-gray-400'}`}>
                                                    <span className="text-lg">{currentConfig.is_active ? '🟢' : '⚪'}</span>
                                                    {currentConfig.is_active ? 'Active Strategy' : 'Draft Mode'}
                                                </h3>
                                                <p className="text-xs text-gray-500 mt-1">
                                                    {currentConfig.is_active
                                                        ? "Included in Integrated Portfolio Analysis."
                                                        : "Excluded from Portfolio. Use for isolated testing."}
                                                </p>
                                            </div>
                                            <label className="relative inline-flex items-center cursor-pointer">
                                                <input
                                                    type="checkbox"
                                                    className="sr-only peer"
                                                    checked={!!currentConfig.is_active}
                                                    onChange={(e) => handleConfigChange('is_active', e.target.checked)}
                                                />
                                                <div className="w-11 h-6 bg-gray-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-green-600"></div>
                                            </label>
                                        </div>

                                        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                                            {/* 1. Target Data */}
                                            <div>
                                                <h4 className="text-sm font-bold text-gray-300 mb-3 flex items-center gap-2">
                                                    <div className="w-6 h-6 rounded bg-blue-500/20 text-blue-400 flex items-center justify-center text-xs">1</div>
                                                    Target Asset
                                                </h4>
                                                <div className="bg-black/20 p-4 rounded-lg border border-white/5 h-full">
                                                    <SymbolSelector
                                                        currentSymbol={currentSymbol}
                                                        setCurrentSymbol={setCurrentSymbol}
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
                                    </div>
                                )}
                            </Card>

                            {/* Backtest Controls (Relocated) */}
                            <Card title="Backtest Settings & Execution" variant="major" className="border-t-4 border-t-blue-500">
                                <div className="flex flex-col gap-4">
                                    {/* Row 1: Data Interval & Status */}
                                    <div className="flex flex-col md:flex-row justify-between items-center gap-4 w-full">
                                        <div className="flex items-center gap-4 w-full md:w-auto">
                                            <div className="relative w-32">
                                                <label className="text-[10px] text-gray-500 absolute -top-1.5 left-2 bg-[#1e2029] px-1">Interval</label>
                                                <select
                                                    value={currentInterval}
                                                    onChange={(e) => setCurrentInterval(e.target.value)}
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
                                                    disabled={isFetchingData}
                                                    className={`px-3 py-1 rounded text-sm font-bold transition-all shadow-lg flex items-center gap-2 whitespace-nowrap disabled:opacity-50 ${fetchMessage && fetchMessage.includes("Updated") ? "bg-green-600 text-white" :
                                                        fetchMessage && fetchMessage.includes("Up to date") ? "bg-blue-600 text-white" :
                                                            "bg-amber-600 hover:bg-amber-500 text-white hover:shadow-amber-500/30"
                                                        }`}
                                                >
                                                    {isFetchingData ? 'Fetching...' :
                                                        fetchMessage ? fetchMessage : 'Update Data'}
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
                                                value={initialCapital.toLocaleString()}
                                                onChange={(e) => {
                                                    const rawValue = e.target.value.replace(/[^0-9]/g, '');
                                                    setInitialCapital(rawValue === '' ? 0 : parseInt(rawValue, 10));
                                                }}
                                                className="w-full bg-black/40 border border-white/10 rounded px-3 py-2 text-sm text-white focus:border-blue-500 outline-none"
                                            />
                                        </div>

                                        <div className="relative">
                                            <label className="text-[10px] text-gray-500 absolute -top-1.5 left-2 bg-[#1e2029] px-1">Start Date</label>
                                            <input
                                                type="date"
                                                value={fromDate}
                                                onChange={(e) => setFromDate(e.target.value)}
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
                                            disabled={isLoading || !selectedStrategy || !dataStatus.count}
                                            className="bg-blue-600 hover:bg-blue-500 text-white px-4 py-4 rounded-xl font-bold transition-all shadow-lg hover:shadow-blue-500/30 flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed disabled:bg-gray-700"
                                        >
                                            {isLoading ? (
                                                <>
                                                    <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                                                    Running...
                                                </>
                                            ) : (
                                                <>🚀 Run Backtest</>
                                            )}
                                        </button>
                                    </div>

                                    {/* Execution Status Feedback */}
                                    {(backtestStatus.status !== 'idle' || !backtestResult) && (
                                        <div className="mt-2 border-t border-white/5 pt-4">
                                            {backtestStatus.status === 'running' ? (
                                                <div className="flex items-center justify-center gap-3 py-4 text-blue-400">
                                                    <div className="w-5 h-5 border-2 border-current border-t-transparent rounded-full animate-spin"></div>
                                                    <span className="font-bold">{backtestStatus.message}</span>
                                                </div>
                                            ) : backtestStatus.status === 'error' ? (
                                                <div className="flex items-center justify-center gap-3 py-4 text-red-400">
                                                    <span className="text-xl">⚠️</span>
                                                    <span className="font-bold">{backtestStatus.message}</span>
                                                </div>
                                            ) : !backtestResult && (
                                                <div className="text-center text-gray-500 py-2 text-sm">
                                                    Ready to Backtest - Configure parameters above and click Run
                                                </div>
                                            )}
                                        </div>
                                    )}
                                </div>
                            </Card>

                            {/* VISUAL CHART SECTION (Dedicated) */}
                            {showChart && backtestResult && (
                                <div className="mb-6 animate-fade-in-down">
                                    <Card title="Visual Backtest Analysis">
                                        {backtestResult.ohlcv_data ? (
                                            <VisualBacktestChart
                                                data={backtestResult.ohlcv_data}
                                                trades={backtestResult.trades}
                                            />
                                        ) : (
                                            <div className="h-[200px] flex items-center justify-center text-gray-500">
                                                No visual data available.
                                            </div>
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
                                                    <div className="col-span-2 p-3 bg-white/5 rounded-lg">
                                                        <div className="text-xs text-gray-400">Max Drawdown</div>
                                                        <div className="text-xl font-bold text-red-400">{backtestResult.max_drawdown}</div>
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
                                                        <h4 className="text-sm font-bold text-gray-400 mb-2">Execution Logs</h4>
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
                                            {PARAM_DEFINITIONS.map((param) => (
                                                <div key={param.key} className={`p-3 rounded-lg border transition-colors ${optEnabled[param.key] ? 'bg-purple-900/20 border-purple-500/50' : 'bg-black/20 border-white/5'}`}>
                                                    <div className="flex items-center gap-2 mb-2">
                                                        <input
                                                            type="checkbox"
                                                            id={`opt-${param.key}`}
                                                            checked={!!optEnabled[param.key]}
                                                            onChange={(e) => handleOptEnableChange(param.key, e.target.checked)}
                                                            className="w-4 h-4 rounded border-gray-600 text-purple-600 focus:ring-purple-500 bg-gray-700"
                                                        />
                                                        <label htmlFor={`opt-${param.key}`} className={`text-xs font-bold ${optEnabled[param.key] ? 'text-purple-300' : 'text-gray-500'}`}>
                                                            {param.label}
                                                        </label>
                                                    </div>
                                                    {param.type === 'select' && optEnabled[param.key] ? (
                                                        <div className="relative">
                                                            <div
                                                                onClick={() => setActiveDropdown(activeDropdown === param.key ? null : param.key)}
                                                                className={`w-full bg-black/40 border rounded px-3 py-2 text-sm text-white cursor-pointer min-h-[38px] flex items-center justify-between ${activeDropdown === param.key ? 'border-purple-500 ring-1 ring-purple-500' : 'border-purple-500/30'
                                                                    }`}
                                                            >
                                                                <span className="truncate">
                                                                    {optValues[param.key] || <span className="text-gray-500">Select options...</span>}
                                                                </span>
                                                                <span className="text-gray-400 text-xs ml-2">▼</span>
                                                            </div>

                                                            {/* Dropdown Menu */}
                                                            {activeDropdown === param.key && (
                                                                <div className="absolute z-50 mt-1 w-full bg-[#1a1c23] border border-white/20 rounded-lg shadow-xl max-h-60 overflow-y-auto">
                                                                    {param.options.map(option => {
                                                                        const currentVals = (optValues[param.key] || '').split(',').map(v => v.trim()).filter(Boolean);
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
                                                            disabled={!optEnabled[param.key]}
                                                            className={`w-full bg-black/40 border rounded px-3 py-2 text-sm focus:outline-none transition-colors ${optEnabled[param.key]
                                                                ? 'border-purple-500/30 text-white focus:border-purple-500'
                                                                : 'border-white/5 text-gray-400 bg-white/5 cursor-not-allowed opacity-70'}`}
                                                            value={optEnabled[param.key] ? (optValues[param.key] || "") : (currentConfig[param.key] ?? "")}
                                                            onChange={(e) => handleOptValueChange(param.key, e.target.value)}
                                                        />
                                                    )}
                                                    {optEnabled[param.key] && (
                                                        <p className="text-[10px] text-gray-500 mt-1 truncate">
                                                            e.g. {param.placeholder}
                                                        </p>
                                                    )}
                                                </div>
                                            ))}
                                        </div>

                                        {/* Action */}
                                        <div className="flex gap-2">
                                            <button
                                                onClick={runOptimization}
                                                disabled={isOptimizing}
                                                className={`flex-1 bg-gradient-to-r from-purple-900 to-blue-900 hover:from-purple-800 hover:to-blue-800 py-3 rounded-lg font-bold text-white shadow-lg shadow-purple-900/40 transition-all flex justify-center items-center gap-2 ${isOptimizing ? 'cursor-not-allowed opacity-80' : ''}`}
                                            >
                                                {isOptimizing ? (
                                                    <>
                                                        <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                                                        {optProgress.total > 0
                                                            ? `Processing (${optProgress.current}/${optProgress.total})...`
                                                            : "Initializing..."}
                                                    </>
                                                ) : (
                                                    <>🧪 Start Optimization Analysis ({Object.values(optEnabled).filter(Boolean).length} Params)</>
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
                                                                <th className="p-3 text-center">Action</th>
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
                                                                .map((res, idx) => (
                                                                    <tr key={idx} className={`text-sm border-b border-white/5 hover:bg-white/5 transition-colors ${res.rank === 1 ? 'bg-green-500/10' : ''}`}>
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
                                                                        <td className="p-3 text-center">
                                                                            <button
                                                                                onClick={() => applyOptParams(res)}
                                                                                className="text-xs bg-white/10 hover:bg-white/20 px-2 py-1 rounded text-purple-300 transition-colors"
                                                                            >
                                                                                Apply
                                                                            </button>
                                                                        </td>
                                                                    </tr>
                                                                ))}
                                                        </tbody>
                                                    </table>
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                </div>
                            </Card>




                        </div>

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
            </div >

            {/* AI Generator Input - Fixed Bottom */}
            < Card className="shrink-0 mt-auto border-t border-white/10 bg-gradient-to-b from-[#1a1c23] to-[#111]" >
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
            </Card >
        </div >
    );
};

export default StrategyView;
