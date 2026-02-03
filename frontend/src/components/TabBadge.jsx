import React from 'react';

/**
 * TabBadge - Displays real-time status indicators on tabs
 * 
 * Usage:
 *   <TabBadge count={3} />           // Shows count: "3"
 *   <TabBadge status="success" />    // Green dot
 *   <TabBadge status="running" />    // Pulsing blue
 *   <TabBadge status="warning" />    // Yellow dot
 *   <TabBadge status="error" />      // Red dot
 */
const TabBadge = ({ count, status, size = 'sm' }) => {
    // Size variants
    const sizeClasses = {
        xs: 'w-4 h-4 text-[9px]',
        sm: 'w-5 h-5 text-[10px]',
        md: 'w-6 h-6 text-xs'
    };

    // Status-based styling
    const statusStyles = {
        success: 'bg-green-500 shadow-green-500/50',
        running: 'bg-blue-500 shadow-blue-500/50 animate-pulse',
        warning: 'bg-yellow-500 shadow-yellow-500/50',
        error: 'bg-red-500 shadow-red-500/50',
        pending: 'bg-gray-500 shadow-gray-500/50',
        default: 'bg-purple-500 shadow-purple-500/50'
    };

    const baseStyle = statusStyles[status] || statusStyles.default;
    const sizeStyle = sizeClasses[size] || sizeClasses.sm;

    // If count is provided, show as number badge
    if (count !== undefined && count !== null) {
        return (
            <span
                className={`
                    ${sizeStyle} ${baseStyle}
                    inline-flex items-center justify-center
                    rounded-full font-bold text-white
                    shadow-lg
                    transition-all duration-200
                `}
            >
                {count > 99 ? '99+' : count}
            </span>
        );
    }

    // Status-only dot indicator
    if (status) {
        return (
            <span
                className={`
                    w-2 h-2 rounded-full
                    ${baseStyle}
                    shadow-md
                `}
            />
        );
    }

    return null;
};

export default TabBadge;
