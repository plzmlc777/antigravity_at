import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import { useMarketData } from '../context/MarketDataContext';
import { useWatchlist } from '../context/WatchlistContext';
import LiveStrategyPanel from '../components/LiveStrategyPanel';
import SessionSwitcher from '../components/SessionSwitcher';
import NewSessionModal from '../components/NewSessionModal';
import ConfirmModal from '../components/ConfirmModal';
import { Radio } from 'lucide-react';

const LiveTradingView = () => {
    // 계좌 중심: 활성 계좌 ID 가져오기
    const { systemStatus } = useMarketData();
    const activeAccountId = systemStatus?.account_id || null;

    // Symbol State - Use shared watchlist context (synced with DB)
    const { currentSymbol, setCurrentSymbol, savedSymbols } = useWatchlist();

    // Strategy State (for NewSessionModal)
    const [strategies, setStrategies] = useState([]);
    const [selectedStrategy, setSelectedStrategy] = useState(null);

    // Live-specific State
    const [isLiveRunning, setIsLiveRunning] = useState(false);
    const [isNewSessionModalOpen, setIsNewSessionModalOpen] = useState(false);
    const [activeSessionGroup, setActiveSessionGroup] = useState(null);
    const [executionMode, setExecutionMode] = useState(() => {
        const saved = localStorage.getItem('integratedExecutionMode');
        return saved || 'exclusive';
    });

    // Refs
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

    // Save execution mode to localStorage (profile-level setting is in NewSessionModal)
    useEffect(() => {
        localStorage.setItem('integratedExecutionMode', executionMode);
    }, [executionMode]);

    // Fetch strategies on mount (for NewSessionModal)
    useEffect(() => {
        fetchStrategies();
    }, []);

    const fetchStrategies = async () => {
        try {
            const res = await axios.get('/api/v1/strategies/list');
            setStrategies(res.data);
        } catch (e) {
            console.error(e);
        }
    };

    return (
        <div className="flex flex-col gap-6 pb-10">
            {/* Main Content Area */}
            <div className="space-y-6 pb-20">
                <div className="animate-fade-in-up">
                    {/* Session Switcher for Multi-Account Support */}
                    <SessionSwitcher
                        ref={sessionSwitcherRef}
                        onSelectSessionGroup={(group) => {
                            setActiveSessionGroup(group);
                            // Update selectedStrategy from session group
                            if (group?.strategyName) {
                                const matchingStrategy = strategies.find(s => s.id === group.strategyName);
                                if (matchingStrategy) {
                                    setSelectedStrategy(matchingStrategy);
                                }
                            }
                        }}
                        onNewSession={() => setIsNewSessionModalOpen(true)}
                        activeSessionGroup={activeSessionGroup}
                        savedSymbols={savedSymbols}
                    />

                    {/* Live Strategy Panel - only show when session is selected */}
                    {activeSessionGroup ? (
                        <LiveStrategyPanel
                            strategyConfig={activeSessionGroup.configList?.[0] || {}}
                            strategyName={activeSessionGroup.strategyName}
                            configList={activeSessionGroup.configList || []}
                            savedSymbols={savedSymbols}
                            currentRankIndex={0}
                            onRankChange={() => {}}
                            executionMode={executionMode}
                            onExecutionModeChange={(mode) => setExecutionMode(mode)}
                            parameterSchema={selectedStrategy?.parameter_schema}
                            onStatusChange={(newStatus) => setIsLiveRunning(newStatus === 'RUNNING')}
                            onCapitalChange={() => {}}
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
                        />
                    ) : (
                        <div className="flex flex-col items-center justify-center p-20 text-gray-400 bg-white/5 border border-white/10 rounded-xl mt-4">
                            <div className="w-20 h-20 bg-gray-800/50 rounded-full flex items-center justify-center mx-auto mb-4">
                                <Radio size={36} className="text-gray-600" />
                            </div>
                            <p className="text-lg font-medium">세션을 선택하세요</p>
                            <p className="text-sm text-gray-500 mt-2">위에서 세션을 선택하거나, "새 세션" 버튼을 눌러 새 세션을 시작하세요</p>
                        </div>
                    )}

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

                            // Update selectedStrategy from result (for display purposes)
                            if (result.strategyName !== selectedStrategy?.id) {
                                const matchingStrategy = strategies.find(s => s.id === result.strategyName);
                                if (matchingStrategy) {
                                    setSelectedStrategy(matchingStrategy);
                                }
                            }
                        }}
                        strategies={strategies}
                    />
                </div>
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
