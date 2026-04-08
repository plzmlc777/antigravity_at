// Vertical 24h activity timeline. Sources from /api/v1/decisions (CIO + audits).
import { Link } from 'react-router-dom';

const KIND_DOT = {
    cio: 'bg-blue-500 ring-blue-500/30',
    audit: 'bg-amber-500 ring-amber-500/30',
};

export default function ActivityTimeline({ items = [], loading = false }) {
    if (loading) {
        return <div className="text-xs text-gray-500">Loading timeline…</div>;
    }
    if (!items.length) {
        return (
            <div className="text-xs text-gray-500 italic">
                지난 24시간 동안 기록된 결정이 없습니다.
            </div>
        );
    }
    return (
        <ol className="relative border-l border-white/10 pl-4 space-y-4">
            {items.map((d) => (
                <li key={d.id} className="relative">
                    <span
                        className={`absolute -left-[22px] top-1.5 w-3 h-3 rounded-full ring-4 ${KIND_DOT[d.kind] || 'bg-gray-500 ring-gray-500/30'}`}
                    />
                    <div className="text-[10px] text-gray-500 font-mono">
                        {d.date} · {d.id}
                    </div>
                    <Link
                        to={`/decisions?id=${d.id}`}
                        className="block text-sm text-white hover:text-blue-300 transition"
                    >
                        {d.title}
                    </Link>
                    {d.body_preview && (
                        <p className="mt-1 text-xs text-gray-400 line-clamp-2 whitespace-pre-line">
                            {d.body_preview}
                        </p>
                    )}
                </li>
            ))}
        </ol>
    );
}
