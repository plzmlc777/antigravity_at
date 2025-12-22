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

    const handleActivate = async (id) => {
        try {
            await axios.put(`/api/v1/accounts/${id}/activate`);
            fetchAccounts();
        } catch (error) {
            console.error(error);
            alert("Failed to activate account");
        }
    };

    // ... inside render ...
    {
        accounts.map(acc => (
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
        ))
    }
            </div >
        </div >
    );
};

export default Settings;
