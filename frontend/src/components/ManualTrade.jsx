import React, { useState, useRef, useEffect } from 'react';
import { placeManualOrder } from '../api/client';
import OrderProgress from './OrderProgress';

const ManualTrade = ({ defaultSymbol }) => {
    const [symbol, setSymbol] = useState(defaultSymbol || '');

    useEffect(() => {
        if (defaultSymbol) setSymbol(defaultSymbol);
    }, [defaultSymbol]);

    const [price, setPrice] = useState('');
    const [orderType, setOrderType] = useState('buy');
    const [priceType, setPriceType] = useState('limit'); // 'limit' or 'market'
    const [mode, setMode] = useState('quantity');
    const [value, setValue] = useState('');

    // Status for logical flow: 'idle', 'processing', 'success', 'error', 'cancelled'
    const [orderStatus, setOrderStatus] = useState('idle');
    const [errorMessage, setErrorMessage] = useState(null);
    const [orderDetails, setOrderDetails] = useState(null);

    // Refs for cancellation
    const abortControllerRef = useRef(null);
    const simulationTimeoutsRef = useRef([]);

    const handleCancel = (e) => {
        if (e) e.preventDefault();

        // Cancel Real Order
        if (abortControllerRef.current) {
            abortControllerRef.current.abort();
            abortControllerRef.current = null;
        }

        // Cancel Simulation
        simulationTimeoutsRef.current.forEach(timeoutId => clearTimeout(timeoutId));
        simulationTimeoutsRef.current = [];

        setOrderStatus('cancelled');
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setOrderStatus('processing');
        setErrorMessage(null);
        setOrderDetails(null);

        // Abort previous request if any
        if (abortControllerRef.current) abortControllerRef.current.abort();

        // Create new controller
        const controller = new AbortController();
        abortControllerRef.current = controller;

        try {
            // Simulate a small delay
            await new Promise(r => {
                const id = setTimeout(r, 800);
                simulationTimeoutsRef.current.push(id);
            });

            if (controller.signal.aborted) return;

            const payload = {
                symbol: symbol,
                order_type: orderType,
                price_type: priceType,
                price: priceType === 'market' ? 0 : parseFloat(price),
                mode: mode,
                quantity: mode === 'quantity' ? parseFloat(value) : null,
                amount: mode === 'amount' ? parseFloat(value) : null,
                percent: (mode === 'percent_cash' || mode === 'percent_holding') ? parseFloat(value) / 100 : null
            };

            const data = await placeManualOrder(payload, { signal: controller.signal });

            setOrderDetails({
                filled: data.quantity,
                total: data.quantity,
                avgPrice: data.price
            });

            await new Promise(r => {
                const id = setTimeout(r, 600);
                simulationTimeoutsRef.current.push(id);
            });

            if (!controller.signal.aborted) {
                setOrderStatus('success');
            }
        } catch (error) {
            if (error.name === 'CanceledError' || error.name === 'AbortError') {
                setOrderStatus('cancelled');
            } else {
                const msg = error.response?.data?.detail || error.message || 'Order failed';
                setErrorMessage(msg);
                setOrderStatus('error');
            }
        } finally {
            abortControllerRef.current = null;
        }
    };

    const handleSimulation = async () => {
        setOrderStatus('processing');
        setErrorMessage(null);
        setOrderDetails({ filled: 0, total: 100, avgPrice: 0 }); // Init

        simulationTimeoutsRef.current = []; // Reset timeouts

        const steps = [
            { delay: 1000, action: () => setOrderDetails({ filled: 30, total: 100, avgPrice: 75000 }) },
            { delay: 1000, action: () => setOrderDetails({ filled: 80, total: 100, avgPrice: 75200 }) },
            {
                delay: 1000, action: () => {
                    setOrderDetails({ filled: 100, total: 100, avgPrice: 75100 });
                    setOrderStatus('success');
                }
            }
        ];

        // Execute steps sequentially, checking for cancellation implicitly via timeouts clearing
        let accumulatedDelay = 0;
        for (const step of steps) {
            accumulatedDelay += step.delay;
            const timeoutId = setTimeout(() => {
                // If this runs, it means it wasn't cleared (cancelled)
                step.action();
            }, accumulatedDelay);
            simulationTimeoutsRef.current.push(timeoutId);
        }
    };

    return (
        <div className="bg-white/5 border border-white/10 rounded-xl p-6 backdrop-blur-md">
            <h2 className="text-lg font-semibold mb-4 text-blue-300">Manual Trade</h2>

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
                                onClick={() => setOrderStatus('idle')}
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
