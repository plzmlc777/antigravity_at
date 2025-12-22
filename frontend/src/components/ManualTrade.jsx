import React from 'react';
import OrderProgress from './OrderProgress';
import { useManualTrade } from '../hooks/useManualTrade';

const ManualTrade = ({ defaultSymbol }) => {
    const {
        symbol,
        price, setPrice,
        orderType, setOrderType,
        priceType, setPriceType,
        mode, setMode,
        value, setValue,
        orderStatus,
        errorMessage,
        orderDetails,
        handleSubmit,
        handleCancel,
        handleSimulation,
        resetStatus
    } = useManualTrade(defaultSymbol);

    return (
        <div className="p-1">

            <form onSubmit={handleSubmit} className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                    <div>
                        <label className="block text-sm text-gray-400 mb-1">Symbol</label>
                        <input
                            type="text"
                            value={symbol}
                            readOnly
                            className="w-full bg-black/20 border border-white/5 rounded p-2 text-gray-400 cursor-not-allowed focus:outline-none"
                            placeholder="Selected Symbol"
                            required
                        />
                    </div>
                    <div>
                        <label className="block text-sm text-gray-400 mb-1">Price</label>
                        <div className="flex gap-2 mb-2">
                            <button
                                type="button"
                                onClick={() => setPriceType('limit')}
                                className={`flex-1 py-1 rounded text-xs font-medium transition-colors border ${priceType === 'limit' ? 'bg-blue-500/20 border-blue-500 text-blue-300' : 'bg-black/20 border-white/10 text-gray-400'}`}
                            >
                                Limit
                            </button>
                            <button
                                type="button"
                                onClick={() => { setPriceType('market'); setPrice(''); }}
                                className={`flex-1 py-1 rounded text-xs font-medium transition-colors border ${priceType === 'market' ? 'bg-blue-500/20 border-blue-500 text-blue-300' : 'bg-black/20 border-white/10 text-gray-400'}`}
                            >
                                Market
                            </button>
                        </div>
                        <input
                            type="number"
                            value={price}
                            onChange={(e) => setPrice(e.target.value)}
                            disabled={priceType === 'market'}
                            className={`w-full bg-black/40 border border-white/10 rounded p-2 text-white focus:outline-none focus:border-blue-500 ${priceType === 'market' ? 'opacity-50 cursor-not-allowed' : ''}`}
                            placeholder={priceType === 'market' ? 'Market Price' : 'Price'}
                            required={priceType === 'limit'}
                        />
                    </div>
                </div>

                <div className="flex bg-black/40 p-1 rounded">
                    <button
                        type="button"
                        onClick={() => setOrderType('buy')}
                        className={`flex-1 py-1 rounded text-sm font-medium transition-colors ${orderType === 'buy' ? 'bg-red-500/80 text-white' : 'text-gray-400 hover:text-white'}`}
                    >
                        Buy
                    </button>
                    <button
                        type="button"
                        onClick={() => setOrderType('sell')}
                        className={`flex-1 py-1 rounded text-sm font-medium transition-colors ${orderType === 'sell' ? 'bg-blue-500/80 text-white' : 'text-gray-400 hover:text-white'}`}
                    >
                        Sell
                    </button>
                </div>

                <div>
                    <label className="block text-sm text-gray-400 mb-1">Mode</label>
                    <select
                        value={mode}
                        onChange={(e) => setMode(e.target.value)}
                        className="w-full bg-black/40 border border-white/10 rounded p-2 text-white focus:outline-none focus:border-blue-500"
                    >
                        <option value="quantity">Fixed Quantity</option>
                        <option value="amount">Fixed Amount (KRW)</option>
                        {orderType === 'buy' && <option value="percent_cash">% of Cash</option>}
                        {orderType === 'sell' && <option value="percent_holding">% of Holding</option>}
                    </select>
                </div>

                <div>
                    <label className="block text-sm text-gray-400 mb-1">
                        {mode === 'quantity' ? 'Quantity' :
                            mode === 'amount' ? 'Amount (KRW)' :
                                'Percentage (0-100)'}
                    </label>
                    <input
                        type="number"
                        value={value}
                        onChange={(e) => setValue(e.target.value)}
                        className="w-full bg-black/40 border border-white/10 rounded p-2 text-white focus:outline-none focus:border-blue-500"
                        placeholder="Value"
                        required
                    />
                </div>

                <div className="flex flex-col gap-3">
                    {orderStatus === 'processing' ? (
                        <button
                            type="button"
                            onClick={handleCancel}
                            className="w-full bg-red-500/20 hover:bg-red-500/30 text-red-300 border border-red-500/50 font-bold py-2 rounded transition-all animate-pulse"
                        >
                            Cancel Order
                        </button>
                    ) : (
                        <button
                            type="submit"
                            className="w-full bg-gradient-to-r from-blue-500 to-indigo-600 hover:from-blue-600 hover:to-indigo-700 text-white font-bold py-2 rounded transition-all disabled:opacity-50"
                        >
                            Place Order
                        </button>
                    )}

                    {orderStatus === 'idle' && (
                        <button
                            type="button"
                            onClick={handleSimulation}
                            className="w-full bg-white/5 hover:bg-white/10 text-blue-300 text-xs py-1.5 rounded transition-colors border border-dashed border-blue-500/30"
                        >
                            Place Order Simulation
                        </button>
                    )}
                </div>

                {/* Order Process Visualization */}
                {orderStatus !== 'idle' && (
                    <div className="mt-4 pt-4 border-t border-white/10">
                        <OrderProgress status={orderStatus} error={errorMessage} details={orderDetails} />
                        {/* Button to reset and place another order if finished/failed/cancelled */}
                        {(orderStatus === 'success' || orderStatus === 'error' || orderStatus === 'cancelled') && (
                            <button
                                type="button"
                                onClick={resetStatus}
                                className="w-full mt-2 text-xs text-center text-gray-500 hover:text-white transition-colors"
                            >
                                Trace New Order
                            </button>
                        )}
                    </div>
                )}
            </form>
        </div>
    );
};

export default ManualTrade;
