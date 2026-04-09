// Custom ReactFlow node for the Workflow (n8n-style) visualization.
// CIO-20260408-016 Level 2.
import { Handle, Position } from 'reactflow';

const TYPE_STYLE = {
    trigger: {
        border: 'border-blue-500',
        bg: 'bg-blue-500/15',
        text: 'text-blue-100',
        icon: '⏰',
        labelColor: 'text-blue-300',
    },
    agent: {
        border: 'border-emerald-500',
        bg: 'bg-emerald-500/15',
        text: 'text-emerald-100',
        icon: '🤖',
        labelColor: 'text-emerald-300',
    },
    router: {
        border: 'border-orange-500',
        bg: 'bg-orange-500/15',
        text: 'text-orange-100',
        icon: '🔀',
        labelColor: 'text-orange-300',
    },
    datastore: {
        border: 'border-slate-500',
        bg: 'bg-slate-500/15',
        text: 'text-slate-100',
        icon: '🗄️',
        labelColor: 'text-slate-300',
    },
    file: {
        border: 'border-purple-500',
        bg: 'bg-purple-500/15',
        text: 'text-purple-100',
        icon: '📄',
        labelColor: 'text-purple-300',
    },
};

function formatRelative(isoTs) {
    if (!isoTs) return 'never';
    const d = new Date(isoTs);
    const diffMs = Date.now() - d.getTime();
    const diffMin = Math.round(diffMs / 60000);
    if (diffMin < 1) return 'just now';
    if (diffMin < 60) return `${diffMin}m ago`;
    const diffH = Math.round(diffMin / 60);
    if (diffH < 24) return `${diffH}h ago`;
    const diffD = Math.round(diffH / 24);
    return `${diffD}d ago`;
}

export default function WorkflowNode({ data, selected }) {
    const type = data?.type || 'agent';
    const style = TYPE_STYLE[type] || TYPE_STYLE.agent;
    const label = data?.label || 'unnamed';
    const sub = data?.sub;
    const count = data?.count ?? 0;
    const lastStatus = data?.lastStatus;
    const lastRunAt = data?.lastRunAt;
    const isActive = count > 0;

    const ringClass = selected
        ? 'ring-2 ring-blue-400'
        : isActive
            ? 'ring-1 ring-white/20'
            : '';

    // Status pill color
    let statusPill = null;
    if (lastStatus) {
        const pillMap = {
            success: 'bg-emerald-500/30 text-emerald-200',
            consumed: 'bg-emerald-500/30 text-emerald-200',
            winner: 'bg-yellow-500/30 text-yellow-200',
            created: 'bg-blue-500/30 text-blue-200',
            eliminated: 'bg-red-500/30 text-red-200',
            rejected: 'bg-red-500/30 text-red-200',
            failed: 'bg-red-500/30 text-red-200',
            error: 'bg-red-500/30 text-red-200',
            moved: 'bg-slate-500/30 text-slate-200',
            resurrected: 'bg-amber-500/30 text-amber-200',
        };
        const cls = pillMap[lastStatus] || 'bg-white/10 text-white/70';
        statusPill = (
            <span className={`px-1.5 py-0.5 rounded text-[9px] ${cls}`}>
                {lastStatus}
            </span>
        );
    }

    return (
        <div
            className={`px-3 py-2 rounded-md border-2 ${style.border} ${style.bg} ${ringClass} shadow-md min-w-[180px] max-w-[220px] ${isActive ? '' : 'opacity-60'}`}
            title={`${label}${sub ? '\n' + sub : ''}`}
        >
            <Handle type="target" position={Position.Left} className="!bg-white/30" />

            {/* Header: icon + label */}
            <div className="flex items-center gap-2 mb-1">
                <span className="text-base leading-none">{style.icon}</span>
                <div className="flex-1 min-w-0">
                    <div className={`text-xs font-mono font-semibold truncate ${style.text}`}>
                        {label}
                    </div>
                    {sub && (
                        <div className={`text-[9px] ${style.labelColor} truncate`}>
                            {sub}
                        </div>
                    )}
                </div>
            </div>

            {/* Stats row */}
            <div className="flex items-center gap-2 text-[10px] text-white/60">
                <span className="font-mono text-white/80">
                    {count}×
                </span>
                <span className="text-white/40 truncate flex-1">
                    {formatRelative(lastRunAt)}
                </span>
                {statusPill}
            </div>

            <Handle type="source" position={Position.Right} className="!bg-white/30" />
        </div>
    );
}
