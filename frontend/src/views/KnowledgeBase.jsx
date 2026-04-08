// Knowledge Base — browse meta_learnings + strategy_candidates with KPI compound color coding.
import { useEffect, useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import {
    fetchMetaLearnings,
    fetchStrategyCandidates,
    fetchStrategyCandidate,
} from '../api/agentsMeta';

export default function KnowledgeBase() {
    const [tab, setTab] = useState('candidates'); // candidates | learnings

    return (
        <div className="space-y-4">
            <div className="flex items-end justify-between">
                <div>
                    <h1 className="text-3xl font-bold tracking-tight">Knowledge Base</h1>
                    <p className="text-sm text-gray-400 mt-1">
                        전략 후보 + 메타러너 학습 로그 · KPI 12% 복리 색상 코딩
                    </p>
                </div>
                <div className="flex gap-1 p-1 rounded-lg bg-white/5 border border-white/10">
                    <TabBtn active={tab === 'candidates'} onClick={() => setTab('candidates')}>
                        전략 후보
                    </TabBtn>
                    <TabBtn active={tab === 'learnings'} onClick={() => setTab('learnings')}>
                        Meta Learnings
                    </TabBtn>
                </div>
            </div>

            {tab === 'candidates' ? <CandidatesPanel /> : <MetaLearningsPanel />}
        </div>
    );
}

function CandidatesPanel() {
    const [items, setItems] = useState([]);
    const [loading, setLoading] = useState(true);
    const [err, setErr] = useState(null);
    const [selected, setSelected] = useState(null);
    const [body, setBody] = useState(null);
    const [bodyLoading, setBodyLoading] = useState(false);
    const [statusFilter, setStatusFilter] = useState('all');

    useEffect(() => {
        let alive = true;
        fetchStrategyCandidates()
            .then(d => { if (alive) setItems(d || []); })
            .catch(e => { if (alive) setErr(e?.message || 'load failed'); })
            .finally(() => { if (alive) setLoading(false); });
        return () => { alive = false; };
    }, []);

    const filtered = useMemo(() => {
        if (statusFilter === 'all') return items;
        if (statusFilter === 'fail') return items.filter(i => (i.status || '').includes('FAIL'));
        if (statusFilter === 'promising') return items.filter(i => (i.status || '').includes('PROMISING'));
        if (statusFilter === 'rejected') return items.filter(i => (i.status || '').includes('REJECTED'));
        return items;
    }, [items, statusFilter]);

    useEffect(() => {
        if (!selected) { setBody(null); return; }
        const filename = selected.doc_filename;
        if (!filename) { setBody(null); return; }
        let alive = true;
        setBodyLoading(true);
        fetchStrategyCandidate(filename)
            .then(d => { if (alive) setBody(d?.body || ''); })
            .catch(e => { if (alive) setBody(`로드 실패: ${e?.message}`); })
            .finally(() => { if (alive) setBodyLoading(false); });
        return () => { alive = false; };
    }, [selected]);

    if (err) return <div className="p-3 rounded bg-red-500/10 border border-red-500/30 text-red-300 text-sm">{err}</div>;

    const counts = {
        all: items.length,
        fail: items.filter(i => (i.status || '').includes('FAIL')).length,
        promising: items.filter(i => (i.status || '').includes('PROMISING')).length,
        rejected: items.filter(i => (i.status || '').includes('REJECTED')).length,
    };

    return (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 min-h-[600px]">
            <aside className="lg:col-span-1 space-y-3">
                <div className="flex flex-wrap gap-1">
                    <FilterBtn active={statusFilter === 'all'} onClick={() => setStatusFilter('all')}>
                        전체 ({counts.all})
                    </FilterBtn>
                    <FilterBtn active={statusFilter === 'fail'} onClick={() => setStatusFilter('fail')} accent="red">
                        FAIL ({counts.fail})
                    </FilterBtn>
                    <FilterBtn active={statusFilter === 'promising'} onClick={() => setStatusFilter('promising')} accent="green">
                        PROMISING ({counts.promising})
                    </FilterBtn>
                    <FilterBtn active={statusFilter === 'rejected'} onClick={() => setStatusFilter('rejected')} accent="gray">
                        REJECTED ({counts.rejected})
                    </FilterBtn>
                </div>
                {loading ? (
                    <div className="text-sm text-gray-500">로딩 중…</div>
                ) : filtered.length === 0 ? (
                    <div className="text-sm text-gray-500 italic">후보가 없습니다.</div>
                ) : (
                    <div className="space-y-2 max-h-[700px] overflow-y-auto pr-1">
                        {filtered.map(c => (
                            <CandidateRow
                                key={c.id}
                                candidate={c}
                                active={selected?.id === c.id}
                                onClick={() => setSelected(c)}
                            />
                        ))}
                    </div>
                )}
            </aside>

            <main className="lg:col-span-2 p-4 rounded-lg bg-white/5 border border-white/10 min-h-[600px]">
                {!selected ? (
                    <div className="h-full flex items-center justify-center text-sm text-gray-500 italic">
                        좌측에서 후보를 선택하세요.
                    </div>
                ) : (
                    <>
                        <div className="mb-3">
                            <div className="text-[10px] text-gray-500 font-mono">{selected.timestamp}</div>
                            <h2 className="text-lg font-bold text-white mt-1">
                                {selected.symbol} · {selected.strategy}
                            </h2>
                            <StatusPill status={selected.status} />
                        </div>
                        {bodyLoading ? (
                            <div className="text-sm text-gray-500">로딩 중…</div>
                        ) : body ? (
                            <div className="prose prose-invert prose-sm max-w-none">
                                <ReactMarkdown>{body}</ReactMarkdown>
                            </div>
                        ) : (
                            <div className="text-sm text-gray-500 italic">
                                본문 파일이 없습니다 (status only).
                            </div>
                        )}
                    </>
                )}
            </main>
        </div>
    );
}

function CandidateRow({ candidate, active, onClick }) {
    return (
        <button
            onClick={onClick}
            className={`w-full text-left p-2.5 rounded-lg border transition ${
                active
                    ? 'border-blue-500/60 bg-blue-500/10'
                    : 'border-white/10 bg-white/5 hover:border-white/30'
            }`}
        >
            <div className="flex items-center justify-between gap-2 mb-1">
                <span className="text-sm font-semibold text-white">{candidate.symbol}</span>
                <StatusPill status={candidate.status} compact />
            </div>
            <div className="text-[11px] text-gray-400 truncate">{candidate.strategy}</div>
            <div className="text-[10px] text-gray-500 font-mono mt-0.5">{candidate.timestamp}</div>
        </button>
    );
}

function StatusPill({ status, compact }) {
    const s = status || 'UNKNOWN';
    let color = 'bg-white/10 text-gray-300 border-white/20';
    if (s.includes('FAIL')) color = 'bg-red-500/20 text-red-300 border-red-500/40';
    else if (s.includes('PROMISING')) color = 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40';
    else if (s.includes('REJECTED')) color = 'bg-gray-500/20 text-gray-400 border-gray-500/40';
    return (
        <span className={`text-[10px] px-1.5 py-0.5 rounded border ${color} ${compact ? '' : 'inline-block mt-2'}`}>
            {s}
        </span>
    );
}

function MetaLearningsPanel() {
    const [body, setBody] = useState('');
    const [loading, setLoading] = useState(true);
    const [err, setErr] = useState(null);

    useEffect(() => {
        let alive = true;
        fetchMetaLearnings()
            .then(d => { if (alive) setBody(d?.body || ''); })
            .catch(e => { if (alive) setErr(e?.message || 'load failed'); })
            .finally(() => { if (alive) setLoading(false); });
        return () => { alive = false; };
    }, []);

    if (loading) return <div className="text-sm text-gray-500">로딩 중…</div>;
    if (err) return <div className="p-3 rounded bg-red-500/10 border border-red-500/30 text-red-300 text-sm">{err}</div>;

    return (
        <div className="p-6 rounded-lg bg-white/5 border border-white/10">
            <div className="prose prose-invert prose-sm max-w-none">
                <ReactMarkdown>{body}</ReactMarkdown>
            </div>
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

function FilterBtn({ active, onClick, children, accent }) {
    const accentClass = accent === 'red'
        ? (active ? 'bg-red-600 text-white' : 'bg-red-500/10 text-red-300')
        : accent === 'green'
            ? (active ? 'bg-emerald-600 text-white' : 'bg-emerald-500/10 text-emerald-300')
            : accent === 'gray'
                ? (active ? 'bg-gray-600 text-white' : 'bg-gray-500/10 text-gray-300')
                : (active ? 'bg-blue-600 text-white' : 'bg-white/5 text-gray-400');
    return (
        <button onClick={onClick} className={`px-2 py-1 rounded text-xs transition ${accentClass}`}>
            {children}
        </button>
    );
}
