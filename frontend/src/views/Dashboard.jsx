import React, { useState, useEffect } from 'react';
import Diagram from '../components/Diagram';
import SymbolSelector from '../components/SymbolSelector';
import TradingInfoPanel from '../components/TradingInfoPanel';
import ApiLogPanel from '../components/ApiLogPanel';
import Card from '../components/common/Card';

const Dashboard = () => {
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

    useEffect(() => {
        localStorage.setItem('lastSymbol', currentSymbol);
        localStorage.setItem('savedSymbols', JSON.stringify(savedSymbols));
    }, [currentSymbol, savedSymbols]);

    return (
        <div className="space-y-6">
            {/* Symbol Selection Area */}
            <Card title="Watchlist & Search">
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
                <div className="lg:col-span-2 space-y-6">
                    <Card title="Process Visualization">
                        <Diagram />
                    </Card>
                </div>

                <div className="space-y-6">
                    <Card title="System Logs">
                        <ApiLogPanel />
                    </Card>
                </div>
            </div>
        </div>
    );


};

export default Dashboard;
