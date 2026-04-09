// Workflow Execution Visualization — CIO-20260408-016 Level 2.
//
// n8n-style live dashboard for the SAS + gap_signal pipeline. Shows a
// hardcoded node graph (triggers → agents → data stores) with live
// execution counts overlaid from /api/v1/workflow/executions/recent.
//
// READ-ONLY per feedback_no_manual_frontend_controls — no buttons
// affect backend state, only a client-side timeline window selector.
import { useCallback, useEffect, useMemo, useState } from 'react';
import ReactFlow, {
    Background,
    Controls,
    MiniMap,
    useNodesState,
    useEdgesState,
} from 'reactflow';
import 'reactflow/dist/style.css';

import { fetchRecentExecutions } from '../api/workflow';
import WorkflowNode from '../components/workflow/WorkflowNode';

const nodeTypes = {
    workflowNode: WorkflowNode,
};

// ─────────────────────────────────────────────────────────────────────
// Hardcoded node layout — 5 columns, one flow per row
// Column 0: Triggers (PM2 cron, user)
// Column 1: Emitter agents (meta-learner, self-critic, cio)
// Column 2: Queue / Router (gap_signals DB, main-turn)
// Column 3: Consumer agents (strategy-builder, skill-architect, audition-judge, monthly-resurrect)
// Column 4: Sinks (strategies dir, skills dir, audition DB, graveyard)
// ─────────────────────────────────────────────────────────────────────

const COL = { c0: 0, c1: 280, c2: 560, c3: 840, c4: 1180 };
const ROW = { r0: 40, r1: 140, r2: 240, r3: 340, r4: 440, r5: 540, r6: 640, r7: 740 };

const NODE_DEFS = [
    // Triggers
    { id: 'cron-daily', type: 'trigger', label: 'PM2 daily cron', sub: '09:00 KST', x: COL.c0, y: ROW.r0 },
    { id: 'cron-weekly', type: 'trigger', label: 'PM2 weekly cron', sub: '월 10:00 KST', x: COL.c0, y: ROW.r1 },
    { id: 'cron-monthly', type: 'trigger', label: 'PM2 monthly cron', sub: '1일 11:00 KST', x: COL.c0, y: ROW.r2 },
    { id: 'user-request', type: 'trigger', label: 'user request', sub: '대화창', x: COL.c0, y: ROW.r3 },

    // Emitter agents
    { id: 'meta-learner', type: 'agent', label: 'meta-learner', sub: 'D-019 gap emit', x: COL.c1, y: ROW.r0 },
    { id: 'self-critic', type: 'agent', label: 'self-critic', sub: 'audit gap emit', x: COL.c1, y: ROW.r3 },
    { id: 'audition-judge', type: 'agent', label: 'audition-judge', sub: '주간 심사', x: COL.c1, y: ROW.r1 },
    { id: 'monthly-resurrect', type: 'agent', label: 'monthly-resurrect', sub: '월간 부활', x: COL.c1, y: ROW.r2 },

    // Queue + Router
    { id: 'gap-signals-db', type: 'datastore', label: 'gap_signals DB', sub: 'POST/GET/PATCH', x: COL.c2, y: ROW.r0 },
    { id: 'main-turn', type: 'router', label: 'main-turn', sub: 'family routing', x: COL.c2, y: ROW.r1 },

    // Consumer agents
    { id: 'strategy-builder', type: 'agent', label: 'strategy-builder', sub: 'autonomous', x: COL.c3, y: ROW.r0 },
    { id: 'skill-architect', type: 'agent', label: 'skill-architect', sub: 'analytical primitive', x: COL.c3, y: ROW.r1 },
    { id: 'risk-manager', type: 'agent', label: 'risk-manager', sub: 'margin gate', x: COL.c3, y: ROW.r3 },

    // Sinks
    { id: 'strategies-dir', type: 'file', label: 'strategies/*.py', sub: 'BaseStrategy', x: COL.c4, y: ROW.r0 },
    { id: 'audition-db', type: 'datastore', label: 'strategy_audition DB', sub: '오디션 풀', x: COL.c4, y: ROW.r1 },
    { id: 'skills-dir', type: 'file', label: 'skills/**/*.py', sub: 'pure primitives', x: COL.c4, y: ROW.r2 },
    { id: 'graveyard', type: 'file', label: 'strategies/_graveyard/', sub: 'eliminated', x: COL.c4, y: ROW.r3 },
];

