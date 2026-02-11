import React from 'react';
import { AlertTriangle, AlertCircle, CheckCircle, Info, X } from 'lucide-react';

/**
 * AlertModal - Custom styled alert modal to replace system alert()
 *
 * Props:
 * - isOpen: boolean
 * - onClose: () => void
 * - title: string (optional, auto-generated based on type if not provided)
 * - message: string
 * - type: 'info' | 'warning' | 'error' | 'success' (default: 'info')
 * - confirmText: string (default: '확인')
 */
const AlertModal = ({
    isOpen,
    onClose,
    title,
    message,
    type = 'info',
    confirmText = '확인'
}) => {
    if (!isOpen) return null;

    // Type-based styling
    const typeConfig = {
        info: {
            icon: Info,
            iconColor: 'text-blue-400',
            bgColor: 'bg-blue-500/10',
            borderColor: 'border-blue-500/30',
            buttonColor: 'bg-blue-600 hover:bg-blue-500',
            defaultTitle: '알림'
        },
        warning: {
            icon: AlertTriangle,
            iconColor: 'text-yellow-400',
            bgColor: 'bg-yellow-500/10',
            borderColor: 'border-yellow-500/30',
            buttonColor: 'bg-yellow-600 hover:bg-yellow-500',
            defaultTitle: '경고'
        },
        error: {
            icon: AlertCircle,
            iconColor: 'text-red-400',
            bgColor: 'bg-red-500/10',
            borderColor: 'border-red-500/30',
            buttonColor: 'bg-red-600 hover:bg-red-500',
            defaultTitle: '오류'
        },
        success: {
            icon: CheckCircle,
            iconColor: 'text-green-400',
            bgColor: 'bg-green-500/10',
            borderColor: 'border-green-500/30',
            buttonColor: 'bg-green-600 hover:bg-green-500',
            defaultTitle: '성공'
        }
    };

    const config = typeConfig[type] || typeConfig.info;
    const Icon = config.icon;
    const displayTitle = title || config.defaultTitle;

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            {/* Backdrop */}
            <div
                className="absolute inset-0 bg-black/70 backdrop-blur-sm"
                onClick={onClose}
            />

            {/* Modal Content */}
            <div className={`relative bg-[#1a1a2e] border ${config.borderColor} rounded-2xl shadow-2xl max-w-md w-full overflow-hidden`}>
                {/* Header */}
                <div className={`flex items-center gap-3 px-6 py-4 border-b ${config.borderColor} ${config.bgColor}`}>
                    <Icon size={24} className={config.iconColor} />
                    <h2 className={`text-lg font-bold ${config.iconColor}`}>
                        {displayTitle}
                    </h2>
                    <button
                        onClick={onClose}
                        className="ml-auto p-1 hover:bg-white/10 rounded transition-colors"
                    >
                        <X size={18} className="text-gray-400" />
                    </button>
                </div>

                {/* Body */}
                <div className="p-6">
                    <p className="text-gray-300 text-sm leading-relaxed whitespace-pre-line">
                        {message}
                    </p>
                </div>

                {/* Footer */}
                <div className="px-6 pb-6">
                    <button
                        onClick={onClose}
                        className={`w-full py-3 rounded-xl text-white font-bold text-sm transition-all ${config.buttonColor} shadow-lg active:scale-[0.98]`}
                    >
                        {confirmText}
                    </button>
                </div>
            </div>
        </div>
    );
};

export default AlertModal;
