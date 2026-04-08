// One row in the left-hand decision list.
const KIND_BADGE = {
    cio: 'bg-blue-500/20 text-blue-300 border-blue-500/40',
    audit: 'bg-amber-500/20 text-amber-300 border-amber-500/40',
};

export default function DecisionListItem({ decision, active, onClick }) {
    const badge = KIND_BADGE[decision.kind] || 'bg-white/10 text-gray-300';
    return (
        <button
            onClick={() => onClick(decision)}
            className={`w-full text-left p-3 rounded-lg border transition ${
                active
                    ? 'border-blue-500/60 bg-blue-500/10'
                    : 'border-white/10 bg-white/5 hover:border-white/30'
            }`}
        >
            <div className="flex items-center justify-between gap-2 mb-1">
                <span className={`text-[10px] px-1.5 py-0.5 rounded border ${badge}`}>
                    {decision.kind.toUpperCase()}
                </span>
                <span className="text-[10px] text-gray-500 font-mono">{decision.date}</span>
            </div>
            <div className="text-[10px] text-gray-500 font-mono mb-0.5 truncate">{decision.id}</div>
            <div className="text-sm text-white line-clamp-2">{decision.title}</div>
        </button>
    );
}
