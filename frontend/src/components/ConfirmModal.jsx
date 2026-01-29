import React from 'react';

const ConfirmModal = ({ isOpen, onClose, onConfirm, onCancel, title, message, confirmText = "Confirm", cancelText = "Cancel", isDanger = false }) => {
    if (!isOpen) return null;

    const handleCancelClick = () => {
        if (onCancel) {
            onCancel();
            onClose();
        } else {
            onClose();
        }
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            {/* Backdrop */}
            <div
                className="absolute inset-0 bg-black/60 backdrop-blur-sm transition-opacity"
                onClick={onClose}
            />

            {/* Modal Content */}
            <div className="relative bg-[#1e2029] border border-white/10 rounded-xl shadow-2xl max-w-sm w-full p-6 transform transition-all scale-100 animate-in fade-in zoom-in duration-200">
                {/* Header */}
                <h3 className="text-xl font-bold text-white mb-2">
                    {title}
                </h3>

                {/* Body */}
                <p className="text-gray-400 text-sm mb-6 leading-relaxed whitespace-pre-line">
                    {message}
                </p>

                {/* Footer / Actions */}
                <div className="flex justify-end gap-3">
                    {cancelText && (
                        <button
                            onClick={handleCancelClick}
                            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${onCancel
                                ? 'bg-orange-600 hover:bg-orange-500 text-white font-bold shadow-lg shadow-orange-900/30'
                                : 'text-gray-400 hover:text-white hover:bg-white/5'
                                }`}
                        >
                            {cancelText}
                        </button>
                    )}
                    <button
                        onClick={() => {
                            onConfirm();
                            onClose();
                        }}
                        className={`px-4 py-2 rounded-lg text-sm font-bold text-white shadow-lg transition-all active:scale-95 ${isDanger
                            ? 'bg-red-600 hover:bg-red-500 shadow-red-900/30'
                            : 'bg-blue-600 hover:bg-blue-500 shadow-blue-900/30'
                            }`}
                    >
                        {confirmText}
                    </button>
                </div>
            </div>
        </div>
    );
};

export default ConfirmModal;
