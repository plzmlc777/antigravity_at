import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Send, Search, User, Loader2, RotateCcw, Plus, Check, CheckSquare, Square, Clock } from 'lucide-react';
import { stockSearchChat, getStockSearchTokenStatus } from '../api/client';

const GREETING = `안녕하세요! AI 종목 검색 도우미입니다.

원하는 종목을 자연어로 설명해주세요. KOSPI/KOSDAQ 전 종목 데이터와 실시간 시장 순위를 분석하여 조건에 맞는 종목을 찾아드립니다.

검색 예시:
- "반도체 관련 코스닥 종목 찾아줘"
- "오늘 거래량 상위 종목 보여줘"
- "외국인이 많이 사는 종목은?"
- "오늘 급등한 종목 알려줘"
- "거래량 급증 종목 찾아줘"
- "바이오/제약 관련 코스피 대형주"
- "2차전지 소재 관련 종목"
- "AI/인공지능 관련 종목 추천해줘"`;

const StockSearchChat = ({ onStocksFound, savedSymbols = [] }) => {
    const [messages, setMessages] = useState([
        { role: 'assistant', content: GREETING }
    ]);
    const [input, setInput] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [sessionId, setSessionId] = useState(null);
    const messagesEndRef = useRef(null);
    const inputRef = useRef(null);

    // Track selected stocks per message
    const [selectedStocks, setSelectedStocks] = useState({});

    // Token status
    const [tokenStatus, setTokenStatus] = useState(null);

    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages]);

    useEffect(() => {
        inputRef.current?.focus();
    }, []);

    // Poll token status every 60s
    useEffect(() => {
        const fetchStatus = () => {
            getStockSearchTokenStatus()
                .then(setTokenStatus)
                .catch(() => setTokenStatus(null));
        };
        fetchStatus();
        const interval = setInterval(fetchStatus, 60000);
        return () => clearInterval(interval);
    }, []);

    const existingCodes = new Set(savedSymbols.map(s => s.code));

    const toggleStock = useCallback((msgIdx, code) => {
        setSelectedStocks(prev => {
            const key = String(msgIdx);
            const current = prev[key] || new Set();
            const next = new Set(current);
            if (next.has(code)) {
                next.delete(code);
            } else {
                next.add(code);
            }
            return { ...prev, [key]: next };
        });
    }, []);

    const toggleAllStocks = useCallback((msgIdx, stocks) => {
        setSelectedStocks(prev => {
            const key = String(msgIdx);
            const current = prev[key] || new Set();
            const addable = stocks.filter(s => !existingCodes.has(s.code));
            if (current.size === addable.length && addable.length > 0) {
                return { ...prev, [key]: new Set() };
            }
            return { ...prev, [key]: new Set(addable.map(s => s.code)) };
        });
    }, [existingCodes]);

    const handleAddStocks = useCallback((msgIdx, stocks) => {
        const key = String(msgIdx);
        const selected = selectedStocks[key] || new Set();
        const toAdd = stocks
            .filter(s => selected.has(s.code) && !existingCodes.has(s.code))
            .map(s => ({ code: s.code, name: s.name }));
        if (toAdd.length > 0 && onStocksFound) {
            onStocksFound(toAdd);
        }
        // Clear selection for this message
        setSelectedStocks(prev => {
            const next = { ...prev };
            delete next[key];
            return next;
        });
    }, [selectedStocks, existingCodes, onStocksFound]);

    const sendMessage = async () => {
        const text = input.trim();
        if (!text || isLoading) return;

        setInput('');
        setMessages(prev => [...prev, { role: 'user', content: text }]);
        setIsLoading(true);

        try {
            const data = await stockSearchChat(text, sessionId);

            if (data.error) {
                setMessages(prev => [...prev, {
                    role: 'assistant',
                    content: `Error: ${data.error}`,
                    isError: true
                }]);
            } else {
                if (data.session_id) setSessionId(data.session_id);

                // Strip [STOCK_RESULTS] block from display text
                let displayText = data.response;
                displayText = displayText.replace(/\[STOCK_RESULTS\][\s\S]*?\[\/STOCK_RESULTS\]/g, '').trim();

                setMessages(prev => [...prev, {
                    role: 'assistant',
                    content: displayText,
                    duration: data.duration_ms,
                    stocks: data.stocks || null,
                }]);
            }
        } catch (err) {
            const msg = err.response?.data?.detail || err.message || 'Unknown error';
            setMessages(prev => [...prev, {
                role: 'assistant',
                content: `Connection error: ${msg}`,
                isError: true
            }]);
        } finally {
            setIsLoading(false);
        }
    };

    const handleKeyDown = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    };

    const resetChat = () => {
        setMessages([{ role: 'assistant', content: GREETING }]);
        setSessionId(null);
        setSelectedStocks({});
    };

    return (
        <div className="flex flex-col h-full">
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-white/10">
                <div className="flex items-center gap-2">
                    <Search size={18} className="text-cyan-400" />
                    <span className="text-sm font-medium text-white">AI Symbol Search</span>
                    {sessionId && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-cyan-500/10 text-cyan-400">
                            Session Active
                        </span>
                    )}
                    <TokenBadge status={tokenStatus} />
                </div>
                <button
                    onClick={resetChat}
                    className="p-1.5 hover:bg-white/5 rounded text-gray-500 hover:text-white transition-colors"
                    title="New conversation"
                >
                    <RotateCcw size={14} />
                </button>
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4">
                {messages.map((msg, i) => (
                    <div key={i}>
                        <div className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : ''}`}>
                            {msg.role === 'assistant' && (
                                <div className="w-7 h-7 rounded-lg bg-cyan-500/20 flex items-center justify-center flex-shrink-0 mt-0.5">
                                    <Search size={14} className="text-cyan-400" />
                                </div>
                            )}
                            <div className={`max-w-[85%] ${msg.role === 'user'
                                ? 'bg-blue-600/20 border border-blue-500/20 rounded-2xl rounded-br-md px-4 py-2.5'
                                : msg.isError
                                    ? 'bg-red-500/10 border border-red-500/20 rounded-2xl rounded-bl-md px-4 py-2.5'
                                    : 'bg-white/[0.03] border border-white/5 rounded-2xl rounded-bl-md px-4 py-2.5'
                            }`}>
                                <div className="text-sm text-gray-200 whitespace-pre-wrap break-words leading-relaxed">
                                    {msg.content}
                                </div>
                                {msg.duration && (
                                    <div className="text-[10px] text-gray-600 mt-1 text-right">
                                        {(msg.duration / 1000).toFixed(1)}s
                                    </div>
                                )}
                            </div>
                            {msg.role === 'user' && (
                                <div className="w-7 h-7 rounded-lg bg-blue-500/20 flex items-center justify-center flex-shrink-0 mt-0.5">
                                    <User size={14} className="text-blue-400" />
                                </div>
                            )}
                        </div>

                        {/* Stock Results UI */}
                        {msg.stocks && msg.stocks.length > 0 && (
                            <StockResultsPanel
                                stocks={msg.stocks}
                                msgIdx={i}
                                existingCodes={existingCodes}
                                selectedStocks={selectedStocks[String(i)] || new Set()}
                                onToggle={toggleStock}
                                onToggleAll={toggleAllStocks}
                                onAdd={handleAddStocks}
                            />
                        )}
                    </div>
                ))}

                {isLoading && (
                    <div className="flex gap-3">
                        <div className="w-7 h-7 rounded-lg bg-cyan-500/20 flex items-center justify-center flex-shrink-0">
                            <Search size={14} className="text-cyan-400" />
                        </div>
                        <div className="bg-white/[0.03] border border-white/5 rounded-2xl rounded-bl-md px-4 py-3">
                            <div className="flex flex-col gap-1">
                                <div className="flex items-center gap-2 text-sm text-gray-400">
                                    <Loader2 size={14} className="animate-spin" />
                                    종목을 검색하고 있습니다...
                                </div>
                                <div className="text-[10px] text-gray-600">
                                    전체 종목 데이터 분석 중 (최대 수 분 소요)
                                </div>
                            </div>
                        </div>
                    </div>
                )}

                <div ref={messagesEndRef} />
            </div>

            {/* Input */}
            <div className="px-4 py-3 border-t border-white/10">
                <div className="flex items-end gap-2">
                    <textarea
                        ref={inputRef}
                        value={input}
                        onChange={e => setInput(e.target.value)}
                        onKeyDown={handleKeyDown}
                        placeholder="찾고 싶은 종목을 설명해주세요... (Enter: 전송, Shift+Enter: 줄바꿈)"
                        rows={1}
                        disabled={isLoading}
                        className="flex-1 px-3 py-2 bg-white/5 border border-white/10 rounded-xl text-sm text-white placeholder-gray-600 focus:outline-none focus:border-cyan-500/50 resize-none disabled:opacity-50"
                        style={{ minHeight: '40px', maxHeight: '120px' }}
                        onInput={e => {
                            e.target.style.height = 'auto';
                            e.target.style.height = Math.min(e.target.scrollHeight, 120) + 'px';
                        }}
                    />
                    <button
                        onClick={sendMessage}
                        disabled={!input.trim() || isLoading}
                        className="p-2.5 bg-cyan-600 hover:bg-cyan-500 disabled:bg-gray-700 disabled:opacity-50 text-white rounded-xl transition-colors"
                    >
                        <Send size={16} />
                    </button>
                </div>
            </div>
        </div>
    );
};

/* ───── Stock Results Panel ───── */
const StockResultsPanel = ({ stocks, msgIdx, existingCodes, selectedStocks, onToggle, onToggleAll, onAdd }) => {
    const addableStocks = stocks.filter(s => !existingCodes.has(s.code));
    const allSelected = addableStocks.length > 0 && selectedStocks.size === addableStocks.length;
    const someSelected = selectedStocks.size > 0;

    return (
        <div className="ml-10 mt-2 bg-cyan-500/5 border border-cyan-500/20 rounded-xl overflow-hidden">
            {/* Header */}
            <div className="flex items-center justify-between px-3 py-2 bg-cyan-500/10 border-b border-cyan-500/20">
                <div className="flex items-center gap-2">
                    <span className="text-xs font-bold text-cyan-400">
                        검색 결과: {stocks.length}개 종목
                    </span>
                    {addableStocks.length < stocks.length && (
                        <span className="text-[10px] text-gray-500">
                            ({stocks.length - addableStocks.length}개 이미 추가됨)
                        </span>
                    )}
                </div>
                <div className="flex items-center gap-2">
                    {addableStocks.length > 0 && (
                        <button
                            onClick={() => onToggleAll(msgIdx, stocks)}
                            className="text-[10px] text-cyan-400 hover:text-cyan-300 transition-colors"
                        >
                            {allSelected ? '선택 해제' : '전체 선택'}
                        </button>
                    )}
                    {someSelected && (
                        <button
                            onClick={() => onAdd(msgIdx, stocks)}
                            className="flex items-center gap-1 px-2 py-1 text-[10px] font-bold bg-cyan-600 hover:bg-cyan-500 text-white rounded transition-colors"
                        >
                            <Plus size={10} />
                            프로필에 추가 ({selectedStocks.size})
                        </button>
                    )}
                </div>
            </div>

            {/* Stock List */}
            <div className="max-h-[300px] overflow-y-auto">
                {stocks.map(stock => {
                    const isExisting = existingCodes.has(stock.code);
                    const isSelected = selectedStocks.has(stock.code);

                    return (
                        <div
                            key={stock.code}
                            onClick={() => !isExisting && onToggle(msgIdx, stock.code)}
                            className={`flex items-center gap-3 px-3 py-2 border-b border-white/5 last:border-0 transition-colors ${
                                isExisting
                                    ? 'opacity-40 cursor-default'
                                    : isSelected
                                        ? 'bg-cyan-500/10 cursor-pointer'
                                        : 'hover:bg-white/5 cursor-pointer'
                            }`}
                        >
                            {/* Checkbox */}
                            <div className="flex-shrink-0">
                                {isExisting ? (
                                    <Check size={14} className="text-green-500" />
                                ) : isSelected ? (
                                    <CheckSquare size={14} className="text-cyan-400" />
                                ) : (
                                    <Square size={14} className="text-gray-600" />
                                )}
                            </div>

                            {/* Code */}
                            <span className="text-xs font-mono text-gray-400 w-16 flex-shrink-0">
                                {stock.code}
                            </span>

                            {/* Name */}
                            <span className={`text-sm font-medium flex-1 ${isExisting ? 'text-gray-500' : 'text-white'}`}>
                                {stock.name}
                            </span>

                            {/* Market Badge */}
                            <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded flex-shrink-0 ${
                                stock.market === 'KOSPI'
                                    ? 'bg-blue-500/20 text-blue-400'
                                    : 'bg-purple-500/20 text-purple-400'
                            }`}>
                                {stock.market}
                            </span>

                            {/* Reason */}
                            <span className="text-[10px] text-gray-500 max-w-[150px] truncate flex-shrink-0">
                                {stock.reason}
                            </span>
                        </div>
                    );
                })}
            </div>
        </div>
    );
};

/* ───── Token Status Badge ───── */
const TokenBadge = ({ status }) => {
    if (!status) return null;

    if (status.status === 'expired' || status.status === 'missing') {
        return (
            <span className="flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-red-500/15 text-red-400" title="Claude CLI token expired">
                <Clock size={9} />
                Token Expired
            </span>
        );
    }

    if (status.status === 'valid' && status.remaining_ms != null) {
        const h = Math.floor(status.remaining_ms / 3600000);
        const m = Math.floor((status.remaining_ms % 3600000) / 60000);
        const isLow = status.remaining_ms < 3600000; // < 1 hour
        return (
            <span
                className={`flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded ${
                    isLow ? 'bg-yellow-500/15 text-yellow-400' : 'bg-green-500/10 text-green-500'
                }`}
                title={`Token expires in ${h}h ${m}m`}
            >
                <Clock size={9} />
                {h}h {m}m
            </span>
        );
    }

    return null;
};

export default StockSearchChat;