const EDGE_DEFS = [
    // Daily SAS flow
    { source: 'cron-daily', target: 'meta-learner', label: 'claude -p' },
    { source: 'meta-learner', target: 'gap-signals-db', label: 'POST' },
    { source: 'gap-signals-db', target: 'main-turn', label: 'GET pending' },
    { source: 'main-turn', target: 'strategy-builder', label: 'family=strategy' },
    { source: 'main-turn', target: 'skill-architect', label: 'family=at-*' },
    { source: 'strategy-builder', target: 'strategies-dir', label: 'Write' },
    { source: 'strategy-builder', target: 'audition-db', label: 'POST audition' },
    { source: 'skill-architect', target: 'skills-dir', label: 'Write' },

    // Weekly SAS flow
    { source: 'cron-weekly', target: 'audition-judge', label: 'claude -p' },
    { source: 'audition-db', target: 'audition-judge', label: 'GET audition' },
    { source: 'audition-judge', target: 'audition-db', label: 'PATCH winner/eliminated' },
    { source: 'audition-judge', target: 'graveyard', label: 'mv eliminated' },

    // Monthly SAS flow
    { source: 'cron-monthly', target: 'monthly-resurrect', label: 'claude -p' },
    { source: 'graveyard', target: 'monthly-resurrect', label: 'scan eligible' },
    { source: 'monthly-resurrect', target: 'audition-db', label: 'PATCH resurrected' },

    // Self-critic emission path
    { source: 'user-request', target: 'self-critic', label: 'on-demand' },
    { source: 'self-critic', target: 'gap-signals-db', label: 'POST' },

    // Consumer integration
    { source: 'skills-dir', target: 'risk-manager', label: 'margin_exhaustion' },
];

function buildGraph(data) {
    const stats = data?.node_stats || {};
    const flow = data?.edge_flow || {};

    const nodes = NODE_DEFS.map(def => {
        const ns = stats[def.id] || {};
        return {
            id: def.id,
            type: 'workflowNode',
            position: { x: def.x, y: def.y },
            data: {
                type: def.type,
                label: def.label,
                sub: def.sub,
                count: ns.count || 0,
                lastStatus: ns.last_status || null,
                lastRunAt: ns.last_run_at || null,
            },
        };
    });

    const edges = EDGE_DEFS.map(def => {
        const key = `${def.source}->${def.target}`;
        const count = flow[key] || 0;
        const isActive = count > 0;
        return {
            id: key,
            source: def.source,
            target: def.target,
            label: count > 0 ? `${def.label} (${count})` : def.label,
            animated: isActive,
            style: {
                stroke: isActive ? '#60a5fa' : '#52525b',
                strokeWidth: isActive ? 2 : 1,
            },
            labelStyle: {
                fill: isActive ? '#93c5fd' : '#71717a',
                fontSize: 10,
                fontFamily: 'monospace',
            },
            labelBgStyle: { fill: '#0a0a0f', fillOpacity: 0.8 },
        };
    });

    return { nodes, edges };
}

function Legend() {
    return (
        <div className="bg-black/40 border border-white/10 rounded-lg p-3 text-xs space-y-1">
            <div className="text-white/80 font-semibold mb-2">Legend</div>
            <div className="flex items-center gap-2">
                <span className="inline-block w-3 h-3 rounded-sm border-2 border-blue-500 bg-blue-500/15" />
                <span className="text-white/60">trigger</span>
            </div>
            <div className="flex items-center gap-2">
                <span className="inline-block w-3 h-3 rounded-sm border-2 border-emerald-500 bg-emerald-500/15" />
                <span className="text-white/60">agent</span>
            </div>
            <div className="flex items-center gap-2">
                <span className="inline-block w-3 h-3 rounded-sm border-2 border-orange-500 bg-orange-500/15" />
                <span className="text-white/60">router</span>
            </div>
            <div className="flex items-center gap-2">
                <span className="inline-block w-3 h-3 rounded-sm border-2 border-slate-500 bg-slate-500/15" />
                <span className="text-white/60">data store</span>
            </div>
            <div className="flex items-center gap-2">
                <span className="inline-block w-3 h-3 rounded-sm border-2 border-purple-500 bg-purple-500/15" />
                <span className="text-white/60">file</span>
            </div>
            <div className="pt-2 border-t border-white/10 mt-2">
                <div className="text-white/60">
                    <span className="text-blue-400">◆</span> active edges animate
                </div>
                <div className="text-white/60">
                    count 0 → dimmed
                </div>
            </div>
        </div>
    );
}

function TimelineStrip({ events }) {
    if (!events || events.length === 0) {
        return (
            <div className="text-xs text-white/40 text-center py-6">
                No activity in the selected window
            </div>
        );
    }
    return (
        <div className="space-y-1 max-h-64 overflow-y-auto text-xs font-mono">
            {events.map((e, i) => {
                const ts = e.timestamp ? new Date(e.timestamp).toLocaleString() : '—';
                const statusColor = {
                    success: 'text-emerald-400',
                    consumed: 'text-emerald-400',
                    created: 'text-blue-400',
                    winner: 'text-yellow-400',
                    eliminated: 'text-red-400',
                    failed: 'text-red-400',
                    error: 'text-red-400',
                    rejected: 'text-red-400',
                    resurrected: 'text-amber-400',
                }[e.status] || 'text-white/60';
                return (
                    <div key={i} className="flex gap-3 py-1 border-b border-white/5">
                        <span className="text-white/40 w-40 shrink-0">{ts}</span>
                        <span className={`${statusColor} w-24 shrink-0`}>{e.status || '—'}</span>
                        <span className="text-white/50 w-32 shrink-0">{e.node}</span>
                        <span className="text-white/80 flex-1 truncate">{e.label}</span>
                    </div>
                );
            })}
        </div>
    );
}

