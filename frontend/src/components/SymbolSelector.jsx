import React, { useState } from 'react';

const SymbolSelector = ({ currentSymbol, setCurrentSymbol, savedSymbols, setSavedSymbols }) => {
    const [inputValue, setInputValue] = useState('');

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

    return (
        <div className="flex flex-wrap items-center gap-4">
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
    );
};

export default SymbolSelector;
