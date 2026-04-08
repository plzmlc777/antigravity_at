// Static React Flow layout: 16 agents organized into 7 role columns + USER CEO node.
// Skill nodes are NOT placed in this graph (rendered separately as bottom carousel),
// but the helper `getSkillUsers(skillName)` returns highlight targets when a skill
// card is clicked.

const COL_X = {
    user: 0,
    'user-facing': 220,
    orchestrator: 460,
    assess: 700,
    plan: 940,
    execute: 1180,
    intelligence: 1420,
    utility: 1660,
};

const ROW_GAP = 90;
const ROW_BASE = 60;

// Hand-curated agent → role → row index. Keeps the chart deterministic.
// Edit this map when new agents are added.
export const ORG_AGENTS = [
    // user-facing column
    { name: 'strategy-builder', row: 0 },
    { name: 'stock-searcher',   row: 1 },
    // orchestrator column
    { name: 'cio',              row: 0 },
    // assess column
    { name: 'ops-monitor',      row: 0 },
    { name: 'market-researcher', row: 1 },
    // plan column
    { name: 'strategy-advisor', row: 0 },
    { name: 'backtest-analyst', row: 1 },
    { name: 'risk-manager',     row: 2 },
    // execute column
    { name: 'trade-executor',     row: 0 },
    { name: 'signal-synthesizer', row: 1 },
    // intelligence column
    { name: 'meta-learner',     row: 0 },
    { name: 'strategy-evolver', row: 1 },
    { name: 'self-critic',      row: 2 },
    { name: 'tech-scout',       row: 3 },
    // utility column
    { name: 'symbol-evaluator', row: 0 },
    { name: 'symbol-scout',     row: 1 },
];

// Edges: USER → user-facing/CIO; CIO → ASSESS/PLAN/EXECUTE/INTELLIGENCE columns.
const STATIC_EDGES = [
    // CEO supervises direct-conversation agents and CIO
    { source: 'user', target: 'strategy-builder' },
    { source: 'user', target: 'stock-searcher' },
    { source: 'user', target: 'cio' },
    // CIO dispatches downstream
    { source: 'cio', target: 'ops-monitor' },
    { source: 'cio', target: 'market-researcher' },
    { source: 'cio', target: 'strategy-advisor' },
    { source: 'cio', target: 'backtest-analyst' },
    { source: 'cio', target: 'risk-manager' },
    { source: 'cio', target: 'trade-executor' },
    { source: 'cio', target: 'signal-synthesizer' },
    { source: 'cio', target: 'meta-learner' },
    { source: 'cio', target: 'strategy-evolver' },
    { source: 'cio', target: 'self-critic' },
    { source: 'cio', target: 'tech-scout' },
    // Utility — invoked from anywhere (visualized as edges from CIO too)
    { source: 'cio', target: 'symbol-evaluator' },
    { source: 'cio', target: 'symbol-scout' },
];

export function buildOrgGraph(agentsMeta = []) {
    const byName = new Map(agentsMeta.map(a => [a.name, a]));

    // CEO (user) node
    const userNode = {
        id: 'user',
        type: 'agentNode',
        position: { x: COL_X.user, y: ROW_BASE + ROW_GAP },
        data: {
            name: 'USER',
            description: '최종 의사결정자 — supervisor',
            role: 'ceo',
            model: null,
            isCeo: true,
        },
    };

    const agentNodes = ORG_AGENTS.map(({ name, row }) => {
        const meta = byName.get(name) || {};
        const role = meta.role || 'other';
        const x = COL_X[role] ?? 800;
        const y = ROW_BASE + row * ROW_GAP;
        return {
            id: name,
            type: 'agentNode',
            position: { x, y },
            data: {
                name,
                description: meta.description || '',
                role,
                model: meta.model || null,
                isVeto: name === 'risk-manager',
            },
        };
    });

    // Header label nodes (column titles) — rendered as plain group nodes
    const COLUMN_LABELS = [
        { role: 'user-facing', label: '직접 대화' },
        { role: 'orchestrator', label: '오케스트레이터' },
        { role: 'assess', label: 'ASSESS' },
        { role: 'plan', label: 'PLAN' },
        { role: 'execute', label: 'EXECUTE' },
        { role: 'intelligence', label: 'INTELLIGENCE' },
        { role: 'utility', label: 'UTILITY' },
    ];
    const labelNodes = COLUMN_LABELS.map(({ role, label }) => ({
        id: `label-${role}`,
        type: 'columnLabel',
        position: { x: COL_X[role], y: 0 },
        data: { label },
        draggable: false,
        selectable: false,
    }));

    const edges = STATIC_EDGES.map(e => ({
        id: `${e.source}->${e.target}`,
        source: e.source,
        target: e.target,
        animated: false,
        style: { stroke: 'rgba(255,255,255,0.18)', strokeWidth: 1 },
    }));

    return {
        nodes: [userNode, ...labelNodes, ...agentNodes],
        edges,
    };
}

// Skill usage map — which agents are heavy users of each at-* skill.
// (Hand-curated from agent definitions.)
export const SKILL_USERS = {
    'at-backtest':      ['backtest-analyst', 'strategy-evolver', 'strategy-advisor'],
    'at-monitor':       ['ops-monitor', 'cio'],
    'at-symbol-select': ['symbol-scout', 'symbol-evaluator', 'cio'],
    'at-live-signal':   ['signal-synthesizer', 'trade-executor'],
    'at-strategy':      ['strategy-builder', 'strategy-evolver', 'strategy-advisor', 'meta-learner'],
    'at-binance':       ['trade-executor', 'symbol-scout'],
};

export function getSkillUsers(skillName) {
    return SKILL_USERS[skillName] || [];
}
