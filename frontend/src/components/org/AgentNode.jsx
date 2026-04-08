// React Flow custom node for an agent (or USER CEO).
import { Handle, Position } from 'reactflow';

const MODEL_COLORS = {
    opus:   'border-purple-500 bg-purple-500/15',
    sonnet: 'border-blue-500 bg-blue-500/15',
    haiku:  'border-gray-500 bg-gray-500/15',
};

const ROLE_LABEL = {
    'user-facing': '직접 대화',
    orchestrator: '오케스트레이터',
    assess: 'ASSESS',
    plan: 'PLAN',
    execute: 'EXECUTE',
    intelligence: 'INTELLIGENCE',
    utility: 'UTILITY',
    ceo: 'CEO',
    other: 'OTHER',
};

export default function AgentNode({ data, selected }) {
    const { name, role, model, isCeo, isVeto, highlighted } = data;
    const modelClass = MODEL_COLORS[model] || 'border-white/20 bg-white/5';
    const ringClass = selected
        ? 'ring-2 ring-blue-400'
        : highlighted
            ? 'ring-2 ring-amber-400'
            : '';
    const vetoClass = isVeto ? 'border-red-500' : '';
    const ceoClass = isCeo
        ? 'border-yellow-500 bg-yellow-500/10 text-yellow-200 font-bold'
        : '';

    return (
        <div
            className={`px-3 py-2 rounded-md border ${modelClass} ${vetoClass} ${ceoClass} ${ringClass} text-white shadow-md min-w-[150px] cursor-pointer transition`}
            title={data.description}
        >
            <Handle type="target" position={Position.Left} className="!bg-white/30" />
            <div className="text-[9px] uppercase tracking-wider text-gray-400">
                {ROLE_LABEL[role] || role}
                {isVeto && <span className="ml-1 text-red-400">· VETO</span>}
            </div>
            <div className="text-sm font-semibold truncate">{name}</div>
            {model && <div className="text-[10px] text-gray-400 mt-0.5">{model}</div>}
            <Handle type="source" position={Position.Right} className="!bg-white/30" />
        </div>
    );
}

export function ColumnLabelNode({ data }) {
    return (
        <div className="px-2 py-1 text-[10px] uppercase tracking-wider text-gray-500 font-bold">
            {data.label}
        </div>
    );
}
