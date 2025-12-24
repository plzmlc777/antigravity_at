import { useState, useRef, useEffect } from 'react';
import { placeManualOrder } from '../api/client';

export const useManualTrade = (defaultSymbol) => {
    const [symbol, setSymbol] = useState(defaultSymbol || '');
    useEffect(() => {
        if (defaultSymbol) setSymbol(defaultSymbol);
    }, [defaultSymbol]);

    const [price, setPrice] = useState('');
    const [orderType, setOrderType] = useState('buy');
    const [priceType, setPriceType] = useState('limit'); // 'limit' or 'market'
    const [mode, setMode] = useState('quantity');
    const [value, setValue] = useState('');

    // Advanced Options (Stop Loss / Take Profit)
    const [stopLoss, setStopLoss] = useState({ enabled: false, percent: 3.0 });
    const [takeProfit, setTakeProfit] = useState({ enabled: false, percent: 5.0 });

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
                percent: (mode === 'percent_cash' || mode === 'percent_holding') ? parseFloat(value) / 100 : null,
                stop_loss: stopLoss.enabled ? stopLoss.percent : undefined,
                take_profit: takeProfit.enabled ? takeProfit.percent : undefined
            };

            const data = await placeManualOrder(payload, { signal: controller.signal });

            if (!data) {
                throw new Error("No response data received from server");
            }

            setOrderDetails({
                filled: data.quantity || 0,
                total: data.quantity || 0,
                avgPrice: data.price || 0
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
                const msg = error.response?.data?.detail
                    ? (typeof error.response.data.detail === 'object'
                        ? JSON.stringify(error.response.data.detail)
                        : error.response.data.detail)
                    : error.message || 'Order failed';
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

    const resetStatus = () => setOrderStatus('idle');

    return {
        // State
        symbol,
        price, setPrice,
        orderType, setOrderType,
        priceType, setPriceType,
        mode, setMode,
        value, setValue,
        stopLoss, setStopLoss,
        takeProfit, setTakeProfit,
        orderStatus,
        errorMessage,
        orderDetails,

        // Actions
        handleSubmit,
        handleCancel,
        handleSimulation,
        resetStatus
    };
};
