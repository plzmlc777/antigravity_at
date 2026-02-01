import React, { useState } from 'react';
import axios from 'axios';

const SymbolSelector = ({ currentSymbol, setCurrentSymbol, savedSymbols, setSavedSymbols, hideSymbolList = false }) => {
    const [inputValue, setInputValue] = useState('');
    const [draggedIndex, setDraggedIndex] = useState(null);
    const [dragOverIndex, setDragOverIndex] = useState(null);

    const handleAddSymbol = async (e) => {
        e.preventDefault();
        if (!inputValue) return;

        const code = inputValue.trim();
        setInputValue('');

        // Fetch symbol name from API
        let symbolName = '';
        try {
            const res = await axios.get(`/api/v1/market-data/info/${code}`);
            if (res.data.name && res.data.name !== code) {
                symbolName = res.data.name;
            }
        } catch (err) {
            console.error("Failed to fetch symbol name", err);
        }

        // Check duplication and add/update
        if (!savedSymbols.some(s => s.code === code)) {
            setSavedSymbols(prev => [...prev, { code, name: symbolName }]);
        } else if (symbolName) {
            // Update existing symbol's name if we got a valid name
            setSavedSymbols(prev => prev.map(s =>
                s.code === code ? { ...s, name: symbolName } : s
            ));
        }
        setCurrentSymbol(code);
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

    // Drag & Drop handlers
    const handleDragStart = (e, index) => {
        setDraggedIndex(index);
        e.dataTransfer.effectAllowed = 'move';
    };

    const handleDragOver = (e, index) => {
        e.preventDefault();
        if (draggedIndex === null || draggedIndex === index) return;
        setDragOverIndex(index);
    };

    const handleDragLeave = () => {
        setDragOverIndex(null);
    };

    const handleDrop = (e, dropIndex) => {
        e.preventDefault();
        if (draggedIndex === null || draggedIndex === dropIndex) {
            setDraggedIndex(null);
            setDragOverIndex(null);
            return;
        }

        // Reorder array
        const newSymbols = [...savedSymbols];
        const [draggedItem] = newSymbols.splice(draggedIndex, 1);
        newSymbols.splice(dropIndex, 0, draggedItem);
        setSavedSymbols(newSymbols);

        setDraggedIndex(null);
        setDragOverIndex(null);
    };

    const handleDragEnd = () => {
        setDraggedIndex(null);
        setDragOverIndex(null);
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

            {!hideSymbolList && (
                <>
                    <div className="h-6 w-px bg-white/10 mx-2 hidden md:block"></div>

                    <div className="flex flex-wrap gap-2">
                        {savedSymbols.map((sym, index) => (
                            <div
                                key={sym.code}
                                draggable
                                onDragStart={(e) => handleDragStart(e, index)}
                                onDragOver={(e) => handleDragOver(e, index)}
                                onDragLeave={handleDragLeave}
                                onDrop={(e) => handleDrop(e, index)}
                                onDragEnd={handleDragEnd}
                                onClick={() => setCurrentSymbol(sym.code)}
                                className={`group flex items-center gap-2 px-3 py-1 rounded cursor-grab border transition-all ${
                                    currentSymbol === sym.code
                                        ? 'bg-blue-900/30 border-blue-500 text-blue-300'
                                        : 'bg-black/20 border-white/10 text-gray-400 hover:bg-white/5'
                                } ${draggedIndex === index ? 'opacity-50' : ''} ${
                                    dragOverIndex === index ? 'border-yellow-500 border-dashed' : ''
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
                </>
            )}
        </div>
    );
};

export default SymbolSelector;
