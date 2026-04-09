// Calibration Dashboard — SISDS Phase 7 (CIO-20260410-001 / CIO-017).
//
// The answer to "Is the system improving?" lives here.
// CIR (Calibration Improvement Rate) > 0 means predictions are getting more accurate.
// READ-ONLY. No manual actions.
import { useEffect, useState } from 'react';
import { fetchCalibrationSummary, fetchCalibrationTrend, fetchCalibrationRecent, fetchWorstStrategies } from '../api/calibration';

const HEALTH_COLORS = {
    excellent: 'text-emerald-400',
    good: 'text-blue-400',
    fair: 'text-yellow-400',
    poor: 'text-red-400',
    no_data: 'text-gray-500',
};

const CIR_COLORS = {
    improving: 'text-emerald-400',
    stable: 'text-yellow-400',
    declining: 'text-red-400',
    insufficient_data: 'text-gray-500',
};

function BigMetric({ label, value, unit, color, hint }) {
    return (
        <div className="bg-black/30 border border-white/10 rounded-lg p-5 text-center">
            <div className="text-xs text-gray-400 uppercase tracking-wider">{label}</div>
            <div className={`text-4xl font-bold mt-2 ${color || 'text-white'}`}>
                {value ?? '—'}{unit && <span className="text-lg text-gray-400 ml-1">{unit}</span>}
            </div>
            {hint && <div className="text-xs text-gray-500 mt-2">{hint}</div>}
        </div>
    );
}

