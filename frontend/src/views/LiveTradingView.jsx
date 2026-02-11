import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import { useMarketData } from '../context/MarketDataContext';
import { useWatchlist } from '../context/WatchlistContext';
import { useStrategyConfig } from '../hooks/useStrategyConfig';
import { getAccountPreferences, updateLastSelectedStrategy, updateExecutionMode } from '../api/client';
import LiveStrategyPanel from '../components/LiveStrategyPanel';
import SessionSwitcher from '../components/SessionSwitcher';
import NewSessionModal from '../components/NewSessionModal';
import ConfirmModal from '../components/ConfirmModal';
import { Radio } from 'lucide-react';

const generateUUID = () => {
    if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID();
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
        var r = Math.random() * 16 | 0, v = c == 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
};

const LiveTradingView = () => {
    // 계좌 중심: 활성 계좌 ID 가져오기
    const { systemStatus } = useMarketData();
    const activeAccountId = systemStatus?.account_id || null;

    // Symbol State - Use shared watchlist context (synced with DB)
    const { currentSymbol, setCurrentSymbol, savedSymbols } = useWatchlist();

    // Strategy State
    const [strategies, setStrategies] = useState([]);
    const [selectedStrategy, setSelectedStrategy] = useState(null);

    // Live-specific State
    const [liveRankIndex, setLiveRankIndex] = useState(() => {
        const saved = localStorage.getItem('live_currentRankIndex');
        return saved ? parseInt(saved, 10) : 0;
    });
    const [isLiveRunning, setIsLiveRunning] = useState(false);
    const [isNewSessionModalOpen, setIsNewSessionModalOpen] = useState(false);
    const [activeSessionGroup, setActiveSessionGroup] = useState(null);
    const [executionMode, setExecutionMode] = useState(() => {
        const saved = localStorage.getItem('integratedExecutionMode');
        return saved || 'exclusive';
    });

    // Config Management (uses useStrategyConfig hook)
    const {
        configList,
        setConfigList,
        isLoaded: isConfigLoaded,
        saveConfigs,
        scope,
        getDynamicDefaultConfig: getHookDefaultConfig
    } = useStrategyConfig({
        selectedStrategy,
        accountId: activeAccountId,
        defaultConfig: {},
        generateUUID
    });

    // Refs
    const capitalSaveTimeoutRef = useRef(null);
    const sessionSwitcherRef = useRef(null);

    // Confirm Modal State
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

    // Save execution mode to DB (with localStorage fallback)
    useEffect(() => {
        localStorage.setItem('integratedExecutionMode', executionMode);
        updateExecutionMode(executionMode).catch(e => {
            console.warn('Failed to save execution mode to DB:', e);
        });
    }, [executionMode]);

    // Save liveRankIndex to localStorage for persistence across refresh
    useEffect(() => {
        localStorage.setItem('live_currentRankIndex', liveRankIndex.toString());
    }, [liveRankIndex]);

    // Validate liveRankIndex when configList changes (prevent out-of-bounds)
    useEffect(() => {
        if (configList.length > 0 && liveRankIndex >= configList.length) {
            setLiveRankIndex(0);
        }
    }, [configList.length, liveRankIndex]);

    // Fetch strategies on mount
    useEffect(() => {
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

    // Strategy Change Handler (simplified for Live page - no dirty check needed)
    const handleStrategyChange = (newStrategy) => {
        setSelectedStrategy(newStrategy);
    };

    return (
        <div className="flex flex-col gap-6 pb-10">
            {/* Strategy selector removed - strategy is determined by session group */}

            {/* Main Content Area */}
            <div className="space-y-6 pb-20">
                {!isConfigLoaded ? (
                    <div className="flex flex-col items-center justify-center p-20 text-gray-500">
                        <div className="w-10 h-10 border-4 border-blue-500/30 border-t-blue-500 rounded-full animate-spin mb-4"></div>
                        <p>Loading Strategy Configuration...</p>
                        <p className="text-xs text-gray-600 mt-2">Synchronizing with Database...</p>
                    </div>
                ) : configList.length > 0 ? (
                    <div className="animate-fade-in-up">
                        {/* Session Switcher for Multi-Account Support */}
                        <SessionSwitcher
                            ref={sessionSwitcherRef}
                            onSelectSessionGroup={(group) => {
                                setActiveSessionGroup(group);
                                // If switching to a different strategy, update selection
                                if (group?.strategyName && group.strategyName !== selectedStrategy?.id) {
                                    const matchingStrategy = strategies.find(s => s.id === group.strategyName);
                                    if (matchingStrategy) {
                                        handleStrategyChange(matchingStrategy);
                                    }
                                }
                            }}
                            onNewSession={() => setIsNewSessionModalOpen(true)}
                            activeSessionGroup={activeSessionGroup}
                            savedSymbols={savedSymbols}
                        />

                        {/* Live Strategy Panel */}
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
                            activeSessionGroup={activeSessionGroup}
                            onSessionAction={(action, session) => {
                                // Refresh session list after resume/delete
                                sessionSwitcherRef.current?.refresh?.();
                                // Clear selection if deleted - delay to allow refresh to complete
                                if (action === 'delete') {
                                    setTimeout(() => {
                                        setActiveSessionGroup(null);
                                    }, 300);
                                }
                            }}
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

                        {/* New Session Modal */}
                        <NewSessionModal
                            isOpen={isNewSessionModalOpen}
                            onClose={() => setIsNewSessionModalOpen(false)}
                            onSessionStarted={(result) => {
                                // Refresh SessionSwitcher first to get new session data
                                sessionSwitcherRef.current?.refresh?.();

                                // Set the new session group as active
                                setActiveSessionGroup({
                                    accountId: result.accountId,
                                    strategyName: result.strategyName,
                                    groupId: result.groupId,
                                    sessionId: result.sessions?.[0]?.sessionId,
                                    sessions: result.sessions
                                });

                                // Switch to the new strategy if different
                                if (result.strategyName !== selectedStrategy?.id) {
                                    const matchingStrategy = strategies.find(s => s.id === result.strategyName);
                                    if (matchingStrategy) {
                                        handleStrategyChange(matchingStrategy);
                                    }
                                }
                            }}
                            strategies={strategies}
                        />
                    </div>
                ) : (
                    <div className="flex flex-col items-center justify-center p-20 text-gray-400 bg-white/5 border border-white/10 rounded-xl">
                        <div className="w-20 h-20 bg-gray-800/50 rounded-full flex items-center justify-center mx-auto mb-4">
                            <Radio size={36} className="text-gray-600" />
                        </div>
                        <p className="text-lg font-medium">설정이 없습니다</p>
                        <p className="text-sm text-gray-500 mt-2">Strategies 페이지에서 전략 설정을 먼저 구성하세요</p>
                    </div>
                )}
            </div>

            {/* Confirm Modal */}
            <ConfirmModal
                isOpen={confirmModal.isOpen}
                onClose={closeConfirm}
                onConfirm={() => {
                    confirmModal.onConfirm();
                    closeConfirm();
                }}
                onCancel={confirmModal.onCancel ? () => {
                    confirmModal.onCancel();
                    closeConfirm();
                } : null}
                title={confirmModal.title}
                message={confirmModal.message}
                isDanger={confirmModal.isDanger}
                confirmText={confirmModal.confirmText}
                cancelText={confirmModal.cancelText}
            />
        </div>
    );
};

export default LiveTradingView;
