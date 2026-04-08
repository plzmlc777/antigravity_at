// Agent Org Chart — answers user's request: "에이전트 흐름과 스킬 구조를 한눈에"
// React Flow renders 16 agents in 7 role columns. Skill cards at bottom highlight users.
import { useEffect, useMemo, useState, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import ReactFlow, {
    Background,
    Controls,
    MiniMap,
    useNodesState,
    useEdgesState,
} from 'reactflow';
import 'reactflow/dist/style.css';

import { fetchAgents, fetchSkills } from '../api/agentsMeta';
import AgentNode, { ColumnLabelNode } from '../components/org/AgentNode';
import SkillCard from '../components/org/SkillCard';
import AgentDetailDrawer from '../components/org/AgentDetailDrawer';
import { buildOrgGraph, getSkillUsers } from '../components/org/orgLayout';

const nodeTypes = {
    agentNode: AgentNode,
    columnLabel: ColumnLabelNode,
};

export default function Organization() {
    const [agents, setAgents] = useState([]);
    const [skills, setSkills] = useState([]);
    const [loading, setLoading] = useState(true);
    const [err, setErr] = useState(null);
    const [activeSkill, setActiveSkill] = useState(null);
    const [searchParams, setSearchParams] = useSearchParams();
    const selectedAgent = searchParams.get('agent');

    useEffect(() => {
        let alive = true;
        Promise.all([fetchAgents(), fetchSkills()])
            .then(([a, s]) => {
                if (!alive) return;
                setAgents(a);
                setSkills(s);
            })
            .catch(e => { if (alive) setErr(e?.message || 'load failed'); })
            .finally(() => { if (alive) setLoading(false); });
        return () => { alive = false; };
    }, []);

    const baseGraph = useMemo(() => buildOrgGraph(agents), [agents]);

    const [nodes, setNodes, onNodesChange] = useNodesState([]);
    const [edges, setEdges, onEdgesChange] = useEdgesState([]);

    // Sync base graph to state when data loads
    useEffect(() => {
        setNodes(baseGraph.nodes);
        setEdges(baseGraph.edges);
    }, [baseGraph, setNodes, setEdges]);

    // Highlight nodes when a skill is active
    useEffect(() => {
        if (!activeSkill) {
            setNodes(nds => nds.map(n => ({ ...n, data: { ...n.data, highlighted: false } })));
            return;
        }
        const users = new Set(getSkillUsers(activeSkill.name));
        setNodes(nds => nds.map(n => ({
            ...n,
            data: { ...n.data, highlighted: users.has(n.id) },
        })));
    }, [activeSkill, setNodes]);

    const handleNodeClick = useCallback((_evt, node) => {
        if (node.type !== 'agentNode' || node.id === 'user') return;
        setSearchParams({ agent: node.id });
    }, [setSearchParams]);

    const handleSkillClick = useCallback((skill) => {
        setActiveSkill(prev => (prev?.name === skill.name ? null : skill));
    }, []);

    const closeDrawer = useCallback(() => {
        searchParams.delete('agent');
        setSearchParams(searchParams);
    }, [searchParams, setSearchParams]);

    return (
        <div className="space-y-4">
            <div className="flex items-end justify-between">
                <div>
                    <h1 className="text-3xl font-bold tracking-tight">조직도</h1>
                    <p className="text-sm text-gray-400 mt-1">
                        {agents.length}개 에이전트 · {skills.length}개 스킬 · 노드 클릭 = 상세, 스킬 클릭 = 사용자 강조
                    </p>
                </div>
                <div className="flex items-center gap-3 text-[11px] text-gray-400">
                    <Legend swatch="bg-purple-500/40 border-purple-500" label="opus" />
                    <Legend swatch="bg-blue-500/40 border-blue-500" label="sonnet" />
                    <Legend swatch="bg-gray-500/40 border-gray-500" label="haiku" />
                    <Legend swatch="bg-red-500/20 border-red-500" label="VETO" />
                </div>
            </div>

            {err && (
                <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-300 text-sm">
                    {err}
                </div>
            )}

            {/* React Flow chart */}
            <div className="h-[560px] rounded-lg border border-white/10 bg-[#06060a]">
                <ReactFlow
                    nodes={nodes}
                    edges={edges}
                    onNodesChange={onNodesChange}
                    onEdgesChange={onEdgesChange}
                    onNodeClick={handleNodeClick}
                    nodeTypes={nodeTypes}
                    fitView
                    fitViewOptions={{ padding: 0.15 }}
                    minZoom={0.3}
                    maxZoom={1.5}
                    proOptions={{ hideAttribution: true }}
                >
                    <Background color="#1a1a2e" gap={20} />
                    <Controls className="!bg-white/5 !border-white/10" />
                    <MiniMap
                        nodeColor="#3b82f6"
                        maskColor="rgba(0,0,0,0.6)"
                        className="!bg-[#06060a] !border !border-white/10"
                    />
                </ReactFlow>
            </div>

            {/* Skills panel */}
            <section>
                <div className="flex items-center justify-between mb-2">
                    <h2 className="text-sm font-semibold text-gray-300">스킬 (at-*)</h2>
                    {activeSkill && (
                        <button
                            onClick={() => setActiveSkill(null)}
                            className="text-[11px] text-amber-300 hover:text-amber-200"
                        >
                            강조 해제 ✕
                        </button>
                    )}
                </div>
                {loading ? (
                    <div className="text-sm text-gray-500">스킬 로딩 중…</div>
                ) : (
                    <div className="flex gap-3 overflow-x-auto pb-2">
                        {skills.map(s => (
                            <SkillCard
                                key={s.name}
                                skill={s}
                                active={activeSkill?.name === s.name}
                                onClick={handleSkillClick}
                            />
                        ))}
                    </div>
                )}
            </section>

            {/* Detail drawer */}
            <AgentDetailDrawer agentName={selectedAgent} onClose={closeDrawer} />
        </div>
    );
}

function Legend({ swatch, label }) {
    return (
        <div className="flex items-center gap-1">
            <span className={`inline-block w-3 h-3 rounded-sm border ${swatch}`} />
            <span>{label}</span>
        </div>
    );
}
