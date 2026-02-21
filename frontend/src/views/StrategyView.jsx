import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar, Cell, ReferenceLine, ComposedChart, LabelList } from 'recharts';
import Card from '../components/common/Card';
import SymbolSelector from '../components/SymbolSelector';
import CryptoSymbolSelector from '../components/CryptoSymbolSelector';
import SymbolChip from '../components/SymbolChip';
import IntegratedAnalysis from '../components/IntegratedAnalysis';
import VisualBacktestChart from '../components/VisualBacktestChart';
import {
    runBacktest as apiRunBacktest,
    runIntegratedBacktestApi,
    getSymbolInfo,
    saveStrategyResult, getStrategyResults,
} from '../api/strategies';
import { buildDynamicDefaultConfig, buildDynamicOptValues,
         getStrategyParamNames as extractParamNames, coerceConfigTypes } from '../utils/strategyParamUtils';
import { useWatchlist } from '../context/WatchlistContext';
import { useStrategies } from '../context/StrategiesContext';
import { useProfileConfig } from '../hooks/useProfileConfig';
import { useProfileLock } from '../hooks/useProfileLock';
import { useCopyPaste } from '../hooks/useCopyPaste';
import { useImportExport } from '../hooks/useImportExport';
import { useDataFetching } from '../hooks/useDataFetching';
import { useSymbolComparison } from '../hooks/useSymbolComparison';
import { useOptimization } from '../hooks/useOptimization';
import { useScoreWeights } from '../hooks/useScoreWeights';

import { isValidScope } from '../types/ConfigScope';
import { DEFAULT_EXCHANGE, DEFAULT_INITIAL_CAPITAL, getMaxDays, getMaxDaysLabel, getDefaultCapital, getDefaultDays, getOptRangeDefaults } from '../constants/exchanges';
import NewProfileModal from '../components/NewProfileModal';
import ConfirmModal from '../components/ConfirmModal'; // Custom Modal
import AlertModal from '../components/AlertModal';
import ActiveStrategiesPanel from '../components/ActiveStrategiesPanel';
import StrategyDetailModal from '../components/StrategyDetailModal';
import DynamicParameterForm from '../components/DynamicParameterForm';
import RankVersionSelector from '../components/RankVersionSelector';
import TabBadge from '../components/TabBadge';
import DateDropdown from '../components/DateDropdown';
import PerformanceStatsGrid from '../components/PerformanceStatsGrid';
import MonthlyAnalysisChart from '../components/MonthlyAnalysisChart';
import DualScrollContainer from '../components/DualScrollContainer';
import { STAT_COLUMNS, formatStatValue, getStatColor, shouldShowConditional, computeTotalStats, getVisibleColumns, parseStatValue, getOptValue, getOptVisibleColumns, normalizeStats } from '../config/statsConfig';
import { EQUITY_DATE_KEY, EQUITY_VALUE_KEY } from '../config/chartConfig';
import { History as HistoryIcon, HelpCircle, ChevronRight, Settings, Rocket, Crosshair, Sparkles, Terminal, Save, Copy, ClipboardPaste, RefreshCw, Download, Upload, Plus, Trash2, FolderOpen, X, Check, Lock, Building2 } from 'lucide-react';
import { INTERVAL_OPTIONS, getIntervalLabel, INTERVAL_VALUES, DEFAULT_OPT_INTERVALS } from '../constants/intervals';
import { generateUUID, PARAM_DEFINITIONS, DEFAULT_CONFIG, DEFAULT_OPT_VALUES, convertSchemaToParamDefs, getIntegratedUUID, getCrossOptUUID, SCORE_WEIGHT_PRESETS, STORAGE_KEYS, createConfigHash } from '../constants/strategies';

// Constants imported from '../constants/strategies' (Single Source of Truth)

// ApplyButton 컴포넌트 제거 — 탭별 Apply 제거, 헤더 Save로 통합

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
// DEFAULT_OPT_VALUES, getIntegratedUUID, getCrossOptUUID imported from constants/strategies

