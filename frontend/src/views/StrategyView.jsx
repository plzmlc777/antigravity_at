import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar, Cell, ReferenceLine, ComposedChart, LabelList } from 'recharts';
import Card from '../components/common/Card';
import SymbolSelector from '../components/SymbolSelector';
import SymbolChip from '../components/SymbolChip';
import IntegratedAnalysis from '../components/IntegratedAnalysis';
import VisualBacktestChart from '../components/VisualBacktestChart';
import { saveStrategyResult, getStrategyResults, runIntegratedBacktest, fetchMarketData, getMarketDataStatus, getStrategyConfigs, syncStrategyConfigs, syncStrategyConfigsSelective, getAccountPreferences, updateLastSelectedStrategy, updateSymbolCompareSettings, updateExecutionMode } from '../api/client';
import { useWatchlist } from '../context/WatchlistContext';
import { useStrategyConfig } from '../hooks/useStrategyConfig';
import { isValidScope } from '../types/ConfigScope';
import { useMarketData } from '../context/MarketDataContext';
import ConfirmModal from '../components/ConfirmModal'; // Custom Modal
import LiveStrategyPanel from '../components/LiveStrategyPanel'; // Live Panel
import ActiveStrategiesPanel from '../components/ActiveStrategiesPanel';
import LiveHistoryList from '../components/LiveHistoryList';
import LiveReplayView from '../components/LiveReplayView';
import StrategyDetailModal from '../components/StrategyDetailModal';
import DynamicParameterForm from '../components/DynamicParameterForm';
import ParameterVersionManager from '../components/ParameterVersionManager';
import RankVersionSelector from '../components/RankVersionSelector';
import TabBadge from '../components/TabBadge';
import DateDropdown from '../components/DateDropdown';
import PerformanceStatsGrid from '../components/PerformanceStatsGrid';
import MonthlyAnalysisChart from '../components/MonthlyAnalysisChart';
import DualScrollContainer from '../components/DualScrollContainer';
import { STAT_COLUMNS, formatStatValue, getStatColor, shouldShowConditional, computeTotalStats, getVisibleColumns, parseStatValue, getOptValue, getOptVisibleColumns } from '../config/statsConfig';
import { EQUITY_DATE_KEY, EQUITY_VALUE_KEY } from '../config/chartConfig';
import { History as HistoryIcon, Activity, HelpCircle, ChevronRight, Settings, Rocket, Crosshair, Sparkles, Terminal, Save, Lock, Copy, ClipboardPaste, RefreshCw, Download, Upload } from 'lucide-react';
import { INTERVAL_OPTIONS, getIntervalLabel, INTERVAL_VALUES, DEFAULT_OPT_INTERVALS } from '../constants/intervals';

const generateUUID = () => {
    if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID();
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
        var r = Math.random() * 16 | 0, v = c == 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
};

// Defined outside component to prevent re-creation
// Defined outside component to prevent re-creation
// [Single Source of Truth] All strategy parameters defined here.
const PARAM_DEFINITIONS = [
    {
        key: 'start_time',
        label: 'Start Time',
        type: 'select',
        defaultValue: "09:00",
        defaultOptRange: "09:00, 09:30, 10:00",
        options: Array.from({ length: 14 }).map((_, i) => {
            const h = 9 + Math.floor(i / 2);
            const m = i % 2 === 0 ? "00" : "30";
            return `${h.toString().padStart(2, '0')}:${m}`;
        }),
        placeholder: '09:00, 09:30'
    },
    { key: 'delay_minutes', label: 'Delay (min)', type: 'number', defaultValue: 60, defaultOptRange: "30, 60, 90", placeholder: '5, 10, 15' },
    { key: 'direction', label: 'Direction', type: 'select', defaultValue: "fall", defaultOptRange: "rise, fall", options: ['rise', 'fall'], placeholder: 'rise, fall' },
    { key: 'target_percent', label: 'Target (%)', type: 'number', defaultValue: 0.2, defaultOptRange: "0.1, 0.2, 0.3, 0.5", placeholder: '1, 2, 3' },
    { key: 'safety_stop_percent', label: 'Stop Loss (%)', type: 'number', defaultValue: 10, defaultOptRange: "3, 5, 10", placeholder: '2, 3, 5' },
    { key: 'trailing_start_percent', label: 'Trail Start (%)', type: 'number', defaultValue: 1, defaultOptRange: "0.5, 1.0, 1.5", placeholder: '3, 5' },
    { key: 'trailing_stop_drop', label: 'Trail Drop (%)', type: 'number', defaultValue: 0, defaultOptRange: "0, 0.2, 0.5", placeholder: '1, 2' },
    {
        key: 'stop_time',
        label: 'Stop Time',
        type: 'select',
        defaultValue: "15:00",
        defaultOptRange: "14:30, 15:00, 15:20",
        options: Array.from({ length: 48 }).map((_, i) => {
            const h = Math.floor(i / 2);
            const m = i % 2 === 0 ? "00" : "30";
            return `${h.toString().padStart(2, '0')}:${m}`;
        }),
        placeholder: '15:00, 15:20'
    }
];

// Helper: Generate Defaults from Definitions
const generateDefaultConfig = () => {
    // 기본 시작일: 1년 전
    const oneYearAgo = new Date();
    oneYearAgo.setFullYear(oneYearAgo.getFullYear() - 1);
    const defaultFromDate = oneYearAgo.toISOString().split('T')[0]; // YYYY-MM-DD

    const config = {
        // System Defaults (Non-Param)
        initial_capital: 10000000,
        from_date: defaultFromDate,
        interval: "1m",
        symbol: "005930",
        betting_strategy: "fixed",
        uuid: null // Will be generated
    };

    // Merge Parameter Defaults
    PARAM_DEFINITIONS.forEach(p => {
        config[p.key] = p.defaultValue;
    });

    return config;
};

const generateDefaultOptValues = () => {
    const opts = {};
    PARAM_DEFINITIONS.forEach(p => {
        opts[p.key] = p.defaultOptRange;
    });
    return opts;
};

// Helper: Convert DB parameter_schema to PARAM_DEFINITIONS format
// This allows the optimization panel to use dynamic schema instead of hardcoded definitions
// IMPORTANT: Ensures that optimization panel and backtest settings use identical options
// (e.g., interval options must match for proper chart calculations during optimization)
const convertSchemaToParamDefs = (schema) => {
    if (!schema || !schema.fields) return PARAM_DEFINITIONS;

    const fields = schema.fields;

    // Handle both array and object formats
    const fieldArray = Array.isArray(fields) ? fields : Object.values(fields);

    return fieldArray.map(field => {
        const key = field.key || field.name;
        const def = {
            key,
            label: field.label || key,
            type: field.type || 'text',
            defaultValue: field.default || field.defaultValue,
            defaultOptRange: field.defaultOptRange || '',
            placeholder: field.placeholder || ''
        };

        // Handle select options - directly from schema to ensure consistency
        // Backtest Settings (DynamicParameterForm) and Optimization panel MUST use same options
        if (field.type === 'select' && field.options) {
            def.options = field.options; // Direct copy from schema ensures identical options
        } else if (field.type === 'time') {
            // Generate time options for time-type fields
            def.type = 'select';
            def.options = Array.from({ length: 48 }).map((_, i) => {
                const h = Math.floor(i / 2);
                const m = i % 2 === 0 ? "00" : "30";
                return `${h.toString().padStart(2, '0')}:${m}`;
            });
        }

        return def;
    });
};

const DEFAULT_CONFIG = generateDefaultConfig();

// 공통 ApplyButton 컴포넌트 - 중앙 집중화된 Apply/Saved 버튼
const ApplyButton = ({ onClick, disabled, feedback }) => (
    <button
        onClick={onClick}
        disabled={disabled}
        className={`px-4 py-2 rounded-lg text-xs font-bold transition-all shadow-sm flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed ${
            feedback === 'saved'
                ? 'bg-green-600/30 text-green-300 border border-green-500/30'
                : 'bg-blue-600 hover:bg-blue-500 text-white hover:shadow-blue-500/30 disabled:bg-gray-700'
        }`}
    >
        <Save size={14} />
        {feedback === 'saved' ? 'Saved!' : 'Apply'}
    </button>
);

// 공통 CopyPasteButtons 컴포넌트 - 중앙 집중화된 Copy/Paste 버튼
const CopyPasteButtons = ({ onCopy, onPaste, feedback, hasCopied, sourceLabel }) => (
    <div className="flex items-center gap-1">
        <button
            onClick={onCopy}
            className={`px-2 py-1 rounded text-xs font-medium transition-all flex items-center gap-1 ${
                feedback === 'copied'
                    ? 'bg-green-600/30 text-green-300 border border-green-500/30'
                    : 'bg-white/5 hover:bg-white/10 text-gray-400 hover:text-white'
            }`}
            title="Copy"
        >
            <Copy size={12} />
            {feedback === 'copied' ? '✓' : 'Copy'}
        </button>
        <button
            onClick={onPaste}
            disabled={!hasCopied}
            className={`px-2 py-1 rounded text-xs font-medium transition-all flex items-center gap-1 ${
                feedback === 'pasted'
                    ? 'bg-green-600/30 text-green-300 border border-green-500/30'
                    : hasCopied
                        ? 'bg-purple-600/30 hover:bg-purple-600/50 text-purple-300 border border-purple-500/30'
                        : 'bg-white/5 text-gray-500 cursor-not-allowed'
            }`}
            title={hasCopied ? `Paste from ${sourceLabel}` : 'No data copied'}
        >
            <ClipboardPaste size={12} />
            {feedback === 'pasted' ? '✓' : 'Paste'}
        </button>
    </div>
);

// 공통 ImportExportButtons 컴포넌트 - 중앙 집중화된 Import/Export 버튼
// feedback: 'exported' | 'imported' | 'importing' | 'error' | null
const ImportExportButtons = ({ onExport, onImport, feedback, disabled = false, errorMessage = '' }) => {
    const getImportButtonStyle = () => {
        switch (feedback) {
            case 'imported':
                return 'bg-green-600/30 text-green-300 border border-green-500/30';
            case 'importing':
                return 'bg-blue-600/30 text-blue-300 border border-blue-500/30 cursor-wait';
            case 'error':
                return 'bg-red-600/30 text-red-300 border border-red-500/30';
            default:
                return 'bg-white/5 hover:bg-white/10 text-gray-400 hover:text-white';
        }
    };

    const getImportLabel = () => {
        switch (feedback) {
            case 'imported':
                return '✓';
            case 'importing':
                return '...';
            case 'error':
                return '✗';
            default:
                return 'Import';
        }
    };

    return (
        <div className="flex items-center gap-1">
            <button
                onClick={onExport}
                disabled={disabled}
                className={`px-2 py-1 rounded text-xs font-medium transition-all flex items-center gap-1 ${
                    feedback === 'exported'
                        ? 'bg-green-600/30 text-green-300 border border-green-500/30'
                        : 'bg-white/5 hover:bg-white/10 text-gray-400 hover:text-white disabled:opacity-50 disabled:cursor-not-allowed'
                }`}
                title="Export to file"
            >
                <Download size={12} />
                {feedback === 'exported' ? '✓' : 'Export'}
            </button>
            <label
                className={`px-2 py-1 rounded text-xs font-medium transition-all flex items-center gap-1 ${
                    feedback === 'importing' ? 'cursor-wait' : 'cursor-pointer'
                } ${getImportButtonStyle()}`}
                title={feedback === 'error' && errorMessage ? errorMessage : 'Import from file'}
            >
                <Upload size={12} />
                {getImportLabel()}
                <input
                    type="file"
                    accept=".json"
                    onChange={onImport}
                    className="hidden"
                    disabled={feedback === 'importing'}
                />
            </label>
        </div>
    );
};
const DEFAULT_OPT_VALUES = generateDefaultOptValues();

// Generate UUID for Integrated View Persistence (strategy-specific)
const getIntegratedUUID = (strategyId) => `integrated-${strategyId || 'unknown'}`;

