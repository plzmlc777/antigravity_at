// Strategy Audition Dashboard — SAS Phase 4 (CIO-20260408-015).
// READ-ONLY. No buttons, no manual controls. User is supervisor, AI is operator.
// Displays: audition pool, category distribution, last winners, graveyard summary.
import { useEffect, useState } from 'react';
import { fetchAuditionList, fetchAuditionStats, fetchGraveyardStats, fetchStageStats } from '../api/audition';

const STATUS_COLORS = {
    audition: 'bg-blue-500/20 text-blue-300 border-blue-500/40',
    graduated: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40',
    eliminated: 'bg-red-500/20 text-red-300 border-red-500/40',
    resurrected: 'bg-amber-500/20 text-amber-300 border-amber-500/40',
    error: 'bg-gray-500/20 text-gray-300 border-gray-500/40',
};

// SISDS Phase 1 stage colors (CIO-017)
const STAGE_COLORS = {
    birth:   { bg: 'bg-cyan-500/15',    border: 'border-cyan-500/40',    text: 'text-cyan-300',    icon: '🌱' },
    sandbox: { bg: 'bg-violet-500/15',  border: 'border-violet-500/40',  text: 'text-violet-300',  icon: '🧪' },
    paper:   { bg: 'bg-blue-500/15',    border: 'border-blue-500/40',    text: 'text-blue-300',    icon: '📄' },
    live:    { bg: 'bg-emerald-500/15', border: 'border-emerald-500/40', text: 'text-emerald-300', icon: '💹' },
    retired: { bg: 'bg-red-500/15',     border: 'border-red-500/40',     text: 'text-red-300',     icon: '⚰️' },
    legacy:  { bg: 'bg-gray-500/15',    border: 'border-gray-500/40',    text: 'text-gray-300',    icon: '📜' },
};

