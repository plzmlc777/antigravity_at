import { useState } from 'react';
import { Clock, TrendingUp, TrendingDown, AlertTriangle, CheckCircle, XCircle, Loader, ChevronDown, ChevronUp, Target, BarChart3, Brain } from 'lucide-react';

const STATUS_STYLES = {
    PENDING: { bg: 'bg-yellow-500/10', border: 'border-yellow-500/30', text: 'text-yellow-400', icon: Loader, label: '대기' },
    EXECUTING: { bg: 'bg-blue-500/10', border: 'border-blue-500/30', text: 'text-blue-400', icon: Loader, label: '실행 중' },
    COMPLETED: { bg: 'bg-emerald-500/10', border: 'border-emerald-500/30', text: 'text-emerald-400', icon: CheckCircle, label: '완료' },
    FAILED: { bg: 'bg-red-500/10', border: 'border-red-500/30', text: 'text-red-400', icon: XCircle, label: '실패' },
    SKIPPED: { bg: 'bg-gray-500/10', border: 'border-gray-500/30', text: 'text-gray-400', icon: AlertTriangle, label: '스킵' },
    REJECTED: { bg: 'bg-orange-500/10', border: 'border-orange-500/30', text: 'text-orange-400', icon: XCircle, label: '거부' },
};

const TRIGGER_LABELS = {
    initial_start: '초기 시작',
    manual: '수동 트리거',
    cycle_complete: '사이클 완료',
};

