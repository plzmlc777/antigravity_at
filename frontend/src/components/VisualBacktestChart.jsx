import React, { useEffect, useRef } from 'react';
import { createChart, ColorType } from 'lightweight-charts';

const VisualBacktestChart = ({ data, trades }) => {
    const chartContainerRef = useRef();
    const chartInstance = useRef(null);

    useEffect(() => {
        if (!data || data.length === 0 || !chartContainerRef.current) return;

        // Cleanup previous instance
        if (chartInstance.current) {
            chartInstance.current.remove();
        }

        const chart = createChart(chartContainerRef.current, {
            layout: {
                background: { type: ColorType.Solid, color: '#1a1c23' },
                textColor: '#d1d5db',
            },
            grid: {
                vertLines: { color: '#334155' },
                horzLines: { color: '#334155' },
            },
            width: chartContainerRef.current.clientWidth,
            height: 400,
            timeScale: {
                timeVisible: true,
                secondsVisible: false,
                borderColor: '#4b5563',
            },
            rightPriceScale: {
                borderColor: '#4b5563',
            },
        });

        chartInstance.current = chart;

        // Candlestick Series
        const candlestickSeries = chart.addCandlestickSeries({
            upColor: '#26a69a',
            downColor: '#ef5350',
            borderVisible: false,
            wickUpColor: '#26a69a',
            wickDownColor: '#ef5350',
        });

        // Ensure data is sorted by time (Backtest engine usually does this, but safety check)
        // And lightweight charts needs unique sorted time.
        // We assume backend resampling handled this well, but let's dedupe if needed?
        // Let's trust backend for now to save perf.
        candlestickSeries.setData(data);

        // Process Trades for Markers
        // Logic: Snap trades to nearest available chart data point
        const markers = [];
        if (trades && trades.length > 0) {
            const dataTimes = data.map(d => ({
                original: d.time,
                ts: new Date(d.time).getTime()
            }));

            trades.forEach(t => {
                const tradeTs = new Date(t.time).getTime();
                let closestTime = null;
                let minDiff = Infinity;

                // Find nearest candle
                for (const dt of dataTimes) {
                    const diff = Math.abs(dt.ts - tradeTs);
                    if (diff < minDiff) {
                        minDiff = diff;
                        closestTime = dt.original;
                    }
                }

                if (closestTime && minDiff < 3600000 * 24) { // Only show if within reasonable range (e.g. 24h)
                    // Determine Marker Color & Shape
                    const isBuy = t.type === 'buy';
                    markers.push({
                        time: closestTime,
                        position: isBuy ? 'belowBar' : 'aboveBar',
                        color: isBuy ? '#2196F3' : '#E91E63',
                        shape: isBuy ? 'arrowUp' : 'arrowDown',
                        text: `${isBuy ? 'B' : 'S'}`,
                        size: 1
                    });
                }
            });

            // Sort markers by time (required by lightweight-charts?) - Actually markers don't strictly need sort but better.
            markers.sort((a, b) => new Date(a.time) - new Date(b.time));

            candlestickSeries.setMarkers(markers);
        }

        // Fit Content
        chart.timeScale().fitContent();

        const handleResize = () => {
            if (chartContainerRef.current && chartInstance.current) {
                chartInstance.current.applyOptions({ width: chartContainerRef.current.clientWidth });
            }
        };

        window.addEventListener('resize', handleResize);

        return () => {
            window.removeEventListener('resize', handleResize);
            if (chartInstance.current) {
                chartInstance.current.remove();
                chartInstance.current = null;
            }
        };
    }, [data, trades]);

    return (
        <div className="w-full bg-black/20 rounded-lg p-2 border border-white/5">
            <div ref={chartContainerRef} className="w-full relative" />
            <div className="text-center text-xs text-gray-500 mt-2">
                * Markers are snapped to the nearest visible candle (Downsampled View)
            </div>
        </div>
    );
};

export default VisualBacktestChart;
