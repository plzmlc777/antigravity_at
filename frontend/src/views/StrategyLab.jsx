import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { getStrategyRequests, deleteStrategyRequest, activateStrategy } from '../api/client';
import DynamicParameterForm from '../components/DynamicParameterForm';
import {
    FlaskConical, Trash2, Edit3, X, AlertCircle, CheckCircle, Clock, Zap,
    TrendingUp, BarChart3, Layers, Play, Wrench, Bot, Send
} from 'lucide-react';
import StrategyLabChat from '../components/StrategyLabChat';

// ============================================================
// Constants
// ============================================================
const ENTRY_TYPES = [
    { value: 'price', label: 'Price Based', icon: TrendingUp, desc: 'Price movement triggers' },
    { value: 'time', label: 'Time Based', icon: Clock, desc: 'Specific time-based entry' },
    { value: 'indicator', label: 'Indicator Based', icon: BarChart3, desc: 'Technical indicators' },
    { value: 'composite', label: 'Composite', icon: Layers, desc: 'Multiple conditions' },
];

const INDICATORS = [
    { id: 'ma', label: 'Moving Average' },
    { id: 'rsi', label: 'RSI' },
    { id: 'macd', label: 'MACD' },
    { id: 'bollinger', label: 'Bollinger Bands' },
    { id: 'volume', label: 'Volume' },
    { id: 'vwap', label: 'VWAP' },
    { id: 'stochastic', label: 'Stochastic' },
    { id: 'other', label: 'Other' },
];

const STATUS_CONFIG = {
    draft: { label: 'Draft', color: 'bg-gray-500/20 text-gray-400', icon: Edit3 },
    submitted: { label: 'Submitted', color: 'bg-yellow-500/20 text-yellow-400', icon: Send },
    implemented: { label: 'Implemented', color: 'bg-emerald-500/20 text-emerald-400', icon: CheckCircle },
    active: { label: 'Active', color: 'bg-blue-500/20 text-blue-400', icon: Zap },
};

