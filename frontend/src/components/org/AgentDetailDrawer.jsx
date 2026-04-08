// Right-side slide-in drawer that renders the selected agent's full markdown.
import { useEffect, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { fetchAgent } from '../../api/agentsMeta';

export default function AgentDetailDrawer({ agentName, onClose }) {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(false);
    const [err, setErr] = useState(null);

    useEffect(() => {
        if (!agentName) { setData(null); return; }
        let alive = true;
        setLoading(true);
        setErr(null);
        fetchAgent(agentName)
            .then(d => { if (alive) setData(d); })
            .catch(e => { if (alive) setErr(e?.message || 'load failed'); })
            .finally(() => { if (alive) setLoading(false); });
        return () => { alive = false; };
    }, [agentName]);

    if (!agentName) return null;

    return (
        <div className="fixed inset-y-0 right-0 w-full sm:w-[480px] bg-[#0a0a0f] border-l border-white/10 shadow-2xl z-40 overflow-y-auto">
            <div className="sticky top-0 flex items-center justify-between p-4 border-b border-white/10 bg-[#0a0a0f]/95 backdrop-blur">
                <div>
                    <div className="text-[10px] uppercase tracking-wider text-gray-500">AGENT</div>
                    <h2 className="text-lg font-bold text-white">{agentName}</h2>
                </div>
                <button
                    onClick={onClose}
                    className="px-3 py-1 rounded text-sm text-gray-400 hover:text-white hover:bg-white/10"
                >
                    ✕
                </button>
            </div>
            <div className="p-4">
                {loading && <div className="text-sm text-gray-500">로딩 중…</div>}
                {err && <div className="text-sm text-red-400">{err}</div>}
                {data && (
                    <>
                        <div className="mb-4 space-y-1 text-xs">
                            <div><span className="text-gray-500">role:</span> <span className="text-gray-300">{data.role}</span></div>
                            {data.model && <div><span className="text-gray-500">model:</span> <span className="text-gray-300">{data.model}</span></div>}
                            {data.tools?.length > 0 && (
                                <div><span className="text-gray-500">tools:</span> <span className="text-gray-300">{data.tools.join(', ')}</span></div>
                            )}
                            {data.dispatch_targets?.length > 0 && (
                                <div><span className="text-gray-500">dispatches:</span> <span className="text-gray-300">{data.dispatch_targets.join(', ')}</span></div>
                            )}
                        </div>
                        <p className="text-sm text-gray-300 mb-4 italic">{data.description}</p>
                        <div className="prose prose-invert prose-sm max-w-none">
                            <ReactMarkdown>{data.body || ''}</ReactMarkdown>
                        </div>
                    </>
                )}
            </div>
        </div>
    );
}
