import React, { useState, useEffect } from 'react';
import { getBalance, getPrice } from '../api/client';
import { ChevronDown, ChevronUp, RefreshCw, Wallet, TrendingUp, DollarSign } from 'lucide-react';

const AccountStatusPanel = () => {
    const [balanceData, setBalanceData] = useState(null);
    const [holdingsDetails, setHoldingsDetails] = useState([]);
    const [loading, setLoading] = useState(true);
    const [expanded, setExpanded] = useState(false);
    const [totalAssets, setTotalAssets] = useState(0);
    const [totalInvested, setTotalInvested] = useState(0);

    const fetchData = async () => {
        setLoading(true);
        try {
            // 1. Fetch Balance & Holdings
            // API returns: { cash: { KRW: 10000 }, holdings: { "005930": 10 } }
            const balance = await getBalance();
            setBalanceData(balance);

            const holdings = balance.holdings || {};
            const cash = balance.cash?.KRW || 0;

            // 2. Fetch Current Prices for each holding to calculate valuation
            const details = [];
            let investedSum = 0;

            const symbols = Object.keys(holdings);
            if (symbols.length > 0) {
                const results = await Promise.all(
                    symbols.map(symbol => getPrice(symbol))
                );

                results.forEach((priceInfo, index) => {
                    const symbol = symbols[index];
                    const qty = holdings[symbol];
                    const currentPrice = priceInfo.price;
                    const valuation = currentPrice * qty;

                    investedSum += valuation;
                    details.push({
                        symbol,
                        name: priceInfo.name,
                        quantity: qty,
                        price: currentPrice,
                        valuation: valuation
                    });
                });
            }

            setHoldingsDetails(details);
            setTotalInvested(investedSum);
            setTotalAssets(cash + investedSum);

        } catch (error) {
            console.error("Failed to fetch account status:", error);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchData();
        // Auto-refresh every 30 seconds
        const interval = setInterval(fetchData, 30000);
        return () => clearInterval(interval);
    }, []);

    if (loading && !balanceData) {
        return (
            <div className="max-w-7xl mx-auto px-6 mb-6">
                <div className="bg-white/5 border border-white/10 rounded-xl p-4 animate-pulse h-24"></div>
            </div>
        );
    }

    const formatKRW = (val) => new Intl.NumberFormat('ko-KR', { style: 'currency', currency: 'KRW' }).format(val);

    return (
        <div className="max-w-7xl mx-auto px-6 mb-8 mt-4">
            <div className="bg-gradient-to-r from-gray-900 to-gray-800 border border-white/10 rounded-xl overflow-hidden shadow-2xl">
                {/* Main Status Bar */}
                <div className="p-4 flex flex-col md:flex-row items-center justify-between gap-4">

                    {/* Key Metrics */}
                    <div className="flex flex-wrap items-center gap-6 md:gap-12 flex-1">
                        <div className="flex items-center gap-3">
                            <div className="p-2 bg-blue-500/20 rounded-lg text-blue-400">
                                <Wallet size={24} />
                            </div>
                            <div>
                                <div className="text-xs text-gray-400 font-medium uppercase tracking-wider">Total Assets</div>
                                <div className="text-xl font-bold text-white">{formatKRW(totalAssets)}</div>
                            </div>
                        </div>

                        <div className="flex items-center gap-3">
                            <div className="p-2 bg-emerald-500/20 rounded-lg text-emerald-400">
                                <TrendingUp size={24} />
                            </div>
                            <div>
                                <div className="text-xs text-gray-400 font-medium uppercase tracking-wider">Invested</div>
                                <div className="text-xl font-bold text-white">{formatKRW(totalInvested)}</div>
                            </div>
                        </div>

                        <div className="flex items-center gap-3">
                            <div className="p-2 bg-purple-500/20 rounded-lg text-purple-400">
                                <DollarSign size={24} />
                            </div>
                            <div>
                                <div className="text-xs text-gray-400 font-medium uppercase tracking-wider">Cash (KRW)</div>
                                <div className="text-xl font-bold text-white">{formatKRW(balanceData?.cash?.KRW || 0)}</div>
                            </div>
                        </div>
                    </div>

                    {/* Actions */}
                    <div className="flex items-center gap-2">
                        <button
                            onClick={fetchData}
                            disabled={loading}
                            className={`p-2 rounded-lg hover:bg-white/5 text-gray-400 transition-all ${loading ? 'animate-spin' : ''}`}
                            title="Refresh Data"
                        >
                            <RefreshCw size={20} />
                        </button>
                        <button
                            onClick={() => setExpanded(!expanded)}
                            className="flex items-center gap-1 text-sm text-gray-400 hover:text-white px-3 py-1.5 rounded-lg hover:bg-white/5 transition-colors"
                        >
                            {expanded ? "Hide Details" : "Show Details"}
                            {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                        </button>
                    </div>
                </div>

                {/* Expanded Details Panel */}
                {expanded && (
                    <div className="border-t border-white/5 bg-black/20 p-4 animate-in slide-in-from-top-2 duration-200">
                        <h4 className="text-sm font-semibold text-gray-300 mb-3">Current Holdings</h4>
                        {holdingsDetails.length === 0 ? (
                            <div className="text-gray-500 text-sm py-2">No active holdings.</div>
                        ) : (
                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                                {holdingsDetails.map((item) => (
                                    <div key={item.symbol} className="bg-white/5 rounded-lg p-3 flex items-center justify-between border border-white/5 hover:border-white/10 transition-colors">
                                        <div>
                                            <div className="font-medium text-white">{item.name}</div>
                                            <div className="text-xs text-gray-400">{item.symbol}</div>
                                        </div>
                                        <div className="text-right">
                                            <div className="font-semibold text-white">{formatKRW(item.valuation)}</div>
                                            <div className="text-xs text-gray-400">
                                                {item.quantity} shares × {formatKRW(item.price)}
                                            </div>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
};

export default AccountStatusPanel;
