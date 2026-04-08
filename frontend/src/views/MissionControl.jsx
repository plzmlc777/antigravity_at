// Mission Control — home page tower view.
// Surfaces: KPI banner, agent activity cards, 24h decision timeline, session summary.
import { useEffect, useState } from 'react';
import {
    fetchAgents,
    fetchDecisions,
    fetchMonitorSessions,
    fetchGoalProgress,
    fetchStrategyCandidates,
} from '../api/agentsMeta';
import AgentActivityCard from '../components/AgentActivityCard';
import ActivityTimeline from '../components/ActivityTimeline';
import { Link } from 'react-router-dom';

const POLL_MS = 30000;

export default function MissionControl() {
    const [agents, setAgents] = useState([]);
    const [decisions, setDecisions] = useState([]);
    const [sessions, setSessions] = useState([]);
    const [goal, setGoal] = useState(null);
    const [candidates, setCandidates] = useState([]);
    const [loading, setLoading] = useState(true);
    const [err, setErr] = useState(null);

    useEffect(() => {
        let alive = true;
        const load = async () => {
            try {
                const [a, d, s, g, c] = await Promise.all([
                    fetchAgents(),
                    fetchDecisions({ limit: 20 }),
                    fetchMonitorSessions(),
                    fetchGoalProgress().catch(() => null),
                    fetchStrategyCandidates().catch(() => []),
                ]);
                if (!alive) return;
                setAgents(a);
                setDecisions(d.items || []);
                setSessions(s.sessions || []);
                setGoal(g);
                setCandidates(c);
                setErr(null);
            } catch (e) {
                if (alive) setErr(e?.message || 'load failed');
            } finally {
                if (alive) setLoading(false);
            }
        };
        load();
        const t = setInterval(load, POLL_MS);
        return () => { alive = false; clearInterval(t); };
    }, []);

    // Featured agents (orchestrator + plan + intelligence + user-facing first)
    const ROLE_ORDER = ['orchestrator', 'plan', 'intelligence', 'execute', 'assess', 'utility', 'user-facing'];
    const sortedAgents = [...agents].sort((a, b) => {
        return (ROLE_ORDER.indexOf(a.role) - ROLE_ORDER.indexOf(b.role));
    });
    const featured = sortedAgents.slice(0, 8);

    const runningSessions = sessions.filter(s => s.status === 'RUNNING');
    const realRunning = runningSessions.filter(s => !s.is_paper);
    const paperRunning = runningSessions.filter(s => s.is_paper);

    // KPI compound passed/failed candidates count
    const failedCompound = candidates.filter(c => (c.status || '').includes('FAIL')).length;
    const promising = candidates.filter(c => (c.status || '').includes('PROMISING')).length;

    return (
        <div className="space-y-8">
            {/* Header */}
            <div className="flex items-end justify-between">
                <div>
                    <h1 className="text-3xl font-bold tracking-tight">Mission Control</h1>
                    <p className="text-sm text-gray-400 mt-1">
                        AI 트레이딩 시스템 관제탑 · 17개 에이전트 + 6개 스킬 자율 운영
                    </p>
                </div>
                <Link
                    to="/organization"
                    className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium transition"
                >
                    조직도 →
                </Link>
            </div>

            {err && (
                <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-300 text-sm">
                    {err}
                </div>
            )}

            {/* KPI Banner */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <KpiTile
                    label="월 복리 KPI"
                    value={goal ? `${goal.monthly_return_pct.toFixed(2)}%` : '—'}
                    sub={`목표 ${goal?.target_monthly_pct ?? 12}% / 월`}
                    accent={goal && goal.monthly_return_pct >= (goal?.target_monthly_pct || 12) ? 'green' : 'blue'}
                />
                <KpiTile
                    label="활성 세션"
                    value={runningSessions.length}
                    sub={`실거래 ${realRunning.length} · 모의 ${paperRunning.length}`}
                    accent={realRunning.length > 0 ? 'amber' : 'gray'}
                />
                <KpiTile
                    label="최근 결정"
                    value={decisions.length}
                    sub="24h CIO + 감사"
                    accent="blue"
                />
                <KpiTile
                    label="전략 후보"
                    value={candidates.length}
                    sub={`KPI fail ${failedCompound} · promising ${promising}`}
                    accent={failedCompound > 0 ? 'red' : 'gray'}
                />
            </div>

            {/* Agent Activity Cards */}
            <section>
                <div className="flex items-center justify-between mb-3">
                    <h2 className="text-lg font-semibold">에이전트 활동</h2>
                    <Link to="/organization" className="text-xs text-blue-400 hover:text-blue-300">
                        전체 조직도 보기 →
                    </Link>
                </div>
                {loading && !featured.length ? (
                    <div className="text-sm text-gray-500">로딩 중…</div>
                ) : (
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
                        {featured.map(a => <AgentActivityCard key={a.name} agent={a} />)}
                    </div>
                )}
            </section>

            {/* Two-column: Decisions + Sessions */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <section className="lg:col-span-2">
                    <h2 className="text-lg font-semibold mb-3">24h 결정 타임라인</h2>
                    <div className="p-4 rounded-lg bg-white/5 border border-white/10">
                        <ActivityTimeline items={decisions} loading={loading} />
                    </div>
                </section>

                <section>
                    <h2 className="text-lg font-semibold mb-3">세션 요약</h2>
                    <div className="space-y-2">
                        {runningSessions.length === 0 && (
                            <div className="text-xs text-gray-500 italic p-3 rounded-lg bg-white/5 border border-white/10">
                                실행 중인 세션이 없습니다.
                            </div>
                        )}
                        {runningSessions.map(s => (
                            <div key={s.session_id}
                                className="p-3 rounded-lg bg-white/5 border border-white/10 hover:border-blue-500/40 transition">
                                <div className="flex items-center justify-between">
                                    <span className="text-sm font-semibold text-white">{s.symbol}</span>
                                    <span className={`text-[10px] px-1.5 py-0.5 rounded ${s.is_paper ? 'bg-gray-500/20 text-gray-300' : 'bg-amber-500/20 text-amber-300'}`}>
                                        {s.is_paper ? 'PAPER' : 'REAL'}
                                    </span>
                                </div>
                                <div className="mt-1 flex items-baseline gap-2 text-xs">
                                    <span className={s.return_pct >= 0 ? 'text-emerald-400' : 'text-red-400'}>
                                        {s.return_pct >= 0 ? '+' : ''}{s.return_pct?.toFixed(2)}%
                                    </span>
                                    <span className="text-gray-500 truncate">{s.session_id.slice(0, 12)}</span>
                                </div>
                            </div>
                        ))}
                        <Link
                            to="/strategies"
                            className="block text-center text-xs text-blue-400 hover:text-blue-300 py-2"
                        >
                            전체 세션 →
                        </Link>
                    </div>
                </section>
            </div>
        </div>
    );
}

const ACCENT = {
    green: 'border-emerald-500/40 text-emerald-300',
    blue: 'border-blue-500/40 text-blue-300',
    amber: 'border-amber-500/40 text-amber-300',
    red: 'border-red-500/40 text-red-300',
    gray: 'border-white/10 text-gray-300',
};

function KpiTile({ label, value, sub, accent = 'gray' }) {
    return (
        <div className={`p-4 rounded-lg bg-white/5 border ${ACCENT[accent]}`}>
            <div className="text-[10px] uppercase tracking-wider text-gray-500">{label}</div>
            <div className={`text-2xl font-bold mt-1 ${ACCENT[accent].split(' ')[1]}`}>{value}</div>
            <div className="text-xs text-gray-400 mt-1">{sub}</div>
        </div>
    );
}
