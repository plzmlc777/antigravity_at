#!/usr/bin/env python3
"""1h RSI12 + 15m RSI8 결합 포트폴리오 시뮬레이션.

거래 덤프에서 슬롯 제약 포트폴리오를 재구성한다. 커널 재실행 없음 —
덤프의 진입/청산 시각과 수익률을 그대로 쓰고 슬롯 배분만 시뮬레이션한다.
"""
import pandas as pd, numpy as np, sys
from dataclasses import dataclass, asdict

D = 'runs/research_track/rsi_tp_sl/'
FEE_BP = 10.0        # 왕복 테이커 수수료 (bp)
SLOTS  = 20

@dataclass
class SimCfg:
    name: str
    slots: int = SLOTS
    fee_bp: float = FEE_BP
    priority: str = ''     # '', '15m', '1h'  — 같은 종목 충돌 시 우선권


def load(fname, thr, tp, sl, placebo, src):
    d = pd.read_csv(D + fname)
    d = d[(d.placebo == placebo) & (d.side == 'long') &
          (d.thr == thr) & (d.tp == tp) & (d.sl == sl)].copy()
    d['entry_ts'] = pd.to_datetime(d.entry_ts)
    d['exit_ts']  = pd.to_datetime(d.exit_ts)
    d['src'] = src
    return d[['entry_ts', 'exit_ts', 'symbol', 'ret_pct', 'exit_reason', 'src']]


def simulate(df, cfg):
    """시각순 슬롯 배분. 슬롯이 차 있으면 신호를 버린다(현실과 동일)."""
    df = df.sort_values('entry_ts', kind='mergesort').reset_index(drop=True)
    open_pos = []                 # (exit_ts, symbol, ret_pct, src)
    equity, taken, skipped_slot, skipped_prio = 1.0, [], 0, 0
    occ_num, occ_den = 0.0, 0
    for r in df.itertuples():
        # 이 시각 이전에 끝난 포지션 청산 → 자본 반영
        still = []
        for p in open_pos:
            if p[0] <= r.entry_ts:
                equity *= 1.0 + (p[2] - cfg.fee_bp / 100.0) / 100.0 / cfg.slots
            else:
                still.append(p)
        open_pos = still
        occ_num += len(open_pos); occ_den += 1
        # 같은 종목 중복 노출 차단 + 우선권
        held = {p[1] for p in open_pos}
        if r.symbol in held:
            skipped_prio += 1
            continue
        if len(open_pos) >= cfg.slots:
            skipped_slot += 1
            continue
        open_pos.append((r.exit_ts, r.symbol, r.ret_pct, r.src))
        taken.append((r.entry_ts, r.exit_ts, r.symbol, r.ret_pct, r.src))
    for p in open_pos:
        equity *= 1.0 + (p[2] - cfg.fee_bp / 100.0) / 100.0 / cfg.slots
    t = pd.DataFrame(taken, columns=['entry_ts', 'exit_ts', 'symbol', 'ret_pct', 'src'])
    return {
        'name': cfg.name,
        'n_signal': len(df), 'n_taken': len(t),
        'skip_slot': skipped_slot, 'skip_dup': skipped_prio,
        'equity': equity, 'occupancy': occ_num / max(occ_den, 1) / cfg.slots,
        'per_trade': t.ret_pct.mean() if len(t) else 0.0,
        'win': (t.ret_pct > 0).mean() * 100 if len(t) else 0.0,
        'by_src': t.src.value_counts().to_dict(),
        'trades': t,
    }


def combine(h, m, priority):
    """두 스트림 병합. priority 쪽이 같은 종목 충돌에서 이긴다.

    인과적으로만 판정한다 — 진입 시점에 이미 열려 있는 포지션만 본다.
    미래의 신호를 보고 현재를 거르지 않는다."""
    both = pd.concat([h, m], ignore_index=True)
    both['prio_rank'] = np.where(both.src == priority, 0, 1)
    # 같은 시각 동시 발생 시 우선권 쪽을 먼저 처리 → 슬롯/중복 판정에서 이김
    both = both.sort_values(['entry_ts', 'prio_rank'], kind='mergesort')
    return both.drop(columns=['prio_rank']).reset_index(drop=True)


def main():
    placebo = sys.argv[1] if len(sys.argv) > 1 else 'real'
    h = load('trades_long_h48_EXPANDED.csv',        12.0, 0.08, 0.03, placebo, '1h')
    m = load('trades_long_15mfrom1m_h192_MTF15.csv', 8.0, 0.08, 0.03, placebo, '15m')
    # 공통 구간 · 공통 종목으로 잘라야 세 구성이 같은 조건에서 비교된다
    lo = max(h.entry_ts.min(), m.entry_ts.min())
    hi = min(h.entry_ts.max(), m.entry_ts.max())
    cs = set(h.symbol) & set(m.symbol)
    h = h[(h.entry_ts >= lo) & (h.entry_ts <= hi) & h.symbol.isin(cs)]
    m = m[(m.entry_ts >= lo) & (m.entry_ts <= hi) & m.symbol.isin(cs)]
    yrs = (hi - lo).days / 365.25
    print(f'위약={placebo} · 구간 {lo.date()} ~ {hi.date()} ({yrs:.2f}년) · 공통종목 {len(cs)}')
    print(f'원신호  1h {len(h)}건 · 15m {len(m)}건 · 슬롯 {SLOTS} · 수수료 {FEE_BP}bp 왕복')
    print()
    runs = [
        (h,                       SimCfg('1h 단독')),
        (m,                       SimCfg('15m 단독')),
        (combine(h, m, '15m'),    SimCfg('결합 (15m 우선)', priority='15m')),
        (combine(h, m, '1h'),     SimCfg('결합 (1h 우선)',  priority='1h')),
    ]
    hdr = f"{'구성':<20}{'신호':>7}{'체결':>7}{'슬롯탈락':>9}{'중복탈락':>9}{'점유율':>8}{'거래당%':>9}{'승률%':>7}{'연복리%':>9}"
    print(hdr); print('-' * len(hdr.encode('utf-8')) // 2 * '-' if False else '-' * 100)
    out = []
    for df, cfg in runs:
        r = simulate(df, cfg)
        cagr = (r['equity'] ** (1 / yrs) - 1) * 100
        r['cagr'] = cagr
        out.append(r)
        print(f"{r['name']:<20}{r['n_signal']:>7}{r['n_taken']:>7}{r['skip_slot']:>9}{r['skip_dup']:>9}"
              f"{r['occupancy']*100:>7.1f}%{r['per_trade']:>9.3f}{r['win']:>7.1f}{cagr:>9.2f}")
    print()
    for r in out[2:]:
        print(f"{r['name']}  출처 구성: {r['by_src']}")
    return out

if __name__ == '__main__':
    main()
