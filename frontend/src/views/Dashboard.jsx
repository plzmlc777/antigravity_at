import React, { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import StatusCard from '../components/StatusCard';
import Diagram from '../components/Diagram';
import { getStatus, getPrice, getBalance } from '../api/client';
import { apiLogger } from '../utils/eventBus';

const Dashboard = () => {
    const [logs, setLogs] = useState([]);

    // Symbol State Management
    const [currentSymbol, setCurrentSymbol] = useState(() =>
        localStorage.getItem('lastSymbol') || '005930'
    );

    const [savedSymbols, setSavedSymbols] = useState(() => {
        const saved = localStorage.getItem('savedSymbols');
        // Default init
        if (!saved) return [{ code: '005930', name: '삼성전자' }, { code: '000660', name: 'SK하이닉스' }];

        try {
            const parsed = JSON.parse(saved);
            // Migration logic: convert strings to objects
            return parsed.map(item => {
                if (typeof item === 'string') return { code: item, name: '' };
                return item;
            });
        } catch {
            return [{ code: '005930', name: '삼성전자' }, { code: '000660', name: 'SK하이닉스' }];
        }
    });

    const [inputValue, setInputValue] = useState('');

    useEffect(() => {
        localStorage.setItem('lastSymbol', currentSymbol);
        localStorage.setItem('savedSymbols', JSON.stringify(savedSymbols));
    }, [currentSymbol, savedSymbols]);

    const handleAddSymbol = (e) => {
        e.preventDefault();
        // Check duplication
        if (inputValue && !savedSymbols.some(s => s.code === inputValue)) {
            setSavedSymbols(prev => [...prev, { code: inputValue, name: '' }]);
            setCurrentSymbol(inputValue);
            setInputValue('');
        } else if (inputValue) {
            setCurrentSymbol(inputValue);
            setInputValue('');
        }
    };

    const removeSymbol = (e, code) => {
        e.stopPropagation();
        setSavedSymbols(prev => prev.filter(s => s.code !== code));

        // If current was removed, switch to another
        if (currentSymbol === code) {
            const next = savedSymbols.find(s => s.code !== code);
            setCurrentSymbol(next ? next.code : '005930');
        }
    };

    const { data: status } = useQuery({
        queryKey: ['status'],
        queryFn: getStatus,
        refetchInterval: 5000
    });

    const { data: price } = useQuery({
        queryKey: ['price', currentSymbol],
        queryFn: () => getPrice(currentSymbol),
        refetchInterval: 2000
    });

    const { data: balance } = useQuery({
        queryKey: ['balance'],
        queryFn: getBalance,
        refetchInterval: 5000
    });

    // Auto-update name in saved list if fetched from API
    useEffect(() => {
        if (price?.symbol && price?.name) {
            setSavedSymbols(prev => prev.map(item => {
                // Update name if missing
                if (item.code === price.symbol && !item.name) {
                    return { ...item, name: price.name };
                }
                return item;
            }));
        }
    }, [price]);

    // Subscribe to logs
    useEffect(() => {
        const unsubscribe = apiLogger.subscribe((log) => {
            setLogs((prev) => {
                const newLogs = [log, ...prev].slice(0, 50);
                return newLogs;
            });
        });
        return () => unsubscribe();
    }, []);

    return (
        <div className="space-y-6">
            {/* Symbol Selection Area */}
            <div className="bg-white/5 border border-white/10 rounded-xl p-4 flex flex-wrap items-center gap-4">
                <form onSubmit={handleAddSymbol} className="flex gap-2">
                    <input
                        type="text"
                        value={inputValue}
                        onChange={(e) => setInputValue(e.target.value)}
                        placeholder="Enter Code (e.g. 005930)"
                        className="bg-black/40 border border-white/20 rounded px-3 py-1.5 text-sm focus:outline-none focus:border-blue-500 w-48 text-white"
                    />
                    <button type="submit" className="bg-blue-600 hover:bg-blue-500 px-4 py-1.5 rounded text-sm font-medium transition-colors">
                        Load
                    </button>
                </form>

                <div className="h-6 w-px bg-white/10 mx-2 hidden md:block"></div>

                <div className="flex flex-wrap gap-2">
                    {savedSymbols.map(sym => (
                        <div
                            key={sym.code}
                            onClick={() => setCurrentSymbol(sym.code)}
                            className={`group flex items-center gap-2 px-3 py-1 rounded cursor-pointer border transition-all ${currentSymbol === sym.code
                                    ? 'bg-blue-900/30 border-blue-500 text-blue-300'
                                    : 'bg-black/20 border-white/10 text-gray-400 hover:bg-white/5'
                                }`}
                        >
                            <span className="text-sm font-mono">
                                {sym.code} <span className="text-xs opacity-70">{sym.name && `(${sym.name})`}</span>
                            </span>
                            <button
                                onClick={(e) => removeSymbol(e, sym.code)}
                                className="w-4 h-4 rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 hover:bg-red-500/20 hover:text-red-400 transition-all text-xs"
                            >
                                ×
                            </button>
                        </div>
                    ))}
                </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <StatusCard
                    title="System Status"
                    value={status?.status === 'online' ? 'ONLINE' : 'OFFLINE'}
                    subtext={`Exchange: ${status?.exchange || '-'}`}
                    type={status?.status === 'online' ? 'success' : 'danger'}
                />
                <StatusCard
                    title={`Price (${price?.name || currentSymbol})`}
                    value={price?.price ? `${price.price.toLocaleString()} KRW` : '-'}
                    subtext={price?.name ? `${currentSymbol} | Real-time` : "Real-time Price"}
                    type="neutral"
                />
                <StatusCard
                    title="Cash Balance"
                    value={balance?.cash?.KRW ? `${balance.cash.KRW.toLocaleString()} KRW` : '0 KRW'}
                    subtext="Available for Trade"
                    type="warning"
                />
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div className="lg:col-span-2">
                    <h2 className="text-lg font-semibold mb-4 text-white/80">Process Visualization</h2>
                    <Diagram />
                </div>
                <div>
                    <h2 className="text-lg font-semibold mb-4 text-white/80">
                        Real-time API Log
                        <span className="ml-2 text-xs font-normal text-gray-400">(Latest First)</span>
                    </h2>
                    <div className="bg-black/20 border border-white/10 rounded-xl p-4 h-[300px] overflow-y-auto font-mono text-xs space-y-2 scrollbar-thin scrollbar-thumb-white/10">
                        {logs.length === 0 && <div className="text-gray-500 text-center py-4">Waiting for requests...</div>}

                        {logs.map((log) => (
                            <div key={log.id + log.timestamp} className={`flex items-start gap-2 pb-2 border-b border-white/5 ${log.isError ? 'text-red-400' : 'text-gray-300'}`}>
                                <span className="text-gray-600 min-w-[60px]">{log.timestamp}</span>
                                <div className="flex-1">
                                    <div className="flex items-center gap-2">
                                        <span className={`font-bold px-1.5 rounded text-[10px] ${log.type === 'req' ? 'bg-blue-500/20 text-blue-300' : log.isError ? 'bg-red-500/20 text-red-300' : 'bg-green-500/20 text-green-300'}`}>
                                            {log.method}
                                        </span>
                                        <span className="truncate max-w-[150px]">{log.url}</span>
                                    </div>
                                    {log.type !== 'req' && (
                                        <div className="mt-1 flex justify-between opacity-70">
                                            <span>{log.status}</span>
                                            <span>{log.duration}</span>
                                        </div>
                                    )}
                                    {log.message && <div className="mt-1 text-red-400">{log.message}</div>}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </div>
        </div>
    );
};

export default Dashboard;
