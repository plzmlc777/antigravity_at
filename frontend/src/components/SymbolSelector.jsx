import React, { useState } from 'react';
import axios from 'axios';
import SymbolChip from './SymbolChip';

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

    const removeSymbol = (code) => {
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
        if (draggedIndex === null || draggedIndex === index) return;
        setDragOverIndex(index);
    };

    const handleDragLeave = () => {
        setDragOverIndex(null);
    };

    const handleDrop = (e, dropIndex) => {
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
                            <SymbolChip
                                key={sym.code}
                                symbol={sym}
                                index={index}
                                isSelected={currentSymbol === sym.code}
                                onSelect={setCurrentSymbol}
                                onDelete={removeSymbol}
                                draggable={true}
                                isDragging={draggedIndex === index}
                                isDragOver={dragOverIndex === index}
                                onDragStart={handleDragStart}
                                onDragOver={handleDragOver}
                                onDragLeave={handleDragLeave}
                                onDrop={handleDrop}
                                onDragEnd={handleDragEnd}
                            />
                        ))}
                    </div>
                </>
            )}
        </div>
    );
};

export default SymbolSelector;
