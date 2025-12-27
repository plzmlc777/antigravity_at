import React, { useState, useEffect } from 'react';
import axios from 'axios';

const AdminView = () => {
    const [loading, setLoading] = useState(false);
    const [users, setUsers] = useState([]);
    const [fetching, setFetching] = useState(true);

    useEffect(() => {
        fetchUsers();
    }, []);

    const fetchUsers = async () => {
        try {
            const res = await axios.get('/api/v1/admin/users');
            setUsers(res.data);
        } catch (e) {
            console.error("Failed to fetch users", e);
        } finally {
            setFetching(false);
        }
    };

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

    const toggleAdminRole = async (user) => {
        const newRole = !user.is_admin;
        try {
            await axios.put(`/api/v1/admin/users/${user.id}/role`, { is_admin: newRole });
            fetchUsers();
        } catch (e) {
            alert(e.response?.data?.detail || "Failed to update user role");
        }
    };

    return (
        <div className="container mx-auto max-w-5xl p-6">
            <h1 className="text-2xl font-bold mb-8 text-white">Admin Dashboard</h1>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
                {/* Data Management Card */}
                <div className="md:col-span-1 p-6 bg-white/5 border border-white/10 rounded-xl">
                    <div className="flex items-center gap-3 mb-4">
                        <div className="p-2 bg-red-500/20 text-red-400 rounded-lg">
                            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                            </svg>
                        </div>
                        <h2 className="text-lg font-bold text-white">Data Management</h2>
                    </div>
                    <p className="text-sm text-gray-400 mb-6">
                        Manage global stores. Deleting OHLCV data affects all users.
                    </p>
                    <button
                        onClick={handleResetData}
                        disabled={loading}
                        className={`w-full py-2.5 rounded-lg font-bold transition-all ${loading
                                ? 'bg-gray-700 text-gray-400'
                                : 'bg-red-600 hover:bg-red-500 text-white shadow-lg shadow-red-600/20'
                            }`}
                    >
                        {loading ? 'Processing...' : 'Reset All Chart Data'}
                    </button>
                </div>

                {/* User Stats Card */}
                <div className="md:col-span-1 p-6 bg-white/5 border border-white/10 rounded-xl">
                    <div className="flex items-center gap-3 mb-4">
                        <div className="p-2 bg-blue-500/20 text-blue-400 rounded-lg">
                            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" />
                            </svg>
                        </div>
                        <h2 className="text-lg font-bold text-white">User Statistics</h2>
                    </div>
                    <div className="mt-4">
                        <div className="text-3xl font-bold text-white mb-1">{users.length}</div>
                        <div className="text-sm text-gray-400">Total Registered Users</div>
                    </div>
                </div>

                {/* System Status Placeholder */}
                <div className="md:col-span-1 p-6 bg-white/5 border border-white/10 rounded-xl opacity-50">
                    <div className="flex items-center gap-3 mb-4">
                        <div className="p-2 bg-green-500/20 text-green-400 rounded-lg">
                            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                            </svg>
                        </div>
                        <h2 className="text-lg font-bold text-white">System Status</h2>
                    </div>
                    <p className="text-sm text-gray-400">All systems operational.</p>
                </div>
            </div>

            {/* User Management Section */}
            <div className="bg-white/5 border border-white/10 rounded-xl overflow-hidden shadow-2xl">
                <div className="p-6 border-b border-white/10 flex justify-between items-center bg-white/5">
                    <div>
                        <h2 className="text-lg font-bold text-white">User Management</h2>
                        <p className="text-sm text-gray-400">View registered users and manage roles.</p>
                    </div>
                    <button onClick={fetchUsers} className="p-2 hover:bg-white/10 rounded-full transition-colors text-gray-400" title="Refresh list">
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                        </svg>
                    </button>
                </div>

                <div className="overflow-x-auto">
                    <table className="w-full text-left">
                        <thead>
                            <tr className="bg-black/20 text-gray-400 text-xs font-medium uppercase tracking-wider">
                                <th className="px-6 py-4">ID</th>
                                <th className="px-6 py-4">Email</th>
                                <th className="px-6 py-4">Status</th>
                                <th className="px-6 py-4 text-right">Actions</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-white/5">
                            {fetching ? (
                                <tr>
                                    <td colSpan="4" className="px-6 py-12 text-center">
                                        <div className="flex flex-col items-center gap-3">
                                            <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin"></div>
                                            <span className="text-sm text-gray-500 italic">Fetching secure user data...</span>
                                        </div>
                                    </td>
                                </tr>
                            ) : users.length === 0 ? (
                                <tr>
                                    <td colSpan="4" className="px-6 py-12 text-center text-gray-500 italic text-sm">
                                        No registered users found.
                                    </td>
                                </tr>
                            ) : users.map((u) => (
                                <tr key={u.id} className="hover:bg-white/5 transition-colors group">
                                    <td className="px-6 py-4 text-xs text-gray-500 font-mono">#{u.id}</td>
                                    <td className="px-6 py-4">
                                        <div className="flex flex-col">
                                            <span className="text-sm font-medium text-white">{u.email}</span>
                                            <span className="text-[10px] text-gray-500">Registered Account</span>
                                        </div>
                                    </td>
                                    <td className="px-6 py-4">
                                        <div className="flex items-center gap-2">
                                            <div className={`w-1.5 h-1.5 rounded-full ${u.is_admin ? 'bg-purple-500' : 'bg-gray-500 animate-pulse'}`}></div>
                                            <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wide ${u.is_admin
                                                    ? 'bg-purple-500/10 text-purple-400 border border-purple-500/20'
                                                    : 'bg-gray-500/10 text-gray-400 border border-gray-500/20'
                                                }`}>
                                                {u.is_admin ? 'Administrator' : 'Standard User'}
                                            </span>
                                        </div>
                                    </td>
                                    <td className="px-6 py-4 text-right">
                                        <button
                                            onClick={() => toggleAdminRole(u)}
                                            className={`text-[11px] font-bold px-4 py-1.5 rounded-lg border transition-all duration-200 ${u.is_admin
                                                    ? 'bg-white/5 border-white/10 text-gray-400 hover:bg-red-500/10 hover:border-red-500/30 hover:text-red-400'
                                                    : 'bg-blue-600/10 border-blue-500/30 text-blue-400 hover:bg-blue-600 hover:text-white hover:border-blue-600 hover:shadow-lg hover:shadow-blue-600/20'
                                                }`}
                                        >
                                            {u.is_admin ? 'Demote to User' : 'Grant Admin Role'}
                                        </button>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
                <div className="p-4 bg-black/10 text-[10px] text-gray-600 italic text-center border-t border-white/5">
                    Security Policy: Administrators can manage global chart data and user roles. Self-demotion is restricted to prevent lockout.
                </div>
            </div>
        </div>
    );
};

export default AdminView;
