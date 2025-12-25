import { useState, useRef, useEffect, useCallback } from 'react';
import {
    placeManualOrder,
    placeConditionalOrder,
    getOutstandingOrders,
    cancelOrder,
    getPrice,
    getConditionalOrders, // New
    cancelConditionalOrder // New
} from '../api/client';

export const useManualTrade = (defaultSymbol) => {
    // ... (Existing State) ...
    const [symbol, setSymbol] = useState(defaultSymbol || '');
    useEffect(() => {
        if (defaultSymbol) setSymbol(defaultSymbol);
    }, [defaultSymbol]);

    const [price, setPrice] = useState('');
    const [currentPrice, setCurrentPrice] = useState(null);
    const [orderType, setOrderType] = useState('buy');
    const [priceType, setPriceType] = useState('limit');
    const [mode, setMode] = useState('quantity');
    const [value, setValue] = useState('');

    // Watch Order States - Conditions
    const [watchOrderType, setWatchOrderType] = useState('buy');
    const [conditionType, setConditionType] = useState('BUY_STOP');
    const [triggerPrice, setTriggerPrice] = useState('');
    const [trailingPercent, setTrailingPercent] = useState('');

    // Watch Order List State
    const [watchOrders, setWatchOrders] = useState([]);
    const [isLoadingWatchOrders, setIsLoadingWatchOrders] = useState(false);

    // ... (Effects) ...
    useEffect(() => {
        if (watchOrderType === 'buy') {
            setConditionType('BUY_STOP');
        } else {
            setConditionType('STOP_LOSS');
        }
    }, [watchOrderType]);

    const [stopLoss, setStopLoss] = useState({ enabled: false, percent: 3.0 });
    const [takeProfit, setTakeProfit] = useState({ enabled: false, percent: 5.0 });

    const [orderStatus, setOrderStatus] = useState('idle');
    const [errorMessage, setErrorMessage] = useState(null);
    const [orderDetails, setOrderDetails] = useState(null);

    const [outstandingOrders, setOutstandingOrders] = useState([]);
    const [isLoadingOrders, setIsLoadingOrders] = useState(false);

    const abortControllerRef = useRef(null);
    const simulationTimeoutsRef = useRef([]);

    const handleCancel = (e) => {
        if (e) e.preventDefault();
        if (abortControllerRef.current) {
            abortControllerRef.current.abort();
            abortControllerRef.current = null;
        }
        simulationTimeoutsRef.current.forEach(timeoutId => clearTimeout(timeoutId));
        simulationTimeoutsRef.current = [];
        setOrderStatus('cancelled');
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setOrderStatus('processing');
        setErrorMessage(null);
        setOrderDetails(null);
        if (abortControllerRef.current) abortControllerRef.current.abort();
        const controller = new AbortController();
        abortControllerRef.current = controller;

        try {
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
            if (!data) throw new Error("No response data");

            setOrderDetails({
                filled: data.quantity || 0,
                total: data.quantity || 0,
                avgPrice: data.price || 0
            });

            await new Promise(r => {
                const id = setTimeout(r, 600);
                simulationTimeoutsRef.current.push(id);
            });

            if (!controller.signal.aborted) setOrderStatus('success');
        } catch (error) {
            if (error.name === 'CanceledError' || error.name === 'AbortError') {
                setOrderStatus('cancelled');
            } else {
                setErrorMessage(error.response?.data?.detail || error.message || 'Order failed');
                setOrderStatus('error');
            }
        } finally {
            abortControllerRef.current = null;
        }
    };

    const handleWatchSubmit = async (e) => {
        e.preventDefault();
        setOrderStatus('processing');
        setErrorMessage(null);
        setOrderDetails(null);

        try {
            const payload = {
                symbol: symbol,
                condition_type: conditionType,
                trigger_price: parseFloat(triggerPrice),
                order_type: watchOrderType,
                price_type: 'market',
                mode: mode,
                quantity: mode === 'quantity' ? parseFloat(value) : null,
                amount: mode === 'amount' ? parseFloat(value) : null,
                trailing_percent: conditionType === 'TRAILING_STOP' ? parseFloat(trailingPercent) / 100 : null
            };

            const data = await placeConditionalOrder(payload);
            setOrderDetails({ message: data.message, id: data.id || 'N/A' });
            setOrderStatus('success');

            // Refresh Watch List if available
            fetchWatchOrders();

        } catch (error) {
            setErrorMessage(error.response?.data?.detail || error.message || 'Watch Order Failed');
            setOrderStatus('error');
        }
    };

    const handleSimulation = async () => {
        setOrderStatus('processing');
        setErrorMessage(null);
        setOrderDetails({ filled: 0, total: 100, avgPrice: 0 });
        simulationTimeoutsRef.current = [];
        const steps = [
            { delay: 1000, action: () => setOrderDetails({ filled: 30, total: 100, avgPrice: 75000 }) },
            { delay: 1000, action: () => setOrderDetails({ filled: 80, total: 100, avgPrice: 75200 }) },
            { delay: 1000, action: () => { setOrderDetails({ filled: 100, total: 100, avgPrice: 75100 }); setOrderStatus('success'); } }
        ];
        let accumulatedDelay = 0;
        for (const step of steps) {
            accumulatedDelay += step.delay;
            simulationTimeoutsRef.current.push(setTimeout(step.action, accumulatedDelay));
        }
    };

    const fetchOutstanding = useCallback(async () => {
        setIsLoadingOrders(true);
        try {
            const data = await getOutstandingOrders();
            setOutstandingOrders(data || []);
        } catch (e) {
            console.error("Failed to fetch outstanding orders", e);
        } finally {
            setIsLoadingOrders(false);
        }
    }, []);

    const fetchWatchOrders = useCallback(async () => {
        setIsLoadingWatchOrders(true);
        try {
            const data = await getConditionalOrders();
            setWatchOrders(data || []);
        } catch (e) {
            console.error("Failed to fetch watch orders", e);
        } finally {
            setIsLoadingWatchOrders(false);
        }
    }, []);

    const handleCancelOrder = async (order) => {
        if (!confirm(`Cancel order ${order.order_no} (${order.name})?`)) return;
        try {
            await cancelOrder({
                order_no: order.order_no,
                symbol: order.symbol,
                quantity: order.unfilled_qty,
                origin_order_no: order.origin_order_no
            });
            fetchOutstanding();
        } catch (e) {
            alert(e.response?.data?.detail || "Failed to cancel order");
        }
    };

    const handleCancelWatchOrder = async (id) => {
        if (!confirm(`Cancel Watch Order #${id}?`)) return;
        try {
            await cancelConditionalOrder(id);
            fetchWatchOrders();
        } catch (e) {
            console.error("Failed to cancel watch order", e);
            alert(e.response?.data?.detail || "Failed to cancel watch order");
        }
    };

    const fetchPrice = async () => {
        if (!symbol) return;
        try {
            const data = await getPrice(symbol);
            if (data && typeof data.price === 'number') {
                setCurrentPrice(data.price);
                return data.price;
            }
        } catch (e) {
            setCurrentPrice(null);
        }
        return null;
    };

    const resetStatus = () => setOrderStatus('idle');

    useEffect(() => {
        if (symbol && symbol.length >= 6) fetchPrice();
    }, [symbol]);

    return {
        symbol, setSymbol,
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
        conditionType, setConditionType,
        triggerPrice, setTriggerPrice,
        watchOrderType, setWatchOrderType,
        trailingPercent, setTrailingPercent,

        // Watch List Exports
        watchOrders,
        isLoadingWatchOrders,
        fetchWatchOrders,
        handleCancelWatchOrder,

        handleSubmit,
        handleWatchSubmit,
        handleCancel,
        handleSimulation,
        resetStatus,
        fetchPrice,
        currentPrice,
        outstandingOrders,
        fetchOutstanding,
        handleCancelOrder,
        isLoadingOrders
    };
};
