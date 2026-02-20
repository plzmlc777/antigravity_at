import React, { useState, useEffect, useRef, useCallback } from 'react';
import { getBinanceSymbols, getBinancePrice } from '../api/client';
import SymbolChip from './SymbolChip';

/**
 * CryptoSymbolSelector - Binance symbol selector with autocomplete
 *
 * Drop-in replacement for SymbolSelector when account is Binance/BinanceFutures.
 * Props match SymbolSelector interface for seamless swapping.
 */
const CryptoSymbolSelector = ({
    currentSymbol,
    setCurrentSymbol,
    savedSymbols,
    setSavedSymbols,
    hideSymbolList = false,
    exchangeName = 'Binance',  // "Binance" or "BinanceFutures"
}) => {
    const [inputValue, setInputValue] = useState('');
    const [suggestions, setSuggestions] = useState([]);
    const [showDropdown, setShowDropdown] = useState(false);
    const [loading, setLoading] = useState(false);
    const [draggedIndex, setDraggedIndex] = useState(null);
    const [dragOverIndex, setDragOverIndex] = useState(null);
    const dropdownRef = useRef(null);
    const inputRef = useRef(null);
    const debounceRef = useRef(null);

    const market = exchangeName === 'BinanceFutures' ? 'futures' : 'spot';

    // Close dropdown on outside click
    useEffect(() => {
        const handleClickOutside = (e) => {
            if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
                setShowDropdown(false);
            }
        };
        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, []);

    // Debounced search
    const searchSymbols = useCallback(async (term) => {
        if (!term || term.length < 1) {
            setSuggestions([]);
            setShowDropdown(false);
            return;
        }

        setLoading(true);
        try {
            const result = await getBinanceSymbols(market, 'USDT', term);
            setSuggestions(result.symbols || []);
            setShowDropdown(true);
        } catch (err) {
            console.error('Failed to search Binance symbols:', err);
            setSuggestions([]);
        } finally {
            setLoading(false);
        }
    }, [market]);

    const handleInputChange = (e) => {
        const val = e.target.value;
        setInputValue(val);

        // Debounce search
        if (debounceRef.current) clearTimeout(debounceRef.current);
        debounceRef.current = setTimeout(() => searchSymbols(val), 300);
    };

    const handleSelectSymbol = async (symbolInfo) => {
        const code = symbolInfo.symbol; // e.g., "BTCUSDT"
        const name = `${symbolInfo.baseAsset}/${symbolInfo.quoteAsset}`;

        // Fetch current price for display
        let priceStr = '';
        try {
            const priceData = await getBinancePrice(code, market);
            priceStr = `$${priceData.price.toLocaleString()}`;
        } catch {
            // Price fetch is optional
        }

        const displayName = priceStr ? `${name} ${priceStr}` : name;

        // Add to saved symbols if not duplicate
        if (!savedSymbols.some(s => s.code === code)) {
            setSavedSymbols(prev => [...prev, { code, name: displayName }]);
        }
        setCurrentSymbol(code);
        setInputValue('');
        setShowDropdown(false);
        setSuggestions([]);
    };

    const handleAddDirect = async (e) => {
        e.preventDefault();
        if (!inputValue) return;

        const code = inputValue.trim().toUpperCase();
        // Ensure it ends with USDT if not specified
        const fullCode = code.includes('USDT') ? code : `${code}USDT`;

        setInputValue('');
        setShowDropdown(false);

        // Verify symbol exists
        try {
            const result = await getBinanceSymbols(market, 'USDT', fullCode);
            const match = result.symbols?.find(s => s.symbol === fullCode);
            if (match) {
                await handleSelectSymbol(match);
            } else {
                // Try adding anyway with basic info
                if (!savedSymbols.some(s => s.code === fullCode)) {
                    setSavedSymbols(prev => [...prev, { code: fullCode, name: fullCode }]);
                }
                setCurrentSymbol(fullCode);
            }
        } catch {
            // Fallback: add with code only
            if (!savedSymbols.some(s => s.code === fullCode)) {
                setSavedSymbols(prev => [...prev, { code: fullCode, name: fullCode }]);
            }
            setCurrentSymbol(fullCode);
        }
    };

    const removeSymbol = (code) => {
        setSavedSymbols(prev => prev.filter(s => s.code !== code));
        if (currentSymbol === code) {
            const next = savedSymbols.find(s => s.code !== code);
            setCurrentSymbol(next ? next.code : '');
        }
    };

    // Drag & Drop handlers (same as SymbolSelector)
    const handleDragStart = (e, index) => {
        setDraggedIndex(index);
        e.dataTransfer.effectAllowed = 'move';
    };

    const handleDragOver = (e, index) => {
        if (draggedIndex === null || draggedIndex === index) return;
        setDragOverIndex(index);
    };

    const handleDragLeave = () => setDragOverIndex(null);

    const handleDrop = (e, dropIndex) => {
        if (draggedIndex === null || draggedIndex === dropIndex) {
            setDraggedIndex(null);
            setDragOverIndex(null);
            return;
        }
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

    // Load popular symbols on focus if no input
    const handleFocus = async () => {
        if (!inputValue && suggestions.length === 0) {
            setLoading(true);
            try {
                const result = await getBinanceSymbols(market, 'USDT', '');
                // Show top symbols by default
                setSuggestions((result.symbols || []).slice(0, 20));
                setShowDropdown(true);
            } catch {
                // Silent fail
            } finally {
                setLoading(false);
            }
        } else if (suggestions.length > 0) {
            setShowDropdown(true);
        }
    };

    return (
        <div className="flex flex-wrap items-center gap-4">
            {/* Search Input with Dropdown */}
            <div className="relative" ref={dropdownRef}>
                <form onSubmit={handleAddDirect} className="flex gap-2">
                    <div className="relative">
                        <input
                            ref={inputRef}
                            type="text"
                            value={inputValue}
                            onChange={handleInputChange}
                            onFocus={handleFocus}
                            placeholder={market === 'futures' ? 'Search (e.g. BTC, ETH)' : 'Search (e.g. BTC, ETH)'}
                            className="bg-black/40 border border-white/20 rounded px-3 py-1.5 text-sm focus:outline-none focus:border-blue-500 w-56 text-white"
                            autoComplete="off"
                        />
                        {loading && (
                            <div className="absolute right-2 top-1/2 -translate-y-1/2">
                                <div className="w-4 h-4 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
                            </div>
                        )}
                    </div>
                    <button
                        type="submit"
                        className="bg-blue-600 hover:bg-blue-500 px-4 py-1.5 rounded text-sm font-medium transition-colors"
                    >
                        Add
                    </button>
                </form>

                {/* Dropdown */}
                {showDropdown && suggestions.length > 0 && (
                    <div className="absolute z-50 mt-1 w-80 max-h-64 overflow-y-auto bg-[#1a1a2e] border border-white/20 rounded-lg shadow-xl">
                        {suggestions.map((sym) => {
                            const isAdded = savedSymbols.some(s => s.code === sym.symbol);
                            return (
                                <button
                                    key={sym.symbol}
                                    onClick={() => handleSelectSymbol(sym)}
                                    className={`w-full text-left px-3 py-2 hover:bg-white/10 transition-colors flex items-center justify-between ${
                                        isAdded ? 'opacity-50' : ''
                                    }`}
                                    disabled={isAdded}
                                >
                                    <div className="flex items-center gap-2">
                                        <span className="text-sm font-mono text-white font-medium">
                                            {sym.baseAsset}
                                        </span>
                                        <span className="text-xs text-gray-400">
                                            /{sym.quoteAsset}
                                        </span>
                                    </div>
                                    <div className="flex items-center gap-2">
                                        <span className="text-xs text-gray-500 font-mono">
                                            {sym.symbol}
                                        </span>
                                        {isAdded && (
                                            <span className="text-xs text-green-400">Added</span>
                                        )}
                                    </div>
                                </button>
                            );
                        })}
                    </div>
                )}
            </div>

            {/* Market indicator badge */}
            <span className={`text-xs px-2 py-0.5 rounded-full ${
                market === 'futures'
                    ? 'bg-orange-500/20 text-orange-400 border border-orange-500/30'
                    : 'bg-green-500/20 text-green-400 border border-green-500/30'
            }`}>
                {market === 'futures' ? 'Futures' : 'Spot'}
            </span>

            {/* Saved symbols list */}
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

export default CryptoSymbolSelector;
