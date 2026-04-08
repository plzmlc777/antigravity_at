// Right-pane: full decision detail with phase trace + raw markdown.
import { useEffect, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { fetchDecision } from '../../api/agentsMeta';
import PhaseTrace from './PhaseTrace';

export default function DecisionDetail({ decisionId }) {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(false);
    const [err, setErr] = useState(null);
    const [showRaw, setShowRaw] = useState(false);

    useEffect(() => {
        if (!decisionId) { setData(null); return; }
        let alive = true;
        setLoading(true);
        setErr(null);
        fetchDecision(decisionId)
            .then(d => { if (alive) setData(d); })
            .catch(e => { if (alive) setErr(e?.message || 'load failed'); })
            .finally(() => { if (alive) setLoading(false); });
        return () => { alive = false; };
    }, [decisionId]);

    if (!decisionId) {
        return (
            <div className="h-full flex items-center justify-center text-sm text-gray-500 italic">
                좌측에서 결정을 선택하세요.
            </div>
        );
    }
    if (loading) return <div className="text-sm text-gray-500">로딩 중…</div>;
    if (err) return <div className="text-sm text-red-400">{err}</div>;
    if (!data) return null;

    return (
        <div className="space-y-4">
            <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                    <div className="text-[10px] text-gray-500 font-mono">{data.id} · {data.date}</div>
                    <h2 className="text-lg font-bold text-white mt-1">{data.title}</h2>
                </div>
                <button
                    onClick={() => setShowRaw(s => !s)}
                    className="flex-shrink-0 px-3 py-1 rounded text-xs text-gray-400 hover:text-white hover:bg-white/10 border border-white/10"
                >
                    {showRaw ? 'Trace 보기' : 'Raw 보기'}
                </button>
            </div>

            {showRaw ? (
                <div className="prose prose-invert prose-sm max-w-none p-4 rounded-lg bg-white/5 border border-white/10">
                    <ReactMarkdown>{data.body || ''}</ReactMarkdown>
                </div>
            ) : (
                <PhaseTrace body={data.body || ''} />
            )}
        </div>
    );
}
