// Pending approvals queue. Backend table not yet implemented — uses mock data
// gated behind an env-style flag so the UI surface exists for review.
// When the real /api/v1/approvals endpoint lands, swap MOCK_APPROVALS for fetch.

const MOCK_APPROVALS = [
    {
        id: 'mock-1',
        decision_id: 'CIO-20260408-001',
        action: '실거래 전환 (RIVERUSDT)',
        rationale: 'risk-manager: KPI 복리 8.37% (목표 12% 미달, gap 3.63pp). 사용자 확인 필요.',
        created_at: '2026-04-08T01:30:00Z',
    },
    {
        id: 'mock-2',
        decision_id: 'CIO-20260408-002',
        action: '레버리지 5x → 10x 상향 (BTCUSDT)',
        rationale: 'risk-manager: 레버리지 정책 (futures ≤5x) 위반. 명시 승인 필요.',
        created_at: '2026-04-08T02:15:00Z',
    },
];

export default function ApprovalQueue() {
    return (
        <div className="space-y-3">
            <div className="p-2 rounded bg-amber-500/10 border border-amber-500/30 text-[11px] text-amber-200">
                ⚠ Mock 데이터 표시 중. 실제 approval 백엔드는 후속 작업.
            </div>
            {MOCK_APPROVALS.map(a => (
                <div key={a.id} className="p-3 rounded-lg bg-white/5 border border-amber-500/30">
                    <div className="flex items-center justify-between gap-2 mb-1">
                        <span className="text-[10px] text-gray-500 font-mono">{a.decision_id}</span>
                        <span className="text-[10px] text-gray-500">{new Date(a.created_at).toLocaleString()}</span>
                    </div>
                    <div className="text-sm font-semibold text-white">{a.action}</div>
                    <p className="text-xs text-gray-400 mt-1">{a.rationale}</p>
                    <div className="mt-3 flex gap-2">
                        <button
                            disabled
                            className="px-3 py-1 rounded bg-emerald-600/40 text-emerald-200 text-xs cursor-not-allowed"
                        >
                            승인 (mock)
                        </button>
                        <button
                            disabled
                            className="px-3 py-1 rounded bg-red-600/40 text-red-200 text-xs cursor-not-allowed"
                        >
                            거부 (mock)
                        </button>
                    </div>
                </div>
            ))}
        </div>
    );
}
