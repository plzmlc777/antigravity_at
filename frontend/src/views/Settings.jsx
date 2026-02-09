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
    const { token, user } = useAuth();
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

    // AI API Key State
    const [aiKeyStatus, setAiKeyStatus] = useState({ has_ai_key: false, key_preview: null, has_google_key: false, google_key_preview: null, ai_model: null });
    const [aiKeyInput, setAiKeyInput] = useState('');
    const [googleKeyInput, setGoogleKeyInput] = useState('');
    const [aiKeyLoading, setAiKeyLoading] = useState(false);
    const [showAiKeyInput, setShowAiKeyInput] = useState(false);
    const [showGoogleKeyInput, setShowGoogleKeyInput] = useState(false);
    const [aiModels, setAiModels] = useState([]);
    const [defaultAiModel, setDefaultAiModel] = useState('');
    const [selectedProvider, setSelectedProvider] = useState('anthropic'); // 'anthropic' or 'google'

    // Telegram Notification State (Per Account)
    const [expandedAccountId, setExpandedAccountId] = useState(null);  // Track which account's telegram section is expanded
    const [accountTelegramState, setAccountTelegramState] = useState({});  // { [accountId]: { settings, loading, showInput, input } }

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

    // Fetch AI Key Status
    const fetchAiKeyStatus = async () => {
        try {
            const response = await axios.get('/api/v1/accounts/ai-key/status', {
                headers: { Authorization: `Bearer ${token}` }
            });
            setAiKeyStatus(response.data);
        } catch (error) {
            console.error('Failed to fetch AI key status:', error);
        }
    };

    // Fetch AI Models
    const fetchAiModels = async () => {
        try {
            const response = await axios.get('/api/v1/accounts/ai-models', {
                headers: { Authorization: `Bearer ${token}` }
            });
            setAiModels(response.data.models || []);
            setDefaultAiModel(response.data.default || '');
        } catch (error) {
            console.error('Failed to fetch AI models:', error);
        }
    };

    // Update AI Model
    const handleModelChange = async (modelId) => {
        setAiKeyLoading(true);
        try {
            await axios.put('/api/v1/accounts/ai-model',
                { ai_model: modelId },
                { headers: { Authorization: `Bearer ${token}` } }
            );
            setAiKeyStatus(prev => ({ ...prev, ai_model: modelId }));
            showToast('AI 모델이 변경되었습니다', 'success');
        } catch (error) {
            showToast(error.response?.data?.detail || 'AI 모델 변경 실패', 'error');
        } finally {
            setAiKeyLoading(false);
        }
    };

    // Save Google Key
    const handleSaveGoogleKey = async () => {
        if (!googleKeyInput.trim()) {
            showToast('API 키를 입력해주세요', 'warning');
            return;
        }

        setAiKeyLoading(true);
        try {
            const response = await axios.put('/api/v1/accounts/google-key',
                { google_api_key: googleKeyInput },
                { headers: { Authorization: `Bearer ${token}` } }
            );
            showToast('Google API 키가 저장되었습니다', 'success');
            setGoogleKeyInput('');
            setShowGoogleKeyInput(false);
            fetchAiKeyStatus();
            fetchAiModels();  // Refresh model list to fetch latest Google models
        } catch (error) {
            showToast(error.response?.data?.detail || 'Google API 키 저장 실패', 'error');
        } finally {
            setAiKeyLoading(false);
        }
    };

    // Delete Google Key
    const handleDeleteGoogleKey = async () => {
        setAiKeyLoading(true);
        try {
            await axios.delete('/api/v1/accounts/google-key', {
                headers: { Authorization: `Bearer ${token}` }
            });
            showToast('Google API 키가 삭제되었습니다', 'success');
            setAiKeyStatus(prev => ({ ...prev, has_google_key: false, google_key_preview: null }));
            fetchAiModels();  // Refresh model list (will fall back to static Google models)
        } catch (error) {
            showToast(error.response?.data?.detail || 'Google API 키 삭제 실패', 'error');
        } finally {
            setAiKeyLoading(false);
        }
    };

    // Save AI Key
    const handleSaveAiKey = async () => {
        if (!aiKeyInput.trim()) {
            showToast('API 키를 입력해주세요', 'warning');
            return;
        }
        if (!aiKeyInput.startsWith('sk-ant-')) {
            showToast('Anthropic API 키는 sk-ant-로 시작해야 합니다', 'warning');
            return;
        }

        setAiKeyLoading(true);
        try {
            const response = await axios.put('/api/v1/accounts/ai-key',
                { ai_api_key: aiKeyInput },
                { headers: { Authorization: `Bearer ${token}` } }
            );
            showToast('AI API 키가 저장되었습니다', 'success');
            setAiKeyInput('');
            setShowAiKeyInput(false);
            fetchAiKeyStatus();
        } catch (error) {
            showToast(error.response?.data?.detail || 'AI API 키 저장 실패', 'error');
        } finally {
            setAiKeyLoading(false);
        }
    };

    // Delete AI Key
    const handleDeleteAiKey = async () => {
        setAiKeyLoading(true);
        try {
            await axios.delete('/api/v1/accounts/ai-key', {
                headers: { Authorization: `Bearer ${token}` }
            });
            showToast('AI API 키가 삭제되었습니다', 'success');
            setAiKeyStatus({ has_ai_key: false, key_preview: null });
        } catch (error) {
            showToast(error.response?.data?.detail || 'AI API 키 삭제 실패', 'error');
        } finally {
            setAiKeyLoading(false);
        }
    };

    // ═══════════════════════════════════════════════════════════════════════════
    // Telegram Notification Functions (Per Account)
    // ═══════════════════════════════════════════════════════════════════════════

    const getAccountTelegram = (accountId) => {
        return accountTelegramState[accountId] || {
            settings: { enabled: false, has_bot_token: false, token_preview: null, chat_id: '', notify_trades: true, notify_ai_eval: true, notify_errors: true },
            loading: false,
            showInput: false,
            input: { bot_token: '', chat_id: '' }
        };
    };

    const setAccountTelegramField = (accountId, field, value) => {
        setAccountTelegramState(prev => ({
            ...prev,
            [accountId]: { ...getAccountTelegram(accountId), ...prev[accountId], [field]: value }
        }));
    };

    const fetchTelegramSettings = async (accountId) => {
        try {
            const response = await axios.get(`/api/v1/accounts/${accountId}/telegram`, {
                headers: { Authorization: `Bearer ${token}` }
            });
            setAccountTelegramState(prev => ({
                ...prev,
                [accountId]: { ...getAccountTelegram(accountId), ...prev[accountId], settings: response.data }
            }));
        } catch (error) {
            console.error('Failed to fetch Telegram settings:', error);
        }
    };

    const handleSaveTelegram = async (accountId) => {
        const state = getAccountTelegram(accountId);
        if (!state.input.bot_token && !state.settings.has_bot_token) {
            showToast('Bot Token을 입력해주세요', 'warning');
            return;
        }
        if (!state.input.chat_id && !state.settings.chat_id) {
            showToast('Chat ID를 입력해주세요', 'warning');
            return;
        }

        setAccountTelegramField(accountId, 'loading', true);
        try {
            await axios.put(`/api/v1/accounts/${accountId}/telegram`,
                {
                    bot_token: state.input.bot_token || undefined,
                    chat_id: state.input.chat_id || state.settings.chat_id,
                    enabled: state.settings.enabled,
                    notify_trades: state.settings.notify_trades,
                    notify_ai_eval: state.settings.notify_ai_eval,
                    notify_errors: state.settings.notify_errors
                },
                { headers: { Authorization: `Bearer ${token}` } }
            );
            showToast('텔레그램 설정이 저장되었습니다', 'success');
            setAccountTelegramState(prev => ({
                ...prev,
                [accountId]: { ...prev[accountId], showInput: false, input: { bot_token: '', chat_id: '' } }
            }));
            fetchTelegramSettings(accountId);
        } catch (error) {
            showToast(error.response?.data?.detail || '텔레그램 설정 저장 실패', 'error');
        } finally {
            setAccountTelegramField(accountId, 'loading', false);
        }
    };

    const handleToggleTelegramSetting = async (accountId, key, value) => {
        const state = getAccountTelegram(accountId);
        setAccountTelegramField(accountId, 'loading', true);
        try {
            const newSettings = { ...state.settings, [key]: value };
            await axios.put(`/api/v1/accounts/${accountId}/telegram`,
                newSettings,
                { headers: { Authorization: `Bearer ${token}` } }
            );
            setAccountTelegramState(prev => ({
                ...prev,
                [accountId]: { ...prev[accountId], settings: newSettings }
            }));
            showToast('설정이 업데이트되었습니다', 'success');
        } catch (error) {
            showToast(error.response?.data?.detail || '설정 업데이트 실패', 'error');
        } finally {
            setAccountTelegramField(accountId, 'loading', false);
        }
    };

    const handleTestTelegram = async (accountId) => {
        setAccountTelegramField(accountId, 'loading', true);
        try {
            const response = await axios.post(`/api/v1/accounts/${accountId}/telegram/test`, {},
                { headers: { Authorization: `Bearer ${token}` } }
            );
            if (response.data.success) {
                showToast('테스트 메시지가 전송되었습니다', 'success');
            } else {
                showToast(response.data.message || '테스트 실패', 'error');
            }
        } catch (error) {
            showToast(error.response?.data?.detail || '테스트 실패', 'error');
        } finally {
            setAccountTelegramField(accountId, 'loading', false);
        }
    };

    const toggleAccountExpand = (accountId) => {
        if (expandedAccountId === accountId) {
            setExpandedAccountId(null);
        } else {
            setExpandedAccountId(accountId);
            // Fetch telegram settings when expanding
            if (!accountTelegramState[accountId]?.settings?.has_bot_token !== undefined) {
                fetchTelegramSettings(accountId);
            }
        }
    };

    useEffect(() => {
        if (token) {
            fetchAccounts();
            fetchAiKeyStatus();
            fetchAiModels();
        }
    }, [token]);

    // Sync selectedProvider based on current model
    useEffect(() => {
        const currentModel = aiKeyStatus.ai_model || defaultAiModel;
        if (currentModel) {
            if (currentModel.startsWith('gemini')) {
                setSelectedProvider('google');
            } else {
                setSelectedProvider('anthropic');
            }
        }
    }, [aiKeyStatus.ai_model, defaultAiModel]);

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

            {/* User Info Section */}
            <div className="mb-8 p-4 bg-white/5 border border-white/10 rounded-xl flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <div className="h-10 w-10 flex items-center justify-center rounded-full bg-blue-500/20 text-blue-400">
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                        </svg>
                    </div>
                    <div>
                        <div className="text-xs text-gray-400">로그인 계정</div>
                        <div className="text-white font-medium">{user?.email || '-'}</div>
                    </div>
                </div>
                {user?.is_admin && (
                    <span className="px-2 py-1 rounded-full bg-amber-500/20 text-amber-400 text-xs font-bold tracking-wider uppercase border border-amber-500/20">
                        Admin
                    </span>
                )}
            </div>

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

                {accounts.map(acc => {
                    const telegramState = getAccountTelegram(acc.id);
                    const isExpanded = expandedAccountId === acc.id;

                    return (
                    <div
                        key={acc.id}
                        className={`border rounded-xl transition-all ${
                            acc.is_disabled
                                ? 'bg-gray-800/30 border-gray-700/50 opacity-60'
                                : acc.is_active
                                    ? 'bg-blue-500/10 border-blue-500/50 shadow-[0_0_15px_rgba(59,130,246,0.15)]'
                                    : 'bg-white/5 border-white/10 hover:border-white/20'
                        }`}
                    >
                        {/* Account Header */}
                        <div className="flex items-center justify-between p-4">
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
                                        {/* Telegram indicator */}
                                        {telegramState.settings.has_bot_token && telegramState.settings.enabled && (
                                            <span className="px-2 py-0.5 rounded-full bg-cyan-500/20 text-cyan-400 text-[10px] font-bold tracking-wider uppercase border border-cyan-500/20">
                                                📱 Telegram
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
                                {/* Telegram Settings Toggle */}
                                {!acc.is_disabled && (
                                    <button
                                        onClick={() => toggleAccountExpand(acc.id)}
                                        className={`p-2 rounded transition-colors ${isExpanded ? 'bg-cyan-500/20 text-cyan-400' : 'text-gray-400 hover:text-cyan-400 hover:bg-cyan-500/10'}`}
                                        title="텔레그램 설정"
                                    >
                                        <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                                            <path d="M11.944 0A12 12 0 1 0 24 12.056A12.014 12.014 0 0 0 11.944 0Zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472c-.18 1.898-.962 6.502-1.36 8.627c-.168.9-.499 1.201-.82 1.23c-.696.065-1.225-.46-1.9-.902c-1.056-.693-1.653-1.124-2.678-1.8c-1.185-.78-.417-1.21.258-1.91c.177-.184 3.247-2.977 3.307-3.23c.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345c-.48.33-.913.49-1.302.48c-.428-.008-1.252-.241-1.865-.44c-.752-.245-1.349-.374-1.297-.789c.027-.216.325-.437.893-.663c3.498-1.524 5.83-2.529 6.998-3.014c3.332-1.386 4.025-1.627 4.476-1.635Z"/>
                                        </svg>
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

                        {/* Telegram Settings Section (Expandable) */}
                        {isExpanded && !acc.is_disabled && (
                            <div className="px-4 pb-4 pt-2 border-t border-white/10">
                                <div className="bg-gradient-to-br from-cyan-500/5 to-blue-500/5 rounded-lg p-4">
                                    <div className="flex items-center justify-between mb-3">
                                        <div className="flex items-center gap-2">
                                            <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5 text-cyan-400" fill="currentColor" viewBox="0 0 24 24">
                                                <path d="M11.944 0A12 12 0 1 0 24 12.056A12.014 12.014 0 0 0 11.944 0Zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472c-.18 1.898-.962 6.502-1.36 8.627c-.168.9-.499 1.201-.82 1.23c-.696.065-1.225-.46-1.9-.902c-1.056-.693-1.653-1.124-2.678-1.8c-1.185-.78-.417-1.21.258-1.91c.177-.184 3.247-2.977 3.307-3.23c.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345c-.48.33-.913.49-1.302.48c-.428-.008-1.252-.241-1.865-.44c-.752-.245-1.349-.374-1.297-.789c.027-.216.325-.437.893-.663c3.498-1.524 5.83-2.529 6.998-3.014c3.332-1.386 4.025-1.627 4.476-1.635Z"/>
                                            </svg>
                                            <span className="text-sm font-semibold text-cyan-400">Telegram 알림</span>
                                        </div>
                                        {/* Enable Toggle */}
                                        <div className="flex items-center gap-2">
                                            <span className={`text-xs font-bold px-2 py-0.5 rounded ${
                                                telegramState.settings.enabled
                                                    ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/50'
                                                    : 'bg-red-500/20 text-red-400 border border-red-500/50'
                                            }`}>
                                                {telegramState.settings.enabled ? 'ON' : 'OFF'}
                                            </span>
                                            <button
                                                onClick={() => handleToggleTelegramSetting(acc.id, 'enabled', !telegramState.settings.enabled)}
                                                disabled={telegramState.loading || !telegramState.settings.has_bot_token}
                                                className={`relative inline-flex h-7 w-14 items-center rounded-full transition-colors border-2 ${
                                                    telegramState.settings.enabled
                                                        ? 'bg-cyan-500 border-cyan-400'
                                                        : 'bg-gray-700 border-gray-500'
                                                } ${(!telegramState.settings.has_bot_token || telegramState.loading) ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
                                            >
                                                <span className={`inline-block h-5 w-5 transform rounded-full bg-white shadow-md transition-transform ${
                                                    telegramState.settings.enabled ? 'translate-x-7' : 'translate-x-1'
                                                }`} />
                                            </button>
                                        </div>
                                    </div>

                                    {/* Connection Status */}
                                    {telegramState.settings.has_bot_token && telegramState.settings.chat_id ? (
                                        <div className="flex items-center justify-between p-2 rounded bg-black/20 mb-3">
                                            <div className="flex items-center gap-2">
                                                <span className={`inline-block w-2 h-2 rounded-full ${telegramState.settings.enabled ? 'bg-cyan-400 animate-pulse' : 'bg-gray-500'}`}></span>
                                                <span className="text-xs text-cyan-400">연결됨</span>
                                                <span className="text-xs text-gray-500">Chat: {telegramState.settings.chat_id}</span>
                                            </div>
                                            <div className="flex gap-2">
                                                <button
                                                    onClick={() => handleTestTelegram(acc.id)}
                                                    disabled={telegramState.loading}
                                                    className="px-2 py-1 bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-400 text-xs rounded transition-colors"
                                                >
                                                    테스트
                                                </button>
                                                <button
                                                    onClick={() => setAccountTelegramState(prev => ({
                                                        ...prev,
                                                        [acc.id]: { ...prev[acc.id], showInput: true }
                                                    }))}
                                                    className="px-2 py-1 bg-white/10 hover:bg-white/20 text-gray-300 text-xs rounded transition-colors"
                                                >
                                                    변경
                                                </button>
                                            </div>
                                        </div>
                                    ) : (
                                        <div className="text-center p-3 rounded bg-black/20 mb-3">
                                            <p className="text-xs text-gray-400 mb-2">텔레그램 봇이 연결되지 않았습니다.</p>
                                            <button
                                                onClick={() => setAccountTelegramState(prev => ({
                                                    ...prev,
                                                    [acc.id]: { ...prev[acc.id], showInput: true }
                                                }))}
                                                className="px-3 py-1.5 bg-cyan-500 hover:bg-cyan-400 text-white text-xs font-medium rounded transition-colors"
                                            >
                                                봇 연결
                                            </button>
                                        </div>
                                    )}

                                    {/* Input Form */}
                                    {telegramState.showInput && (
                                        <div className="p-3 rounded bg-black/30 border border-cyan-500/20 mb-3 space-y-2">
                                            <p className="text-xs text-gray-500">@BotFather에서 봇 생성 → Token 복사 / @userinfobot으로 Chat ID 확인</p>
                                            <input
                                                type="password"
                                                value={telegramState.input.bot_token}
                                                onChange={(e) => setAccountTelegramState(prev => ({
                                                    ...prev,
                                                    [acc.id]: { ...prev[acc.id], input: { ...prev[acc.id]?.input, bot_token: e.target.value } }
                                                }))}
                                                placeholder={telegramState.settings.has_bot_token ? '(기존 토큰 유지)' : 'Bot Token'}
                                                className="w-full bg-black/50 border border-white/20 rounded px-3 py-1.5 text-xs focus:outline-none focus:border-cyan-500"
                                            />
                                            <input
                                                type="text"
                                                value={telegramState.input.chat_id}
                                                onChange={(e) => setAccountTelegramState(prev => ({
                                                    ...prev,
                                                    [acc.id]: { ...prev[acc.id], input: { ...prev[acc.id]?.input, chat_id: e.target.value } }
                                                }))}
                                                placeholder={telegramState.settings.chat_id || 'Chat ID'}
                                                className="w-full bg-black/50 border border-white/20 rounded px-3 py-1.5 text-xs focus:outline-none focus:border-cyan-500"
                                            />
                                            <div className="flex gap-2">
                                                <button
                                                    onClick={() => handleSaveTelegram(acc.id)}
                                                    disabled={telegramState.loading}
                                                    className="px-3 py-1.5 bg-cyan-500 hover:bg-cyan-400 text-white text-xs font-medium rounded transition-colors disabled:opacity-50"
                                                >
                                                    {telegramState.loading ? '저장 중...' : '저장'}
                                                </button>
                                                <button
                                                    onClick={() => setAccountTelegramState(prev => ({
                                                        ...prev,
                                                        [acc.id]: { ...prev[acc.id], showInput: false, input: { bot_token: '', chat_id: '' } }
                                                    }))}
                                                    className="px-3 py-1.5 bg-white/10 hover:bg-white/20 text-gray-300 text-xs rounded transition-colors"
                                                >
                                                    취소
                                                </button>
                                            </div>
                                        </div>
                                    )}

                                    {/* Notification Options */}
                                    {telegramState.settings.has_bot_token && (
                                        <div className="grid grid-cols-3 gap-2">
                                            {[
                                                { key: 'notify_trades', label: '거래 체결' },
                                                { key: 'notify_ai_eval', label: 'AI 평가' },
                                                { key: 'notify_errors', label: '오류 알림' }
                                            ].map(opt => (
                                                <div key={opt.key} className="flex items-center justify-between p-2 rounded bg-black/20">
                                                    <span className="text-xs text-gray-300">{opt.label}</span>
                                                    <button
                                                        onClick={() => handleToggleTelegramSetting(acc.id, opt.key, !telegramState.settings[opt.key])}
                                                        disabled={telegramState.loading}
                                                        className={`relative inline-flex h-4 w-7 items-center rounded-full transition-colors ${
                                                            telegramState.settings[opt.key] ? 'bg-cyan-500' : 'bg-gray-600'
                                                        }`}
                                                    >
                                                        <span className={`inline-block h-2.5 w-2.5 transform rounded-full bg-white transition-transform ${
                                                            telegramState.settings[opt.key] ? 'translate-x-3.5' : 'translate-x-0.5'
                                                        }`} />
                                                    </button>
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                </div>
                            </div>
                        )}
                    </div>
                )})}
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

            {/* AI API Key Section */}
            <div className="mt-12 p-6 bg-gradient-to-br from-purple-500/5 to-indigo-500/5 border border-purple-500/20 rounded-xl">
                <div className="flex items-center gap-3 mb-4">
                    <div className="p-2 bg-purple-500/20 rounded-lg">
                        <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5 text-purple-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                        </svg>
                    </div>
                    <div>
                        <h2 className="text-lg font-semibold">AI API Key (Anthropic/Claude)</h2>
                        <p className="text-xs text-gray-400">최적화 결과 AI 분석에 사용됩니다</p>
                    </div>
                </div>

                {aiKeyStatus.has_ai_key ? (
                    <div className="space-y-4">
                        <div className="flex items-center gap-3 p-3 bg-green-500/10 border border-green-500/30 rounded-lg">
                            <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                            </svg>
                            <div>
                                <p className="text-sm text-green-400 font-medium">API 키 등록됨</p>
                                <p className="text-xs text-gray-400 font-mono">{aiKeyStatus.key_preview}</p>
                            </div>
                        </div>
                        <div className="flex gap-3">
                            <button
                                onClick={() => setShowAiKeyInput(true)}
                                className="px-4 py-2 bg-white/10 hover:bg-white/20 rounded text-sm transition-colors"
                            >
                                키 변경
                            </button>
                            <button
                                onClick={handleDeleteAiKey}
                                disabled={aiKeyLoading}
                                className="px-4 py-2 bg-red-500/20 hover:bg-red-500/30 text-red-400 rounded text-sm transition-colors"
                            >
                                {aiKeyLoading ? '삭제 중...' : '키 삭제'}
                            </button>
                        </div>
                    </div>
                ) : (
                    <div className="space-y-4">
                        <div className="flex items-center gap-3 p-3 bg-yellow-500/10 border border-yellow-500/30 rounded-lg">
                            <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5 text-yellow-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                            </svg>
                            <p className="text-sm text-yellow-400">API 키가 등록되지 않았습니다. AI 분석 기능을 사용하려면 키를 등록하세요.</p>
                        </div>
                        <button
                            onClick={() => setShowAiKeyInput(true)}
                            className="px-4 py-2 bg-purple-600 hover:bg-purple-500 rounded text-sm font-medium transition-colors"
                        >
                            API 키 등록
                        </button>
                    </div>
                )}

                {/* Anthropic Key Input Form */}
                {showAiKeyInput && (
                    <div className="mt-4 p-4 bg-black/20 rounded-lg space-y-3">
                        <div>
                            <label className="block text-xs text-gray-400 mb-1">Anthropic API Key</label>
                            <input
                                type="password"
                                value={aiKeyInput}
                                onChange={e => setAiKeyInput(e.target.value)}
                                placeholder="sk-ant-api..."
                                className="w-full bg-black/30 border border-white/10 rounded px-3 py-2 text-sm font-mono"
                            />
                            <p className="text-xs text-gray-500 mt-1">
                                <a href="https://console.anthropic.com/settings/keys" target="_blank" rel="noopener noreferrer" className="text-purple-400 hover:underline">
                                    Anthropic Console
                                </a>
                                에서 API 키를 발급받으세요
                            </p>
                        </div>
                        <div className="flex gap-2">
                            <button
                                onClick={handleSaveAiKey}
                                disabled={aiKeyLoading}
                                className="px-4 py-2 bg-purple-600 hover:bg-purple-500 disabled:bg-gray-600 rounded text-sm font-medium transition-colors"
                            >
                                {aiKeyLoading ? '저장 중...' : '저장'}
                            </button>
                            <button
                                onClick={() => { setShowAiKeyInput(false); setAiKeyInput(''); }}
                                className="px-4 py-2 bg-white/10 hover:bg-white/20 rounded text-sm transition-colors"
                            >
                                취소
                            </button>
                        </div>
                    </div>
                )}

                {/* Google API Key Section */}
                <div className="mt-6 pt-6 border-t border-white/10">
                    <div className="flex items-center gap-3 mb-4">
                        <div className="p-2 bg-blue-500/20 rounded-lg">
                            <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5 text-blue-400" viewBox="0 0 24 24" fill="currentColor">
                                <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                                <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                                <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                                <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
                            </svg>
                        </div>
                        <div>
                            <h3 className="text-sm font-semibold">Google API Key (Gemini)</h3>
                            <p className="text-xs text-gray-400">Gemini 모델 사용 시 필요합니다</p>
                        </div>
                    </div>

                    {aiKeyStatus.has_google_key ? (
                        <div className="space-y-4">
                            <div className="flex items-center gap-3 p-3 bg-green-500/10 border border-green-500/30 rounded-lg">
                                <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                                </svg>
                                <div>
                                    <p className="text-sm text-green-400 font-medium">Google API 키 등록됨</p>
                                    <p className="text-xs text-gray-400 font-mono">{aiKeyStatus.google_key_preview}</p>
                                </div>
                            </div>
                            <div className="flex gap-3">
                                <button
                                    onClick={() => setShowGoogleKeyInput(true)}
                                    className="px-4 py-2 bg-white/10 hover:bg-white/20 rounded text-sm transition-colors"
                                >
                                    키 변경
                                </button>
                                <button
                                    onClick={handleDeleteGoogleKey}
                                    disabled={aiKeyLoading}
                                    className="px-4 py-2 bg-red-500/20 hover:bg-red-500/30 text-red-400 rounded text-sm transition-colors"
                                >
                                    {aiKeyLoading ? '삭제 중...' : '키 삭제'}
                                </button>
                            </div>
                        </div>
                    ) : (
                        <div className="space-y-4">
                            <div className="flex items-center gap-3 p-3 bg-gray-500/10 border border-gray-500/30 rounded-lg">
                                <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                                </svg>
                                <p className="text-sm text-gray-400">Google API 키가 등록되지 않았습니다. Gemini 모델을 사용하려면 등록하세요.</p>
                            </div>
                            <button
                                onClick={() => setShowGoogleKeyInput(true)}
                                className="px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded text-sm font-medium transition-colors"
                            >
                                Google API 키 등록
                            </button>
                        </div>
                    )}

                    {/* Google Key Input Form */}
                    {showGoogleKeyInput && (
                        <div className="mt-4 p-4 bg-black/20 rounded-lg space-y-3">
                            <div>
                                <label className="block text-xs text-gray-400 mb-1">Google API Key</label>
                                <input
                                    type="password"
                                    value={googleKeyInput}
                                    onChange={e => setGoogleKeyInput(e.target.value)}
                                    placeholder="AIza..."
                                    className="w-full bg-black/30 border border-white/10 rounded px-3 py-2 text-sm font-mono"
                                />
                                <p className="text-xs text-gray-500 mt-1">
                                    <a href="https://aistudio.google.com/apikey" target="_blank" rel="noopener noreferrer" className="text-blue-400 hover:underline">
                                        Google AI Studio
                                    </a>
                                    에서 API 키를 발급받으세요
                                </p>
                            </div>
                            <div className="flex gap-2">
                                <button
                                    onClick={handleSaveGoogleKey}
                                    disabled={aiKeyLoading}
                                    className="px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-600 rounded text-sm font-medium transition-colors"
                                >
                                    {aiKeyLoading ? '저장 중...' : '저장'}
                                </button>
                                <button
                                    onClick={() => { setShowGoogleKeyInput(false); setGoogleKeyInput(''); }}
                                    className="px-4 py-2 bg-white/10 hover:bg-white/20 rounded text-sm transition-colors"
                                >
                                    취소
                                </button>
                            </div>
                        </div>
                    )}
                </div>

                {/* Model Selection */}
                {aiModels.length > 0 && (
                    <div className="mt-6 pt-6 border-t border-white/10">
                        <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
                            <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4 text-purple-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                            </svg>
                            Default AI Model
                        </h3>
                        <p className="text-xs text-gray-400 mb-3">AI 분석 시 기본으로 사용할 모델을 선택하세요.</p>

                        {/* Two-level dropdown: Provider → Model */}
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                            {/* Provider Dropdown */}
                            <div>
                                <label className="block text-xs text-gray-400 mb-1">AI Provider</label>
                                <select
                                    value={selectedProvider}
                                    onChange={(e) => {
                                        const newProvider = e.target.value;
                                        setSelectedProvider(newProvider);
                                        // Auto-select first model of new provider
                                        const providerModels = aiModels.filter(m => m.provider === newProvider);
                                        if (providerModels.length > 0) {
                                            const currentModel = aiKeyStatus.ai_model || defaultAiModel;
                                            const currentModelProvider = currentModel?.startsWith('gemini') ? 'google' : 'anthropic';
                                            if (currentModelProvider !== newProvider) {
                                                handleModelChange(providerModels[0].id);
                                            }
                                        }
                                    }}
                                    disabled={aiKeyLoading}
                                    className="w-full bg-black/30 border border-white/20 rounded-lg px-4 py-3 text-sm focus:outline-none focus:border-purple-500 transition-colors cursor-pointer"
                                >
                                    <option value="anthropic" className="bg-[#1a1a2e]">
                                        Anthropic (Claude) {!aiKeyStatus.has_ai_key ? '- API 키 필요' : ''}
                                    </option>
                                    <option value="google" className="bg-[#1a1a2e]">
                                        Google (Gemini) {!aiKeyStatus.has_google_key ? '- API 키 필요' : ''}
                                    </option>
                                </select>
                            </div>

                            {/* Model Dropdown (filtered by provider) */}
                            <div>
                                <label className="block text-xs text-gray-400 mb-1">Model</label>
                                <select
                                    value={aiKeyStatus.ai_model || defaultAiModel}
                                    onChange={(e) => handleModelChange(e.target.value)}
                                    disabled={aiKeyLoading || (selectedProvider === 'anthropic' && !aiKeyStatus.has_ai_key) || (selectedProvider === 'google' && !aiKeyStatus.has_google_key)}
                                    className="w-full bg-black/30 border border-white/20 rounded-lg px-4 py-3 text-sm focus:outline-none focus:border-purple-500 transition-colors cursor-pointer disabled:opacity-50"
                                >
                                    {aiModels.filter(m => m.provider === selectedProvider).map(model => (
                                        <option
                                            key={model.id}
                                            value={model.id}
                                            className="bg-[#1a1a2e] py-2"
                                        >
                                            {model.name} - {model.description}
                                        </option>
                                    ))}
                                </select>
                            </div>
                        </div>

                        {/* API Key Status */}
                        <div className="mt-3 flex gap-4 text-xs">
                            <span className={aiKeyStatus.has_ai_key ? 'text-purple-400' : 'text-gray-500'}>
                                <span className={`inline-block w-2 h-2 rounded-full mr-1 ${aiKeyStatus.has_ai_key ? 'bg-purple-400' : 'bg-gray-600'}`}></span>
                                Claude {aiKeyStatus.has_ai_key ? '사용 가능' : '키 미등록'}
                            </span>
                            <span className={aiKeyStatus.has_google_key ? 'text-blue-400' : 'text-gray-500'}>
                                <span className={`inline-block w-2 h-2 rounded-full mr-1 ${aiKeyStatus.has_google_key ? 'bg-blue-400' : 'bg-gray-600'}`}></span>
                                Gemini {aiKeyStatus.has_google_key ? '사용 가능' : '키 미등록'}
                            </span>
                        </div>
                    </div>
                )}
            </div>

        </div>
    );
};

export default Settings;
