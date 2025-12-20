import React, { useState, useEffect } from 'react';
import ManualTrade from '../components/ManualTrade';
import SymbolSelector from '../components/SymbolSelector';
import TradingInfoPanel from '../components/TradingInfoPanel';
import ApiLogPanel from '../components/ApiLogPanel';

const ManualTrading = () => {
    // Symbol State Management (Shared Logic with Dashboard via LocalStorage)
    const [currentSymbol, setCurrentSymbol] = useState(() =>
        localStorage.getItem('lastSymbol') || '005930'
    );

    const [savedSymbols, setSavedSymbols] = useState(() => {
        const saved = localStorage.getItem('savedSymbols');
        if (!saved) return [{ code: '005930', name: '삼성전자' }, { code: '000660', name: 'SK하이닉스' }];
        try {
            const parsed = JSON.parse(saved);
            return parsed.map(item => {
                if (typeof item === 'string') return { code: item, name: '' };
                return item;
            });
        } catch {
            return [{ code: '005930', name: '삼성전자' }, { code: '000660', name: 'SK하이닉스' }];
        }
    });

    useEffect(() => {
        localStorage.setItem('lastSymbol', currentSymbol);
        localStorage.setItem('savedSymbols', JSON.stringify(savedSymbols));
    }, [currentSymbol, savedSymbols]);

    return (
        <div className="space-y-6">
            <SymbolSelector
                currentSymbol={currentSymbol}
                setCurrentSymbol={setCurrentSymbol}
                savedSymbols={savedSymbols}
                setSavedSymbols={setSavedSymbols}
            />

            <TradingInfoPanel
                currentSymbol={currentSymbol}
                setSavedSymbols={setSavedSymbols}
            />

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div className="lg:col-span-2">
                    <div className="bg-white/5 border border-white/10 rounded-xl p-6 backdrop-blur-md">
                        <h2 className="text-xl font-bold text-blue-300 mb-2">Manual Trading Execution</h2>
                        <p className="text-gray-400 mb-6">
                            Execute buy and sell orders manually using Limit or Market prices.
                        </p>
                        <div className="max-w-xl">
                            <ManualTrade defaultSymbol={currentSymbol} />
                        </div>
                    </div>
                </div>
                <div>
                    <ApiLogPanel />
                </div>
            </div>
        </div>
    );
};

export default ManualTrading;