function formatDate(isoStr) {
    if (!isoStr) return '-';
    const d = new Date(isoStr);
    return d.toLocaleString('ko-KR', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function DecisionCard({ decision, isExpanded, onToggle }) {
    const style = STATUS_STYLES[decision.status] || STATUS_STYLES.PENDING;
    const Icon = style.icon;
    const hasPrevPnl = decision.previous_cycle_pnl != null;

    return (
        <div className={`${style.bg} border ${style.border} rounded-lg overflow-hidden`}>
            {/* Summary Row */}
            <button
                onClick={onToggle}
                className="w-full flex items-center gap-3 px-3 py-2.5 text-left hover:bg-white/5 transition-colors"
            >
                {/* Status Icon */}
                <Icon size={14} className={`${style.text} flex-shrink-0 ${decision.status === 'EXECUTING' ? 'animate-spin' : ''}`} />

                {/* Main Info */}
                <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                        <span className="text-xs font-medium text-white truncate">
                            {decision.chosen_symbol_name || decision.chosen_symbol || '결정 중...'}
                        </span>
                        {decision.chosen_symbol && (
                            <span className="text-[10px] text-gray-500">{decision.chosen_symbol}</span>
                        )}
                        {decision.chosen_score != null && (
                            <span className="text-[10px] px-1.5 py-0.5 bg-blue-500/20 text-blue-400 rounded">
                                Score {Math.round(decision.chosen_score)}
                            </span>
                        )}
                    </div>
                    <div className="flex items-center gap-2 mt-0.5">
                        <span className="text-[10px] text-gray-500">
                            {TRIGGER_LABELS[decision.trigger_type] || decision.trigger_type}
                        </span>
                        <span className="text-[10px] text-gray-600">|</span>
                        <span className="text-[10px] text-gray-500">
                            {formatDate(decision.created_at)}
                        </span>
                        {hasPrevPnl && (
                            <>
                                <span className="text-[10px] text-gray-600">|</span>
                                <span className={`text-[10px] flex items-center gap-0.5 ${
                                    decision.previous_cycle_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'
                                }`}>
                                    {decision.previous_cycle_pnl >= 0 ? <TrendingUp size={10} /> : <TrendingDown size={10} />}
                                    {decision.previous_cycle_pnl >= 0 ? '+' : ''}{decision.previous_cycle_pnl?.toLocaleString()}
                                </span>
                            </>
                        )}
                    </div>
                </div>

                {/* Status Badge */}
                <span className={`text-[10px] px-1.5 py-0.5 rounded ${style.bg} ${style.text}`}>
                    {style.label}
                </span>

                {/* Expand */}
                {isExpanded ? <ChevronUp size={12} className="text-gray-500" /> : <ChevronDown size={12} className="text-gray-500" />}
            </button>

            {/* Expanded Detail */}
            {isExpanded && (
                <div className="border-t border-white/5 px-3 py-2 space-y-2">
                    {/* Reasoning */}
                    {decision.chosen_reasoning && (
                        <div>
                            <div className="flex items-center gap-1 text-[10px] text-gray-400 mb-1">
                                <Brain size={10} /> AI 판단 근거
                            </div>
                            <p className="text-xs text-gray-300 leading-relaxed">
                                {decision.chosen_reasoning}
                            </p>
                        </div>
                    )}

                    {/* Chosen Params */}
                    {decision.chosen_params && (
                        <div>
                            <div className="flex items-center gap-1 text-[10px] text-gray-400 mb-1">
                                <BarChart3 size={10} /> 선택된 파라미터
                            </div>
                            <div className="flex flex-wrap gap-1">
                                {Object.entries(decision.chosen_params).map(([k, v]) => (
                                    <span key={k} className="px-1.5 py-0.5 bg-white/5 rounded text-[10px] text-gray-300">
                                        {k}: {typeof v === 'number' ? v.toFixed(2) : String(v)}
                                    </span>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Stock Candidates */}
                    {decision.stock_candidates && decision.stock_candidates.length > 0 && (
                        <div>
                            <div className="flex items-center gap-1 text-[10px] text-gray-400 mb-1">
                                <Target size={10} /> 후보 종목 ({decision.stock_candidates.length})
                            </div>
                            <div className="flex flex-wrap gap-1">
                                {decision.stock_candidates.map((c, i) => (
                                    <span key={i} className="px-1.5 py-0.5 bg-white/5 rounded text-[10px] text-gray-300">
                                        {c.name || c.code} <span className="text-gray-500">({c.score || '-'})</span>
                                    </span>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Pipeline Durations */}
                    <div className="flex items-center gap-3 text-[10px] text-gray-500">
                        {decision.stock_selection_duration_ms != null && (
                            <span>종목선정: {(decision.stock_selection_duration_ms / 1000).toFixed(1)}s</span>
                        )}
                        {decision.optimization_duration_ms != null && (
                            <span>최적화: {(decision.optimization_duration_ms / 1000).toFixed(1)}s</span>
                        )}
                        {decision.final_decision_duration_ms != null && (
                            <span>결정: {(decision.final_decision_duration_ms / 1000).toFixed(1)}s</span>
                        )}
                    </div>

                    {/* Error */}
                    {decision.error_message && (
                        <div className="bg-red-500/10 border border-red-500/20 rounded px-2 py-1 text-xs text-red-400">
                            {decision.error_message}
                        </div>
                    )}

                    {/* Previous session info */}
                    {decision.previous_symbol && (
                        <div className="text-[10px] text-gray-500">
                            이전: {decision.previous_symbol}
                            {decision.previous_session_id && ` (${decision.previous_session_id.slice(0, 8)}...)`}
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}

export default function AIDecisionTimeline({ decisions = [], loading = false }) {
    const [expandedId, setExpandedId] = useState(null);

    if (loading) {
        return (
            <div className="flex items-center justify-center py-8 text-gray-500">
                <Loader size={16} className="animate-spin mr-2" /> 결정 히스토리 로딩...
            </div>
        );
    }

    if (decisions.length === 0) {
        return (
            <div className="text-center py-8 text-gray-500 text-sm">
                <Clock size={20} className="mx-auto mb-2 opacity-50" />
                아직 AI 결정 기록이 없습니다
            </div>
        );
    }

    return (
        <div className="space-y-2">
            {decisions.map(d => (
                <DecisionCard
                    key={d.id}
                    decision={d}
                    isExpanded={expandedId === d.id}
                    onToggle={() => setExpandedId(expandedId === d.id ? null : d.id)}
                />
            ))}
        </div>
    );
}
