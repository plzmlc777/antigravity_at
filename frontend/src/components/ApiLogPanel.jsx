import React, { useState, useEffect } from 'react';
import { apiLogger } from '../utils/eventBus';

const ApiLogPanel = () => {
    const [logs, setLogs] = useState([]);

    useEffect(() => {
        const unsubscribe = apiLogger.subscribe((log) => {
            setLogs((prev) => {
                const newLogs = [log, ...prev].slice(0, 50);
                return newLogs;
            });
        });
        return () => unsubscribe();
    }, []);

    return (
        <div>
            <h2 className="text-lg font-semibold mb-4 text-white/80">
                Real-time API Log
                <span className="ml-2 text-xs font-normal text-gray-400">(Latest First)</span>
            </h2>
            <div className="bg-black/20 border border-white/10 rounded-xl p-4 h-[300px] overflow-y-auto font-mono text-xs space-y-2 scrollbar-thin scrollbar-thumb-white/10">
                {logs.length === 0 && <div className="text-gray-500 text-center py-4">Waiting for requests...</div>}

                {logs.map((log) => (
                    <div key={log.id + log.timestamp} className={`flex items-start gap-2 pb-2 border-b border-white/5 ${log.isError ? 'text-red-400' : 'text-gray-300'}`}>
                        <span className="text-gray-600 min-w-[60px]">{log.timestamp}</span>
                        <div className="flex-1">
                            <div className="flex items-center gap-2">
                                <span className={`font-bold px-1.5 rounded text-[10px] ${log.type === 'req' ? 'bg-blue-500/20 text-blue-300' : log.isError ? 'bg-red-500/20 text-red-300' : 'bg-green-500/20 text-green-300'}`}>
                                    {log.method}
                                </span>
                                <span className="truncate max-w-[150px]">{log.url}</span>
                            </div>
                            {log.type !== 'req' && (
                                <div className="mt-1 flex justify-between opacity-70">
                                    <span>{log.status}</span>
                                    <span>{log.duration}</span>
                                </div>
                            )}
                            {log.message && <div className="mt-1 text-red-400">{log.message}</div>}
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
};

export default ApiLogPanel;
