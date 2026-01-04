import React, { useEffect, useRef, useState } from 'react';
import { createChart, ColorType, CandlestickSeries, createSeriesMarkers, LineSeries } from 'lightweight-charts';

const VisualBacktestChart = ({
    data,
    trades,
    yAxisFormatter,
    priceScaleOptions,
    showOnlyPnl,
    onChartClick // Event Handler for Single Click
}) => {
    const chartContainerRef = useRef();
    const chartInstance = useRef(null);
    const seriesInstance = useRef(null);
    const markersPluginRef = useRef(null);
    const tradeSeriesRef = useRef(null); // Ref for invisible price series

    // UI State
    const [isReady, setIsReady] = useState(false);
    const [sliderValue, setSliderValue] = useState(100);
    const [isPlaying, setIsPlaying] = useState(false);
    const [speed, setSpeed] = useState(100);
    const [zoomLevel, setZoomLevel] = useState(60);

    // Data Refs
    const allDataRef = useRef([]);
    const allTradesRef = useRef([]);
    const allTradePriceDataRef = useRef([]); // Store full trade price data

    useEffect(() => {
        if (!data || data.length === 0 || !chartContainerRef.current) return;

        // Cleanup
        if (chartInstance.current) {
            chartInstance.current.remove();
            chartInstance.current = null;
        }
        setIsReady(false);

        const timer = setTimeout(() => {
            console.log("Chart: Starting Initialization...");
            try {
                // 1. Process Candle Data
                const uniqueDataMap = new Map();
                data.forEach(item => {
                    let time = item.time;
                    if (typeof time === 'string') time = new Date(time).getTime() / 1000;
                    const timeNum = Number(time);
                    if (!isNaN(timeNum)) {
                        uniqueDataMap.set(timeNum, {
                            time: timeNum,
                            open: Number(item.open),
                            high: Number(item.high),
                            low: Number(item.low),
                            close: Number(item.close)
                        });
                    }
                });
                const validData = Array.from(uniqueDataMap.values()).sort((a, b) => a.time - b.time);
                allDataRef.current = validData;

                // 2. Process Trades
                let processedTrades = [];
                try {
                    if (trades && Array.isArray(trades)) {
                        processedTrades = trades.map(t => {
                            let time = t.time;
                            if (typeof time === 'string') time = new Date(time).getTime() / 1000;
                            return { ...t, time: Number(time) };
                        }).sort((a, b) => a.time - b.time);
                        allTradesRef.current = processedTrades;
                    }
                } catch (err) {
                    console.error("Chart: Trade Processing Error", err);
                }

                // 3. Create Chart Instance
                const chart = createChart(chartContainerRef.current, {
                    layout: {
                        background: { type: ColorType.Solid, color: '#111827' },
                        textColor: '#9ca3af',
                    },
                    grid: {
                        vertLines: { color: '#1f2937' },
                        horzLines: { color: '#1f2937' },
                    },
                    width: chartContainerRef.current.clientWidth,
                    height: 500,
                    timeScale: {
                        timeVisible: true,
                        secondsVisible: true,
                        borderColor: '#374151',
                        rightOffset: 12,
                        tickMarkFormatter: (time, tickMarkType, locale) => {
                            const date = new Date(time * 1000);

                            // tickMarkType: 0=Year, 1=Month, 2=DayOfMonth, 3=Time, 4=TimeWithSeconds
                            // If Type < 3, it's a date boundary (Day/Month/Year change). Show Date.
                            if (tickMarkType < 3) {
                                // Date only: MM/DD
                                return new Intl.DateTimeFormat('ko-KR', {
                                    timeZone: 'Asia/Seoul',
                                    month: 'numeric',
                                    day: 'numeric',
                                }).format(date).replace(/\. /g, '/').replace('.', '');
                            } else {
                                // Time only: HH:mm
                                return new Intl.DateTimeFormat('ko-KR', {
                                    timeZone: 'Asia/Seoul',
                                    hour: '2-digit',
                                    minute: '2-digit',
                                    hour12: false
                                }).format(date);
                            }
                        }
                    },
                    rightPriceScale: {
                        borderColor: '#374151',
                        ...priceScaleOptions,
                        // If fixedYRange is provided, use it to LOCK the Y-axis range
                        ...(priceScaleOptions?.fixedYRange ? {
                            autoScale: false, // Turn off generic autoscale
                            scaleMargins: { top: 0, bottom: 0 }, // We manage margins via the range itself usually, or keep inherited. 
                            // Actually, autoscaleInfoProvider works WITH autoScale=true usually to 'suggest' range.
                            // But for PURE locking, we override it. 
                            // Lightweight Charts 4.0 trick:
                            // We might just need series.applyOptions({ autoscaleInfoProvider: ... }) ?
                            // No, chart options don't have this. Series do.
                        } : {}),
                    },
                    localization: {
                        timezone: 'Asia/Seoul',
                        dateFormat: 'yyyy-MM-dd',
                        timeFormatter: (timestamp) => {
                            const date = new Date(timestamp * 1000);
                            return date.toLocaleTimeString('ko-KR', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit', timeZone: 'Asia/Seoul' });
                        },
                        priceFormatter: (price) => {
                            if (yAxisFormatter) return yAxisFormatter(price);
                            return price.toFixed(2);
                        }
                    },
                });

                // 4. Add Series (Faded Candles)
                // If showOnlyPnl is true, we hide the candlestick visuals (transparent)
                const transparent = 'rgba(0, 0, 0, 0)';
                const series = chart.addSeries(CandlestickSeries, {
                    upColor: showOnlyPnl ? transparent : '#26a69a4D',
                    downColor: showOnlyPnl ? transparent : '#ef53504D',
                    borderVisible: !showOnlyPnl,
                    borderColor: '#4b5563',
                    wickVisible: !showOnlyPnl,
                    wickUpColor: showOnlyPnl ? transparent : '#26a69a4D',
                    wickDownColor: showOnlyPnl ? transparent : '#ef53504D',
                    borderUpColor: showOnlyPnl ? transparent : '#26a69a80',
                    borderDownColor: showOnlyPnl ? transparent : '#ef535080',
                    autoscaleInfoProvider: priceScaleOptions?.fixedYRange
                        ? () => ({
                            priceRange: {
                                minValue: priceScaleOptions.fixedYRange.min,
                                maxValue: priceScaleOptions.fixedYRange.max,
                            },
                        })
                        : undefined,
                });
                series.setData(validData);
                seriesInstance.current = series;

                // 5. Add Invisible Helper Series for Crosshair Price Labels
                const tradePriceSeries = chart.addSeries(LineSeries, {
                    color: 'rgba(0, 0, 0, 0)', // Invisible line
                    lineVisible: false,
                    pointMarkersVisible: false,
                    crosshairMarkerVisible: true, // Show dot only on hover
                    crosshairMarkerRadius: 4,
                    lastValueVisible: false,
                    priceLineVisible: false,
                    title: 'W/L Price',
                });

                // Prepare Data (Deduplicated for LineSeries)
                const tradeMap = new Map();
                processedTrades.forEach(t => {
                    tradeMap.set(t.time, {
                        time: t.time,
                        value: t.price
                    });
                });
                const tradePriceData = Array.from(tradeMap.values()).sort((a, b) => a.time - b.time);

                // Helper ref to update this series on slider move
                // We attach it to a temporary property on the chart instance or just manage it here
                // Simplest is to just set it once for the full range if we aren't dynamically slicing it strictly.
                // Wait, we DO slice data in playback. So we need a ref for this series too.
                tradePriceSeries.setData(tradePriceData);

                // We need to expose this series to the updateChartState function
                // Let's store it in a ref. We can reuse 'dotSeriesRef' or create 'tradeSeriesRef'.
                // Since I removed dotSeriesRef in previous step, I will create a new ref or just use a property.
                // Actually, I need to add `tradeSeriesRef` to the component top level first.
                // For this edit, I'll rely on `seriesInstance` pattern.

                // BETTER: Just set the data once. 
                // LineSeries handles data outside the visible range gracefully? 
                // Yes, but for "Replay", we want to hide future trades.
                // So I MUST maintain a reference to update it.
                // I will overwrite `lineSeriesRef` which is currently unused/removed.
                // Wait, I removed `lineSeriesRef` in the previous "Clean" step.
                // I need to check if `lineSeriesRef` still exists in the file.
                // I'll assume I need to RE-ADD the ref definition if I deleted it.

                // Let's look at the file content again or just add the Ref definition in the `MultiReplace` if needed.
                // Or I can use `useRef` inside the component body in a separate `replace_file_content`.
                // Actually, I'll just add `const tradeSeriesRef = useRef(null);` at the top and use it.
                // But `replace_file_content` is a single block edit.

                // Strategy: 
                // 1. Modify component start to add `tradeSeriesRef`.
                // 2. Modify init logic to create and assign `tradePriceSeries`.
                // 3. Modify `updateChartState` to update `tradePriceSeries`.

                // This requires MULTIPLE edits.
                // I will use `multi_replace_file_content`.


                // 5. Initialize Markers Plugin (Arrows at EXACT Price)
                try {
                    const markersPlugin = createSeriesMarkers(series, []);
                    markersPluginRef.current = markersPlugin;

                    // Initial Markers
                    if (validData.length > 0) {
                        const endTime = validData[validData.length - 1].time;
                        updateMarkersInViewLogic(endTime, markersPlugin);
                    }
                } catch (err) {
                    console.warn("Chart: Markers Plugin Init Failed:", err);
                }

                chartInstance.current = chart;

                // Initial Viewport
                const total = validData.length;
                chart.timeScale().setVisibleLogicalRange({
                    from: total - zoomLevel,
                    to: total
                });

                // Resize Observer
                try {
                    const resizeObserver = new ResizeObserver(entries => {
                        if (chartInstance.current) {
                            const { width } = entries[0].contentRect;
                            chartInstance.current.applyOptions({ width });
                        }
                    });
                    resizeObserver.observe(chartContainerRef.current);
                } catch (e) { }

                setIsReady(true);

            } catch (e) {
                console.error("Chart: Fatal Init Error:", e);
                setIsReady(true);
            }
        }, 100);

        return () => {
            clearTimeout(timer);
            if (chartInstance.current) chartInstance.current.remove();
        };
    }, [data, trades]);

    // Click Detection Logic
    useEffect(() => {
        if (!chartInstance.current || !seriesInstance.current || !onChartClick) return;

        const clickHandler = (param) => {
            if (!param.point || !param.time) return;

            const price = seriesInstance.current.coordinateToPrice(param.point.y);
            onChartClick({
                time: param.time,
                price: price
            });
        };

        chartInstance.current.subscribeClick(clickHandler);
        return () => {
            if (chartInstance.current) {
                chartInstance.current.unsubscribeClick(clickHandler);
            }
        };
    }, [data, trades, onChartClick, isReady]);

    // Marker Logic Encapsulation
    const updateMarkersInViewLogic = (endTime, plugin = null) => {
        const targetPlugin = plugin || markersPluginRef.current;
        if (!targetPlugin || !allTradesRef.current.length) return;

        const visibleTrades = allTradesRef.current.filter(t => t.time <= endTime);

        let lastBuyPrice = 0; // Track last buy price for PnL calc

        const markers = visibleTrades.map(t => {
            // Use original_price (Asset Price) for PnL, fallback to t.price (Chart Y-Value)
            const realPrice = t.original_price !== undefined ? t.original_price : t.price;

            if (t.type === 'buy') {
                lastBuyPrice = realPrice;
                if (showOnlyPnl) return null; // Hide Buy Markers in Integrated Mode
                return {
                    time: t.time,
                    price: t.price, // Plot at Chart Y (Lane or Price)
                    position: 'atPriceBottom', // Arrow sits below price, pointing UP
                    color: '#00BFFF',
                    shape: 'arrowUp',
                    text: 'BUY',
                    size: 1 // Reduced size for thinner look
                };
            } else {
                // Calculate PnL manually if not provided
                let pnlPercent = 0;
                if (t.pnl_percent !== undefined) {
                    pnlPercent = t.pnl_percent;
                } else if (lastBuyPrice > 0) {
                    pnlPercent = (realPrice - lastBuyPrice) / lastBuyPrice;
                }

                const isWin = pnlPercent > 0;
                const pnlText = (pnlPercent * 100).toFixed(2) + "%";

                return {
                    time: t.time,
                    price: t.price, // Exact Price
                    position: showOnlyPnl ? 'inBar' : 'atPriceTop', // Use inBar for Integrated (Lane), atPriceTop for Rank
                    color: isWin ? (showOnlyPnl ? '#00FF00' : '#00FF00') : (showOnlyPnl ? '#FF0055' : '#FF0055'),
                    shape: showOnlyPnl ? 'circle' : 'arrowDown',
                    text: pnlText,
                    size: showOnlyPnl ? 0.5 : 1 // Smallest possible dot
                };
            }
        }).filter(m => m !== null); // Filter out hidden markers

        targetPlugin.setMarkers(markers);
    };

    // Helper: Update View Range + Markers
    const updateChartState = (index) => {
        if (!seriesInstance.current || !chartInstance.current || !allDataRef.current.length) return;

        const visibleData = allDataRef.current.slice(0, index);
        seriesInstance.current.setData(visibleData);

        // 2. Update Trade Price Series (Sync with playback)
        if (tradeSeriesRef.current && allTradePriceDataRef.current.length > 0) {
            const lastTime = visibleData[visibleData.length - 1].time;
            const visibleTrades = allTradePriceDataRef.current.filter(d => d.time <= lastTime);
            tradeSeriesRef.current.setData(visibleTrades);
        }

        const lastCandle = visibleData[visibleData.length - 1];
        if (lastCandle) {
            updateMarkersInViewLogic(lastCandle.time);
        }

        const from = Math.max(0, index - zoomLevel);
        const to = index;
        chartInstance.current.timeScale().setVisibleLogicalRange({ from, to });
    };

    // Playback Animation Loop
    useEffect(() => {
        let interval;
        if (isPlaying) {
            interval = setInterval(() => {
                setSliderValue(prev => {
                    if (prev >= 100) {
                        setIsPlaying(false);
                        return 100;
                    }
                    return Math.min(prev + 0.2, 100);
                });
            }, speed);
        }
        return () => clearInterval(interval);
    }, [isPlaying, speed]);

    // Effect: Slider Change -> Update Chart
    useEffect(() => {
        if (!isReady || allDataRef.current.length === 0) return;

        const total = allDataRef.current.length;
        const minCandles = 30;
        const targetCount = minCandles + Math.floor((sliderValue / 100) * (total - minCandles));
        const index = Math.min(targetCount, total);

        updateChartState(index);

    }, [sliderValue, isReady, zoomLevel]);

    // ... helper ...
    const getCurrentDate = () => {
        if (!allDataRef.current.length) return "";
        const total = allDataRef.current.length;
        const minCandles = 30;
        const targetCount = minCandles + Math.floor((sliderValue / 100) * (total - minCandles));
        const index = Math.min(targetCount, total) - 1;
        const item = allDataRef.current[index];
        return item ? new Date(item.time * 1000).toLocaleDateString() : "";
    };

    return (
        <div className="w-full flex flex-col gap-2">
            <div className="w-full h-[500px] relative bg-gray-900 rounded-lg overflow-hidden border border-gray-700 shadow-xl">
                {!isReady && (
                    <div className="absolute inset-0 flex items-center justify-center z-20 bg-gray-900 text-gray-500 font-mono text-sm animate-pulse">
                        initializing chart...
                    </div>
                )}

                {/* Chart Canvas */}
                <div ref={chartContainerRef} className="w-full h-full relative z-10" />
            </div>

            {/* Playback Controls (Moved Below Chart) */}
            {isReady && (
                <div className="w-full bg-gray-800/50 rounded-lg p-3 border border-gray-700 flex items-center gap-4 shadow-lg">
                    <button
                        onClick={() => {
                            if (sliderValue >= 100) setSliderValue(0);
                            setIsPlaying(!isPlaying);
                        }}
                        className="w-8 h-8 flex items-center justify-center bg-blue-600 rounded-full hover:bg-blue-500 text-white shadow transition-all active:scale-95 shrink-0"
                    >
                        {isPlaying ? "⏸" : "▶"}
                    </button>

                    <div className="flex flex-col min-w-[80px] shrink-0">
                        <span className="text-[10px] text-gray-400 font-bold uppercase tracking-wider">Replay</span>
                        <span className="text-xs text-blue-300 font-mono font-bold">{getCurrentDate()}</span>
                    </div>

                    <input
                        type="range"
                        min="0"
                        max="100"
                        step="0.05"
                        value={sliderValue}
                        onChange={(e) => {
                            setIsPlaying(false);
                            setSliderValue(Number(e.target.value));
                        }}
                        className="w-full h-1.5 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-blue-500 hover:accent-blue-400"
                    />

                    <div className="flex gap-2 shrink-0">
                        <select
                            value={zoomLevel}
                            onChange={(e) => setZoomLevel(Number(e.target.value))}
                            className="bg-gray-900 border border-gray-600 rounded text-[10px] px-2 py-1 text-gray-300 outline-none focus:border-blue-500 hover:bg-gray-800 transition-colors"
                        >
                            <option value={30}>Zoom: 30</option>
                            <option value={60}>Zoom: 60</option>
                            <option value={120}>Zoom: 120</option>
                            <option value={300}>Zoom: 300</option>
                        </select>

                        <select
                            value={speed}
                            onChange={(e) => setSpeed(Number(e.target.value))}
                            className="bg-gray-900 border border-gray-600 rounded text-[10px] px-2 py-1 text-gray-300 outline-none focus:border-blue-500 hover:bg-gray-800 transition-colors"
                        >
                            <option value={1000}>Speed: 0.1x</option>
                            <option value={330}>Speed: 0.3x</option>
                            <option value={200}>Speed: 0.5x</option>
                            <option value={100}>Speed: 1x</option>
                            <option value={50}>Speed: 2x</option>
                            <option value={10}>Speed: Max</option>
                        </select>
                    </div>
                </div>
            )}
        </div>
    );
};

export default VisualBacktestChart;
