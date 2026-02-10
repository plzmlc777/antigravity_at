import React, { useState, useEffect } from 'react';
import { X, Play, Building2, Briefcase, Target, DollarSign, AlertTriangle, Layers } from 'lucide-react';
import { getAccounts, startLiveBot, stopAllLiveBots, getStrategyConfigs } from '../api/client';

/**
 * NewSessionModal - Phase 5: Start New Live Session
 *
 * Modal for starting a new live trading session with:
 * - Account selection
 * - Strategy selection
 * - Rank (symbol) selection from strategy configs
 * - Capital allocation
 * - Execution mode (Exclusive/Parallel)
 */
const NewSessionModal = ({ isOpen, onClose, onSessionStarted, strategies = [] }) => {
    // State
    const [accounts, setAccounts] = useState([]);
    const [selectedAccountId, setSelectedAccountId] = useState(null);
    const [selectedStrategyId, setSelectedStrategyId] = useState('');
    const [strategyConfigs, setStrategyConfigs] = useState([]);
    const [selectedRanks, setSelectedRanks] = useState([]); // Array of indices
    const [capital, setCapital] = useState(10000000);
    const [executionMode, setExecutionMode] = useState('exclusive');
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState(null);

    // Fetch accounts on mount
    useEffect(() => {
        if (isOpen) {
            fetchAccounts();
            // Reset state
            setSelectedStrategyId('');
            setStrategyConfigs([]);
            setSelectedRanks([]);
            setError(null);
        }
    }, [isOpen]);

    // Fetch strategy configs when strategy changes
    useEffect(() => {
        if (selectedStrategyId) {
            fetchStrategyConfigs(selectedStrategyId);
        } else {
            setStrategyConfigs([]);
            setSelectedRanks([]);
        }
    }, [selectedStrategyId]);

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

    const fetchStrategyConfigs = async (strategyId) => {
        try {
            const configs = await getStrategyConfigs(strategyId);
            const activeConfigs = configs.filter(c => c.is_active);
            setStrategyConfigs(activeConfigs);
            // Default: select all active ranks
            setSelectedRanks(activeConfigs.map((_, idx) => idx));
        } catch (err) {
            console.error('Failed to fetch strategy configs:', err);
            setStrategyConfigs([]);
            setSelectedRanks([]);
        }
    };

    const toggleRankSelection = (idx) => {
        setSelectedRanks(prev => {
            if (prev.includes(idx)) {
                return prev.filter(i => i !== idx);
            } else {
                return [...prev, idx].sort((a, b) => a - b);
            }
        });
    };

    const selectAllRanks = () => {
        setSelectedRanks(strategyConfigs.map((_, idx) => idx));
    };

    const handleStart = async () => {
        if (!selectedAccountId) {
            setError('계좌를 선택해주세요');
            return;
        }
        if (!selectedStrategyId) {
            setError('전략을 선택해주세요');
            return;
        }
        if (selectedRanks.length === 0) {
            setError('최소 하나의 Rank를 선택해주세요');
            return;
        }

        setIsLoading(true);
        setError(null);

        try {
            // First stop any existing sessions for this account
            try {
                await stopAllLiveBots({ force: true });
            } catch (e) {
                // Ignore - might not have any sessions
            }

            // Start sessions for each selected rank
            const startedSessions = [];
            const totalCapital = parseFloat(capital) || 10000000;
            const capitalPerRank = executionMode === 'parallel'
                ? Math.floor(totalCapital / selectedRanks.length)
                : totalCapital;

            for (const idx of selectedRanks) {
                const cfg = strategyConfigs[idx];
                const payload = {
                    symbol: cfg.symbol,
                    strategy_name: selectedStrategyId,
                    strategy_config: {
                        ...cfg,
                        execution_mode: executionMode
                    },
                    initial_capital: capitalPerRank,
                    account_id: selectedAccountId
                };

                try {
                    const result = await startLiveBot(payload);
                    startedSessions.push({
                        sessionId: result.session_id,
                        symbol: cfg.symbol,
                        rankIndex: idx
                    });
                } catch (err) {
                    console.error(`Failed to start session for ${cfg.symbol}:`, err);
                }
            }

            if (startedSessions.length > 0) {
                if (onSessionStarted) {
                    onSessionStarted({
                        accountId: selectedAccountId,
                        strategyName: selectedStrategyId,
                        sessions: startedSessions,
                        executionMode
                    });
                }
                onClose();
            } else {
                setError('세션을 시작할 수 없습니다');
            }
        } catch (err) {
            setError(err.response?.data?.detail || err.message || '세션 시작 실패');
        } finally {
            setIsLoading(false);
        }
    };

    const selectedAccount = accounts.find(a => a.id === selectedAccountId);

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
            {/* Backdrop */}
            <div
                className="absolute inset-0 bg-black/70 backdrop-blur-sm"
                onClick={onClose}
            />

            {/* Modal */}
            <div className="relative bg-[#1a1a2e] border border-white/10 rounded-2xl w-full max-w-lg mx-4 shadow-2xl max-h-[90vh] overflow-y-auto">
                {/* Header */}
                <div className="flex items-center justify-between px-6 py-4 border-b border-white/10 sticky top-0 bg-[#1a1a2e]">
                    <h2 className="text-lg font-bold text-white flex items-center gap-2">
                        <Play size={20} className="text-green-400" />
                        새 라이브 세션
                    </h2>
                    <button
                        onClick={onClose}
                        className="p-2 hover:bg-white/10 rounded-lg transition-colors"
                    >
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
                            className="w-full bg-black/40 border border-white/10 rounded-xl px-4 py-3 text-white outline-none focus:border-indigo-500/50 transition-all appearance-none cursor-pointer"
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

                    {/* Strategy Selection */}
                    <div>
                        <label className="flex items-center gap-2 text-sm font-bold text-gray-400 uppercase tracking-wider mb-2">
                            <Briefcase size={14} />
                            전략
                        </label>
                        <select
                            value={selectedStrategyId}
                            onChange={(e) => setSelectedStrategyId(e.target.value)}
                            className="w-full bg-black/40 border border-white/10 rounded-xl px-4 py-3 text-white outline-none focus:border-indigo-500/50 transition-all appearance-none cursor-pointer"
                        >
                            <option value="">전략을 선택하세요</option>
                            {strategies.map(s => (
                                <option key={s.id} value={s.id}>
                                    {s.name || s.id}
                                </option>
                            ))}
                        </select>
                    </div>

                    {/* Rank Selection (only if strategy selected) */}
                    {strategyConfigs.length > 0 && (
                        <div>
                            <div className="flex items-center justify-between mb-2">
                                <label className="flex items-center gap-2 text-sm font-bold text-gray-400 uppercase tracking-wider">
                                    <Target size={14} />
                                    종목 (Rank)
                                </label>
                                <button
                                    onClick={selectAllRanks}
                                    className="text-xs text-indigo-400 hover:text-indigo-300"
                                >
                                    전체 선택
                                </button>
                            </div>
                            <div className="grid grid-cols-2 gap-2">
                                {strategyConfigs.map((cfg, idx) => (
                                    <button
                                        key={idx}
                                        onClick={() => toggleRankSelection(idx)}
                                        className={`
                                            flex items-center gap-2 px-3 py-2 rounded-lg text-left transition-all
                                            ${selectedRanks.includes(idx)
                                                ? 'bg-indigo-600/30 border-2 border-indigo-500 text-white'
                                                : 'bg-black/30 border border-white/10 text-gray-400 hover:border-white/30'}
                                        `}
                                    >
                                        <div className={`w-4 h-4 rounded border-2 flex items-center justify-center
                                            ${selectedRanks.includes(idx) ? 'border-indigo-500 bg-indigo-500' : 'border-gray-500'}`}>
                                            {selectedRanks.includes(idx) && (
                                                <span className="text-white text-xs">✓</span>
                                            )}
                                        </div>
                                        <span className="text-sm">
                                            R{idx + 1}: {cfg.symbol}
                                        </span>
                                    </button>
                                ))}
                            </div>
                            <p className="text-xs text-gray-500 mt-2">
                                {selectedRanks.length}개 선택됨
                            </p>
                        </div>
                    )}

                    {/* Execution Mode */}
                    <div>
                        <label className="flex items-center gap-2 text-sm font-bold text-gray-400 uppercase tracking-wider mb-2">
                            <Layers size={14} />
                            실행 모드
                        </label>
                        <div className="grid grid-cols-2 gap-2">
                            <button
                                onClick={() => setExecutionMode('exclusive')}
                                className={`px-4 py-3 rounded-xl text-sm font-medium transition-all ${
                                    executionMode === 'exclusive'
                                        ? 'bg-indigo-600/30 border-2 border-indigo-500 text-white'
                                        : 'bg-black/30 border border-white/10 text-gray-400 hover:border-white/30'
                                }`}
                            >
                                Exclusive
                                <p className="text-[10px] opacity-70 mt-1">한 번에 하나만 매매</p>
                            </button>
                            <button
                                onClick={() => setExecutionMode('parallel')}
                                className={`px-4 py-3 rounded-xl text-sm font-medium transition-all ${
                                    executionMode === 'parallel'
                                        ? 'bg-indigo-600/30 border-2 border-indigo-500 text-white'
                                        : 'bg-black/30 border border-white/10 text-gray-400 hover:border-white/30'
                                }`}
                            >
                                Parallel
                                <p className="text-[10px] opacity-70 mt-1">동시에 여러 종목 매매</p>
                            </button>
                        </div>
                    </div>

                    {/* Capital */}
                    <div>
                        <label className="flex items-center gap-2 text-sm font-bold text-gray-400 uppercase tracking-wider mb-2">
                            <DollarSign size={14} />
                            투자 자본 (KRW)
                        </label>
                        <div className="relative">
                            <input
                                type="number"
                                value={capital}
                                onChange={(e) => setCapital(parseFloat(e.target.value) || 0)}
                                className="w-full bg-black/40 border border-white/10 rounded-xl px-4 py-3 text-white font-mono text-lg outline-none focus:border-indigo-500/50 transition-all"
                                placeholder="10000000"
                            />
                            <span className="absolute right-4 top-1/2 -translate-y-1/2 text-gray-500 font-bold">
                                KRW
                            </span>
                        </div>
                        {executionMode === 'parallel' && selectedRanks.length > 1 && (
                            <p className="text-xs text-gray-500 mt-1.5">
                                Rank당 약 {Math.floor(capital / selectedRanks.length).toLocaleString()} KRW 배분
                            </p>
                        )}
                    </div>

                    {/* Error Message */}
                    {error && (
                        <div className="flex items-center gap-2 px-4 py-3 bg-red-500/10 border border-red-500/30 rounded-xl text-red-400 text-sm">
                            <AlertTriangle size={16} />
                            {error}
                        </div>
                    )}

                    {/* Summary */}
                    {selectedAccount && selectedStrategyId && selectedRanks.length > 0 && (
                        <div className="bg-indigo-500/10 border border-indigo-500/20 rounded-xl p-4">
                            <p className="text-sm text-indigo-300 font-medium mb-2">세션 요약</p>
                            <div className="grid grid-cols-2 gap-2 text-xs text-gray-400">
                                <div>계좌: <span className="text-white">{selectedAccount.account_name}</span></div>
                                <div>환경: <span className={selectedAccount.environment === 'real' ? 'text-red-400' : 'text-yellow-400'}>
                                    {selectedAccount.environment === 'real' ? '실거래' : '모의/페이퍼'}
                                </span></div>
                                <div>전략: <span className="text-white">{selectedStrategyId}</span></div>
                                <div>종목: <span className="text-white">{selectedRanks.length}개</span></div>
                                <div>모드: <span className="text-white">{executionMode}</span></div>
                                <div>자본: <span className="text-white">{capital.toLocaleString()}</span></div>
                            </div>
                        </div>
                    )}
                </div>

                {/* Footer */}
                <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-white/10 sticky bottom-0 bg-[#1a1a2e]">
                    <button
                        onClick={onClose}
                        className="px-5 py-2.5 text-gray-400 hover:text-white transition-colors"
                    >
                        취소
                    </button>
                    <button
                        onClick={handleStart}
                        disabled={isLoading || !selectedAccountId || !selectedStrategyId || selectedRanks.length === 0}
                        className="flex items-center gap-2 px-6 py-2.5 bg-green-600 hover:bg-green-500 disabled:bg-gray-700 disabled:cursor-not-allowed text-white font-bold rounded-xl transition-all"
                    >
                        {isLoading ? (
                            <>
                                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                                시작 중...
                            </>
                        ) : (
                            <>
                                <Play size={16} />
                                세션 시작
                            </>
                        )}
                    </button>
                </div>
            </div>
        </div>
    );
};

export default NewSessionModal;
