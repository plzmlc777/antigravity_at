import { useState, useEffect } from 'react';
import { Save, Play, Square, Zap, Settings, Target, BarChart3, Shield, ChevronDown, ChevronUp } from 'lucide-react';
import { DEFAULT_INITIAL_CAPITAL } from '../constants/exchanges';

const STOCK_SOURCE_MODES = [
    { value: 'FIXED', label: '고정 종목', desc: '지정된 종목만 사용' },
    { value: 'CANDIDATE_LIST', label: '후보 종목', desc: 'AI가 후보 중 선택' },
    { value: 'AI_AUTO_SEARCH', label: 'AI 자동 탐색', desc: 'AI가 랭킹 기반 탐색' },
];

const APPROVAL_MODES = [
    { value: 'AUTO', label: '자동 실행' },
    { value: 'MANUAL', label: '수동 승인' },
];

const DEFAULT_FORM = {
    name: '',
    description: '',
    strategy_name: '',
    stock_source_mode: 'AI_AUTO_SEARCH',
    fixed_symbols: [],
    candidate_symbols: [],
    search_conditions: '',
    param_ranges: null,
    fixed_params: null,
    backtest_days: 30,
    backtest_interval: '1m',
    optimization_top_n: 5,
    max_optimization_combos: 500,
    approval_mode: 'AUTO',
    account_id: null,
    initial_capital: DEFAULT_INITIAL_CAPITAL,
    is_paper: true,
    max_consecutive_losses: 5,
    cooldown_minutes: 0,
};

