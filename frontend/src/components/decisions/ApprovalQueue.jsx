// Pending approvals queue — wired to /api/v1/approvals.
import { useEffect, useState, useCallback } from 'react';
import { fetchApprovals, resolveApproval } from '../../api/agentsMeta';

export default function ApprovalQueue() {
    const [items, setItems] = useState([]);
    const [loading, setLoading] = useState(true);
    const [err, setErr] = useState(null);
    const [statusFilter, setStatusFilter] = useState('pending'); // pending | all
    const [busyId, setBusyId] = useState(null);

    const load = useCallback(async () => {
        setLoading(true);
        try {
            const d = await fetchApprovals(statusFilter);
            setItems(d || []);
            setErr(null);
        } catch (e) {
            setErr(e?.message || 'load failed');
        } finally {
            setLoading(false);
        }
    }, [statusFilter]);

    useEffect(() => { load(); }, [load]);

    const handleResolve = async (id, decision) => {
        setBusyId(id);
        try {
            await resolveApproval(id, decision);
            await load();
        } catch (e) {
            setErr(e?.response?.data?.detail || e?.message || 'resolve failed');
        } finally {
            setBusyId(null);
        }
    };

    return (
        <div className="space-y-3">
            <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold text-gray-300">승인 대기열</h2>
                <div className="flex gap-1">
                    <FilterBtn active={statusFilter === 'pending'} onClick={() => setStatusFilter('pending')}>
                        대기 중
                    </FilterBtn>
                    <FilterBtn active={statusFilter === 'all'} onClick={() => setStatusFilter('all')}>
                        전체
                    </FilterBtn>
                </div>
            </div>

            {err && (
                <div className="p-2 rounded bg-red-500/10 border border-red-500/30 text-xs text-red-300">
                    {err}
                </div>
            )}

            {loading ? (
                <div className="text-sm text-gray-500">로딩 중…</div>
            ) : items.length === 0 ? (
                <div className="p-4 rounded-lg bg-white/5 border border-white/10 text-sm text-gray-500 italic text-center">
                    {statusFilter === 'pending'
                        ? '대기 중인 승인 요청이 없습니다.'
                        : '승인 요청이 없습니다.'}
                </div>
            ) : (
                items.map(a => (
                    <ApprovalRow
                        key={a.id}
                        approval={a}
                        busy={busyId === a.id}
                        onResolve={handleResolve}
                    />
                ))
            )}
        </div>
    );
}

function ApprovalRow({ approval, busy, onResolve }) {
    const isPending = approval.status === 'pending';
    const statusBadge = {
        pending: 'bg-amber-500/20 text-amber-300 border-amber-500/40',
        approved: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40',
        rejected: 'bg-red-500/20 text-red-300 border-red-500/40',
    }[approval.status] || 'bg-white/10 text-gray-400';

    return (
        <div className={`p-3 rounded-lg bg-white/5 border ${isPending ? 'border-amber-500/30' : 'border-white/10'}`}>
            <div className="flex items-center justify-between gap-2 mb-1">
                <span className="text-[10px] text-gray-500 font-mono">
                    {approval.decision_id || `#${approval.id}`}
                </span>
                <div className="flex items-center gap-2">
                    <span className={`text-[10px] px-1.5 py-0.5 rounded border ${statusBadge}`}>
                        {approval.status}
                    </span>
                    <span className="text-[10px] text-gray-500">
                        {new Date(approval.created_at).toLocaleString()}
                    </span>
                </div>
            </div>
            <div className="text-sm font-semibold text-white">{approval.action}</div>
            {approval.rationale && (
                <p className="text-xs text-gray-400 mt-1 whitespace-pre-line">{approval.rationale}</p>
            )}
            {approval.resolved_by && (
                <div className="mt-2 text-[11px] text-gray-500">
                    by <span className="text-gray-300">{approval.resolved_by}</span>
                    {approval.resolution_note && <> · {approval.resolution_note}</>}
                </div>
            )}
            {isPending && (
                <div className="mt-3 flex gap-2">
                    <button
                        disabled={busy}
                        onClick={() => onResolve(approval.id, 'approve')}
                        className="px-3 py-1 rounded bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium disabled:opacity-50"
                    >
                        승인
                    </button>
                    <button
                        disabled={busy}
                        onClick={() => onResolve(approval.id, 'reject')}
                        className="px-3 py-1 rounded bg-red-600 hover:bg-red-500 text-white text-xs font-medium disabled:opacity-50"
                    >
                        거부
                    </button>
                </div>
            )}
        </div>
    );
}

function FilterBtn({ active, onClick, children }) {
    return (
        <button
            onClick={onClick}
            className={`px-2 py-1 rounded text-xs transition ${
                active ? 'bg-blue-600 text-white' : 'bg-white/5 text-gray-400 hover:text-white'
            }`}
        >
            {children}
        </button>
    );
}
