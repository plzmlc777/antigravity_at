/**
 * ParamSweepHeatmap — 파라미터 스윕 2D 지형도
 *
 * 설계: .claude/plans/param_sweep_heatmap_component.md
 *
 * **이건 예쁜 차트가 아니라 판정 도구다.** 유일한 목적은 파라미터 공간의
 * 지형을 보이게 하는 것 — 고원(plateau)인가 절벽(cliff)인가.
 *
 * 명시적 비목표(§1): 성과 홍보용 시각화 아님 · 최적점 자동 선택 아님 ·
 * 백테스트 실행 트리거 아님(읽기 전용).
 *
 * ⚠ 출처를 숨기지 않는다(§9). 히트맵은 숫자를 **설득력 있게** 만드는 도구라
 *   출처 없이 렌더하면 무효 데이터를 세탁한다. 경고 배지는 접을 수 없다.
 *
 * recharts 에 히트맵 프리미티브가 없어 **순수 SVG** 로 그린다(신규 의존성 금지).
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '../api/client';   // named export — default 는 없다
import {
  SWEEP_DIVERGING, SWEEP_SEQUENTIAL, SWEEP_FADE, SWEEP_LABEL_MAX, SWEEP_SIG_T,
} from '../config/chartConfig';

const CELL = 54;
const GAP = 2;          // §6.4 셀 사이 표면 간격
const PAD_L = 96;
const PAD_T = 30;

const fmt = (v, d = 1) =>
  v === null || v === undefined || Number.isNaN(v) ? '—' : Number(v).toFixed(d);

/** 발산 램프는 **0 에 고정**하고 max(|min|,|max|) 로 대칭 정규화한다(§6.1).
 *  분위수 스케일은 쓰지 않는다 — 극단값을 시각적으로 삭제한다. */
function colorFor(v, { diverging, absMax, max }) {
  if (v === null || v === undefined) return null;
  if (diverging) {
    if (!absMax) return SWEEP_DIVERGING[4];
    const mid = (SWEEP_DIVERGING.length - 1) / 2;
    const idx = Math.round(mid + (v / absMax) * mid);
    return SWEEP_DIVERGING[Math.max(0, Math.min(SWEEP_DIVERGING.length - 1, idx))];
  }
  if (!max) return SWEEP_SEQUENTIAL[0];
  const idx = Math.round((v / max) * (SWEEP_SEQUENTIAL.length - 1));
  return SWEEP_SEQUENTIAL[Math.max(0, Math.min(SWEEP_SEQUENTIAL.length - 1, idx))];
}

