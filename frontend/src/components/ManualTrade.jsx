import React, { useState } from 'react';
import OrderProgress from './OrderProgress';
import OutstandingOrders from './OutstandingOrders';
import WatchList from './WatchList';
import { useManualTrade } from '../hooks/useManualTrade';

const ManualTrade = ({ defaultSymbol }) => {
    const {
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
        handleSubmit,
        handleWatchSubmit,
        handleCancel,
        handleSimulation,
        resetStatus,

        // Watch Order State
        conditionType, setConditionType,
        triggerPrice, setTriggerPrice,
        watchOrderType, setWatchOrderType,
        trailingPercent, setTrailingPercent,

        currentPrice, fetchPrice,
        outstandingOrders, fetchOutstanding, handleCancelOrder, isLoadingOrders,

        // Watch List Exports
        watchOrders, fetchWatchOrders, handleCancelWatchOrder, isLoadingWatchOrders
    } = useManualTrade(defaultSymbol);

    const [showAdvanced, setShowAdvanced] = useState(false);
    const [activeTab, setActiveTab] = useState('instant'); // 'instant', 'watch', 'watchlist', 'outstanding'

    // Auto refresh lists when tab active
    React.useEffect(() => {
        if (activeTab === 'outstanding') {
            fetchOutstanding();
        } else if (activeTab === 'watchlist') {
            fetchWatchOrders();
        }
    }, [activeTab, fetchOutstanding, fetchWatchOrders]);

    return (
        <div className="p-1">
            {/* Tabs */}
            <div className="flex space-x-4 mb-4 border-b border-white/10 pb-2 overflow-x-auto">
                <button
                    onClick={() => setActiveTab('instant')}
                    className={`pb-1 px-2 whitespace-nowrap ${activeTab === 'instant' ? 'text-blue-400 border-b-2 border-blue-400 font-bold' : 'text-gray-400 hover:text-white'}`}
                >
                    Instant Order
                </button>
                <button
                    onClick={() => setActiveTab('watch')}
                    className={`pb-1 px-2 whitespace-nowrap ${activeTab === 'watch' ? 'text-purple-400 border-b-2 border-purple-400 font-bold' : 'text-gray-400 hover:text-white'}`}
                >
                    Register Watch
                </button>
                <button
                    onClick={() => setActiveTab('watchlist')}
                    className={`pb-1 px-2 whitespace-nowrap ${activeTab === 'watchlist' ? 'text-green-400 border-b-2 border-green-400 font-bold' : 'text-gray-400 hover:text-white'}`}
                >
                    Watch List
                </button>
                <button
                    onClick={() => setActiveTab('outstanding')}
                    className={`pb-1 px-2 whitespace-nowrap ${activeTab === 'outstanding' ? 'text-yellow-400 border-b-2 border-yellow-400 font-bold' : 'text-gray-400 hover:text-white'}`}
                >
                    Outstanding
                </button>
            </div>

            {activeTab === 'instant' ? (
                /* Instant Order Form */
                <form onSubmit={handleSubmit} className="space-y-4">
                    <div className="grid grid-cols-2 gap-4">
                        <div>
                            <label className="block text-sm text-gray-400 mb-1 flex justify-between">
                                Symbol
                                <span className="text-xs text-blue-400 font-mono flex items-center gap-1 cursor-pointer hover:text-blue-300" onClick={fetchPrice}>
                                    {currentPrice !== null ? `${currentPrice.toLocaleString()} KRW` : 'Get Price'} ↻
                                </span>
                            </label>
                            <input
                                type="text"
                                value={symbol}
                                onChange={(e) => setSymbol(e.target.value)}
                                className="w-full bg-black/40 border border-white/5 rounded p-2 text-white focus:outline-none focus:border-blue-500"
                                placeholder="Symbol (e.g 005930)"
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

                    <div className="pt-2 border-t border-white/5">
                        <button
                            type="button"
                            onClick={() => setShowAdvanced(!showAdvanced)}
                            className="flex items-center gap-2 text-xs text-gray-400 hover:text-white transition-colors w-full py-1"
                        >
                            <span className={`transform transition-transform ${showAdvanced ? 'rotate-90' : ''}`}>▶</span>
                            Advanced Options (Stop Loss / Take Profit)
                        </button>

                        {showAdvanced && (
                            <div className="grid grid-cols-2 gap-4 mt-2 mb-4 pl-2 bg-black/20 p-2 rounded">
                                {/* Stop Loss */}
                                <div className="space-y-1">
                                    <label className="flex items-center gap-2 cursor-pointer select-none">
                                        <input
                                            type="checkbox"
                                            checked={stopLoss.enabled}
                                            onChange={(e) => setStopLoss({ ...stopLoss, enabled: e.target.checked })}
                                            className="rounded border-gray-600 bg-black/20 text-red-500 focus:ring-0"
                                        />
                                        <span className="text-xs text-gray-300">Stop Loss</span>
                                    </label>
                                    <div className="flex items-center gap-2 relative">
                                        <span className="absolute left-2 text-gray-500 text-xs">-</span>
                                        <input
                                            type="number"
                                            value={stopLoss.percent}
                                            onChange={(e) => setStopLoss({ ...stopLoss, percent: parseFloat(e.target.value) || 0 })}
                                            disabled={!stopLoss.enabled}
                                            className={`w-full bg-black/20 border text-right px-2 pl-4 py-1.5 text-xs rounded transition-colors ${stopLoss.enabled ? 'border-gray-600 text-white' : 'border-transparent text-gray-600 cursor-not-allowed'}`}
                                        />
                                        <span className="text-xs text-gray-500 w-4">%</span>
                                    </div>
                                </div>

                                {/* Take Profit */}
                                <div className="space-y-1">
                                    <label className="flex items-center gap-2 cursor-pointer select-none">
                                        <input
                                            type="checkbox"
                                            checked={takeProfit.enabled}
                                            onChange={(e) => setTakeProfit({ ...takeProfit, enabled: e.target.checked })}
                                            className="rounded border-gray-600 bg-black/20 text-green-500 focus:ring-0"
                                        />
                                        <span className="text-xs text-gray-300">Take Profit</span>
                                    </label>
                                    <div className="flex items-center gap-2 relative">
                                        <span className="absolute left-2 text-gray-500 text-xs">+</span>
                                        <input
                                            type="number"
                                            value={takeProfit.percent}
                                            onChange={(e) => setTakeProfit({ ...takeProfit, percent: parseFloat(e.target.value) || 0 })}
                                            disabled={!takeProfit.enabled}
                                            className={`w-full bg-black/20 border text-right px-2 pl-4 py-1.5 text-xs rounded transition-colors ${takeProfit.enabled ? 'border-gray-600 text-white' : 'border-transparent text-gray-600 cursor-not-allowed'}`}
                                        />
                                        <span className="text-xs text-gray-500 w-4">%</span>
                                    </div>
                                </div>
                            </div>
                        )}
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
            ) : activeTab === 'watch' ? (
                /* Watch Order Form */
                <form onSubmit={handleWatchSubmit} className="space-y-4">
                    <div className="grid grid-cols-2 gap-4">
                        <div>
                            <label className="block text-sm text-gray-400 mb-1 flex justify-between">
                                Symbol
                                <span className="text-xs text-blue-400 font-mono flex items-center gap-1 cursor-pointer hover:text-blue-300" onClick={fetchPrice}>
                                    {currentPrice !== null ? `${currentPrice.toLocaleString()} KRW` : 'Get Price'} ↻
                                </span>
                            </label>
                            <input
                                type="text"
                                value={symbol}
                                onChange={(e) => setSymbol(e.target.value)}
                                className="w-full bg-black/40 border border-white/5 rounded p-2 text-white focus:outline-none focus:border-purple-500"
                                placeholder="Symbol"
                                required
                            />
                        </div>
                        <div>
                            <label className="block text-sm text-gray-400 mb-1">Trigger Price</label>
                            <input
                                type="number"
                                value={triggerPrice}
                                onChange={(e) => setTriggerPrice(e.target.value)}
                                className="w-full bg-black/40 border border-white/10 rounded p-2 text-white focus:outline-none focus:border-purple-500"
                                placeholder="Trigger Price"
                                required
                            />
                        </div>
                    </div>

                    {/* Condition Type Selection */}
                    {/* Buy/Sell Watch Type Toggle */}
                    <div className="flex bg-black/40 p-1 rounded">
                        <button
                            type="button"
                            onClick={() => setWatchOrderType('buy')}
                            className={`flex-1 py-1 rounded text-sm font-medium transition-colors ${watchOrderType === 'buy' ? 'bg-red-500/80 text-white' : 'text-gray-400 hover:text-white'}`}
                        >
                            Buy (Entry)
                        </button>
                        <button
                            type="button"
                            onClick={() => setWatchOrderType('sell')}
                            className={`flex-1 py-1 rounded text-sm font-medium transition-colors ${watchOrderType === 'sell' ? 'bg-blue-500/80 text-white' : 'text-gray-400 hover:text-white'}`}
                        >
                            Sell (Exit)
                        </button>
                    </div>

                    {/* Condition Type Selection */}
                    {watchOrderType === 'buy' ? (
                        <div className="flex bg-black/40 p-1 rounded">
                            <button
                                type="button"
                                onClick={() => setConditionType('BUY_STOP')}
                                className={`flex-1 py-2 rounded text-xs font-medium transition-colors flex flex-col items-center gap-1 ${conditionType === 'BUY_STOP' ? 'bg-purple-500/80 text-white' : 'text-gray-400 hover:text-white'}`}
                            >
                                <span className="text-sm font-bold">🚀 Breakout (Buy Stop)</span>
                                <span className="opacity-70">Price &ge; Trigger</span>
                            </button>
                            <button
                                type="button"
                                onClick={() => setConditionType('BUY_LIMIT')}
                                className={`flex-1 py-2 rounded text-xs font-medium transition-colors flex flex-col items-center gap-1 ${conditionType === 'BUY_LIMIT' ? 'bg-blue-500/80 text-white' : 'text-gray-400 hover:text-white'}`}
                            >
                                <span className="text-sm font-bold">📉 Dip Buy (Buy Limit)</span>
                                <span className="opacity-70">Price &le; Trigger</span>
                            </button>
                        </div>
                    ) : (
                        <div className="flex bg-black/40 p-1 rounded gap-1">
                            <button
                                type="button"
                                onClick={() => setConditionType('STOP_LOSS')}
                                className={`flex-1 py-2 rounded text-xs font-medium transition-colors flex flex-col items-center gap-1 ${conditionType === 'STOP_LOSS' ? 'bg-red-500/80 text-white' : 'text-gray-400 hover:text-white'}`}
                            >
                                <span className="text-sm font-bold">🛡️ Stop Loss</span>
                                <span className="opacity-70">Price &le; Trigger</span>
                            </button>
                            <button
                                type="button"
                                onClick={() => setConditionType('TAKE_PROFIT')}
                                className={`flex-1 py-2 rounded text-xs font-medium transition-colors flex flex-col items-center gap-1 ${conditionType === 'TAKE_PROFIT' ? 'bg-green-500/80 text-white' : 'text-gray-400 hover:text-white'}`}
                            >
                                <span className="text-sm font-bold">💰 Take Profit</span>
                                <span className="opacity-70">Price &ge; Trigger</span>
                            </button>
                            <button
                                type="button"
                                onClick={() => setConditionType('TRAILING_STOP')}
                                className={`flex-1 py-2 rounded text-xs font-medium transition-colors flex flex-col items-center gap-1 ${conditionType === 'TRAILING_STOP' ? 'bg-yellow-500/80 text-white' : 'text-gray-400 hover:text-white'}`}
                            >
                                <span className="text-sm font-bold">📉 Trailing Stop</span>
                                <span className="opacity-70">Follow High</span>
                            </button>
                        </div>
                    )}

                    {/* Trailing Percent Input */}
                    {conditionType === 'TRAILING_STOP' && (
                        <div className="mt-2">
                            <label className="block text-sm text-yellow-400 mb-1">Trailing Percent (%)</label>
                            <div className="flex items-center gap-2 relative">
                                <span className="absolute left-3 text-gray-500 text-sm">-</span>
                                <input
                                    type="number"
                                    value={trailingPercent}
                                    onChange={(e) => setTrailingPercent(e.target.value)}
                                    className="w-full bg-black/40 border border-yellow-500/50 rounded p-2 pl-6 text-white focus:outline-none focus:border-yellow-500"
                                    placeholder="e.g. 3.0"
                                    required
                                />
                                <span className="text-sm text-gray-400">%</span>
                            </div>
                            <p className="text-[10px] text-gray-500 mt-1">
                                * Sell if price drops by X% from the highest price reached.
                            </p>
                        </div>
                    )}

                    <div>
                        <label className="block text-sm text-gray-400 mb-1">Mode</label>
                        <select
                            value={mode}
                            onChange={(e) => setMode(e.target.value)}
                            className="w-full bg-black/40 border border-white/10 rounded p-2 text-white focus:outline-none focus:border-purple-500"
                        >
                            <option value="quantity">Fixed Quantity</option>
                            <option value="amount">Fixed Amount (KRW)</option>
                        </select>
                    </div>

                    <div>
                        <label className="block text-sm text-gray-400 mb-1">
                            {mode === 'quantity' ? 'Quantity' : 'Amount (KRW)'}
                        </label>
                        <input
                            type="number"
                            value={value}
                            onChange={(e) => setValue(e.target.value)}
                            className="w-full bg-black/40 border border-white/10 rounded p-2 text-white focus:outline-none focus:border-purple-500"
                            placeholder="Value"
                            required
                        />
                    </div>

                    {/* Reuse Stop Loss / Take Profit UI?
                        Currently ConditionalOrderRequest doesn't support SL/TP on Entry (chained conditions),
                        but we can add 'Coming Soon' or hide it.
                        Let's hide it for simplicity in MVP to avoid complexity overload.
                    */}

                    <div className="flex flex-col gap-3 pt-4 border-t border-white/5">
                        {orderStatus === 'processing' ? (
                            <button
                                type="button"
                                disabled
                                className="w-full bg-purple-500/20 text-purple-300 border border-purple-500/50 font-bold py-2 rounded animate-pulse"
                            >
                                Registering Watch Order...
                            </button>
                        ) : (
                            <button
                                type="submit"
                                className="w-full bg-gradient-to-r from-purple-500 to-indigo-600 hover:from-purple-600 hover:to-indigo-700 text-white font-bold py-2 rounded transition-all"
                            >
                                Register Watch Order
                            </button>
                        )}
                    </div>
                </form>
            ) : activeTab === 'watchlist' ? (
                /* Watch List Tab */
                <div className="space-y-4">
                    <div className="flex justify-between items-center">
                        <h3 className="text-sm font-bold text-gray-300">Active Watch Orders</h3>
                        <button
                            onClick={fetchWatchOrders}
                            disabled={isLoadingWatchOrders}
                            className="text-xs text-green-400 hover:text-green-300 flex items-center gap-1"
                        >
                            <span className={isLoadingWatchOrders ? "animate-spin" : ""}>↻</span> Refresh
                        </button>
                    </div>
                    <WatchList
                        orders={watchOrders}
                        onCancel={handleCancelWatchOrder}
                        isLoading={isLoadingWatchOrders}
                    />
                </div>
            ) : (
                /* Outstanding Orders Tab */
                <div className="space-y-4">
                    <div className="flex justify-between items-center">
                        <h3 className="text-sm font-bold text-gray-300">Outstanding Orders</h3>
                        <button
                            onClick={fetchOutstanding}
                            disabled={isLoadingOrders}
                            className="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1"
                        >
                            <span className={isLoadingOrders ? "animate-spin" : ""}>↻</span> Refresh
                        </button>
                    </div>
                    <OutstandingOrders
                        orders={outstandingOrders}
                        onCancel={handleCancelOrder}
                        isLoading={isLoadingOrders}
                    />
                </div>
            )}
        </div >
    );
};

export default ManualTrade;
