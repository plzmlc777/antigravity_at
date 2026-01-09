import React, { useMemo, useState, useCallback } from 'react';
import VisualBacktestChart from './VisualBacktestChart';

const IntegratedAnalysis = ({ trades, backtestResult, strategiesConfig }) => {
    // 1. Data Source
    const tradeList = useMemo(() => {
        let list = trades || backtestResult?.trades || [];
        return [...list].sort((a, b) => new Date(a.time) - new Date(b.time));
    }, [trades, backtestResult]);

    // 3. Transform Data & Build Lookup Map
    const { transformedTrades, tradeLookupMap, totalRanks } = useMemo(() => {
        const symbolRankMap = {};

        // Build Map from Config (Rank 1 = Index 0)
        // strategiesConfig is expected to be sorted by Rank 1..N
        console.log("IntegratedAnalysis: Strategies Config:", strategiesConfig); // DEBUG

        if (strategiesConfig && strategiesConfig.length > 0) {
            strategiesConfig.forEach((cfg, index) => {
                const sym = cfg.symbol || "UNKNOWN";
                symbolRankMap[sym] = index + 1; // Rank 1-based
            });
        }
        console.log("IntegratedAnalysis: Symbol Rank Map:", symbolRankMap); // DEBUG

        // Calculate Max Rank dynamically or from config
        let maxRankDerived = strategiesConfig ? strategiesConfig.length : 1;

        const lookup = new Map();

        const transformed = tradeList.map(t => {
            // Priority: Explicit Rank > Symbol Map > Default 1
            let rank = t.strategy_rank || symbolRankMap[t.symbol] || 1;

            // Log warning if symbol not found?
            // console.log(`Mapping ${t.symbol} -> Rank ${rank}`);

            maxRankDerived = Math.max(maxRankDerived, rank);

            // Invert Y for Chart (Rank 1 at top? Recharts Y grows upwards usually)
            // Let's assume standard Y: 0 at bottom.
            // Lane 1 (Rank 1): Y = Total + 1 - 1 = Total
            // Lane N (Rank N): Y = Total + 1 - N = 1
            // So Rank 1 is highest Y value.

            // We need 'totalRanks' to be fixed though.
            // Let's defer Y calculation or do it in a second pass? 
            // Better: Just use maxRankDerived later.
            return {
                ...t,
                _temp_rank: rank,
                original_price: t.price
            };
        });

        const finalizedTrades = transformed.map(t => {
            const yVal = (maxRankDerived + 1) - t._temp_rank;
            const tradeObj = {
                ...t,
                strategy_rank: t._temp_rank,
                price: yVal // Override price for Scatter/Candle Y-axis
            };

            // Lookup Key
            const timeMin = Math.floor(new Date(t.time).getTime() / 60000);
            const rankY = Math.round(yVal);
            const key = `${timeMin}_${rankY}`;
            lookup.set(key, tradeObj);

            return tradeObj;
        });

        return {
            transformedTrades: finalizedTrades,
            tradeLookupMap: lookup,
            totalRanks: maxRankDerived
        };
    }, [tradeList, strategiesConfig]);

    const syntheticData = useMemo(() => {
        if (!transformedTrades.length) return [];

        const uniqueTimeMap = new Map();

        transformedTrades.forEach(trade => {
            const timeVal = new Date(trade.time).getTime() / 1000;
            const timeNum = Math.floor(timeVal);
            const yVal = trade.price;

            const existing = uniqueTimeMap.get(timeNum);

            if (existing) {
                uniqueTimeMap.set(timeNum, {
                    time: timeNum,
                    open: existing.open,
                    high: Math.max(existing.high, yVal),
                    low: Math.min(existing.low, yVal),
                    close: yVal,
                });
            } else {
                uniqueTimeMap.set(timeNum, {
                    time: timeNum,
                    open: yVal,
                    high: yVal,
                    low: yVal,
                    close: yVal,
                });
            }
        });

        const dataArray = Array.from(uniqueTimeMap.values()).sort((a, b) => a.time - b.time);
        if (dataArray.length === 0) return [];
        return dataArray;
    }, [transformedTrades]);


    // 4. Formatter & Options
    const rankFormatter = (price) => {
        const yVal = Math.round(price);
        if (Math.abs(price - yVal) < 0.1) {
            const rank = (totalRanks + 1) - yVal;

            if (rank > 0 && rank <= totalRanks) {
                const count = transformedTrades.filter(t => t.strategy_rank === rank && t.type === 'sell').length;
                return `Rank ${rank} (${count})`;
            }
        }
        return "";
    };

    const priceScaleOptions = {
        fixedYRange: {
            min: 0.5,
            max: totalRanks + 0.5
        },
        autoScale: false,
        minimumWidth: 80, // Prevent Rank text cutoff
    };

    // 5. Interaction
    const [isModalOpen, setIsModalOpen] = useState(false);
    const [modalData, setModalData] = useState(null);
    const [debugLogs, setDebugLogs] = useState([]);

    const handleChartClick = useCallback((param) => {
        if (!param || !param.time || !param.price) return;

        const logs = [];
        const addLog = (msg) => logs.push(`[${new Date().toLocaleTimeString()}] ${msg}`);

        addLog(`Clicked Time=${param.time}, Price=${param.price}`);

        // O(1) Lookup Strategy
        const clickTimeMin = Math.floor(param.time / 60);
        const clickRankY = Math.round(param.price);
        const lookupKey = `${clickTimeMin}_${clickRankY}`;

        const clickedTrade = tradeLookupMap.get(lookupKey);

        if (clickedTrade) {
            addLog(`Trade Found (Map): ${clickedTrade.symbol} @ ${clickedTrade.time}`);
            const symbol = clickedTrade.symbol;

            // 2. Get Data
            const allCandles = backtestResult?.multi_ohlcv_data?.[symbol] || [];
            addLog(`Total Candles for ${symbol}: ${allCandles.length}`);

            // 3. Filter using Correct Timestamp Logic
            const tradeDate = new Date(clickedTrade.time);
            const startOfDay = new Date(tradeDate).setHours(0, 0, 0, 0) / 1000; // Seconds
            const endOfDay = new Date(tradeDate).setHours(23, 59, 59, 999) / 1000; // Seconds

            const dailyCandles = allCandles.filter(c => {
                // c.time is ALREADY in seconds from backend. Do not wrap in new Date()!
                const cTime = c.time;
                return cTime >= startOfDay && cTime <= endOfDay;
            });
            addLog(`Daily Candles (Filtered): ${dailyCandles.length}`);

            // 4. Get ALL Trades for this Symbol & Date (to show Buys & Sells)
            const dailyTrades = transformedTrades.filter(t => {
                if (t.symbol !== symbol) return false;
                const tTime = new Date(t.time).getTime() / 1000;
                return tTime >= startOfDay && tTime <= endOfDay;
            }).map(t => ({
                ...t,
                // Critical Fix: Restore 'price' to 'original_price' so it plots on the Candle Chart Y-axis
                price: t.original_price || t.price
            }));
            addLog(`Daily Trades Found: ${dailyTrades.length}`);
            dailyTrades.forEach((dt, i) => {
                addLog(`[${i + 1}] ${dt.type.toUpperCase()}: ${dt.time} (${new Date(dt.time).toLocaleTimeString()})`);
            });

            // ALWAYS OPEN MODAL & SET STATE
            // Reverted Resampling Logic to ensure stability
            setModalData({
                symbol: symbol,
                date: tradeDate.toLocaleDateString(),
                data: dailyCandles,
                trades: dailyTrades // Pass the full list
            });
            setDebugLogs(logs);
            setIsModalOpen(true);

        } else {
            addLog(`No matching trade found for key: ${lookupKey}`);
            setModalData(null);
            setDebugLogs(logs);
            setIsModalOpen(true);
        }
    }, [tradeLookupMap, backtestResult, transformedTrades]);

    // 6. Render
    if (!tradeList.length) {
        return (
            <div className="text-gray-500 text-center py-20 flex flex-col items-center justify-center gap-2">
                <span className="text-4xl">📭</span>
                <p>No Trades Available to Visualize.</p>
            </div>
        );
    }

    // 7. Rank Selector Logic (Task 2)
    const [selectedRank, setSelectedRank] = useState(1); // Default Rank 1

    const rankOptions = useMemo(() => {
        const ranks = [];
        for (let i = 1; i <= totalRanks; i++) {
            ranks.push(i);
        }
        return ranks;
    }, [totalRanks]);

    const rankSelectorUI = (
        <select
            value={selectedRank}
            onChange={(e) => setSelectedRank(Number(e.target.value))}
            className="bg-gray-800 border border-gray-600 rounded text-[10px] px-2 py-1 text-white outline-none focus:border-blue-500 hover:bg-gray-700 transition-colors font-bold"
        >
            {rankOptions.map(r => (
                <option key={r} value={r}>Rank {r}</option>
            ))}
        </select>
    );

    return (
        <div className="w-full relative">
            <VisualBacktestChart
                data={syntheticData}
                trades={transformedTrades}
                yAxisFormatter={rankFormatter}
                priceScaleOptions={priceScaleOptions}
                showOnlyPnl={true}
                onChartClick={handleChartClick}
                customControls={rankSelectorUI}
            />

            {/* Drill-Down Modal */}
            {isModalOpen && (
                <div
                    className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm"
                    onClick={() => setIsModalOpen(false)}
                >
                    <div
                        className="bg-gray-900 border border-gray-700 w-[90vw] h-[80vh] rounded-xl shadow-2xl flex flex-col overflow-hidden"
                        onClick={e => e.stopPropagation()}
                    >
                        {/* Header */}
                        <div className="bg-gray-800 px-4 py-3 border-b border-gray-700 flex justify-between items-center">
                            <div className="flex items-center gap-3">
                                <h3 className="text-lg font-bold text-white">
                                    {modalData ? modalData.symbol : "Debug Mode"}
                                </h3>
                                {modalData && (
                                    <span className="text-sm text-gray-400 bg-black/30 px-2 py-0.5 rounded">
                                        {modalData.date}
                                    </span>
                                )}
                            </div>
                            <button
                                onClick={() => setIsModalOpen(false)}
                                className="text-gray-400 hover:text-white transition-colors"
                            >
                                ✕
                            </button>
                        </div>

                        {/* Content Body: Chart + Logs */}
                        <div className="flex-1 w-full bg-[#111827] flex flex-col relative">
                            {/* Chart Area */}
                            <div className="flex-1 relative border-b border-gray-800">
                                {modalData && modalData.data.length > 0 ? (
                                    <VisualBacktestChart
                                        data={modalData.data}
                                        trades={modalData.trades}
                                        showOnlyPnl={false}
                                    />
                                ) : (
                                    <div className="absolute inset-0 flex items-center justify-center text-gray-500">
                                        {modalData ? "Chart Data Empty" : "No Trade Selected"}
                                    </div>
                                )}
                            </div>

                            {/* Debug Console */}
                            <div className="h-32 bg-black/90 p-3 overflow-y-auto font-mono text-xs text-green-400 border-t border-gray-700">
                                <div className="font-bold text-gray-500 mb-2 sticky top-0 bg-black/90 pb-1 border-b border-gray-800 flex justify-between">
                                    <span>CONSOLE LOGS (O(1) Map Lookup)</span>
                                    <button onClick={() => setDebugLogs([])} className="hover:text-white transition-colors">Clear</button>
                                </div>
                                {debugLogs.map((log, i) => (
                                    <div key={i} className="whitespace-pre-wrap mb-1 border-b border-gray-800/50 pb-0.5">{log}</div>
                                ))}
                                {debugLogs.length === 0 && <div className="text-gray-600 italic">Waiting for interactions...</div>}
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default IntegratedAnalysis;
