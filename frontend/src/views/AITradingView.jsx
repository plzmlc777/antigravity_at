import { useState, useEffect, useCallback } from 'react';
import { Bot, Plus, Trash2, RefreshCw, Radio } from 'lucide-react';
import { useLiveTrading } from '../context/LiveTradingContext';
import AIProfileForm from '../components/AIProfileForm';
import AIDecisionTimeline from '../components/AIDecisionTimeline';
import {
    getAIProfiles,
    createAIProfile,
    updateAIProfile,
    deleteAIProfile,
    startAITrading,
    stopAITrading,
    triggerAIDecision,
    getAIDecisions,
} from '../api/client';

export default function AITradingView() {
    const { strategies, accounts } = useLiveTrading();

    // Profile state
    const [profiles, setProfiles] = useState([]);
    const [selectedProfileId, setSelectedProfileId] = useState(null);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [actionRunning, setActionRunning] = useState(false);

    // Decision state
    const [decisions, setDecisions] = useState([]);
    const [decisionsLoading, setDecisionsLoading] = useState(false);

    // Error/success feedback
    const [message, setMessage] = useState(null);

    const selectedProfile = profiles.find(p => p.id === selectedProfileId) || null;

    // ── Load Profiles ──────────────────────────────
    const loadProfiles = useCallback(async () => {
        try {
            setLoading(true);
            const res = await getAIProfiles();
            setProfiles(res.data || []);
        } catch (err) {
            console.error('Failed to load AI profiles:', err);
            showMessage('프로필 목록 로딩 실패', 'error');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        loadProfiles();
    }, [loadProfiles]);

    // ── Load Decisions when profile selected ───────
    const loadDecisions = useCallback(async (profileId) => {
        if (!profileId) { setDecisions([]); return; }
        try {
            setDecisionsLoading(true);
            const res = await getAIDecisions(profileId);
            setDecisions(res.data || []);
        } catch (err) {
            console.error('Failed to load decisions:', err);
        } finally {
            setDecisionsLoading(false);
        }
    }, []);

    useEffect(() => {
        loadDecisions(selectedProfileId);
    }, [selectedProfileId, loadDecisions]);

    // ── Auto-refresh for running profiles ──────────
    useEffect(() => {
        const hasRunning = profiles.some(p => p.is_running);
        if (!hasRunning) return;
        const interval = setInterval(() => {
            loadProfiles();
            if (selectedProfileId) loadDecisions(selectedProfileId);
        }, 10000);
        return () => clearInterval(interval);
    }, [profiles, selectedProfileId, loadProfiles, loadDecisions]);

    // ── Message helper ─────────────────────────────
    const showMessage = (text, type = 'success') => {
        setMessage({ text, type });
        setTimeout(() => setMessage(null), 4000);
    };

    // ── Profile CRUD handlers ──────────────────────
    const handleSave = async (formData) => {
        try {
            setSaving(true);
            if (selectedProfile) {
                await updateAIProfile(selectedProfile.id, formData);
                showMessage('프로필 저장 완료');
            } else {
                const res = await createAIProfile(formData);
                setSelectedProfileId(res.data?.id);
                showMessage('프로필 생성 완료');
            }
            await loadProfiles();
        } catch (err) {
            showMessage(err.response?.data?.detail || '저장 실패', 'error');
        } finally {
            setSaving(false);
        }
    };

    const handleDelete = async (profileId) => {
        if (!confirm('이 AI 프로필을 삭제하시겠습니까?')) return;
        try {
            await deleteAIProfile(profileId);
            if (selectedProfileId === profileId) setSelectedProfileId(null);
            showMessage('프로필 삭제 완료');
            await loadProfiles();
        } catch (err) {
            showMessage(err.response?.data?.detail || '삭제 실패', 'error');
        }
    };

    // ── AI Trading Control ─────────────────────────
    const handleStart = async (profileId) => {
        try {
            setActionRunning(true);
            showMessage('AI 트레이딩 시작 중... (종목 선정 → 최적화 → 결정)', 'info');
            await startAITrading(profileId);
            showMessage('AI 트레이딩 시작 완료');
            await loadProfiles();
            await loadDecisions(profileId);
        } catch (err) {
            showMessage(err.response?.data?.detail || 'AI 시작 실패', 'error');
        } finally {
            setActionRunning(false);
        }
    };

    const handleStop = async (profileId) => {
        try {
            setActionRunning(true);
            await stopAITrading(profileId);
            showMessage('AI 트레이딩 중지 완료');
            await loadProfiles();
        } catch (err) {
            showMessage(err.response?.data?.detail || 'AI 중지 실패', 'error');
        } finally {
            setActionRunning(false);
        }
    };

    const handleTrigger = async (profileId) => {
        try {
            setActionRunning(true);
            showMessage('AI 결정 파이프라인 실행 중...', 'info');
            await triggerAIDecision(profileId);
            showMessage('AI 결정 완료');
            await loadProfiles();
            await loadDecisions(profileId);
        } catch (err) {
            showMessage(err.response?.data?.detail || '트리거 실패', 'error');
        } finally {
            setActionRunning(false);
        }
    };

    const handleNewProfile = () => {
        setSelectedProfileId(null);
    };

    return (
        <div className="space-y-6">
            {/* Page Header */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <Bot size={24} className="text-purple-400" />
                    <div>
                        <h1 className="text-xl font-bold text-white">AI Trading</h1>
                        <p className="text-xs text-gray-500">AI가 종목 선정 → 최적화 → 매매 결정을 자동으로 수행합니다</p>
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    <button
                        onClick={loadProfiles}
                        className="p-2 text-gray-400 hover:text-white hover:bg-white/5 rounded-lg transition-colors"
                        title="새로고침"
                    >
                        <RefreshCw size={16} />
                    </button>
                    <button
                        onClick={handleNewProfile}
                        className="flex items-center gap-1 px-3 py-2 bg-purple-600 text-white rounded-lg text-sm hover:bg-purple-700 transition-colors"
                    >
                        <Plus size={14} /> 새 프로필
                    </button>
                </div>
            </div>

            {/* Message Banner */}
            {message && (
                <div className={`px-4 py-2 rounded-lg text-sm ${
                    message.type === 'error' ? 'bg-red-500/10 border border-red-500/30 text-red-400'
                    : message.type === 'info' ? 'bg-blue-500/10 border border-blue-500/30 text-blue-400'
                    : 'bg-emerald-500/10 border border-emerald-500/30 text-emerald-400'
                }`}>
                    {message.text}
                </div>
            )}

            {/* Profile Tabs */}
            {profiles.length > 0 && (
                <div className="flex gap-2 flex-wrap">
                    {profiles.map(p => (
                        <div key={p.id} className="flex items-center">
                            <button
                                onClick={() => setSelectedProfileId(p.id)}
                                className={`flex items-center gap-2 px-3 py-1.5 rounded-l-lg text-sm transition-colors ${
                                    selectedProfileId === p.id
                                        ? 'bg-purple-600/30 text-purple-300 border border-purple-500/50'
                                        : 'bg-white/5 text-gray-400 hover:text-white border border-white/10'
                                }`}
                            >
                                {p.is_running && <Radio size={10} className="text-emerald-400 animate-pulse" />}
                                {p.name}
                                {p.current_symbol && (
                                    <span className="text-[10px] text-gray-500">({p.current_symbol})</span>
                                )}
                            </button>
                            <button
                                onClick={() => handleDelete(p.id)}
                                disabled={p.is_running}
                                className={`px-2 py-1.5 rounded-r-lg text-xs transition-colors border border-l-0 ${
                                    selectedProfileId === p.id
                                        ? 'border-purple-500/50 text-gray-500 hover:text-red-400'
                                        : 'border-white/10 text-gray-600 hover:text-red-400'
                                } disabled:opacity-30 disabled:cursor-not-allowed`}
                                title="삭제"
                            >
                                <Trash2 size={12} />
                            </button>
                        </div>
                    ))}
                </div>
            )}

            {/* Main Layout: Form + Timeline */}
            <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
                {/* Left: Profile Form (2/5) */}
                <div className="lg:col-span-2 bg-white/[0.02] border border-white/10 rounded-xl p-4">
                    {loading ? (
                        <div className="text-center py-8 text-gray-500 text-sm">로딩 중...</div>
                    ) : (
                        <AIProfileForm
                            profile={selectedProfile}
                            strategies={strategies}
                            accounts={accounts}
                            onSave={handleSave}
                            onStart={handleStart}
                            onStop={handleStop}
                            onTrigger={handleTrigger}
                            saving={saving}
                            running={actionRunning}
                        />
                    )}
                </div>

                {/* Right: Decision Timeline (3/5) */}
                <div className="lg:col-span-3 bg-white/[0.02] border border-white/10 rounded-xl p-4">
                    <div className="flex items-center justify-between mb-3">
                        <h3 className="text-sm font-semibold text-white">AI 결정 히스토리</h3>
                        {selectedProfile && (
                            <span className="text-[10px] text-gray-500">
                                총 {decisions.length}건
                            </span>
                        )}
                    </div>
                    {selectedProfile ? (
                        <AIDecisionTimeline
                            decisions={decisions}
                            loading={decisionsLoading}
                        />
                    ) : (
                        <div className="text-center py-12 text-gray-500 text-sm">
                            <Bot size={32} className="mx-auto mb-3 opacity-30" />
                            {profiles.length === 0
                                ? '첫 AI 프로필을 만들어 보세요'
                                : '프로필을 선택하면 결정 히스토리가 표시됩니다'
                            }
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
