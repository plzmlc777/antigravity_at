import React from 'react';

const OrderErrorModal = ({ isOpen, onClose, error }) => {
    if (!isOpen || !error) return null;

    const message = error.message || '알 수 없는 오류';
    const statusCode = error.statusCode;
    const requestPayload = error.requestPayload;

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />
            <div className="relative bg-[#1e2029] border-2 border-red-500 rounded-xl shadow-2xl max-w-md w-full p-6">
                <div className="flex items-center gap-3 mb-3">
                    <span className="text-3xl">❌</span>
                    <h3 className="text-xl font-bold text-red-400">주문 실패</h3>
                </div>

                <div className="bg-black/40 rounded-lg p-4 mb-4">
                    <div className="text-gray-400 text-xs mb-1">오류 메시지</div>
                    <div className="text-white text-sm font-mono whitespace-pre-wrap break-words">
                        {message}
                    </div>
                </div>

                {(statusCode || requestPayload) && (
                    <details className="mb-4 text-xs">
                        <summary className="text-gray-500 cursor-pointer hover:text-gray-300">상세 정보</summary>
                        <div className="mt-2 bg-black/30 rounded p-3 space-y-2 font-mono">
                            {statusCode && (
                                <div className="text-gray-400">
                                    <span className="text-gray-500">HTTP Status:</span> {statusCode}
                                </div>
                            )}
                            {requestPayload && (
                                <div className="text-gray-400">
                                    <div className="text-gray-500 mb-1">Request:</div>
                                    <pre className="text-[10px] overflow-x-auto">{JSON.stringify(requestPayload, null, 2)}</pre>
                                </div>
                            )}
                        </div>
                    </details>
                )}

                <div className="flex justify-end">
                    <button
                        onClick={onClose}
                        className="px-4 py-2 rounded-lg text-sm font-bold bg-red-600 hover:bg-red-500 text-white shadow-lg shadow-red-900/30 active:scale-95 transition-all"
                    >
                        확인
                    </button>
                </div>
            </div>
        </div>
    );
};

export default OrderErrorModal;
