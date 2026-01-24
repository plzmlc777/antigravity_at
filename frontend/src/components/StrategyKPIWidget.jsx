import React, { useState, useEffect } from 'react';
import { Clock, TrendingUp, TrendingDown, Activity, Target, Timer } from 'lucide-react';

/**
 * StrategyKPIWidget - Displays strategy-specific live metrics
 * 
 * Props:
 *   strategyId - Strategy identifier (e.g., 'time_momentum', 'rsi_strategy')
 *   strategyConfig - Full strategy configuration object
 *   liveData - Real-time data from WebSocket
 */
const StrategyKPIWidget = ({ strategyId, strategyConfig, liveData }) => {
    const [currentTime, setCurrentTime] = useState(new Date());

    // Update current time every second for countdown
    useEffect(() => {
        const timer = setInterval(() => setCurrentTime(new Date()), 1000);
        return () => clearInterval(timer);
    }, []);

    // Parse time string (HH:MM) to today's Date object
    const parseTimeToToday = (timeStr) => {
        if (!timeStr) return null;
        const [hours, minutes] = timeStr.split(':').map(Number);
        const date = new Date();
        date.setHours(hours, minutes, 0, 0);
        return date;
    };

    // Format countdown (minutes and seconds)
    const formatCountdown = (milliseconds) => {
        if (milliseconds <= 0) return '진입 가능';
        const totalSeconds = Math.floor(milliseconds / 1000);
        const hours = Math.floor(totalSeconds / 3600);
        const minutes = Math.floor((totalSeconds % 3600) / 60);
        const seconds = totalSeconds % 60;
        if (hours > 0) {
            return `${hours}시간 ${minutes}분`;
        }
        return `${minutes}분 ${seconds}초`;
    };

    // Time Momentum Strategy Widget
    if (strategyId === 'time_momentum') {
        const startTime = strategyConfig?.start_time || '09:00';
        const stopTime = strategyConfig?.stop_time || '15:00';
        const direction = strategyConfig?.direction || 'fall';
        const targetPercent = strategyConfig?.target_percent || 0.2;
        const delayMinutes = strategyConfig?.delay_minutes || 60;

        const startDate = parseTimeToToday(startTime);
        const stopDate = parseTimeToToday(stopTime);
        const now = currentTime;

        // Calculate countdown to start
        let countdownMs = 0;
        let tradingStatus = 'waiting';

        if (startDate && stopDate) {
            if (now < startDate) {
                countdownMs = startDate - now;
                tradingStatus = 'waiting';
            } else if (now >= startDate && now <= stopDate) {
                tradingStatus = 'active';
            } else {
                tradingStatus = 'closed';
            }
        }

        // Progress bar percentage (time elapsed in trading window)
        let progressPercent = 0;
        if (startDate && stopDate && tradingStatus === 'active') {
            const totalWindow = stopDate - startDate;
            const elapsed = now - startDate;
            progressPercent = Math.min(100, Math.max(0, (elapsed / totalWindow) * 100));
        }

        return (
            <div className="bg-gradient-to-br from-indigo-900/30 to-purple-900/20 border border-indigo-500/30 rounded-xl p-4 mb-6">
                {/* Header */}
                <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-2">
                        <Timer size={18} className="text-indigo-400" />
                        <span className="text-sm font-bold text-white">Time Momentum Monitor</span>
                    </div>
                    <span className={`px-3 py-1 rounded-full text-xs font-bold ${tradingStatus === 'active'
                            ? 'bg-green-500/20 text-green-400 border border-green-500/30'
                            : tradingStatus === 'waiting'
                                ? 'bg-yellow-500/20 text-yellow-400 border border-yellow-500/30'
                                : 'bg-gray-500/20 text-gray-400 border border-gray-500/30'
                        }`}>
                        {tradingStatus === 'active' ? '🟢 거래 중' : tradingStatus === 'waiting' ? '⏳ 대기 중' : '🔴 마감'}
                    </span>
                </div>

                {/* Main Stats Grid */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
                    {/* Start Time */}
                    <div className="bg-black/30 rounded-lg p-3 text-center">
                        <div className="text-gray-400 text-[10px] uppercase tracking-wider mb-1">시작 시간</div>
                        <div className="text-lg font-mono text-white">{startTime}</div>
                    </div>

                    {/* Countdown / Status */}
                    <div className="bg-black/30 rounded-lg p-3 text-center">
                        <div className="text-gray-400 text-[10px] uppercase tracking-wider mb-1">
                            {tradingStatus === 'waiting' ? '카운트다운' : '종료 시간'}
                        </div>
                        <div className={`text-lg font-mono ${tradingStatus === 'waiting' ? 'text-yellow-400' : 'text-white'}`}>
                            {tradingStatus === 'waiting' ? formatCountdown(countdownMs) : stopTime}
                        </div>
                    </div>

                    {/* Direction */}
                    <div className="bg-black/30 rounded-lg p-3 text-center">
                        <div className="text-gray-400 text-[10px] uppercase tracking-wider mb-1">방향</div>
                        <div className={`text-lg font-bold flex items-center justify-center gap-1 ${direction === 'rise' ? 'text-red-400' : 'text-blue-400'
                            }`}>
                            {direction === 'rise' ? <TrendingUp size={18} /> : <TrendingDown size={18} />}
                            {direction === 'rise' ? '상승' : '하락'}
                        </div>
                    </div>

                    {/* Target */}
                    <div className="bg-black/30 rounded-lg p-3 text-center">
                        <div className="text-gray-400 text-[10px] uppercase tracking-wider mb-1">목표 %</div>
                        <div className="text-lg font-mono text-green-400">{targetPercent}%</div>
                    </div>
                </div>

                {/* Progress Bar (only shown when active) */}
                {tradingStatus === 'active' && (
                    <div className="bg-black/30 rounded-lg p-3">
                        <div className="flex justify-between text-[10px] text-gray-400 mb-2">
                            <span>{startTime}</span>
                            <span>Trading Window Progress</span>
                            <span>{stopTime}</span>
                        </div>
                        <div className="w-full bg-gray-700 rounded-full h-2">
                            <div
                                className="bg-gradient-to-r from-indigo-500 to-purple-500 h-2 rounded-full transition-all duration-1000"
                                style={{ width: `${progressPercent}%` }}
                            />
                        </div>
                    </div>
                )}
            </div>
        );
    }

    // RSI Strategy Widget
    if (strategyId === 'rsi_strategy') {
        const rsiPeriod = strategyConfig?.rsi_period || 14;
        const oversold = strategyConfig?.oversold || 30;
        const overbought = strategyConfig?.overbought || 70;
        const currentRSI = liveData?.rsi || null;

        return (
            <div className="bg-gradient-to-br from-cyan-900/30 to-blue-900/20 border border-cyan-500/30 rounded-xl p-4 mb-6">
                <div className="flex items-center gap-2 mb-4">
                    <Activity size={18} className="text-cyan-400" />
                    <span className="text-sm font-bold text-white">RSI Monitor</span>
                </div>

                <div className="grid grid-cols-3 gap-3">
                    <div className="bg-black/30 rounded-lg p-3 text-center">
                        <div className="text-gray-400 text-[10px] uppercase tracking-wider mb-1">RSI Period</div>
                        <div className="text-lg font-mono text-white">{rsiPeriod}</div>
                    </div>
                    <div className="bg-black/30 rounded-lg p-3 text-center">
                        <div className="text-gray-400 text-[10px] uppercase tracking-wider mb-1">과매도</div>
                        <div className="text-lg font-mono text-green-400">&lt; {oversold}</div>
                    </div>
                    <div className="bg-black/30 rounded-lg p-3 text-center">
                        <div className="text-gray-400 text-[10px] uppercase tracking-wider mb-1">과매수</div>
                        <div className="text-lg font-mono text-red-400">&gt; {overbought}</div>
                    </div>
                </div>

                {/* RSI Level Indicator */}
                <div className="mt-4 bg-black/30 rounded-lg p-3">
                    <div className="flex justify-between text-[10px] text-gray-400 mb-2">
                        <span className="text-green-400">{oversold}</span>
                        <span>Current RSI</span>
                        <span className="text-red-400">{overbought}</span>
                    </div>
                    <div className="relative w-full bg-gradient-to-r from-green-600 via-gray-600 to-red-600 rounded-full h-3">
                        {currentRSI !== null && (
                            <div
                                className="absolute top-0 w-3 h-3 bg-white rounded-full border-2 border-black shadow-lg transform -translate-x-1/2"
                                style={{ left: `${Math.min(100, Math.max(0, currentRSI))}%` }}
                            />
                        )}
                    </div>
                    {currentRSI !== null && (
                        <div className="text-center mt-2 text-xl font-mono text-white">{currentRSI.toFixed(1)}</div>
                    )}
                </div>
            </div>
        );
    }

    // Generic Fallback for other strategies
    return (
        <div className="bg-gradient-to-br from-gray-800/50 to-gray-900/30 border border-gray-600/30 rounded-xl p-4 mb-6">
            <div className="flex items-center gap-2 mb-3">
                <Target size={18} className="text-gray-400" />
                <span className="text-sm font-bold text-white">Strategy Monitor</span>
            </div>
            <div className="text-gray-400 text-sm">
                {strategyId ? `${strategyId} 전략 실행 중` : '전략 정보 없음'}
            </div>
        </div>
    );
};

export default StrategyKPIWidget;
