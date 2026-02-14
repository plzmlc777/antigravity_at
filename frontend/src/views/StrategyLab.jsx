import React, { useState, useEffect, useCallback } from 'react';
import {
    getStrategyRequests, createStrategyRequest, updateStrategyRequest, deleteStrategyRequest
} from '../api/client';
import {
    Plus, FlaskConical, ChevronRight, ChevronLeft, Save, Send, Trash2,
    Edit3, Eye, X, AlertCircle, CheckCircle, Clock, Zap, TrendingUp,
    BarChart3, Activity, Layers
} from 'lucide-react';

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

const EMPTY_FORM = {
    name: '', description: '', entry_type: 'price', entry_condition: '',
    indicators: [], entry_mode: 'single', additional_entry: '', exit_condition: '',
    custom_parameters: [], default_overrides: {}, notes: '', status: 'draft',
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
// RequestCard
// ============================================================
const RequestCard = ({ request, isSelected, onSelect, onDelete }) => (
    <div
        onClick={() => onSelect(request)}
        className={`p-4 rounded-xl border cursor-pointer transition-all ${isSelected
            ? 'border-blue-500/50 bg-blue-500/5'
            : 'border-white/10 bg-white/[0.02] hover:border-white/20 hover:bg-white/[0.04]'
        }`}
    >
        <div className="flex items-start justify-between mb-2">
            <h3 className="font-semibold text-white text-sm truncate flex-1">{request.name}</h3>
            <StatusBadge status={request.status} />
        </div>
        {request.description && (
            <p className="text-xs text-gray-500 mb-2 line-clamp-2">{request.description}</p>
        )}
        <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/5 text-gray-400">
                {ENTRY_TYPES.find(e => e.value === request.entry_type)?.label || request.entry_type}
            </span>
            {(request.indicators || []).slice(0, 3).map(ind => (
                <span key={ind} className="text-[10px] px-1.5 py-0.5 rounded bg-purple-500/10 text-purple-400">
                    {INDICATORS.find(i => i.id === ind)?.label || ind}
                </span>
            ))}
        </div>
        <div className="flex items-center justify-between mt-2">
            <span className="text-[10px] text-gray-600">
                {request.created_at ? new Date(request.created_at).toLocaleDateString('ko-KR') : ''}
            </span>
            <button
                onClick={(e) => { e.stopPropagation(); onDelete(request.id); }}
                className="p-1 hover:bg-red-500/10 rounded text-gray-600 hover:text-red-400 transition-colors"
            >
                <Trash2 size={12} />
            </button>
        </div>
    </div>
);

// ============================================================
// Wizard Steps
// ============================================================
const StepBasicInfo = ({ form, setField }) => (
    <div className="space-y-4">
        <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">Strategy Name *</label>
            <input
                type="text" value={form.name} onChange={e => setField('name', e.target.value)}
                placeholder="e.g. Golden Cross Buy"
                className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-600 focus:outline-none focus:border-blue-500/50"
            />
        </div>
        <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">Description</label>
            <input
                type="text" value={form.description} onChange={e => setField('description', e.target.value)}
                placeholder="Brief one-line description"
                className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-600 focus:outline-none focus:border-blue-500/50"
            />
        </div>
    </div>
);

const StepEntryCondition = ({ form, setField }) => (
    <div className="space-y-4">
        <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">Entry Type</label>
            <div className="grid grid-cols-2 gap-2">
                {ENTRY_TYPES.map(et => {
                    const Icon = et.icon;
                    return (
                        <button
                            key={et.value}
                            onClick={() => setField('entry_type', et.value)}
                            className={`p-3 rounded-lg border text-left transition-all ${form.entry_type === et.value
                                ? 'border-blue-500/50 bg-blue-500/10'
                                : 'border-white/10 bg-white/[0.02] hover:border-white/20'
                            }`}
                        >
                            <div className="flex items-center gap-2 mb-1">
                                <Icon size={14} className={form.entry_type === et.value ? 'text-blue-400' : 'text-gray-500'} />
                                <span className="text-sm font-medium text-white">{et.label}</span>
                            </div>
                            <span className="text-[10px] text-gray-500">{et.desc}</span>
                        </button>
                    );
                })}
            </div>
        </div>
        <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">Entry Condition *</label>
            <textarea
                value={form.entry_condition} onChange={e => setField('entry_condition', e.target.value)}
                placeholder="Describe when to buy. e.g.: Buy when 5-day MA crosses above 20-day MA"
                rows={4}
                className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-600 focus:outline-none focus:border-blue-500/50 resize-none"
            />
        </div>
        <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">Indicators Used</label>
            <div className="flex flex-wrap gap-2">
                {INDICATORS.map(ind => {
                    const selected = (form.indicators || []).includes(ind.id);
                    return (
                        <button
                            key={ind.id}
                            onClick={() => {
                                const current = form.indicators || [];
                                setField('indicators', selected
                                    ? current.filter(i => i !== ind.id)
                                    : [...current, ind.id]
                                );
                            }}
                            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${selected
                                ? 'bg-purple-500/20 text-purple-300 border border-purple-500/30'
                                : 'bg-white/5 text-gray-400 border border-white/10 hover:border-white/20'
                            }`}
                        >
                            {ind.label}
                        </button>
                    );
                })}
            </div>
        </div>
    </div>
);

const StepEntryExit = ({ form, setField }) => (
    <div className="space-y-4">
        <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">Entry Mode</label>
            <div className="flex gap-3">
                {[
                    { value: 'single', label: 'Single Entry', desc: 'One buy, max_buy_count=1' },
                    { value: 'multi', label: 'Multi-Level', desc: 'Averaging down (martingale)' },
                ].map(opt => (
                    <button
                        key={opt.value}
                        onClick={() => setField('entry_mode', opt.value)}
                        className={`flex-1 p-3 rounded-lg border text-left transition-all ${form.entry_mode === opt.value
                            ? 'border-blue-500/50 bg-blue-500/10'
                            : 'border-white/10 bg-white/[0.02] hover:border-white/20'
                        }`}
                    >
                        <span className="text-sm font-medium text-white">{opt.label}</span>
                        <p className="text-[10px] text-gray-500 mt-0.5">{opt.desc}</p>
                    </button>
                ))}
            </div>
        </div>
        {form.entry_mode === 'multi' && (
            <div>
                <label className="block text-sm font-medium text-gray-300 mb-1">Additional Entry Condition</label>
                <textarea
                    value={form.additional_entry} onChange={e => setField('additional_entry', e.target.value)}
                    placeholder="e.g.: Buy again when price drops 2% from last entry"
                    rows={3}
                    className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-600 focus:outline-none focus:border-blue-500/50 resize-none"
                />
            </div>
        )}
        <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">Special Exit Condition</label>
            <textarea
                value={form.exit_condition} onChange={e => setField('exit_condition', e.target.value)}
                placeholder="Leave empty for default trailing stop / stop loss. e.g.: Force sell at 15:00"
                rows={3}
                className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-600 focus:outline-none focus:border-blue-500/50 resize-none"
            />
        </div>
    </div>
);

const StepParameters = ({ form, setField }) => {
    const params = form.custom_parameters || [];

    const addParam = () => {
        setField('custom_parameters', [...params, { name: '', type: 'number', default: '', description: '' }]);
    };
    const removeParam = (idx) => {
        setField('custom_parameters', params.filter((_, i) => i !== idx));
    };
    const updateParam = (idx, key, value) => {
        const updated = params.map((p, i) => i === idx ? { ...p, [key]: value } : p);
        setField('custom_parameters', updated);
    };

    return (
        <div className="space-y-4">
            <div className="flex items-center justify-between">
                <label className="text-sm font-medium text-gray-300">Custom Parameters</label>
                <button
                    onClick={addParam}
                    className="flex items-center gap-1 px-2 py-1 text-xs text-blue-400 hover:bg-blue-500/10 rounded-lg transition-colors"
                >
                    <Plus size={12} /> Add Parameter
                </button>
            </div>
            {params.length === 0 && (
                <p className="text-xs text-gray-600 italic">No custom parameters. Common parameters (trailing stop, stop loss, etc.) are included automatically.</p>
            )}
            {params.map((p, idx) => (
                <div key={idx} className="grid grid-cols-12 gap-2 items-start">
                    <input
                        value={p.name} onChange={e => updateParam(idx, 'name', e.target.value)}
                        placeholder="name" className="col-span-3 px-2 py-1.5 bg-white/5 border border-white/10 rounded text-xs text-white placeholder-gray-600 focus:outline-none focus:border-blue-500/50"
                    />
                    <select
                        value={p.type} onChange={e => updateParam(idx, 'type', e.target.value)}
                        className="col-span-2 px-2 py-1.5 bg-white/5 border border-white/10 rounded text-xs text-white focus:outline-none focus:border-blue-500/50"
                    >
                        <option value="number">Number</option>
                        <option value="select">Select</option>
                        <option value="time">Time</option>
                    </select>
                    <input
                        value={p.default} onChange={e => updateParam(idx, 'default', e.target.value)}
                        placeholder="default" className="col-span-2 px-2 py-1.5 bg-white/5 border border-white/10 rounded text-xs text-white placeholder-gray-600 focus:outline-none focus:border-blue-500/50"
                    />
                    <input
                        value={p.description} onChange={e => updateParam(idx, 'description', e.target.value)}
                        placeholder="description" className="col-span-4 px-2 py-1.5 bg-white/5 border border-white/10 rounded text-xs text-white placeholder-gray-600 focus:outline-none focus:border-blue-500/50"
                    />
                    <button onClick={() => removeParam(idx)} className="col-span-1 p-1.5 hover:bg-red-500/10 rounded text-gray-500 hover:text-red-400">
                        <X size={14} />
                    </button>
                </div>
            ))}
        </div>
    );
};

const StepNotes = ({ form, setField }) => (
    <div className="space-y-4">
        <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">Notes & References</label>
            <textarea
                value={form.notes} onChange={e => setField('notes', e.target.value)}
                placeholder="Additional details, reference URLs, edge cases, etc."
                rows={6}
                className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-600 focus:outline-none focus:border-blue-500/50 resize-none"
            />
        </div>
    </div>
);

const STEPS = [
    { title: 'Basic Info', component: StepBasicInfo },
    { title: 'Entry Condition', component: StepEntryCondition },
    { title: 'Entry & Exit', component: StepEntryExit },
    { title: 'Parameters', component: StepParameters },
    { title: 'Notes & Submit', component: StepNotes },
];

// ============================================================
// Detail View (read-only)
// ============================================================
const DetailView = ({ request, onEdit, onClose }) => (
    <div className="space-y-4">
        <div className="flex items-center justify-between">
            <div>
                <h2 className="text-lg font-bold text-white">{request.name}</h2>
                <p className="text-xs text-gray-500">{request.description}</p>
            </div>
            <div className="flex items-center gap-2">
                <StatusBadge status={request.status} />
                {(request.status === 'draft' || request.status === 'submitted') && (
                    <button onClick={onEdit} className="p-2 hover:bg-white/5 rounded-lg text-gray-400 hover:text-white">
                        <Edit3 size={16} />
                    </button>
                )}
                <button onClick={onClose} className="p-2 hover:bg-white/5 rounded-lg text-gray-400 hover:text-white">
                    <X size={16} />
                </button>
            </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
            <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5">
                <span className="text-[10px] text-gray-500 uppercase">Entry Type</span>
                <p className="text-sm text-white mt-1">{ENTRY_TYPES.find(e => e.value === request.entry_type)?.label}</p>
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
    </div>
);

// ============================================================
// Main Component
// ============================================================
const StrategyLab = () => {
    const [requests, setRequests] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    // Modes: 'list' | 'detail' | 'wizard'
    const [mode, setMode] = useState('list');
    const [selectedRequest, setSelectedRequest] = useState(null);
    const [editingId, setEditingId] = useState(null); // null = new, string = editing existing

    // Wizard state
    const [step, setStep] = useState(0);
    const [form, setForm] = useState({ ...EMPTY_FORM });
    const [saving, setSaving] = useState(false);

    // ========================================
    // Load requests
    // ========================================
    const loadRequests = useCallback(async () => {
        try {
            setLoading(true);
            const data = await getStrategyRequests();
            setRequests(data);
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
    const setField = useCallback((key, value) => {
        setForm(prev => ({ ...prev, [key]: value }));
    }, []);

    const startNewWizard = () => {
        setForm({ ...EMPTY_FORM });
        setEditingId(null);
        setStep(0);
        setMode('wizard');
    };

    const startEditWizard = (request) => {
        setForm({
            name: request.name || '',
            description: request.description || '',
            entry_type: request.entry_type || 'price',
            entry_condition: request.entry_condition || '',
            indicators: request.indicators || [],
            entry_mode: request.entry_mode || 'single',
            additional_entry: request.additional_entry || '',
            exit_condition: request.exit_condition || '',
            custom_parameters: request.custom_parameters || [],
            default_overrides: request.default_overrides || {},
            notes: request.notes || '',
            status: request.status || 'draft',
        });
        setEditingId(request.id);
        setStep(0);
        setMode('wizard');
    };

    const selectRequest = (req) => {
        setSelectedRequest(req);
        setMode('detail');
    };

    const handleSave = async (targetStatus) => {
        if (!form.name.trim() || !form.entry_condition.trim()) {
            setError('Name and Entry Condition are required');
            return;
        }
        setSaving(true);
        setError(null);
        try {
            const payload = { ...form, status: targetStatus };
            if (editingId) {
                await updateStrategyRequest(editingId, payload);
            } else {
                await createStrategyRequest(payload);
            }
            await loadRequests();
            setMode('list');
            setSelectedRequest(null);
        } catch (err) {
            setError(err.response?.data?.detail || 'Failed to save');
        } finally {
            setSaving(false);
        }
    };

    const handleDelete = async (id) => {
        if (!confirm('Delete this strategy request?')) return;
        try {
            await deleteStrategyRequest(id);
            if (selectedRequest?.id === id) {
                setSelectedRequest(null);
                setMode('list');
            }
            await loadRequests();
        } catch (err) {
            setError('Failed to delete');
        }
    };

    // ========================================
    // Render
    // ========================================
    const StepComponent = STEPS[step]?.component;

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-purple-500/20 flex items-center justify-center">
                        <FlaskConical size={20} className="text-purple-400" />
                    </div>
                    <div>
                        <h1 className="text-xl font-bold text-white">Strategy Lab</h1>
                        <p className="text-xs text-gray-500">Design your trading strategy ideas</p>
                    </div>
                </div>
                <button
                    onClick={startNewWizard}
                    className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-500 text-white rounded-lg text-sm font-medium transition-colors"
                >
                    <Plus size={16} /> New Strategy
                </button>
            </div>

            {/* Error */}
            {error && (
                <div className="flex items-center gap-2 p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm">
                    <AlertCircle size={16} /> {error}
                    <button onClick={() => setError(null)} className="ml-auto"><X size={14} /></button>
                </div>
            )}

            <div className="grid grid-cols-12 gap-6">
                {/* Left: Request List */}
                <div className="col-span-4 space-y-3">
                    <div className="flex items-center justify-between">
                        <h2 className="text-sm font-medium text-gray-400">
                            My Requests ({requests.length})
                        </h2>
                    </div>

                    {loading ? (
                        <div className="text-center py-8 text-gray-600 text-sm">Loading...</div>
                    ) : requests.length === 0 ? (
                        <div className="text-center py-12 border border-dashed border-white/10 rounded-xl">
                            <FlaskConical size={32} className="mx-auto text-gray-700 mb-2" />
                            <p className="text-sm text-gray-500">No strategy requests yet</p>
                            <p className="text-xs text-gray-600 mt-1">Click "New Strategy" to create one</p>
                        </div>
                    ) : (
                        <div className="space-y-2 max-h-[calc(100vh-280px)] overflow-y-auto pr-1">
                            {requests.map(req => (
                                <RequestCard
                                    key={req.id}
                                    request={req}
                                    isSelected={selectedRequest?.id === req.id}
                                    onSelect={selectRequest}
                                    onDelete={handleDelete}
                                />
                            ))}
                        </div>
                    )}
                </div>

                {/* Right: Detail or Wizard */}
                <div className="col-span-8">
                    {mode === 'list' && (
                        <div className="flex items-center justify-center h-64 border border-dashed border-white/10 rounded-xl">
                            <div className="text-center">
                                <Eye size={32} className="mx-auto text-gray-700 mb-2" />
                                <p className="text-sm text-gray-500">Select a request to view details</p>
                                <p className="text-xs text-gray-600">or create a new strategy</p>
                            </div>
                        </div>
                    )}

                    {mode === 'detail' && selectedRequest && (
                        <div className="p-6 bg-white/[0.02] border border-white/10 rounded-xl">
                            <DetailView
                                request={selectedRequest}
                                onEdit={() => startEditWizard(selectedRequest)}
                                onClose={() => { setMode('list'); setSelectedRequest(null); }}
                            />
                        </div>
                    )}

                    {mode === 'wizard' && (
                        <div className="p-6 bg-white/[0.02] border border-white/10 rounded-xl space-y-6">
                            {/* Wizard Header */}
                            <div className="flex items-center justify-between">
                                <h2 className="text-lg font-bold text-white">
                                    {editingId ? 'Edit Strategy Request' : 'New Strategy Request'}
                                </h2>
                                <button
                                    onClick={() => setMode('list')}
                                    className="p-2 hover:bg-white/5 rounded-lg text-gray-400 hover:text-white"
                                >
                                    <X size={18} />
                                </button>
                            </div>

                            {/* Progress */}
                            <div className="flex items-center gap-1">
                                {STEPS.map((s, i) => (
                                    <React.Fragment key={i}>
                                        <button
                                            onClick={() => setStep(i)}
                                            className={`px-3 py-1 rounded-full text-xs font-medium transition-all ${i === step
                                                ? 'bg-purple-500/20 text-purple-300'
                                                : i < step
                                                    ? 'bg-emerald-500/10 text-emerald-400'
                                                    : 'bg-white/5 text-gray-500'
                                            }`}
                                        >
                                            {i + 1}. {s.title}
                                        </button>
                                        {i < STEPS.length - 1 && <div className="flex-1 h-px bg-white/5" />}
                                    </React.Fragment>
                                ))}
                            </div>

                            {/* Step Content */}
                            <div className="min-h-[300px]">
                                {StepComponent && <StepComponent form={form} setField={setField} />}
                            </div>

                            {/* Navigation */}
                            <div className="flex items-center justify-between pt-4 border-t border-white/5">
                                <button
                                    onClick={() => setStep(Math.max(0, step - 1))}
                                    disabled={step === 0}
                                    className="flex items-center gap-1 px-4 py-2 text-sm text-gray-400 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                                >
                                    <ChevronLeft size={16} /> Back
                                </button>

                                <div className="flex items-center gap-2">
                                    {step === STEPS.length - 1 ? (
                                        <>
                                            <button
                                                onClick={() => handleSave('draft')}
                                                disabled={saving}
                                                className="flex items-center gap-1 px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
                                            >
                                                <Save size={14} /> {saving ? 'Saving...' : 'Save Draft'}
                                            </button>
                                            <button
                                                onClick={() => handleSave('submitted')}
                                                disabled={saving}
                                                className="flex items-center gap-1 px-4 py-2 bg-purple-600 hover:bg-purple-500 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
                                            >
                                                <Send size={14} /> {saving ? 'Saving...' : 'Submit'}
                                            </button>
                                        </>
                                    ) : (
                                        <button
                                            onClick={() => setStep(Math.min(STEPS.length - 1, step + 1))}
                                            className="flex items-center gap-1 px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors"
                                        >
                                            Next <ChevronRight size={16} />
                                        </button>
                                    )}
                                </div>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};

export default StrategyLab;