const StrategyView = () => {
    // ==========================================
    // Context: Strategies (centralized state)
    // ==========================================
    const {
        strategies,
        selectedStrategy, setSelectedStrategy,
        accounts, effectiveAccountId,
    } = useStrategies();

    // Active account info - 기본값 (profileMeta 로드 후 아래에서 재계산)
    const defaultAccount = accounts.find(a => a.id === effectiveAccountId) || accounts.find(a => !a.is_disabled);
    // Preliminary exchange name (profileMeta 로드 전, effectiveAccountId 기반)
    const preliminaryExchangeName = defaultAccount?.exchange_name || DEFAULT_EXCHANGE;

    // Symbol State - currentSymbol은 글로벌, savedSymbols는 프로필 레벨
    const { currentSymbol, setCurrentSymbol } = useWatchlist();

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
    // Live state variables moved to LiveTradingView.jsx
    // executionMode is now from profileMeta.execution_mode (profile-level)
    const [isDetailModalOpen, setIsDetailModalOpen] = useState(false);
    // Old Profile Save Modal state removed - now using Profile Selector's Save As modal

    // Symbol Compare dirty tracking (local state - hooks manage their own state)
    const [isSymbolCompareDirty, setIsSymbolCompareDirty] = useState(false);

    // Execution Log Helper (moved up for useProfileConfig)
    const addLog = useCallback((message, level = 'info') => {
        const timestamp = new Date().toLocaleTimeString('ko-KR', {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            fractionalSecondDigits: 3
        });
        const newLog = { timestamp, message, level };
        setExecutionLogs(prev => [...prev.slice(-99), newLog]); // Keep last 100 logs
        console.log(`[${timestamp}] ${message}`); // Still log to console
    }, []);

    // Profile-based Config State (Profile-Centric Architecture)
    // Profiles are the single source of truth for strategy configurations
    const {
        // Profile Management
        profiles,
        selectedProfileId,
        selectedProfile,
        isProfilesLoading,
        loadProfiles,
        selectProfile,
        initNewProfile,
        createNewProfile,
        saveProfile,
        saveProfileAs,
        deleteCurrentProfile,
        discardChanges,
        profileMeta,
        setProfileMeta,
        // Symbol Compare Settings (from profile - 프로필별 저장)
        symbolCompareSettings: symbolCompareConfig,
        setSymbolCompareSettings: setSymbolCompareConfig,
        // Profile Symbols - Target Asset list (프로필별 종목)
        profileSymbols,
        setProfileSymbols,
        isDirty: isProfileDirty,
        // Config List (from profile's rank_configs)
        configList,
        setConfigList,
        isLoaded: isConfigLoaded,
        needsInit,
        setNeedsInit,
        error: profileError,
        saveStatus,
        saveConfigs,
        scope, // Backward compatible scope object
        transformUiToDbConfig, // Legacy API compatibility
        // reloadConfigs already aliased to loadProfiles above
        initDefaultList: hookInitDefaultList,
        getDynamicDefaultConfig: getHookDefaultConfig,
        // Parameter Preset Management
        addPreset,
        deletePreset,
        renamePreset,
        selectPreset,
    } = useProfileConfig({
        selectedStrategy,
        defaultConfig: DEFAULT_CONFIG,
        generateUUID,
        onLog: addLog,
        accountId: effectiveAccountId, // 실계좌 우선 자동 선택된 계좌 ID
        exchangeName: preliminaryExchangeName, // 거래소별 기본값 적용 (profileMeta 로드 후 activeExchangeName으로 갱신)
    });

    // Profile-level symbols alias (하위 컴포넌트/훅 변경 불필요)
    const savedSymbols = profileSymbols;
    const setSavedSymbols = setProfileSymbols;

    // Profile-Account 초기값 설정
    // 프로필 로딩 완료 후, account_id가 없을 때만 effectiveAccountId로 초기화
    // isConfigLoaded 게이트: 로딩 중 null 상태에서 Kiwoom으로 덮어쓰는 레이스 컨디션 방지
    useEffect(() => {
        if (isConfigLoaded && effectiveAccountId && !profileMeta.account_id) {
            setProfileMeta(prev => ({ ...prev, account_id: effectiveAccountId }));
        }
    }, [isConfigLoaded, effectiveAccountId, profileMeta.account_id]);

    // Active account info (profileMeta.account_id 우선, effectiveAccountId 폴백)
    const activeAccount = accounts.find(a => a.id === (profileMeta.account_id || effectiveAccountId)) || defaultAccount;
    const activeAccountName = activeAccount?.account_name || null;
    const activeExchangeName = activeAccount?.exchange_name || DEFAULT_EXCHANGE;
    const isCryptoExchange = activeExchangeName?.startsWith('Binance');

    // Profile Lock Detection (extracted to useProfileLock hook)
    const { isProfileLocked } = useProfileLock({ selectedProfileId, profileName: profileMeta.name });

    // New Profile Modal State
    const [isNewProfileModalOpen, setIsNewProfileModalOpen] = useState(false);
    const [isSaveAsModalOpen, setIsSaveAsModalOpen] = useState(false);
    const [saveAsName, setSaveAsName] = useState('');
    const [saveAsDescription, setSaveAsDescription] = useState('');
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


    const [activeTab, setActiveTab] = useState(() => {
        const saved = localStorage.getItem(STORAGE_KEYS.ACTIVE_TAB);
        const val = saved !== null ? parseInt(saved, 10) : 0;
        // Redirect from old Live tab (-2) to Rank 1 (0) - Live tab moved to /live page
        return val === -2 ? 0 : val;
    });
    const [isDirty, setIsDirty] = useState(false); // Track unsaved configuration changes
    const [pendingTabSwitch, setPendingTabSwitch] = useState(null); // Store pending tab switch during confirmation

    useEffect(() => {
        localStorage.setItem(STORAGE_KEYS.ACTIVE_TAB, activeTab);
    }, [activeTab]);
    // isConfigLoaded는 useProfileConfig 훅에서 제공됨
    const lastInitializedStrategyRef = useRef(null); // Track which strategy schema was initialized for
    // Live refs moved to LiveTradingView.jsx



    // Backtest Settings
    // const [fromDate, setFromDate] = useState(""); // YYYY-MM-DD
    // const [initialCapital, setInitialCapital] = useState(() => {
    //    const saved = localStorage.getItem('initialCapital');
    //    return saved ? parseInt(saved, 10) : 10000000;
    // });


    // Custom Confirmation Modal State


    // Note: currentSymbol and savedSymbols are now managed by WatchlistContext (synced with DB)

    // executionMode is now stored in profile (profileMeta.execution_mode)
    // No need for separate localStorage/DB sync

    // liveRankIndex effects moved to LiveTradingView.jsx

    // Persistence logic removed for initialCapital

    // [REFACTORED] 설정 로드 로직이 useProfileConfig 훅으로 이동됨
    // Profile-Centric Architecture: 프로필이 설정의 단일 진실 소스

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

    // needsInit 플래그 처리 - 프로필이 선택되었고 DB가 비어있을 때 호출
    // 프로필 중심 아키텍처: 프로필 없이는 configList 초기화 안 함
    useEffect(() => {
        if (needsInit && selectedProfileId && selectedStrategy) {
            console.log("[StrategyView] needsInit detected with profile, configList.length:", configList.length);
            // 훅에서 이미 기본 설정을 생성했으면 initDefaultList 호출 생략
            if (configList.length === 0) {
                console.log("[StrategyView] configList empty, calling initDefaultList");
                initDefaultList();
            }
            setNeedsInit(false);
            setIsDirty(false);  // 초기화는 "변경"이 아니므로 dirty 리셋
        }
    }, [needsInit, selectedProfileId, selectedStrategy, configList.length]);

    // ==========================================
    // Dynamic Config Helpers
    // ==========================================
    const getDynamicDefaultConfig = () => buildDynamicDefaultConfig(selectedStrategy, currentSymbol, DEFAULT_CONFIG, activeExchangeName);
    const getDynamicOptValues = () => buildDynamicOptValues(selectedStrategy, DEFAULT_OPT_VALUES, getOptRangeDefaults(activeExchangeName));

    const getSymbolCompareConfig = () => {
        const rank1 = configList[0];
        if (symbolCompareConfig) {
            if (rank1 && (!symbolCompareConfig.from_date || !symbolCompareConfig.to_date)) {
                return {
                    ...symbolCompareConfig,
                    from_date: symbolCompareConfig.from_date || rank1.from_date || '',
                    to_date: symbolCompareConfig.to_date || rank1.to_date || '',
                };
            }
            return symbolCompareConfig;
        }
        const baseConfig = rank1 || getDynamicDefaultConfig();
        return { ...baseConfig, symbol: '', tabName: 'Symbol Compare' };
    };

    const currentConfig = (activeTab >= 0 && configList[activeTab])
        ? configList[activeTab]
        : (activeTab === -3
            ? getSymbolCompareConfig()
            : (activeTab === -2 && configList.length > 0 ? configList[0] : getDynamicDefaultConfig()));

    const activeSymbol = currentConfig?.symbol || currentSymbol;
    const isSymbolValid = !!activeSymbol && activeSymbol.trim().length > 0;

    // ==========================================
    // Extracted Hooks
    // ==========================================
    const {
        copiedParams, copyPasteFeedback,
        copiedOptSettings, optCopyPasteFeedback,
        handleCopyParams, handlePasteParams,
        handleCopyOptSettings, handlePasteOptSettings,
        getStrategyParamNames
    } = useCopyPaste({
        configList, setConfigList, activeTab,
        parameterSchema: selectedStrategy?.parameter_schema,
        symbolCompareConfig, setSymbolCompareConfig,
        setIsDirty, setIsSymbolCompareDirty, addLog,
        extractParamNames
    });

    const {
        assetImportExportFeedback, assetImportError,
        paramImportExportFeedback, paramImportError,
        handleExportAssets, handleImportAssets,
        handleExportParams, handleImportParams
    } = useImportExport({
        configList, setConfigList, activeTab,
        symbolCompareConfig, setSymbolCompareConfig,
        setIsDirty, setIsSymbolCompareDirty,
        savedSymbols, setSavedSymbols, activeAccountName,
        selectedStrategy, getStrategyParamNames, addLog
    });

    const {
        selectedCompareSymbols, setSelectedCompareSymbols,
        stockCompareResults, setStockCompareResults,
        isStockComparing, stockCompareProgress,
        compareSortConfig, setCompareSortConfig,
        handleStockCompareBacktest, handleExportCompareResults
    } = useSymbolComparison({
        symbolCompareConfig, configList, selectedStrategy,
        savedSymbols, setIsSymbolCompareDirty, addLog,
        saveProfile, selectedProfileId,
        exchangeName: activeExchangeName
    });

    const {
        dataStatus, isFetchingData, fetchMessage, setFetchMessage,
        isDataUpdated, checkDataStatus, handleFetchData, handleUpdateAllData
    } = useDataFetching({
        currentConfig, currentSymbol, configList, setConfigList,
        activeTab, isConfigLoaded, addLog, exchangeName: activeExchangeName
    });

    const {
        optResults, setOptResults, optProgress, optError, setOptError,
        isOptimizing, sortConfig, heavyOptTaskId, heavyOptStatus,
        pendingOptResult, setPendingOptResult, completedOptTaskId,
        currentOptTaskId, isCancelling, isHeavyOptRunning, optStatusMessage,
        executionMode, setExecutionMode,
        optAlertModal, setOptAlertModal,
        runOptimization, cancelOptimization, startHeavyOptimization,
        handleCancelHeavyOpt, handleSort, exportOptResultsToCSV,
        downloadFullOptResultsCSV, applyOptParams, savePendingOptResult,
        discardPendingOptResult, downloadHeavyOptCSV, clearHeavyOptTask,
        handleOptEnableChange, handleOptValueChange, resetOptState
    } = useOptimization({
        currentConfig, selectedStrategy, configList, setConfigList,
        activeTab, savedSymbols, addLog,
        symbolCompareConfig, setSymbolCompareConfig,
        setIsDirty, setIsSymbolCompareDirty,
        selectedCompareSymbols, selectedProfileId, currentSymbol,
        exchangeName: activeExchangeName,
    });

    const {
        scoreWeightsMap, setScoreWeightsMap,
        scoreWeights, isRecalculating, showWeightPanel, setShowWeightPanel,
        handleWeightChange, applyWeightPreset, recalculateScores,
        initScoreWeightsFromProfile
    } = useScoreWeights({
        activeTab, configList, setConfigList,
        symbolCompareConfig, setSymbolCompareConfig,
        completedOptTaskId, heavyOptTaskId,
        currentConfig,
        optResults, setOptResults,
        selectedStrategy, savedSymbols, addLog
    });

    // Reset related state when profile changes (Symbol Compare, Integrated, Backtest results)
    const prevProfileIdRef = useRef(selectedProfileId);
    const isFirstProfileLoadRef = useRef(true);
    useEffect(() => {
        if (prevProfileIdRef.current !== selectedProfileId && selectedProfileId !== null) {
            console.log('[StrategyView] Profile changed, resetting tab states');

            // Reset Integrated tab state
            setIntegratedResults(null);
            setShowIntegratedAnalysis(false);

            // Reset Symbol Compare tab state (hook manages its own state)
            setSelectedCompareSymbols([]);
            setStockCompareResults([]);
            setIsSymbolCompareDirty(false);

            // Reset backtest result
            setBacktestResult(null);

            // Reset optimization state (hook manages all opt state)
            resetOptState();

            // Restore score weights from profile config
            initScoreWeightsFromProfile(configList, symbolCompareConfig);

            // On first load (page refresh), restore saved tab from localStorage
            // On subsequent profile switches, reset to Rank 0
            if (isFirstProfileLoadRef.current) {
                isFirstProfileLoadRef.current = false;
                // activeTab already initialized from localStorage in useState
            } else {
                setActiveTab(0);
            }
        }
        prevProfileIdRef.current = selectedProfileId;
    }, [selectedProfileId]);

    // ═══════════════════════════════════════════════════════════════════════════
    // Navigation Guards — 저장하지 않은 변경사항이 있을 때 페이지 이탈 방지
    // ═══════════════════════════════════════════════════════════════════════════
    const hasPendingChanges = useMemo(() =>
        isProfileDirty || isDirty || isSymbolCompareDirty || !!pendingOptResult,
        [isProfileDirty, isDirty, isSymbolCompareDirty, pendingOptResult]
    );

    // beforeunload (브라우저 닫기/새로고침 방지)
    // Note: useBlocker는 createBrowserRouter에서만 지원되므로 beforeunload만 사용
    useEffect(() => {
        const handler = (e) => {
            if (hasPendingChanges) {
                e.preventDefault();
                e.returnValue = '';
            }
        };
        window.addEventListener('beforeunload', handler);
        return () => window.removeEventListener('beforeunload', handler);
    }, [hasPendingChanges]);

    // Sync Symbol Compare state from profile's symbolCompareConfig
    useEffect(() => {
        if (symbolCompareConfig) {
            // Load selectedSymbols from profile
            if (symbolCompareConfig.selectedSymbols) {
                setSelectedCompareSymbols(symbolCompareConfig.selectedSymbols);
            }
            // Load results from profile
            if (symbolCompareConfig.results) {
                setStockCompareResults(symbolCompareConfig.results);
            }
            console.log('[StrategyView] Symbol Compare loaded from profile:', {
                symbols: symbolCompareConfig.selectedSymbols?.length || 0,
                results: symbolCompareConfig.results?.length || 0
            });
        }
    }, [symbolCompareConfig]);

    // Sync selectedStrategy when profile is auto-selected (on mount)
    useEffect(() => {
        if (profileMeta.strategy_name && !selectedStrategy && strategies.length > 0) {
            const matchingStrategy = strategies.find(s => s.id === profileMeta.strategy_name);
            if (matchingStrategy) {
                console.log('[StrategyView] Auto-syncing strategy from profile:', matchingStrategy.name);
                setSelectedStrategy(matchingStrategy);
            }
        }
    }, [profileMeta.strategy_name, selectedStrategy, strategies]);

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

                // Tab deletion is reflected in configList state
                // User must explicitly save profile to persist changes
                setIsDirty(true); // Mark as dirty to prompt save
            },
            true // isDanger
        );
    };

    const handleConfigChange = (key, value) => {
        if (activeTab === -1) return; // Cannot edit in Integrated View
        if (isProfileLocked) return; // Cannot edit locked profile (live session in use)

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

        // Validate from_date: Use exchange MAX_DAYS as the limit
        if (key === 'from_date' && value) {
            // Compare dates only (strip time component to avoid timezone issues)
            const selectedStr = value; // "YYYY-MM-DD"
            const today = new Date();

            const minAllowedDate = new Date(today);
            minAllowedDate.setDate(minAllowedDate.getDate() - getMaxDays(activeExchangeName));
            const limitDesc = getMaxDaysLabel(activeExchangeName);

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

    // (Copy/Paste, Import/Export, Dynamic Config, currentConfig — all moved to hooks section above)

    // 3. Persistence: Load Results when switching tabs
    useEffect(() => {
        console.log('[Persistence] useEffect triggered - activeTab:', activeTab, 'isConfigLoaded:', isConfigLoaded, 'strategyId:', selectedStrategy?.id);

        // Reset transient states
        setShowChart(false);

        // Restore Results on Tab Change

        // If not loaded yet, wait
        if (!isConfigLoaded) {
            console.log('[Persistence] Skipping: isConfigLoaded is false');
            return;
        }

        let targetUUID = null;

        if (activeTab === -1) {
            targetUUID = getIntegratedUUID(selectedProfileId);
            console.log('[Persistence] Integrated tab - UUID:', targetUUID, 'profileId:', selectedProfileId);
        } else if (activeTab === -3) {
            targetUUID = getCrossOptUUID(selectedProfileId);
            console.log('[Persistence] Cross-opt tab - UUID:', targetUUID, 'profileId:', selectedProfileId);
        } else {
            targetUUID = configList[activeTab]?.uuid;
            console.log('[Persistence] Rank tab', activeTab, '- UUID:', targetUUID);
        }

        if (!targetUUID) {
            // Should not happen for activeTab !== -1/-3 if configList is valid
            if (activeTab !== -1 && activeTab !== -3) {
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
                    const formattedResults = data.optimization.results.map((item, index) => {
                        const stats = normalizeStats(item);
                        return {
                            ...(item.config || {}),
                            ...stats, // Normalized stats with consistent types
                            symbol: item.symbol || item.config?.symbol || '',
                            symbolName: savedSymbols?.find(s => s.code === (item.symbol || item.config?.symbol))?.name || '',
                            return: stats.total_return,
                            trades: stats.total_trades,
                            score: item.score,
                            full_config: item.config || {},
                            rank: item.rank > 0 ? item.rank : (index + 1)
                        };
                    });
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
    }, [activeTab, isConfigLoaded, selectedProfileId]); // Re-run on tab change or profile change

    // 4. Persistence & Initialization
    // Strategy list & selection are now managed by StrategiesContext
    useEffect(() => {
        setExecutionLogs([]); // Clear logs on page load/refresh
    }, []);

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
            getSymbolInfo(currentSymbol)
                .then(infoData => {
                    if (infoData.name && infoData.name !== currentSymbol) {
                        setSavedSymbols(prev => prev.map(s =>
                            s.code === currentSymbol ? { ...s, name: infoData.name } : s
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
        setIsDirty(true); // Mark as dirty when running backtest

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

            // to_date: fixed end boundary for reproducible results (default: yesterday)
            const defaultToDate = new Date(Date.now() - 86400000).toISOString().split('T')[0];

            // Ensure dates are explicitly stored in config (not just display fallbacks)
            const resolvedFromDate = activeConfig?.from_date || "";
            const resolvedToDate = activeConfig?.to_date || defaultToDate;
            if (!configOverride) {
                if (!activeConfig.to_date && resolvedToDate) {
                    handleConfigChange('to_date', resolvedToDate);
                }
                if (!activeConfig.from_date && resolvedFromDate) {
                    handleConfigChange('from_date', resolvedFromDate);
                }
            }

            const payload = {
                symbol: activeConfig.symbol || currentSymbol, // Use config's symbol if available, else global
                from_date: resolvedFromDate,
                days: activeConfig?.days || getDefaultDays(activeExchangeName),
                initial_capital: activeConfig?.initial_capital || getDefaultCapital(activeExchangeName),
                interval: activeConfig?.interval || "1m",
                to_date: resolvedToDate,
                config: cleanConfig,
                exchange_name: activeExchangeName // 프로필 계좌 기반 거래소 자동 결정
            };

            setBacktestStatus({ status: 'running', message: `Running Backtest on ${activeConfig.symbol || currentSymbol}...` });

            const backtestData = await apiRunBacktest(strategyId, payload);
            setBacktestResult(backtestData);
            setBacktestStatus({ status: 'success', message: 'Backtest Completed' });

            // Persistence: save result + auto-save profile (dates & config synced with results)
            if (activeConfig.uuid) {
                saveStrategyResult(activeConfig.uuid, 'backtest', backtestData).catch(err => console.error("Failed to save backtest result", err));
            }
            if (selectedProfileId) {
                saveProfile().then(() => {
                    setIsDirty(false);
                    setIsSymbolCompareDirty(false);
                }).catch(err => console.warn("Auto-save profile after backtest failed:", err));
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

    // Profile Save (header Save button handler) — DB 저장만, 자동 백테스트 없음
    const handleProfileSave = async () => {
        if (!selectedProfileId) {
            openConfirm("⚠️ No Profile Selected", "프로필을 먼저 선택하거나 새로 만들어주세요.", () => {}, true);
            return;
        }
        if (isProfileLocked) {
            openConfirm("🔒 Profile Locked", "라이브 세션에서 사용 중인 프로필은 수정할 수 없습니다. 'Save As'로 복사본을 만들어 사용해주세요.", () => {}, true);
            return;
        }

        try {
            // 1. Merge Symbol Compare local state into symbolCompareConfig before save
            if (symbolCompareConfig) {
                setSymbolCompareConfig({
                    ...symbolCompareConfig,
                    selectedSymbols: selectedCompareSymbols,
                    results: stockCompareResults,
                });
            }

            // 2. DB 저장
            await saveProfile();

            // 3. Save pending optimization results if exists
            if (pendingOptResult) {
                await saveStrategyResult(pendingOptResult.tabUuid, 'optimization', pendingOptResult.data);
                addLog('Optimization results saved to DB', 'info');
                setPendingOptResult(null);
            }

            // 4. Clear dirty flags
            setIsDirty(false);
            setIsSymbolCompareDirty(false);

            addLog('Profile saved successfully', 'success');
        } catch (e) {
            console.error("Failed to save profile:", e);
            openConfirm("❌ Save Failed", `프로필 저장에 실패했습니다.\n\n${e.message || "다시 시도해주세요."}`, () => {}, true);
        }
    };

    // Discard all changes (restore from profile) — 모든 탭의 변경사항 폐기
    const handleDiscardAll = () => {
        try {
            discardChanges(); // useProfileConfig hook (원본 복원 + localStorage draft 삭제)
            setPendingOptResult(null);
            setIsDirty(false);
            setIsSymbolCompareDirty(false);
            addLog('Changes discarded, reverted to saved state', 'info');
        } catch (e) {
            console.error("Failed to discard changes:", e);
            addLog('Failed to discard changes', 'error');
        }
    };

    // Tab Switch — draft가 자동 저장되므로 탭 전환 시 확인 불필요 (pendingOptResult만 체크)
    const handleTabSwitch = (newTabIndex) => {
        // Check for pending optimization results (not saved to localStorage draft)
        if (pendingOptResult) {
            setPendingTabSwitch(newTabIndex);
            openConfirm(
                "Unsaved Optimization Results",
                "You have unsaved optimization results.\n\nWould you like to save them before switching tabs?",
                async () => {
                    // Save & Switch
                    await savePendingOptResult();
                    setActiveTab(newTabIndex);
                    localStorage.setItem(STORAGE_KEYS.ACTIVE_TAB, newTabIndex.toString());
                    setPendingTabSwitch(null);
                },
                false,
                "Save & Switch",
                "Discard & Switch",
                () => {
                    // Discard & Switch
                    discardPendingOptResult();
                    setActiveTab(newTabIndex);
                    localStorage.setItem(STORAGE_KEYS.ACTIVE_TAB, newTabIndex.toString());
                    setPendingTabSwitch(null);
                }
            );
            return;
        }

        // No confirmation needed — changes auto-saved to localStorage draft
        setActiveTab(newTabIndex);
        localStorage.setItem(STORAGE_KEYS.ACTIVE_TAB, newTabIndex.toString());
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
                // Save & Switch Strategy (프로필 중심)
                try {
                    if (selectedProfileId) {
                        await saveProfile();
                        console.log("Profile saved before strategy change");
                    }
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

    // ==========================================
    // All data/optimization/AI/score/comparison handlers moved to hooks above
    // ==========================================

    return (
        <div className="flex flex-col gap-6 pb-10">
            {/* Top Bar: Profile Selector (Profile-Centric Architecture) */}
            <div className="shrink-0 z-20 bg-white/5 border border-white/10 rounded-xl px-4 pt-4 pb-5 overflow-hidden">
                <div className="flex flex-col gap-3">
                    {/* Row 1: Profile Header */}
                    <div className="flex items-center justify-between">
                        <h3 className="font-bold text-gray-200 text-sm flex items-center gap-2">
                            <FolderOpen size={14} className="text-emerald-400" /> Strategy Profile
                        </h3>
                        {/* Profile Actions */}
                        <div className="flex items-center gap-2">
                            <button
                                onClick={() => setIsNewProfileModalOpen(true)}
                                className="px-3 py-1.5 bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-400 text-xs font-bold rounded-lg transition-all flex items-center gap-1.5"
                            >
                                <Plus size={14} />
                                New Profile
                            </button>
                            {selectedProfileId && !isProfileLocked && (
                                <button
                                    onClick={() => {
                                        openConfirm(
                                            'Delete Profile',
                                            `정말 "${profileMeta.name}" 프로필을 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.`,
                                            async () => {
                                                try {
                                                    await deleteCurrentProfile();
                                                    setSelectedStrategy(null);
                                                } catch (e) {
                                                    console.error('Failed to delete profile:', e);
                                                }
                                            },
                                            true,
                                            'Delete',
                                            'Cancel'
                                        );
                                    }}
                                    className="px-3 py-1.5 bg-red-600/20 hover:bg-red-600/30 text-red-400 text-xs font-bold rounded-lg transition-all flex items-center gap-1.5"
                                >
                                    <Trash2 size={14} />
                                </button>
                            )}
                        </div>
                    </div>

                    {/* Row 2: Profile Dropdown & Info */}
                    <div className="flex flex-col md:flex-row items-stretch gap-4 w-full">
                        {/* Profile Dropdown */}
                        <div className="relative w-full md:max-w-md">
                            <select
                                value={selectedProfileId || ''}
                                onChange={(e) => {
                                    const newProfileId = e.target.value;
                                    if (!newProfileId) {
                                        // Clear selection
                                        selectProfile(null);
                                        setSelectedStrategy(null);
                                        setBacktestResult(null);
                                        setIsDirty(false);
                                        return;
                                    }

                                    // Check for unsaved changes (all dirty states)
                                    const hasPendingChanges = isProfileDirty || isDirty || isSymbolCompareDirty || !!pendingOptResult;
                                    if (hasPendingChanges) {
                                        openConfirm(
                                            '저장하지 않은 변경사항',
                                            '현재 프로필에 저장하지 않은 변경사항이 있습니다. 저장하시겠습니까?',
                                            async () => {
                                                // Save then switch
                                                await handleProfileSave();
                                                await selectProfile(newProfileId);
                                                const profile = profiles.find(p => p.id === newProfileId);
                                                if (profile) {
                                                    const strat = strategies.find(s => s.id === profile.strategy_name);
                                                    setSelectedStrategy(strat);
                                                }
                                            },
                                            false,
                                            'Save',
                                            'Discard',
                                            async () => {
                                                // Discard and switch
                                                handleDiscardAll();
                                                await selectProfile(newProfileId);
                                                const profile = profiles.find(p => p.id === newProfileId);
                                                if (profile) {
                                                    const strat = strategies.find(s => s.id === profile.strategy_name);
                                                    setSelectedStrategy(strat);
                                                }
                                            }
                                        );
                                    } else {
                                        // No unsaved changes, switch directly
                                        selectProfile(newProfileId);
                                        const profile = profiles.find(p => p.id === newProfileId);
                                        if (profile) {
                                            const strat = strategies.find(s => s.id === profile.strategy_name);
                                            setSelectedStrategy(strat);
                                        }
                                    }
                                }}
                                className="w-full bg-black/40 border border-white/20 text-white cursor-pointer focus:border-emerald-500 rounded-lg px-4 py-3 appearance-none outline-none text-sm font-medium"
                            >
                                <option value="" className="bg-slate-900 text-gray-400">
                                    프로필을 선택하세요
                                </option>
                                {profiles.map(profile => (
                                    <option key={profile.id} value={profile.id} className="bg-slate-900 text-white">
                                        {profile.name} ({profile.strategy_name})
                                    </option>
                                ))}
                            </select>
                            <div className="absolute right-4 top-1/2 -translate-y-1/2 pointer-events-none text-gray-400">
                                ▼
                            </div>
                        </div>

                        {/* Profile Info & Strategy + Account */}
                        {selectedProfile && selectedStrategy && (
                            <div className="hidden md:flex items-center gap-3 text-sm text-gray-400 border-l border-white/10 pl-4 flex-1">
                                <div className="flex items-center gap-2">
                                    <Rocket size={14} className="text-blue-400" />
                                    <span className="text-white font-medium">{selectedStrategy.name}</span>
                                </div>
                                {isProfileLocked && (
                                    <span className="flex items-center gap-1 text-xs text-orange-400 bg-orange-500/10 px-2 py-0.5 rounded">
                                        <Lock size={10} /> LIVE
                                    </span>
                                )}
                                <span className="text-gray-600">|</span>
                                {/* Account Selector */}
                                <div className="flex items-center gap-1.5">
                                    <Building2 size={13} className="text-gray-500" />
                                    <select
                                        value={profileMeta.account_id || ''}
                                        onChange={(e) => {
                                            const newAccountId = e.target.value ? parseInt(e.target.value) : null;
                                            setProfileMeta(prev => ({ ...prev, account_id: newAccountId }));
                                        }}
                                        className="bg-transparent border border-white/10 rounded px-2 py-0.5 text-xs text-white outline-none focus:border-emerald-500/50 cursor-pointer appearance-none max-w-[160px]"
                                        title="연결된 거래 계좌"
                                    >
                                        <option value="" className="bg-slate-900 text-gray-400">계좌 없음</option>
                                        {accounts.filter(a => {
                                            if (a.is_disabled) return false;
                                            // 프로필에 명시적으로 계좌가 연결된 경우만 같은 거래소 필터
                                            if (profileMeta.account_id && activeAccount?.exchange_name) {
                                                return a.exchange_name === activeAccount.exchange_name;
                                            }
                                            return true;
                                        }).map(acc => (
                                            <option key={acc.id} value={acc.id} className="bg-slate-900 text-white">
                                                {acc.account_name} ({acc.exchange_name})
                                            </option>
                                        ))}
                                    </select>
                                </div>
                                <span className="flex-1 truncate text-gray-500">{profileMeta.description || ''}</span>
                                <button
                                    onClick={() => setIsDetailModalOpen(true)}
                                    className="p-1.5 rounded-lg bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 hover:text-blue-300 transition-all group relative"
                                    title="View Detailed Strategy Specification"
                                >
                                    <HelpCircle size={16} />
                                </button>
                            </div>
                        )}
                    </div>

                    {/* Row 3: Lock Banner or Save/Discard Buttons */}
                    {selectedProfileId && isProfileLocked && (
                        <div className="flex items-center gap-3 pt-2 border-t mt-1 border-orange-500/30">
                            <div className="flex-1 flex items-center gap-2 text-xs text-orange-400">
                                <Lock size={12} />
                                <span>라이브 세션에서 사용 중 — 수정 불가</span>
                            </div>
                            <button
                                onClick={() => {
                                    setSaveAsName(profileMeta.name + ' (Copy)');
                                    setSaveAsDescription(profileMeta.description || '');
                                    setIsSaveAsModalOpen(true);
                                }}
                                className="px-3 py-1.5 bg-blue-600/20 hover:bg-blue-600/30 text-blue-400 text-xs font-bold rounded-lg transition-all flex items-center gap-1.5"
                            >
                                <Copy size={14} />
                                Save As...
                            </button>
                        </div>
                    )}
                    {selectedProfileId && !isProfileLocked && (
                        <div className={`flex items-center gap-3 pt-2 border-t mt-1 ${
                            (isProfileDirty || isDirty || isSymbolCompareDirty || pendingOptResult)
                                ? 'border-yellow-500/30'
                                : 'border-white/10'
                        }`}>
                            {/* 변경 상태 표시 */}
                            <div className="flex-1 text-xs flex items-center gap-2">
                                {(isProfileDirty || isDirty || isSymbolCompareDirty || pendingOptResult) ? (
                                    <span className="text-yellow-400 flex items-center gap-2">
                                        <span className="animate-pulse">●</span>
                                        변경사항이 있습니다
                                    </span>
                                ) : (
                                    <span className="text-gray-500 flex items-center gap-1">
                                        <Check size={12} /> 저장됨
                                    </span>
                                )}
                            </div>
                            <button
                                onClick={handleDiscardAll}
                                disabled={!(isProfileDirty || isDirty || isSymbolCompareDirty || pendingOptResult)}
                                className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-gray-200 text-xs font-bold rounded-lg transition-all flex items-center gap-1.5 disabled:opacity-30 disabled:cursor-not-allowed"
                            >
                                <X size={14} />
                                Discard
                            </button>
                            <button
                                onClick={handleProfileSave}
                                disabled={!(isProfileDirty || isDirty || isSymbolCompareDirty || pendingOptResult) || saveStatus === 'saving'}
                                className="px-4 py-1.5 bg-gradient-to-r from-emerald-600 to-emerald-500 hover:from-emerald-500 hover:to-emerald-400 text-white text-xs font-bold rounded-lg transition-all disabled:opacity-30 disabled:cursor-not-allowed flex items-center gap-1.5"
                            >
                                {saveStatus === 'saving' ? (
                                    <><div className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin" /> Saving...</>
                                ) : saveStatus === 'saved' ? (
                                    <><Check size={14} /> Saved!</>
                                ) : (
                                    <><Save size={14} /> Save</>
                                )}
                            </button>
                            <button
                                onClick={() => {
                                    setSaveAsName(profileMeta.name + ' (Copy)');
                                    setSaveAsDescription(profileMeta.description || '');
                                    setIsSaveAsModalOpen(true);
                                }}
                                className="px-3 py-1.5 bg-blue-600/20 hover:bg-blue-600/30 text-blue-400 text-xs font-bold rounded-lg transition-all flex items-center gap-1.5"
                            >
                                <Copy size={14} />
                                Save As...
                            </button>
                        </div>
                    )}
                </div>
            </div>

            {/* New Profile Modal */}
            <NewProfileModal
                isOpen={isNewProfileModalOpen}
                onClose={() => setIsNewProfileModalOpen(false)}
                onProfileCreated={async (data) => {
                    try {
                        // 1. Set strategy first
                        const strat = strategies.find(s => s.id === data.strategyId);
                        setSelectedStrategy(strat);

                        // 2. Determine default symbols based on account's exchange
                        const account = accounts.find(a => a.id === data.accountId);
                        const exchangeName = account?.exchange_name || DEFAULT_EXCHANGE;
                        const defaultSymbols = exchangeName.startsWith('Binance')
                            ? [{ code: 'BTCUSDT', name: 'Bitcoin' }, { code: 'ETHUSDT', name: 'Ethereum' }]
                            : [{ code: '005930', name: '삼성전자' }, { code: '000660', name: 'SK하이닉스' }];

                        // 3. Create new profile with default config + account + symbols + exchange defaults (atomic operation)
                        const result = await createNewProfile(data.name, data.description, data.strategyId, data.accountId, defaultSymbols, exchangeName);
                        console.log('[NewProfile] Created:', result);

                        addLog(`✅ 프로필 생성됨: ${data.name}`, 'success');
                    } catch (e) {
                        console.error('[NewProfile] Failed to create:', e);
                        addLog(`❌ 프로필 생성 실패: ${e.message}`, 'error');
                        openConfirm("❌ Profile Creation Failed", e.message || "프로필 생성에 실패했습니다.", () => {}, true);
                    }
                }}
                strategies={strategies}
                accounts={accounts}
            />

            {/* Save As Modal */}
            {isSaveAsModalOpen && (
                <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <div className="bg-gradient-to-b from-gray-900 to-gray-950 border border-white/10 rounded-2xl w-full max-w-md shadow-2xl p-6">
                        <h3 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
                            <Copy size={20} className="text-blue-400" />
                            Save Profile As
                        </h3>
                        <div className="space-y-4">
                            <div>
                                <label className="block text-sm text-gray-400 mb-1">New Profile Name</label>
                                <input
                                    type="text"
                                    value={saveAsName}
                                    onChange={(e) => setSaveAsName(e.target.value)}
                                    className="w-full bg-black/40 border border-white/10 rounded-lg px-4 py-2.5 text-white outline-none focus:border-blue-500/50"
                                    autoFocus
                                />
                            </div>
                            <div>
                                <label className="block text-sm text-gray-400 mb-1">Description</label>
                                <textarea
                                    value={saveAsDescription}
                                    onChange={(e) => setSaveAsDescription(e.target.value)}
                                    rows={2}
                                    className="w-full bg-black/40 border border-white/10 rounded-lg px-4 py-2.5 text-white outline-none focus:border-blue-500/50 resize-none"
                                />
                            </div>
                        </div>
                        <div className="flex justify-end gap-3 mt-6">
                            <button
                                onClick={() => setIsSaveAsModalOpen(false)}
                                className="px-4 py-2 text-gray-400 hover:text-white transition-colors"
                            >
                                Cancel
                            </button>
                            <button
                                onClick={async () => {
                                    if (!saveAsName.trim()) return;
                                    try {
                                        await saveProfileAs(saveAsName.trim(), saveAsDescription.trim());
                                        setIsSaveAsModalOpen(false);
                                        setIsDirty(false);
                                    } catch (e) {
                                        console.error('Failed to save as:', e);
                                    }
                                }}
                                disabled={!saveAsName.trim()}
                                className="px-6 py-2 bg-gradient-to-r from-blue-600 to-blue-500 hover:from-blue-500 hover:to-blue-400 text-white font-bold rounded-lg transition-all disabled:opacity-50"
                            >
                                Save
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Main Content Area (No Scroll Container) */}
            <div className="space-y-6 pb-20">
                {/* 프로필 중심 아키텍처: 프로필 선택이 필수 */}
                {!selectedProfileId ? (
                    <div className="flex flex-col items-center justify-center p-20 text-gray-400 bg-white/5 border border-white/10 rounded-xl">
                        <FolderOpen size={48} className="mb-4 text-emerald-500/50" />
                        <p className="text-lg font-medium">프로필을 선택하거나 새로 만드세요</p>
                        <p className="text-sm text-gray-500 mt-2">위에서 기존 프로필을 선택하거나 "New Profile" 버튼을 클릭하세요</p>
                        <button
                            onClick={() => setIsNewProfileModalOpen(true)}
                            className="mt-6 px-6 py-3 bg-gradient-to-r from-emerald-600 to-emerald-500 hover:from-emerald-500 hover:to-emerald-400 text-white font-bold rounded-xl transition-all flex items-center gap-2"
                        >
                            <Plus size={20} />
                            New Profile
                        </button>
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
                            {/* Row 1: Main Tabs (Integrated, Symbol Compare) */}
                            {/* Live Operation tab moved to /live page */}
                            <div className="flex items-center gap-2 mb-3">
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
                                                {!isProfileLocked && showLeft && (
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
                                                {!isProfileLocked && showRight && (
                                                    <span
                                                        onClick={(e) => moveRankTab(idx, 1, e)}
                                                        className="hover:bg-black/20 rounded px-1 -mr-1 text-white/50 hover:text-white"
                                                    >
                                                        ▶
                                                    </span>
                                                )}

                                                {/* Delete Button */}
                                                {!isProfileLocked && configList.length > 1 && (
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
                                {!isProfileLocked && (
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
                                            localStorage.setItem(STORAGE_KEYS.ACTIVE_TAB, (newList.length - 1).toString());

                                            // Mark profile as dirty - actual save happens via profile save
                                            setIsDirty(true);
                                        }}
                                        className="px-3 py-2 rounded-lg bg-white/5 text-gray-400 hover:bg-white/10 hover:text-white transition-all"
                                    >
                                        +
                                    </button>
                                )}
                            </div>
                            {/* Active tab indicator line */}
                            <div className="mt-3 pt-3 border-t border-white/10 flex items-center gap-2 text-xs text-gray-500">
                                <div className="w-1.5 h-1.5 rounded-full bg-blue-500/60 animate-pulse" />
                                <span>{activeTab === -1 ? 'Integrated Portfolio' : activeTab === -3 ? 'Symbol Compare' : `Rank ${activeTab + 1}`} selected</span>
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
                                                    onVersionChange={(idx, newParams, presetInfo) => {
                                                        // Update configList with params from selected preset
                                                        const parameterFields = selectedStrategy?.parameter_schema?.fields?.map(f => f.key || f.name) || [];

                                                        setConfigList(prev => {
                                                            const updated = [...prev];
                                                            if (updated[idx]) {
                                                                const filteredParams = {};
                                                                parameterFields.forEach(key => {
                                                                    if (newParams[key] !== undefined) {
                                                                        filteredParams[key] = newParams[key];
                                                                    }
                                                                });

                                                                updated[idx] = {
                                                                    ...updated[idx],
                                                                    ...filteredParams,
                                                                    selected_preset_id: presetInfo.id,
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
                                                    const rank1Capital = displayConfig?.initial_capital || DEFAULT_INITIAL_CAPITAL;
                                                    const displayCapital = (isIntegrated && profileMeta.execution_mode === 'parallel')
                                                        ? rank1Capital * activeConfigCount
                                                        : rank1Capital;

                                                    return (
                                                        <div className="flex flex-wrap gap-6">
                                                            <div className="text-left">
                                                                <label className="text-xs text-gray-400 mb-1 block">
                                                                    {isIntegrated && profileMeta.execution_mode === 'parallel'
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
                                                                    Start Date {dataStatus?.start_date ? `(${dataStatus.start_date}~)` : `(Max ${getMaxDaysLabel(activeExchangeName)})`} {isIntegrated && <span className="text-blue-400">(Inherited from Rank 1)</span>}
                                                                </label>
                                                                <DateDropdown
                                                                    value={displayConfig?.from_date || ""}
                                                                    onChange={(dateStr) => {
                                                                        if (isIntegrated) return;
                                                                        handleConfigChange('from_date', dateStr);
                                                                    }}
                                                                    disabled={isIntegrated}
                                                                    minDate={(() => {
                                                                        const d = new Date();
                                                                        d.setDate(d.getDate() - getMaxDays(activeExchangeName));
                                                                        return d;
                                                                    })()}
                                                                />
                                                            </div>
                                                            <div className="text-left">
                                                                <label className="text-xs text-gray-400 mb-1 block">
                                                                    End Date {isIntegrated && <span className="text-blue-400">(Inherited from Rank 1)</span>}
                                                                </label>
                                                                <DateDropdown
                                                                    value={displayConfig?.to_date || new Date(Date.now() - 86400000).toISOString().split('T')[0]}
                                                                    onChange={(dateStr) => {
                                                                        if (isIntegrated) return;
                                                                        handleConfigChange('to_date', dateStr);
                                                                    }}
                                                                    disabled={isIntegrated}
                                                                />
                                                            </div>
                                                            {isIntegrated && (
                                                                <div className="text-left">
                                                                    <label className="text-xs text-gray-400 mb-1 block">
                                                                        Execution Mode
                                                                    </label>
                                                                    <select
                                                                        value={profileMeta.execution_mode}
                                                                        onChange={(e) => setProfileMeta(prev => ({ ...prev, execution_mode: e.target.value }))}
                                                                        className="bg-black/40 border border-white/20 rounded px-3 py-2 text-white w-44 text-center appearance-none cursor-pointer focus:border-blue-500"
                                                                    >
                                                                        <option value="exclusive">Exclusive (Waterfall)</option>
                                                                        <option value="parallel">Parallel (Equal Split)</option>
                                                                    </select>
                                                                    <p className="text-[10px] text-gray-500 mt-1">
                                                                        {profileMeta.execution_mode === 'exclusive'
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
                                                            setIsDirty(true); // Mark as dirty when running integrated backtest

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
                                                                const rank1Capital = leaderConfig?.initial_capital || DEFAULT_INITIAL_CAPITAL;
                                                                const totalCapital = profileMeta.execution_mode === 'parallel'
                                                                    ? rank1Capital * activeConfigs.length  // Parallel: Rank1 capital × number of active ranks
                                                                    : rank1Capital;                         // Exclusive: Just Rank1 capital

                                                                const defaultToDate = new Date(Date.now() - 86400000).toISOString().split('T')[0];
                                                                const integratedData = await runIntegratedBacktestApi({
                                                                    configs: validConfigs,
                                                                    symbol: currentSymbol || "KRW-BTC", // Use global or default
                                                                    interval: leaderConfig?.interval || "1m", // Use selected interval
                                                                    days: diffDays > 0 ? diffDays : 365,
                                                                    from_date: leaderConfig?.from_date || "",
                                                                    to_date: leaderConfig?.to_date || defaultToDate,
                                                                    initial_capital: totalCapital,
                                                                    execution_mode: profileMeta.execution_mode, // 'exclusive' or 'parallel'
                                                                    exchange_name: activeExchangeName // 프로필 계좌 기반 거래소 자동 결정
                                                                });

                                                                // Update Result State and Store for Visualization
                                                                setBacktestResult(integratedData);
                                                                setIntegratedResults(integratedData); // Store full result for visualization
                                                                setBacktestStatus({ status: 'completed', message: 'Simulation Complete' });

                                                                // Save Result for Persistence (profile-specific UUID)
                                                                const integratedUUID = getIntegratedUUID(selectedProfileId);
                                                                console.log('[Integrated] Saving result with UUID:', integratedUUID, 'profileId:', selectedProfileId);
                                                                saveStrategyResult(integratedUUID, 'backtest', integratedData)
                                                                    .then(() => console.log('[Integrated] Result saved successfully'))
                                                                    .catch(err => console.error("Failed to save Integrated Result", err));

                                                                // Auto-save profile to persist dates alongside results
                                                                if (selectedProfileId) {
                                                                    saveProfile().then(() => {
                                                                        setIsDirty(false);
                                                                        setIsSymbolCompareDirty(false);
                                                                    }).catch(err => console.warn("Auto-save profile after integrated backtest failed:", err));
                                                                }

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
                                                    {/* Save Profile 버튼 제거 — 헤더 Save로 통합 */}
                                                </div>
                                                <p className="text-xs text-gray-500 mt-3">
                                                    {profileMeta.execution_mode === 'exclusive'
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
                                            {/* Reset to Rank 1 + Mode label - Only for Symbol Compare */}
                                            {activeTab === -3 && (
                                                <div className="flex items-center gap-2">
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
                                                {/* SymbolSelector - exchange-aware (Korean stock vs Crypto) */}
                                                {isCryptoExchange ? (
                                                    <CryptoSymbolSelector
                                                        currentSymbol={activeTab === -3 ? '' : (currentConfig?.symbol || currentSymbol)}
                                                        setCurrentSymbol={isProfileLocked ? () => {} : (activeTab === -3 ? () => {} : (newSymbol) => handleConfigChange('symbol', newSymbol))}
                                                        savedSymbols={savedSymbols}
                                                        setSavedSymbols={setSavedSymbols}
                                                        hideSymbolList={activeTab === -3}
                                                        exchangeName={activeExchangeName}
                                                    />
                                                ) : (
                                                    <SymbolSelector
                                                        currentSymbol={activeTab === -3 ? '' : (currentConfig?.symbol || currentSymbol)}
                                                        setCurrentSymbol={isProfileLocked ? () => {} : (activeTab === -3 ? () => {} : (newSymbol) => handleConfigChange('symbol', newSymbol))}
                                                        savedSymbols={savedSymbols}
                                                        setSavedSymbols={setSavedSymbols}
                                                        hideSymbolList={activeTab === -3}
                                                    />
                                                )}

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
                                                        presets={currentConfig?.parameter_presets || []}
                                                        selectedPresetId={currentConfig?.selected_preset_id}
                                                        currentParams={currentConfig}
                                                        disabled={isProfileLocked}
                                                        parameterSchema={selectedStrategy?.parameter_schema}
                                                        onSelectPreset={(presetId) => {
                                                            if (activeTab === -3) {
                                                                // Symbol Compare tab: update symbolCompareConfig directly
                                                                const preset = (currentConfig?.parameter_presets || []).find(p => p.id === presetId);
                                                                if (!preset) return;
                                                                const paramKeys = selectedStrategy?.parameter_schema?.fields?.map(f => f.key || f.name) || [];
                                                                const updated = { ...currentConfig };
                                                                paramKeys.forEach(key => { if (preset.params[key] !== undefined) updated[key] = preset.params[key]; });
                                                                updated.selected_preset_id = presetId;
                                                                setSymbolCompareConfig(updated);
                                                                setIsDirty(true);
                                                            } else {
                                                                selectPreset(activeTab, presetId, selectedStrategy?.parameter_schema);
                                                            }
                                                        }}
                                                        onAddPreset={(desc) => {
                                                            if (activeTab === -3) {
                                                                // Symbol Compare tab: add preset to symbolCompareConfig
                                                                const schema = selectedStrategy?.parameter_schema;
                                                                const paramKeys = schema?.fields?.map(f => f.key || f.name) || [];
                                                                const params = {};
                                                                paramKeys.forEach(key => { if (currentConfig[key] !== undefined) params[key] = currentConfig[key]; });
                                                                const presets = [...(currentConfig?.parameter_presets || [])];
                                                                const usedNums = new Set(presets.map(p => { const m = p.name?.match(/^(\d{3})_/); return m ? parseInt(m[1]) : 0; }));
                                                                let nextNum = 1;
                                                                while (usedNums.has(nextNum)) nextNum++;
                                                                const cleanDesc = (desc || 'unnamed').replace(/[^\w\s가-힣-]/g, '').trim().slice(0, 30) || 'unnamed';
                                                                const newPreset = {
                                                                    id: `preset-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
                                                                    name: `${String(nextNum).padStart(3, '0')}_${cleanDesc}`,
                                                                    params,
                                                                    config_hash: createConfigHash(params),
                                                                    created_at: new Date().toISOString()
                                                                };
                                                                if (presets.length >= 20) presets.shift();
                                                                presets.push(newPreset);
                                                                setSymbolCompareConfig({ ...currentConfig, parameter_presets: presets, selected_preset_id: newPreset.id });
                                                                setIsDirty(true);
                                                            } else {
                                                                addPreset(activeTab, desc, selectedStrategy?.parameter_schema);
                                                            }
                                                        }}
                                                        onDeletePreset={(presetId) => {
                                                            if (activeTab === -3) {
                                                                const presets = (currentConfig?.parameter_presets || []).filter(p => p.id !== presetId);
                                                                const updated = { ...currentConfig, parameter_presets: presets };
                                                                if (currentConfig?.selected_preset_id === presetId) updated.selected_preset_id = null;
                                                                setSymbolCompareConfig(updated);
                                                                setIsDirty(true);
                                                            } else {
                                                                deletePreset(activeTab, presetId);
                                                            }
                                                        }}
                                                        onRenamePreset={(presetId, newName) => {
                                                            if (activeTab === -3) {
                                                                const presets = (currentConfig?.parameter_presets || []).map(p =>
                                                                    p.id === presetId ? { ...p, name: newName } : p
                                                                );
                                                                setSymbolCompareConfig({ ...currentConfig, parameter_presets: presets });
                                                                setIsDirty(true);
                                                            } else {
                                                                renamePreset(activeTab, presetId, newName);
                                                            }
                                                        }}
                                                        onRevertParams={(params) => {
                                                            const parameterFields = selectedStrategy?.parameter_schema?.fields?.map(f => f.key || f.name) || [];
                                                            const filteredParams = {};
                                                            parameterFields.forEach(key => {
                                                                if (params[key] !== undefined) filteredParams[key] = params[key];
                                                            });
                                                            handleConfigChange({...currentConfig, ...filteredParams});
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
                                                        disabled={isProfileLocked}
                                                    />
                                                ) : (
                                                    <div className="text-gray-500 text-sm text-center py-4">No configurable parameters for this strategy</div>
                                                )}

                                            </div>
                                        </div>
                                    </div>
                                </div>
                            )}

                            {/* Content Area based on Tab */}
                            {/* Live tab content moved to /live page (LiveTradingView.jsx) */}

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
                                                        value={(currentConfig?.initial_capital || DEFAULT_INITIAL_CAPITAL).toLocaleString()}
                                                        onChange={(e) => {
                                                            const val = parseInt(e.target.value.replace(/,/g, ''), 10);
                                                            if (!isNaN(val)) handleConfigChange('initial_capital', val);
                                                        }}
                                                        className="w-full bg-black/40 border border-white/10 rounded px-3 py-2 text-sm text-white focus:border-blue-500 outline-none"
                                                    />
                                                </div>

                                                <div className="relative">
                                                    <label className="text-[10px] text-gray-500 absolute -top-1.5 left-2 bg-[#1e2029] px-1">
                                                        Start Date (Max {getMaxDaysLabel(activeExchangeName)})
                                                    </label>
                                                    <DateDropdown
                                                        value={currentConfig?.from_date || ""}
                                                        onChange={(dateStr) => handleConfigChange('from_date', dateStr)}
                                                        minDate={(() => {
                                                            const d = new Date();
                                                            d.setDate(d.getDate() - getMaxDays(activeExchangeName));
                                                            return d;
                                                        })()}
                                                    />
                                                </div>

                                                <div className="relative">
                                                    <label className="text-[10px] text-gray-500 absolute -top-1.5 left-2 bg-[#1e2029] px-1">
                                                        End Date
                                                    </label>
                                                    <DateDropdown
                                                        value={currentConfig?.to_date || new Date(Date.now() - 86400000).toISOString().split('T')[0]}
                                                        onChange={(dateStr) => handleConfigChange('to_date', dateStr)}
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
                                                    {!isDataUpdated && (
                                                        <span className="text-amber-400/80 text-[10px] whitespace-nowrap animate-pulse">
                                                            Update first to run backtest/optimization
                                                        </span>
                                                    )}
                                                </div>
                                            </div>
                                        </div>

                                        {/* Row 2: Capital & Date & Strategy */}
                                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 border-t border-white/5 pt-4">
                                            <div className="relative">
                                                <label className="text-[10px] text-gray-500 absolute -top-1.5 left-2 bg-[#1e2029] px-1">Initial Capital</label>
                                                <input
                                                    type="text"
                                                    value={(currentConfig?.initial_capital || DEFAULT_INITIAL_CAPITAL).toLocaleString()}
                                                    onChange={(e) => {
                                                        const val = parseInt(e.target.value.replace(/,/g, ''), 10);
                                                        if (!isNaN(val)) handleConfigChange('initial_capital', val);
                                                    }}
                                                    className="w-full bg-black/40 border border-white/10 rounded px-3 py-2 text-sm text-white focus:border-blue-500 outline-none"
                                                />
                                            </div>

                                            <div className="relative">
                                                <label className="text-[10px] text-gray-500 absolute -top-1.5 left-2 bg-[#1e2029] px-1">
                                                    Start Date {dataStatus?.start_date ? `(${dataStatus.start_date}~)` : `(Max ${getMaxDaysLabel(activeExchangeName)})`}
                                                </label>
                                                <DateDropdown
                                                    value={currentConfig?.from_date || ""}
                                                    onChange={(dateStr) => handleConfigChange('from_date', dateStr)}
                                                    minDate={(() => {
                                                        const d = new Date();
                                                        d.setDate(d.getDate() - getMaxDays(activeExchangeName));
                                                        return d;
                                                    })()}
                                                />
                                            </div>

                                            <div className="relative">
                                                <label className="text-[10px] text-gray-500 absolute -top-1.5 left-2 bg-[#1e2029] px-1">
                                                    End Date
                                                </label>
                                                <DateDropdown
                                                    value={currentConfig?.to_date || new Date(Date.now() - 86400000).toISOString().split('T')[0]}
                                                    onChange={(dateStr) => handleConfigChange('to_date', dateStr)}
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
                                                disabled={isLoading || !selectedStrategy || !dataStatus.count || activeTab === -1 || !isDataUpdated}
                                                title={!isDataUpdated ? 'Update 버튼을 먼저 클릭하여 데이터를 최신화하세요' : ''}
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
                            (activeTab >= 0 || activeTab === -3) && (
                                <div className="bg-white/5 border border-white/10 rounded-xl overflow-hidden">
                                    <div className="bg-white/5 px-4 py-3 border-b border-white/10 flex items-center justify-between">
                                        <h3 className="font-bold text-gray-200 text-sm flex items-center gap-2">
                                            <Sparkles size={14} className="text-gray-400" /> Parameter Optimization
                                        </h3>
                                        <CopyPasteButtons
                                            onCopy={handleCopyOptSettings}
                                            onPaste={handlePasteOptSettings}
                                            feedback={optCopyPasteFeedback}
                                            hasCopied={!!copiedOptSettings}
                                            sourceLabel={copiedOptSettings?.sourceTab}
                                        />
                                    </div>
                                    <div className="px-4 py-4">
                                        <div className="space-y-6">
                                            <div className="space-y-6">
                                                {/* Dynamic Grid Inputs */}
                                                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                                                    {(() => {
                                                        const currentOptEnabled = currentConfig.optEnabled || {};
                                                        const defaults = getDynamicOptValues();
                                                        const savedOptValues = currentConfig.optValues || {};
                                                        // Merge: saved values take priority, fallback to dynamic defaults per key
                                                        const currentOptValues = { ...defaults, ...savedOptValues };

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





                                                {/* Execution Mode Toggle */}
                                                {(activeTab >= 0 || activeTab === -3) && (
                                                    <div className="flex items-center gap-2 mb-1">
                                                        <div className="flex rounded-lg overflow-hidden border border-white/10">
                                                            <button
                                                                onClick={() => setExecutionMode("standard")}
                                                                disabled={isHeavyOptRunning}
                                                                className={`px-3 py-1 text-xs font-medium transition-all ${executionMode === "standard" ? 'bg-purple-700 text-white' : 'bg-black/30 text-gray-400 hover:text-gray-200'} disabled:opacity-50`}
                                                            >
                                                                Standard
                                                            </button>
                                                            <button
                                                                onClick={() => setExecutionMode("fast")}
                                                                disabled={isHeavyOptRunning}
                                                                className={`px-3 py-1 text-xs font-medium transition-all ${executionMode === "fast" ? 'bg-orange-600 text-white' : 'bg-black/30 text-gray-400 hover:text-gray-200'} disabled:opacity-50`}
                                                            >
                                                                Fast
                                                            </button>
                                                        </div>
                                                        <span className="text-[10px] text-gray-500">
                                                            {executionMode === "fast" ? "Parallel (multi-core)" : "Sequential (stable)"}
                                                        </span>
                                                    </div>
                                                )}

                                                {/* Action */}
                                                <div className="flex gap-2">
                                                    {/* Rank Tabs and Symbol Compare Tab: Use unified startHeavyOptimization */}
                                                    {(activeTab >= 0 || activeTab === -3) && (
                                                        <button
                                                            onClick={startHeavyOptimization}
                                                            disabled={isHeavyOptRunning || !isDataUpdated || (activeTab === -3 && selectedCompareSymbols.length === 0)}
                                                            title={!isDataUpdated ? 'Update 버튼을 먼저 클릭하여 데이터를 최신화하세요' : ''}
                                                            className={`flex-1 bg-gradient-to-r from-purple-900 to-blue-900 hover:from-purple-800 hover:to-blue-800 py-3 rounded-lg font-bold text-white shadow-lg shadow-purple-900/40 transition-all flex justify-center items-center gap-2 ${isHeavyOptRunning ? 'cursor-not-allowed opacity-80' : ''} disabled:opacity-50 disabled:cursor-not-allowed`}
                                                        >
                                                            {isHeavyOptRunning ? (
                                                                <>
                                                                    <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                                                                    {heavyOptStatus?.message || "Initializing..."}
                                                                </>
                                                            ) : activeTab === -3 ? (
                                                                `Run Optimization (${selectedCompareSymbols.length} Symbols × ${Object.values((symbolCompareConfig?.optEnabled || {})).filter(Boolean).length} Params)`
                                                            ) : (
                                                                `Run Optimization (${Object.values((currentConfig.optEnabled || {})).filter(Boolean).length} Params)`
                                                            )}
                                                        </button>
                                                    )}

                                                    {/* Integrated Tab: Disabled */}
                                                    {activeTab === -1 && (
                                                        <button
                                                            disabled
                                                            className="flex-1 bg-gray-700 py-3 rounded-lg font-bold text-gray-400 cursor-not-allowed opacity-60"
                                                        >
                                                            Optimization Unavailable (Integrated)
                                                        </button>
                                                    )}
                                                </div>

                                                {/* Optimization Status Panel (Symbol Compare Tab) */}
                                                {(activeTab >= 0 || activeTab === -3) && heavyOptStatus && (
                                                    <div className="mt-4 p-4 bg-gradient-to-br from-purple-900/20 to-blue-900/20 rounded-xl border border-purple-500/30">
                                                        <div className="flex items-center justify-between mb-3">
                                                            <div className="flex items-center gap-2">
                                                                <span className="text-lg">⚡</span>
                                                                <span className="font-bold text-purple-300">Optimization Progress</span>
                                                                <span className={`text-xs px-2 py-0.5 rounded-full ${
                                                                    heavyOptStatus.status === 'running' ? 'bg-green-500/20 text-green-400 animate-pulse' :
                                                                    heavyOptStatus.status === 'completed' ? 'bg-blue-500/20 text-blue-400' :
                                                                    heavyOptStatus.status === 'cancelled' ? 'bg-yellow-500/20 text-yellow-400' :
                                                                    heavyOptStatus.status === 'failed' ? 'bg-red-500/20 text-red-400' :
                                                                    'bg-gray-500/20 text-gray-400'
                                                                }`}>
                                                                    {heavyOptStatus.status?.toUpperCase()}
                                                                </span>
                                                            </div>
                                                            {heavyOptStatus.status === 'running' && (
                                                                <button
                                                                    onClick={handleCancelHeavyOpt}
                                                                    className="px-3 py-1 text-xs bg-red-600 hover:bg-red-500 text-white rounded font-bold"
                                                                >
                                                                    Cancel
                                                                </button>
                                                            )}
                                                            {(heavyOptStatus.status === 'completed' || heavyOptStatus.status === 'cancelled' || heavyOptStatus.status === 'failed') && (
                                                                <button
                                                                    onClick={clearHeavyOptTask}
                                                                    className="px-3 py-1 text-xs bg-gray-600 hover:bg-gray-500 text-white rounded font-bold"
                                                                >
                                                                    Clear
                                                                </button>
                                                            )}
                                                        </div>

                                                        {/* Progress Bar */}
                                                        {(heavyOptStatus.status === 'running' || heavyOptStatus.status === 'initializing') && (
                                                            <div className="mb-3">
                                                                <div className="flex justify-between text-xs text-gray-400 mb-1">
                                                                    <span>{heavyOptStatus.progress_current?.toLocaleString()} / {heavyOptStatus.progress_total?.toLocaleString()}</span>
                                                                    <span>{heavyOptStatus.progress_percent?.toFixed(1)}%</span>
                                                                </div>
                                                                <div className="h-2 bg-black/40 rounded-full overflow-hidden">
                                                                    <div
                                                                        className="h-full bg-gradient-to-r from-purple-500 to-pink-500 transition-all duration-500"
                                                                        style={{ width: `${heavyOptStatus.progress_percent || 0}%` }}
                                                                    />
                                                                </div>
                                                                <div className="flex justify-between text-xs text-gray-500 mt-1">
                                                                    <span>Elapsed: {heavyOptStatus.elapsed_seconds ? `${Math.floor(heavyOptStatus.elapsed_seconds / 60)}m ${Math.floor(heavyOptStatus.elapsed_seconds % 60)}s` : '-'}</span>
                                                                    <span>Remaining: {heavyOptStatus.estimated_remaining_seconds ? `~${Math.floor(heavyOptStatus.estimated_remaining_seconds / 60)}m` : '-'}</span>
                                                                </div>
                                                            </div>
                                                        )}

                                                        {/* Completed: Download & AI Analyze */}
                                                        {heavyOptStatus.status === 'completed' && (
                                                            <div className="space-y-3">
                                                                <div className="flex items-center gap-3">
                                                                    <button
                                                                        onClick={downloadHeavyOptCSV}
                                                                        className="px-4 py-2 bg-gradient-to-r from-green-600 to-emerald-600 hover:from-green-500 hover:to-emerald-500 text-white rounded-lg font-bold flex items-center gap-2"
                                                                    >
                                                                        <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                                                                        </svg>
                                                                        Download CSV
                                                                    </button>
                                                                    <span className="text-xs text-gray-400">
                                                                        {heavyOptStatus.file_size_bytes ? `${(heavyOptStatus.file_size_bytes / 1024 / 1024).toFixed(2)} MB` : ''}
                                                                    </span>
                                                                </div>

                                                            </div>
                                                        )}

                                                        {/* Message */}
                                                        {heavyOptStatus.message && (
                                                            <div className="text-xs text-gray-400 font-mono mt-2">
                                                                {heavyOptStatus.message}
                                                            </div>
                                                        )}
                                                    </div>
                                                )}

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

                                                {/* Score Weight / Download panel - visible even after refresh if lastOptTaskId exists */}
                                                {!isOptimizing && !optResults?.length && (completedOptTaskId || heavyOptTaskId || currentConfig?.lastOptTaskId) && (
                                                    <div className="bg-black/40 rounded-lg overflow-hidden border border-white/10 mt-4">
                                                        <div className="p-4 flex items-center justify-between">
                                                            <span className="text-sm text-gray-400">Previous optimization results available on server</span>
                                                            <div className="flex items-center gap-2">
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
                                                                <button
                                                                    onClick={() => setShowWeightPanel(!showWeightPanel)}
                                                                    className={`px-4 py-2 ${showWeightPanel ? 'bg-orange-600 hover:bg-orange-700' : 'bg-gray-600 hover:bg-gray-700'} text-white text-sm font-medium rounded-lg transition-colors flex items-center gap-2`}
                                                                    title="Adjust score weights and recalculate top 50 from full results"
                                                                >
                                                                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" />
                                                                    </svg>
                                                                    {showWeightPanel ? 'Hide Weights' : 'Score Weights'}
                                                                </button>
                                                            </div>
                                                        </div>
                                                    </div>
                                                )}

                                                {/* Score Weight Adjustment Panel (shared - works with or without results) */}
                                                {showWeightPanel && (completedOptTaskId || heavyOptTaskId || currentConfig?.lastOptTaskId) && !isOptimizing && (
                                                    <div className="bg-black/40 rounded-lg overflow-hidden border border-white/10 mt-4 p-4 bg-gradient-to-r from-orange-900/20 to-yellow-900/20">
                                                        <div className="flex items-center justify-between mb-3">
                                                            <span className="text-sm font-medium text-white">Score Weight Settings</span>
                                                            <div className="flex items-center gap-2">
                                                                <span className="text-xs text-gray-400">Presets:</span>
                                                                {(() => {
                                                                    const isBalanced = JSON.stringify(scoreWeights) === JSON.stringify(SCORE_WEIGHT_PRESETS.balanced);
                                                                    const isReturn = JSON.stringify(scoreWeights) === JSON.stringify(SCORE_WEIGHT_PRESETS.return_focused);
                                                                    const isStability = JSON.stringify(scoreWeights) === JSON.stringify(SCORE_WEIGHT_PRESETS.stability_focused);
                                                                    const isCustom = !isBalanced && !isReturn && !isStability;
                                                                    return (
                                                                        <>
                                                                            <button
                                                                                onClick={() => applyWeightPreset('balanced')}
                                                                                className={`px-2 py-1 text-xs rounded ${isBalanced ? 'bg-blue-600 text-white ring-1 ring-blue-400' : 'bg-gray-700 text-gray-300 hover:bg-gray-600'}`}
                                                                            >
                                                                                {isBalanced && '✓ '}균형
                                                                            </button>
                                                                            <button
                                                                                onClick={() => applyWeightPreset('return_focused')}
                                                                                className={`px-2 py-1 text-xs rounded ${isReturn ? 'bg-green-600 text-white ring-1 ring-green-400' : 'bg-gray-700 text-gray-300 hover:bg-gray-600'}`}
                                                                            >
                                                                                {isReturn && '✓ '}수익 중심
                                                                            </button>
                                                                            <button
                                                                                onClick={() => applyWeightPreset('stability_focused')}
                                                                                className={`px-2 py-1 text-xs rounded ${isStability ? 'bg-purple-600 text-white ring-1 ring-purple-400' : 'bg-gray-700 text-gray-300 hover:bg-gray-600'}`}
                                                                            >
                                                                                {isStability && '✓ '}안정 중심
                                                                            </button>
                                                                            {isCustom && (
                                                                                <span className="px-2 py-1 text-xs rounded bg-yellow-600/30 text-yellow-300 border border-yellow-500/40">
                                                                                    커스텀
                                                                                </span>
                                                                            )}
                                                                        </>
                                                                    );
                                                                })()}
                                                            </div>
                                                        </div>
                                                        <div className="mb-2">
                                                            <span className="text-xs text-gray-500 mb-1 block">주요 지표</span>
                                                            <div className="grid grid-cols-3 md:grid-cols-5 gap-3">
                                                                {[
                                                                    { key: 'return_weight', label: 'Return', color: 'green' },
                                                                    { key: 'sharpe_weight', label: 'Sharpe', color: 'blue' },
                                                                    { key: 'stability_weight', label: 'Stability', color: 'purple' },
                                                                    { key: 'mdd_weight', label: 'MDD (패널티)', color: 'red' },
                                                                    { key: 'avg_pnl_weight', label: 'AvgPnL', color: 'indigo' }
                                                                ].map(({ key, label, color }) => (
                                                                    <div key={key} className="flex flex-col items-center bg-black/20 rounded p-2">
                                                                        <label className={`text-xs text-${color}-400 mb-1`}>{label}</label>
                                                                        <input
                                                                            type="range"
                                                                            min="0"
                                                                            max="3"
                                                                            step="0.1"
                                                                            value={scoreWeights[key]}
                                                                            onChange={(e) => handleWeightChange(key, e.target.value)}
                                                                            className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer"
                                                                        />
                                                                        <span className="text-xs text-gray-300 mt-1">{scoreWeights[key].toFixed(1)}</span>
                                                                    </div>
                                                                ))}
                                                            </div>
                                                        </div>
                                                        <div className="mb-3">
                                                            <span className="text-xs text-gray-500 mb-1 block">선택 지표 (기본값 0 = 미적용)</span>
                                                            <div className="grid grid-cols-3 md:grid-cols-5 gap-2">
                                                                {[
                                                                    { key: 'win_rate_weight', label: 'WinRate', color: 'cyan' },
                                                                    { key: 'recent_10_weight', label: 'Recent10', color: 'lime' },
                                                                    { key: 'profit_factor_weight', label: 'ProfitFactor', color: 'emerald' },
                                                                    { key: 'accel_weight', label: 'Accel', color: 'yellow' },
                                                                    { key: 'trades_weight', label: 'Cycles', color: 'orange' },
                                                                    { key: 'activity_weight', label: 'Activity', color: 'pink' }
                                                                ].map(({ key, label, color }) => (
                                                                    <div key={key} className="flex flex-col items-center opacity-80 bg-black/10 rounded p-1">
                                                                        <label className={`text-xs text-${color}-400 mb-1`}>{label}</label>
                                                                        <input
                                                                            type="range"
                                                                            min="0"
                                                                            max="3"
                                                                            step="0.1"
                                                                            value={scoreWeights[key]}
                                                                            onChange={(e) => handleWeightChange(key, e.target.value)}
                                                                            className="w-full h-1.5 bg-gray-700 rounded-lg appearance-none cursor-pointer"
                                                                        />
                                                                        <span className="text-xs text-gray-400 mt-0.5">{scoreWeights[key].toFixed(1)}</span>
                                                                    </div>
                                                                ))}
                                                            </div>
                                                        </div>
                                                        <div className="flex items-center justify-between">
                                                            <p className="text-xs text-gray-400">
                                                                Formula: (Return<sup>w</sup> × Sharpe<sup>w</sup> × Stability<sup>w</sup>) / MDD<sup>w</sup> | Weight 0 = Exclude
                                                            </p>
                                                            <button
                                                                onClick={recalculateScores}
                                                                disabled={isRecalculating}
                                                                className="px-4 py-2 bg-orange-600 hover:bg-orange-700 disabled:bg-gray-600 text-white text-sm font-medium rounded-lg transition-colors flex items-center gap-2"
                                                            >
                                                                {isRecalculating ? (
                                                                    <>
                                                                        <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
                                                                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                                                                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
                                                                        </svg>
                                                                        Recalculating...
                                                                    </>
                                                                ) : (
                                                                    <>
                                                                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                                                                        </svg>
                                                                        Recalculate Top 50
                                                                    </>
                                                                )}
                                                            </button>
                                                        </div>
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
                                                                        Unsaved
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
                                                                {(completedOptTaskId || currentConfig?.lastOptTaskId) && (
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
                                                                {/* Score Weight Recalculation Toggle */}
                                                                {(completedOptTaskId || heavyOptTaskId || currentConfig?.lastOptTaskId) && !isOptimizing && (
                                                                    <button
                                                                        onClick={() => setShowWeightPanel(!showWeightPanel)}
                                                                        className={`px-4 py-2 ${showWeightPanel ? 'bg-orange-600 hover:bg-orange-700' : 'bg-gray-600 hover:bg-gray-700'} text-white text-sm font-medium rounded-lg transition-colors flex items-center gap-2`}
                                                                        title="Adjust score weights and recalculate top 50 from full results"
                                                                    >
                                                                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" />
                                                                        </svg>
                                                                        {showWeightPanel ? 'Hide Weights' : 'Score Weights'}
                                                                    </button>
                                                                )}
                                                            </div>
                                                        </div>

                                                        <DualScrollContainer>
                                                            <table className="w-full text-left border-collapse whitespace-nowrap">
                                                                <thead>
                                                                    {(() => {
                                                                        const optCols = getOptVisibleColumns(optResults);
                                                                        const hasSymbolCol = optResults.some(r => r.symbol);
                                                                        const extraCols = [
                                                                            { key: 'rank', label: 'Rank' },
                                                                            ...(hasSymbolCol ? [{ key: 'symbol', label: 'Symbol' }, { key: 'symbolName', label: 'Name' }] : []),
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
                                                                                                const symbolInfo = res.symbol ? `Symbol: ${res.symbol} (${res.symbolName || ''})\n` : '';
                                                                                                openConfirm(
                                                                                                    "Apply Optimization Config?",
                                                                                                    `${symbolInfo}Rank: #${res.rank}\nReturn: ${res.return}%\nScore: ${res.score}\n\nThis will overwrite your current configuration. Continue?`,
                                                                                                    async () => {
                                                                                                        // Extract ONLY strategy parameters (current config's initial_capital/days/from_date always takes priority)
                                                                                                        const paramNames = getStrategyParamNames();
                                                                                                        const source = res.full_config || res;
                                                                                                        const configToApply = {};
                                                                                                        paramNames.forEach(key => {
                                                                                                            if (source[key] !== undefined) {
                                                                                                                configToApply[key] = source[key];
                                                                                                            }
                                                                                                        });

                                                                                                        // Coerce string values to proper types (CSV round-trip turns numbers into strings)
                                                                                                        const typedConfig = coerceConfigTypes(configToApply, selectedStrategy?.parameter_schema);

                                                                                                        if (Object.keys(typedConfig).length === 0) {
                                                                                                            addLog(`⚠️ No strategy parameters found in optimization result #${res.rank}`, 'warning');
                                                                                                            return;
                                                                                                        }

                                                                                                        if (activeTab === -3) {
                                                                                                            // Symbol tab: apply to symbolCompareConfig
                                                                                                            setSymbolCompareConfig(prev => ({
                                                                                                                ...(prev || {}),
                                                                                                                ...typedConfig
                                                                                                            }));
                                                                                                            addLog(`Applied config from ${res.symbol || 'optimization'} #${res.rank}`, 'success');
                                                                                                        } else {
                                                                                                            // Rank tab: merge ONLY strategy params into current config (preserves metadata)
                                                                                                            const merged = { ...currentConfig, ...typedConfig };

                                                                                                            // Update state
                                                                                                            setConfigList(prev => {
                                                                                                                const next = [...prev];
                                                                                                                next[activeTab] = merged;
                                                                                                                return next;
                                                                                                            });
                                                                                                            setIsDirty(true);

                                                                                                            addLog(`Applied optimization #${res.rank} params: ${Object.entries(typedConfig).map(([k, v]) => `${k}=${v}`).join(', ')}`, 'success');

                                                                                                            // Run backtest with merged config
                                                                                                            runBacktest(selectedStrategy.id, merged);
                                                                                                        }
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
                                                                                    {/* Symbol column for cross-optimization */}
                                                                                    {optResults.some(r => r.symbol) && (
                                                                                        <td className="p-3 text-white font-mono font-bold">{res.symbol || '-'}</td>
                                                                                    )}
                                                                                    {optResults.some(r => r.symbol) && (
                                                                                        <td className="p-3 text-gray-300 text-xs">{res.symbolName || '-'}</td>
                                                                                    )}

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

            {/* Optimization Alert Modal */}
            <AlertModal
                isOpen={optAlertModal.isOpen}
                onClose={() => setOptAlertModal(prev => ({ ...prev, isOpen: false }))}
                title={optAlertModal.title}
                message={optAlertModal.message}
                type={optAlertModal.type}
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
