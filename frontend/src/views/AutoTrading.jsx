import React, { useState, useEffect } from 'react';
import axios from 'axios';
import SymbolSelector from '../components/SymbolSelector';
import BotFlowChart from '../components/BotFlowChart';
import Card from '../components/common/Card';

const AutoTrading = () => {
    // --- State ---
    const [currentSymbol, setCurrentSymbol] = useState(() => localStorage.getItem('lastSymbol') || '005930');
    const [savedSymbols, setSavedSymbols] = useState(() => {
        const saved = localStorage.getItem('savedSymbols');
        if (!saved) return [{ code: '005930', name: '삼성전자' }, { code: '000660', name: 'SK하이닉스' }];
        try {
            const parsed = JSON.parse(saved);
            return parsed.map(item => typeof item === 'string' ? { code: item, name: '' } : item);
        } catch {
            return [{ code: '005930', name: '삼성전자' }, { code: '000660', name: 'SK하이닉스' }];
        }
    });

    const [strategy, setStrategy] = useState('rsi');
    const [intervalSec, setIntervalSec] = useState(5); // Testing default 5s
    const [amount, setAmount] = useState(100000);

    // Bots
    const [bots, setBots] = useState([]);
    const [selectedBotId, setSelectedBotId] = useState(null);

    // --- Effects ---
    useEffect(() => {
        localStorage.setItem('lastSymbol', currentSymbol);
        localStorage.setItem('savedSymbols', JSON.stringify(savedSymbols));
    }, [currentSymbol, savedSymbols]);

    const fetchBots = async () => {
        try {
            const res = await axios.get('/api/v1/auto/status');
            setBots(res.data);

            // Auto select first bot if none selected
            if (!selectedBotId && res.data.length > 0) {
                setSelectedBotId(res.data[0].id);
            }
        } catch (e) {
            console.error("Failed to fetch bots", e);
        }
    };

    // Poll bot status every 1 second
    useEffect(() => {
        fetchBots();
        const timer = setInterval(fetchBots, 1000);
        return () => clearInterval(timer);
    }, []);

    const handleStartBot = async (mode = 'real') => {
        try {
            const isSimulation = mode !== 'real';
            let symbolPrefix = "";
            if (mode === 'virtual') symbolPrefix = "[V-SIM] ";
            if (mode === 'random') symbolPrefix = "[R-SIM] ";

            const payload = {
                symbol: isSimulation ? `${symbolPrefix}${currentSymbol}` : currentSymbol,
                strategy: strategy,
                interval: parseInt(intervalSec),
                amount: parseFloat(amount),
                sim_mode: isSimulation ? mode : null, // 'virtual' or 'random'
                strategy_config: {
                    period: 14,
                    buy_threshold: 30,
                    sell_threshold: 70
                }
            };
            await axios.post('/api/v1/auto/start', payload);
            fetchBots();
        } catch (e) {
            alert("Failed to start bot: " + (e.response?.data?.detail || e.message));
        }
    };

    const handleStopBot = async (botId) => {
        try {
            await axios.post(`/api/v1/auto/stop/${botId}`);
            fetchBots();
        } catch (e) {
            alert("Error stopping bot");
        }
    };

    const handleRemoveBot = async (botId) => {
        try {
            await axios.delete(`/api/v1/auto/${botId}`);
            fetchBots();
            if (selectedBotId === botId) setSelectedBotId(null);
        } catch (e) {
            alert("Error removing bot");
        }
    };

    const handleResumeBot = async (oldBot) => {
        try {
            // Start new bot with same config
            const payload = {
                symbol: oldBot.symbol,
                strategy: 'rsi',
                interval: oldBot.interval, // Preserves the user-set interval
                amount: oldBot.amount,
                strategy_config: {
                    period: 14,
                    buy_threshold: 30,
                    sell_threshold: 70
                }
            };
            await axios.post('/api/v1/auto/start', payload);

            // Remove old stopped bot to avoid duplicates
            await axios.delete(`/api/v1/auto/${oldBot.id}`);

            fetchBots();
        } catch (e) {
            alert("Failed to resume bot: " + e.message);
        }
    };



    const activeBot = bots.length > 0 ? bots[0] : null;

    return (
        <div className="space-y-6">
            {!activeBot ? (
                /* 1. Configuration Section (Only shown when no bot is active) */
                <div className="max-w-2xl mx-auto space-y-6">
                    <Card title="Strategy Target">
                        <SymbolSelector
                            currentSymbol={currentSymbol}
                            setCurrentSymbol={setCurrentSymbol}
                            savedSymbols={savedSymbols}
                            setSavedSymbols={setSavedSymbols}
                        />
                    </Card>

                    <Card title="Auto Trading Setup" className="shadow-2xl">
                        <div className="space-y-6">
                            <div>
                                <label className="block text-sm text-gray-400 mb-2">Strategy</label>
                                <select
                                    className="w-full bg-black/40 border border-white/10 rounded-lg p-3 text-white focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none"
                                    value={strategy}
                                    onChange={e => setStrategy(e.target.value)}
                                >
                                    <option value="rsi">RSI Strategy (Buy &lt; 30, Sell &gt; 70)</option>
                                </select>
                            </div>

                            <div className="grid grid-cols-2 gap-6">
                                <div>
                                    <label className="block text-sm text-gray-400 mb-2">Interval (Sec)</label>
                                    <input
                                        type="number"
                                        className="w-full bg-black/40 border border-white/10 rounded-lg p-3 text-white text-center font-mono focus:border-blue-500 outline-none"
                                        value={intervalSec}
                                        onChange={e => setIntervalSec(e.target.value)}
                                        min="1"
                                    />
                                    <span className="text-xs text-center block mt-1 text-gray-500">Test: 1-30s / Real: 60s+</span>
                                </div>
                                <div>
                                    <label className="block text-sm text-gray-400 mb-2">Amount (KRW)</label>
                                    <input
                                        type="number"
                                        className="w-full bg-black/40 border border-white/10 rounded-lg p-3 text-white text-center font-mono focus:border-blue-500 outline-none"
                                        value={amount}
                                        onChange={e => setAmount(e.target.value)}
                                    />
                                </div>
                            </div>

                            <div className="pt-4 space-y-3">
                                <button
                                    onClick={() => handleStartBot('real')}
                                    className="w-full bg-gradient-to-r from-green-600 to-emerald-600 hover:from-green-500 hover:to-emerald-500 text-white font-bold py-4 rounded-lg transition-all shadow-lg hover:shadow-green-500/30 text-lg"
                                >
                                    Start Real Trading
                                </button>
                                <div className="grid grid-cols-2 gap-3">
                                    <button
                                        onClick={() => handleStartBot('virtual')}
                                        className="bg-blue-500/20 hover:bg-blue-500/30 text-blue-300 font-bold py-3 rounded-lg transition-all border border-blue-500/30"
                                    >
                                        Sim (Real Data)
                                    </button>
                                    <button
                                        onClick={() => handleStartBot('random')}
                                        className="bg-purple-500/20 hover:bg-purple-500/30 text-purple-300 font-bold py-3 rounded-lg transition-all border border-purple-500/30"
                                    >
                                        Sim (Random)
                                    </button>
                                </div>
                            </div>
                        </div>
                    </Card>
                </div>
            ) : (
                /* 2. Active Bot View (Single Mode) */
                <div className="space-y-6 animate-fade-in">
                    {/* Header / Controls */}
                    <Card>
                        <div className="flex flex-col md:flex-row justify-between items-center gap-4">
                            <div>
                                <h2 className="text-2xl font-bold text-white flex items-center gap-3">
                                    {activeBot.symbol}
                                    <span className={`text-xs px-2 py-1 rounded font-bold ${activeBot.is_running ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>
                                        {activeBot.is_running ? 'RUNNING' : 'PAUSED'}
                                    </span>
                                    {activeBot.sim_mode && (
                                        <span className="text-xs px-2 py-1 rounded font-bold bg-purple-500/20 text-purple-300">
                                            {activeBot.sim_mode === 'random' ? 'RANDOM SIM' : 'VIRTUAL SIM'}
                                        </span>
                                    )}
                                </h2>
                                <div className="text-gray-400 text-sm mt-1">
                                    Strategy: <span className="text-white">{activeBot.strategy}</span> | Interval: <span className="text-white">{activeBot.interval}s</span> | Amount: <span className="text-white">{Number(activeBot.amount).toLocaleString()} KRW</span>
                                </div>
                            </div>

                            <div className="flex gap-3">
                                {activeBot.is_running ? (
                                    <button
                                        onClick={() => handleStopBot(activeBot.id)}
                                        className="px-6 py-2 bg-yellow-500/20 hover:bg-yellow-500/30 text-yellow-300 font-bold rounded-lg border border-yellow-500/30 transition-all"
                                    >
                                        Pause
                                    </button>
                                ) : (
                                    <button
                                        onClick={() => handleResumeBot(activeBot)}
                                        className="px-6 py-2 bg-green-500/20 hover:bg-green-500/30 text-green-300 font-bold rounded-lg border border-green-500/30 transition-all"
                                    >
                                        Resume
                                    </button>
                                )}

                                <button
                                    onClick={() => handleRemoveBot(activeBot.id)}
                                    className="px-6 py-2 bg-red-500/20 hover:bg-red-500/30 text-red-300 font-bold rounded-lg border border-red-500/30 transition-all"
                                >
                                    Stop & Exit
                                </button>
                            </div>
                        </div>
                    </Card>

                    {/* Flow Chart */}
                    <Card title="Strategy Flow">
                        <BotFlowChart bot={activeBot} />
                    </Card>

                    {/* Logs */}
                    <Card title="Execution Logs" headerAction={<span className="text-xs text-gray-500">Auto-refreshing</span>}>
                        <div className="bg-black rounded p-4 h-[300px] overflow-y-auto font-mono text-sm space-y-1 scrollbar-thin scrollbar-thumb-white/20">
                            {activeBot.logs.map((log, idx) => (
                                <div key={idx} className={`border-b border-white/5 pb-1 ${log.is_error ? 'text-red-400'
                                    : log.message.includes('BUY EXECUTED') ? 'text-red-400 font-bold bg-red-500/5'
                                        : log.message.includes('SELL EXECUTED') ? 'text-blue-400 font-bold bg-blue-500/5'
                                            : log.message.includes('Signal') ? 'text-yellow-300'
                                                : 'text-gray-400'}`}>
                                    <span className="text-gray-600 mr-3">[{log.timestamp}]</span>
                                    {log.message}
                                </div>
                            ))}
                        </div>
                    </Card>
                </div>
            )}
        </div>
    );
};

export default AutoTrading;
