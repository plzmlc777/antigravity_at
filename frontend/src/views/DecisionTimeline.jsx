// Decision log browser. Left = list, right = ASSESS/PLAN/EXECUTE phase trace.
// Tabs: Decisions | Approval Queue
import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { fetchDecisions } from '../api/agentsMeta';
import DecisionListItem from '../components/decisions/DecisionListItem';
import DecisionDetail from '../components/decisions/DecisionDetail';
import ApprovalQueue from '../components/decisions/ApprovalQueue';

export default function DecisionTimeline() {
    const [items, setItems] = useState([]);
    const [loading, setLoading] = useState(true);
    const [err, setErr] = useState(null);
    const [filter, setFilter] = useState('all'); // all | cio | audit
    const [tab, setTab] = useState('decisions'); // decisions | approvals
    const [searchParams, setSearchParams] = useSearchParams();
    const selectedId = searchParams.get('id');

    useEffect(() => {
        let alive = true;
        setLoading(true);
        fetchDecisions({ limit: 200 })
            .then(d => { if (alive) setItems(d.items || []); })
            .catch(e => { if (alive) setErr(e?.message || 'load failed'); })
            .finally(() => { if (alive) setLoading(false); });
        return () => { alive = false; };
    }, []);

    const filtered = useMemo(() => {
        if (filter === 'all') return items;
        return items.filter(i => i.kind === filter);
    }, [items, filter]);

    // Auto-select first decision if none selected
    useEffect(() => {
        if (!selectedId && filtered.length > 0) {
            setSearchParams({ id: filtered[0].id }, { replace: true });
        }
    }, [filtered, selectedId, setSearchParams]);

    const handleSelect = (decision) => {
        setSearchParams({ id: decision.id });
    };

    return (
        <div className="space-y-4">
            <div className="flex items-end justify-between">
                <div>
                    <h1 className="text-3xl font-bold tracking-tight">결정 타임라인</h1>
                    <p className="text-sm text-gray-400 mt-1">
                        CIO 결정과 감사 로그 · ASSESS → PLAN → EXECUTE 추적
                    </p>
                </div>
                <div className="flex gap-1 p-1 rounded-lg bg-white/5 border border-white/10">
                    <TabBtn active={tab === 'decisions'} onClick={() => setTab('decisions')}>
                        결정 로그 ({items.length})
                    </TabBtn>
                    <TabBtn active={tab === 'approvals'} onClick={() => setTab('approvals')}>
                        승인 대기열
                    </TabBtn>
                </div>
            </div>

            {err && (
                <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-300 text-sm">
                    {err}
                </div>
            )}

            {tab === 'decisions' ? (
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 min-h-[600px]">
                    {/* Left list */}
                    <aside className="lg:col-span-1 space-y-3">
                        <div className="flex gap-1">
                            <FilterBtn active={filter === 'all'} onClick={() => setFilter('all')}>전체</FilterBtn>
                            <FilterBtn active={filter === 'cio'} onClick={() => setFilter('cio')}>CIO</FilterBtn>
                            <FilterBtn active={filter === 'audit'} onClick={() => setFilter('audit')}>Audit</FilterBtn>
                        </div>
                        {loading ? (
                            <div className="text-sm text-gray-500">로딩 중…</div>
                        ) : filtered.length === 0 ? (
                            <div className="text-sm text-gray-500 italic">결정 항목이 없습니다.</div>
                        ) : (
                            <div className="space-y-2 max-h-[700px] overflow-y-auto pr-1">
                                {filtered.map(d => (
                                    <DecisionListItem
                                        key={d.id}
                                        decision={d}
                                        active={d.id === selectedId}
                                        onClick={handleSelect}
                                    />
                                ))}
                            </div>
                        )}
                    </aside>

                    {/* Right detail */}
                    <main className="lg:col-span-2 p-4 rounded-lg bg-white/5 border border-white/10 min-h-[600px]">
                        <DecisionDetail decisionId={selectedId} />
                    </main>
                </div>
            ) : (
                <div className="max-w-2xl">
                    <ApprovalQueue />
                </div>
            )}
        </div>
    );
}

function TabBtn({ active, onClick, children }) {
    return (
        <button
            onClick={onClick}
            className={`px-3 py-1.5 rounded text-xs font-medium transition ${
                active ? 'bg-blue-600 text-white' : 'text-gray-400 hover:text-white'
            }`}
        >
            {children}
        </button>
    );
}

function FilterBtn({ active, onClick, children }) {
    return (
        <button
            onClick={onClick}
            className={`flex-1 px-2 py-1 rounded text-xs transition ${
                active ? 'bg-blue-600 text-white' : 'bg-white/5 text-gray-400 hover:text-white'
            }`}
        >
            {children}
        </button>
    );
}
