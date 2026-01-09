import React, { useEffect, useRef, useState } from 'react';
import { createChart, ColorType, CandlestickSeries, createSeriesMarkers, LineSeries } from 'lightweight-charts';

const VisualBacktestChart = ({
    data,
    trades,
    yAxisFormatter,
    priceScaleOptions,
    showOnlyPnl,
    onChartClick, // Event Handler for Single Click
    customControls // Custom UI Elements (Rank Selector, etc.)
}) => {
    const chartContainerRef = useRef();
    const overlayCanvasRef = useRef(); // Canvas for 1px Lines
    const chartInstance = useRef(null);
    const seriesInstance = useRef(null);
    const markersPluginRef = useRef(null);
    const tradeSeriesRef = useRef(null);

    // UI State
    const [isReady, setIsReady] = useState(false);
    const [sliderValue, setSliderValue] = useState(100);
    const [isPlaying, setIsPlaying] = useState(false);
    const [speed, setSpeed] = useState(100);
    const [zoomLevel, setZoomLevel] = useState(60);

    // Data Refs
    const allDataRef = useRef([]);
    const allTradesRef = useRef([]);
    const allTradePriceDataRef = useRef([]);
    const dayChangesRef = useRef([]); // Store timestamps of day boundaries

    // Helper to Draw Date Separators (Canvas Overlay)
    const drawSeparators = () => {
        const chart = chartInstance.current;
        const canvas = overlayCanvasRef.current;
        if (!chart || !canvas || dayChangesRef.current.length === 0) return;

        const ctx = canvas.getContext('2d');
        const dpr = window.devicePixelRatio || 1;
        const width = canvas.clientWidth * dpr;
        const height = canvas.clientHeight * dpr;

        // Clear Canvas
        ctx.clearRect(0, 0, width, height);

        // Styling
        ctx.strokeStyle = 'rgba(75, 85, 99, 0.5)'; // #4B5563 with 0.5 Opacity
        ctx.lineWidth = 1; // 1px Line (User Requirement)
        ctx.beginPath();

        const timeScale = chart.timeScale();

        dayChangesRef.current.forEach(ts => {
            const x = timeScale.timeToCoordinate(ts);
            if (x !== null) {
                // Adjust x for DPR if ctx is scaled?
                // Scale is applied in ResizeObserver
                ctx.moveTo(x, 0);
                ctx.lineTo(x, height / dpr); // height is physical pixels, divide by dpr
            }
        });

        ctx.stroke();
    };

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

                // [NEW] Pre-calculate Day Change Timestamps for Overlay
                const dayChanges = [];
                let lastDateStr = null;
                validData.forEach(d => {
                    const dateStr = new Date(d.time * 1000).toLocaleDateString('ko-KR', { timeZone: 'Asia/Seoul' });
                    if (lastDateStr && dateStr !== lastDateStr) {
                        dayChanges.push(d.time);
                    }
                    lastDateStr = dateStr;
                });
                dayChangesRef.current = dayChanges;


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
                        vertLines: { visible: !showOnlyPnl, color: '#1f2937' },
                        horzLines: { visible: !showOnlyPnl, color: '#1f2937' },
                    },
                    crosshair: {
                        vertLine: { visible: !showOnlyPnl, labelVisible: !showOnlyPnl },
                        horzLine: { visible: !showOnlyPnl, labelVisible: false },
                    },
                    width: chartContainerRef.current.clientWidth,
                    height: 500,
                    timeScale: {
                        timeVisible: true,
                        secondsVisible: true,
                        borderColor: '#374151',
                        rightOffset: 12,
                        tickMarkFormatter: (time, tickMarkType) => {
                            const date = new Date(time * 1000);
                            if (tickMarkType < 3) {
                                const d = new Intl.DateTimeFormat('ko-KR', {
                                    month: 'numeric',
                                    day: 'numeric',
                                }).format(date);
                                return `[[ ${d} ]]`;
                            } else {
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
                        ...(priceScaleOptions?.fixedYRange ? {
                            autoScale: false,
                            scaleMargins: { top: 0.1, bottom: 0.1 },
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

                // 4. Add Series (Candles)
                const seriesColor = showOnlyPnl ? 'rgba(0,0,0,0)' : undefined;
                const series = chart.addSeries(CandlestickSeries, {
                    upColor: seriesColor || '#26a69a',
                    downColor: seriesColor || '#ef5350',
                    borderVisible: false,
                    wickUpColor: seriesColor || '#26a69a',
                    wickDownColor: seriesColor || '#ef5350',
                    priceLineVisible: !showOnlyPnl,
                    lastValueVisible: !showOnlyPnl,
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

                // 5. Add Invisible Helper Series for Crosshair
                const tradePriceSeries = chart.addSeries(LineSeries, {
                    color: 'rgba(0, 0, 0, 0)',
                    lineVisible: false,
                    pointMarkersVisible: false,
                    crosshairMarkerVisible: true,
                    crosshairMarkerRadius: 4,
                    lastValueVisible: false,
                    priceLineVisible: false,
                    title: 'W/L Price',
                });
                tradeSeriesRef.current = tradePriceSeries;

                const tradeMap = new Map();
                processedTrades.forEach(t => {
                    tradeMap.set(t.time, { time: t.time, value: t.price });
                });
                const tradePriceData = Array.from(tradeMap.values()).sort((a, b) => a.time - b.time);
                allTradePriceDataRef.current = tradePriceData;
                if (tradePriceData.length > 0) tradePriceSeries.setData(tradePriceData);

                // 6. Initialize Markers Plugin
                try {
                    const markersPlugin = createSeriesMarkers(series, []);
                    markersPluginRef.current = markersPlugin;
                    if (validData.length > 0) {
                        const endTime = validData[validData.length - 1].time;
                        updateMarkersInViewLogic(endTime, markersPlugin);
                    }
                } catch (err) { }

                chartInstance.current = chart;

                // Initial Viewport
                const total = validData.length;
                chart.timeScale().setVisibleLogicalRange({
                    from: total - zoomLevel,
                    to: total
                });

                // 7. Subscribe to Layout/Range Changes for Canvas Overlay
                chart.timeScale().subscribeVisibleLogicalRangeChange(() => {
                    requestAnimationFrame(drawSeparators);
                });
                chart.timeScale().subscribeVisibleTimeRangeChange(() => {
                    requestAnimationFrame(drawSeparators);
                });

                // Resize Observer (Handles Chart AND Canvas)
                try {
                    const resizeObserver = new ResizeObserver(entries => {
                        if (chartInstance.current && entries[0]) {
                            const { width, height } = entries[0].contentRect;

                            // 1. Resize Chart
                            chartInstance.current.applyOptions({ width, height });

                            // 2. Resize Canvas (Overlay)
                            if (overlayCanvasRef.current) {
                                const dpr = window.devicePixelRatio || 1;
                                overlayCanvasRef.current.width = width * dpr;
                                overlayCanvasRef.current.height = height * dpr;

                                const ctx = overlayCanvasRef.current.getContext('2d');
                                ctx.scale(dpr, dpr);

                                requestAnimationFrame(drawSeparators);
                            }
                        }
                    });
                    resizeObserver.observe(chartContainerRef.current);
                } catch (e) { }

                setIsReady(true);

                // Initial Draw
                setTimeout(drawSeparators, 200);

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
            onChartClick({ time: param.time, price: price });
        };

        chartInstance.current.subscribeClick(clickHandler);
        return () => {
            if (chartInstance.current) chartInstance.current.unsubscribeClick(clickHandler);
        };
    }, [data, trades, onChartClick, isReady]);

    // Marker Logic
    const updateMarkersInViewLogic = (endTime, plugin = null) => {
        const targetPlugin = plugin || markersPluginRef.current;
        if (!targetPlugin || !allTradesRef.current.length) return;
        const visibleTrades = allTradesRef.current.filter(t => t.time <= endTime);
        let lastBuyPrice = 0;
        const markers = visibleTrades.map(t => {
            const realPrice = t.original_price !== undefined ? t.original_price : t.price;
            if (t.type === 'buy') {
                lastBuyPrice = realPrice;
                if (showOnlyPnl) return null;
                return {
                    time: t.time, price: t.price, position: 'atPriceBottom', color: '#00BFFF', shape: 'arrowUp', text: 'BUY', size: 1
                };
            } else {
                let pnlPercent = 0;
                if (t.pnl_percent !== undefined) pnlPercent = t.pnl_percent;
                else if (lastBuyPrice > 0) pnlPercent = (realPrice - lastBuyPrice) / lastBuyPrice;
                const isWin = pnlPercent > 0;
                return {
                    time: t.time, price: t.price,
                    position: showOnlyPnl ? 'inBar' : 'atPriceTop',
                    color: isWin ? '#00FF00' : '#FF0055',
                    shape: showOnlyPnl ? 'circle' : 'arrowDown',
                    text: (pnlPercent * 100).toFixed(2) + "%",
                    size: showOnlyPnl ? 0.5 : 1
                };
            }
        }).filter(m => m !== null);
        targetPlugin.setMarkers(markers);
    };

    // Helper: Update View Range + Markers + Separators
    const updateChartState = (index) => {
        if (!seriesInstance.current || !chartInstance.current || !allDataRef.current.length) return;
        const visibleData = allDataRef.current.slice(0, index);
        seriesInstance.current.setData(visibleData);

        if (tradeSeriesRef.current && allTradePriceDataRef.current.length > 0) {
            const lastTime = visibleData[visibleData.length - 1].time;
            const visibleTrades = allTradePriceDataRef.current.filter(d => d.time <= lastTime);
            tradeSeriesRef.current.setData(visibleTrades);
        }

        const lastCandle = visibleData[visibleData.length - 1];
        if (lastCandle) updateMarkersInViewLogic(lastCandle.time);

        const from = Math.max(0, index - zoomLevel);
        const to = index;
        chartInstance.current.timeScale().setVisibleLogicalRange({ from, to });

        // Redraw separators after update
        requestAnimationFrame(drawSeparators);
    };

    // Playback Animation
    useEffect(() => {
        let interval;
        if (isPlaying) {
            interval = setInterval(() => {
                setSliderValue(prev => {
                    if (prev >= 100) { setIsPlaying(false); return 100; }
                    return Math.min(prev + 0.2, 100);
                });
            }, speed);
        }
        return () => clearInterval(interval);
    }, [isPlaying, speed]);

    // Slider Effect
    useEffect(() => {
        if (!isReady || allDataRef.current.length === 0) return;
        const total = allDataRef.current.length;
        const minCandles = 30;
        const targetCount = minCandles + Math.floor((sliderValue / 100) * (total - minCandles));
        const index = Math.min(targetCount, total);
        updateChartState(index);
    }, [sliderValue, isReady, zoomLevel]);

    const [showDebugModal, setShowDebugModal] = useState(false);
    const [debugContent, setDebugContent] = useState("");

    return (
        <div className="w-full flex flex-col gap-2">
            {showDebugModal && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
                    <div className="bg-gray-800 border border-gray-600 rounded-lg shadow-2xl w-full max-w-lg flex flex-col max-h-[80vh]">
                        <div className="flex items-center justify-between p-3 border-b border-gray-700">
                            <h3 className="text-gray-200 font-bold text-sm">Data Inspector</h3>
                            <button onClick={() => setShowDebugModal(false)} className="text-gray-400 hover:text-white">✕</button>
                        </div>
                        <div className="p-3 flex-1 overflow-hidden flex flex-col gap-2">
                            <textarea readOnly value={debugContent} className="w-full flex-1 bg-gray-900 border border-gray-700 rounded p-2 text-xs font-mono text-green-400 resize-none focus:outline-none" onClick={(e) => e.target.select()} />
                        </div>
                        <div className="p-3 border-t border-gray-700 flex justify-end">
                            <button onClick={() => { navigator.clipboard.writeText(debugContent); alert("Copied!"); }} className="bg-blue-600 hover:bg-blue-500 text-white text-xs px-3 py-1.5 rounded">Copy to Clipboard</button>
                        </div>
                    </div>
                </div>
            )}

            <div className="w-full h-[500px] relative bg-gray-900 rounded-lg overflow-hidden border border-gray-700 shadow-xl">
                {!isReady && (
                    <div className="absolute inset-0 flex items-center justify-center z-20 bg-gray-900 text-gray-500 font-mono text-sm animate-pulse">
                        initializing chart...
                    </div>
                )}
                {/* HTML Canvas Overlay for 1px Lines - FIX: Z-Index 20 to be ABOVE Chart (Z-10) */}
                <canvas
                    ref={overlayCanvasRef}
                    className="absolute inset-0 w-full h-full pointer-events-none"
                    style={{ zIndex: 20 }}
                />
                <div ref={chartContainerRef} className="w-full h-full relative" style={{ zIndex: 10 }} />
            </div>

            {isReady && (
                <div className="w-full bg-gray-800/50 rounded-lg p-3 border border-gray-700 flex items-center gap-4 shadow-lg">
                    <button onClick={() => { if (sliderValue >= 100) setSliderValue(0); setIsPlaying(!isPlaying); }} className="w-8 h-8 flex items-center justify-center bg-blue-600 rounded-full hover:bg-blue-500 text-white shadow transition-all active:scale-95 shrink-0">
                        {isPlaying ? "⏸" : "▶"}
                    </button>
                    <div className="flex flex-col min-w-[80px] shrink-0">
                        <div className="flex items-center gap-1">
                            <span className="text-[10px] text-gray-400 font-bold uppercase tracking-wider">Replay</span>
                            {allDataRef.current.length > 1 && (
                                <span className="text-[10px] bg-gray-700 px-1 rounded text-gray-300">
                                    {(() => {
                                        const d = allDataRef.current;
                                        const diff = d[1].time - d[0].time;
                                        const min = Math.floor(diff / 60);
                                        return min >= 60 ? `${min / 60}h` : `${min}m`;
                                    })()}
                                </span>
                            )}
                        </div>
                        <span className="text-xs text-blue-300 font-mono font-bold whitespace-nowrap">
                            {(() => {
                                if (!allDataRef.current.length) return "";
                                const total = allDataRef.current.length;
                                const minCandles = 30;
                                const targetCount = minCandles + Math.floor((sliderValue / 100) * (total - minCandles));
                                const index = Math.min(targetCount, total) - 1;
                                const item = allDataRef.current[index];
                                return item ? new Date(item.time * 1000).toLocaleString('ko-KR', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : "";
                            })()}
                        </span>
                    </div>

                    <input type="range" min="0" max="100" step="0.05" value={sliderValue} onChange={(e) => { setIsPlaying(false); setSliderValue(Number(e.target.value)); }} className="w-full h-1.5 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-blue-500 hover:accent-blue-400" />

                    <div className="flex gap-2 shrink-0 items-center">
                        {customControls && (
                            <div className="mr-2 border-r border-gray-700 pr-2">
                                {customControls}
                            </div>
                        )}
                        <select value={zoomLevel} onChange={(e) => setZoomLevel(Number(e.target.value))} className="bg-gray-900 border border-gray-600 rounded text-[10px] px-2 py-1 text-gray-300 outline-none focus:border-blue-500 hover:bg-gray-800 transition-colors">
                            <option value={30}>Zoom: 30</option>
                            <option value={60}>Zoom: 60</option>
                            <option value={120}>Zoom: 120</option>
                            <option value={300}>Zoom: 300</option>
                        </select>
                        <select value={speed} onChange={(e) => setSpeed(Number(e.target.value))} className="bg-gray-900 border border-gray-600 rounded text-[10px] px-2 py-1 text-gray-300 outline-none focus:border-blue-500 hover:bg-gray-800 transition-colors">
                            <option value={1000}>Speed: 0.1x</option>
                            <option value={330}>Speed: 0.3x</option>
                            <option value={200}>Speed: 0.5x</option>
                            <option value={100}>Speed: 1x</option>
                            <option value={50}>Speed: 2x</option>
                            <option value={10}>Speed: Max</option>
                        </select>
                        <button onClick={() => { const debugText = allDataRef.current.slice(0, 10).map(d => { const date = new Date(d.time * 1000); return `[${d.time}] ${date.toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' })}`; }).join('\n'); setDebugContent(debugText); setShowDebugModal(true); }} className="bg-red-600 text-white text-[10px] px-2 py-1 rounded hover:bg-red-500 font-bold shadow-lg animate-pulse">INSPECT</button>
                    </div>
                </div>
            )}
        </div>
    );
};

export default VisualBacktestChart;