function TrendChart({ monthlyAvg }) {
    if (!monthlyAvg || Object.keys(monthlyAvg).length === 0) {
        return (
            <div className="bg-black/30 border border-white/10 rounded-lg p-6 text-center text-gray-500 text-sm">
                Trend data will appear after strategies complete stage transitions (sandbox → paper → live).
            </div>
        );
    }
    const months = Object.keys(monthlyAvg).sort();
    const values = months.map(m => monthlyAvg[m]);
    const maxVal = Math.max(...values.filter(v => v != null), 1);

    return (
        <div className="bg-black/30 border border-white/10 rounded-lg p-4">
            <div className="text-sm font-semibold text-white mb-3">
                Monthly Calibration Error Trend
                <span className="text-xs text-gray-500 ml-2">(lower = better)</span>
            </div>
            <div className="flex items-end gap-2 h-40">
                {months.map((m, i) => {
                    const v = values[i];
                    if (v == null) return null;
                    const h = Math.max(4, (v / maxVal) * 100);
                    const color = v < 0.2 ? 'bg-emerald-500' : v < 0.35 ? 'bg-blue-500' : v < 0.5 ? 'bg-yellow-500' : 'bg-red-500';
                    return (
                        <div key={m} className="flex-1 flex flex-col items-center gap-1">
                            <div className="text-[9px] text-gray-400 font-mono">{(v * 100).toFixed(0)}%</div>
                            <div className={`w-full rounded-t ${color}`} style={{ height: `${h}%` }} title={`${m}: ${(v * 100).toFixed(1)}%`} />
                            <div className="text-[9px] text-gray-500 font-mono">{m.slice(5)}</div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}

function WorstTable({ strategies }) {
    if (!strategies || strategies.length === 0) {
        return (
            <div className="bg-black/30 border border-white/10 rounded-lg p-6 text-center text-gray-500 text-sm">
                No calibration data for individual strategies yet.
            </div>
        );
    }
    return (
        <div className="bg-black/30 border border-white/10 rounded-lg overflow-hidden">
            <div className="text-sm font-semibold text-white p-3 border-b border-white/10">
                Worst Calibrated Strategies
                <span className="text-xs text-gray-500 ml-2">(fix these first)</span>
            </div>
            <table className="w-full text-sm">
                <thead className="bg-white/5 border-b border-white/10">
                    <tr>
                        <th className="px-4 py-2 text-left text-xs text-gray-400">Strategy</th>
                        <th className="px-4 py-2 text-right text-xs text-gray-400">Avg Error</th>
                        <th className="px-4 py-2 text-right text-xs text-gray-400">Records</th>
                    </tr>
                </thead>
                <tbody>
                    {strategies.map(s => {
                        const errPct = (s.avg_calibration_error * 100).toFixed(1);
                        const color = s.avg_calibration_error < 0.2 ? 'text-emerald-400' : s.avg_calibration_error < 0.35 ? 'text-blue-400' : s.avg_calibration_error < 0.5 ? 'text-yellow-400' : 'text-red-400';
                        return (
                            <tr key={s.strategy_id} className="border-b border-white/5">
                                <td className="px-4 py-2 font-mono text-white">{s.strategy_id}</td>
                                <td className={`px-4 py-2 text-right font-mono ${color}`}>{errPct}%</td>
                                <td className="px-4 py-2 text-right text-gray-400">{s.record_count}</td>
                            </tr>
                        );
                    })}
                </tbody>
            </table>
        </div>
    );
}

function RecentRecords({ records }) {
    if (!records || records.length === 0) return null;
    return (
        <div className="bg-black/30 border border-white/10 rounded-lg overflow-hidden">
            <div className="text-sm font-semibold text-white p-3 border-b border-white/10">
                Recent Calibration Records ({records.length})
            </div>
            <div className="max-h-64 overflow-y-auto">
                <table className="w-full text-xs">
                    <thead className="bg-white/5 border-b border-white/10 sticky top-0">
                        <tr>
                            <th className="px-3 py-1.5 text-left text-gray-400">Date</th>
                            <th className="px-3 py-1.5 text-left text-gray-400">Strategy</th>
                            <th className="px-3 py-1.5 text-left text-gray-400">Transition</th>
                            <th className="px-3 py-1.5 text-right text-gray-400">Error</th>
                            <th className="px-3 py-1.5 text-left text-gray-400">Resolution</th>
                        </tr>
                    </thead>
                    <tbody>
                        {records.map(r => (
                            <tr key={r.id} className="border-b border-white/5">
                                <td className="px-3 py-1.5 text-gray-500 font-mono">{r.measured_at?.slice(0, 10)}</td>
                                <td className="px-3 py-1.5 text-white font-mono">{r.strategy_id}</td>
                                <td className="px-3 py-1.5 text-gray-400">{r.transition}</td>
                                <td className="px-3 py-1.5 text-right font-mono text-yellow-400">{(r.calibration_error * 100).toFixed(1)}%</td>
                                <td className="px-3 py-1.5 text-gray-500">{r.resolution || '—'}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
}

export default function Calibration() {
    const [summary, setSummary] = useState(null);
    const [trend, setTrend] = useState(null);
    const [records, setRecords] = useState([]);
    const [worst, setWorst] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    useEffect(() => {
        let alive = true;
        async function load() {
            try {
                const [s, t, r, w] = await Promise.all([
                    fetchCalibrationSummary(),
                    fetchCalibrationTrend({ months: 6 }),
                    fetchCalibrationRecent({ days: 90, limit: 50 }),
                    fetchWorstStrategies({ limit: 10 }),
                ]);
                if (!alive) return;
                setSummary(s);
                setTrend(t);
                setRecords(r);
                setWorst(w);
            } catch (e) {
                if (alive) setError(e?.message || 'Failed to load calibration data');
            } finally {
                if (alive) setLoading(false);
            }
        }
        load();
        const interval = setInterval(load, 120000); // 2 min refresh
        return () => { alive = false; clearInterval(interval); };
    }, []);

    if (loading) return <div className="text-gray-400 text-center py-12">Loading calibration data...</div>;
    if (error) return <div className="text-red-400 text-center py-12">Error: {error}</div>;

    const healthColor = HEALTH_COLORS[summary?.health] || 'text-gray-500';
    const cirColor = CIR_COLORS[trend?.interpretation] || 'text-gray-500';
    const avgErrorPct = summary?.overall_avg_error != null ? (summary.overall_avg_error * 100).toFixed(1) : null;
    const recentErrorPct = summary?.recent_30d_avg_error != null ? (summary.recent_30d_avg_error * 100).toFixed(1) : null;
    const cirPct = trend?.overall_cir != null ? (trend.overall_cir * 100).toFixed(1) : null;

    return (
        <div className="space-y-6">
            <div>
                <h1 className="text-2xl font-bold text-white">Calibration Dashboard</h1>
                <p className="text-sm text-gray-400 mt-1">
                    "시스템이 발전하고 있는가?" — 예측 정확도가 시간에 따라 개선되는지 측정 (SISDS Phase 7, READ-ONLY)
                </p>
            </div>

            {/* Big metrics */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <BigMetric
                    label="System Health"
                    value={summary?.health?.toUpperCase() || '—'}
                    color={healthColor}
                    hint={summary?.total_records ? `Based on ${summary.total_records} records` : 'No data yet'}
                />
                <BigMetric
                    label="Overall Avg Error"
                    value={avgErrorPct}
                    unit="%"
                    color={avgErrorPct && parseFloat(avgErrorPct) < 20 ? 'text-emerald-400' : avgErrorPct && parseFloat(avgErrorPct) < 35 ? 'text-blue-400' : 'text-yellow-400'}
                    hint="Lower is better. < 20% = excellent"
                />
                <BigMetric
                    label="Recent 30d Error"
                    value={recentErrorPct}
                    unit="%"
                    color={recentErrorPct && parseFloat(recentErrorPct) < 20 ? 'text-emerald-400' : 'text-yellow-400'}
                    hint="Recent accuracy. Compare with overall"
                />
                <BigMetric
                    label="CIR"
                    value={cirPct != null ? `${parseFloat(cirPct) > 0 ? '+' : ''}${cirPct}` : '—'}
                    unit="%"
                    color={cirColor}
                    hint={trend?.interpretation === 'improving' ? 'Predictions improving!' : trend?.interpretation === 'declining' ? 'Predictions worsening' : 'Calibration Improvement Rate'}
                />
            </div>

            {/* Trend chart */}
            <TrendChart monthlyAvg={trend?.monthly_avg_error} />

            {/* Bottom grid: worst + recent */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <WorstTable strategies={worst} />
                <RecentRecords records={records} />
            </div>

            {/* By transition */}
            {summary?.by_transition && Object.keys(summary.by_transition).length > 0 && (
                <div className="bg-black/30 border border-white/10 rounded-lg p-4">
                    <div className="text-sm font-semibold text-white mb-2">Error by Transition Type</div>
                    <div className="flex gap-4 text-xs">
                        {Object.entries(summary.by_transition).map(([t, v]) => (
                            <div key={t} className="bg-white/5 rounded px-3 py-2">
                                <div className="text-gray-400 font-mono">{t}</div>
                                <div className="text-white font-bold">{(v.avg_error * 100).toFixed(1)}%</div>
                                <div className="text-gray-500">{v.count} records</div>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            <div className="text-xs text-gray-500 text-center pt-2">
                READ-ONLY. Calibration records are auto-generated by paper-scheduler and live-monitor. CIR {'>'} 0 for 3 months = system is self-improving. (CIO-017 Phase 7)
            </div>
        </div>
    );
}
