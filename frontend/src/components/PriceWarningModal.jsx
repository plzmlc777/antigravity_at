import React, { useState, useEffect } from 'react';

const PriceWarningModal = ({ isOpen, onConfirm, onCancel, warning }) => {
    const [acknowledged, setAcknowledged] = useState(false);

    useEffect(() => {
        if (!isOpen) setAcknowledged(false);
    }, [isOpen]);

    if (!isOpen || !warning) return null;

    const { orderType, currentPrice, inputPrice, deviationPct, severity } = warning;
    const isHard = severity === 'hard';
    const lossLabel = orderType === 'buy' ? '비싸게 매수' : '싸게 매도';
    const absPct = Math.abs(deviationPct);

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onCancel} />
            <div className={`relative bg-[#1e2029] border-2 rounded-xl shadow-2xl max-w-md w-full p-6 ${isHard ? 'border-red-500' : 'border-yellow-500'}`}>
                <div className="flex items-center gap-3 mb-3">
                    <span className="text-3xl">{isHard ? '🚨' : '⚠️'}</span>
                    <h3 className={`text-xl font-bold ${isHard ? 'text-red-400' : 'text-yellow-400'}`}>
                        {isHard ? '비정상 가격 경고' : '가격 확인'}
                    </h3>
                </div>

                <div className="bg-black/40 rounded-lg p-4 mb-4 space-y-2 font-mono text-sm">
                    <div className="flex justify-between">
                        <span className="text-gray-400">현재가</span>
                        <span className="text-white">{currentPrice.toLocaleString()}</span>
                    </div>
                    <div className="flex justify-between">
                        <span className="text-gray-400">주문가</span>
                        <span className="text-white">{inputPrice.toLocaleString()}</span>
                    </div>
                    <div className="flex justify-between border-t border-white/10 pt-2">
                        <span className="text-gray-400">차이</span>
                        <span className={`font-bold ${isHard ? 'text-red-400' : 'text-yellow-400'}`}>
                            {deviationPct >= 0 ? '+' : ''}{deviationPct.toFixed(2)}% ({lossLabel})
                        </span>
                    </div>
                </div>

                <p className="text-gray-300 text-sm mb-4 leading-relaxed">
                    {orderType === 'buy'
                        ? `현재가보다 ${absPct.toFixed(2)}% 비싼 가격에 매수합니다.`
                        : `현재가보다 ${absPct.toFixed(2)}% 싼 가격에 매도합니다.`
                    }
                    {isHard && ' 입력 실수 가능성이 매우 높습니다. 확인 후 진행하세요.'}
                </p>

                {isHard && (
                    <label className="flex items-center gap-2 mb-4 cursor-pointer select-none p-2 bg-red-500/10 border border-red-500/30 rounded">
                        <input
                            type="checkbox"
                            checked={acknowledged}
                            onChange={(e) => setAcknowledged(e.target.checked)}
                            className="w-4 h-4"
                        />
                        <span className="text-sm text-red-300">의도된 주문임을 확인합니다</span>
                    </label>
                )}

                <div className="flex justify-end gap-3">
                    <button
                        onClick={onCancel}
                        className="px-4 py-2 rounded-lg text-sm font-bold bg-orange-600 hover:bg-orange-500 text-white shadow-lg shadow-orange-900/30"
                    >
                        취소
                    </button>
                    <button
                        onClick={onConfirm}
                        disabled={isHard && !acknowledged}
                        className={`px-4 py-2 rounded-lg text-sm font-bold text-white transition-all active:scale-95 shadow-lg ${
                            isHard && !acknowledged
                                ? 'bg-gray-600 cursor-not-allowed opacity-50'
                                : isHard
                                    ? 'bg-red-600 hover:bg-red-500 shadow-red-900/30'
                                    : 'bg-yellow-600 hover:bg-yellow-500 shadow-yellow-900/30'
                        }`}
                    >
                        {isHard ? '강제 주문' : '주문 진행'}
                    </button>
                </div>
            </div>
        </div>
    );
};

export default PriceWarningModal;
