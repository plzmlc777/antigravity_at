import React, { useState } from 'react';
import { useMarketData } from '../context/MarketDataContext';
import { ChevronDown, ChevronUp, RefreshCw, Wallet, TrendingUp, DollarSign } from 'lucide-react';
import Card from './common/Card';

const AccountStatusPanel = () => {
    const {
        balanceData,
        holdingsDetails,
        totalAssets,
        totalInvested,
        loading,
        refresh
    } = useMarketData();

    const [expanded, setExpanded] = useState(false);

    if (loading && !balanceData) {
        return (
            <div className="max-w-7xl mx-auto px-6 mb-6">
                <div className="bg-white/5 border border-white/10 rounded-xl p-4 animate-pulse h-24"></div>
            </div>
        );
    }

    const formatKRW = (val) => new Intl.NumberFormat('ko-KR', { style: 'decimal' }).format(val);

    return (
        <div className="max-w-7xl mx-auto px-6 mb-8 mt-4">

            <Card>
                {/* Main Status Bar */}
                <div className="flex flex-col md:flex-row items-center justify-between gap-4">

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
                            onClick={refresh}
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
                    <div className="mt-4 pt-4 border-t border-white/5 animate-in slide-in-from-top-2 duration-200">
                        <h4 className="text-sm font-semibold text-gray-300 mb-3">Current Holdings</h4>
                        {holdingsDetails.length === 0 ? (
                            <div className="text-gray-500 text-sm py-2">No active holdings.</div>
                        ) : (
                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                                {holdingsDetails.map((item) => (
                                    <div key={item.symbol} className="bg-white/5 rounded-lg p-3 border border-white/5 hover:border-white/10 transition-colors">
                                        <div className="flex justify-between items-start mb-2">
                                            <div>
                                                <div className="font-medium text-white">{item.name}</div>
                                                <div className="text-xs text-gray-400">{item.symbol}</div>
                                            </div>
                                            <div className="text-right">
                                                <div className="font-semibold text-white">{formatKRW(item.valuation)}</div>
                                                <div className="text-xs text-gray-400">
                                                    {item.quantity} shares
                                                </div>
                                            </div>
                                        </div>

                                        <div className="flex justify-between items-center text-xs mt-2 pt-2 border-t border-white/5">
                                            <div className="text-gray-400">
                                                Avg: <span className="text-gray-300">{formatKRW(item.avgPrice)}</span>
                                            </div>
                                            <div className={`flex gap-3 ${item.profitAmount >= 0 ? 'text-red-400' : 'text-blue-400'}`}>
                                                <span>{item.profitRate > 0 ? '+' : ''}{item.profitRate}%</span>
                                                <span>{item.profitAmount > 0 ? '+' : ''}{formatKRW(item.profitAmount)}</span>
                                            </div>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                )}
            </Card>
        </div>
    );
};

export default AccountStatusPanel;
