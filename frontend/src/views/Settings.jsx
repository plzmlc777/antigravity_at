import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';

const Settings = () => {
    const [accounts, setAccounts] = useState([]);
    const [loading, setLoading] = useState(true);
    const { token } = useAuth();

    // Form State
    const [isAdding, setIsAdding] = useState(false);
    const [formData, setFormData] = useState({
        exchange_name: 'Kiwoom',
        account_name: '',
        access_key: '',
        secret_key: '',
        account_number: ''
    });

    const fetchAccounts = async () => {
        try {
            const response = await axios.get('/api/v1/accounts');
            setAccounts(response.data);
        } catch (error) {
            console.error(error);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchAccounts();
    }, []);

    const handleAddAccount = async (e) => {
        e.preventDefault();
        try {
            await axios.post('/api/v1/accounts', formData);
            setIsAdding(false);
            setFormData({
                exchange_name: 'Kiwoom',
                account_name: '',
                access_key: '',
                secret_key: '',
                account_number: ''
            });
            fetchAccounts();
        } catch (error) {
            alert(error.response?.data?.detail || 'Failed to add account');
        }
    };

    const handleDelete = async (id) => {
        if (!confirm('Are you sure you want to delete this account?')) return;
        try {
            await axios.delete(`/api/v1/accounts/${id}`);
            fetchAccounts();
        } catch (error) {
            console.error(error);
        }
    };

    const handleActivate = async (id) => {
        try {
            await axios.put(`/api/v1/accounts/${id}/activate`);
            fetchAccounts();
        } catch (error) {
            console.error(error);
            alert("Failed to activate account");
        }
    };

    return (
        <div className="container mx-auto max-w-4xl">
            <div className="flex justify-between items-center mb-6">
                <h1 className="text-2xl font-bold">Exchange Accounts</h1>
                <button
                    onClick={() => setIsAdding(!isAdding)}
                    className="bg-blue-600 hover:bg-blue-500 px-4 py-2 rounded-lg text-sm transition-colors"
                >
                    {isAdding ? 'Cancel' : 'Add Account'}
                </button>
            </div>

            {isAdding && (
                <div className="mb-8 p-6 bg-white/5 border border-white/10 rounded-xl">
                    <h3 className="text-lg font-semibold mb-4">Add New Account</h3>
                    <form onSubmit={handleAddAccount} className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div>
                            <label className="block text-xs text-gray-400 mb-1">Exchange</label>
                            <select
                                value={formData.exchange_name}
                                onChange={e => setFormData({ ...formData, exchange_name: e.target.value })}
                                className="w-full bg-black/20 border border-white/10 rounded px-3 py-2 text-sm"
                            >
                                <option value="Kiwoom">Kiwoom (Korea)</option>
                                <option value="Upbit">Upbit</option>
                                <option value="Binance">Binance</option>
                            </select>
                        </div>
                        <div>
                            <label className="block text-xs text-gray-400 mb-1">Account Alias</label>
                            <input
                                type="text"
                                placeholder="e.g. Main Account"
                                value={formData.account_name}
                                onChange={e => setFormData({ ...formData, account_name: e.target.value })}
                                className="w-full bg-black/20 border border-white/10 rounded px-3 py-2 text-sm"
                                required
                            />
                        </div>
                        <div className="md:col-span-2">
                            <label className="block text-xs text-gray-400 mb-1">Access Key / App Key</label>
                            <input
                                type="password"
                                value={formData.access_key}
                                onChange={e => setFormData({ ...formData, access_key: e.target.value })}
                                className="w-full bg-black/20 border border-white/10 rounded px-3 py-2 text-sm"
                                required
                            />
                        </div>
                        <div className="md:col-span-2">
                            <label className="block text-xs text-gray-400 mb-1">Secret Key / App Secret</label>
                            <input
                                type="password"
                                value={formData.secret_key}
                                onChange={e => setFormData({ ...formData, secret_key: e.target.value })}
                                className="w-full bg-black/20 border border-white/10 rounded px-3 py-2 text-sm"
                                required
                            />
                        </div>
                        <div className="md:col-span-2">
                            <label className="block text-xs text-gray-400 mb-1">Account Number (Optional)</label>
                            <input
                                type="text"
                                value={formData.account_number}
                                onChange={e => setFormData({ ...formData, account_number: e.target.value })}
                                className="w-full bg-black/20 border border-white/10 rounded px-3 py-2 text-sm"
                            />
                        </div>
                        <div className="md:col-span-2 mt-2">
                            <button type="submit" className="w-full bg-green-600 hover:bg-green-500 py-2 rounded text-sm font-medium">Save Account</button>
                        </div>
                    </form>
                </div>
            )}

            <div className="grid gap-4">
                {accounts.length === 0 && !loading && (
                    <div className="text-center py-12 text-gray-500">
                        No accounts configured. Add one to get started!
                    </div>
                )}

                {accounts.map(acc => (
                    <div key={acc.id} className={`flex items-center justify-between p-4 border rounded-xl transition-all ${acc.is_active
                            ? 'bg-blue-500/10 border-blue-500/50 shadow-[0_0_15px_rgba(59,130,246,0.15)]'
                            : 'bg-white/5 border-white/10 hover:border-white/20'
                        }`}>
                        <div className="flex items-center gap-4">
                            <div className={`h-10 w-10 flex items-center justify-center rounded-lg ${acc.is_active ? 'bg-blue-500 text-white' : 'bg-blue-500/20 text-blue-400'
                                }`}>
                                {acc.exchange_name[0]}
                            </div>
                            <div>
                                <div className="flex items-center gap-2">
                                    <span className="font-medium text-white">{acc.account_name}</span>
                                    {acc.is_active && (
                                        <span className="px-2 py-0.5 rounded-full bg-blue-500/20 text-blue-400 text-[10px] font-bold tracking-wider uppercase border border-blue-500/20">
                                            Active
                                        </span>
                                    )}
                                </div>
                                <div className="text-xs text-gray-400">{acc.exchange_name} {acc.account_number && `• ${acc.account_number}`}</div>
                            </div>
                        </div>
                        <div className="flex items-center gap-2">
                            {!acc.is_active && (
                                <button
                                    onClick={() => handleActivate(acc.id)}
                                    className="px-3 py-1.5 rounded text-xs font-medium bg-white/5 hover:bg-white/10 text-gray-300 transition-colors"
                                >
                                    Activate
                                </button>
                            )}
                            <button
                                onClick={() => handleDelete(acc.id)}
                                className="text-red-400 hover:text-red-300 hover:bg-red-500/10 p-2 rounded transition-colors"
                            >
                                Delete
                            </button>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
};

export default Settings;
