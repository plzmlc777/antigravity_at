// Sticky KPI gauge: monthly compound return vs 12%/mo target.
// Polls /api/v1/live/monitor/goal/progress every 30s. Compact pill format for navbar.
import { useEffect, useState } from 'react';
import { fetchGoalProgress } from '../api/agentsMeta';

const POLL_MS = 30000;

export default function KpiGoalHeader() {
    const [data, setData] = useState(null);
    const [err, setErr] = useState(null);

    useEffect(() => {
        let alive = true;
        const load = async () => {
            try {
                const d = await fetchGoalProgress();
                if (alive) { setData(d); setErr(null); }
            } catch (e) {
                if (alive) setErr(e?.message || 'fetch failed');
            }
        };
        load();
        const t = setInterval(load, POLL_MS);
        return () => { alive = false; clearInterval(t); };
    }, []);

    if (err && !data) {
        return (
            <div className="px-3 py-1.5 rounded-md bg-red-500/10 border border-red-500/30 text-xs text-red-300">
                KPI N/A
            </div>
        );
    }
    if (!data) {
        return (
            <div className="px-3 py-1.5 rounded-md bg-white/5 border border-white/10 text-xs text-gray-400">
                KPI loading…
            </div>
        );
    }

    const target = data.target_monthly_pct ?? 12;
    const current = data.monthly_return_pct ?? 0;
    const progress = Math.max(0, Math.min(100, data.progress_pct ?? 0));
    const isPositive = current >= 0;
    const isOnTrack = current >= target;
    const barColor = isOnTrack
        ? 'bg-emerald-500'
        : isPositive
            ? 'bg-blue-500'
            : 'bg-red-500';
    const textColor = isOnTrack
        ? 'text-emerald-300'
        : isPositive
            ? 'text-blue-300'
            : 'text-red-300';

    return (
        <div className="flex items-center gap-3 px-3 py-1.5 rounded-md bg-white/5 border border-white/10"
            title={`월 PnL: ${data.monthly_pnl_krw?.toLocaleString()} KRW · 세션 ${data.session_count}개 · target ${target}%/월 복리`}>
            <span className="text-[10px] uppercase tracking-wider text-gray-500">KPI</span>
            <div className="flex flex-col gap-0.5 min-w-[120px]">
                <div className="flex items-baseline gap-1">
                    <span className={`text-sm font-bold ${textColor}`}>{current.toFixed(2)}%</span>
                    <span className="text-[10px] text-gray-500">/ {target.toFixed(0)}%</span>
                </div>
                <div className="w-full h-1 bg-white/10 rounded-full overflow-hidden">
                    <div className={`h-full ${barColor} transition-all`} style={{ width: `${progress}%` }} />
                </div>
            </div>
        </div>
    );
}
