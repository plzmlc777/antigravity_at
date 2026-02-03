import React from 'react';
import { X, Info } from 'lucide-react';
import ReactMarkdown from 'react-markdown';

const StrategyDetailModal = ({ isOpen, onClose, strategy }) => {
    if (!isOpen || !strategy) return null;

    return (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
            {/* Backdrop */}
            <div
                className="absolute inset-0 bg-black/80 backdrop-blur-md transition-opacity"
                onClick={onClose}
            />

            {/* Modal Content */}
            <div className="relative bg-[#1a1c24] border border-white/10 rounded-2xl shadow-2xl max-w-2xl w-full max-h-[85vh] flex flex-col transform transition-all scale-100 animate-in fade-in zoom-in duration-200">

                {/* Header */}
                <div className="flex items-center justify-between p-6 border-b border-white/5">
                    <div className="flex items-center gap-3">
                        <div className="p-2 bg-blue-500/20 rounded-lg text-blue-400">
                            <Info size={20} />
                        </div>
                        <div>
                            <h3 className="text-xl font-bold text-white leading-tight">
                                {strategy.name}
                            </h3>
                            <p className="text-xs text-gray-500 uppercase tracking-widest mt-1">Detailed Technical Specification</p>
                        </div>
                    </div>
                    <button
                        onClick={onClose}
                        className="p-2 rounded-xl bg-white/5 text-gray-400 hover:text-white hover:bg-white/10 transition-all active:scale-90"
                    >
                        <X size={20} />
                    </button>
                </div>

                {/* Body (Scrollable) */}
                <div className="flex-1 overflow-y-auto p-8 custom-scrollbar">
                    <div className="prose prose-invert prose-blue max-w-none">
                        {strategy.detailed_description ? (
                            <ReactMarkdown
                                components={{
                                    h3: ({ node, ...props }) => <h3 className="text-lg font-bold text-blue-400 mt-6 mb-3 flex items-center gap-2 border-b border-blue-500/20 pb-2" {...props} />,
                                    h4: ({ node, ...props }) => <h4 className="text-md font-semibold text-white mt-4 mb-2" {...props} />,
                                    ul: ({ node, ...props }) => <ul className="list-disc list-inside space-y-1 text-gray-300 ml-2" {...props} />,
                                    li: ({ node, ...props }) => <li className="text-gray-300" {...props} />,
                                    p: ({ node, ...props }) => <p className="text-gray-400 leading-relaxed mb-4 text-sm" {...props} />,
                                    strong: ({ node, ...props }) => <strong className="text-blue-300 font-bold" {...props} />,
                                    blockquote: ({ node, ...props }) => <blockquote className="border-l-4 border-blue-500/40 bg-blue-500/5 px-4 py-1 italic my-4 rounded-r-md" {...props} />,
                                }}
                            >
                                {strategy.detailed_description}
                            </ReactMarkdown>
                        ) : (
                            <div className="flex flex-col items-center justify-center py-20 text-gray-600 italic">
                                <Info size={40} className="mb-4 opacity-20" />
                                <p>No detailed description available for this strategy.</p>
                            </div>
                        )}
                    </div>
                </div>

                {/* Footer */}
                <div className="p-6 border-t border-white/5 flex justify-end bg-black/10">
                    <button
                        onClick={onClose}
                        className="px-6 py-2.5 rounded-xl text-sm font-bold text-white bg-blue-600 hover:bg-blue-500 shadow-lg shadow-blue-900/30 transition-all active:scale-95"
                    >
                        Got it, thanks!
                    </button>
                </div>
            </div>
        </div>
    );
};

export default StrategyDetailModal;
