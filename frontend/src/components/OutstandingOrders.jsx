import React from 'react';

const OutstandingOrders = ({ orders, onCancel, isLoading }) => {
    if (!orders || orders.length === 0) {
        return (
            <div className="bg-black/20 rounded p-4 text-center text-gray-500 text-sm border border-white/5">
                No outstanding orders.
            </div>
        );
    }

    return (
        <div className="overflow-x-auto">
            <table className="w-full text-xs text-left">
                <thead className="text-gray-400 bg-white/5 uppercase font-medium">
                    <tr>
                        <th className="px-3 py-2 rounded-tl">Time</th>
                        <th className="px-3 py-2">Symbol</th>
                        <th className="px-3 py-2">Side</th>
                        <th className="px-3 py-2">Price</th>
                        <th className="px-3 py-2">Qty</th>
                        <th className="px-3 py-2">Unfilled</th>
                        <th className="px-3 py-2 rounded-tr text-right">Action</th>
                    </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                    {orders.map((order, index) => (
                        <tr key={order.order_no || index} className="hover:bg-white/5 transition-colors">
                            <td className="px-3 py-2 text-gray-400 font-mono">{order.time}</td>
                            <td className="px-3 py-2 font-medium">
                                <span className="text-white block">{order.name}</span>
                                <span className="text-gray-500 text-[10px]">{order.symbol}</span>
                            </td>
                            <td className={`px-3 py-2 font-bold ${order.side.includes('매수') || order.side.includes('buy') ? 'text-red-400' : 'text-blue-400'}`}>
                                {order.side}
                            </td>
                            <td className="px-3 py-2 text-gray-300 font-mono">
                                {order.order_price > 0 ? order.order_price.toLocaleString() : 'Market'}
                            </td>
                            <td className="px-3 py-2 text-gray-300">{order.order_qty}</td>
                            <td className="px-3 py-2 text-yellow-500 font-bold">{order.unfilled_qty}</td>
                            <td className="px-3 py-2 text-right">
                                <button
                                    onClick={() => onCancel(order)}
                                    disabled={isLoading}
                                    className="bg-red-500/20 hover:bg-red-500/40 text-red-400 border border-red-500/30 px-2 py-1 rounded text-xs transition-colors disabled:opacity-50"
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

export default OutstandingOrders;
