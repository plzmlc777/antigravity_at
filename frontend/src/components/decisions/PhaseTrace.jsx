// Parses a CIO decision body into ASSESS / PLAN / EXECUTE phase traces.
// The CIO decision schema (decision_log.md):
//   - **Workflow**: ...
//   - **Process**:
//       - ops-monitor: ...           (ASSESS)
//       - market-researcher: ...     (ASSESS)
//       - strategy-advisor: ...      (PLAN)
//       - backtest-analyst: ...      (PLAN)
//       - risk-manager: ...          (PLAN, may VETO)
//   - **Executed**: yes | no | dry-run

const ASSESS_AGENTS = new Set(['ops-monitor', 'market-researcher']);
const PLAN_AGENTS = new Set(['strategy-advisor', 'backtest-analyst', 'risk-manager']);
const EXECUTE_AGENTS = new Set(['trade-executor', 'signal-synthesizer']);

function parseProcess(body) {
    const lines = body.split('\n');
    const out = { assess: [], plan: [], execute: [], other: [] };
    let inProcess = false;
    for (const raw of lines) {
        const line = raw.trim();
        if (/^[-*]\s*\*\*Process\*\*/i.test(line)) { inProcess = true; continue; }
        if (inProcess) {
            // exit when we hit another top-level bullet that starts with **Foo**:
            if (/^[-*]\s*\*\*[A-Z][^*]+\*\*/i.test(line)) { inProcess = false; }
        }
        // sub-bullet under Process:  - agent-name: text
        const m = raw.match(/^\s+-\s*([a-z][a-z-]+):\s*(.+)$/);
        if (m) {
            const agent = m[1];
            const text = m[2].trim();
            const item = { agent, text };
            if (ASSESS_AGENTS.has(agent)) out.assess.push(item);
            else if (PLAN_AGENTS.has(agent)) out.plan.push(item);
            else if (EXECUTE_AGENTS.has(agent)) out.execute.push(item);
            else out.other.push(item);
        }
    }
    return out;
}

function parseField(body, name) {
    const re = new RegExp(`\\*\\*${name}\\*\\*:?\\s*(.+)`, 'i');
    const m = body.match(re);
    return m ? m[1].trim() : null;
}

const PHASES = [
    { key: 'assess', label: 'ASSESS', color: 'border-cyan-500/40 bg-cyan-500/10 text-cyan-200' },
    { key: 'plan', label: 'PLAN', color: 'border-blue-500/40 bg-blue-500/10 text-blue-200' },
    { key: 'execute', label: 'EXECUTE', color: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-200' },
];

export default function PhaseTrace({ body }) {
    if (!body) return null;
    const parsed = parseProcess(body);
    const workflow = parseField(body, 'Workflow');
    const session = parseField(body, 'Session');
    const symbol = parseField(body, 'Symbol');
    const executed = parseField(body, 'Executed');
    const status = parseField(body, 'Status');

    const hasAnyPhase = parsed.assess.length + parsed.plan.length + parsed.execute.length > 0;

    // KPI gate detection: scan for "복리" / "compound" mentions to flag KPI evaluations.
    const kpiHit = /복리|compound|kpi/i.test(body);

    // VETO detection
    const veto = parsed.plan.find(p => p.agent === 'risk-manager' && /reject/i.test(p.text));

    return (
        <div className="space-y-4">
            {/* Meta */}
            <div className="grid grid-cols-2 gap-2 text-xs">
                {workflow && <Meta label="workflow" value={workflow} />}
                {session && <Meta label="session" value={session} />}
                {symbol && <Meta label="symbol" value={symbol} />}
                {executed && <Meta label="executed" value={executed} highlight={executed === 'yes' ? 'green' : executed === 'no' ? 'gray' : 'amber'} />}
                {status && <Meta label="status" value={status} />}
                {kpiHit && <Meta label="KPI gate" value="evaluated" highlight="blue" />}
                {veto && <Meta label="risk-manager" value="REJECTED" highlight="red" />}
            </div>

            {/* Phases */}
            {hasAnyPhase ? (
                <div className="space-y-3">
                    {PHASES.map(phase => (
                        <PhaseSection
                            key={phase.key}
                            label={phase.label}
                            color={phase.color}
                            items={parsed[phase.key]}
                        />
                    ))}
                    {parsed.other.length > 0 && (
                        <PhaseSection
                            label="OTHER"
                            color="border-white/10 bg-white/5 text-gray-300"
                            items={parsed.other}
                        />
                    )}
                </div>
            ) : (
                <div className="text-xs text-gray-500 italic">
                    Process 항목이 감지되지 않았습니다. 본문 원문을 참조하세요.
                </div>
            )}
        </div>
    );
}

function PhaseSection({ label, color, items }) {
    if (!items.length) return null;
    return (
        <div className={`p-3 rounded-lg border ${color}`}>
            <div className="text-[10px] uppercase tracking-wider font-bold mb-2">{label}</div>
            <ul className="space-y-1.5">
                {items.map((it, idx) => (
                    <li key={idx} className="text-xs">
                        <span className="font-mono text-white">{it.agent}</span>
                        <span className="text-gray-400">: {it.text}</span>
                    </li>
                ))}
            </ul>
        </div>
    );
}

const META_HIGHLIGHT = {
    green: 'border-emerald-500/40 text-emerald-300',
    amber: 'border-amber-500/40 text-amber-300',
    blue: 'border-blue-500/40 text-blue-300',
    red: 'border-red-500/40 text-red-300',
    gray: 'border-white/10 text-gray-300',
};

function Meta({ label, value, highlight = 'gray' }) {
    return (
        <div className={`p-2 rounded border bg-white/5 ${META_HIGHLIGHT[highlight]}`}>
            <div className="text-[9px] uppercase tracking-wider text-gray-500">{label}</div>
            <div className="text-xs font-medium truncate">{value}</div>
        </div>
    );
}
