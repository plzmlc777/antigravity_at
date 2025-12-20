import React from 'react';

const StatusCard = ({ title, value, subtext, type = 'neutral' }) => {
    const colors = {
        neutral: 'bg-white/5 border-white/10',
        success: 'bg-green-500/10 border-green-500/20 text-green-400',
        danger: 'bg-red-500/10 border-red-500/20 text-red-400',
        warning: 'bg-yellow-500/10 border-yellow-500/20 text-yellow-400',
    };

    return (
        <div className={`border rounded-xl p-4 ${colors[type]}`}>
            <h3 className="text-sm text-gray-400 mb-1">{title}</h3>
            <div className="text-2xl font-mono font-semibold">{value}</div>
            {subtext && <div className="text-xs text-gray-500 mt-2">{subtext}</div>}
        </div>
    );
};

export default StatusCard;
