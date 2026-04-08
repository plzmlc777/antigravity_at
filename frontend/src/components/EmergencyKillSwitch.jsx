// Emergency global kill switch — only manual write surface in the AI-centric UI.
// Two-step confirmation to prevent accidental clicks. Calls /api/v1/live/emergency-stop
// which halts every RUNNING session across all accounts.
import { useState } from 'react';

export default function EmergencyKillSwitch({ onTrigger, runningCount = 0 }) {
    const [armed, setArmed] = useState(false);
    const [busy, setBusy] = useState(false);
    const [result, setResult] = useState(null);
    const [err, setErr] = useState(null);

    const handleArm = () => {
        setArmed(true);
        setErr(null);
        setResult(null);
    };

    const handleCancel = () => {
        setArmed(false);
    };

    const handleConfirm = async () => {
        if (busy) return;
        setBusy(true);
        setErr(null);
        try {
            const r = await onTrigger();
            setResult(r);
            setArmed(false);
        } catch (e) {
            setErr(e?.response?.data?.detail || e?.message || 'kill switch failed');
        } finally {
            setBusy(false);
        }
    };

    if (result) {
        return (
            <div className="px-3 py-2 rounded-lg bg-red-500/10 border border-red-500/40 text-xs text-red-200">
                <div className="font-semibold">⚠ ALL STOP 실행됨</div>
                <div className="mt-0.5">
                    {result.stopped_count}개 정지 · {result.remaining_running}개 잔존
                </div>
                <button
                    onClick={() => setResult(null)}
                    className="mt-1 underline text-red-300 hover:text-white"
                >
                    닫기
                </button>
            </div>
        );
    }

    if (!armed) {
        return (
            <button
                onClick={handleArm}
                title="모든 라이브 세션 비상 정지 (AI 정책 우회)"
                className="px-3 py-2 rounded-lg border border-red-500/40 bg-red-500/10 hover:bg-red-500/20 text-red-300 text-xs font-semibold transition"
            >
                🛑 ALL STOP {runningCount > 0 && <span className="ml-1 px-1.5 rounded bg-red-500/30">{runningCount}</span>}
            </button>
        );
    }

    return (
        <div className="flex items-center gap-2 px-3 py-2 rounded-lg border-2 border-red-500/60 bg-red-500/15">
            <span className="text-xs text-red-200 font-semibold">
                ⚠ {runningCount}개 세션 즉시 정지?
            </span>
            <button
                disabled={busy}
                onClick={handleConfirm}
                className="px-2 py-1 rounded bg-red-600 hover:bg-red-500 text-white text-xs font-bold disabled:opacity-50"
            >
                {busy ? '정지 중…' : '확인'}
            </button>
            <button
                disabled={busy}
                onClick={handleCancel}
                className="px-2 py-1 rounded bg-white/10 hover:bg-white/20 text-gray-300 text-xs disabled:opacity-50"
            >
                취소
            </button>
            {err && <span className="text-xs text-red-300">{err}</span>}
        </div>
    );
}
