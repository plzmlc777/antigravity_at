import React, { useMemo } from 'react';

const BotFlowChart = ({ bot }) => {
    // Animation State
    const [activeStep, setActiveStep] = React.useState(3); // Default to end state

    // Parse the latest log to get state
    const { price, rsi, signal, isOrderError, lastUpdate } = useMemo(() => {
        if (!bot || !bot.logs || bot.logs.length === 0) return {};

        // Find the latest log that contains analysis data
        const analysisLog = bot.logs.find(l => l.message.includes('Signal:'));

        let parsed = { lastUpdate: bot.logs[0].timestamp };

        if (analysisLog) {
            // Flexible regex for both formats (comma or pipe separated)
            // Matches: "Price: 70123... RSI: 45.2... Signal: BUY..."
            const match = analysisLog.message.match(/Price:\s*([\d,.]+).*?RSI:\s*([\d.]+).*?Signal:\s*(\w+)/);
            if (match) {
                parsed.price = parseFloat(match[1].replace(/,/g, ''));
                parsed.rsi = parseFloat(match[2]);
                parsed.signal = match[3].toUpperCase();
            } else {
                console.warn("BotFlowChart Regex Parse Failed:", analysisLog.message);
                // Fallback debug - show error in UI via parsed.signal
                parsed.signal = "PARSE_ERR";
            }
        }
        if (bot.logs[0].is_error) parsed.isOrderError = true;
        return parsed;
    }, [bot]);

    // Trigger Animation on Update
    React.useEffect(() => {
        if (!lastUpdate) return;

        // Sequence: Data(0) -> RSI(1) -> Decision(2) -> Action(3)
        setActiveStep(0);

        const t1 = setTimeout(() => setActiveStep(1), 500);
        const t2 = setTimeout(() => setActiveStep(2), 1000);
        const t3 = setTimeout(() => setActiveStep(3), 1500);

        return () => {
            clearTimeout(t1);
            clearTimeout(t2);
            clearTimeout(t3);
        };
    }, [lastUpdate]);

    if (!bot) return null;

    // Countdown State
    const [countdown, setCountdown] = React.useState(bot?.interval || 0);

    // Reset countdown when lastUpdate changes
    React.useEffect(() => {
        if (bot?.interval) {
            setCountdown(bot.interval);
        }
    }, [lastUpdate, bot?.interval]);

    // Decrement timer
    React.useEffect(() => {
        if (countdown <= 0) return;
        const timer = setInterval(() => {
            setCountdown(prev => Math.max(0, prev - 1));
        }, 1000);
        return () => clearInterval(timer);
    }, [countdown]);

    // Helper for Node Styling
    const Node = ({ title, value, subtext, active, color, isCurrent }) => {
        const colorStyles = {
            indigo: {
                active: "bg-indigo-500/10 border-indigo-500 shadow-[0_0_15px_rgba(99,102,241,0.2)] text-indigo-300",
                line: "bg-indigo-500 shadow-[0_0_10px_rgba(99,102,241,0.5)]"
            },
            green: {
                active: "bg-green-500/10 border-green-500 shadow-[0_0_15px_rgba(34,197,94,0.2)] text-green-300",
                line: "bg-green-500 shadow-[0_0_10px_rgba(34,197,94,0.5)]"
            },
            blue: {
                active: "bg-blue-500/10 border-blue-500 shadow-[0_0_15px_rgba(59,130,246,0.2)] text-blue-300",
                line: "bg-blue-500 shadow-[0_0_10px_rgba(59,130,246,0.5)]"
            },
            red: {
                active: "bg-red-500/10 border-red-500 shadow-[0_0_15px_rgba(239,68,68,0.2)] text-red-300",
                line: "bg-red-500 shadow-[0_0_10px_rgba(239,68,68,0.5)]"
            },
            gray: {
                active: "bg-gray-500/10 border-gray-500 shadow-[0_0_15px_rgba(107,114,128,0.2)] text-gray-300",
                line: "bg-gray-500 shadow-[0_0_10px_rgba(107,114,128,0.5)]"
            }
        };

        const style = colorStyles[color] || colorStyles['gray'];

        return (
            <div className={`relative flex flex-col items-center justify-center p-4 rounded-xl border-2 transition-all duration-500 w-32 md:w-40 h-28 ${active
                ? `${style.active}`
                : 'bg-white/5 border-white/10 opacity-50'
                } ${isCurrent ? 'ring-2 ring-yellow-400 ring-offset-2 ring-offset-black scale-110 z-10 shadow-[0_0_30px_rgba(250,204,21,0.4)]' : ''}`}>

                {isCurrent && (
                    <div className="absolute -top-3 left-1/2 transform -translate-x-1/2 bg-yellow-400 text-black text-[10px] font-bold px-2 py-0.5 rounded-full z-20 animate-bounce">
                        CURRENT
                    </div>
                )}

                <div className={`text-xs uppercase font-bold mb-1 ${active ? style.text : 'text-gray-500'}`}>{title}</div>
                <div className={`text-xl font-bold ${active ? 'text-white' : 'text-gray-400'}`}>{value || '-'}</div>
                {subtext && <div className="text-[10px] text-gray-500 mt-1">{subtext}</div>}

                {/* Connector Line (Right) */}
                <div className="hidden md:block absolute -right-6 top-1/2 w-6 h-0.5 bg-white/10">
                    {active && <div className={`h-full w-full ${style.line}`}></div>}
                </div>
                {/* Connector Arrow */}
                <div className="hidden md:block absolute -right-6 top-1/2 transform translate-x-1 -translate-y-[3px] border-t-[3px] border-r-[3px] border-white/10 w-2 h-2 rotate-45"></div>
            </div>
        );
    };

    const getLastNode = () => {
        const isCurrent = activeStep === 3;
        if (isOrderError) return <Node title="Result" value="Error" color="red" active={true} isCurrent={isCurrent} />;
        if (signal === 'BUY' || signal === 'SELL') return <Node title="Order" value="Placed" subtext="In Progress" color="green" active={true} isCurrent={isCurrent} />;

        // Show Countdown in the Wait Node
        return <Node title="Action" value="Wait" subtext="Next Cycle" color="gray" active={true} isCurrent={isCurrent} />;
    };

    const getRsiColor = (val) => {
        if (!val) return 'gray';
        if (val <= 30) return 'green'; // Buy Zone
        if (val >= 70) return 'blue';  // Sell Zone
        return 'gray';
    };

    return (
        <div className="bg-black/40 border border-white/10 rounded-xl p-6 mb-6 relative overflow-hidden">
            {/* Background Progress Bar for Interval */}
            <div className="absolute bottom-0 left-0 h-1 bg-gradient-to-r from-blue-500 to-indigo-500 transition-all duration-1000 ease-linear"
                style={{ width: `${((bot.interval - countdown) / bot.interval) * 100}%` }}>
            </div>

            <div className="flex justify-between items-center mb-6">
                <h3 className="text-lg font-bold text-white flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse"></span>
                    Live Execution Flow
                </h3>
                <div className="text-right">
                    <span className="text-xs text-gray-500 font-mono block">Last Update: {lastUpdate}</span>
                    <div className="text-sm font-bold text-blue-300">
                        Next Check: <span className="text-white font-mono text-lg">{countdown}s</span>
                    </div>
                </div>
            </div>

            <div className="flex flex-col md:flex-row items-center justify-center gap-8 md:gap-6 overflow-x-auto p-4 pt-6">
                {/* Node 1: Market Data */}
                <Node
                    title="Market Data"
                    value={price?.toLocaleString()}
                    subtext="Current Price"
                    color="indigo"
                    active={true}
                    isCurrent={activeStep === 0}
                />

                {/* Node 2: RSI Calculation */}
                <Node
                    title="RSI Analysis"
                    value={rsi?.toFixed(1)}
                    subtext="Target: <30 or >70"
                    color={getRsiColor(rsi)}
                    active={true}
                    isCurrent={activeStep === 1}
                />

                {/* Node 3: Decision */}
                <Node
                    title="Decision"
                    value={signal}
                    subtext={signal === 'HOLD' ? 'Pass' : 'Triggered'}
                    color={signal === 'BUY' ? 'red' : signal === 'SELL' ? 'blue' : 'gray'}
                    active={true}
                    isCurrent={activeStep === 2}
                />

                {/* Node 4: Action/Result */}
                <div className="relative">
                    {getLastNode()}
                    {/* Remove connector from last node */}
                    <div className="hidden md:block absolute -right-6 top-1/2 w-6 h-0.5 bg-transparent"></div>
                </div>
            </div>

            {/* Legend / Status Text */}
            <div className="mt-4 text-center text-xs text-gray-500 min-h-[20px]">
                {activeStep === 3 && signal === 'BUY' && <span className="text-red-400 font-bold animate-pulse">Buying Signal Detected! Placing Order...</span>}
                {activeStep === 3 && signal === 'SELL' && <span className="text-blue-400 font-bold animate-pulse">Selling Signal Detected! Placing Order...</span>}
                {activeStep === 3 && signal === 'HOLD' && <span>Condition not met. Waiting for next interval...</span>}
                {activeStep < 3 && <span className="text-yellow-400/70">Analyzing market data...</span>}
            </div>
        </div>
    );
};

export default BotFlowChart;
