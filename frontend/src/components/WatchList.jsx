import React from 'react';

const WatchList = ({ orders, onCancel, isLoading }) => {
    if (isLoading) {
        return <div className="text-center text-gray-500 py-4">Loading active watch orders...</div>;
    }

    if (!orders || orders.length === 0) {
        return <div className="text-center text-gray-500 py-4">No active watch orders.</div>;
    }

    return (
        <div className="overflow-x-auto">
            <table className="w-full text-xs text-left text-gray-400">
                <thead className="text-xs text-gray-500 uppercase bg-black/20">
                    <tr>
                        <th className="px-3 py-2">Symbol</th>
                        <th className="px-3 py-2">Condition</th>
                        <th className="px-3 py-2 text-right">Trigger</th>
                        <th className="px-3 py-2 text-right">Target</th>
                        <th className="px-3 py-2 text-center">Action</th>
                    </tr>
                </thead>
                <tbody>
                    {orders.map((order) => (
                        <tr key={order.id} className="border-b border-white/5 hover:bg-white/5">
                            <td className="px-3 py-2 font-medium text-white">{order.symbol}</td>
                            <td className="px-3 py-2">
                                <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold 
                                    ${order.condition_type.includes('BUY') ? 'bg-red-900/50 text-red-300' :
                                        order.condition_type.includes('STOP') && !order.condition_type.includes('TRAILING') ? 'bg-blue-900/50 text-blue-300' :
                                            order.condition_type === 'TAKE_PROFIT' ? 'bg-green-900/50 text-green-300' :
                                                'bg-yellow-900/50 text-yellow-300'}`}>
                                    {order.condition_type.replace('_', ' ')}
                                </span>
                            </td>
                            <td className="px-3 py-2 text-right font-mono text-white">
                                {order.condition_type === 'TRAILING_STOP' ? (
                                    <div className="flex flex-col items-end">
                                        <span className="text-yellow-400 font-bold">-{order.trailing_percent}%</span>
                                        {order.highest_price && (
                                            <span className="text-[10px] text-gray-500">High: {order.highest_price.toLocaleString()}</span>
                                        )}
                                    </div>
                                ) : (
                                    order.trigger_price?.toLocaleString()
                                )}
                            </td>
                            <td className="px-3 py-2 text-right">
                                {order.quantity > 0 ? `${order.quantity} Qty` : 'Amount Mode'}
                            </td>
                            <td className="px-3 py-2 text-center">
                                <button
                                    onClick={() => onCancel(order.id)}
                                    className="text-red-400 hover:text-red-300 hover:underline"
                                >
                                    Cancel
                                </button>
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
};

export default WatchList;
