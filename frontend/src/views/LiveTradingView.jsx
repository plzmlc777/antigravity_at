import React, { useState, useRef } from 'react';
import { useWatchlist } from '../context/WatchlistContext';
import { useLiveTrading } from '../context/LiveTradingContext';
import LiveStrategyPanel from '../components/LiveStrategyPanel';
import SessionSwitcher from '../components/SessionSwitcher';
import NewSessionModal from '../components/NewSessionModal';
import ConfirmModal from '../components/ConfirmModal';
import { Radio } from 'lucide-react';

const LiveTradingView = () => {
    // Symbol State - Use shared watchlist context (synced with DB)
    const { savedSymbols } = useWatchlist();

    // Use centralized LiveTradingContext for state management
    const {
        activeSessionGroup,
        setActiveSessionGroup,
        executionMode,
        setExecutionMode,
        setIsLiveRunning,
        strategies,
        selectedStrategy,
        setSelectedStrategy,
        getStrategyById,
    } = useLiveTrading();

    // Local state for rank selection and modal
    const [currentRankIndex, setCurrentRankIndex] = useState(0);
    const [isNewSessionModalOpen, setIsNewSessionModalOpen] = useState(false);

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

    const closeConfirm = () => {
        setConfirmModal(prev => ({ ...prev, isOpen: false }));
    };

    // Handle session group selection
    const handleSelectSessionGroup = (group) => {
        setActiveSessionGroup(group);
        setCurrentRankIndex(0); // Reset rank to first when switching sessions
        // Update selectedStrategy from session group
        if (group?.strategyName) {
            const matchingStrategy = getStrategyById(group.strategyName);
            if (matchingStrategy) {
                setSelectedStrategy(matchingStrategy);
            }
        }
    };

    // Handle new session created
    const handleSessionStarted = (result) => {
        // Switch to "Show All" so the new session is visible
        sessionSwitcherRef.current?.showAllSessions?.();
        // Refresh SessionSwitcher to get new session data
        sessionSwitcherRef.current?.refresh?.();

        // Set the new session group as active (also store account_id in snake_case for balance)
        setActiveSessionGroup({
            accountId: result.accountId,
            account_id: result.accountId,
            strategyName: result.strategyName,
            groupId: result.groupId,
            sessionId: result.sessions?.[0]?.sessionId,
            sessions: result.sessions,
            profile_name: result.profileName,
        });

        // Update selectedStrategy from result
        if (result.strategyName !== selectedStrategy?.id) {
            const matchingStrategy = getStrategyById(result.strategyName);
            if (matchingStrategy) {
                setSelectedStrategy(matchingStrategy);
            }
        }
    };

    // Handle session action (resume/delete)
    const handleSessionAction = (action, session) => {
        // Refresh session list after resume/delete
        sessionSwitcherRef.current?.refresh?.();
        // Clear selection if deleted - delay to allow refresh to complete
        if (action === 'delete') {
            setTimeout(() => {
                setActiveSessionGroup(null);
            }, 300);
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
                        onSelectSessionGroup={handleSelectSessionGroup}
                        onNewSession={() => setIsNewSessionModalOpen(true)}
                        activeSessionGroup={activeSessionGroup}
                        savedSymbols={savedSymbols}
                    />

                    {/* Live Strategy Panel - only show when session is selected */}
                    {activeSessionGroup ? (
                        <LiveStrategyPanel
                            strategyConfig={activeSessionGroup.configList?.[currentRankIndex] || activeSessionGroup.configList?.[0] || {}}
                            strategyName={activeSessionGroup.strategyName}
                            configList={activeSessionGroup.configList || []}
                            savedSymbols={savedSymbols}
                            currentRankIndex={currentRankIndex}
                            onRankChange={setCurrentRankIndex}
                            executionMode={executionMode}
                            onExecutionModeChange={setExecutionMode}
                            parameterSchema={selectedStrategy?.parameter_schema}
                            onStatusChange={(newStatus) => setIsLiveRunning(newStatus === 'RUNNING')}
                            onCapitalChange={() => {}}
                            activeSessionGroup={activeSessionGroup}
                            onSessionAction={handleSessionAction}
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
                        onSessionStarted={handleSessionStarted}
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
