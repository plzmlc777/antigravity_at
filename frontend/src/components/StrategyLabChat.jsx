import React, { useState, useRef, useEffect } from 'react';
import { Send, Bot, User, Loader2, X, RotateCcw } from 'lucide-react';
import { strategyLabChat } from '../api/client';

const getGreeting = (strategy) => {
    if (!strategy) {
        return '안녕하세요! AI Strategy Builder입니다.\n\n만들고 싶은 전략의 핵심 매매 로직만 설명해주세요.\n방향, 지수, 임계값 등은 모두 UI 파라미터로 자동 생성됩니다.\n\n자동 제공 기능 (별도 요청 불필요):\n- 물타기(마틴게일) 분할 매수\n- Trailing Stop 자동 익절\n- HODL 모드, 손절 등 공통 파라미터\n\n요청 예시:\n- "미국 증시 변동률 기반으로 한국 주식 매매하는 전략 만들어줘"\n- "RSI 지표 기반으로 과매도 구간에서 매수하는 전략"\n- "장 시작 후 일정 시간 내 가격 변동률이 크면 진입하는 전략"\n- "특정 시간대에 캔들이 일정% 이상 하락하면 분할 매수하는 전략"';
    }
    if (strategy.strategyId) {
        return `「${strategy.name}」 전략이 선택되었습니다.\n\n이 전략을 어떻게 수정할까요?\n\n수정 예시:\n- "진입 조건의 임계값을 변경해줘"\n- "trailing stop 로직을 개선해줘"\n- "새로운 파라미터를 추가해줘"\n- "매도 조건을 변경해줘"`;
    }
    return `「${strategy.name}」 요청이 선택되었습니다.\n\n이 요청을 기반으로 전략을 구현해드릴까요?\n전략의 매매 로직을 자세히 설명해주세요.`;
};

const StrategyLabChat = ({ onClose, onStrategyCreated, prefillInput, onPrefillConsumed, selectedStrategy }) => {
    const [messages, setMessages] = useState([
        { role: 'assistant', content: getGreeting(null) }
    ]);
    const [input, setInput] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [sessionId, setSessionId] = useState(null);
    const [error, setError] = useState(null);
    const messagesEndRef = useRef(null);
    const inputRef = useRef(null);
    const prevStrategyRef = useRef(undefined);

    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages]);

    useEffect(() => {
        inputRef.current?.focus();
    }, []);

    // Reset chat when strategy selection changes
    useEffect(() => {
        const prevId = prevStrategyRef.current;
        const currId = selectedStrategy?.strategyId || null;
        prevStrategyRef.current = currId;

        // Skip initial render
        if (prevId === undefined) return;

        // Only reset if selection actually changed
        if (prevId !== currId) {
            setMessages([{ role: 'assistant', content: getGreeting(selectedStrategy) }]);
            setSessionId(null);
            setError(null);
            setInput('');
        }
    }, [selectedStrategy]);

    useEffect(() => {
        if (prefillInput) {
            setInput(prefillInput);
            onPrefillConsumed?.();
            setTimeout(() => inputRef.current?.focus(), 50);
        }
    }, [prefillInput]);

    const sendMessage = async () => {
        const text = input.trim();
        if (!text || isLoading) return;

        setInput('');
        setError(null);
        setMessages(prev => [...prev, { role: 'user', content: text }]);
        setIsLoading(true);

        try {
            const data = await strategyLabChat(text, sessionId);

            if (data.error) {
                setError(data.error);
                setMessages(prev => [...prev, {
                    role: 'assistant',
                    content: `Error: ${data.error}`,
                    isError: true
                }]);
            } else {
                if (data.session_id) setSessionId(data.session_id);
                setMessages(prev => [...prev, {
                    role: 'assistant',
                    content: data.response,
                    duration: data.duration_ms
                }]);
                // Refresh My Requests when new strategy was created
                if (data.new_strategies?.length > 0) {
                    onStrategyCreated?.();
                }
            }
        } catch (err) {
            const msg = err.response?.data?.detail || err.message || 'Unknown error';
            setError(msg);
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
        setMessages([{ role: 'assistant', content: getGreeting(selectedStrategy) }]);
        setSessionId(null);
        setError(null);
    };

    return (
        <div className="flex flex-col h-full">
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-white/10">
                <div className="flex items-center gap-2">
                    <Bot size={18} className="text-purple-400" />
                    <span className="text-sm font-medium text-white">AI Strategy Builder</span>
                    {sessionId && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-purple-500/10 text-purple-400">
                            Session Active
                        </span>
                    )}
                </div>
                <div className="flex items-center gap-1">
                    <button
                        onClick={resetChat}
                        className="p-1.5 hover:bg-white/5 rounded text-gray-500 hover:text-white transition-colors"
                        title="New conversation"
                    >
                        <RotateCcw size={14} />
                    </button>
                    {onClose && (
                        <button
                            onClick={onClose}
                            className="p-1.5 hover:bg-white/5 rounded text-gray-500 hover:text-white transition-colors"
                        >
                            <X size={14} />
                        </button>
                    )}
                </div>
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4">
                {messages.map((msg, i) => (
                    <div key={i} className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : ''}`}>
                        {msg.role === 'assistant' && (
                            <div className="w-7 h-7 rounded-lg bg-purple-500/20 flex items-center justify-center flex-shrink-0 mt-0.5">
                                <Bot size={14} className="text-purple-400" />
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
                ))}

                {isLoading && (
                    <div className="flex gap-3">
                        <div className="w-7 h-7 rounded-lg bg-purple-500/20 flex items-center justify-center flex-shrink-0">
                            <Bot size={14} className="text-purple-400" />
                        </div>
                        <div className="bg-white/[0.03] border border-white/5 rounded-2xl rounded-bl-md px-4 py-3">
                            <div className="flex flex-col gap-1">
                                <div className="flex items-center gap-2 text-sm text-gray-400">
                                    <Loader2 size={14} className="animate-spin" />
                                    AI가 분석 중입니다...
                                </div>
                                <div className="text-[10px] text-gray-600">
                                    최대 수 분 소요될 수 있습니다
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
                        placeholder="전략 아이디어를 설명해주세요... (Enter: 전송, Shift+Enter: 줄바꿈)"
                        rows={1}
                        disabled={isLoading}
                        className="flex-1 px-3 py-2 bg-white/5 border border-white/10 rounded-xl text-sm text-white placeholder-gray-600 focus:outline-none focus:border-purple-500/50 resize-none disabled:opacity-50"
                        style={{ minHeight: '40px', maxHeight: '120px' }}
                        onInput={e => {
                            e.target.style.height = 'auto';
                            e.target.style.height = Math.min(e.target.scrollHeight, 120) + 'px';
                        }}
                    />
                    <button
                        onClick={sendMessage}
                        disabled={!input.trim() || isLoading}
                        className="p-2.5 bg-purple-600 hover:bg-purple-500 disabled:bg-gray-700 disabled:opacity-50 text-white rounded-xl transition-colors"
                    >
                        <Send size={16} />
                    </button>
                </div>
            </div>
        </div>
    );
};

export default StrategyLabChat;
