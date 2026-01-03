import React, { useMemo } from 'react';
import VisualBacktestChart from './VisualBacktestChart';

const IntegratedAnalysis = ({ trades, backtestResult }) => {
    // 1. Data Source
    const tradeList = useMemo(() => {
        let list = trades || backtestResult?.trades || [];
        return [...list].sort((a, b) => new Date(a.time) - new Date(b.time));
    }, [trades, backtestResult]);

    // 2. Identify Ranks
    // User wants "Rank 1, Rank 2..." lanes.
    // The backend provides 'strategy_rank' in the trade object.
    const { totalRanks } = useMemo(() => {
        // Find max rank from trades or default to 1
        const maxRank = tradeList.reduce((max, t) => {
            return Math.max(max, t.strategy_rank || 1);
        }, 0);

        // If no rank info, maybe just 1 lane? Or count symbols?
        // Fallback: If MAX rank is 0 or 1 but multiple symbols exist, use symbol count.
        // But assuming backend provides rank.
        const count = Math.max(maxRank, 1);

        return { totalRanks: count };
    }, [tradeList]);

    // 3. Transform Data 
    const transformedTrades = useMemo(() => {
        // RANK INFERENCE LOGIC:
        // Sells often lack 'strategy_rank' in the raw data.
        // We must propagate rank from the corresponding Buy.
        // Since trades are time-sorted, we can track "Last Rank for Symbol".

        const symbolRankMap = {};

        return tradeList.map(t => {
            let rank = t.strategy_rank;

            // If Buy, update the map
            if (t.type === 'buy' && rank) {
                symbolRankMap[t.symbol] = rank;
            }

            // If Sell (or missing rank), try to infer from last known rank for this symbol
            if (!rank) {
                rank = symbolRankMap[t.symbol] || 1; // Default to 1 if unknown
            }

            // Determine Y-Value based on Rank
            // Rank 1 (Top) -> Y = totalRanks
            // Rank N (Bottom) -> Y = 1
            // Formula: Y = (Total + 1) - Rank
            const yVal = (totalRanks + 1) - rank;

            return {
                ...t,
                strategy_rank: rank, // Fill distinct rank for downstream use if needed
                original_price: t.price,
                price: yVal // Map to Y-Lane
            };
        });
    }, [tradeList, totalRanks]);

    const syntheticData = useMemo(() => {
        if (!transformedTrades.length) return [];

        const uniqueTimeMap = new Map();

        transformedTrades.forEach(trade => {
            const timeVal = new Date(trade.time).getTime() / 1000;
            const timeNum = Math.floor(timeVal);
            const yVal = trade.price;

            // Simplified: Just use Close = Y-Value.
            const existing = uniqueTimeMap.get(timeNum);

            if (existing) {
                uniqueTimeMap.set(timeNum, {
                    time: timeNum,
                    open: existing.open,
                    high: Math.max(existing.high, yVal),
                    low: Math.min(existing.low, yVal),
                    close: yVal, // Latest
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

        // Add Padder Points?
        // Not needed if we use scaleMargins effectively, but to be safe against single-point data
        // we can let autoScale handle it.
        return dataArray;
    }, [transformedTrades]);


    // 4. Formatter & Options
    const rankFormatter = (price) => {
        const yVal = Math.round(price);
        if (Math.abs(price - yVal) < 0.1) {
            // Convert Y-Value back to Rank
            // Y = (Total + 1) - Rank  =>  Rank = (Total + 1) - Y
            const rank = (totalRanks + 1) - yVal;

            if (rank > 0 && rank <= totalRanks) {
                // Calculate count for this rank (Only calculate once or memoize ideally, but this is fast enough)
                // We count 'Sell' markers (Results) as completed trades? Or 'Entries'?
                // User sees Sells in chart. Let's count Sells (Results).
                const count = transformedTrades.filter(t => t.strategy_rank === rank && t.type === 'sell').length;

                // Or count Entries? "Total Trades". Usually implies pairs. 
                // If we used 'sell' markers, let's match that count.
                return `Rank ${rank} (${count})`;
            }
        }
        return "";
    };

    // Force strict visual padding so Y=1 and Y=count don't touch edges
    const priceScaleOptions = {
        // Enforce fixed range: 0.5 to Total+0.5
        // This ensures Y=1, Y=2, Y=3... occupy equal vertical segments.
        fixedYRange: {
            min: 0.5,
            max: totalRanks + 0.5
        },
        // We can disable autoScale explicitly here too to be safe, though Chart handles it via fixedYRange check
        autoScale: false,
    };

    // 5. Render
    if (!tradeList.length) {
        return (
            <div className="text-gray-500 text-center py-20 flex flex-col items-center justify-center gap-2">
                <span className="text-4xl">📭</span>
                <p>No Trades Available to Visualize.</p>
            </div>
        );
    }

    return (
        <div className="w-full">
            <VisualBacktestChart
                data={syntheticData}
                trades={transformedTrades}
                yAxisFormatter={rankFormatter}
                priceScaleOptions={priceScaleOptions}
                showOnlyPnl={true}
            />
        </div>
    );
};

export default IntegratedAnalysis;
