import React, { useState, useEffect } from 'react';
import ManualTrade from '../components/ManualTrade';
import SymbolSelector from '../components/SymbolSelector';
import TradingInfoPanel from '../components/TradingInfoPanel';
import ApiLogPanel from '../components/ApiLogPanel';
import Card from '../components/common/Card';

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
            <Card title="Market Selection">
                <SymbolSelector
                    currentSymbol={currentSymbol}
                    setCurrentSymbol={setCurrentSymbol}
                    savedSymbols={savedSymbols}
                    setSavedSymbols={setSavedSymbols}
                />
            </Card>

            <Card title="Market Overview">
                <TradingInfoPanel
                    currentSymbol={currentSymbol}
                    setSavedSymbols={setSavedSymbols}
                />
            </Card>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div className="lg:col-span-2">
                    <Card title="Manual Trading Execution">
                        <p className="text-gray-400 mb-6 text-sm">
                            Execute buy and sell orders manually using Limit or Market prices.
                        </p>
                        <div className="max-w-xl">
                            <ManualTrade defaultSymbol={currentSymbol} />
                        </div>
                    </Card>
                </div>
                <div>
                    <Card title="System Logs">
                        <ApiLogPanel />
                    </Card>
                </div>
            </div>
        </div>
    );
};

export default ManualTrading;