// ============================================================
// StatusBadge
// ============================================================
const StatusBadge = ({ status }) => {
    const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.draft;
    const Icon = cfg.icon;
    return (
        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${cfg.color}`}>
            <Icon size={12} /> {cfg.label}
        </span>
    );
};

// ============================================================
// Detail View (read-only, AI-only modification)
// ============================================================
const DetailView = ({ request, onActivate, onModifyWithAI }) => (
    <div className="space-y-4">
        <div className="flex items-center justify-between">
            <div>
                <h2 className="text-lg font-bold text-white">{request.name}</h2>
                <p className="text-xs text-gray-500">{request.description}</p>
            </div>
            <div className="flex items-center gap-2">
                <StatusBadge status={request.status} />
                {request.strategy_id && onModifyWithAI && (
                    <button
                        onClick={() => onModifyWithAI(request.strategy_id, request.name)}
                        className="flex items-center gap-1 px-2 py-1.5 bg-purple-500/10 hover:bg-purple-500/20 text-purple-400 rounded-lg text-xs font-medium transition-colors"
                        title="AI로 전략 수정"
                    >
                        <Wrench size={12} /> AI 수정
                    </button>
                )}
            </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
            <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5">
                <span className="text-[10px] text-gray-500 uppercase">Entry Type</span>
                <p className="text-sm text-white mt-1">{ENTRY_TYPES.find(e => e.value === request.entry_type)?.label || request.entry_type}</p>
            </div>
            <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5">
                <span className="text-[10px] text-gray-500 uppercase">Entry Mode</span>
                <p className="text-sm text-white mt-1">{request.entry_mode === 'single' ? 'Single Entry' : 'Multi-Level'}</p>
            </div>
        </div>

        <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5">
            <span className="text-[10px] text-gray-500 uppercase">Entry Condition</span>
            <p className="text-sm text-gray-300 mt-1 whitespace-pre-wrap">{request.entry_condition}</p>
        </div>

        {request.indicators?.length > 0 && (
            <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5">
                <span className="text-[10px] text-gray-500 uppercase">Indicators</span>
                <div className="flex flex-wrap gap-1 mt-1">
                    {request.indicators.map(ind => (
                        <span key={ind} className="text-xs px-2 py-0.5 rounded bg-purple-500/10 text-purple-400">
                            {INDICATORS.find(i => i.id === ind)?.label || ind}
                        </span>
                    ))}
                </div>
            </div>
        )}

        {request.additional_entry && (
            <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5">
                <span className="text-[10px] text-gray-500 uppercase">Additional Entry</span>
                <p className="text-sm text-gray-300 mt-1 whitespace-pre-wrap">{request.additional_entry}</p>
            </div>
        )}

        {request.exit_condition && (
            <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5">
                <span className="text-[10px] text-gray-500 uppercase">Special Exit Condition</span>
                <p className="text-sm text-gray-300 mt-1 whitespace-pre-wrap">{request.exit_condition}</p>
            </div>
        )}

        {request.custom_parameters?.length > 0 && (
            <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5">
                <span className="text-[10px] text-gray-500 uppercase">Custom Parameters</span>
                <div className="mt-1 space-y-1">
                    {request.custom_parameters.map((p, i) => (
                        <div key={i} className="flex items-center gap-2 text-xs">
                            <code className="text-blue-400">{p.name}</code>
                            <span className="text-gray-600">({p.type})</span>
                            <span className="text-gray-500">= {p.default}</span>
                            {p.description && <span className="text-gray-600">- {p.description}</span>}
                        </div>
                    ))}
                </div>
            </div>
        )}

        {request.notes && (
            <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5">
                <span className="text-[10px] text-gray-500 uppercase">Notes</span>
                <p className="text-sm text-gray-300 mt-1 whitespace-pre-wrap">{request.notes}</p>
            </div>
        )}

        {request.status === 'implemented' && request.strategy_id && (
            <div className="mt-6 p-4 rounded-lg bg-gradient-to-br from-emerald-500/10 to-blue-500/10 border border-emerald-500/30">
                <BacktestPanel
                    key={`${request.strategy_id}-${request.updated_at}`}
                    strategyId={request.strategy_id}
                    requestId={request.id}
                    onActivate={onActivate}
                />
            </div>
        )}
    </div>
);

// ============================================================
// BacktestPanel (for implemented strategies)
// ============================================================
const BacktestPanel = ({ strategyId, requestId, onActivate }) => {
    const [strategy, setStrategy] = useState(null);
    const [params, setParams] = useState({});
    const [config, setConfig] = useState({ symbol: '005930', interval: '1h', days: 90 });
    const [result, setResult] = useState(null);
    const [loading, setLoading] = useState(false);
    const [activating, setActivating] = useState(false);
    const [error, setError] = useState(null);

    useEffect(() => {
        const load = async () => {
            try {
                const res = await axios.get('/api/v1/strategies/list', { params: { status: 'testing' } });
                const found = res.data.find(s => s.id === strategyId);
                if (!found) {
                    const allRes = await axios.get('/api/v1/strategies/list', { params: { status: '' } });
                    const fallback = allRes.data.find(s => s.id === strategyId);
                    setStrategy(fallback || null);
                    if (fallback?.parameter_schema?.fields) {
                        const defaults = {};
                        fallback.parameter_schema.fields.forEach(f => { defaults[f.key || f.name] = f.default; });
                        setParams(defaults);
                    }
                } else {
                    setStrategy(found);
                    if (found.parameter_schema?.fields) {
                        const defaults = {};
                        found.parameter_schema.fields.forEach(f => { defaults[f.key || f.name] = f.default; });
                        setParams(defaults);
                    }
                }
            } catch (err) {
                setError('Failed to load strategy details');
            }
        };
        load();
    }, [strategyId]);

    const runBacktest = async () => {
        setLoading(true);
        setError(null);
        setResult(null);
        try {
            const res = await axios.post(`/api/v1/strategies/${strategyId}/backtest`, {
                symbol: config.symbol,
                interval: config.interval,
                days: config.days,
                initial_capital: 10000000,
                config: params
            });
            setResult(res.data);
        } catch (err) {
            setError(err.response?.data?.detail || 'Backtest failed');
        } finally {
            setLoading(false);
        }
    };

    const handleActivate = async () => {
        if (!confirm('Activate this strategy? It will appear in the Profiles page.')) return;
        setActivating(true);
        try {
            await activateStrategy(requestId);
            onActivate();
        } catch (err) {
            setError(err.response?.data?.detail || 'Activation failed');
        } finally {
            setActivating(false);
        }
    };

    return (
        <div className="space-y-4">
            <div className="flex items-center justify-between">
                <h3 className="text-sm font-bold text-emerald-400 flex items-center gap-2">
                    <CheckCircle size={16} /> Strategy Testing
                </h3>
                <button
                    onClick={handleActivate}
                    disabled={activating || !result}
                    title={!result ? 'Run a backtest first' : 'Activate strategy'}
                    className="flex items-center gap-1 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 disabled:bg-gray-700 disabled:opacity-50 text-white rounded-lg text-xs font-medium transition-colors"
                >
                    <Zap size={12} /> {activating ? 'Activating...' : 'Activate Strategy'}
                </button>
            </div>

            {strategy?.parameter_schema && (
                <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5">
                    <label className="block text-xs font-medium text-gray-400 mb-2">Strategy Parameters</label>
                    <DynamicParameterForm
                        schema={strategy.parameter_schema}
                        values={params}
                        onChange={(key, val) => setParams(prev => ({ ...prev, [key]: val }))}
                    />
                </div>
            )}

            <div className="grid grid-cols-3 gap-3">
                <div>
                    <label className="block text-xs font-medium text-gray-400 mb-1">Symbol</label>
                    <input
                        type="text" value={config.symbol}
                        onChange={e => setConfig(prev => ({ ...prev, symbol: e.target.value }))}
                        className="w-full px-2 py-1.5 bg-white/5 border border-white/10 rounded text-xs text-white focus:outline-none focus:border-blue-500/50"
                    />
                </div>
                <div>
                    <label className="block text-xs font-medium text-gray-400 mb-1">Interval</label>
                    <select
                        value={config.interval}
                        onChange={e => setConfig(prev => ({ ...prev, interval: e.target.value }))}
                        className="w-full px-2 py-1.5 bg-white/5 border border-white/10 rounded text-xs text-white focus:outline-none focus:border-blue-500/50"
                    >
                        <option value="1m">1m</option>
                        <option value="5m">5m</option>
                        <option value="1h">1h</option>
                        <option value="1d">1d</option>
                    </select>
                </div>
                <div>
                    <label className="block text-xs font-medium text-gray-400 mb-1">Days</label>
                    <input
                        type="number" value={config.days}
                        onChange={e => setConfig(prev => ({ ...prev, days: parseInt(e.target.value) || 90 }))}
                        className="w-full px-2 py-1.5 bg-white/5 border border-white/10 rounded text-xs text-white focus:outline-none focus:border-blue-500/50"
                    />
                </div>
            </div>

            <button
                onClick={runBacktest} disabled={loading}
                className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-colors"
            >
                <Play size={14} /> {loading ? 'Running Backtest...' : 'Run Backtest'}
            </button>

            {error && (
                <div className="flex items-center gap-2 p-2 bg-red-500/10 border border-red-500/20 rounded text-red-400 text-xs">
                    <AlertCircle size={12} /> {error}
                </div>
            )}

            {result && (
                <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5 space-y-3">
                    <h4 className="text-xs font-medium text-gray-400">Backtest Results</h4>
                    <div className="grid grid-cols-4 gap-3">
                        {[
                            { label: 'Return', value: `${(result.total_return || 0).toFixed(2)}%`,
                              color: (result.total_return || 0) >= 0 ? 'text-emerald-400' : 'text-red-400' },
                            { label: 'Win Rate', value: `${(result.win_rate || 0).toFixed(1)}%`, color: 'text-white' },
                            { label: 'Trades', value: result.total_trades || 0, color: 'text-white' },
                            { label: 'Max DD', value: `${(result.max_drawdown || 0).toFixed(2)}%`, color: 'text-orange-400' },
                        ].map(item => (
                            <div key={item.label}>
                                <span className="text-[10px] text-gray-500 block">{item.label}</span>
                                <span className={`text-sm font-medium ${item.color}`}>{item.value}</span>
                            </div>
                        ))}
                    </div>
                    <p className="text-xs text-emerald-400/70 mt-1">
                        Click "Activate Strategy" to make it available in Profiles.
                    </p>
                </div>
            )}
        </div>
    );
};

// ============================================================
// Main Component
// ============================================================
const StrategyLab = () => {
    const [requests, setRequests] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [selectedRequest, setSelectedRequest] = useState(null);

    // AI Chat prefill
    const [chatPrefill, setChatPrefill] = useState(null);

    // ========================================
    // Load requests
    // ========================================
    const loadRequests = useCallback(async () => {
        try {
            setLoading(true);
            const data = await getStrategyRequests();
            setRequests(data);
            setSelectedRequest(prev => {
                if (!prev) return prev;
                const updated = data.find(r => r.id === prev.id);
                return updated || prev;
            });
        } catch (err) {
            setError('Failed to load strategy requests');
            console.error(err);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { loadRequests(); }, [loadRequests]);

    // ========================================
    // Handlers
    // ========================================
    const handleSelectStrategy = (e) => {
        const id = e.target.value;
        if (!id) {
            setSelectedRequest(null);
        } else {
            const req = requests.find(r => r.id === id);
            setSelectedRequest(req || null);
        }
    };

    const handleDelete = async (id) => {
        if (!confirm('이 전략을 삭제하시겠습니까?')) return;
        try {
            await deleteStrategyRequest(id);
            if (selectedRequest?.id === id) {
                setSelectedRequest(null);
            }
            await loadRequests();
        } catch (err) {
            setError('Failed to delete');
        }
    };

    // ========================================
    // Render
    // ========================================
    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-purple-500/20 flex items-center justify-center">
                    <FlaskConical size={20} className="text-purple-400" />
                </div>
                <div>
                    <h1 className="text-xl font-bold text-white">Strategy Lab</h1>
                    <p className="text-xs text-gray-500">AI로 트레이딩 전략을 생성하고 관리하세요</p>
                </div>
            </div>

            {/* Error */}
            {error && (
                <div className="flex items-center gap-2 p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm">
                    <AlertCircle size={16} /> {error}
                    <button onClick={() => setError(null)} className="ml-auto"><X size={14} /></button>
                </div>
            )}

            <div className="grid grid-cols-12 gap-4">
                {/* Left: Strategy Content */}
                <div className="col-span-7">
                    <div className="bg-white/[0.02] border border-white/10 rounded-xl overflow-hidden flex flex-col" style={{ height: 'calc(100vh - 220px)' }}>
                        {/* Strategy Selector */}
                        <div className="flex items-center gap-2 px-4 py-3 border-b border-white/10 flex-shrink-0">
                            <select
                                value={selectedRequest?.id || ''}
                                onChange={handleSelectStrategy}
                                className="flex-1 px-3 py-2 bg-black/40 border border-white/20 rounded-lg text-white text-sm focus:border-purple-500 focus:ring-1 focus:ring-purple-500"
                            >
                                <option value="">+ 새 전략 만들기</option>
                                {requests.map(req => (
                                    <option key={req.id} value={req.id}>
                                        {req.name} ({STATUS_CONFIG[req.status]?.label || req.status})
                                    </option>
                                ))}
                            </select>
                            {selectedRequest && (
                                <button
                                    onClick={() => handleDelete(selectedRequest.id)}
                                    className="p-2 hover:bg-red-500/10 rounded-lg text-gray-500 hover:text-red-400 transition-colors"
                                    title="전략 삭제"
                                >
                                    <Trash2 size={14} />
                                </button>
                            )}
                        </div>

                        {/* Content */}
                        <div className="flex-1 overflow-y-auto p-5">
                            {loading ? (
                                <div className="flex items-center justify-center h-full">
                                    <div className="text-center text-gray-600 text-sm">Loading...</div>
                                </div>
                            ) : !selectedRequest ? (
                                <div className="flex items-center justify-center h-full">
                                    <div className="text-center">
                                        <Bot size={48} className="mx-auto text-purple-500/30 mb-4" />
                                        <p className="text-sm text-gray-400 mb-2">AI Strategy Builder로 새 전략을 만들어보세요</p>
                                        <p className="text-xs text-gray-600">
                                            오른쪽 채팅창에서 전략 아이디어를 설명하면
                                            <br />AI가 자동으로 전략 코드를 생성합니다
                                        </p>
                                    </div>
                                </div>
                            ) : (
                                <DetailView
                                    request={selectedRequest}
                                    onActivate={() => { loadRequests(); }}
                                    onModifyWithAI={(strategyId, name) => {
                                        setChatPrefill(`${strategyId} 전략을 수정해줘: `);
                                    }}
                                />
                            )}
                        </div>
                    </div>
                </div>

                {/* Right: AI Chat (always visible) */}
                <div className="col-span-5">
                    <div className="bg-white/[0.02] border border-white/10 rounded-xl overflow-hidden" style={{ height: 'calc(100vh - 220px)' }}>
                        <StrategyLabChat
                            onStrategyCreated={loadRequests}
                            prefillInput={chatPrefill}
                            onPrefillConsumed={() => setChatPrefill(null)}
                            selectedStrategy={selectedRequest ? {
                                strategyId: selectedRequest.strategy_id,
                                name: selectedRequest.name
                            } : null}
                        />
                    </div>
                </div>
            </div>
        </div>
    );
};

export default StrategyLab;