const StrategyView = () => {
    // 계좌 중심: 활성 계좌 ID 가져오기
    const { systemStatus } = useMarketData();
    const activeAccountId = systemStatus?.account_id || null;

    // Symbol State - Use shared watchlist context (synced with DB)
    const { currentSymbol, setCurrentSymbol, savedSymbols, setSavedSymbols } = useWatchlist();

    const [strategies, setStrategies] = useState([]);
    const [selectedStrategy, setSelectedStrategy] = useState(null);
    const [backtestResult, setBacktestResult] = useState(null);
    const [executionLogs, setExecutionLogs] = useState([]);
    const [isLoading, setIsLoading] = useState(false);
    const [showChart, setShowChart] = useState(false); // Toggle for Visual Chart
    const [activeDropdown, setActiveDropdown] = useState(null); // Key of the currently open optimization dropdown
    const [selectedHistoryId, setSelectedHistoryId] = useState(null); // For Live History

    // Integrated Analysis State - Added for v0.8.7
    const [showIntegratedAnalysis, setShowIntegratedAnalysis] = useState(false);
    const [integratedResults, setIntegratedResults] = useState(null);
    const [selectedVisualSymbol, setSelectedVisualSymbol] = useState(null); // For Multi-Symbol Analysis
    const [activeAnalysisTab, setActiveAnalysisTab] = useState('overview'); // 'overview' | 'rank_details'
    const [liveRankIndex, setLiveRankIndex] = useState(0); // Selected Rank Index for Live Tab
    const [isLiveRunning, setIsLiveRunning] = useState(false); // Live session running status (locks strategy change)
    const [executionMode, setExecutionMode] = useState(() => {
        const saved = localStorage.getItem('integratedExecutionMode');
        return saved || 'exclusive';
    }); // 'exclusive' | 'parallel' for Integrated backtest
    const [isDetailModalOpen, setIsDetailModalOpen] = useState(false);

    // Symbol Comparison State (with localStorage persistence)
    const [selectedCompareSymbols, setSelectedCompareSymbols] = useState(() => {
        try {
            const saved = localStorage.getItem('symbolCompare_selectedSymbols');
            return saved ? JSON.parse(saved) : [];
        } catch { return []; }
    });
    const [stockCompareResults, setStockCompareResults] = useState(() => {
        try {
            const saved = localStorage.getItem('symbolCompare_results');
            if (!saved) return [];
            const parsed = JSON.parse(saved);
            // Validate data has required fields (v2 format with all stats)
            if (parsed.length > 0 && parsed[0].stability_score === undefined) {
                console.log('[Compare] Clearing old format data from localStorage');
                localStorage.removeItem('symbolCompare_results');
                return [];
            }
            return parsed;
        } catch { return []; }
    });
    const [isStockComparing, setIsStockComparing] = useState(false); // Running status
    const [stockCompareProgress, setStockCompareProgress] = useState({ current: 0, total: 0, phase: 'data' });
    const [symbolCompareConfig, setSymbolCompareConfig] = useState(() => {
        try {
            const saved = localStorage.getItem('symbolCompare_config');
            return saved ? JSON.parse(saved) : null;
        } catch { return null; }
    });
    const [isSymbolCompareDirty, setIsSymbolCompareDirty] = useState(false); // Track unsaved changes
    const [compareSortConfig, setCompareSortConfig] = useState({ key: 'score', direction: 'desc' }); // Sort config for comparison results

    // Parameter Copy/Paste State
    const [copiedParams, setCopiedParams] = useState(null);
    const [copyPasteFeedback, setCopyPasteFeedback] = useState(null); // 'copied' | 'pasted' | null
    const [applyFeedback, setApplyFeedback] = useState(null); // 'saved' | null

    // Import/Export Feedback State
    const [assetImportExportFeedback, setAssetImportExportFeedback] = useState(null); // 'exported' | 'imported' | 'importing' | 'error' | null
    const [assetImportError, setAssetImportError] = useState('');
    const [paramImportExportFeedback, setParamImportExportFeedback] = useState(null); // 'exported' | 'imported' | 'importing' | 'error' | null
    const [paramImportError, setParamImportError] = useState('');

    // Dynamic Config State (Refactored for Multi-Symbol Tabs)
    // 커스텀 훅을 사용한 중앙 집중화된 설정 관리
    // ConfigScope(accountId + strategyId)를 함께 관리
    const {
        configList,
        setConfigList,
        isLoaded: isConfigLoaded,
        needsInit,       // 초기화 필요 플래그
        setNeedsInit,    // 플래그 리셋용
        saveConfigs,
        reloadConfigs,
        scope,           // ConfigScope: { accountId, strategyId }
        transformUiToDbConfig,  // UI → DB 변환 함수
        getDynamicDefaultConfig: getHookDefaultConfig
        // initDefaultList는 기존 함수 사용 (getDynamicOptValues 의존성)
    } = useStrategyConfig({
        selectedStrategy,
        accountId: activeAccountId,  // 계좌 중심: 활성 계좌 ID 전달
        defaultConfig: DEFAULT_CONFIG,
        generateUUID
    });
    const [confirmModal, setConfirmModal] = useState({
        isOpen: false,
        title: '',
        message: '',
        onConfirm: () => { },
        onCancel: null,
        isDanger: false,
        confirmText: 'Confirm',
        cancelText: 'Cancel'
    });

    const openConfirm = (title, message, onConfirm, isDanger = false, confirmText = 'Confirm', cancelText = 'Cancel', onCancel = null) => {
        setConfirmModal({
            isOpen: true,
            title,
            message,
            onConfirm,
            onCancel,
            isDanger,
            confirmText,
            cancelText
        });
    };

    const closeConfirm = () => {
        setConfirmModal(prev => ({ ...prev, isOpen: false }));
    };

    // Execution Log Helper
    const addLog = (message, level = 'info') => {
        const timestamp = new Date().toLocaleTimeString('ko-KR', {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            fractionalSecondDigits: 3
        });
        const newLog = { timestamp, message, level };
        setExecutionLogs(prev => [...prev.slice(-99), newLog]); // Keep last 100 logs
        console.log(`[${timestamp}] ${message}`); // Still log to console
    };

    const [activeTab, setActiveTab] = useState(() => {
        const saved = localStorage.getItem('strategyViewActiveTab');
        return saved !== null ? parseInt(saved, 10) : 0;
    });
    const [isDirty, setIsDirty] = useState(false); // Track unsaved configuration changes
    const [pendingTabSwitch, setPendingTabSwitch] = useState(null); // Store pending tab switch during confirmation
    const [pendingOptResult, setPendingOptResult] = useState(null); // Unsaved optimization result (tab_uuid -> resultData)

    useEffect(() => {
        localStorage.setItem('strategyViewActiveTab', activeTab);
    }, [activeTab]);
    // isConfigLoaded는 useStrategyConfig 훅에서 제공됨
    const lastInitializedStrategyRef = useRef(null); // Track which strategy schema was initialized for
    const capitalSaveTimeoutRef = useRef(null); // Debounce timeout for auto-saving capital changes in Live tab



    // Backtest Settings
    // const [fromDate, setFromDate] = useState(""); // YYYY-MM-DD
    // const [initialCapital, setInitialCapital] = useState(() => {
    //    const saved = localStorage.getItem('initialCapital');
    //    return saved ? parseInt(saved, 10) : 10000000;
    // });


    // Custom Confirmation Modal State


    // Note: currentSymbol and savedSymbols are now managed by WatchlistContext (synced with DB)

    // Save execution mode to DB (with localStorage fallback)
    useEffect(() => {
        localStorage.setItem('integratedExecutionMode', executionMode);
        // Sync to DB (debounced in API client)
        updateExecutionMode(executionMode).catch(e => {
            console.warn('Failed to save execution mode to DB:', e);
        });
    }, [executionMode]);

    // Persistence logic removed for initialCapital

    // [REFACTORED] 설정 로드 로직이 useStrategyConfig 훅으로 이동됨
    // 핵심 변경: 의존성 배열에 accountId 포함 → 계좌 전환 시에도 설정 자동 로드
    // 기존 코드: }, [selectedStrategy]);
    // 새 코드 (훅 내부): }, [selectedStrategy, accountId]);

    const initDefaultList = () => {
        console.log("[initDefaultList] Creating default Rank 1 tab (is_active: true)");
        setConfigList([{
            ...getDynamicDefaultConfig(),
            is_active: true,
            tabName: "Rank 1",
            uuid: generateUUID(),
            optEnabled: {},
            optValues: { ...getDynamicOptValues() }
        }]);
    };

    // needsInit 플래그 처리 - 훅에서 DB가 비어있을 때 호출
    useEffect(() => {
        if (needsInit && selectedStrategy) {
            console.log("[StrategyView] needsInit detected, configList.length:", configList.length);
            // 훅에서 이미 기본 설정을 생성했으면 initDefaultList 호출 생략
            if (configList.length === 0) {
                console.log("[StrategyView] configList empty, calling initDefaultList");
                initDefaultList();
            }
            setNeedsInit(false);
            setIsDirty(false);  // 초기화는 "변경"이 아니므로 dirty 리셋
        }
    }, [needsInit, selectedStrategy, configList.length]);

    // Save Strategy Config List on Change (Debounced DB Sync) - DISABLED (Manual Save with Apply button)
    // useEffect(() => {
    //     const timer = setTimeout(async () => {
    //         if (isConfigLoaded && selectedStrategy && configList.length > 0) {
    //             // Map UI Config to DB Schema
    //             const configsToSave = configList.map((cfg, index) => ({
    //                 tab_id: cfg.uuid,
    //                 strategy_id: selectedStrategy.id,
    //                 rank: index, // 0-based for list order
    //                 is_active: cfg.is_active !== false,
    //                 tab_name: cfg.tabName,
    //                 config_json: cfg
    //             }));

    //             try {
    //                 await syncStrategyConfigsSelective(selectedStrategy.id, configsToSave, true);
    //                 // console.log("Strategy configs saved to DB (Inactive tabs preserved)");
    //             } catch (e) {
    //                 console.error("Failed to save configs to DB", e);
    //             }
    //         }
    //     }, 1000); // 1s debounce

    //     return () => clearTimeout(timer);
    // }, [configList, selectedStrategy, isConfigLoaded]);

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

        const tabToDelete = configList[index];
        const tabName = tabToDelete?.tabName || `Tab ${index + 1}`;
        const tabType = tabToDelete?.is_active === false ? "Draft" : "Rank";

        openConfirm(
            `Delete "${tabName}"?`,
            `You are about to delete the ${tabType} tab "${tabName}".\n\nThis action cannot be undone and all configuration in this tab will be permanently lost.`,
            async () => {
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

                // Auto-save to DB after deletion (ConfigScope 사용)
                try {
                    const configsToSave = reLabeledList.map((cfg, idx) => transformUiToDbConfig(cfg, idx));
                    console.log("[Delete] Saving after tab deletion:", configsToSave.map(c => c.tab_name));
                    await syncStrategyConfigsSelective(scope.strategyId, configsToSave, false); // preserve_inactive=false to allow deletion
                    setIsDirty(false);
                } catch (err) {
                    console.error("Failed to save after deletion:", err);
                }
            },
            true // isDanger
        );
    };

    const handleConfigChange = (key, value) => {
        if (activeTab === -1) return; // Cannot edit in Integrated View

        // Handle full config replacement (e.g., from Parameter Version restore)
        if (typeof key === 'object' && key !== null && value === undefined) {
            const newConfig = key;
            if (activeTab === -3) {
                setSymbolCompareConfig(newConfig);
                setIsDirty(true);
                return;
            }
            const newList = [...configList];
            newList[activeTab] = newConfig;
            setConfigList(newList);
            setIsDirty(true);
            return;
        }

        // Validate from_date: Use DB data start date if available, otherwise 1 year back
        if (key === 'from_date' && value) {
            // Compare dates only (strip time component to avoid timezone issues)
            const selectedStr = value; // "YYYY-MM-DD"
            const today = new Date();

            // Use DB data start date if available, otherwise default to 1 year
            let minAllowedDate;
            let limitDesc;
            if (dataStatus?.start_date) {
                // Parse "YY.MM.DD" format
                const parts = dataStatus.start_date.split('.');
                if (parts.length === 3) {
                    const year = parseInt(parts[0]) + 2000;
                    const month = parseInt(parts[1]) - 1;
                    const day = parseInt(parts[2]);
                    minAllowedDate = new Date(year, month, day);
                    limitDesc = `available data (${dataStatus.start_date})`;
                }
            }
            if (!minAllowedDate) {
                minAllowedDate = new Date(today);
                minAllowedDate.setDate(minAllowedDate.getDate() - 365); // 1 year default
                limitDesc = "1 year (365 days)";
            }

            const minDateStr = minAllowedDate.toISOString().split('T')[0];
            if (selectedStr < minDateStr) {
                openConfirm(
                    "⚠️ Date Range Limit",
                    `Start date cannot be earlier than ${limitDesc}.\n\nMinimum allowed date: ${minDateStr}\n\nThe date has been adjusted automatically.`,
                    () => {}, // No action needed
                    true, // isDanger (shows warning style)
                    "OK",
                    "" // Hide cancel button
                );
                value = minDateStr;
            }
        }

        // Handle Symbol Compare tab separately
        if (activeTab === -3) {
            const baseConfig = symbolCompareConfig || configList[0] || getDynamicDefaultConfig();
            setSymbolCompareConfig({ ...baseConfig, [key]: value });
            setIsDirty(true);
            return;
        }

        const newList = [...configList];
        // Ensure we don't start with partial object if configList[activeTab] is missing
        const currentItem = newList[activeTab] || { ...getDynamicDefaultConfig(), is_active: true, tabName: `Rank ${activeTab + 1}` };
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
        setIsDirty(true); // Mark configuration as dirty (unsaved changes)
    };

    // Parameter Copy/Paste Handlers
    // Strategy parameters are determined from parameter_schema (no manual maintenance needed)
    const getStrategyParamNames = () => {
        const schema = selectedStrategy?.parameter_schema;
        if (!schema?.fields) return [];
        return schema.fields.map(f => f.name);
    };

    const handleCopyParams = () => {
        // Determine source config based on active tab
        let currentCfg;
        let sourceLabel;

        if (activeTab === -3) {
            // Symbol Compare tab - use fallback if symbolCompareConfig is null
            currentCfg = symbolCompareConfig || configList[0] || {};
            sourceLabel = 'Symbol Compare';
        } else if (activeTab >= 0 && configList[activeTab]) {
            // Rank tabs
            currentCfg = configList[activeTab];
            sourceLabel = currentCfg.tabName || `Tab ${activeTab + 1}`;
        } else {
            return;
        }

        if (!currentCfg) return;

        const paramsToCopy = {};

        // Copy only strategy parameters defined in schema (whitelist approach)
        const strategyParams = getStrategyParamNames();
        strategyParams.forEach(key => {
            if (key in currentCfg) {
                paramsToCopy[key] = currentCfg[key];
            }
        });

        setCopiedParams({
            params: paramsToCopy,
            sourceTab: sourceLabel,
            sourceSymbol: currentCfg.symbol || 'Multi',
            timestamp: Date.now()
        });

        // Show visual feedback
        setCopyPasteFeedback('copied');
        setTimeout(() => setCopyPasteFeedback(null), 2000);

        addLog(`📋 Parameters copied from ${sourceLabel}`, 'info');
    };

    const handlePasteParams = () => {
        if (!copiedParams) return;

        // Handle Symbol Compare tab (activeTab === -3)
        if (activeTab === -3) {
            const baseConfig = symbolCompareConfig || configList[0] || {};
            const newConfig = { ...baseConfig };

            // Merge copied params into Symbol Compare config
            Object.keys(copiedParams.params).forEach(key => {
                newConfig[key] = copiedParams.params[key];
            });

            setSymbolCompareConfig(newConfig);
            setIsSymbolCompareDirty(true);

            // Show visual feedback
            setCopyPasteFeedback('pasted');
            setTimeout(() => setCopyPasteFeedback(null), 2000);

            addLog(`📥 Parameters pasted from ${copiedParams.sourceTab} (${copiedParams.sourceSymbol})`, 'info');
            return;
        }

        // Handle Rank tabs (activeTab >= 0)
        if (activeTab < 0 || !configList[activeTab]) return;

        const newList = [...configList];
        const currentItem = { ...newList[activeTab] };

        // Merge copied params into current config (overwrite strategy params only)
        Object.keys(copiedParams.params).forEach(key => {
            currentItem[key] = copiedParams.params[key];
        });

        newList[activeTab] = currentItem;
        setConfigList(newList);
        setIsDirty(true);

        // Show visual feedback
        setCopyPasteFeedback('pasted');
        setTimeout(() => setCopyPasteFeedback(null), 2000);

        addLog(`📥 Parameters pasted from ${copiedParams.sourceTab} (${copiedParams.sourceSymbol})`, 'info');
    };

    // Target Asset Import/Export Handlers
    const handleExportAssets = () => {
        if (!savedSymbols || savedSymbols.length === 0) {
            addLog('⚠️ No symbols to export', 'warn');
            return;
        }

        // 계좌 별칭 (파일명에 사용)
        const accountAlias = (systemStatus?.account_name || 'Unknown').replace(/\s+/g, '_');

        const exportData = {
            type: 'target_assets',
            version: '1.0',
            exportedAt: new Date().toISOString(),
            accountName: systemStatus?.account_name,
            symbols: savedSymbols
        };

        const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `target_assets_${accountAlias}_${new Date().toISOString().split('T')[0]}.json`;
        a.click();
        URL.revokeObjectURL(url);

        setAssetImportExportFeedback('exported');
        setTimeout(() => setAssetImportExportFeedback(null), 2000);
        addLog(`📤 Exported ${savedSymbols.length} symbols`, 'info');
    };

    const handleImportAssets = (e) => {
        const file = e.target.files?.[0];
        if (!file) return;

        // Show loading state
        setAssetImportExportFeedback('importing');
        setAssetImportError('');

        const reader = new FileReader();
        reader.onload = async (event) => {
            try {
                const data = JSON.parse(event.target.result);

                // Validate format
                if (!data.type || data.type !== 'target_assets') {
                    const errMsg = 'Invalid file: missing or wrong "type" field (expected: target_assets)';
                    setAssetImportError(errMsg);
                    setAssetImportExportFeedback('error');
                    setTimeout(() => setAssetImportExportFeedback(null), 3000);
                    addLog(`⚠️ ${errMsg}`, 'error');
                    return;
                }

                if (!Array.isArray(data.symbols)) {
                    const errMsg = 'Invalid file: "symbols" must be an array';
                    setAssetImportError(errMsg);
                    setAssetImportExportFeedback('error');
                    setTimeout(() => setAssetImportExportFeedback(null), 3000);
                    addLog(`⚠️ ${errMsg}`, 'error');
                    return;
                }

                if (data.symbols.length === 0) {
                    const errMsg = 'Import file contains no symbols';
                    setAssetImportError(errMsg);
                    setAssetImportExportFeedback('error');
                    setTimeout(() => setAssetImportExportFeedback(null), 3000);
                    addLog(`⚠️ ${errMsg}`, 'error');
                    return;
                }

                // 1. 먼저 종목 코드만 즉시 표시
                const symbolsWithoutNames = data.symbols.map(s => ({
                    code: s.code,
                    name: s.name || ''  // 기존 이름이 있으면 유지
                }));
                setSavedSymbols(symbolsWithoutNames);
                addLog(`📥 Importing ${data.symbols.length} symbols...`, 'info');

                // 2. 종목명을 순차적으로 가져오기 (API 부하 방지를 위해 딜레이 적용)
                const DELAY_MS = 300;  // 종목 간 300ms 딜레이
                let fetchedCount = 0;

                for (let i = 0; i < data.symbols.length; i++) {
                    const sym = data.symbols[i];

                    // 이미 이름이 있으면 스킵
                    if (sym.name) {
                        fetchedCount++;
                        continue;
                    }

                    try {
                        const res = await axios.get(`/api/v1/market-data/info/${sym.code}`);
                        if (res.data.name && res.data.name !== sym.code) {
                            // 종목명 업데이트
                            setSavedSymbols(prev => prev.map(s =>
                                s.code === sym.code ? { ...s, name: res.data.name } : s
                            ));
                        }
                        fetchedCount++;
                    } catch (err) {
                        console.warn(`Failed to fetch name for ${sym.code}:`, err.message);
                    }

                    // 마지막이 아니면 딜레이
                    if (i < data.symbols.length - 1) {
                        await new Promise(resolve => setTimeout(resolve, DELAY_MS));
                    }
                }

                setAssetImportExportFeedback('imported');
                setTimeout(() => setAssetImportExportFeedback(null), 2000);
                addLog(`✅ Imported ${data.symbols.length} symbols (${fetchedCount} names fetched)`, 'info');
            } catch (err) {
                const errMsg = 'Failed to parse JSON file';
                setAssetImportError(errMsg);
                setAssetImportExportFeedback('error');
                setTimeout(() => setAssetImportExportFeedback(null), 3000);
                addLog(`⚠️ ${errMsg}: ${err.message}`, 'error');
            }
        };
        reader.onerror = () => {
            const errMsg = 'Failed to read file';
            setAssetImportError(errMsg);
            setAssetImportExportFeedback('error');
            setTimeout(() => setAssetImportExportFeedback(null), 3000);
            addLog(`⚠️ ${errMsg}`, 'error');
        };
        reader.readAsText(file);
        e.target.value = ''; // Reset input
    };

    // Parameters Import/Export Handlers
    const handleExportParams = () => {
        let currentCfg;
        let sourceLabel;

        if (activeTab === -3) {
            currentCfg = symbolCompareConfig || configList[0] || {};
            sourceLabel = 'SymbolCompare';
        } else if (activeTab >= 0 && configList[activeTab]) {
            currentCfg = configList[activeTab];
            sourceLabel = (currentCfg.tabName || `Tab${activeTab + 1}`).replace(/\s/g, '');
        } else {
            addLog('⚠️ No configuration to export', 'warn');
            return;
        }

        // 계좌 별칭 (파일명에 사용)
        const accountAlias = (systemStatus?.account_name || 'Unknown').replace(/\s+/g, '_');

        // Extract only strategy parameters
        const paramNames = getStrategyParamNames();
        const paramsToExport = {};
        paramNames.forEach(key => {
            if (key in currentCfg) {
                paramsToExport[key] = currentCfg[key];
            }
        });

        const exportData = {
            type: 'strategy_parameters',
            version: '1.0',
            exportedAt: new Date().toISOString(),
            accountName: systemStatus?.account_name,
            strategyId: selectedStrategy?.id || 'unknown',
            params: paramsToExport
        };

        const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `params_${accountAlias}_${selectedStrategy?.id || 'strategy'}_${sourceLabel}_${new Date().toISOString().split('T')[0]}.json`;
        a.click();
        URL.revokeObjectURL(url);

        setParamImportExportFeedback('exported');
        setTimeout(() => setParamImportExportFeedback(null), 2000);
        addLog(`📤 Exported parameters from ${sourceLabel}`, 'info');
    };

    const handleImportParams = (e) => {
        const file = e.target.files?.[0];
        if (!file) return;

        // Show loading state
        setParamImportExportFeedback('importing');
        setParamImportError('');

        const reader = new FileReader();
        reader.onload = (event) => {
            try {
                const data = JSON.parse(event.target.result);

                // Validate format - support two formats:
                // 1. Original: { type: 'strategy_parameters', params: {...} }
                // 2. Exported: { version: '...', strategy: '...', params: {...} }
                const isOriginalFormat = data.type === 'strategy_parameters';
                const isExportedFormat = data.version && data.strategy && data.params;

                if (!isOriginalFormat && !isExportedFormat) {
                    const errMsg = 'Invalid file format: expected "type: strategy_parameters" or exported format with "version", "strategy", and "params"';
                    setParamImportError(errMsg);
                    setParamImportExportFeedback('error');
                    setTimeout(() => setParamImportExportFeedback(null), 3000);
                    addLog(`⚠️ ${errMsg}`, 'error');
                    return;
                }

                if (!data.params || typeof data.params !== 'object') {
                    const errMsg = 'Invalid file: "params" field is missing or invalid';
                    setParamImportError(errMsg);
                    setParamImportExportFeedback('error');
                    setTimeout(() => setParamImportExportFeedback(null), 3000);
                    addLog(`⚠️ ${errMsg}`, 'error');
                    return;
                }

                if (Object.keys(data.params).length === 0) {
                    const errMsg = 'Import file contains no parameters';
                    setParamImportError(errMsg);
                    setParamImportExportFeedback('error');
                    setTimeout(() => setParamImportExportFeedback(null), 3000);
                    addLog(`⚠️ ${errMsg}`, 'error');
                    return;
                }

                // Apply imported params to current config
                if (activeTab === -3) {
                    const baseConfig = symbolCompareConfig || configList[0] || {};
                    const newConfig = { ...baseConfig, ...data.params };
                    setSymbolCompareConfig(newConfig);
                    setIsSymbolCompareDirty(true);
                } else if (activeTab >= 0 && configList[activeTab]) {
                    const newList = [...configList];
                    newList[activeTab] = { ...newList[activeTab], ...data.params };
                    setConfigList(newList);
                    setIsDirty(true);
                }

                setParamImportExportFeedback('imported');
                setTimeout(() => setParamImportExportFeedback(null), 2000);
                const strategyInfo = data.strategy ? ` from "${data.strategy}"` : '';
                const sourceInfo = data.sourceTab ? ` (${data.sourceTab})` : '';
                addLog(`📥 Imported parameters${strategyInfo}${sourceInfo} (${Object.keys(data.params).length} fields)`, 'info');
            } catch (err) {
                const errMsg = 'Failed to parse JSON file';
                setParamImportError(errMsg);
                setParamImportExportFeedback('error');
                setTimeout(() => setParamImportExportFeedback(null), 3000);
                addLog(`⚠️ ${errMsg}: ${err.message}`, 'error');
            }
        };
        reader.onerror = () => {
            const errMsg = 'Failed to read file';
            setParamImportError(errMsg);
            setParamImportExportFeedback('error');
            setTimeout(() => setParamImportExportFeedback(null), 3000);
            addLog(`⚠️ ${errMsg}`, 'error');
        };
        reader.readAsText(file);
        e.target.value = ''; // Reset input
    };

    // Helper to get current config for UI rendering
    // Build dynamic default config from selectedStrategy's schema if configList is empty
    const getDynamicDefaultConfig = () => {
        if (!selectedStrategy || !selectedStrategy.parameter_schema) {
            return DEFAULT_CONFIG;
        }

        const schema = selectedStrategy.parameter_schema;
        if (!schema.fields || schema.fields.length === 0) {
            return DEFAULT_CONFIG;
        }

        const dynamicDefault = {
            initial_capital: 10000000,
            from_date: "",
            interval: "30m",
            symbol: currentSymbol,
            betting_strategy: "fixed",
            uuid: null,
            is_active: true,
            tabName: "Rank 1"
        };

        schema.fields.forEach(field => {
            const key = field.key || field.name;
            if (field.default !== undefined) {
                dynamicDefault[key] = field.default;
            }
        });

        return dynamicDefault;
    };

    // Helper to build dynamic optimization default values from schema
    const getDynamicOptValues = () => {
        if (!selectedStrategy || !selectedStrategy.parameter_schema) {
            return DEFAULT_OPT_VALUES;
        }

        const schema = selectedStrategy.parameter_schema;
        if (!schema.fields || schema.fields.length === 0) {
            return DEFAULT_OPT_VALUES;
        }

        const dynamicOptValues = {};
        schema.fields.forEach(field => {
            const key = field.key || field.name;
            if (field.defaultOptRange !== undefined) {
                dynamicOptValues[key] = field.defaultOptRange;
            }
        });

        return dynamicOptValues;
    };

    // Initialize symbolCompareConfig from Rank 1 if null
    const getSymbolCompareConfig = () => {
        if (symbolCompareConfig) return symbolCompareConfig;
        // Initialize from Rank 1 or default
        const baseConfig = configList[0] || getDynamicDefaultConfig();
        return { ...baseConfig, symbol: '', tabName: 'Symbol Compare' };
    };

    const currentConfig = (activeTab >= 0 && configList[activeTab])
        ? configList[activeTab]
        : (activeTab === -3
            ? getSymbolCompareConfig()  // Symbol Compare tab
            : (activeTab === -2 && configList.length > 0 ? configList[0] : getDynamicDefaultConfig()));

    // Check Symbol Validity for UI
    const activeSymbol = currentConfig?.symbol || currentSymbol;
    const isSymbolValid = !!activeSymbol && activeSymbol.trim().length > 0;

    // DEBUG: Log symbol selection info to Execution Logs
    useEffect(() => {
        if (activeTab >= 0 && isConfigLoaded) {
            const finalSymbol = currentConfig?.symbol || currentSymbol;
            const match = savedSymbols?.some(s => s.code === finalSymbol);
            addLog(`🔍 [DEBUG] Symbol Selection: configSymbol=${currentConfig?.symbol}, contextSymbol=${currentSymbol}, finalSymbol=${finalSymbol}, match=${match}, savedCount=${savedSymbols?.length || 0}`, 'info');
        }
    }, [activeTab, isConfigLoaded, currentConfig?.symbol, currentSymbol, savedSymbols]);

    // 3. Persistence: Load Results when switching tabs
    useEffect(() => {
        console.log('[Persistence] useEffect triggered - activeTab:', activeTab, 'isConfigLoaded:', isConfigLoaded, 'strategyId:', selectedStrategy?.id);

        // Reset transient states
        setShowChart(false);
        setIsOptimizing(false);
        setIsCancelling(false);



        // Restore Results on Tab Change

        // If not loaded yet, wait
        if (!isConfigLoaded) {
            console.log('[Persistence] Skipping: isConfigLoaded is false');
            return;
        }

        let targetUUID = null;

        if (activeTab === -1) {
            targetUUID = getIntegratedUUID(selectedStrategy?.id);
            console.log('[Persistence] Integrated tab - UUID:', targetUUID, 'strategyId:', selectedStrategy?.id);
        } else {
            targetUUID = configList[activeTab]?.uuid;
            console.log('[Persistence] Rank tab', activeTab, '- UUID:', targetUUID);
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
            setShowChart(false); // Reset visual chart (saved results don't include visualization data)
            setBacktestStatus({ status: 'idle', message: 'Restoring history...' });

            try {
                const data = await getStrategyResults(targetUUID);
                console.log('[Persistence] Data Received for UUID', targetUUID, ':', data);
                console.log('[Persistence] data.backtest exists?', !!data.backtest);

                // Restore Backtest
                if (data.backtest) {
                    console.log('[Persistence] Restoring Backtest Data - total_return:', data.backtest.total_return);
                    setBacktestResult(data.backtest);
                    if (activeTab === -1) {
                        console.log('[Persistence] Setting integratedResults');
                        setIntegratedResults(data.backtest);
                    }
                    setBacktestStatus({ status: 'success', message: 'Result Restored' });
                } else {
                    console.log('[Persistence] No Backtest Data found for UUID:', targetUUID);
                    setBacktestStatus({ status: 'idle', message: 'Ready to Backtest' });
                }

                // Restore Optimization
                if (data.optimization && data.optimization.results) {
                    console.log('[Persistence] Restoring Optimization Data');
                    const formattedResults = data.optimization.results.map((item, index) => ({
                        ...(item.config || {}),
                        ...(item.metrics || {}), // Flatten metrics
                        return: item.total_return,
                        win_rate: item.win_rate,
                        trades: item.total_trades,
                        score: item.score,
                        full_config: item.config || {},
                        rank: item.rank > 0 ? item.rank : (index + 1) // Rank LAST to prevent override, with fallback
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
                console.error("[Persistence] Error details:", {
                    status: e.response?.status,
                    statusText: e.response?.statusText,
                    data: e.response?.data,
                    message: e.message
                });
                setBacktestStatus({ status: 'idle', message: 'Ready to Backtest' });
            }
        };

        restoreResults();
    }, [activeTab, isConfigLoaded, selectedStrategy?.id]); // Re-run on tab change or strategy change

    // 4. Persistence & Initialization
    useEffect(() => {
        setExecutionLogs([]); // Clear logs on page load/refresh
        fetchStrategies();
    }, []);

    const fetchStrategies = async () => {
        try {
            const res = await axios.get('/api/v1/strategies/list');
            setStrategies(res.data);

            if (res.data.length > 0) {
                // Try to restore last selected strategy from DB (계좌 중심)
                try {
                    const preferences = await getAccountPreferences();
                    const savedId = preferences?.last_selected_strategy_id;

                    if (savedId) {
                        const target = res.data.find(s => s.id === savedId);
                        if (target) {
                            setSelectedStrategy(target);
                        }
                    }
                    // Fallback to localStorage (마이그레이션 기간 동안)
                    else {
                        const localStorageId = localStorage.getItem('lastStrategyId');
                        if (localStorageId) {
                            const target = res.data.find(s => s.id === localStorageId);
                            if (target) {
                                setSelectedStrategy(target);
                                // DB에도 저장 (마이그레이션)
                                await updateLastSelectedStrategy(localStorageId).catch(e => console.warn('Failed to migrate strategy to DB:', e));
                            }
                        }
                    }

                    // Load execution mode from DB (with localStorage fallback)
                    if (preferences?.execution_mode) {
                        setExecutionMode(preferences.execution_mode);
                    }

                    // Load symbol compare settings from DB (with localStorage migration)
                    if (preferences?.symbol_compare_settings) {
                        const settings = preferences.symbol_compare_settings;
                        if (settings.selectedSymbols) setSelectedCompareSymbols(settings.selectedSymbols);
                        if (settings.results) setStockCompareResults(settings.results);
                        if (settings.config) setSymbolCompareConfig(settings.config);
                    }
                } catch (e) {
                    console.warn('Failed to load account preferences:', e);
                    // Fallback to localStorage
                    const localStorageId = localStorage.getItem('lastStrategyId');
                    if (localStorageId) {
                        const target = res.data.find(s => s.id === localStorageId);
                        if (target) {
                            setSelectedStrategy(target);
                        }
                    }
                }
            }
        } catch (e) {
            console.error(e);
        }
    };

    // Log schema information when strategy changes (NO configList initialization - handled by loadConfigs)
    useEffect(() => {
        if (!selectedStrategy || !selectedStrategy.parameter_schema) {
            return;
        }

        // Skip if we've already logged for this strategy
        if (lastInitializedStrategyRef.current === selectedStrategy.id) {
            return;
        }
        lastInitializedStrategyRef.current = selectedStrategy.id;

        const schema = selectedStrategy.parameter_schema;
        if (!schema.fields || schema.fields.length === 0) {
            addLog('❌ No schema.fields', 'error');
            return;
        }

        addLog(`✅ Schema loaded for: ${selectedStrategy.id}`, 'info');
        addLog(`📋 Schema has ${schema.fields.length} fields`, 'info');

        // Verify interval options are correctly loaded from schema
        const intervalField = schema.fields.find(f => (f.key || f.name) === 'interval');
        if (intervalField && intervalField.options) {
            addLog(`✅ Interval options: [${intervalField.options.join(', ')}]`, 'info');
        }

        // Log parameter defaults for verification
        addLog(`🔍 Schema parameter defaults:`, 'info');
        schema.fields.forEach(field => {
            const key = field.key || field.name;
            const defaultVal = field.default;
            const optRange = field.defaultOptRange;
            const options = field.options ? `options=[${field.options.join(', ')}]` : '';
            addLog(`  ${key}: default=${defaultVal}, optRange="${optRange}" ${options}`, 'info');
        });

        // NOTE: configList initialization is handled ONLY by loadConfigs useEffect
        // This prevents race conditions where schema useEffect overwrites DB-loaded configs
    }, [selectedStrategy?.id]); // Only trigger when strategy ID changes

    // Auto-Fetch Symbol Name if Missing or Same as Code
    useEffect(() => {
        const target = savedSymbols.find(s => s.code === currentSymbol);
        // Fetch if name is missing OR name equals code (invalid cached data)
        if (target && (!target.name || target.name === target.code)) {
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

    const runBacktest = async (strategyId, configOverride = null) => {
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
            // Determine Configuration to use (Override or Current State)
            const activeConfig = configOverride || currentConfig;

            // --- Single Symbol Backtest (Legacy) ---
            // Sanitize Config: Replace empty strings with defaults
            const cleanConfig = { ...activeConfig };
            Object.keys(cleanConfig).forEach(key => {
                if (cleanConfig[key] === '' && DEFAULT_CONFIG[key] !== undefined) {
                    cleanConfig[key] = DEFAULT_CONFIG[key];
                }
            });

            const payload = {
                symbol: activeConfig.symbol || currentSymbol, // Use config's symbol if available, else global
                from_date: activeConfig?.from_date || "",
                days: activeConfig?.days || 365, // Default to 365 days
                initial_capital: activeConfig?.initial_capital || 10000000,
                interval: activeConfig?.interval || "1m",
                config: cleanConfig
            };

            setBacktestStatus({ status: 'running', message: `Running Backtest on ${activeConfig.symbol || currentSymbol}...` });

            const res = await axios.post(`/api/v1/strategies/${strategyId}/backtest`, payload);
            setBacktestResult(res.data);
            setBacktestStatus({ status: 'success', message: 'Backtest Completed' });

            // Persistence
            if (activeConfig.uuid) {
                saveStrategyResult(activeConfig.uuid, 'backtest', res.data).catch(err => console.error("Failed to save backtest result", err));
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

    // Manual Save & Backtest (Apply button handler)
    const handleApplyConfig = async () => {
        if (!selectedStrategy || !isConfigLoaded || configList.length === 0) return;

        try {
            // 1. Save configuration to DB
            if (!isValidScope(scope)) {
                openConfirm("⚠️ No Active Account", "활성화된 계좌가 없습니다. Settings에서 계좌를 활성화해주세요.", () => {}, true);
                return;
            }

            // ConfigScope를 사용하여 configsToSave 생성
            const configsToSave = configList.map((cfg, index) => transformUiToDbConfig(cfg, index));

            // Debug: Log what we're saving
            console.log("[Apply] Saving configs:", configsToSave.map(c => ({
                tab_name: c.tab_name,
                is_active: c.is_active,
                account_id: c.account_id
            })));

            await syncStrategyConfigsSelective(scope.strategyId, configsToSave, true);
            console.log("Configuration saved to DB");

            // 2. Save pending optimization results if exists
            if (pendingOptResult) {
                await saveStrategyResult(pendingOptResult.tabUuid, 'optimization', pendingOptResult.data);
                addLog('💾 Optimization results saved to DB', 'info');
                setPendingOptResult(null);
            }

            // Clear dirty flag after successful save
            setIsDirty(false);

            // Visual feedback (Saved!)
            setApplyFeedback('saved');
            setTimeout(() => setApplyFeedback(null), 2000);

            // 3. Automatically trigger backtest
            if (activeTab !== -1 && selectedStrategy?.id) {
                await runBacktest(selectedStrategy.id);
            }
        } catch (e) {
            console.error("Failed to save configuration:", e);
            openConfirm("❌ Save Failed", `설정 저장에 실패했습니다.\n\n${e.message || "다시 시도해주세요."}`, () => {}, true);
        }
    };

    // Discard all changes (reload from DB)
    const handleDiscardChanges = async () => {
        if (!selectedStrategy) return;

        try {
            // 1. Reload configs from DB
            const savedList = await getStrategyConfigs(selectedStrategy.id);

            if (savedList && savedList.length > 0) {
                // Build dynamic default config from current strategy's schema
                let dynamicDefault = { ...DEFAULT_CONFIG };
                const schema = selectedStrategy?.parameter_schema;
                if (schema?.fields && schema.fields.length > 0) {
                    schema.fields.forEach(field => {
                        const key = field.key || field.name;
                        if (field.default !== undefined) {
                            dynamicDefault[key] = field.default;
                        }
                    });
                }

                const migratedList = savedList.map(cfg => {
                    let configData = cfg.config_json || {};
                    let mergedCfg = { ...dynamicDefault, ...configData };
                    mergedCfg.rank = cfg.rank;
                    mergedCfg.is_active = cfg.is_active === false ? false : true;
                    mergedCfg.tabName = cfg.tab_name;
                    mergedCfg.uuid = cfg.tab_id;
                    if (!mergedCfg.uuid) mergedCfg.uuid = generateUUID();
                    return mergedCfg;
                });

                setConfigList(migratedList);
            }

            // 2. Discard pending optimization results
            if (pendingOptResult) {
                setPendingOptResult(null);
            }

            // 3. Clear dirty flag
            setIsDirty(false);
            addLog('🔄 Changes discarded, reverted to saved state', 'info');
        } catch (e) {
            console.error("Failed to discard changes:", e);
            addLog('Failed to discard changes', 'error');
        }
    };

    // Tab Switch with Unsaved Changes Confirmation
    const handleTabSwitch = (newTabIndex) => {
        // Check for pending optimization results first
        if (pendingOptResult) {
            setPendingTabSwitch(newTabIndex);
            openConfirm(
                "📊 Unsaved Optimization Results",
                "You have unsaved optimization results.\n\nWould you like to save them before switching tabs?",
                async () => {
                    // Save & Switch
                    await savePendingOptResult();
                    setActiveTab(newTabIndex);
                    localStorage.setItem('strategyViewActiveTab', newTabIndex.toString());
                    setPendingTabSwitch(null);
                },
                false,
                "Save & Switch",
                "Discard & Switch",
                () => {
                    // Discard & Switch
                    discardPendingOptResult();
                    setActiveTab(newTabIndex);
                    localStorage.setItem('strategyViewActiveTab', newTabIndex.toString());
                    setPendingTabSwitch(null);
                }
            );
            return;
        }

        // If no unsaved changes, switch immediately
        if (!isDirty) {
            setActiveTab(newTabIndex);
            localStorage.setItem('strategyViewActiveTab', newTabIndex.toString());
            return;
        }

        // If there are unsaved changes, show confirmation
        setPendingTabSwitch(newTabIndex);
        openConfirm(
            "⚠️ Unsaved Changes",
            "You have unsaved configuration changes.\n\nWhat would you like to do?",
            async () => {
                // Save & Switch (ConfigScope 사용)
                try {
                    const configsToSave = configList.map((cfg, index) => transformUiToDbConfig(cfg, index));

                    // Debug: Log what we're saving
                    console.log("[TabSwitch Save] Saving configs:", configsToSave.map(c => ({
                        tab_name: c.tab_name,
                        is_active: c.is_active,
                        account_id: c.account_id
                    })));

                    await syncStrategyConfigsSelective(scope.strategyId, configsToSave, true);
                    console.log("Configuration saved before tab switch");
                    setIsDirty(false);
                    setActiveTab(newTabIndex);
                    localStorage.setItem('strategyViewActiveTab', newTabIndex.toString());
                    setPendingTabSwitch(null);
                } catch (e) {
                    console.error("Failed to save configuration:", e);
                    openConfirm("❌ Save Failed", `설정 저장에 실패했습니다. 탭 전환이 취소되었습니다.\n\n${e.message || ""}`, () => {}, true);
                    setPendingTabSwitch(null);
                }
            },
            false, // not danger
            "Save & Switch",
            "Discard & Switch",
            () => {
                // Discard & Switch
                setIsDirty(false);
                setActiveTab(newTabIndex);
                localStorage.setItem('strategyViewActiveTab', newTabIndex.toString());
                setPendingTabSwitch(null);
                // Reload config from configList to discard changes
                // (changes are already in configList, so no action needed)
            }
        );
    };

    // Strategy Change with Unsaved Changes Confirmation
    const handleStrategyChange = (newStrategy) => {
        // If no unsaved changes, change immediately
        if (!isDirty) {
            setSelectedStrategy(newStrategy);
            setBacktestResult(null);
            setIsDirty(false); // Reset dirty flag for new strategy
            return;
        }

        // If there are unsaved changes, show confirmation
        openConfirm(
            "⚠️ Unsaved Changes",
            "You have unsaved configuration changes.\n\nWhat would you like to do before switching strategies?",
            async () => {
                // Save & Switch Strategy (ConfigScope 사용)
                try {
                    const configsToSave = configList.map((cfg, index) => transformUiToDbConfig(cfg, index));

                    // Debug: Log what we're saving
                    console.log("[StrategyChange Save] Saving configs:", configsToSave.map(c => ({
                        tab_name: c.tab_name,
                        is_active: c.is_active,
                        account_id: c.account_id
                    })));

                    await syncStrategyConfigsSelective(scope.strategyId, configsToSave, true);
                    console.log("Configuration saved before strategy change");
                    setIsDirty(false);
                    setSelectedStrategy(newStrategy);
                    setBacktestResult(null);
                } catch (e) {
                    console.error("Failed to save configuration:", e);
                    openConfirm("❌ Save Failed", `설정 저장에 실패했습니다. 전략 변경이 취소되었습니다.\n\n${e.message || ""}`, () => {}, true);
                }
            },
            false, // not danger
            "Save & Switch",
            "Discard & Switch",
            () => {
                // Discard & Switch Strategy
                setIsDirty(false);
                setSelectedStrategy(newStrategy);
                setBacktestResult(null);
            }
        );
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
    const [isOptimizing, setIsOptimizing] = useState(false);
    const [optResults, setOptResults] = useState(null);
    const [optProgress, setOptProgress] = useState({ current: 0, total: 0 });
    const [optStatusMessage, setOptStatusMessage] = useState("");
    const [optError, setOptError] = useState(null);

    // State for Dynamic Optimization
    // Refactored to Per-Tab Config (Legacy Global State Removed)

    // DEFAULT_OPT_VALUES constant defined below...


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
                optValues: { ...(currentCfg.optValues || getDynamicOptValues()), [key]: value }
            };
            return next;
        });
    };

    const [currentOptTaskId, setCurrentOptTaskId] = useState(null);
    const [completedOptTaskId, setCompletedOptTaskId] = useState(null); // For CSV download

    // Sorting State
    const [sortConfig, setSortConfig] = useState({ key: 'rank', direction: 'asc' });

    const handleSort = (key) => {
        setSortConfig(current => ({
            key,
            direction: current.key === key && current.direction === 'asc' ? 'desc' : 'asc'
        }));
    };

    // Save Pending Optimization Results to DB
    const savePendingOptResult = async () => {
        if (!pendingOptResult) {
            addLog('No pending optimization results to save', 'warning');
            return;
        }
        try {
            await saveStrategyResult(pendingOptResult.tabUuid, 'optimization', pendingOptResult.data);
            addLog('💾 Optimization results saved to DB', 'info');
            setPendingOptResult(null);
        } catch (err) {
            console.error("Failed to save opt result", err);
            addLog('Failed to save optimization results', 'error');
        }
    };

    // Discard Pending Optimization Results
    const discardPendingOptResult = () => {
        setPendingOptResult(null);
        addLog('🗑️ Optimization results discarded', 'info');
    };

    // Export Optimization Results to CSV
    const exportOptResultsToCSV = () => {
        if (!optResults || optResults.length === 0) {
            addLog('No optimization results to export', 'error');
            return;
        }

        const esc = (v) => `"${String(v == null ? '' : v).replace(/"/g, '""')}"`;

        // Build headers: Rank + Parameter columns + Stat columns + Score
        const paramDefs = convertSchemaToParamDefs(selectedStrategy?.parameter_schema);
        const paramHeaders = paramDefs.map(p => p.key);
        const statHeaders = STAT_COLUMNS.map(col => col.key);
        const headers = ['Rank', ...paramHeaders, ...statHeaders, 'Score'];

        // Build rows
        const rows = optResults.map(result => {
            const paramValues = paramDefs.map(p => result[p.key] ?? '');
            const statValues = STAT_COLUMNS.map(col => {
                const dataKey = col.optKey || col.key;
                return result[dataKey] ?? '';
            });
            return [result.rank ?? '', ...paramValues, ...statValues, result.score ?? ''];
        });

        const csvContent = [headers, ...rows]
            .map(row => row.map(v => esc(v)).join(','))
            .join('\n');

        const BOM = '\uFEFF';
        const blob = new Blob([BOM + csvContent], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        const filename = `optimization_${selectedStrategy?.id}_${currentConfig?.symbol}_${new Date().toISOString().split('T')[0]}.csv`;
        link.download = filename;
        link.click();
        URL.revokeObjectURL(url);

        addLog(`Exported ${optResults.length} results to ${filename}`, 'success');
    };

    // Download FULL optimization results from backend (all combinations, not just top 200)
    const downloadFullOptResultsCSV = async () => {
        if (!completedOptTaskId) {
            addLog('No optimization task available for download', 'error');
            return;
        }

        try {
            const response = await axios.get(`/api/v1/strategies/optimize/download/${completedOptTaskId}`, {
                responseType: 'blob'
            });

            const blob = new Blob([response.data], { type: 'text/csv' });
            const url = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            const filename = `optimization_full_${selectedStrategy?.id}_${currentConfig?.symbol}_${new Date().toISOString().split('T')[0]}.csv`;
            link.download = filename;
            link.click();
            URL.revokeObjectURL(url);

            addLog(`Downloaded full optimization results (all combinations)`, 'success');
        } catch (error) {
            const msg = error.response?.status === 404
                ? 'CSV file not found. It may have been cleaned up.'
                : error.message;
            addLog(`Failed to download CSV: ${msg}`, 'error');
        }
    };

    // Helper: Parse parameter string
    const parseValues = (valStr) => {
        if (!valStr) return [];
        return valStr.split(',').map(v => {
            const trimmed = v.trim();
            // Fix: Do not parse as number if it looks like a time string (has colon)
            if (trimmed.includes(':')) return trimmed;

            // Fix: Do not parse as number if it looks like an interval (e.g., "1m", "5m", "1h", "1d")
            // Pattern: digits followed by letters (like "1m", "60m", "1h", "1d")
            if (/^\d+[a-zA-Z]+$/.test(trimmed)) return trimmed;

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
        const currentOptValues = currentConfig.optValues || getDynamicOptValues();

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
            // Log parsed values for verification
            addLog(`📊 Parsed ${key}: [${values.join(', ')}]`, 'info');
        }

        setIsOptimizing(true);
        setIsCancelling(false);
        setOptResults([]);
        setOptError(null);
        setOptStatusMessage("");
        setOptProgress({ current: 0, total: 0 }); // Reset

        try {
            // Sanitize Config for Base - Include ALL schema defaults first
            const base_config = {};

            // 1. First, populate with schema default values (so ALL params are included)
            const paramDefs = convertSchemaToParamDefs(selectedStrategy?.parameter_schema);
            paramDefs.forEach(param => {
                if (param.defaultValue !== undefined) {
                    base_config[param.key] = param.defaultValue;
                }
            });

            // 2. Overlay with currentConfig values (user-entered values take precedence)
            Object.keys(currentConfig).forEach(key => {
                if (currentConfig[key] !== undefined && currentConfig[key] !== '') {
                    base_config[key] = currentConfig[key];
                }
            });

            // 3. Fill any remaining empty values from DEFAULT_CONFIG
            Object.keys(base_config).forEach(key => {
                if (base_config[key] === '' && DEFAULT_CONFIG[key] !== undefined) {
                    base_config[key] = DEFAULT_CONFIG[key];
                }
            });

            const payload = {
                symbol: currentConfig.symbol || currentSymbol || "SEC", // Use config's symbol if available, else global
                interval: currentConfig?.interval || "1m", // Sync with Backtest (UI State)
                days: currentConfig?.days || 365, // Must match Backtest payload
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

                        if (statusData.message) {
                            setOptStatusMessage(statusData.message);
                        }

                        // Show partial results during optimization (live preview)
                        if (statusData.status === 'running' && statusData.partial_results && statusData.partial_results.length > 0) {
                            const formattedPartial = statusData.partial_results.map((item, index) => ({
                                ...item.config,
                                ...item.metrics,
                                return: item.total_return,
                                win_rate: item.win_rate,
                                trades: item.total_trades,
                                score: item.score,
                                full_config: item.config,
                                rank: item.rank > 0 ? item.rank : (index + 1),
                                _isPartial: true  // Mark as partial result
                            }));
                            setOptResults(formattedPartial);
                        }

                        if (statusData.status === 'completed' || statusData.status === 'cancelled') {
                            // Finished (or Cancelled)
                            const resultData = statusData.result;
                            if (resultData && resultData.results && resultData.results.length > 0) {
                                const formattedResults = resultData.results.map((item, index) => ({
                                    ...item.config,
                                    ...item.metrics, // Flatten metrics
                                    return: item.total_return,
                                    win_rate: item.win_rate,
                                    trades: item.total_trades,
                                    score: item.score,
                                    full_config: item.config,
                                    rank: item.rank > 0 ? item.rank : (index + 1) // Rank LAST to prevent override, with fallback
                                }));
                                setOptResults(formattedResults);
                                setCompletedOptTaskId(taskId); // For full CSV download

                                // Pending Save: Store in state, save to DB only on Apply/Tab switch confirmation
                                if (currentConfig.uuid && statusData.status === 'completed') {
                                    setPendingOptResult({
                                        tabUuid: currentConfig.uuid,
                                        data: resultData
                                    });
                                    addLog('✅ Optimization complete. Click "Save Results" or apply a config to save to DB.', 'info');
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

    // Save last selected strategy to DB (계좌 중심)
    useEffect(() => {
        if (selectedStrategy) {
            // Save to DB (primary)
            updateLastSelectedStrategy(selectedStrategy.id).catch(e => {
                console.warn('Failed to save strategy preference to DB:', e);
            });
            // Keep localStorage as fallback (캐싱)
            localStorage.setItem('lastStrategyId', selectedStrategy.id);
        }
    }, [selectedStrategy]);

    // Check Data Status
    useEffect(() => {
        if (!isConfigLoaded) return; // Prevent race condition before config loads
        if (activeTab < 0) return; // Only check for Rank tabs (not Live, Integrated, Symbol Compare)

        // Use currentConfig.symbol for data status check
        const symbolToCheck = currentConfig.symbol || currentSymbol;
        if (symbolToCheck) {
            checkDataStatus(symbolToCheck);
        }
        setFetchMessage(null);
    }, [currentConfig?.symbol, currentSymbol, isConfigLoaded, activeTab]); // activeTab 추가: Rank 탭 전환 시 from_date 자동 설정

    const checkDataStatus = async (symbol) => {
        try {
            // Always check 1m data status - higher timeframes are aggregated from 1m
            const data = await getMarketDataStatus(symbol, {
                interval: "1m"
            });
            setDataStatus(data);

            // Auto-set Start Date to Data Start (clamped to 1 year back)
            if (data.start_date) {
                // Server returns YY.MM.DD -> Convert to YYYY-MM-DD for input type="date"
                const parts = data.start_date.split('.');
                if (parts.length === 3) {
                    const yyyy = `20${parts[0]}`;
                    const mm = parts[1];
                    const dd = parts[2];
                    let newDate = `${yyyy}-${mm}-${dd}`;
                    // Clamp to 1 year back silently (no popup on auto-set)
                    const minDate = new Date();
                    minDate.setDate(minDate.getDate() - 365);
                    if (new Date(newDate) < minDate) {
                        newDate = minDate.toISOString().split('T')[0];
                    }
                    if (currentConfig?.from_date !== newDate) {
                        // 자동 설정은 isDirty를 트리거하지 않음 - 직접 configList 업데이트
                        if (activeTab >= 0 && activeTab < configList.length) {
                            const newList = [...configList];
                            newList[activeTab] = { ...newList[activeTab], from_date: newDate };
                            setConfigList(newList);
                            // isDirty는 설정하지 않음 - 자동 설정은 사용자 변경이 아님
                        }
                    }
                }
            }
        } catch (e) {
            console.error("Failed to check data status", e);
            setFetchMessage(`Status Error: ${e.message}`);
        }
    };

    const handleFetchData = async (backfill = false) => {
        setIsFetchingData(true);
        setFetchMessage(backfill ? `Backfilling...` : `Updating...`);
        const symbolToFetch = currentConfig.symbol || currentSymbol; // Use config's symbol
        try {
            // Always fetch 1m data - higher timeframes are aggregated from 1m on demand
            // backfill=true: Fetch full 2-year history even if partial data exists
            // backfill=false: Incremental update, stops when hitting existing data
            const res = await axios.post(`/api/v1/market-data/fetch/${symbolToFetch}`, {
                interval: "1m",
                days: 365, // Max 1 year (API limit)
                backfill: backfill
            });

            const data = res.data;
            const added = data.added;
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

    // Integrated Tab: Update Data for All Ranks
    const handleUpdateAllData = async () => {
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
                    // Always fetch 1m data - higher timeframes are aggregated from 1m on demand
                    const res = await axios.post(`/api/v1/market-data/fetch/${cfg.symbol}`, {
                        interval: "1m",
                        days: 365 // Max 1 year (API limit)
                    });
                    totalAdded += (res.data.added || 0);
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
    };

    // Symbol Comparison: Run backtest for multiple symbols with same strategy params
    const handleStockCompareBacktest = async () => {
        if (selectedCompareSymbols.length === 0) {
            addLog('No symbols selected for comparison', 'error');
            return;
        }

        // Use symbolCompareConfig if available, fallback to Rank 1
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
            // Step 1: Update chart data for all selected symbols
            // Add delay between API calls to avoid Kiwoom rate limiting
            const DATA_FETCH_DELAY_MS = 500; // 500ms delay between data fetches
            addLog(`Updating chart data for ${totalSymbols} symbols...`, 'info');
            let totalDataAdded = 0;
            for (let i = 0; i < totalSymbols; i++) {
                const symbol = selectedCompareSymbols[i];
                setStockCompareProgress({ current: i + 1, total: totalSymbols, phase: 'data' });
                try {
                    const res = await axios.post(`/api/v1/market-data/fetch/${symbol}`, {
                        interval: "1m",
                        days: 365
                    });
                    const added = res.data?.added || 0;
                    totalDataAdded += added;
                    if (added > 0) {
                        addLog(`${symbol}: +${added} candles updated`, 'info');
                    }
                } catch (err) {
                    console.warn(`Failed to update data for ${symbol}`, err);
                    addLog(`${symbol}: data update failed`, 'warning');
                }
                // Delay before next API call (skip delay after last item)
                if (i < totalSymbols - 1) {
                    await new Promise(resolve => setTimeout(resolve, DATA_FETCH_DELAY_MS));
                }
            }
            addLog(`Data update completed: +${totalDataAdded} total candles`, totalDataAdded > 0 ? 'success' : 'info');

            // Step 2: Run backtest for each symbol sequentially
            const BACKTEST_DELAY_MS = 200; // 200ms delay between backtests
            addLog(`Running backtests for ${totalSymbols} symbols...`, 'info');
            for (let i = 0; i < totalSymbols; i++) {
                const symbol = selectedCompareSymbols[i];
                setStockCompareProgress({ current: i + 1, total: totalSymbols, phase: 'backtest' });

                try {
                    const payload = {
                        symbol: symbol,
                        interval: baseConfig.interval || "1m",
                        days: baseConfig.days || 365,
                        from_date: baseConfig.from_date || "",
                        initial_capital: baseConfig.initial_capital || 10000000,
                        config: {
                            ...baseConfig,
                            symbol: symbol
                        }
                    };

                    const response = await axios.post(
                        `/api/v1/strategies/${selectedStrategy.id}/backtest`,
                        payload
                    );

                    const data = response.data;
                    const ret = parseFloat(String(data.total_return || 0).replace('%', '').replace(',', ''));
                    const wr = parseFloat(String(data.win_rate || 0).replace('%', ''));
                    const score = ret * (wr / 100);

                    // Extract ALL stats from STAT_COLUMNS (consistent with backtest results)
                    results.push({
                        symbol: symbol,
                        name: savedSymbols?.find(s => s.code === symbol)?.name || '',
                        // Core stats
                        total_return: data.total_return,
                        profit_factor: data.profit_factor,
                        win_rate: data.win_rate,
                        sharpe_ratio: data.sharpe_ratio,
                        // Trading activity
                        total_trades: data.total_trades,
                        stability_score: data.stability_score,
                        acceleration_score: data.acceleration_score,
                        activity_rate: data.activity_rate,
                        // PnL details
                        avg_pnl: data.avg_pnl,
                        avg_holding_time: data.avg_holding_time,
                        max_profit: data.max_profit,
                        max_loss: data.max_loss,
                        // Cycle metrics (may be null)
                        cycle_count: data.cycle_count,
                        cycle_avg_pnl: data.cycle_avg_pnl,
                        cycle_avg_hold: data.cycle_avg_hold,
                        cycle_max_hold: data.cycle_max_hold,
                        cycle_min_hold: data.cycle_min_hold,
                        // Max drawdown & score
                        max_drawdown: data.max_drawdown,
                        score: score
                    });

                    // Update results in real-time
                    setStockCompareResults([...results]);

                } catch (err) {
                    console.error(`Backtest failed for ${symbol}`, err);
                    results.push({
                        symbol: symbol,
                        name: savedSymbols?.find(s => s.code === symbol)?.name || '',
                        total_return: 'Error',
                        profit_factor: null,
                        win_rate: null,
                        sharpe_ratio: null,
                        total_trades: 0,
                        stability_score: null,
                        acceleration_score: null,
                        activity_rate: null,
                        avg_pnl: null,
                        avg_holding_time: null,
                        max_profit: null,
                        max_loss: null,
                        cycle_count: null,
                        cycle_avg_pnl: null,
                        cycle_avg_hold: null,
                        cycle_max_hold: null,
                        cycle_min_hold: null,
                        max_drawdown: null,
                        score: -999
                    });
                    setStockCompareResults([...results]);
                }

                // Delay before next backtest (skip delay after last item)
                if (i < totalSymbols - 1) {
                    await new Promise(resolve => setTimeout(resolve, BACKTEST_DELAY_MS));
                }
            }

            addLog(`Stock comparison completed: ${results.length} symbols tested`, 'success');
            setIsSymbolCompareDirty(true); // Mark as dirty after comparison

        } catch (e) {
            console.error("Symbol Comparison Failed", e);
            addLog(`Stock comparison failed: ${e.message}`, 'error');
        } finally {
            setIsStockComparing(false);
            setStockCompareProgress({ current: 0, total: 0, phase: 'data' });
        }
    };

    // Export Symbol Compare results to CSV
    const handleExportCompareResults = () => {
        if (stockCompareResults.length === 0) {
            addLog('No results to export', 'warning');
            return;
        }

        // Sort by score descending
        const sortedResults = [...stockCompareResults].sort((a, b) => b.score - a.score);

        // CSV header
        const headers = ['Rank', 'Symbol', 'Name', 'Total Return', 'Win Rate', 'Max DD', 'Trades', 'Profit Factor', 'Sharpe', 'Avg PnL', 'Score'];

        // CSV rows
        const rows = sortedResults.map((result, idx) => [
            idx + 1,
            result.symbol,
            result.name || '',
            parseStatValue(result.total_return) ?? result.total_return,
            parseStatValue(result.win_rate) ?? result.win_rate,
            parseStatValue(result.max_drawdown) ?? result.max_drawdown,
            result.total_trades,
            parseStatValue(result.profit_factor) ?? result.profit_factor,
            parseStatValue(result.sharpe_ratio) ?? result.sharpe_ratio,
            parseStatValue(result.avg_pnl) ?? result.avg_pnl,
            result.score?.toFixed(2) ?? ''
        ]);

        // Build CSV content
        const csvContent = [
            headers.join(','),
            ...rows.map(row => row.map(cell => {
                // Escape cells that contain commas or quotes
                const str = String(cell);
                if (str.includes(',') || str.includes('"') || str.includes('\n')) {
                    return `"${str.replace(/"/g, '""')}"`;
                }
                return str;
            }).join(','))
        ].join('\n');

        // Create and download file
        const blob = new Blob(['\uFEFF' + csvContent], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        const timestamp = new Date().toISOString().slice(0, 19).replace(/[:-]/g, '');
        link.download = `symbol_compare_${timestamp}.csv`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);

        addLog(`Exported ${sortedResults.length} results to CSV`, 'success');
    };

    // Apply Symbol Compare settings (save to DB with localStorage cache)
    const handleApplySymbolCompare = async () => {
        try {
            const settings = {
                selectedSymbols: selectedCompareSymbols,
                results: stockCompareResults,
                config: symbolCompareConfig
            };

            // Save to localStorage (cache)
            localStorage.setItem('symbolCompare_selectedSymbols', JSON.stringify(selectedCompareSymbols));
            localStorage.setItem('symbolCompare_results', JSON.stringify(stockCompareResults));
            if (symbolCompareConfig) {
                localStorage.setItem('symbolCompare_config', JSON.stringify(symbolCompareConfig));
            }

            // Save to DB
            await updateSymbolCompareSettings(settings);

            setIsSymbolCompareDirty(false);

            // Visual feedback
            setApplyFeedback('saved');
            setTimeout(() => setApplyFeedback(null), 2000);

            addLog('Symbol Compare settings saved to DB', 'success');
        } catch (e) {
            console.error('Failed to save Symbol Compare settings:', e);
            addLog('Failed to save settings (saved to cache only)', 'error');
        }
    };

    // Discard Symbol Compare changes (reload from DB/localStorage)
    const handleDiscardSymbolCompare = async () => {
        try {
            // Try to reload from DB first
            const preferences = await getAccountPreferences();
            if (preferences?.symbol_compare_settings) {
                const settings = preferences.symbol_compare_settings;
                setSelectedCompareSymbols(settings.selectedSymbols || []);
                setStockCompareResults(settings.results || []);
                setSymbolCompareConfig(settings.config || null);
            } else {
                // Fallback to localStorage
                const savedSymbols = localStorage.getItem('symbolCompare_selectedSymbols');
                const savedResults = localStorage.getItem('symbolCompare_results');
                const savedConfig = localStorage.getItem('symbolCompare_config');

                setSelectedCompareSymbols(savedSymbols ? JSON.parse(savedSymbols) : []);
                setStockCompareResults(savedResults ? JSON.parse(savedResults) : []);
                setSymbolCompareConfig(savedConfig ? JSON.parse(savedConfig) : null);
            }
            setIsSymbolCompareDirty(false);
            addLog('Symbol Compare settings restored', 'info');
        } catch (e) {
            console.error('Failed to restore Symbol Compare settings:', e);
            // Fallback to localStorage on error
            const savedSymbols = localStorage.getItem('symbolCompare_selectedSymbols');
            const savedResults = localStorage.getItem('symbolCompare_results');
            const savedConfig = localStorage.getItem('symbolCompare_config');

            setSelectedCompareSymbols(savedSymbols ? JSON.parse(savedSymbols) : []);
            setStockCompareResults(savedResults ? JSON.parse(savedResults) : []);
            setSymbolCompareConfig(savedConfig ? JSON.parse(savedConfig) : null);
            setIsSymbolCompareDirty(false);
        }
    };

    return (
        <div className="flex flex-col gap-6 pb-10">
            {/* Top Bar: Strategy Selector */}
            <div className="shrink-0 z-20 bg-white/5 border border-white/10 rounded-xl px-4 pt-4 pb-5 overflow-hidden">
                <div className="flex flex-col gap-3">
                    <h3 className="font-bold text-gray-200 text-sm flex items-center gap-2">
                        <HelpCircle size={14} className="text-gray-400" /> Strategy
                        {isLiveRunning && (
                            <span className="flex items-center gap-1 text-xs text-amber-400 bg-amber-500/10 px-2 py-0.5 rounded-full ml-2">
                                <Lock size={10} /> Live Running
                            </span>
                        )}
                    </h3>
                    <div className="flex flex-col md:flex-row items-center gap-4 w-full">
                        <div className="relative w-full md:max-w-md">
                            <select
                                value={selectedStrategy?.id || ''}
                                onChange={(e) => {
                                    if (!e.target.value) {
                                        // 플레이스홀더 선택 시 전략 선택 해제
                                        setSelectedStrategy(null);
                                        setBacktestResult(null);
                                        setIsDirty(false);
                                        localStorage.removeItem('lastStrategyId');
                                        return;
                                    }
                                    const strat = strategies.find(s => s.id === e.target.value);
                                    handleStrategyChange(strat);
                                }}
                                disabled={isLiveRunning}
                                className={`w-full bg-black/40 border rounded-lg px-4 py-3 appearance-none outline-none text-sm font-medium ${
                                    isLiveRunning
                                        ? 'border-amber-500/30 text-gray-500 cursor-not-allowed opacity-60'
                                        : 'border-white/20 text-white cursor-pointer focus:border-blue-500'
                                }`}
                            >
                                <option value="" className="bg-slate-900 text-gray-400">
                                    전략을 선택하세요
                                </option>
                                {strategies.map(strat => (
                                    <option key={strat.id} value={strat.id} className="bg-slate-900 text-white">
                                        {strat.name}
                                    </option>
                                ))}
                            </select>
                            <div className={`absolute right-4 top-1/2 -translate-y-1/2 pointer-events-none ${isLiveRunning ? 'text-gray-600' : 'text-gray-400'}`}>
                                {isLiveRunning ? <Lock size={14} /> : '▼'}
                            </div>
                        </div>
                        {isLiveRunning && (
                            <div className="flex items-center gap-2 text-xs text-amber-400 bg-amber-500/10 px-3 py-2 rounded-lg border border-amber-500/20">
                                <Lock size={12} />
                                <span>라이브 세션 실행 중 - 전략 변경 불가</span>
                            </div>
                        )}
                        {selectedStrategy && !isLiveRunning && (
                            <div className="hidden md:flex items-center gap-2 text-sm text-gray-400 border-l border-white/10 pl-4 h-10 flex-1">
                                <span className="flex-1 truncate">{selectedStrategy.description}</span>
                                <button
                                    onClick={() => setIsDetailModalOpen(true)}
                                    className="p-1.5 rounded-lg bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 hover:text-blue-300 transition-all group relative"
                                    title="View Detailed Strategy Specification"
                                >
                                    <HelpCircle size={16} />
                                    <span className="absolute bottom-full mb-2 left-1/2 -translate-x-1/2 bg-gray-900 text-white text-[10px] px-2 py-1 rounded opacity-0 group-hover:opacity-100 whitespace-nowrap pointer-events-none border border-white/10 shadow-xl">
                                        Detail Specs
                                    </span>
                                </button>
                            </div>
                        )}
                    </div>
                </div>
            </div>

            {/* Main Content Area (No Scroll Container) */}
            <div className="space-y-6 pb-20">
                {!selectedStrategy ? (
                    <div className="flex flex-col items-center justify-center p-20 text-gray-400 bg-white/5 border border-white/10 rounded-xl">
                        <Crosshair size={48} className="mb-4 text-blue-500/50" />
                        <p className="text-lg font-medium">전략을 선택해주세요</p>
                        <p className="text-sm text-gray-500 mt-2">위의 드롭다운에서 백테스트할 전략을 선택하세요</p>
                    </div>
                ) : !isConfigLoaded ? (
                    <div className="flex flex-col items-center justify-center p-20 text-gray-500">
                        <div className="w-10 h-10 border-4 border-blue-500/30 border-t-blue-500 rounded-full animate-spin mb-4"></div>
                        <p>Loading Strategy Configuration...</p>
                        <p className="text-xs text-gray-600 mt-2">Synchronizing with Database...</p>
                    </div>
                ) : configList.length > 0 ? (
                    <>

                        {/* SECTION 1: BACKTEST SIMULATION (Config + Execution + Results) */}
                        <div className="space-y-4">

                            <div className="bg-white/5 border border-white/10 rounded-xl px-4 pt-4 pb-5 mb-6 overflow-x-auto scrollbar-hide">
                            {/* Row 1: Main Tabs (Live, Integrated, Symbol Compare) */}
                            <div className="flex items-center gap-2 mb-3">
                                {/* Live Operation Tab */}
                                <button
                                    type="button"
                                    key="live-tab"
                                    onClick={(e) => { e.preventDefault(); handleTabSwitch(-2); }}
                                    className={`px-5 py-2.5 rounded-lg text-sm font-bold transition-all whitespace-nowrap flex items-center gap-2 border ${activeTab === -2
                                        ? 'bg-gradient-to-r from-red-600 to-rose-600 text-white border-red-400 shadow-[0_0_15px_rgba(225,29,72,0.4)] scale-105'
                                        : 'bg-gradient-to-r from-gray-800 to-gray-900 text-rose-500 border-rose-500/30 hover:border-rose-500 hover:text-rose-400 hover:shadow-[0_0_10px_rgba(225,29,72,0.2)]'
                                        }`}
                                >
                                    {activeTab === -2 && <span className="text-green-400 font-bold">✓</span>}
                                    <span className="text-lg">🔴</span>
                                    <Activity size={16} className={activeTab === -2 ? "animate-pulse" : ""} />
                                    <span>Live Operation</span>
                                    {/* Badge: Active Rank Count */}
                                    {configList.filter(c => c.is_active !== false).length > 0 && (
                                        <TabBadge
                                            count={configList.filter(c => c.is_active !== false).length}
                                            status={activeTab === -2 ? "running" : "success"}
                                            size="xs"
                                        />
                                    )}
                                </button>

                                {/* Workflow Arrow: Live → Portfolio */}
                                <div className="flex items-center mx-1 text-white/20 hover:text-white/40 transition-colors">
                                    <ChevronRight size={16} />
                                </div>

                                {/* Integrated Tab */}
                                <button
                                    onClick={() => handleTabSwitch(-1)}
                                    className={`px-5 py-2.5 rounded-lg text-sm font-bold transition-all whitespace-nowrap flex items-center gap-2 border ${activeTab === -1
                                        ? 'bg-gradient-to-r from-amber-500 to-orange-600 text-white border-amber-300 shadow-[0_0_15px_rgba(245,158,11,0.4)] scale-105'
                                        : 'bg-gradient-to-r from-gray-800 to-gray-900 text-amber-500 border-amber-500/30 hover:border-amber-500 hover:text-amber-400 hover:shadow-[0_0_10px_rgba(245,158,11,0.2)]'
                                        }`}
                                >
                                    {activeTab === -1 && <span className="text-green-400 font-bold">✓</span>}
                                    <span className="text-lg">💎</span>
                                    <span>Integrated Portfolio</span>
                                </button>

                                {/* Workflow Arrow: Portfolio → Symbol Compare */}
                                <div className="flex items-center mx-1 text-white/20 hover:text-white/40 transition-colors">
                                    <ChevronRight size={16} />
                                </div>

                                {/* Symbol Comparison Tab */}
                                <button
                                    onClick={() => handleTabSwitch(-3)}
                                    className={`px-5 py-2.5 rounded-lg text-sm font-bold transition-all whitespace-nowrap flex items-center gap-2 border ${activeTab === -3
                                        ? 'bg-gradient-to-r from-emerald-500 to-teal-600 text-white border-emerald-300 shadow-[0_0_15px_rgba(16,185,129,0.4)] scale-105'
                                        : 'bg-gradient-to-r from-gray-800 to-gray-900 text-emerald-500 border-emerald-500/30 hover:border-emerald-500 hover:text-emerald-400 hover:shadow-[0_0_10px_rgba(16,185,129,0.2)]'
                                        }`}
                                >
                                    {activeTab === -3 && <span className="text-green-400 font-bold">✓</span>}
                                    <span className="text-lg">📊</span>
                                    <span>Symbol Compare</span>
                                </button>
                            </div>

                            {/* Row 2: Rank/Draft Tabs */}
                            <div className="flex items-center gap-2 flex-wrap">
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
                                                onClick={() => handleTabSwitch(idx)}
                                                className={`group px-3 py-2 rounded-lg text-xs font-medium transition-all whitespace-nowrap flex items-center gap-2 border-2 ${isSelected
                                                    ? isActive
                                                        ? 'bg-blue-600 text-white border-yellow-400 shadow-lg shadow-blue-900/30'
                                                        : 'bg-gray-600 text-white border-yellow-400 shadow-lg'
                                                    : 'bg-white/5 text-gray-400 border-transparent hover:bg-white/10 hover:text-gray-200'
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

                                                {/* Selection Checkmark */}
                                                {isSelected && (
                                                    <span className="text-green-400 font-bold">✓</span>
                                                )}

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
                                    onClick={async () => {
                                        const newConfig = {
                                            ...getDynamicDefaultConfig(),
                                            is_active: false,
                                            tabName: `Draft ${configList.filter(c => c.is_active === false).length + 1}`,
                                            symbol: currentSymbol,
                                            uuid: generateUUID() // Generate UUID for new tab
                                        };
                                        const newList = [...configList, newConfig];
                                        setConfigList(newList);
                                        setActiveTab(newList.length - 1);
                                        localStorage.setItem('strategyViewActiveTab', (newList.length - 1).toString());

                                        // Auto-save to DB after adding new tab (ConfigScope 사용)
                                        try {
                                            const configsToSave = newList.map((cfg, idx) => transformUiToDbConfig(cfg, idx));
                                            console.log("[Add Tab] Saving new tab:", configsToSave.map(c => ({ name: c.tab_name, is_active: c.is_active })));
                                            await syncStrategyConfigsSelective(scope.strategyId, configsToSave, true);
                                            setIsDirty(false);
                                        } catch (err) {
                                            console.error("Failed to save new tab:", err);
                                        }
                                    }}
                                    className="px-3 py-2 rounded-lg bg-white/5 text-gray-400 hover:bg-white/10 hover:text-white transition-all"
                                >
                                    +
                                </button>
                            </div>
                            {/* Active tab indicator line */}
                            <div className="mt-3 pt-3 border-t border-white/10 flex items-center gap-2 text-xs text-gray-500">
                                <div className="w-1.5 h-1.5 rounded-full bg-blue-500/60 animate-pulse" />
                                <span>{activeTab === -2 ? 'Live Operation' : activeTab === -1 ? 'Integrated Portfolio' : activeTab === -3 ? 'Symbol Compare' : `Rank ${activeTab + 1}`} selected</span>
                            </div>
                            </div>

                            {activeTab === -1 && (
                                <div className="space-y-4 mb-6">
                                            {/* Section 1: Strategy Configurations Card */}
                                            <div className="[&>div]:mb-0">
                                                <ActiveStrategiesPanel
                                                    configList={configList}
                                                    savedSymbols={savedSymbols}
                                                    strategyId={selectedStrategy?.id}
                                                    parameterSchema={selectedStrategy?.parameter_schema}
                                                    onVersionChange={(idx, newParams, versionInfo) => {
                                                        // Update configList with new params from selected version
                                                        // IMPORTANT: Only apply strategy parameters, preserve metadata
                                                        const metadataFields = ['uuid', 'tabName', 'is_active', 'symbol', 'selected_version_id', 'selected_version_name', 'initial_capital', 'start_date'];
                                                        const parameterFields = selectedStrategy?.parameter_schema?.fields?.map(f => f.key || f.name) || [];

                                                        setConfigList(prev => {
                                                            const updated = [...prev];
                                                            if (updated[idx]) {
                                                                // Only copy parameter fields from newParams
                                                                const filteredParams = {};
                                                                parameterFields.forEach(key => {
                                                                    if (newParams[key] !== undefined) {
                                                                        filteredParams[key] = newParams[key];
                                                                    }
                                                                });

                                                                updated[idx] = {
                                                                    ...updated[idx],  // Preserve all existing fields (including is_active, tabName, etc.)
                                                                    ...filteredParams,  // Only apply strategy parameters
                                                                    selected_version_id: versionInfo.id,
                                                                    selected_version_name: versionInfo.version_name,
                                                                };
                                                            }
                                                            return updated;
                                                        });
                                                        setIsDirty(true);
                                                    }}
                                                />
                                            </div>



                                            {/* Section 2: Backtest Settings Card */}
                                            <div className="bg-white/5 border border-white/10 rounded-xl overflow-hidden">
                                                <div className="bg-white/5 px-4 py-3 border-b border-white/10">
                                                    <h3 className="font-bold text-gray-200 text-sm flex items-center gap-2"><Settings size={14} className="text-gray-400" /> Backtest Settings</h3>
                                                </div>
                                                <div className="px-4 py-4">
                                                {(() => {
                                                    const isIntegrated = activeTab === -1;
                                                    // If Integrated, inherit from Rank 1 (index 0). Fallback to DEFAULT if empty.
                                                    const displayConfig = isIntegrated ? (configList[0] || DEFAULT_CONFIG) : currentConfig;

                                                    // Calculate display capital for parallel mode
                                                    const activeConfigCount = configList.filter(c => c.is_active).length;
                                                    const rank1Capital = displayConfig?.initial_capital || 10000000;
                                                    const displayCapital = (isIntegrated && executionMode === 'parallel')
                                                        ? rank1Capital * activeConfigCount
                                                        : rank1Capital;

                                                    return (
                                                        <div className="flex flex-wrap gap-6">
                                                            <div className="text-left">
                                                                <label className="text-xs text-gray-400 mb-1 block">
                                                                    {isIntegrated && executionMode === 'parallel'
                                                                        ? <>Total Capital <span className="text-purple-400">({rank1Capital.toLocaleString()} × {activeConfigCount} Ranks)</span></>
                                                                        : <>Initial Capital {isIntegrated && <span className="text-blue-400">(Inherited from Rank 1)</span>}</>
                                                                    }
                                                                </label>
                                                                <input
                                                                    type="text"
                                                                    value={displayCapital.toLocaleString()}
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
                                                                    Start Date {dataStatus?.start_date ? `(${dataStatus.start_date}~)` : '(Max 1yr)'} {isIntegrated && <span className="text-blue-400">(Inherited from Rank 1)</span>}
                                                                </label>
                                                                <DateDropdown
                                                                    value={displayConfig?.from_date || ""}
                                                                    onChange={(dateStr) => {
                                                                        if (isIntegrated) return;
                                                                        handleConfigChange('from_date', dateStr);
                                                                    }}
                                                                    disabled={isIntegrated}
                                                                    minDate={dataStatus?.start_date ? (() => {
                                                                        const parts = dataStatus.start_date.split('.');
                                                                        if (parts.length === 3) {
                                                                            const year = parseInt(parts[0]) + 2000;
                                                                            const month = parseInt(parts[1]) - 1;
                                                                            const day = parseInt(parts[2]);
                                                                            return new Date(year, month, day);
                                                                        }
                                                                        return undefined;
                                                                    })() : undefined}
                                                                />
                                                            </div>
                                                            {isIntegrated && (
                                                                <div className="text-left">
                                                                    <label className="text-xs text-gray-400 mb-1 block">
                                                                        Execution Mode
                                                                    </label>
                                                                    <select
                                                                        value={executionMode}
                                                                        onChange={(e) => setExecutionMode(e.target.value)}
                                                                        className="bg-black/40 border border-white/20 rounded px-3 py-2 text-white w-44 text-center appearance-none cursor-pointer focus:border-blue-500"
                                                                    >
                                                                        <option value="exclusive">Exclusive (Waterfall)</option>
                                                                        <option value="parallel">Parallel (Equal Split)</option>
                                                                    </select>
                                                                    <p className="text-[10px] text-gray-500 mt-1">
                                                                        {executionMode === 'exclusive'
                                                                            ? 'Ranks evaluated sequentially, first signal wins'
                                                                            : 'All Ranks run simultaneously (each gets Rank1 capital)'}
                                                                    </p>
                                                                </div>
                                                            )}
                                                        </div>
                                                    );
                                                })()}
                                                </div>
                                            </div>

                                            {/* Section 3: Actions Card */}
                                            <div className="bg-white/5 border border-white/10 rounded-xl overflow-hidden">
                                                <div className="bg-white/5 px-4 py-3 border-b border-white/10">
                                                    <h3 className="font-bold text-gray-200 text-sm flex items-center gap-2"><Rocket size={14} className="text-gray-400" /> Actions</h3>
                                                </div>
                                                <div className="px-4 py-4">
                                                <div className="flex gap-4">
                                                    <button
                                                        onClick={() => setShowChart(!showChart)}
                                                        disabled={!integratedResults?.multi_ohlcv_data}
                                                        className={`px-6 py-4 rounded-xl font-bold transition-all shadow-lg flex items-center justify-center gap-2 ${!integratedResults?.multi_ohlcv_data
                                                            ? 'bg-gray-800 text-gray-600 cursor-not-allowed opacity-50'
                                                            : 'bg-purple-600 text-white hover:bg-purple-500 shadow-purple-500/30'
                                                            }`}
                                                    >
                                                        {showChart ? '📉 Hide Analysis' : '📊 Visual Analysis'}
                                                    </button>
                                                    <button
                                                        onClick={handleUpdateAllData}
                                                        disabled={isFetchingData}
                                                        className={`px-6 py-4 rounded-xl font-bold transition-all shadow-lg flex items-center justify-center gap-2 text-white ${fetchMessage && (fetchMessage.includes("All Active") || fetchMessage.includes("Updating"))
                                                            ? "bg-green-600"
                                                            : "bg-amber-600 hover:bg-amber-500 shadow-amber-500/30"
                                                            } disabled:opacity-50 disabled:cursor-not-allowed`}
                                                    >
                                                        {fetchMessage && (fetchMessage.includes("All Active") || fetchMessage.includes("Updating"))
                                                            ? fetchMessage
                                                            : <><span className="text-2xl">📥</span> Update All Data</>
                                                        }
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

                                                                // Apply Global Overrides & Format for Backend IntegratedConfig Schema
                                                                // Backend expects: { id, rank, config: {}, strategy_id, symbol }
                                                                const validConfigs = activeConfigs.map(cfg => {
                                                                    const mergedConfig = {
                                                                        ...cfg,
                                                                        betting_strategy: globalBettingStrategy,
                                                                        // Ensure Symbol is present in config
                                                                        symbol: cfg.symbol || currentSymbol
                                                                    };

                                                                    return {
                                                                        id: cfg.uuid || generateUUID(),
                                                                        rank: cfg.rank || 999,
                                                                        strategy_id: selectedStrategy?.id || "time_momentum", // Default or current
                                                                        symbol: mergedConfig.symbol,
                                                                        config: mergedConfig // Pass entire flat config as nested dict
                                                                    };
                                                                });

                                                                // Calculate days based on fromDate safely
                                                                let diffDays = 365; // Default
                                                                if (leaderConfig?.from_date) {
                                                                    const startDate = new Date(leaderConfig.from_date);
                                                                    const today = new Date();
                                                                    if (!isNaN(startDate.getTime())) {
                                                                        const diffTime = Math.abs(today - startDate);
                                                                        diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
                                                                    }
                                                                }

                                                                // Calculate total capital based on execution mode
                                                                const rank1Capital = leaderConfig?.initial_capital || 10000000;
                                                                const totalCapital = executionMode === 'parallel'
                                                                    ? rank1Capital * activeConfigs.length  // Parallel: Rank1 capital × number of active ranks
                                                                    : rank1Capital;                         // Exclusive: Just Rank1 capital

                                                                const result = await axios.post('/api/v1/strategies/integrated-backtest', {
                                                                    configs: validConfigs,
                                                                    symbol: currentSymbol || "KRW-BTC", // Use global or default
                                                                    interval: leaderConfig?.interval || "1m", // Use selected interval
                                                                    days: diffDays > 0 ? diffDays : 365,
                                                                    from_date: leaderConfig?.from_date || "",
                                                                    initial_capital: totalCapital,
                                                                    execution_mode: executionMode // 'exclusive' or 'parallel'
                                                                });

                                                                // Update Result State and Store for Visualization
                                                                setBacktestResult(result.data);
                                                                setIntegratedResults(result.data); // Store full result for visualization
                                                                setBacktestStatus({ status: 'completed', message: 'Simulation Complete' });

                                                                // Save Result for Persistence (strategy-specific UUID)
                                                                const integratedUUID = getIntegratedUUID(selectedStrategy?.id);
                                                                console.log('[Integrated] Saving result with UUID:', integratedUUID);
                                                                saveStrategyResult(integratedUUID, 'backtest', result.data)
                                                                    .then(() => console.log('[Integrated] Result saved successfully'))
                                                                    .catch(err => console.error("Failed to save Integrated Result", err));

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
                                                <p className="text-xs text-gray-500 mt-3">
                                                    {executionMode === 'exclusive'
                                                        ? '* Simulates the Waterfall execution logic (Rank 1 → Rank 2 priority) on historical data.'
                                                        : '* Simulates Parallel execution: Each Rank gets Rank 1 capital (Total = Rank1 × Active Ranks).'}
                                                </p>

                                            {/* Integrated Backtest Results (inside Actions card) */}
                                            {(backtestStatus.status !== 'idle' || !backtestResult) && (
                                                <div className="mt-4">
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
                                                            Click 'Run Integrated Backtest' to see results here.
                                                        </div>
                                                    )}
                                                </div>
                                            )}

                                            {showChart && backtestResult && backtestResult.multi_ohlcv_data && (
                                                <div className="mt-4 animate-fade-in-down">
                                                    <Card title={backtestResult.strategy_id.includes('Integrated') ? "Integrated Replay Analysis" : "Visual Backtest Analysis"}>
                                                        {backtestResult.strategy_id.includes('Integrated') ? (
                                                            <IntegratedAnalysis
                                                                mode="backtest"
                                                                trades={backtestResult.trades || []}
                                                                backtestResult={backtestResult}
                                                                strategiesConfig={configList.filter(c => c.is_active !== false)}
                                                                savedSymbols={savedSymbols || []}
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

                                            {backtestResult && (
                                                <div className="space-y-6 mt-4">
                                                    <div className="space-y-6">
                                                        <div className="flex gap-4 mb-4">
                                                            <button
                                                                onClick={() => setActiveAnalysisTab('overview')}
                                                                className={`px-4 py-2 rounded-lg text-sm font-bold transition-all ${activeAnalysisTab === 'overview'
                                                                    ? 'bg-purple-600 text-white shadow-lg'
                                                                    : 'bg-white/5 text-gray-400 hover:bg-white/10'}`}
                                                            >
                                                                Overview
                                                            </button>
                                                            <button
                                                                onClick={() => setActiveAnalysisTab('rank_details')}
                                                                className={`px-4 py-2 rounded-lg text-sm font-bold transition-all ${activeAnalysisTab === 'rank_details'
                                                                    ? 'bg-purple-600 text-white shadow-lg'
                                                                    : 'bg-white/5 text-gray-400 hover:bg-white/10'}`}
                                                            >
                                                                Rank Details
                                                            </button>
                                                        </div>

                                                        <Card title={activeAnalysisTab === 'overview' ? "Performance Stats" : "Rank Performance Breakdown"}>
                                                            {activeAnalysisTab === 'overview' ? (
                                                                <div className="space-y-4">
                                                                    <PerformanceStatsGrid stats={backtestResult} />
                                                                    <MonthlyAnalysisChart bucketStats={backtestResult.bucket_stats} decileStats={backtestResult.decile_stats} />
                                                                </div>
                                                            ) : (
                                                                <div className="overflow-x-auto">
                                                                    {backtestResult.rank_stats_list && backtestResult.rank_stats_list.length > 0 ? (
                                                                        (() => {
                                                                            const visibleCols = getVisibleColumns(backtestResult);
                                                                            const totalStats = computeTotalStats(backtestResult.rank_stats_list);
                                                                            const renderCell = (data, col, opacity = '') => {
                                                                                const value = data[col.key];
                                                                                const colorClass = getStatColor(value, col) + (opacity ? `/${opacity}` : '');
                                                                                const formatted = formatStatValue(value, col);
                                                                                const prefix = col.signed && typeof value === 'number' && value > 0 ? '+' : '';
                                                                                const align = col.lastColumn ? ' text-right' : '';
                                                                                const bold = col.bold ? ' font-bold' : '';
                                                                                return (
                                                                                    <td key={col.key} className={`p-3${bold}${align} ${colorClass}`}>{prefix}{formatted}</td>
                                                                                );
                                                                            };
                                                                            return (
                                                                                <table className="w-full text-left border-collapse whitespace-nowrap">
                                                                                    <thead>
                                                                                        <tr className="border-b border-white/10 text-xs text-gray-400 uppercase">
                                                                                            <th className="p-3 sticky left-0 bg-[#0f1115] z-10 shadow-r">Rank</th>
                                                                                            {visibleCols.map(col => (
                                                                                                <th key={col.key} className={`p-3${col.lastColumn ? ' text-right' : ''}`}>{col.tableLabel || col.label}</th>
                                                                                            ))}
                                                                                        </tr>
                                                                                    </thead>
                                                                                    <tbody className="text-sm">
                                                                                        {backtestResult.rank_stats_list.map((stat, idx) => (
                                                                                            <tr key={idx} className="border-b border-white/5 hover:bg-white/5 transition-colors">
                                                                                                <td className="p-3 font-bold text-white sticky left-0 bg-[#0f1115] z-10 shadow-r">#{stat.rank}</td>
                                                                                                {visibleCols.map(col => renderCell(stat, col))}
                                                                                            </tr>
                                                                                        ))}
                                                                                    </tbody>
                                                                                    <tfoot className="text-sm border-t-2 border-white/20">
                                                                                        <tr className="bg-[#1a1d24]/50 border-b border-white/10 font-bold text-gray-300">
                                                                                            <td className="p-3 sticky left-0 bg-[#15181e] z-10 shadow-r">TOTAL (Sum/W.Avg)</td>
                                                                                            {visibleCols.map(col => renderCell(totalStats, col, '80'))}
                                                                                        </tr>
                                                                                        <tr className="bg-[#2d3748] font-bold text-white border-t border-purple-500/30">
                                                                                            <td className="p-3 text-purple-300 sticky left-0 bg-[#2d3748] z-10 shadow-r">OVERVIEW</td>
                                                                                            {visibleCols.map(col => renderCell(backtestResult, col))}
                                                                                        </tr>
                                                                                    </tfoot>
                                                                                </table>
                                                                            );
                                                                        })()
                                                                    ) : (
                                                                        <div className="py-12 text-center">
                                                                            <div className="text-gray-500 italic mb-2">No rank details available</div>
                                                                        </div>
                                                                    )}
                                                                </div>
                                                            )}
                                                        </Card>
                                                    </div>
                                                </div>
                                            )}

                                                </div>
                                            </div>

                                </div>
                            )}

                            {activeTab !== -2 && activeTab !== -1 && (
                                <div className="bg-white/5 border border-white/10 rounded-xl overflow-hidden">
                                    <div className="bg-white/5 px-4 py-3 border-b border-white/10 flex items-center justify-between">
                                        <h3 className="font-bold text-gray-200 text-sm flex items-center gap-2">
                                            <Crosshair size={14} className="text-gray-400" /> Configuration
                                        </h3>
                                        <div className="flex items-center gap-4">
                                            {/* Apply/Discard - Only for Rank tabs */}
                                            {activeTab >= 0 && (
                                                <div className="flex items-center gap-2">
                                                    <ApplyButton
                                                        onClick={handleApplyConfig}
                                                        disabled={isLoading || !selectedStrategy}
                                                        feedback={applyFeedback}
                                                    />
                                                    {(isDirty || pendingOptResult) && (
                                                        <button
                                                            onClick={handleDiscardChanges}
                                                            disabled={isLoading}
                                                            className="bg-gray-600 hover:bg-gray-500 text-white px-4 py-2 rounded-lg text-xs font-bold transition-all flex items-center gap-2 disabled:opacity-50"
                                                        >
                                                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                                                            </svg>
                                                            Discard
                                                        </button>
                                                    )}
                                                </div>
                                            )}
                                            {/* Apply/Discard/Reset - Only for Symbol Compare */}
                                            {activeTab === -3 && (
                                                <div className="flex items-center gap-2">
                                                    <ApplyButton
                                                        onClick={handleApplySymbolCompare}
                                                        disabled={isStockComparing}
                                                        feedback={applyFeedback}
                                                    />
                                                    {isSymbolCompareDirty && (
                                                        <button
                                                            onClick={handleDiscardSymbolCompare}
                                                            disabled={isStockComparing}
                                                            className="bg-gray-600 hover:bg-gray-500 text-white px-4 py-2 rounded-lg text-xs font-bold transition-all flex items-center gap-2 disabled:opacity-50"
                                                        >
                                                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                                                            </svg>
                                                            Discard
                                                        </button>
                                                    )}
                                                    <button
                                                        onClick={() => {
                                                            if (configList[0]) {
                                                                setSymbolCompareConfig({ ...configList[0], symbol: '', tabName: 'Symbol Compare' });
                                                                setIsSymbolCompareDirty(true);
                                                                addLog('Reset to Rank 1 parameters', 'success');
                                                            }
                                                        }}
                                                        className="bg-amber-600 hover:bg-amber-500 text-white px-4 py-2 rounded-lg text-xs font-bold transition-all shadow-sm flex items-center gap-2"
                                                    >
                                                        <RefreshCw size={14} />
                                                        Reset to Rank 1
                                                    </button>
                                                    <span className="text-[10px] uppercase font-bold tracking-wider text-blue-400">
                                                        Symbol Compare Mode
                                                    </span>
                                                </div>
                                            )}
                                            {/* Active/Draft Toggle - Only for Rank tabs */}
                                            {activeTab >= 0 && (
                                                <>
                                                    <span className={`text-[10px] uppercase font-bold tracking-wider ${currentConfig.is_active !== false ? 'text-green-400' : 'text-gray-500'}`}>
                                                        {currentConfig.is_active !== false ? 'Active Strategy' : 'Draft Mode'}
                                                    </span>
                                                    <button
                                                        onClick={(e) => {
                                                            e.stopPropagation();
                                                            handleConfigChange('is_active', currentConfig.is_active === false);
                                                        }}
                                                        className={`w-8 h-4 rounded-full p-0.5 transition-colors ${currentConfig.is_active !== false ? 'bg-green-500' : 'bg-gray-600'}`}
                                                    >
                                                        <div className={`w-3 h-3 bg-white rounded-full shadow-sm transform transition-transform ${currentConfig.is_active !== false ? 'translate-x-4' : 'translate-x-0'}`} />
                                                    </button>
                                                </>
                                            )}
                                        </div>
                                    </div>
                                    <div className="px-4 py-4 space-y-4">
                                        {/* Row 1: Target Asset */}
                                        <div>
                                            <div className="flex items-center justify-between mb-3">
                                                <h4 className="text-sm font-bold text-gray-300 flex items-center gap-2">
                                                    Target Asset
                                                    {activeTab === -3 && <span className="text-xs text-blue-400">(Multi-Select for Compare)</span>}
                                                </h4>
                                                <ImportExportButtons
                                                    onExport={handleExportAssets}
                                                    onImport={handleImportAssets}
                                                    feedback={assetImportExportFeedback}
                                                    disabled={!savedSymbols || savedSymbols.length === 0}
                                                    errorMessage={assetImportError}
                                                />
                                            </div>
                                            <div className="bg-black/20 p-4 rounded-lg border border-white/5 space-y-4">
                                                {/* SymbolSelector - shared for both Rank and Symbol Compare */}
                                                <SymbolSelector
                                                    currentSymbol={activeTab === -3 ? '' : (currentConfig?.symbol || currentSymbol)} // No single selection for Symbol Compare
                                                    setCurrentSymbol={activeTab === -3 ? () => {} : (newSymbol) => handleConfigChange('symbol', newSymbol)}
                                                    savedSymbols={savedSymbols}
                                                    setSavedSymbols={setSavedSymbols}
                                                    hideSymbolList={activeTab === -3} // Hide symbol list for Symbol Compare (uses multi-select below)
                                                />

                                                {/* Multi-Select UI - Only for Symbol Compare */}
                                                {activeTab === -3 && savedSymbols && savedSymbols.length > 0 && (
                                                    <div className="border-t border-white/10 pt-4">
                                                        <div className="flex items-center justify-between mb-3">
                                                            <span className="text-xs text-gray-400 font-medium">Select Symbols for Comparison</span>
                                                            <div className="flex items-center gap-2">
                                                                <button
                                                                    onClick={() => setSelectedCompareSymbols(savedSymbols.map(s => s.code))}
                                                                    className="px-2 py-1 bg-emerald-600 hover:bg-emerald-700 text-white text-xs rounded transition-colors"
                                                                >
                                                                    Select All ({savedSymbols.length})
                                                                </button>
                                                                <button
                                                                    onClick={() => setSelectedCompareSymbols([])}
                                                                    className="px-2 py-1 bg-gray-600 hover:bg-gray-700 text-white text-xs rounded transition-colors"
                                                                >
                                                                    Clear
                                                                </button>
                                                                <span className="text-xs text-gray-500">
                                                                    {selectedCompareSymbols.length} / {savedSymbols.length}
                                                                </span>
                                                            </div>
                                                        </div>
                                                        <div className="flex flex-wrap gap-2">
                                                            {savedSymbols.map(item => (
                                                                <SymbolChip
                                                                    key={item.code}
                                                                    symbol={item}
                                                                    showCheckbox={true}
                                                                    isChecked={selectedCompareSymbols.includes(item.code)}
                                                                    onCheckChange={(checked) => {
                                                                        if (checked) {
                                                                            setSelectedCompareSymbols(prev => [...prev, item.code]);
                                                                        } else {
                                                                            setSelectedCompareSymbols(prev => prev.filter(s => s !== item.code));
                                                                        }
                                                                    }}
                                                                    onDelete={(code) => {
                                                                        setSavedSymbols(prev => prev.filter(s => s.code !== code));
                                                                        setSelectedCompareSymbols(prev => prev.filter(s => s !== code));
                                                                    }}
                                                                />
                                                            ))}
                                                        </div>
                                                        {savedSymbols.length === 0 && (
                                                            <p className="text-gray-500 text-sm text-center py-2">
                                                                Add symbols above to enable comparison
                                                            </p>
                                                        )}
                                                    </div>
                                                )}
                                            </div>
                                        </div>

                                        {/* Row 2: Parameters */}
                                        <div>
                                            <div className="flex items-center justify-between mb-3">
                                                <div className="flex items-center gap-4">
                                                    <h4 className="text-sm font-bold text-gray-300">Parameters</h4>
                                                    <RankVersionSelector
                                                        strategyId={selectedStrategy?.id}
                                                        symbol={currentConfig?.symbol || currentSymbol}
                                                        currentParams={currentConfig}
                                                        selectedVersionId={currentConfig?.selected_version_id}
                                                        parameterSchema={selectedStrategy?.parameter_schema}
                                                        onVersionSelect={(params, versionInfo) => {
                                                            // Only apply strategy parameters, preserve metadata
                                                            const parameterFields = selectedStrategy?.parameter_schema?.fields?.map(f => f.key || f.name) || [];
                                                            const filteredParams = {};
                                                            parameterFields.forEach(key => {
                                                                if (params[key] !== undefined) {
                                                                    filteredParams[key] = params[key];
                                                                }
                                                            });

                                                            handleConfigChange({
                                                                ...currentConfig,
                                                                ...filteredParams,
                                                                selected_version_id: versionInfo.id,
                                                                selected_version_name: versionInfo.version_name,
                                                            });
                                                        }}
                                                    />
                                                </div>
                                                <div className="flex items-center gap-3">
                                                    <CopyPasteButtons
                                                        onCopy={handleCopyParams}
                                                        onPaste={handlePasteParams}
                                                        feedback={copyPasteFeedback}
                                                        hasCopied={!!copiedParams}
                                                        sourceLabel={copiedParams?.sourceTab}
                                                    />
                                                    <div className="w-px h-4 bg-white/10" />
                                                    <ImportExportButtons
                                                        onExport={handleExportParams}
                                                        onImport={handleImportParams}
                                                        feedback={paramImportExportFeedback}
                                                        errorMessage={paramImportError}
                                                    />
                                                </div>
                                            </div>
                                            <div className="bg-black/20 p-4 rounded-lg border border-white/5">
                                                {/* Dynamic Parameter Form - Renders based on strategy's parameter_schema */}
                                                {selectedStrategy.parameter_schema?.fields?.length > 0 ? (
                                                    <DynamicParameterForm
                                                        schema={selectedStrategy.parameter_schema}
                                                        values={currentConfig}
                                                        onChange={handleConfigChange}
                                                    />
                                                ) : (
                                                    <div className="text-gray-500 text-sm text-center py-4">No configurable parameters for this strategy</div>
                                                )}

                                                {/* Parameter Version Manager */}
                                                <ParameterVersionManager
                                                    strategyId={selectedStrategy?.id}
                                                    symbol={currentConfig?.symbol || currentSymbol}
                                                    currentParams={currentConfig}
                                                    onRestore={(restoredParams) => {
                                                        // Only apply strategy parameters, preserve metadata
                                                        const parameterFields = selectedStrategy?.parameter_schema?.fields?.map(f => f.key || f.name) || [];
                                                        const filteredParams = {};
                                                        parameterFields.forEach(key => {
                                                            if (restoredParams[key] !== undefined) {
                                                                filteredParams[key] = restoredParams[key];
                                                            }
                                                        });
                                                        handleConfigChange({...currentConfig, ...filteredParams});
                                                    }}
                                                    className="mt-4"
                                                />
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            )}

                            {/* Content Area based on Tab */}


                            {activeTab === -2 && (
                                <div className="animate-fade-in-up">
                                    <LiveStrategyPanel
                                        strategyConfig={configList[liveRankIndex] || configList[0]}
                                        strategyName={selectedStrategy?.id}
                                        configList={configList}
                                        savedSymbols={savedSymbols}
                                        currentRankIndex={liveRankIndex}
                                        executionMode={executionMode}
                                        onExecutionModeChange={(mode) => setExecutionMode(mode)}
                                        onRankChange={(index) => {
                                            setLiveRankIndex(index);
                                            if (configList[index] && configList[index].symbol) {
                                                setCurrentSymbol(configList[index].symbol);
                                            }
                                        }}
                                        parameterSchema={selectedStrategy?.parameter_schema}
                                        onStatusChange={(newStatus) => setIsLiveRunning(newStatus === 'RUNNING')}
                                        onCapitalChange={(newCapital) => {
                                            // Update initial_capital in configList for the current liveRankIndex
                                            const targetIndex = liveRankIndex >= 0 && liveRankIndex < configList.length ? liveRankIndex : 0;
                                            setConfigList(prev => {
                                                const newList = [...prev];
                                                if (newList[targetIndex]) {
                                                    newList[targetIndex] = {
                                                        ...newList[targetIndex],
                                                        initial_capital: newCapital
                                                    };
                                                }
                                                return newList;
                                            });
                                            // Auto-save with debounce for Live tab capital (critical setting)
                                            if (capitalSaveTimeoutRef.current) {
                                                clearTimeout(capitalSaveTimeoutRef.current);
                                            }
                                            capitalSaveTimeoutRef.current = setTimeout(async () => {
                                                try {
                                                    await saveConfigs();
                                                    console.log('[Live] Capital auto-saved:', newCapital);
                                                } catch (e) {
                                                    console.error('[Live] Failed to auto-save capital:', e);
                                                }
                                            }, 1000); // 1 second debounce
                                        }}
                                    />
                                </div>
                            )}

                            {/* Symbol Comparison Tab Content */}
                            {activeTab === -3 && (
                                <div className="animate-fade-in-up space-y-4">
                                    {/* Backtest Settings & Run Button */}
                                    <div className="bg-white/5 border border-white/10 rounded-xl overflow-hidden">
                                        <div className="bg-white/5 px-4 py-3 border-b border-white/10">
                                            <h3 className="font-bold text-gray-200 text-sm flex items-center gap-2">
                                                <Settings size={14} className="text-gray-400" /> Backtest Settings
                                            </h3>
                                        </div>
                                        <div className="px-4 py-4 flex flex-col gap-4">
                                            {/* Row 1: Info display */}
                                            <div className="flex items-center gap-3">
                                                <span className="text-blue-400 text-xs font-bold px-2 py-1 bg-blue-500/10 rounded border border-blue-500/20 whitespace-nowrap" title="모든 데이터는 1분봉으로 수집 후 집계됩니다">
                                                    1m
                                                </span>
                                                <span className="text-gray-400 text-xs">
                                                    Data will be fetched for each symbol during comparison
                                                </span>
                                            </div>

                                            {/* Row 2: Capital & Date inputs */}
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
                                                    <label className="text-[10px] text-gray-500 absolute -top-1.5 left-2 bg-[#1e2029] px-1">
                                                        Start Date (Max 1yr)
                                                    </label>
                                                    <DateDropdown
                                                        value={currentConfig?.from_date || ""}
                                                        onChange={(dateStr) => handleConfigChange('from_date', dateStr)}
                                                    />
                                                </div>

                                                <div className="flex items-center justify-end">
                                                    <button
                                                        onClick={handleStockCompareBacktest}
                                                        disabled={isStockComparing || selectedCompareSymbols.length === 0}
                                                        className={`px-6 py-2.5 rounded-lg font-bold text-white transition-all flex items-center gap-2 ${
                                                            isStockComparing || selectedCompareSymbols.length === 0
                                                                ? 'bg-gray-600 cursor-not-allowed'
                                                                : 'bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-600 hover:to-teal-700 shadow-lg'
                                                        }`}
                                                    >
                                                        {isStockComparing ? (
                                                            <>
                                                                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                                                                {stockCompareProgress.phase === 'data' ? 'Updating' : 'Testing'} ({stockCompareProgress.current}/{stockCompareProgress.total})
                                                            </>
                                                        ) : (
                                                            <>
                                                                🚀 Run Comparison ({selectedCompareSymbols.length})
                                                            </>
                                                        )}
                                                    </button>
                                                </div>
                                            </div>
                                        </div>
                                    </div>

                                    {/* Results Table - Sortable Grid */}
                                    {stockCompareResults.length > 0 && (() => {
                                        // Use STAT_COLUMNS for consistent display with backtest results
                                        const visibleCols = getVisibleColumns(stockCompareResults[0] || {});

                                        // Sort handler
                                        const handleCompareSort = (key) => {
                                            setCompareSortConfig(prev => ({
                                                key,
                                                direction: prev.key === key && prev.direction === 'desc' ? 'asc' : 'desc'
                                            }));
                                        };

                                        // Sort indicator component
                                        const SortIndicator = ({ colKey }) => {
                                            if (compareSortConfig.key !== colKey) {
                                                return <span className="text-gray-600 ml-1">↕</span>;
                                            }
                                            return (
                                                <span className="text-blue-400 ml-1">
                                                    {compareSortConfig.direction === 'desc' ? '↓' : '↑'}
                                                </span>
                                            );
                                        };

                                        // Sortable header component
                                        const SortableHeader = ({ colKey, label, align = 'left', sticky = false }) => (
                                            <th
                                                onClick={() => handleCompareSort(colKey)}
                                                className={`p-3 cursor-pointer hover:bg-white/10 transition-colors select-none ${
                                                    align === 'right' ? 'text-right' : ''
                                                } ${sticky ? 'sticky left-0 bg-[#1a1d24] z-10' : ''} ${
                                                    compareSortConfig.key === colKey ? 'text-blue-300' : ''
                                                }`}
                                            >
                                                <div className={`flex items-center gap-1 ${align === 'right' ? 'justify-end' : ''}`}>
                                                    {label}
                                                    <SortIndicator colKey={colKey} />
                                                </div>
                                            </th>
                                        );

                                        // Sort the results
                                        const sortedResults = [...stockCompareResults].sort((a, b) => {
                                            const key = compareSortConfig.key;
                                            const dir = compareSortConfig.direction === 'desc' ? -1 : 1;

                                            // Handle special keys
                                            if (key === 'symbol' || key === 'name') {
                                                const aVal = (a[key] || '').toLowerCase();
                                                const bVal = (b[key] || '').toLowerCase();
                                                return aVal.localeCompare(bVal) * dir;
                                            }

                                            // Numeric comparison with null handling
                                            const aVal = parseStatValue(a[key]);
                                            const bVal = parseStatValue(b[key]);
                                            if (aVal == null && bVal == null) return 0;
                                            if (aVal == null) return 1;
                                            if (bVal == null) return -1;
                                            return (aVal - bVal) * dir;
                                        });

                                        // Render cell for a stat column
                                        const renderStatCell = (data, col) => {
                                            const value = data[col.key];
                                            const colorClass = getStatColor(value, col);
                                            const formatted = formatStatValue(value, col);
                                            const prefix = col.signed && typeof value === 'number' && value > 0 ? '+' : '';
                                            const bold = col.bold ? ' font-bold' : '';
                                            return (
                                                <td key={col.key} className={`p-3 text-right${bold} ${colorClass}`}>
                                                    {prefix}{formatted}
                                                </td>
                                            );
                                        };

                                        return (
                                            <div className="bg-white/5 border border-white/10 rounded-xl overflow-hidden">
                                                <div className="bg-white/5 px-4 py-3 border-b border-white/10 flex items-center justify-between">
                                                    <h3 className="font-bold text-gray-200 text-sm flex items-center gap-2">
                                                        📊 Comparison Results ({stockCompareResults.length} symbols)
                                                        <span className="text-xs text-gray-500 font-normal">
                                                            (Click headers to sort)
                                                        </span>
                                                    </h3>
                                                    <button
                                                        onClick={handleExportCompareResults}
                                                        className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-400 rounded-lg text-xs font-medium transition-colors border border-emerald-500/30"
                                                    >
                                                        <Download size={14} />
                                                        Export CSV
                                                    </button>
                                                </div>
                                                <DualScrollContainer>
                                                    <table className="w-full text-left border-collapse whitespace-nowrap">
                                                        <thead>
                                                            <tr className="bg-white/5 text-xs font-bold text-gray-400 border-b border-white/10">
                                                                <th className="p-3 sticky left-0 bg-[#1a1d24] z-10">#</th>
                                                                <SortableHeader colKey="symbol" label="Symbol" />
                                                                <SortableHeader colKey="name" label="Name" />
                                                                {visibleCols.map(col => (
                                                                    <SortableHeader
                                                                        key={col.key}
                                                                        colKey={col.key}
                                                                        label={col.tableLabel || col.label}
                                                                        align="right"
                                                                    />
                                                                ))}
                                                                <SortableHeader colKey="score" label="Score" align="right" />
                                                            </tr>
                                                        </thead>
                                                        <tbody>
                                                            {sortedResults.map((result, idx) => (
                                                                <tr
                                                                    key={result.symbol}
                                                                    className={`border-b border-white/5 hover:bg-white/5 transition-colors ${
                                                                        idx === 0 && compareSortConfig.key === 'score' && compareSortConfig.direction === 'desc'
                                                                            ? 'bg-emerald-900/20'
                                                                            : ''
                                                                    }`}
                                                                >
                                                                    <td className="p-3 text-gray-500 sticky left-0 bg-[#0f1115] z-10">{idx + 1}</td>
                                                                    <td className="p-3 text-white font-mono font-bold">{result.symbol}</td>
                                                                    <td className="p-3 text-gray-300">{result.name || '-'}</td>
                                                                    {visibleCols.map(col => renderStatCell(result, col))}
                                                                    <td className="p-3 text-right text-purple-400 font-bold">
                                                                        {result.score != null && result.score !== -999 ? result.score.toFixed(2) : '-'}
                                                                    </td>
                                                                </tr>
                                                            ))}
                                                        </tbody>
                                                    </table>
                                                </DualScrollContainer>
                                            </div>
                                        );
                                    })()}
                                </div>
                            )}


                            {/* Backtest Settings Card */}
                            {activeTab >= 0 && (
                                <div className="bg-white/5 border border-white/10 rounded-xl overflow-hidden">
                                    <div className="bg-white/5 px-4 py-3 border-b border-white/10">
                                        <h3 className="font-bold text-gray-200 text-sm flex items-center gap-2">
                                            <Settings size={14} className="text-gray-400" /> Backtest Settings
                                        </h3>
                                    </div>
                                    <div className="px-4 py-4 flex flex-col gap-4">
                                        {/* Row 1: Data Status & Actions */}
                                        <div className="flex flex-col md:flex-row justify-between items-center gap-4 w-full">
                                            <div className="flex items-center gap-4 w-full md:w-auto">
                                                <div className="flex items-center gap-3">
                                                    {/* Fixed 1m indicator - all data is fetched as 1m and aggregated */}
                                                    <span className="text-blue-400 text-xs font-bold px-2 py-1 bg-blue-500/10 rounded border border-blue-500/20 whitespace-nowrap" title="모든 데이터는 1분봉으로 수집 후 집계됩니다">
                                                        1m
                                                    </span>
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
                                                        onClick={() => handleFetchData(false)}
                                                        disabled={isFetchingData || !isSymbolValid}
                                                        title={!isSymbolValid ? "먼저 종목을 선택해주세요" : "최신 데이터만 업데이트 (증분)"}
                                                        className={`px-3 py-1 rounded text-sm font-bold transition-all shadow-lg flex items-center gap-2 whitespace-nowrap disabled:opacity-50 disabled:cursor-not-allowed ${fetchMessage && fetchMessage.includes("Updated") ? "bg-green-600 text-white" :
                                                            fetchMessage && fetchMessage.includes("Up to date") ? "bg-blue-600 text-white" :
                                                                "bg-amber-600 hover:bg-amber-500 text-white hover:shadow-amber-500/30"
                                                            }`}
                                                    >
                                                        {fetchMessage ? fetchMessage : 'Update'}
                                                    </button>
                                                    {/* Full Backfill Button - Hidden by default, enable when data issues occur
                                                    <button
                                                        onClick={() => handleFetchData(true)}
                                                        disabled={isFetchingData || !isSymbolValid}
                                                        title={!isSymbolValid ? "먼저 종목을 선택해주세요" : "전체 1년 데이터 다시 가져오기 (Backfill)"}
                                                        className="px-2 py-1 rounded text-xs font-bold transition-all shadow-lg whitespace-nowrap disabled:opacity-50 disabled:cursor-not-allowed bg-purple-600 hover:bg-purple-500 text-white hover:shadow-purple-500/30"
                                                    >
                                                        Full
                                                    </button>
                                                    */}
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
                                                <label className="text-[10px] text-gray-500 absolute -top-1.5 left-2 bg-[#1e2029] px-1">
                                                    Start Date {dataStatus?.start_date ? `(${dataStatus.start_date}~)` : '(Max 1yr)'}
                                                </label>
                                                <DateDropdown
                                                    value={currentConfig?.from_date || ""}
                                                    onChange={(dateStr) => handleConfigChange('from_date', dateStr)}
                                                    minDate={dataStatus?.start_date ? (() => {
                                                        // Parse "YY.MM.DD" format to Date
                                                        const parts = dataStatus.start_date.split('.');
                                                        if (parts.length === 3) {
                                                            const year = parseInt(parts[0]) + 2000;
                                                            const month = parseInt(parts[1]) - 1;
                                                            const day = parseInt(parts[2]);
                                                            return new Date(year, month, day);
                                                        }
                                                        return undefined;
                                                    })() : undefined}
                                                />
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            )}

                            {/* Actions Card (Individual Rank Tabs Only) */}
                            {activeTab >= 0 && (
                                <div className="bg-white/5 border border-white/10 rounded-xl overflow-hidden">
                                    <div className="bg-white/5 px-4 py-3 border-b border-white/10">
                                        <h3 className="font-bold text-gray-200 text-sm flex items-center gap-2">
                                            <Rocket size={14} className="text-gray-400" /> Actions
                                        </h3>
                                    </div>
                                    <div className="px-4 py-4 space-y-4">
                                        {/* Run Buttons */}
                                        <div className="grid grid-cols-2 gap-4">
                                            <button
                                                onClick={() => setShowChart(!showChart)}
                                                disabled={!backtestResult?.ohlcv_data}
                                                className={`px-4 py-4 rounded-xl font-bold transition-all shadow-lg flex items-center justify-center gap-2 ${!backtestResult?.ohlcv_data
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

                                    {/* Execution Status */}
                                    {(backtestStatus.status !== 'idle' || !backtestResult) && (
                                        <div>
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
                                        </div>
                                    )}


                                    {/* VISUAL CHART SECTION */}
                                    {showChart && backtestResult?.ohlcv_data && (
                                        <div>
                                            <VisualBacktestChart
                                                data={backtestResult.ohlcv_data}
                                                trades={backtestResult.trades}
                                            />
                                        </div>
                                    )}

                                    {/* Backtest Results */}
                                    {backtestResult && (
                                        <div className="space-y-4">
                                                {/* Analysis Mode Tabs */}
                                                <div className="flex gap-4 mb-4">
                                                    <button
                                                        onClick={() => setActiveAnalysisTab('overview')}
                                                        className={`px-4 py-2 rounded-lg text-sm font-bold transition-all ${activeAnalysisTab === 'overview'
                                                            ? 'bg-purple-600 text-white shadow-lg'
                                                            : 'bg-white/5 text-gray-400 hover:bg-white/10'}`}
                                                    >
                                                        Overview
                                                    </button>
                                                    <button
                                                        onClick={() => setActiveAnalysisTab('rank_details')}
                                                        className={`px-4 py-2 rounded-lg text-sm font-bold transition-all ${activeAnalysisTab === 'rank_details'
                                                            ? 'bg-purple-600 text-white shadow-lg'
                                                            : 'bg-white/5 text-gray-400 hover:bg-white/10'}`}
                                                    >
                                                        Rank Details
                                                    </button>
                                                </div>

                                                <div>
                                                    {activeAnalysisTab === 'overview' ? (
                                                        <div className="space-y-4">
                                                            <PerformanceStatsGrid stats={backtestResult} />
                                                            <MonthlyAnalysisChart bucketStats={backtestResult.bucket_stats} decileStats={backtestResult.decile_stats} />
                                                        </div>
                                                    ) : (
                                                        <div className="overflow-x-auto">
                                                            {backtestResult.rank_stats_list && backtestResult.rank_stats_list.length > 0 ? (
                                                                (() => {
                                                                    const visibleCols = getVisibleColumns(backtestResult);
                                                                    const totalStats = computeTotalStats(backtestResult.rank_stats_list);

                                                                    // Render a stat cell for any row
                                                                    const renderCell = (data, col, opacity = '') => {
                                                                        const value = data[col.key];
                                                                        const colorClass = getStatColor(value, col) + (opacity ? `/${opacity}` : '');
                                                                        const formatted = formatStatValue(value, col);
                                                                        const prefix = col.signed && typeof value === 'number' && value > 0 ? '+' : '';
                                                                        const align = col.lastColumn ? ' text-right' : '';
                                                                        const bold = col.bold ? ' font-bold' : '';
                                                                        return (
                                                                            <td key={col.key} className={`p-3${bold}${align} ${colorClass}`}>
                                                                                {prefix}{formatted}
                                                                            </td>
                                                                        );
                                                                    };

                                                                    return (
                                                                        <table className="w-full text-left border-collapse whitespace-nowrap">
                                                                            <thead>
                                                                                <tr className="border-b border-white/10 text-xs text-gray-400 uppercase">
                                                                                    <th className="p-3 sticky left-0 bg-[#0f1115] z-10 shadow-r">Rank</th>
                                                                                    {visibleCols.map(col => (
                                                                                        <th key={col.key} className={`p-3${col.lastColumn ? ' text-right' : ''}`}>
                                                                                            {col.tableLabel || col.label}
                                                                                        </th>
                                                                                    ))}
                                                                                </tr>
                                                                            </thead>
                                                                            <tbody className="text-sm">
                                                                                {backtestResult.rank_stats_list.map((stat, idx) => (
                                                                                    <tr key={idx} className="border-b border-white/5 hover:bg-white/5 transition-colors">
                                                                                        <td className="p-3 font-bold text-white sticky left-0 bg-[#0f1115] z-10 shadow-r">#{stat.rank}</td>
                                                                                        {visibleCols.map(col => renderCell(stat, col))}
                                                                                    </tr>
                                                                                ))}
                                                                            </tbody>
                                                                            <tfoot className="text-sm border-t-2 border-white/20">
                                                                                {/* TOTAL Row (Sum/Weighted Average) */}
                                                                                <tr className="bg-[#1a1d24]/50 border-b border-white/10 font-bold text-gray-300">
                                                                                    <td className="p-3 sticky left-0 bg-[#15181e] z-10 shadow-r">TOTAL (Sum/W.Avg)</td>
                                                                                    {visibleCols.map(col => renderCell(totalStats, col, '80'))}
                                                                                </tr>
                                                                                {/* OVERVIEW Row (Global Stats from backend) */}
                                                                                <tr className="bg-[#2d3748] font-bold text-white border-t border-purple-500/30">
                                                                                    <td className="p-3 text-purple-300 sticky left-0 bg-[#2d3748] z-10 shadow-r">OVERVIEW</td>
                                                                                    {visibleCols.map(col => renderCell(backtestResult, col))}
                                                                                </tr>
                                                                            </tfoot>
                                                                        </table>
                                                                    );
                                                                })()
                                                            ) : (
                                                                <div className="py-12 text-center">
                                                                    <div className="text-gray-500 italic mb-2">No rank details available</div>
                                                                    <div className="text-xs text-gray-600">
                                                                        Debug: {JSON.stringify(Object.keys(backtestResult))}
                                                                        <br />
                                                                        IsList: {Array.isArray(backtestResult.rank_stats_list) ? "Yes" : "No"}
                                                                    </div>
                                                                </div>
                                                            )}
                                                        </div>
                                                    )}
                                                </div>
                                        </div>
                                    )}

                                    </div>
                                </div>
                            )}

                        </div> {/* End of Backtest Simulation Group */}

                        {/* OPTIMIZATION SECTION */}
                        {
                            activeTab >= 0 && (
                                <div className="bg-white/5 border border-white/10 rounded-xl overflow-hidden">
                                    <div className="bg-white/5 px-4 py-3 border-b border-white/10">
                                        <h3 className="font-bold text-gray-200 text-sm flex items-center gap-2">
                                            <Sparkles size={14} className="text-gray-400" /> Parameter Optimization
                                        </h3>
                                    </div>
                                    <div className="px-4 py-4">
                                        <div className="space-y-6">
                                            <div className="space-y-6">
                                                {/* Dynamic Grid Inputs */}
                                                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                                                    {(() => {
                                                        const currentOptEnabled = currentConfig.optEnabled || {};
                                                        const currentOptValues = currentConfig.optValues || getDynamicOptValues();

                                                        return convertSchemaToParamDefs(selectedStrategy?.parameter_schema).map((param) => (
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
                                                                                {/* Use INTERVAL_OPTIONS for interval field, otherwise use param.options */}
                                                                                {(param.key === 'interval' ? INTERVAL_OPTIONS : (param.options || []).map(o => ({ value: o, label: o }))).map(opt => {
                                                                                    const optionValue = typeof opt === 'object' ? opt.value : opt;
                                                                                    const optionLabel = typeof opt === 'object' ? opt.label : opt;
                                                                                    const currentVals = (currentOptValues[param.key] || '').split(',').map(v => v.trim()).filter(Boolean);
                                                                                    const isSelected = currentVals.includes(optionValue);

                                                                                    return (
                                                                                        <div
                                                                                            key={optionValue}
                                                                                            onClick={() => {
                                                                                                let newVals;
                                                                                                if (isSelected) {
                                                                                                    newVals = currentVals.filter(v => v !== optionValue);
                                                                                                } else {
                                                                                                    newVals = [...currentVals, optionValue];
                                                                                                }
                                                                                                handleOptValueChange(param.key, newVals.join(', '));
                                                                                            }}
                                                                                            className={`px-3 py-2 text-sm cursor-pointer hover:bg-white/10 flex items-center justify-between ${isSelected ? 'bg-purple-900/40 text-purple-300' : 'text-gray-300'
                                                                                                }`}
                                                                                        >
                                                                                            <span>{optionLabel}</span>
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
                                                                        value={currentOptEnabled[param.key] ? (currentOptValues[param.key] || "") : (currentConfig[param.key] ?? param.defaultValue ?? "")}
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

                                                {/* Status Message Display */}
                                                {isOptimizing && optStatusMessage && (
                                                    <div className="mt-2 p-2 bg-black/40 rounded border border-white/10 text-xs font-mono text-cyan-400 text-center animate-pulse">
                                                        STATUS: {optStatusMessage}
                                                    </div>
                                                )}

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
                                                        {/* Export & Save Buttons */}
                                                        <div className="p-4 border-b border-white/10 flex items-center justify-between">
                                                            <div className="text-sm text-gray-400 flex items-center gap-3">
                                                                <span><span className="font-bold text-white">{optResults.length}</span> optimization results</span>
                                                                {isOptimizing && optResults[0]?._isPartial && (
                                                                    <span className="px-2 py-1 bg-cyan-500/20 text-cyan-400 text-xs rounded-full animate-pulse">
                                                                        Live Preview (Top 20)
                                                                    </span>
                                                                )}
                                                                {pendingOptResult && (
                                                                    <span className="px-2 py-1 bg-yellow-500/20 text-yellow-400 text-xs rounded-full animate-pulse">
                                                                        ⚠️ Unsaved
                                                                    </span>
                                                                )}
                                                            </div>
                                                            <div className="flex items-center gap-2">
                                                                <button
                                                                    onClick={exportOptResultsToCSV}
                                                                    className="px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white text-sm font-medium rounded-lg transition-colors flex items-center gap-2"
                                                                    title="Export top 200 results shown in this table"
                                                                >
                                                                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                                                                    </svg>
                                                                    Export Top 200
                                                                </button>
                                                                {completedOptTaskId && (
                                                                    <button
                                                                        onClick={downloadFullOptResultsCSV}
                                                                        className="px-4 py-2 bg-green-600 hover:bg-green-700 text-white text-sm font-medium rounded-lg transition-colors flex items-center gap-2"
                                                                        title="Download ALL optimization results (full dataset)"
                                                                    >
                                                                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                                                                        </svg>
                                                                        Download Full CSV
                                                                    </button>
                                                                )}
                                                            </div>
                                                        </div>
                                                        <DualScrollContainer>
                                                            <table className="w-full text-left border-collapse whitespace-nowrap">
                                                                <thead>
                                                                    {(() => {
                                                                        const optCols = getOptVisibleColumns(optResults);
                                                                        const extraCols = [
                                                                            { key: 'rank', label: 'Rank' },
                                                                            ...optCols.map(c => ({ key: c.optKey || c.key, label: c.tableLabel || c.label })),
                                                                            { key: 'score', label: 'Score' },
                                                                            ...convertSchemaToParamDefs(selectedStrategy?.parameter_schema)
                                                                        ];
                                                                        return (
                                                                            <tr className="bg-white/5 text-xs font-bold text-gray-400 border-b border-white/10">
                                                                                <th className="p-3 text-center w-16">Active</th>
                                                                                {extraCols.map((col) => (
                                                                                    <th
                                                                                        key={col.key}
                                                                                        onClick={() => handleSort(col.key)}
                                                                                        className={`p-3 cursor-pointer hover:text-white transition-colors ${sortConfig.key === col.key ? 'text-purple-300' : ''}`}
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
                                                                        );
                                                                    })()}
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
                                                                                for (const param of convertSchemaToParamDefs(selectedStrategy?.parameter_schema)) {
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
                                                                                                openConfirm(
                                                                                                    "Apply Optimization Config?",
                                                                                                    `Rank: #${res.rank}\nReturn: ${res.return}%\nScore: ${res.score}\n\nThis will overwrite your current configuration. Continue?`,
                                                                                                    async () => {
                                                                                                        // 1. Update Configuration
                                                                                                        let updatedConfigList;
                                                                                                        setConfigList(prev => {
                                                                                                            const next = [...prev];
                                                                                                            const configToApply = res.full_config || {};
                                                                                                            next[activeTab] = {
                                                                                                                ...next[activeTab],
                                                                                                                ...configToApply
                                                                                                            };
                                                                                                            updatedConfigList = next;
                                                                                                            return next;
                                                                                                        });

                                                                                                        // 2. Save to DB (ConfigScope 사용)
                                                                                                        try {
                                                                                                            const configsToSave = updatedConfigList.map((cfg, index) => transformUiToDbConfig(cfg, index));

                                                                                                            // Debug: Log what we're saving
                                                                                                            console.log("[Optimization Save] Saving configs:", configsToSave.map(c => ({
                                                                                                                tab_name: c.tab_name,
                                                                                                                is_active: c.is_active,
                                                                                                                account_id: c.account_id
                                                                                                            })));

                                                                                                            await syncStrategyConfigsSelective(scope.strategyId, configsToSave, true);
                                                                                                            console.log("Optimization config saved to DB");
                                                                                                        } catch (e) {
                                                                                                            console.error("Failed to save optimization config:", e);
                                                                                                        }

                                                                                                        // 3. Trigger Real Backtest (User Request)
                                                                                                        runBacktest(selectedStrategy.id, res.full_config || {});
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

                                                                                    {/* Performance Metrics - driven by STAT_COLUMNS (statsConfig.js) */}
                                                                                    {getOptVisibleColumns(optResults).map(col => {
                                                                                        const raw = getOptValue(res, col);
                                                                                        const parsed = parseStatValue(raw);
                                                                                        const colorClass = getStatColor(parsed, col);
                                                                                        const formatted = formatStatValue(parsed, col);
                                                                                        const prefix = col.signed && typeof parsed === 'number' && parsed > 0 ? '+' : '';
                                                                                        return (
                                                                                            <td key={col.key} className={`p-3 ${colorClass}`}>
                                                                                                {prefix}{formatted}
                                                                                            </td>
                                                                                        );
                                                                                    })}
                                                                                    <td className="p-3 text-blue-400 font-bold">{parseFloat(res.score)?.toFixed(2) ?? '-'}</td>

                                                                                    {/* Render All Params - Last */}
                                                                                    {convertSchemaToParamDefs(selectedStrategy?.parameter_schema).map(param => (
                                                                                        <td key={param.key} className="p-3 text-gray-300">
                                                                                            {res[param.key] !== undefined ? res[param.key] : '-'}
                                                                                        </td>
                                                                                    ))}
                                                                                </tr>
                                                                            );
                                                                        })}
                                                                </tbody>
                                                            </table>
                                                        </DualScrollContainer>
                                                    </div>
                                                )}
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            )
                        }

                        {/* Execution Logs Panel (hidden on live tab - LiveStrategyPanel has its own) */}
                        {activeTab !== -2 && <div className="bg-white/5 border border-white/10 rounded-xl overflow-hidden">
                            <div className="bg-white/5 px-4 py-3 border-b border-white/10">
                                <h3 className="font-bold text-gray-200 text-sm flex items-center gap-2">
                                    <Terminal size={14} className="text-gray-400" /> Execution Logs
                                </h3>
                            </div>
                            <div className="px-4 py-4">
                                <div className="bg-black/50 p-4 rounded-lg border border-white/5 max-h-[400px] overflow-y-auto">
                                    {executionLogs.length === 0 ? (
                                        <div className="text-gray-500 text-sm text-center py-8">
                                            No logs yet. Select a strategy to see execution logs.
                                        </div>
                                    ) : (
                                        <div className="space-y-1">
                                            {executionLogs.map((log, index) => (
                                                <div
                                                    key={index}
                                                    className={`flex items-start gap-2 text-xs font-mono p-2 rounded ${
                                                        log.level === 'error' ? 'bg-red-900/20 text-red-300' :
                                                        log.level === 'success' ? 'bg-green-900/20 text-green-300' :
                                                        'bg-blue-900/10 text-gray-300'
                                                    }`}
                                                >
                                                    <span className="text-gray-500 whitespace-nowrap">{log.timestamp}</span>
                                                    <span className="flex-1">{log.message}</span>
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                </div>
                                <div className="mt-2 flex justify-end">
                                    <button
                                        onClick={() => setExecutionLogs([])}
                                        className="px-3 py-1 text-xs bg-red-600/20 text-red-400 rounded hover:bg-red-600/30 transition-colors"
                                    >
                                        Clear Logs
                                    </button>
                                </div>
                            </div>
                        </div>}
                    </>
                ) : (
                    <div className="flex flex-col items-center justify-center h-[50vh] text-gray-500">
                        <div className="text-6xl mb-4 opacity-20">⚡</div>
                        <p className="text-xl">Select a strategy to begin</p>
                    </div>
                )
                }
            </div >



            {/* Dynamic Confirm Modal */}
            <ConfirmModal
                isOpen={confirmModal.isOpen}
                onClose={closeConfirm}
                onConfirm={confirmModal.onConfirm}
                onCancel={confirmModal.onCancel}
                title={confirmModal.title}
                message={confirmModal.message}
                isDanger={confirmModal.isDanger}
                confirmText={confirmModal.confirmText}
                cancelText={confirmModal.cancelText}
            />

            {/* Strategy Detail Modal */}
            <StrategyDetailModal
                isOpen={isDetailModalOpen}
                onClose={() => setIsDetailModalOpen(false)}
                strategy={selectedStrategy}
            />
        </div >
    );
};

export default StrategyView;
