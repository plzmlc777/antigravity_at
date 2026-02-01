import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';
import { useMarketData } from '../context/MarketDataContext';
import Toast from '../components/Toast';

// Trading Environment options (matches backend TradingEnvironment enum)
const ENVIRONMENTS = [
    { value: 'real', label: '실거래', labelEn: 'Real', color: 'green' },
    { value: 'virtual', label: '모의투자', labelEn: 'Virtual', color: 'purple' },
    { value: 'paper', label: '페이퍼', labelEn: 'Paper', color: 'yellow' }
];

const getEnvConfig = (envValue) => ENVIRONMENTS.find(e => e.value === envValue) || ENVIRONMENTS[0];

const Settings = () => {
    const [accounts, setAccounts] = useState([]);
    const [loading, setLoading] = useState(true);
    const { token } = useAuth();
    const { refresh: refreshMarketData } = useMarketData();

    // Toast State
    const [toast, setToast] = useState(null);

    // Confirm Dialog State
    const [confirmDialog, setConfirmDialog] = useState(null);

    // Edit Modal State
    const [editModal, setEditModal] = useState(null);
    const [editData, setEditData] = useState({ account_name: '', is_disabled: false });

    // Form State
    const [isAdding, setIsAdding] = useState(false);
    const [formData, setFormData] = useState({
        exchange_name: 'Kiwoom',
        account_name: '',
        access_key: '',
        secret_key: '',
        account_number: '',
        environment: 'real'  // 'real', 'virtual', 'paper'
    });

    // Password Change State
    const [passwordData, setPasswordData] = useState({
        current_password: '',
        new_password: '',
        confirm_password: ''
    });
    const [passwordChanging, setPasswordChanging] = useState(false);

    const showToast = (message, type = 'info') => {
        setToast({ message, type });
    };

    const fetchAccounts = async () => {
        try {
            const response = await axios.get('/api/v1/accounts/', {
                headers: { Authorization: `Bearer ${token}` }
            });
            // Sort: active first, then enabled (by id), then disabled at bottom
            const sortedAccounts = [...response.data].sort((a, b) => {
                // Disabled accounts go to bottom
                if (a.is_disabled !== b.is_disabled) return a.is_disabled ? 1 : -1;
                // Active account goes to top
                if (a.is_active !== b.is_active) return a.is_active ? -1 : 1;
                // Otherwise sort by id
                return a.id - b.id;
            });
            setAccounts(sortedAccounts);
        } catch (error) {
            console.error(error);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        if (token) fetchAccounts();
    }, [token]);

    const handleAddAccount = async (e) => {
        e.preventDefault();
        try {
            await axios.post('/api/v1/accounts/', formData, {
                headers: { Authorization: `Bearer ${token}` }
            });
            setIsAdding(false);
            setFormData({
                exchange_name: 'Kiwoom',
                account_name: '',
                access_key: '',
                secret_key: '',
                account_number: '',
                environment: 'real'
            });
            fetchAccounts();
            showToast('계좌가 추가되었습니다', 'success');
        } catch (error) {
            showToast(error.response?.data?.detail || '계좌 추가 실패', 'error');
        }
    };

    const handleDelete = async (id) => {
        setConfirmDialog({
            message: '이 계좌를 삭제하시겠습니까?',
            onConfirm: async () => {
                try {
                    await axios.delete(`/api/v1/accounts/${id}`, {
                        headers: { Authorization: `Bearer ${token}` }
                    });
                    fetchAccounts();
                    showToast('계좌가 삭제되었습니다', 'success');
                } catch (error) {
                    showToast('계좌 삭제 실패', 'error');
                }
                setConfirmDialog(null);
            },
            onCancel: () => setConfirmDialog(null)
        });
    };

    const handleActivate = async (id) => {
        try {
            await axios.put(`/api/v1/accounts/${id}/activate`, {}, {
                headers: { Authorization: `Bearer ${token}` }
            });
            await fetchAccounts();
            refreshMarketData();
            showToast('계좌가 활성화되었습니다', 'success');
        } catch (error) {
            console.error(error);
            showToast('계좌 활성화 실패', 'error');
        }
    };

    const openEditModal = (acc) => {
        setEditData({
            account_name: acc.account_name,
            is_disabled: acc.is_disabled || false
        });
        setEditModal(acc);
    };

    const handleEditSave = async () => {
        try {
            await axios.patch(`/api/v1/accounts/${editModal.id}`, editData, {
                headers: { Authorization: `Bearer ${token}` }
            });
            await fetchAccounts();
            refreshMarketData();
            setEditModal(null);
            showToast('계좌 정보가 수정되었습니다', 'success');
        } catch (error) {
            showToast(error.response?.data?.detail || '수정 실패', 'error');
        }
    };

    const handlePasswordChange = async (e) => {
        e.preventDefault();

        if (passwordData.new_password !== passwordData.confirm_password) {
            showToast('새 비밀번호가 일치하지 않습니다', 'error');
            return;
        }

        if (passwordData.new_password.length < 6) {
            showToast('새 비밀번호는 6자 이상이어야 합니다', 'warning');
            return;
        }

        setPasswordChanging(true);
        try {
            await axios.put('/api/v1/auth/password', {
                current_password: passwordData.current_password,
                new_password: passwordData.new_password
            }, {
                headers: { Authorization: `Bearer ${token}` }
            });
            showToast('비밀번호가 변경되었습니다', 'success');
            setPasswordData({ current_password: '', new_password: '', confirm_password: '' });
        } catch (error) {
            showToast(error.response?.data?.detail || '비밀번호 변경 실패', 'error');
        } finally {
            setPasswordChanging(false);
        }
    };

    // Environment badge renderer
    const renderEnvBadge = (acc) => {
        if (acc.is_disabled) return null;

        const env = getEnvConfig(acc.environment);
        const colorClasses = {
            green: 'bg-green-500/20 text-green-400 border-green-500/20',
            purple: 'bg-purple-500/20 text-purple-400 border-purple-500/20',
            yellow: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/20'
        };

        return (
            <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold tracking-wider uppercase border ${colorClasses[env.color]}`}>
                {env.label}
            </span>
        );
    };

    return (
        <div className="container mx-auto max-w-4xl">
            {/* Toast Notification */}
            {toast && (
                <Toast
                    message={toast.message}
                    type={toast.type}
                    onClose={() => setToast(null)}
                />
            )}

            {/* Confirm Dialog */}
            {confirmDialog && (
                <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50">
                    <div className="bg-gray-900 border border-white/10 rounded-xl p-6 max-w-sm w-full mx-4 animate-scale-in">
                        <p className="text-white text-sm mb-6">{confirmDialog.message}</p>
                        <div className="flex gap-3 justify-end">
                            <button
                                onClick={confirmDialog.onCancel}
                                className="px-4 py-2 rounded text-sm text-gray-400 hover:text-white hover:bg-white/10 transition-colors"
                            >
                                취소
                            </button>
                            <button
                                onClick={confirmDialog.onConfirm}
                                className="px-4 py-2 rounded text-sm bg-red-600 hover:bg-red-500 text-white transition-colors"
                            >
                                삭제
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Edit Modal */}
            {editModal && (
                <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50">
                    <div className="bg-gray-900 border border-white/10 rounded-xl p-6 max-w-md w-full mx-4 animate-scale-in">
                        <h3 className="text-lg font-semibold text-white mb-4">계좌 편집</h3>

                        <div className="space-y-4">
                            <div>
                                <label className="block text-xs text-gray-400 mb-1">계좌 별칭</label>
                                <input
                                    type="text"
                                    value={editData.account_name}
                                    onChange={e => setEditData({ ...editData, account_name: e.target.value })}
                                    className="w-full bg-black/20 border border-white/10 rounded px-3 py-2 text-sm text-white"
                                />
                            </div>

                            <div>
                                <label className="flex items-center gap-3 cursor-pointer py-2">
                                    <input
                                        type="checkbox"
                                        checked={editData.is_disabled}
                                        onChange={e => setEditData({ ...editData, is_disabled: e.target.checked })}
                                        className="w-4 h-4 rounded border-white/20 bg-black/20 text-red-500 focus:ring-red-500"
                                    />
                                    <div>
                                        <span className="text-sm text-white">사용 안함</span>
                                        <p className="text-xs text-gray-500">이 계좌를 비활성화하고 목록 하단으로 이동합니다</p>
                                    </div>
                                </label>
                            </div>
                        </div>

                        <div className="flex gap-3 justify-end mt-6">
                            <button
                                onClick={() => setEditModal(null)}
                                className="px-4 py-2 rounded text-sm text-gray-400 hover:text-white hover:bg-white/10 transition-colors"
                            >
                                취소
                            </button>
                            <button
                                onClick={handleEditSave}
                                className="px-4 py-2 rounded text-sm bg-blue-600 hover:bg-blue-500 text-white transition-colors"
                            >
                                저장
                            </button>
                        </div>
                    </div>
                </div>
            )}

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
                            <label className="block text-xs text-gray-400 mb-1">Trading Environment</label>
                            <select
                                value={formData.environment}
                                onChange={e => setFormData({ ...formData, environment: e.target.value })}
                                className="w-full bg-black/20 border border-white/10 rounded px-3 py-2 text-sm"
                            >
                                {ENVIRONMENTS.map(env => (
                                    <option key={env.value} value={env.value}>
                                        {env.label} ({env.labelEn})
                                    </option>
                                ))}
                            </select>
                        </div>
                        <div className="md:col-span-2">
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
                        <div className="md:col-span-2 p-3 bg-black/20 rounded-lg border border-white/5">
                            <div className="text-xs text-gray-400 space-y-1">
                                <p><strong className="text-green-400">실거래:</strong> Kiwoom 실서버 (api.kiwoom.com) - 실제 자금 거래</p>
                                <p><strong className="text-purple-400">모의투자:</strong> Kiwoom 모의서버 (mockapi.kiwoom.com) - 가상 자금 거래</p>
                                <p><strong className="text-yellow-400">페이퍼:</strong> 로컬 시뮬레이션 - API 호출 없음</p>
                            </div>
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
                    <div
                        key={acc.id}
                        className={`flex items-center justify-between p-4 border rounded-xl transition-all ${
                            acc.is_disabled
                                ? 'bg-gray-800/30 border-gray-700/50 opacity-60'
                                : acc.is_active
                                    ? 'bg-blue-500/10 border-blue-500/50 shadow-[0_0_15px_rgba(59,130,246,0.15)]'
                                    : 'bg-white/5 border-white/10 hover:border-white/20'
                        }`}
                    >
                        <div className="flex items-center gap-4">
                            <div className={`h-10 w-10 flex items-center justify-center rounded-lg ${
                                acc.is_disabled
                                    ? 'bg-gray-700/50 text-gray-500'
                                    : acc.is_active
                                        ? 'bg-blue-500 text-white'
                                        : 'bg-blue-500/20 text-blue-400'
                            }`}>
                                {acc.exchange_name[0]}
                            </div>
                            <div>
                                <div className="flex items-center gap-2">
                                    <span className={`font-medium ${acc.is_disabled ? 'text-gray-500' : 'text-white'}`}>
                                        {acc.account_name}
                                    </span>
                                    {acc.is_disabled && (
                                        <span className="px-2 py-0.5 rounded-full bg-gray-600/30 text-gray-500 text-[10px] font-bold tracking-wider uppercase border border-gray-600/30">
                                            사용 안함
                                        </span>
                                    )}
                                    {renderEnvBadge(acc)}
                                    {acc.is_active && (
                                        <span className="px-2 py-0.5 rounded-full bg-blue-500/20 text-blue-400 text-[10px] font-bold tracking-wider uppercase border border-blue-500/20">
                                            Active
                                        </span>
                                    )}
                                </div>
                                <div className="text-xs text-gray-400">
                                    {acc.exchange_name} {acc.account_number && `• ${acc.account_number}`}
                                </div>
                            </div>
                        </div>
                        <div className="flex items-center gap-2">
                            {!acc.is_active && !acc.is_disabled && (
                                <button
                                    onClick={() => handleActivate(acc.id)}
                                    className="px-3 py-1.5 rounded text-xs font-medium bg-white/5 hover:bg-white/10 text-gray-300 transition-colors"
                                >
                                    Activate
                                </button>
                            )}
                            <button
                                onClick={() => openEditModal(acc)}
                                className="text-gray-400 hover:text-white hover:bg-white/10 p-2 rounded transition-colors"
                                title="편집"
                            >
                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                                </svg>
                            </button>
                            <button
                                onClick={() => handleDelete(acc.id)}
                                className="text-red-400 hover:text-red-300 hover:bg-red-500/10 p-2 rounded transition-colors"
                                title="삭제"
                            >
                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                                </svg>
                            </button>
                        </div>
                    </div>
                ))}
            </div>

            {/* Password Change Section */}
            <div className="mt-12 p-6 bg-white/5 border border-white/10 rounded-xl">
                <h2 className="text-lg font-semibold mb-4">비밀번호 변경</h2>
                <form onSubmit={handlePasswordChange} className="space-y-4 max-w-md">
                    <div>
                        <label className="block text-xs text-gray-400 mb-1">현재 비밀번호</label>
                        <input
                            type="password"
                            value={passwordData.current_password}
                            onChange={e => setPasswordData({ ...passwordData, current_password: e.target.value })}
                            className="w-full bg-black/20 border border-white/10 rounded px-3 py-2 text-sm"
                            required
                        />
                    </div>
                    <div>
                        <label className="block text-xs text-gray-400 mb-1">새 비밀번호</label>
                        <input
                            type="password"
                            value={passwordData.new_password}
                            onChange={e => setPasswordData({ ...passwordData, new_password: e.target.value })}
                            className="w-full bg-black/20 border border-white/10 rounded px-3 py-2 text-sm"
                            required
                            minLength={6}
                        />
                    </div>
                    <div>
                        <label className="block text-xs text-gray-400 mb-1">새 비밀번호 확인</label>
                        <input
                            type="password"
                            value={passwordData.confirm_password}
                            onChange={e => setPasswordData({ ...passwordData, confirm_password: e.target.value })}
                            className="w-full bg-black/20 border border-white/10 rounded px-3 py-2 text-sm"
                            required
                            minLength={6}
                        />
                    </div>
                    <button
                        type="submit"
                        disabled={passwordChanging}
                        className="bg-blue-600 hover:bg-blue-500 disabled:bg-gray-600 px-4 py-2 rounded text-sm font-medium transition-colors"
                    >
                        {passwordChanging ? '변경 중...' : '비밀번호 변경'}
                    </button>
                </form>
            </div>
        </div>
    );
};

export default Settings;
