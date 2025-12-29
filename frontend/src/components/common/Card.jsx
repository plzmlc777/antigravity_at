import React from 'react';

const Card = ({ title, children, className = '', headerAction, variant = 'default' }) => {
    const isMajor = variant === 'major';

    return (
        <div className={`bg-[#0f111a] border border-white/10 rounded-xl overflow-hidden shadow-lg hover:shadow-xl transition-shadow duration-300 ${className}`}>
            {(title || headerAction) && (
                <div className={`px-5 py-4 border-b border-white/5 bg-white/[0.02] flex items-center justify-between ${isMajor ? 'bg-white/5 py-5' : ''}`}>
                    {title && (
                        <h3 className={`${isMajor ? 'text-lg font-bold text-white tracking-normal' : 'text-sm font-semibold text-white/90 uppercase tracking-wide'}`}>
                            {title}
                        </h3>
                    )}
                    {headerAction && (
                        <div>{headerAction}</div>
                    )}
                </div>
            )}
            <div className="p-5">
                {children}
            </div>
        </div>
    );
};

export default Card;
