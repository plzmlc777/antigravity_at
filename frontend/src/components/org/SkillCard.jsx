// Skill card displayed in the bottom carousel of /organization.
export default function SkillCard({ skill, active, onClick }) {
    const scriptCount = skill.scripts?.length || 0;
    return (
        <button
            onClick={() => onClick(skill)}
            className={`flex-shrink-0 w-56 text-left p-3 rounded-lg border transition ${
                active
                    ? 'border-amber-400 bg-amber-500/10'
                    : 'border-white/10 bg-white/5 hover:border-blue-500/40'
            }`}
        >
            <div className="text-[10px] uppercase tracking-wider text-gray-500">SKILL</div>
            <div className="text-sm font-semibold text-white truncate">{skill.name}</div>
            <p className="text-[11px] text-gray-400 line-clamp-3 mt-1">
                {skill.description || '— description not available —'}
            </p>
            <div className="mt-2 text-[10px] text-gray-500">
                scripts: <span className="text-gray-300">{scriptCount}</span>
                {skill.version && <span className="ml-2">v{skill.version}</span>}
            </div>
        </button>
    );
}
