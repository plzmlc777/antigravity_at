import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { X, Plus, Building2, FolderOpen, Info, Target, Layers } from 'lucide-react';
import { getAccounts, startLiveBot } from '../api/client';

/**
 * NewSessionModal - Phase 5: Add New Live Session from Profile (Simplified)
 *
 * Modal for adding a new live trading session:
 * - Profile selection only
 * - Profile information display (read-only)
 * - Account selection
 *
 * Other settings (capital, execution mode, paper/real) are configured in Live Operation panel after session creation.
 */
const NewSessionModal = ({ isOpen, onClose, onSessionStarted }) => {
    // State
    const [accounts, setAccounts] = useState([]);
    const [selectedAccountId, setSelectedAccountId] = useState(null);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState(null);

    // Profile state
    const [profiles, setProfiles] = useState([]);
    const [selectedProfileId, setSelectedProfileId] = useState('');
    const [selectedProfile, setSelectedProfile] = useState(null);
    const [isLoadingProfiles, setIsLoadingProfiles] = useState(true);

    // Fetch accounts and profiles on mount
    useEffect(() => {
        if (isOpen) {
            fetchAccounts();
            fetchProfiles();
            // Reset state
            setSelectedProfileId('');
            setSelectedProfile(null);
            setError(null);
        }
    }, [isOpen]);

    const fetchProfiles = async () => {
        setIsLoadingProfiles(true);
        try {
            const response = await axios.get('/api/v1/live/profiles');
            setProfiles(response.data.data || []);
        } catch (err) {
            console.error('Failed to fetch profiles:', err);
            setProfiles([]);
        } finally {
            setIsLoadingProfiles(false);
        }
    };

    const loadProfile = async (profileId) => {
        if (!profileId) {
            setSelectedProfileId('');
            setSelectedProfile(null);
            return;
        }
        try {
            const response = await axios.get(`/api/v1/live/profiles/${profileId}`);
            setSelectedProfileId(profileId);
            setSelectedProfile(response.data);
        } catch (err) {
            console.error('Failed to load profile:', err);
            setError('프로필을 불러올 수 없습니다.');
        }
    };

    const fetchAccounts = async () => {
        try {
            const accountsList = await getAccounts();
            const sorted = [...accountsList].sort((a, b) => {
                if (a.is_active !== b.is_active) return b.is_active ? 1 : -1;
                if (a.is_disabled !== b.is_disabled) return a.is_disabled ? 1 : -1;
                return a.id - b.id;
            }).filter(acc => !acc.is_disabled);
            setAccounts(sorted);
            // Default to active account
            const activeAccount = sorted.find(acc => acc.is_active);
            if (activeAccount) {
                setSelectedAccountId(activeAccount.id);
            }
        } catch (err) {
            console.error('Failed to fetch accounts:', err);
            setError('계좌 목록을 불러올 수 없습니다.');
        }
    };

    const handleAddSession = async () => {
        if (!selectedAccountId) {
            setError('계좌를 선택해주세요');
            return;
        }
        if (!selectedProfile) {
            setError('프로필을 선택해주세요');
            return;
        }

        setIsLoading(true);
        setError(null);

        try {
            // Generate group_id for multi-rank sessions
            const groupId = `grp_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
            // Only include active ranks (filter out draft tabs)
            const allRankConfigs = selectedProfile.rank_configs || [];
            const rankConfigs = allRankConfigs.filter(cfg => cfg.is_active !== false);
            const isMultiRank = rankConfigs.length > 1;

            // Create sessions for all active ranks in the profile (in STOPPED state)
            const startedSessions = [];
            const totalCapital = selectedProfile.initial_capital || 10000000;
            const executionMode = selectedProfile.execution_mode || 'parallel';
            const capitalPerRank = executionMode === 'parallel'
                ? Math.floor(totalCapital / rankConfigs.length)
                : totalCapital;

            for (let idx = 0; idx < rankConfigs.length; idx++) {
                const cfg = rankConfigs[idx];
                // 프로필 데이터를 그대로 사용 (Strategies 탭에서 설정한 값 그대로)
                // Live에서는 계좌, 자본금, Paper/Real 모드만 설정
                // Resolve preset name for live session tracking
                const presetName = cfg.parameter_presets?.find(p => p.id === cfg.selected_preset_id)?.name || null;
                const payload = {
                    symbol: cfg.symbol,
                    strategy_name: selectedProfile.strategy_name,
                    strategy_config: { ...cfg, execution_mode: executionMode, selected_preset_name: presetName },
                    initial_capital: capitalPerRank,
                    is_paper: true,  // 기본값 Paper (LiveStrategyPanel에서 변경 가능)
                    account_id: selectedAccountId,
                    group_id: isMultiRank ? groupId : null,
                    profile_name: selectedProfile.name,
                    profile_id: selectedProfileId,
                    auto_start: false
                };

                try {
                    const result = await startLiveBot(payload);
                    startedSessions.push({
                        sessionId: result.session_id,
                        symbol: cfg.symbol,
                        rankIndex: idx
                    });
                } catch (err) {
                    console.error(`Failed to create session for ${cfg.symbol}:`, err);
                }
            }

            if (startedSessions.length > 0) {
                if (onSessionStarted) {
                    onSessionStarted({
                        accountId: selectedAccountId,
                        strategyName: selectedProfile.strategy_name,
                        sessions: startedSessions,
                        executionMode,
                        groupId: isMultiRank ? groupId : null,
                        profileName: selectedProfile.name
                    });
                }
                onClose();
            } else {
                setError('세션을 생성할 수 없습니다');
            }
        } catch (err) {
            setError(err.response?.data?.detail || err.message || '세션 생성 실패');
        } finally {
            setIsLoading(false);
        }
    };

    const selectedAccount = accounts.find(a => a.id === selectedAccountId);

    if (!isOpen) return null;

    // No profiles available - show guidance
    if (!isLoadingProfiles && profiles.length === 0) {
        return (
            <div className="fixed inset-0 z-50 flex items-center justify-center">
                <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />
                <div className="relative bg-[#1a1a2e] border border-white/10 rounded-2xl w-full max-w-md mx-4 shadow-2xl">
                    {/* Header */}
                    <div className="flex items-center justify-between px-6 py-4 border-b border-white/10">
                        <h2 className="text-lg font-bold text-white flex items-center gap-2">
                            <FolderOpen size={20} className="text-yellow-400" />
                            프로필 필요
                        </h2>
                        <button onClick={onClose} className="p-2 hover:bg-white/10 rounded-lg transition-colors">
                            <X size={20} className="text-gray-400" />
                        </button>
                    </div>

                    {/* Body */}
                    <div className="p-6 space-y-4">
                        <div className="flex items-start gap-3 p-4 bg-yellow-500/10 border border-yellow-500/30 rounded-xl">
                            <Info size={20} className="text-yellow-400 flex-shrink-0 mt-0.5" />
                            <div className="text-sm text-yellow-200">
                                <p className="font-medium mb-2">저장된 프로필이 없습니다</p>
                                <p className="text-yellow-200/70 text-xs leading-relaxed">
                                    라이브 세션을 시작하려면 먼저 전략 프로필을 저장해야 합니다.
                                </p>
                            </div>
                        </div>

                        <div className="bg-black/30 rounded-xl p-4 space-y-3">
                            <p className="text-sm text-gray-300 font-medium">프로필 저장 방법:</p>
                            <ol className="text-xs text-gray-400 space-y-2 list-decimal list-inside">
                                <li>전략 페이지에서 전략 선택</li>
                                <li>랭크탭에서 종목별 파라미터 최적화</li>
                                <li>통합탭에서 전체 설정 확인</li>
                                <li><span className="text-emerald-400 font-medium">Save Profile</span> 버튼 클릭</li>
                            </ol>
                        </div>
                    </div>

                    {/* Footer */}
                    <div className="flex items-center justify-end px-6 py-4 border-t border-white/10">
                        <button
                            onClick={onClose}
                            className="px-5 py-2.5 bg-white/10 hover:bg-white/20 text-white rounded-xl transition-colors"
                        >
                            확인
                        </button>
                    </div>
                </div>
            </div>
        );
    }

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
            {/* Backdrop */}
            <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />

            {/* Modal */}
            <div className="relative bg-[#1a1a2e] border border-white/10 rounded-2xl w-full max-w-lg mx-4 shadow-2xl">
                {/* Header */}
                <div className="flex items-center justify-between px-6 py-4 border-b border-white/10">
                    <h2 className="text-lg font-bold text-white flex items-center gap-2">
                        <Plus size={20} className="text-emerald-400" />
                        새 세션 생성
                    </h2>
                    <button onClick={onClose} className="p-2 hover:bg-white/10 rounded-lg transition-colors">
                        <X size={20} className="text-gray-400" />
                    </button>
                </div>

                {/* Body */}
                <div className="p-6 space-y-5">
                    {/* Account Selection */}
                    <div>
                        <label className="flex items-center gap-2 text-sm font-bold text-gray-400 uppercase tracking-wider mb-2">
                            <Building2 size={14} />
                            거래 계좌
                        </label>
                        <select
                            value={selectedAccountId || ''}
                            onChange={(e) => setSelectedAccountId(parseInt(e.target.value))}
                            className="w-full bg-black/40 border border-white/10 rounded-xl px-4 py-3 text-white outline-none focus:border-emerald-500/50 transition-all appearance-none cursor-pointer"
                        >
                            <option value="">계좌를 선택하세요</option>
                            {accounts.map(acc => (
                                <option key={acc.id} value={acc.id}>
                                    {acc.account_name} ({acc.environment === 'real' ? '실거래' : acc.environment === 'virtual' ? '모의' : '페이퍼'})
                                    {acc.is_active ? ' ★' : ''}
                                </option>
                            ))}
                        </select>
                        {selectedAccount && (
                            <p className="text-xs text-gray-500 mt-1.5">
                                계좌번호: ****{selectedAccount.account_number?.slice(-4) || '----'}
                            </p>
                        )}
                    </div>

                    {/* Profile Selection */}
                    <div>
                        <label className="flex items-center gap-2 text-sm font-bold text-gray-400 uppercase tracking-wider mb-2">
                            <FolderOpen size={14} />
                            전략 프로필
                        </label>
                        {isLoadingProfiles ? (
                            <div className="flex items-center gap-2 px-4 py-3 bg-black/40 border border-white/10 rounded-xl">
                                <div className="w-4 h-4 border-2 border-emerald-500/30 border-t-emerald-500 rounded-full animate-spin" />
                                <span className="text-gray-400 text-sm">프로필 로딩 중...</span>
                            </div>
                        ) : (
                            <select
                                value={selectedProfileId}
                                onChange={(e) => loadProfile(e.target.value)}
                                className="w-full bg-black/40 border border-white/10 rounded-xl px-4 py-3 text-white outline-none focus:border-emerald-500/50 transition-all appearance-none cursor-pointer"
                            >
                                <option value="">프로필을 선택하세요</option>
                                {profiles.map(p => (
                                    <option key={p.id} value={p.id}>
                                        {p.name} ({p.strategy_name}, {p.rank_count}개 종목)
                                    </option>
                                ))}
                            </select>
                        )}
                    </div>

                    {/* Profile Information (Read-only) */}
                    {selectedProfile && (
                        <div className="bg-black/30 border border-white/10 rounded-xl p-4 space-y-3">
                            <h3 className="text-sm font-bold text-white">{selectedProfile.name}</h3>

                            <div className="grid grid-cols-2 gap-3 pt-2 border-t border-white/5">
                                <div className="flex items-center gap-2">
                                    <Target size={12} className="text-gray-500" />
                                    <span className="text-xs text-gray-400">전략:</span>
                                    <span className="text-xs text-white">{selectedProfile.strategy_name}</span>
                                </div>
                                <div className="flex items-center gap-2">
                                    <Layers size={12} className="text-gray-500" />
                                    <span className="text-xs text-gray-400">실행모드:</span>
                                    <span className="text-xs text-white">{selectedProfile.execution_mode || 'parallel'}</span>
                                </div>
                            </div>

                            {/* Rank List - Only show active ranks */}
                            {selectedProfile.rank_configs && selectedProfile.rank_configs.length > 0 && (() => {
                                const activeRanks = selectedProfile.rank_configs.filter(cfg => cfg.is_active !== false);
                                return activeRanks.length > 0 && (
                                    <div className="pt-2 border-t border-white/5">
                                        <p className="text-xs text-gray-500 mb-2">포함된 종목 ({activeRanks.length}개):</p>
                                        <div className="flex flex-wrap gap-1.5">
                                            {activeRanks.map((cfg, idx) => (
                                                <span
                                                    key={idx}
                                                    className="text-xs px-2 py-1 bg-indigo-500/20 text-indigo-300 rounded"
                                                >
                                                    {cfg.tabName?.replace('Rank ', 'R') || `R${cfg.rank ?? (idx + 1)}`}: {cfg.symbol}
                                                </span>
                                            ))}
                                        </div>
                                    </div>
                                );
                            })()}

                            <div className="pt-2 border-t border-white/5">
                                <p className="text-xs text-gray-500 flex items-center gap-1">
                                    <Info size={10} />
                                    세션 생성 후 Live Operation에서 설정을 수정할 수 있습니다
                                </p>
                            </div>
                        </div>
                    )}

                    {/* Error Message */}
                    {error && (
                        <div className="flex items-center gap-2 px-4 py-3 bg-red-500/10 border border-red-500/30 rounded-xl text-red-400 text-sm">
                            <Info size={16} />
                            {error}
                        </div>
                    )}
                </div>

                {/* Footer */}
                <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-white/10">
                    <button
                        onClick={onClose}
                        className="px-5 py-2.5 text-gray-400 hover:text-white transition-colors"
                    >
                        취소
                    </button>
                    <button
                        onClick={handleAddSession}
                        disabled={isLoading || !selectedAccountId || !selectedProfile}
                        className="flex items-center gap-2 px-6 py-2.5 bg-emerald-600 hover:bg-emerald-500 disabled:bg-gray-700 disabled:cursor-not-allowed text-white font-bold rounded-xl transition-all"
                    >
                        {isLoading ? (
                            <>
                                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                                생성 중...
                            </>
                        ) : (
                            <>
                                <Plus size={16} />
                                세션 생성
                            </>
                        )}
                    </button>
                </div>
            </div>
        </div>
    );
};

export default NewSessionModal;
