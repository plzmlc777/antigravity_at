// Single agent activity tile.
import { Link } from 'react-router-dom';

const ROLE_BADGE = {
    orchestrator: 'bg-purple-500/20 text-purple-300 border-purple-500/40',
    assess: 'bg-cyan-500/20 text-cyan-300 border-cyan-500/40',
    plan: 'bg-blue-500/20 text-blue-300 border-blue-500/40',
    execute: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40',
    intelligence: 'bg-amber-500/20 text-amber-300 border-amber-500/40',
    utility: 'bg-gray-500/20 text-gray-300 border-gray-500/40',
    'user-facing': 'bg-pink-500/20 text-pink-300 border-pink-500/40',
    other: 'bg-white/10 text-gray-400 border-white/20',
};

export default function AgentActivityCard({ agent }) {
    const role = agent.role || 'other';
    const badge = ROLE_BADGE[role] || ROLE_BADGE.other;
    return (
        <Link
            to={`/organization?agent=${agent.name}`}
            className="block p-4 rounded-lg bg-white/5 border border-white/10 hover:border-blue-500/40 hover:bg-white/10 transition"
        >
            <div className="flex items-start justify-between gap-2 mb-2">
                <span className="text-sm font-semibold text-white truncate">{agent.name}</span>
                <span className={`text-[10px] px-1.5 py-0.5 rounded border ${badge}`}>
                    {role}
                </span>
            </div>
            <p className="text-xs text-gray-400 line-clamp-3">
                {agent.description || '— description not available —'}
            </p>
            {agent.model && (
                <div className="mt-2 text-[10px] text-gray-500">
                    model: <span className="text-gray-400">{agent.model}</span>
                </div>
            )}
        </Link>
    );
}