export default function Workflow() {
    const [data, setData] = useState(null);
    const [error, setError] = useState(null);
    const [loading, setLoading] = useState(true);
    const [days, setDays] = useState(7);
    const [nodes, setNodes, onNodesChange] = useNodesState([]);
    const [edges, setEdges, onEdgesChange] = useEdgesState([]);

    const load = useCallback(async () => {
        try {
            const result = await fetchRecentExecutions({ days });
            setData(result);
            setError(null);
        } catch (e) {
            setError(e?.message || 'Failed to load workflow data');
        } finally {
            setLoading(false);
        }
    }, [days]);

    useEffect(() => {
        let alive = true;
        load().then(() => { if (!alive) return; });
        const interval = setInterval(() => {
            if (alive) load();
        }, 60000);
        return () => { alive = false; clearInterval(interval); };
    }, [load]);

    useEffect(() => {
        if (!data) return;
        const graph = buildGraph(data);
        setNodes(graph.nodes);
        setEdges(graph.edges);
    }, [data, setNodes, setEdges]);

    const totals = data?.totals;
    const timeRange = data?.time_range;

    if (loading && !data) {
        return <div className="text-center text-gray-400 py-12">Loading workflow...</div>;
    }
    if (error) {
        return <div className="text-center text-red-400 py-12">Error: {error}</div>;
    }

    return (
        <div className="space-y-4">
            {/* Header */}
            <div className="flex items-start justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-white">Agent Workflow — Live Execution</h1>
                    <p className="text-sm text-gray-400 mt-1">
                        SAS + gap_signal 파이프라인 실시간 시각화 (READ-ONLY, 60초 auto-refresh)
                    </p>
                </div>
                <div className="flex items-center gap-2">
                    <span className="text-xs text-gray-400">Window:</span>
                    {[1, 7, 30].map(d => (
                        <button
                            key={d}
                            onClick={() => setDays(d)}
                            className={`px-3 py-1 text-xs rounded border transition ${
                                days === d
                                    ? 'bg-blue-600 border-blue-500 text-white'
                                    : 'bg-white/5 border-white/10 text-gray-400 hover:text-white hover:border-white/30'
                            }`}
                        >
                            {d}d
                        </button>
                    ))}
                </div>
            </div>

            {/* Summary bar */}
            {totals && (
                <div className="flex gap-4 text-xs">
                    <div className="bg-black/30 border border-white/10 rounded px-3 py-2">
                        <span className="text-gray-500">Window: </span>
                        <span className="text-white font-mono">{timeRange?.days || days}d</span>
                    </div>
                    <div className="bg-black/30 border border-white/10 rounded px-3 py-2">
                        <span className="text-gray-500">gap_signals: </span>
                        <span className="text-white font-mono">{totals.gap_signals_in_window}</span>
                    </div>
                    <div className="bg-black/30 border border-white/10 rounded px-3 py-2">
                        <span className="text-gray-500">auditions: </span>
                        <span className="text-white font-mono">{totals.auditions_in_window}</span>
                    </div>
                </div>
            )}

            {/* ReactFlow graph */}
            <div className="bg-black/30 border border-white/10 rounded-lg overflow-hidden">
                <div style={{ width: '100%', height: 600 }}>
                    <ReactFlow
                        nodes={nodes}
                        edges={edges}
                        nodeTypes={nodeTypes}
                        onNodesChange={onNodesChange}
                        onEdgesChange={onEdgesChange}
                        fitView
                        minZoom={0.3}
                        maxZoom={1.5}
                        proOptions={{ hideAttribution: true }}
                    >
                        <Background color="#27272a" gap={16} />
                        <Controls className="!bg-black/60 !border-white/10" />
                        <MiniMap
                            nodeColor={(n) => {
                                const t = n.data?.type;
                                return {
                                    trigger: '#3b82f6',
                                    agent: '#10b981',
                                    router: '#f97316',
                                    datastore: '#64748b',
                                    file: '#a855f7',
                                }[t] || '#71717a';
                            }}
                            maskColor="rgba(0,0,0,0.7)"
                            className="!bg-black/60 !border !border-white/10"
                        />
                    </ReactFlow>
                </div>
            </div>

            {/* Legend + Timeline */}
            <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
                <div className="lg:col-span-1">
                    <Legend />
                </div>
                <div className="lg:col-span-3 bg-black/30 border border-white/10 rounded-lg p-3">
                    <div className="text-sm font-semibold text-white mb-2">
                        Recent Timeline ({data?.timeline?.length || 0})
                    </div>
                    <TimelineStrip events={data?.timeline} />
                </div>
            </div>

            <div className="text-xs text-gray-500 text-center pt-2">
                READ-ONLY. 모든 실행은 PM2 cron + main-turn 에이전트가 수행 (CIO-20260408-016 Level 2).
            </div>
        </div>
    );
}
