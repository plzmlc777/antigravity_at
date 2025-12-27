import React, { useState } from 'react';
import axios from 'axios';

const AdminView = () => {
    const [loading, setLoading] = useState(false);
    const [stats, setStats] = useState(null);

    const handleResetData = async () => {
        if (!confirm("⚠️ CRITICAL: Are you sure? This will delete ALL stored chart data across all users!")) return;

        setLoading(true);
        try {
            const res = await axios.delete('/api/v1/market-data/reset');
            alert(res.data.message);
        } catch (e) {
            alert(e.response?.data?.detail || "Failed to reset chart data");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="container mx-auto max-w-4xl p-6">
            <h1 className="text-2xl font-bold mb-8 text-white">Admin Dashboard</h1>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* Data Management Card */}
                <div className="p-6 bg-white/5 border border-white/10 rounded-xl">
                    <div className="flex items-center gap-3 mb-4">
                        <div className="p-2 bg-red-500/20 text-red-400 rounded-lg">
                            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                            </svg>
                        </div>
                        <h2 className="text-lg font-bold text-white">Shared Chart Data</h2>
                    </div>
                    <p className="text-sm text-gray-400 mb-6">
                        Manage OHLCV price data stored in the database. Deleting this data will clear charts for ALL users.
                    </p>
                    <button
                        onClick={handleResetData}
                        disabled={loading}
                        className={`w-full py-3 rounded-lg font-bold transition-all ${loading
                                ? 'bg-gray-700 text-gray-400'
                                : 'bg-red-600 hover:bg-red-500 text-white shadow-lg shadow-red-600/20'
                            }`}
                    >
                        {loading ? 'Processing...' : 'Reset Shared Chart Data'}
                    </button>
                </div>

                {/* System Status Placeholder */}
                <div className="p-6 bg-white/5 border border-white/10 rounded-xl opacity-50 cursor-not-allowed">
                    <div className="flex items-center gap-3 mb-4">
                        <div className="p-2 bg-blue-500/20 text-blue-400 rounded-lg">
                            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                            </svg>
                        </div>
                        <h2 className="text-lg font-bold text-white">System Metrics</h2>
                    </div>
                    <p className="text-sm text-gray-400 mb-2">Total Users: --</p>
                    <p className="text-sm text-gray-400 mb-2">DB Size: --</p>
                    <p className="text-sm text-gray-400 mb-4">Uptime: --</p>
                    <span className="text-[10px] uppercase font-bold text-blue-400 bg-blue-500/10 px-2 py-1 rounded">Coming Soon</span>
                </div>
            </div>
        </div>
    );
};

export default AdminView;
