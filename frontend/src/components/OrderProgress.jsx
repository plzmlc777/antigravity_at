import React from 'react';

const Step = ({ title, status, isLast, details }) => {
    let circleColor = 'bg-gray-700 border-gray-600 text-gray-400';
    let lineColor = 'bg-gray-800';
    let titleColor = 'text-gray-500';

    if (status === 'completed') {
        circleColor = 'bg-green-500/20 border-green-500 text-green-500';
        lineColor = 'bg-green-500/50';
        titleColor = 'text-green-400';
    } else if (status === 'processing') {
        circleColor = 'bg-blue-500/20 border-blue-500 text-blue-300 animate-pulse';
        lineColor = 'bg-gray-800';
        titleColor = 'text-blue-300 font-bold';
    } else if (status === 'error') {
        circleColor = 'bg-red-500/20 border-red-500 text-red-500';
        titleColor = 'text-red-400';
    } else if (status === 'cancelled') {
        circleColor = 'bg-yellow-500/20 border-yellow-500 text-yellow-500';
        titleColor = 'text-yellow-400';
    }

    return (
        <div className="flex flex-col items-center flex-1 relative">
            {!isLast && (
                <div className={`absolute top-4 left-[50%] right-[-50%] h-0.5 ${lineColor} z-0 transition-colors duration-300`}></div>
            )}
            <div className={`w-8 h-8 rounded-full border-2 flex items-center justify-center font-bold text-xs z-10 transition-all duration-300 ${circleColor} bg-black`}>
                {status === 'completed' ? '✓' : status === 'error' ? '!' : status === 'cancelled' ? '-' : ''}
            </div>
            <div className={`mt-2 text-xs text-center ${titleColor}`}>
                {title}
            </div>
            {details && (
                <div className="mt-1 text-[10px] text-gray-400 text-center whitespace-pre-line leading-tight">
                    {details}
                </div>
            )}
        </div>
    );
};

const OrderProgress = ({ status, error, details }) => {
    let step1 = 'pending';
    let step2 = 'pending';
    let step3 = 'pending';

    let processingDetails = null;
    let resultDetails = null;

    if (status === 'processing') {
        step1 = 'completed';
        step2 = 'processing';
        if (details) {
            processingDetails = `Filling...\n${details.filled}/${details.total}`;
        }
    } else if (status === 'success') {
        step1 = 'completed';
        step2 = 'completed';
        step3 = 'completed';
        if (details) {
            resultDetails = `Avg: ${details.avgPrice?.toLocaleString()}\nQty: ${details.filled}`;
        }
    } else if (status === 'error') {
        step1 = 'completed';
        step2 = 'error';
        step3 = 'pending';
    } else if (status === 'cancelled') {
        step1 = 'completed';
        step2 = 'cancelled';
        step3 = 'pending';
    }

    return (
        <div className="w-full py-4">
            <div className="flex justify-between items-start mb-6 px-4">
                <Step title="Request Sent" status={step1} />
                <Step title="Processing" status={step2} details={processingDetails} />
                <Step title="Order Result" status={status === 'error' ? 'error' : status === 'cancelled' ? 'cancelled' : step3} isLast details={resultDetails} />
            </div>

            {status === 'success' && (
                <div className="bg-green-500/10 border border-green-500/30 text-green-300 p-3 rounded text-sm text-center animate-fade-in space-y-1">
                    <div className="font-bold">Order Executed Successfully!</div>
                    {details && (
                        <div className="text-xs opacity-80">
                            Filled {details.filled} shares at average {details.avgPrice?.toLocaleString()}
                        </div>
                    )}
                </div>
            )}
            {status === 'error' && (
                <div className="bg-red-500/10 border border-red-500/30 text-red-300 p-3 rounded text-sm text-center animate-fade-in">
                    Order Failed: {error || 'Unknown Error'}
                </div>
            )}
            {status === 'cancelled' && (
                <div className="bg-yellow-500/10 border border-yellow-500/30 text-yellow-300 p-3 rounded text-sm text-center animate-fade-in">
                    Order Cancelled by User
                </div>
            )}
        </div>
    );
};

export default OrderProgress;