export default function ParamSweepHeatmap() {
  const [files, setFiles] = useState([]);
  const [file, setFile] = useState('');
  const [schema, setSchema] = useState(null);
  const [grid, setGrid] = useState(null);
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);

  const [x, setX] = useState('');
  const [y, setY] = useState('');
  const [metric, setMetric] = useState('');
  const [fixed, setFixed] = useState({});
  const [split, setSplit] = useState('');
  const [agg, setAgg] = useState('none');
  const [sigOnly, setSigOnly] = useState(false);
  const [showSlope, setShowSlope] = useState(false);
  const [asTable, setAsTable] = useState(false);
  const [hover, setHover] = useState(null);

  useEffect(() => {
    api.get('/research-track/files')
      .then(r => { setFiles(r.data.files || []); if (r.data.files?.[0]) setFile(r.data.files[0].file); })
      .catch(e => setErr(String(e?.message || e)));
  }, []);

  useEffect(() => {
    if (!file) return;
    setSchema(null); setGrid(null); setErr('');
    api.get(`/research-track/files/${encodeURIComponent(file)}/schema`)
      .then(r => {
        const s = r.data; setSchema(s);
        const ax = Object.keys(s.axes || {});
        setX(ax[0] || ''); setY(ax[1] || '');
        setMetric(s.metrics?.[0]?.name || '');
        setFixed({}); setSplit(s.split?.date ? 'IS' : '');
      })
      .catch(e => setErr(e?.response?.data?.detail || String(e?.message || e)));
  }, [file]);

  const load = useCallback(() => {
    if (!file || !x || !y || !metric || x === y) return;
    setBusy(true);
    const params = { x, y, metric, agg };
    const fixStr = Object.entries(fixed).filter(([, v]) => v !== '')
      .map(([k, v]) => `${k}:${v}`).join(',');
    if (fixStr) params.fix = fixStr;
    if (split) params.split = split;
    api.get(`/research-track/files/${encodeURIComponent(file)}/grid`, { params })
      .then(r => { setGrid(r.data); setErr(''); })
      .catch(e => setErr(e?.response?.data?.detail || String(e?.message || e)))
      .finally(() => setBusy(false));
  }, [file, x, y, metric, fixed, split, agg]);

  useEffect(() => { load(); }, [load]);

  const kind = useMemo(
    () => schema?.metrics?.find(m => m.name === metric) || {},
    [schema, metric]);

  const scale = useMemo(() => {
    if (!grid) return { diverging: false, absMax: 0, max: 0 };
    const vals = grid.cells.flat().filter(v => v !== null && v !== undefined);
    const absMax = Math.max(...vals.map(Math.abs), 0);
    return { diverging: kind.ramp === '발산', absMax, max: Math.max(...vals, 0) };
  }, [grid, kind]);

  /** 이웃 기울기(§8) — |셀값 - 이웃평균| / 전체 스케일. 크면 절벽. */
  const slope = useCallback((i, j) => {
    if (!grid) return 0;
    const at = (a, b) => grid.cells[a]?.[b];
    const nb = [at(i - 1, j), at(i + 1, j), at(i, j - 1), at(i, j + 1)]
      .filter(v => v !== null && v !== undefined);
    const v = at(i, j);
    if (!nb.length || v === null || v === undefined) return 0;
    const mean = nb.reduce((s, n) => s + n, 0) / nb.length;
    const span = scale.diverging ? scale.absMax * 2 : scale.max || 1;
    return span ? Math.abs(v - mean) / span : 0;
  }, [grid, scale]);

  const sigOf = (rec) => {
    const t = rec?.t;
    return t !== null && t !== undefined && Math.abs(t) >= SWEEP_SIG_T;
  };

  /** 헤더 요약(§8) — 최댓값 셀이 이웃 없이 홀로 서 있으면 절벽 경고 */
  const summary = useMemo(() => {
    if (!grid) return null;
    let best = null, sig = 0, total = 0;
    grid.cells.forEach((row, i) => row.forEach((v, j) => {
      if (v === null || v === undefined) return;
      total += 1;
      if (sigOf(grid.records?.[i]?.[j])) sig += 1;
      if (!best || v > best.v) best = { v, i, j };
    }));
    if (!best) return { sig, total, same: 0, nb: 0 };
    const at = (a, b) => grid.cells[a]?.[b];
    const nb = [at(best.i - 1, best.j), at(best.i + 1, best.j),
      at(best.i, best.j - 1), at(best.i, best.j + 1)]
      .filter(v => v !== null && v !== undefined);
    const same = nb.filter(v => v * best.v > 0).length;
    return { sig, total, same, nb: nb.length, best };
  }, [grid]);

  const W = grid ? PAD_L + grid.x_values.length * (CELL + GAP) + 20 : 0;
  const H = grid ? PAD_T + grid.y_values.length * (CELL + GAP) + 40 : 0;
  const labelCells = grid &&
    grid.x_values.length <= SWEEP_LABEL_MAX && grid.y_values.length <= SWEEP_LABEL_MAX;

  const otherAxes = useMemo(
    () => Object.keys(schema?.axes || {}).filter(a => a !== x && a !== y),
    [schema, x, y]);

  return (
    <div className="p-4 text-gray-200">
      <h2 className="text-lg font-semibold mb-1">파라미터 스윕 지형도</h2>
      <p className="text-xs text-gray-500 mb-3">
        고원인가 절벽인가를 보는 판정 도구입니다. 최적점을 자동으로 고르지 않습니다.
      </p>

      {/* ── 컨트롤 (§10.2) ───────────────────────────────────────── */}
      <div className="flex flex-wrap gap-2 items-end mb-3 text-sm">
        <Sel label="파일" value={file} onChange={setFile}
          options={files.map(f => [f.file, `${f.file} (${f.n_records})`])} />
        <Sel label="X축" value={x} onChange={setX}
          options={Object.keys(schema?.axes || {}).map(a => [a, a])} />
        <Sel label="Y축" value={y} onChange={setY}
          options={Object.keys(schema?.axes || {}).map(a => [a, a])} />
        <Sel label="지표" value={metric} onChange={setMetric}
          options={(schema?.metrics || []).map(m => [m.name, `${m.name} (${m.polarity})`])} />
        {schema?.split?.date && (
          <Sel label="표본" value={split} onChange={setSplit}
            options={[['IS', '표본 안'], ['OOS', '표본 밖']]} />
        )}
        {otherAxes.map(a => (
          <Sel key={a} label={`${a} 고정`} value={fixed[a] ?? ''}
            onChange={v => setFixed(p => ({ ...p, [a]: v }))}
            options={[['', '(전체)'], ...(schema.axes[a] || []).map(v => [String(v), String(v)])]} />
        ))}
        <Sel label="집계" value={agg} onChange={setAgg}
          options={[['none', '슬라이스'], ['mean', '평균'], ['max', '최대'], ['min', '최소']]} />
        <Chk label="유의 셀만" checked={sigOnly} onChange={setSigOnly} />
        <Chk label="기울기" checked={showSlope} onChange={setShowSlope} />
        <Chk label="표 보기" checked={asTable} onChange={setAsTable} />
      </div>

      {/* ── 출처 + 경고 (§9) — 접을 수 없다 ──────────────────────── */}
      {schema && (
        <div className="mb-3 rounded border border-white/10 bg-white/5 p-2 text-xs">
          <div className="text-gray-400">
            {schema.file} · 레코드 {schema.n_records} ·
            {' '}수정 {new Date(schema.mtime * 1000).toLocaleString()} ·
            {' '}커밋 {schema.meta?.commit || '—'} ·
            {' '}엔진 {schema.meta?.engine || '—'}
          </div>
          <div className="text-gray-400">
            구간 {schema.data_window?.start || '미기재'} ~ {schema.data_window?.end || '미기재'}
            {schema.split?.date
              ? ` · 분할 ${schema.split.date} (IS 사건 ${schema.data_window?.is_events ?? '?'} / OOS ${schema.data_window?.oos_events ?? '?'})`
              : ' · 분할 없음'}
          </div>
          {(grid?.warnings || schema.warnings || []).map((w, i) => (
            <div key={i} className="mt-1 text-amber-300">⚠ {w}</div>
          ))}
        </div>
      )}

      {err && <div className="mb-3 rounded border border-red-500/40 bg-red-500/10 p-2 text-sm text-red-300">{err}</div>}
      {busy && <div className="text-xs text-gray-500 mb-2">불러오는 중…</div>}

      {/* ── 요약 (§8) ────────────────────────────────────────────── */}
      {summary && grid && (
        <div className="mb-2 text-xs text-gray-400">
          유의 셀 {summary.sig}/{summary.total}
          {summary.nb > 0 && (
            <> · 최댓값 셀의 이웃 {summary.same}/{summary.nb} 동일 부호</>
          )}
          {summary.nb > 0 && summary.same === 0 && (
            <span className="ml-2 rounded bg-amber-500/20 px-2 py-0.5 text-amber-300">
              절벽 경고 — 최댓값이 이웃 지지 없이 홀로 서 있다
            </span>
          )}
        </div>
      )}

      {/* ── 격자 ─────────────────────────────────────────────────── */}
      {grid && !asTable && (
        <div className="overflow-x-auto">
          <svg width={W} height={H} role="img"
            aria-label={`${metric} 히트맵, X축 ${x}, Y축 ${y}`}>
            <defs>
              {/* 결측은 색이 아니라 빗금이다 — 발산 램프에서 0 과 결측이
                  같은 중립색이라 구분이 안 된다(§10.3) */}
              <pattern id="miss" width="6" height="6" patternUnits="userSpaceOnUse"
                patternTransform="rotate(45)">
                <rect width="6" height="6" fill="transparent" />
                <line x1="0" y1="0" x2="0" y2="6" stroke="#4b5563" strokeWidth="1.5" />
              </pattern>
            </defs>
            {grid.x_values.map((xv, j) => (
              <text key={`x${j}`} x={PAD_L + j * (CELL + GAP) + CELL / 2} y={PAD_T - 10}
                textAnchor="middle" fontSize="11" fill="#9ca3af">{String(xv)}</text>
            ))}
            {grid.y_values.map((yv, i) => (
              <text key={`y${i}`} x={PAD_L - 8} y={PAD_T + i * (CELL + GAP) + CELL / 2 + 4}
                textAnchor="end" fontSize="11" fill="#9ca3af">{String(yv)}</text>
            ))}
            {grid.cells.map((row, i) => row.map((v, j) => {
              const rec = grid.records?.[i]?.[j];
              const missing = v === null || v === undefined;
              const sig = sigOf(rec);
              if (sigOnly && !sig && !missing) return null;
              const cx = PAD_L + j * (CELL + GAP);
              const cy = PAD_T + i * (CELL + GAP);
              const fill = missing ? 'url(#miss)' : colorFor(v, scale);
              const sl = showSlope && !missing ? slope(i, j) : 0;
              return (
                <g key={`${i}-${j}`}
                  onMouseEnter={() => setHover({ i, j, v, rec })}
                  onMouseLeave={() => setHover(null)}>
                  <rect x={cx} y={cy} width={CELL} height={CELL} fill={fill}
                    fillOpacity={missing ? 1 : (sig ? 1 : SWEEP_FADE)}
                    stroke={sl > 0.35 ? '#fbbf24' : 'rgba(255,255,255,0.08)'}
                    strokeWidth={sl > 0.35 ? 2 : 1} rx="2" />
                  {labelCells && !missing && (
                    <text x={cx + CELL / 2} y={cy + CELL / 2 + 4} textAnchor="middle"
                      fontSize="10" fill="#e5e7eb">{fmt(v, 0)}</text>
                  )}
                </g>
              );
            }))}
            <text x={PAD_L} y={H - 12} fontSize="10" fill="#6b7280">
              {x} →   ·   ↓ {y}   ·   {metric} ({kind.ramp}, {kind.polarity})
              {'  '}빗금 = 결측(0 아님)
            </text>
          </svg>
        </div>
      )}

      {/* ── 표 보기 (§10.2 필수 — 색 단독 판단 방지) ─────────────── */}
      {grid && asTable && (
        <div className="overflow-x-auto text-xs">
          <table className="min-w-full border border-white/10">
            <thead><tr className="bg-white/5">
              <th className="p-1 text-left">{y} \ {x}</th>
              {grid.x_values.map((xv, j) => <th key={j} className="p-1">{String(xv)}</th>)}
            </tr></thead>
            <tbody>
              {grid.cells.map((row, i) => (
                <tr key={i} className="border-t border-white/10">
                  <td className="p-1 text-gray-400">{String(grid.y_values[i])}</td>
                  {row.map((v, j) => (
                    <td key={j} className="p-1 text-right">
                      {v === null || v === undefined ? '—' : fmt(v)}
                      <span className="ml-1 text-gray-600">
                        t{fmt(grid.records?.[i]?.[j]?.t, 2)}
                      </span>
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ── 툴팁 (§7 — t·n·se 를 항상 숫자로) ────────────────────── */}
      {hover && (
        <div className="mt-3 rounded border border-white/10 bg-black/60 p-2 text-xs">
          <div className="text-gray-300">
            {x}={String(grid.x_values[hover.j])} · {y}={String(grid.y_values[hover.i])}
            {Object.entries(grid.fix || {}).map(([k, v]) => ` · ${k}=${v}`)}
          </div>
          <div className="mt-1 grid grid-cols-2 gap-x-4 gap-y-0.5 text-gray-400">
            {hover.rec
              ? Object.entries(hover.rec)
                .filter(([k]) => k !== 'split')
                .map(([k, v]) => (
                  <div key={k}>
                    <span className="text-gray-500">{k}</span>{' '}
                    {typeof v === 'number' ? fmt(v, 3) : String(v)}
                  </div>
                ))
              : <div>결측 — 이 조합은 실행되지 않았다</div>}
          </div>
        </div>
      )}
    </div>
  );
}

function Sel({ label, value, onChange, options }) {
  return (
    <label className="flex flex-col gap-0.5">
      <span className="text-[10px] uppercase tracking-wide text-gray-500">{label}</span>
      <select value={value} onChange={e => onChange(e.target.value)}
        className="rounded border border-white/10 bg-white/5 px-2 py-1 text-sm">
        {options.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
      </select>
    </label>
  );
}

function Chk({ label, checked, onChange }) {
  return (
    <label className="flex items-center gap-1 pb-1 text-xs text-gray-400">
      <input type="checkbox" checked={checked} onChange={e => onChange(e.target.checked)} />
      {label}
    </label>
  );
}