export default function AIProfileForm({
    profile = null,
    strategies = [],
    accounts = [],
    onSave,
    onStart,
    onStop,
    onTrigger,
    saving = false,
    running = false,
}) {
    const [form, setForm] = useState(DEFAULT_FORM);
    const [showAdvanced, setShowAdvanced] = useState(false);
    const [symbolInput, setSymbolInput] = useState('');

    const isEditing = !!profile;
    const isRunning = profile?.is_running;

    useEffect(() => {
        if (profile) {
            setForm({
                name: profile.name || '',
                description: profile.description || '',
                strategy_name: profile.strategy_name || '',
                stock_source_mode: profile.stock_source_mode || 'AI_AUTO_SEARCH',
                fixed_symbols: profile.fixed_symbols || [],
                candidate_symbols: profile.candidate_symbols || [],
                search_conditions: profile.search_conditions || '',
                param_ranges: profile.param_ranges,
                fixed_params: profile.fixed_params,
                backtest_days: profile.backtest_days ?? 30,
                backtest_interval: profile.backtest_interval || '1m',
                optimization_top_n: profile.optimization_top_n ?? 5,
                max_optimization_combos: profile.max_optimization_combos ?? 500,
                approval_mode: profile.approval_mode || 'AUTO',
                account_id: profile.account_id,
                initial_capital: profile.initial_capital ?? DEFAULT_INITIAL_CAPITAL,
                is_paper: profile.is_paper ?? true,
                max_consecutive_losses: profile.max_consecutive_losses ?? 5,
                cooldown_minutes: profile.cooldown_minutes ?? 0,
            });
        } else {
            setForm(DEFAULT_FORM);
        }
    }, [profile]);

    const set = (key, value) => setForm(prev => ({ ...prev, [key]: value }));

    const handleSave = () => {
        if (!form.name.trim() || !form.strategy_name) return;
        onSave?.(form);
    };

    const addSymbol = (listKey) => {
        const trimmed = symbolInput.trim();
        if (!trimmed) return;
        const parts = trimmed.split(/[,\s]+/).filter(Boolean);
        const newSymbols = parts.map(code => ({ code: code.trim(), name: '' }));
        set(listKey, [...(form[listKey] || []), ...newSymbols]);
        setSymbolInput('');
    };

    const removeSymbol = (listKey, idx) => {
        set(listKey, form[listKey].filter((_, i) => i !== idx));
    };

    return (
        <div className="space-y-4">
            {/* Header with action buttons */}
            <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-white">
                    {isEditing ? '프로필 설정' : '새 AI 프로필'}
                </h3>
                <div className="flex gap-2">
                    {isEditing && (
                        <>
                            {isRunning ? (
                                <button
                                    onClick={() => onStop?.(profile.id)}
                                    className="flex items-center gap-1 px-3 py-1.5 bg-red-500/20 text-red-400 rounded-lg text-xs hover:bg-red-500/30 transition-colors"
                                >
                                    <Square size={12} /> Stop
                                </button>
                            ) : (
                                <button
                                    onClick={() => onStart?.(profile.id)}
                                    disabled={running}
                                    className="flex items-center gap-1 px-3 py-1.5 bg-emerald-500/20 text-emerald-400 rounded-lg text-xs hover:bg-emerald-500/30 transition-colors disabled:opacity-50"
                                >
                                    <Play size={12} /> Start
                                </button>
                            )}
                            <button
                                onClick={() => onTrigger?.(profile.id)}
                                disabled={!isRunning || running}
                                className="flex items-center gap-1 px-3 py-1.5 bg-yellow-500/20 text-yellow-400 rounded-lg text-xs hover:bg-yellow-500/30 transition-colors disabled:opacity-50"
                            >
                                <Zap size={12} /> Trigger
                            </button>
                        </>
                    )}
                </div>
            </div>

            {/* Name & Description */}
            <div className="space-y-2">
                <input
                    type="text"
                    placeholder="프로필 이름 (예: AI 공격적 매매)"
                    value={form.name}
                    onChange={e => set('name', e.target.value)}
                    disabled={isRunning}
                    className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 disabled:opacity-50"
                />
                <input
                    type="text"
                    placeholder="설명 (선택)"
                    value={form.description}
                    onChange={e => set('description', e.target.value)}
                    disabled={isRunning}
                    className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 disabled:opacity-50"
                />
            </div>

            {/* Strategy Selection */}
            <div>
                <label className="text-xs text-gray-400 mb-1 block">
                    <Settings size={12} className="inline mr-1" />전략
                </label>
                <select
                    value={form.strategy_name}
                    onChange={e => set('strategy_name', e.target.value)}
                    disabled={isRunning}
                    className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500 disabled:opacity-50"
                >
                    <option value="">전략 선택...</option>
                    {strategies.map(s => (
                        <option key={s.id} value={s.id}>{s.display_name || s.id}</option>
                    ))}
                </select>
            </div>

            {/* Stock Source Mode */}
            <div>
                <label className="text-xs text-gray-400 mb-1 block">
                    <Target size={12} className="inline mr-1" />종목 소스
                </label>
                <div className="grid grid-cols-3 gap-1">
                    {STOCK_SOURCE_MODES.map(mode => (
                        <button
                            key={mode.value}
                            onClick={() => set('stock_source_mode', mode.value)}
                            disabled={isRunning}
                            className={`px-2 py-1.5 rounded-lg text-xs transition-colors ${
                                form.stock_source_mode === mode.value
                                    ? 'bg-blue-600 text-white'
                                    : 'bg-white/5 text-gray-400 hover:bg-white/10'
                            } disabled:opacity-50`}
                        >
                            {mode.label}
                        </button>
                    ))}
                </div>
                <p className="text-[10px] text-gray-500 mt-1">
                    {STOCK_SOURCE_MODES.find(m => m.value === form.stock_source_mode)?.desc}
                </p>
            </div>

            {/* Conditional: Fixed/Candidate Symbols */}
            {(form.stock_source_mode === 'FIXED' || form.stock_source_mode === 'CANDIDATE_LIST') && (
                <div>
                    <label className="text-xs text-gray-400 mb-1 block">
                        {form.stock_source_mode === 'FIXED' ? '고정 종목' : '후보 종목'}
                    </label>
                    <div className="flex gap-1 mb-1">
                        <input
                            type="text"
                            placeholder="종목코드 (예: 005930)"
                            value={symbolInput}
                            onChange={e => setSymbolInput(e.target.value)}
                            onKeyDown={e => e.key === 'Enter' && addSymbol(
                                form.stock_source_mode === 'FIXED' ? 'fixed_symbols' : 'candidate_symbols'
                            )}
                            disabled={isRunning}
                            className="flex-1 bg-white/5 border border-white/10 rounded-lg px-3 py-1.5 text-xs text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 disabled:opacity-50"
                        />
                        <button
                            onClick={() => addSymbol(
                                form.stock_source_mode === 'FIXED' ? 'fixed_symbols' : 'candidate_symbols'
                            )}
                            disabled={isRunning}
                            className="px-3 py-1.5 bg-blue-600/20 text-blue-400 rounded-lg text-xs hover:bg-blue-600/30 disabled:opacity-50"
                        >
                            추가
                        </button>
                    </div>
                    <div className="flex flex-wrap gap-1">
                        {(form.stock_source_mode === 'FIXED' ? form.fixed_symbols : form.candidate_symbols)?.map((s, i) => (
                            <span key={i} className="flex items-center gap-1 px-2 py-0.5 bg-white/5 rounded text-xs text-gray-300">
                                {s.code}{s.name ? ` ${s.name}` : ''}
                                <button
                                    onClick={() => removeSymbol(
                                        form.stock_source_mode === 'FIXED' ? 'fixed_symbols' : 'candidate_symbols', i
                                    )}
                                    disabled={isRunning}
                                    className="text-gray-500 hover:text-red-400 disabled:opacity-50"
                                >
                                    ×
                                </button>
                            </span>
                        ))}
                    </div>
                </div>
            )}

            {/* Conditional: AI Search Conditions */}
            {form.stock_source_mode === 'AI_AUTO_SEARCH' && (
                <div>
                    <label className="text-xs text-gray-400 mb-1 block">AI 탐색 조건</label>
                    <textarea
                        placeholder="예: 거래량 상위 + 외인 순매수 + 시가총액 1조 이상"
                        value={form.search_conditions}
                        onChange={e => set('search_conditions', e.target.value)}
                        disabled={isRunning}
                        rows={2}
                        className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-xs text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 disabled:opacity-50 resize-none"
                    />
                </div>
            )}

            {/* Backtest Settings */}
            <div>
                <label className="text-xs text-gray-400 mb-1 block">
                    <BarChart3 size={12} className="inline mr-1" />백테스트 설정
                </label>
                <div className="grid grid-cols-2 gap-2">
                    <div>
                        <span className="text-[10px] text-gray-500">기간 (일)</span>
                        <input
                            type="number"
                            value={form.backtest_days}
                            onChange={e => set('backtest_days', parseInt(e.target.value) || 30)}
                            disabled={isRunning}
                            className="w-full bg-white/5 border border-white/10 rounded-lg px-2 py-1.5 text-xs text-white focus:outline-none focus:border-blue-500 disabled:opacity-50"
                        />
                    </div>
                    <div>
                        <span className="text-[10px] text-gray-500">인터벌</span>
                        <select
                            value={form.backtest_interval}
                            onChange={e => set('backtest_interval', e.target.value)}
                            disabled={isRunning}
                            className="w-full bg-white/5 border border-white/10 rounded-lg px-2 py-1.5 text-xs text-white focus:outline-none focus:border-blue-500 disabled:opacity-50"
                        >
                            <option value="1m">1분</option>
                            <option value="5m">5분</option>
                            <option value="30m">30분</option>
                            <option value="1h">1시간</option>
                        </select>
                    </div>
                </div>
            </div>

            {/* Execution Settings */}
            <div className="grid grid-cols-2 gap-2">
                <div>
                    <span className="text-[10px] text-gray-500">계좌</span>
                    <select
                        value={form.account_id || ''}
                        onChange={e => set('account_id', e.target.value ? parseInt(e.target.value) : null)}
                        disabled={isRunning}
                        className="w-full bg-white/5 border border-white/10 rounded-lg px-2 py-1.5 text-xs text-white focus:outline-none focus:border-blue-500 disabled:opacity-50"
                    >
                        <option value="">계좌 선택...</option>
                        {accounts.map(a => (
                            <option key={a.id} value={a.id}>{a.name || `계좌 ${a.id}`}</option>
                        ))}
                    </select>
                </div>
                <div>
                    <span className="text-[10px] text-gray-500">초기 자본</span>
                    <input
                        type="number"
                        value={form.initial_capital}
                        onChange={e => set('initial_capital', parseFloat(e.target.value) || DEFAULT_INITIAL_CAPITAL)}
                        disabled={isRunning}
                        className="w-full bg-white/5 border border-white/10 rounded-lg px-2 py-1.5 text-xs text-white focus:outline-none focus:border-blue-500 disabled:opacity-50"
                    />
                </div>
            </div>

            {/* Paper/Real Toggle */}
            <div className="flex items-center gap-3">
                <label className="flex items-center gap-2 cursor-pointer">
                    <input
                        type="checkbox"
                        checked={form.is_paper}
                        onChange={e => set('is_paper', e.target.checked)}
                        disabled={isRunning}
                        className="rounded"
                    />
                    <span className="text-xs text-gray-300">모의 투자</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                    <span className="text-xs text-gray-400">실행 모드:</span>
                    {APPROVAL_MODES.map(m => (
                        <button
                            key={m.value}
                            onClick={() => set('approval_mode', m.value)}
                            disabled={isRunning}
                            className={`px-2 py-0.5 rounded text-[10px] ${
                                form.approval_mode === m.value
                                    ? 'bg-blue-600 text-white'
                                    : 'bg-white/5 text-gray-400'
                            } disabled:opacity-50`}
                        >
                            {m.label}
                        </button>
                    ))}
                </label>
            </div>

            {/* Advanced Settings Toggle */}
            <button
                onClick={() => setShowAdvanced(!showAdvanced)}
                className="flex items-center gap-1 text-xs text-gray-400 hover:text-white transition-colors"
            >
                <Shield size={12} />
                고급 설정
                {showAdvanced ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
            </button>

            {showAdvanced && (
                <div className="space-y-2 bg-white/5 rounded-lg p-3">
                    <div className="grid grid-cols-2 gap-2">
                        <div>
                            <span className="text-[10px] text-gray-500">최적화 Top N</span>
                            <input
                                type="number"
                                value={form.optimization_top_n}
                                onChange={e => set('optimization_top_n', parseInt(e.target.value) || 5)}
                                disabled={isRunning}
                                className="w-full bg-white/5 border border-white/10 rounded-lg px-2 py-1.5 text-xs text-white focus:outline-none focus:border-blue-500 disabled:opacity-50"
                            />
                        </div>
                        <div>
                            <span className="text-[10px] text-gray-500">최대 조합 수</span>
                            <input
                                type="number"
                                value={form.max_optimization_combos}
                                onChange={e => set('max_optimization_combos', parseInt(e.target.value) || 500)}
                                disabled={isRunning}
                                className="w-full bg-white/5 border border-white/10 rounded-lg px-2 py-1.5 text-xs text-white focus:outline-none focus:border-blue-500 disabled:opacity-50"
                            />
                        </div>
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                        <div>
                            <span className="text-[10px] text-gray-500">연속 손실 한도</span>
                            <input
                                type="number"
                                value={form.max_consecutive_losses}
                                onChange={e => set('max_consecutive_losses', parseInt(e.target.value) || 5)}
                                disabled={isRunning}
                                className="w-full bg-white/5 border border-white/10 rounded-lg px-2 py-1.5 text-xs text-white focus:outline-none focus:border-blue-500 disabled:opacity-50"
                            />
                        </div>
                        <div>
                            <span className="text-[10px] text-gray-500">쿨다운 (분)</span>
                            <input
                                type="number"
                                value={form.cooldown_minutes}
                                onChange={e => set('cooldown_minutes', parseInt(e.target.value) || 0)}
                                disabled={isRunning}
                                className="w-full bg-white/5 border border-white/10 rounded-lg px-2 py-1.5 text-xs text-white focus:outline-none focus:border-blue-500 disabled:opacity-50"
                            />
                        </div>
                    </div>
                </div>
            )}

            {/* Save Button */}
            <button
                onClick={handleSave}
                disabled={!form.name.trim() || !form.strategy_name || saving || isRunning}
                className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
                <Save size={14} />
                {saving ? '저장 중...' : isEditing ? '프로필 저장' : '프로필 생성'}
            </button>

            {/* Running Status */}
            {isRunning && (
                <div className="bg-emerald-500/10 border border-emerald-500/30 rounded-lg px-3 py-2 text-xs text-emerald-400">
                    AI 트레이딩 실행 중 — 종목: {profile.current_symbol || '결정 중...'} / 사이클: #{profile.cycles_completed || 0}
                </div>
            )}
        </div>
    );
}
