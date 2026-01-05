import React from 'react';

const ConfirmModal = ({ isOpen, onClose, onConfirm, title, message, confirmText = "Confirm", cancelText = "Cancel", isDanger = false }) => {
    if (!isOpen) return null;

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
                <p className="text-gray-400 text-sm mb-6 leading-relaxed">
                    {message}
                </p>

                {/* Footer / Actions */}
                <div className="flex justify-end gap-3">
                    <button
                        onClick={onClose}
                        className="px-4 py-2 rounded-lg text-sm font-medium text-gray-400 hover:text-white hover:bg-white/5 transition-colors"
                    >
                        {cancelText}
                    </button>
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
