import React, { useCallback } from 'react';
import ReactFlow, {
    Background,
    Controls,
    useNodesState,
    useEdgesState,
    MarkerType
} from 'reactflow';
import 'reactflow/dist/style.css';

const initialNodes = [
    { id: '1', data: { label: 'Market Data' }, position: { x: 100, y: 100 }, type: 'input' },
    { id: '2', data: { label: 'Strategy' }, position: { x: 300, y: 100 } },
    { id: '3', data: { label: 'Execution' }, position: { x: 500, y: 100 } },
    { id: '4', data: { label: 'Kiwoom API' }, position: { x: 500, y: 200 }, type: 'output' },
];

const initialEdges = [
    { id: 'e1-2', source: '1', target: '2', animated: true, markerEnd: { type: MarkerType.ArrowClosed } },
    { id: 'e2-3', source: '2', target: '3', animated: true, markerEnd: { type: MarkerType.ArrowClosed } },
    { id: 'e3-4', source: '3', target: '4', animated: true, markerEnd: { type: MarkerType.ArrowClosed } },
];

const Diagram = () => {
    const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
    const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

    return (
        <div className="h-[300px] w-full border border-white/10 rounded-xl bg-black/20 overflow-hidden">
            <ReactFlow
                nodes={nodes}
                edges={edges}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                fitView
            >
                <Background gap={12} size={1} />
                <Controls />
            </ReactFlow>
        </div>
    );
};

export default Diagram;
