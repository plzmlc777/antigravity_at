// Emergency wrapper around ManualTrading.
// Forces the user to acknowledge that manual orders bypass the AI policy chain
// (CIO + risk-manager veto + KPI compound gate) before exposing the underlying view.
import { useState } from 'react';
import ManualTrading from './ManualTrading';

const ACK_KEY = 'emergency_manual_acknowledged_session';

export default function EmergencyManual() {
    const [acknowledged, setAcknowledged] = useState(
        () => sessionStorage.getItem(ACK_KEY) === '1'
    );

    if (!acknowledged) {
        return (
            <div className="max-w-2xl mx-auto mt-12 p-6 rounded-xl bg-red-500/10 border-2 border-red-500/50">
                <div className="flex items-center gap-3 mb-4">
                    <span className="text-4xl">⚠</span>
                    <h1 className="text-2xl font-bold text-red-300">긴급 수동 거래 모드</h1>
                </div>
                <p className="text-sm text-gray-300 mb-3">
                    이 화면에서 발행되는 모든 주문은 다음 AI 정책 체인을
                    <strong className="text-red-300"> 우회 (bypass) </strong>합니다:
                </p>
                <ul className="text-sm text-gray-300 list-disc list-inside space-y-1 mb-4 ml-2">
                    <li>CIO 오케스트레이터의 ASSESS → PLAN → EXECUTE 워크플로우</li>
                    <li>risk-manager의 VETO 권한 + KPI 12% 복리 게이트</li>
                    <li>backtest-analyst 검증 + strategy-advisor 신뢰도 체크</li>
                    <li>portfolio 노출 / 종목 중복 / kill-switch 정책</li>
                </ul>
                <p className="text-sm text-amber-300 mb-6">
                    수동 주문은 시스템 장애 / 긴급 청산 / 디버깅 목적으로만 사용해야 합니다.
                    일상 거래는 <strong>Mission Control + Live Sessions</strong>에서 진행하세요.
                </p>
                <div className="flex gap-3">
                    <button
                        onClick={() => {
                            sessionStorage.setItem(ACK_KEY, '1');
                            setAcknowledged(true);
                        }}
                        className="px-4 py-2 rounded-lg bg-red-600 hover:bg-red-500 text-white text-sm font-medium"
                    >
                        이해했습니다 — 진입
                    </button>
                    <button
                        onClick={() => window.history.back()}
                        className="px-4 py-2 rounded-lg bg-white/10 hover:bg-white/20 text-gray-300 text-sm"
                    >
                        뒤로 가기
                    </button>
                </div>
            </div>
        );
    }

    return (
        <div>
            <div className="mb-4 p-2 rounded bg-red-500/10 border border-red-500/30 text-xs text-red-300 flex items-center justify-between">
                <span>⚠ EMERGENCY MANUAL MODE — AI 정책 우회 중</span>
                <button
                    onClick={() => {
                        sessionStorage.removeItem(ACK_KEY);
                        setAcknowledged(false);
                    }}
                    className="text-red-200 hover:text-white underline"
                >
                    경고 다시 보기
                </button>
            </div>
            <ManualTrading />
        </div>
    );
}