function StageBadge({ stage, stage_status }) {
    const c = STAGE_COLORS[stage] || STAGE_COLORS.legacy;
    return (
        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded border text-xs font-mono ${c.bg} ${c.border} ${c.text}`}>
            <span>{c.icon}</span>
            <span>{stage}/{stage_status}</span>
        </span>
    );
}

function StageDistributionPanel({ stageStats }) {
    if (!stageStats || !stageStats.distribution) return null;
    const { distribution, stages, total } = stageStats;
    return (
        <div className="bg-black/30 border border-white/10 rounded-lg p-4">
            <div className="flex items-center justify-between mb-3">
                <div className="text-sm font-semibold text-white">
                    SISDS Stage Distribution
                    <span className="ml-2 text-xs text-gray-500">(CIO-017 Phase 1)</span>
                </div>
                <div className="text-xs text-gray-400">Total: {total}</div>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
                {stages.map((stage) => {
                    const c = STAGE_COLORS[stage] || STAGE_COLORS.legacy;
                    const statuses = distribution[stage] || {};
                    const totalForStage = Object.values(statuses).reduce((a, b) => a + b, 0);
                    return (
                        <div
                            key={stage}
                            className={`${c.bg} ${c.border} border rounded-lg p-3`}
                        >
                            <div className="flex items-center gap-2 mb-1">
                                <span className="text-lg">{c.icon}</span>
                                <span className={`text-xs font-semibold ${c.text} uppercase`}>
                                    {stage}
                                </span>
                            </div>
                            <div className="text-2xl font-bold text-white mb-2">{totalForStage}</div>
                            <div className="space-y-0.5">
                                {Object.entries(statuses).map(([status, count]) => (
                                    <div key={status} className="flex justify-between text-[10px]">
                                        <span className="text-gray-400 font-mono">{status}</span>
                                        <span className="text-white font-mono">{count}</span>
                                    </div>
                                ))}
                                {totalForStage === 0 && (
                                    <div className="text-[10px] text-gray-600 text-center py-1">empty</div>
                                )}
                            </div>
                        </div>
                    );
                })}
            </div>
            <div className="mt-3 text-xs text-gray-500">
                Stages: birth → sandbox → paper → live → retired (+ legacy for pre-SISDS pool)
            </div>
        </div>
    );
}

const CATEGORY_COLORS = {
    momentum: 'bg-orange-500/20 text-orange-300',
    mean_reversion: 'bg-cyan-500/20 text-cyan-300',
    breakout: 'bg-purple-500/20 text-purple-300',
    volume: 'bg-yellow-500/20 text-yellow-300',
    arbitrage: 'bg-green-500/20 text-green-300',
    time_based: 'bg-pink-500/20 text-pink-300',
    pattern: 'bg-indigo-500/20 text-indigo-300',
    news_driven: 'bg-rose-500/20 text-rose-300',
};

function StatusBadge({ status }) {
    const cls = STATUS_COLORS[status] || STATUS_COLORS.error;
    return (
        <span className={`px-2 py-0.5 rounded border text-xs font-mono ${cls}`}>
            {status}
        </span>
    );
}

function CategoryBadge({ category }) {
    const cls = CATEGORY_COLORS[category] || 'bg-gray-500/20 text-gray-300';
    return (
        <span className={`px-2 py-0.5 rounded text-xs ${cls}`}>
            {category || 'unknown'}
        </span>
    );
}

function BirthBadge({ birth }) {
    if (!birth) {
        return <span className="text-gray-600 text-xs">—</span>;
    }
    const classification = birth.classification || 'unknown';
    // CIO-015 Phase 4.6: zero_cycles is now an auto-fail (error), not a warning
    const CLS_MAP = {
        healthy: { emoji: '🟢', cls: 'text-emerald-400', label: 'healthy' },
        zero_cycles: { emoji: '🔴', cls: 'text-red-400', label: '0 cycles (fail)' },
        loss_functional: { emoji: '🟠', cls: 'text-orange-400', label: 'loss' },
        api_failure: { emoji: '🔴', cls: 'text-red-400', label: 'api fail' },
        invalid_response: { emoji: '🔴', cls: 'text-red-400', label: 'invalid' },
    };
    const info = CLS_MAP[classification] || { emoji: '⚪', cls: 'text-gray-400', label: classification };
    const cycles = birth.total_cycles != null ? birth.total_cycles : '?';
    return (
        <span className={`text-xs ${info.cls}`} title={`birth backtest: ${classification}, ${cycles} cycles`}>
            {info.emoji} {info.label} ({cycles})
        </span>
    );
}

function StatCard({ label, value, hint }) {
    return (
        <div className="bg-black/30 border border-white/10 rounded-lg p-4">
            <div className="text-xs text-gray-400 uppercase tracking-wider">{label}</div>
            <div className="text-3xl font-bold text-white mt-1">{value}</div>
            {hint && <div className="text-xs text-gray-500 mt-1">{hint}</div>}
        </div>
    );
}

function CategoryDistribution({ distribution, categorySet }) {
    const total = Object.values(distribution || {}).reduce((a, b) => a + b, 0);
    const allCategories = categorySet || Object.keys(distribution || {});
    return (
        <div className="bg-black/30 border border-white/10 rounded-lg p-4">
            <div className="text-sm font-semibold text-white mb-3">카테고리 분포</div>
            <div className="space-y-2">
                {allCategories.map((cat) => {
                    const count = distribution?.[cat] || 0;
                    const pct = total > 0 ? (count / total) * 100 : 0;
                    return (
                        <div key={cat} className="flex items-center gap-2">
                            <div className="w-28"><CategoryBadge category={cat} /></div>
                            <div className="flex-1 bg-white/5 rounded-full h-2 overflow-hidden">
                                <div
                                    className="bg-gradient-to-r from-blue-500 to-indigo-500 h-full transition-all"
                                    style={{ width: `${pct}%` }}
                                />
                            </div>
                            <div className="w-8 text-right text-xs text-gray-400 font-mono">{count}</div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}

function AuditionTable({ entries }) {
    if (!entries || entries.length === 0) {
        return (
            <div className="bg-black/30 border border-white/10 rounded-lg p-8 text-center text-gray-500">
                표시할 엔트리가 없습니다
            </div>
        );
    }
    return (
        <div className="bg-black/30 border border-white/10 rounded-lg overflow-hidden">
            <table className="w-full text-sm">
                <thead className="bg-white/5 border-b border-white/10">
                    <tr>
                        <th className="px-4 py-2 text-left text-xs text-gray-400 uppercase">ID</th>
                        <th className="px-4 py-2 text-left text-xs text-gray-400 uppercase">전략</th>
                        <th className="px-4 py-2 text-left text-xs text-gray-400 uppercase">카테고리</th>
                        <th className="px-4 py-2 text-left text-xs text-gray-400 uppercase">Stage</th>
                        <th className="px-4 py-2 text-left text-xs text-gray-400 uppercase">상태</th>
                        <th className="px-4 py-2 text-left text-xs text-gray-400 uppercase">Birth</th>
                        <th className="px-4 py-2 text-left text-xs text-gray-400 uppercase">주차</th>
                        <th className="px-4 py-2 text-right text-xs text-gray-400 uppercase">월복리(%)</th>
                        <th className="px-4 py-2 text-left text-xs text-gray-400 uppercase">판정일</th>
                    </tr>
                </thead>
                <tbody>
                    {entries.map((e) => {
                        const compound = e.backtest_result?.monthly_return_compound;
                        const birth = e.metadata?.birth_backtest;
                        return (
                            <tr key={e.id} className="border-b border-white/5 hover:bg-white/5">
                                <td className="px-4 py-2 font-mono text-gray-500">{e.id}</td>
                                <td className="px-4 py-2 font-mono text-white">{e.strategy_id}</td>
                                <td className="px-4 py-2"><CategoryBadge category={e.category} /></td>
                                <td className="px-4 py-2">
                                    {e.stage ? <StageBadge stage={e.stage} stage_status={e.stage_status} /> : <span className="text-gray-600 text-xs">—</span>}
                                </td>
                                <td className="px-4 py-2"><StatusBadge status={e.status} /></td>
                                <td className="px-4 py-2"><BirthBadge birth={birth} /></td>
                                <td className="px-4 py-2 text-gray-400 text-xs">{e.audition_week}</td>
                                <td className="px-4 py-2 text-right font-mono text-xs text-gray-300">
                                    {compound != null ? compound.toFixed(2) : '—'}
                                </td>
                                <td className="px-4 py-2 text-gray-500 text-xs">
                                    {e.judged_at ? e.judged_at.slice(0, 10) : '—'}
                                </td>
                            </tr>
                        );
                    })}
                </tbody>
            </table>
        </div>
    );
}

export default function Audition() {
    const [stats, setStats] = useState(null);
    const [entries, setEntries] = useState([]);
    const [graveyard, setGraveyard] = useState(null);
    const [stageStats, setStageStats] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    useEffect(() => {
        let alive = true;
        async function load() {
            try {
                const [s, list, g, ss] = await Promise.all([
                    fetchAuditionStats({ weeks: 8 }),
                    fetchAuditionList({ status: 'all', limit: 50 }),
                    fetchGraveyardStats(),
                    fetchStageStats(),
                ]);
                if (!alive) return;
                setStats(s);
                setEntries(list);
                setGraveyard(g);
                setStageStats(ss);
            } catch (e) {
                if (alive) setError(e?.message || 'Failed to load audition data');
            } finally {
                if (alive) setLoading(false);
            }
        }
        load();
        // Refresh every 60s since autonomy cycles are slow
        const interval = setInterval(load, 60000);
        return () => {
            alive = false;
            clearInterval(interval);
        };
    }, []);

    if (loading) {
        return (
            <div className="text-gray-400 text-center py-12">Loading audition pool...</div>
        );
    }
    if (error) {
        return (
            <div className="text-red-400 text-center py-12">Error: {error}</div>
        );
    }

    const totalByStatus = stats?.total_by_status || {};
    const totalActive =
        (totalByStatus.audition || 0) +
        (totalByStatus.graduated || 0) +
        (totalByStatus.resurrected || 0);

    // Birth backtest aggregation across all entries
    const birthCounts = entries.reduce((acc, e) => {
        const c = e.metadata?.birth_backtest?.classification;
        if (c) acc[c] = (acc[c] || 0) + 1;
        return acc;
    }, {});

    return (
        <div className="space-y-6">
            <div>
                <h1 className="text-2xl font-bold text-white">Strategy Audition System</h1>
                <p className="text-sm text-gray-400 mt-1">
                    AI 자율 전략 발굴 파이프라인 — 하루 1개 생성, 주 1개 선발 (READ-ONLY)
                </p>
            </div>

            {/* SISDS stage distribution (CIO-017 Phase 1) */}
            <StageDistributionPanel stageStats={stageStats} />

            {/* Summary stats */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <StatCard
                    label="Audition"
                    value={totalByStatus.audition || 0}
                    hint="이번 주 판정 대기"
                />
                <StatCard
                    label="Graduated"
                    value={totalByStatus.graduated || 0}
                    hint="주간 우승 누적 (legacy 포함)"
                />
                <StatCard
                    label="Eliminated"
                    value={totalByStatus.eliminated || 0}
                    hint="탈락 → graveyard"
                />
                <StatCard
                    label="Total Active"
                    value={totalActive}
                    hint="전체 풀 크기"
                />
            </div>

            {/* Birth backtest summary */}
            {Object.keys(birthCounts).length > 0 && (
                <div className="bg-black/30 border border-white/10 rounded-lg p-4">
                    <div className="text-sm font-semibold text-white mb-2">Birth Backtest — 생성 직후 smoke test</div>
                    <div className="flex flex-wrap gap-3 text-xs">
                        {birthCounts.healthy > 0 && (
                            <span className="text-emerald-400">🟢 healthy: {birthCounts.healthy}</span>
                        )}
                        {birthCounts.zero_cycles > 0 && (
                            <span className="text-red-400">🔴 0 cycles (auto-fail): {birthCounts.zero_cycles}</span>
                        )}
                        {birthCounts.loss_functional > 0 && (
                            <span className="text-orange-400">🟠 loss (functional): {birthCounts.loss_functional}</span>
                        )}
                        {birthCounts.api_failure > 0 && (
                            <span className="text-red-400">🔴 api failure: {birthCounts.api_failure}</span>
                        )}
                        {birthCounts.invalid_response > 0 && (
                            <span className="text-red-400">🔴 invalid response: {birthCounts.invalid_response}</span>
                        )}
                    </div>
                    <div className="text-xs text-gray-500 mt-2">
                        Birth backtest 는 판정이 아닌 smoke test. 실제 심사는 월요일 audition-judge 에서 수행.
                    </div>
                </div>
            )}

            {/* Last winner highlight */}
            {stats?.last_winner && (
                <div className="bg-gradient-to-r from-emerald-900/30 to-emerald-700/20 border border-emerald-500/40 rounded-lg p-4">
                    <div className="text-xs text-emerald-300 uppercase tracking-wider mb-1">
                        🏆 최근 우승 전략
                    </div>
                    <div className="flex items-center gap-4">
                        <div className="text-xl font-mono text-white">
                            {stats.last_winner.strategy_id}
                        </div>
                        <CategoryBadge category={stats.last_winner.category} />
                        <div className="text-sm text-gray-400">
                            주차: <span className="font-mono">{stats.last_winner.week}</span>
                        </div>
                        {stats.last_winner.monthly_return_compound != null && (
                            <div className="text-sm text-emerald-300">
                                월복리 {stats.last_winner.monthly_return_compound.toFixed(2)}%
                            </div>
                        )}
                    </div>
                </div>
            )}

            {/* Category distribution */}
            <CategoryDistribution
                distribution={stats?.category_distribution}
                categorySet={stats?.category_set}
            />

            {/* Graveyard summary */}
            {graveyard && (
                <div className="bg-black/30 border border-white/10 rounded-lg p-4">
                    <div className="text-sm font-semibold text-white mb-3">
                        Graveyard — 탈락 풀
                    </div>
                    <div className="grid grid-cols-3 gap-4 text-sm">
                        <div>
                            <div className="text-xs text-gray-500">총 탈락</div>
                            <div className="text-xl font-mono text-white">
                                {graveyard.total_eliminated}
                            </div>
                        </div>
                        <div>
                            <div className="text-xs text-gray-500">부활 후보</div>
                            <div className="text-xl font-mono text-amber-400">
                                {graveyard.resurrect_eligible_count}
                            </div>
                            <div className="text-xs text-gray-500">판정 30일 이상 경과</div>
                        </div>
                        <div>
                            <div className="text-xs text-gray-500">카테고리 분포</div>
                            <div className="text-xs text-gray-300 mt-1">
                                {Object.entries(graveyard.by_category || {}).map(([cat, cnt]) => (
                                    <span key={cat} className="mr-2">
                                        {cat}:{cnt}
                                    </span>
                                ))}
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {/* Pool table */}
            <div>
                <div className="text-sm font-semibold text-white mb-2">전체 풀 ({entries.length})</div>
                <AuditionTable entries={entries} />
            </div>

            <div className="text-xs text-gray-500 text-center pt-4">
                이 페이지는 READ-ONLY 입니다. 모든 상태 변경은 SAS 에이전트 자동 워크플로우에 의해 수행됩니다. (CIO-20260408-015)
            </div>
        </div>
    );
}
