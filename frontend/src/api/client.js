import axios from 'axios';
import { getApiLogger } from '../utils/eventBus';

const getLogger = () => {
    if (typeof window !== 'undefined' && window.__apiLogger) return window.__apiLogger;
    return getApiLogger();
};

const api = axios.create({
    baseURL: '/api/v1',
    timeout: 5000,
});

// Single-use flag to prevent multiple 401 redirects
let _isRedirecting = false;
export const resetRedirectFlag = () => { _isRedirecting = false; };

// Request Interceptor
api.interceptors.request.use((config) => {
    const logId = Date.now();
    config.metadata = { logId, startTime: Date.now() };

    getLogger().publish({
        id: logId,
        type: 'req',
        method: config.method.toUpperCase(),
        url: config.url,
        timestamp: new Date().toLocaleTimeString(),
        status: 'pending'
    });

    // Debug console log
    console.log(`[API Log] Req: ${config.method.toUpperCase()} ${config.url}`);

    return config;
});

// Response Interceptor (includes 401 session kick detection)
api.interceptors.response.use(
    (response) => {
        const { logId, startTime } = response.config.metadata || {};
        const duration = startTime ? Date.now() - startTime : 0;

        getLogger().publish({
            id: logId || Date.now(),
            type: 'res',
            method: response.config.method.toUpperCase(),
            url: response.config.url,
            status: response.status,
            duration: `${duration}ms`,
            timestamp: new Date().toLocaleTimeString(),
            isError: false
        });
        return response;
    },
    (error) => {
        const { config, response } = error;
        const logId = config?.metadata?.logId || Date.now();

        getLogger().publish({
            id: logId,
            type: 'err',
            method: config?.method?.toUpperCase() || 'UNKNOWN',
            url: config?.url || 'unknown',
            status: response?.status || 'ERR',
            message: error.message,
            timestamp: new Date().toLocaleTimeString(),
            isError: true
        });

        // 401 session enforcement — redirect once, skip auth endpoints
        if (response?.status === 401 && !_isRedirecting) {
            const url = config?.url || '';
            if (!url.includes('/auth/')) {
                _isRedirecting = true;
                const detail = response.data?.detail || '';
                const isSessionKick = detail.includes('logged in from another device');
                if (isSessionKick) {
                    sessionStorage.setItem('logout_reason', 'session_kicked');
                }
                localStorage.removeItem('token');
                sessionStorage.removeItem('token');
                window.location.href = '/login';
            }
        }

        return Promise.reject(error);
    }
);

// Export api instance for use in specialized API modules (e.g., api/strategies.js)
export { api };

export const getStatus = async () => {
    const { data } = await api.get('/status');
    return data;
};

export const getSystemStatus = getStatus;

export const getSystemVersion = async () => {
    const { data } = await api.get('/system/version');
    return data;
};

export const getPrice = async (symbol) => {
    const { data } = await api.get(`/price/${symbol}`);
    return data;
};

export const getBalance = async () => {
    const { data } = await api.get('/balance');
    return data;
};

export const getBalanceForAccount = async (accountId) => {
    const { data } = await api.get(`/balance/account/${accountId}`);
    return data;
};

export const placeBuyOrder = async (order) => {
    const { data } = await api.post('/order/buy', order);
    return data;
};

export const placeSellOrder = async (order) => {
    const { data } = await api.post('/order/sell', order);
    return data;
};


export const placeManualOrder = async (order, options = {}) => {
    const { data } = await api.post('/order/manual', order, options);
    return data;
};

export const placeConditionalOrder = async (order, options = {}) => {
    const { data } = await api.post('/order/conditional', order, options);
    return data;
};

export const getOutstandingOrders = async () => {
    const { data } = await api.get('/orders/outstanding');
    return data;
};

export const cancelOrder = async (orderData) => {
    const { data } = await api.post('/orders/cancel', orderData);
    return data;
};

export const setAuthToken = (token) => {
    if (token) {
        api.defaults.headers.common['Authorization'] = `Bearer ${token}`;
    } else {
        delete api.defaults.headers.common['Authorization'];
    }
};

export const getConditionalOrders = async () => {
    const { data } = await api.get('/orders/conditions/active');
    return data;
};

export const cancelConditionalOrder = async (id) => {
    const { data } = await api.delete(`/orders/conditions/${id}`);
    return data;
};

export const setupInterceptors = (onUnauth) => {
    // Legacy interceptor kept for backward compatibility
    // Primary 401 handling is now in the main response interceptor above
    api.interceptors.response.use(
        (response) => response,
        (error) => {
            if (error.response && error.response.status === 401 && !_isRedirecting) {
                _isRedirecting = true;
                const detail = error.response.data?.detail || '';
                const isSessionKick = detail.includes('logged in from another device');
                if (onUnauth) onUnauth(isSessionKick ? 'session_kicked' : 'expired');
            }
            return Promise.reject(error);
        }
    )
};

export const runIntegratedBacktest = async (payload) => {
    const { data } = await api.post('/strategies/integrated/v2-backtest', payload);
    return data;
};

export const getStrategyConfigs = async (strategyId) => {
    const { data } = await api.get(`/strategy-configs/${strategyId}`);
    return data;
};

export const syncStrategyConfigs = async (strategyId, configs) => {
    const { data } = await api.post(`/strategy-configs/${strategyId}/sync`, configs);
    return data;
};

export const syncStrategyConfigsSelective = async (strategyId, configs, preserveInactive = true) => {
    const { data } = await api.post(
        `/strategy-configs/${strategyId}/sync-selective?preserve_inactive=${preserveInactive}`,
        configs
    );
    return data;
};

export const startLiveBot = async (config) => {
    const { data} = await api.post('/live/start', config);
    return data;
};

export const stopLiveBot = async (sessionId) => {
    const { data } = await api.post(`/live/stop/${sessionId}`);
    return data;
};

export const stopAllLiveBots = async ({ force = false } = {}) => {
    const { data } = await api.post('/live/stop-all', { force });
    return data;
};

export const checkLivePosition = async (sessionIds = null) => {
    const params = {};
    if (sessionIds && sessionIds.length > 0) {
        params.session_ids = sessionIds.join(',');
    }
    const { data } = await api.get('/live/check-position', { params });
    return data;
};

export const getLiveStatus = async (options = {}) => {
    const { allAccounts = false } = options;
    const params = allAccounts ? { all_accounts: true } : {};
    const { data } = await api.get('/live/status', { params });
    return data;
};

export const getAllSessions = async (options = {}) => {
    const { allAccounts = false, includeStopped = true, limit = 50 } = options;
    const params = {
        all_accounts: allAccounts,
        include_stopped: includeStopped,
        limit
    };
    const { data } = await api.get('/live/sessions', { params });
    return data;
};

export const deleteSession = async (sessionId) => {
    const { data } = await api.delete(`/live/session/${sessionId}`);
    return data;
};

export const resumeSession = async (sessionId) => {
    const { data } = await api.post(`/live/resume/${sessionId}`);
    return data;
};

export const updateSessionSettings = async (sessionId, settings) => {
    // settings: { initial_capital?: number, is_paper?: boolean }
    const { data } = await api.patch(`/live/session/${sessionId}`, settings);
    return data;
};

export const toggleLiveOrders = async (sessionId, enabled) => {
    const { data } = await api.post(`/live/toggle-orders/${sessionId}`, { enabled });
    return data;
};

export const toggleLiveMode = async (sessionId, isPaper) => {
    const { data } = await api.post(`/live/toggle-mode/${sessionId}`, { enabled: isPaper });
    return data;
};

export const liquidateLiveBot = async (sessionId, { autoStop = true } = {}) => {
    const { data } = await api.post(`/live/liquidate/${sessionId}`, null, {
        params: { auto_stop: autoStop }
    });
    return data;
};

export const getAccumulatedStats = async (symbols = [], strategyName = '') => {
    const symbolsParam = symbols.join(',');
    const strategyParam = strategyName ? `&strategy_name=${encodeURIComponent(strategyName)}` : '';
    const { data } = await api.get(`/live/accumulated-stats?symbols=${symbolsParam}${strategyParam}`);
    return data;
};

// AI Evaluation API
export const runAIEvaluation = async (sessionId, options = {}) => {
    const { n_cycles = 10, backtest_days = 30, mode = 'real' } = options;
    const { data } = await api.post(`/live/${sessionId}/ai-evaluate`, {
        n_cycles,
        backtest_days,
        mode
    }, { timeout: 120000 });  // 2min timeout for AI API call
    return data;
};

export const listAIEvaluations = async (sessionId, limit = 10) => {
    const { data } = await api.get(`/live/${sessionId}/ai-evaluations?limit=${limit}`);
    return data;
};

export const getAIEvaluationDetail = async (evaluationId) => {
    const { data } = await api.get(`/live/ai-evaluations/${evaluationId}`);
    return data;
};

export const getAIEvalSettings = async (sessionId) => {
    const { data } = await api.get(`/live/${sessionId}/ai-eval-settings`);
    return data;
};

export const updateAIEvalSettings = async (sessionId, settings) => {
    const { data } = await api.put(`/live/${sessionId}/ai-eval-settings`, settings);
    return data;
};

// AI Analysis Schedule & Reports API
export const createAnalysisSchedule = async (data) => {
    const { data: res } = await api.post('/live/analysis-schedules', data);
    return res;
};

export const listAnalysisSchedules = async () => {
    const { data: res } = await api.get('/live/analysis-schedules');
    return res;
};

export const updateAnalysisSchedule = async (id, data) => {
    const { data: res } = await api.put(`/live/analysis-schedules/${id}`, data);
    return res;
};

export const deleteAnalysisSchedule = async (id) => {
    const { data: res } = await api.delete(`/live/analysis-schedules/${id}`);
    return res;
};

export const runManualAnalysis = async (sessionId) => {
    const { data: res } = await api.post(`/live/${sessionId}/ai-analysis`, {}, { timeout: 120000 });
    return res;
};

export const runAnalysisAllSessions = async () => {
    const { data: res } = await api.post('/live/ai-analysis-all', {}, { timeout: 180000 });
    return res;
};

export const listAnalysisReports = async (sessionId, limit = 10) => {
    const { data: res } = await api.get(`/live/${sessionId}/ai-analysis-reports?limit=${limit}`);
    return res;
};

export const getAnalysisReportDetail = async (reportId) => {
    const { data: res } = await api.get(`/live/ai-analysis-reports/${reportId}`);
    return res;
};

export const getHistorySessions = async () => {
    const { data } = await api.get('/live/history/sessions');
    return data;
};

export const getSessionDetails = async (sessionId) => {
    const { data } = await api.get(`/live/history/sessions/${sessionId}`);
    return data;
};

export const getOHLCV = async (symbol, params = {}) => {
    // params: { interval, date, limit }
    const { data } = await api.get(`/market-data/candles/${symbol}`, { params });
    return data;
};

export const getTradeHistory = async (limit = 1000) => {
    const { data } = await api.get('/trade/history', { params: { limit } });
    return data;
};

export const getTradeHistoryContext = async (payload) => {
    // payload: { configs, symbol, interval, days, limit, is_paper }
    const { data } = await api.post('/trade/history-context', payload, { timeout: 60000 });
    return data;
};

export const getTradeHistoryList = async (payload) => {
    // payload: { is_paper, limit }
    const { data } = await api.post('/trade/history-list', payload);
    return data;
};

export const fetchMarketData = async (symbol, params = {}) => {
    const { data } = await api.post(`/market-data/fetch/${symbol}`, params);
    return data;
};

export const resetMarketData = async (symbol) => {
    const { data } = await api.delete(`/market-data/reset/${symbol}`);
    return data;
};


// ═══════════════════════════════════════════════════════════════════════════════
// Parameter Version Management API
// ═══════════════════════════════════════════════════════════════════════════════

export const listParameterVersions = async (strategyId = '', symbol = '') => {
    const params = {};
    if (strategyId) params.strategy_id = strategyId;
    if (symbol) params.symbol = symbol;
    const { data } = await api.get('/live/parameter-versions', { params });
    return data;
};

export const createParameterVersion = async (payload) => {
    // payload: { strategy_id, symbol?, version_name, description?, params, is_default? }
    const { data } = await api.post('/live/parameter-versions', payload);
    return data;
};

export const getParameterVersion = async (versionId) => {
    const { data } = await api.get(`/live/parameter-versions/${versionId}`);
    return data;
};

export const updateParameterVersion = async (versionId, payload) => {
    // payload: { version_name?, description?, params?, is_default? }
    const { data } = await api.put(`/live/parameter-versions/${versionId}`, payload);
    return data;
};

export const deleteParameterVersion = async (versionId, hardDelete = false) => {
    const { data } = await api.delete(`/live/parameter-versions/${versionId}`, {
        params: { hard_delete: hardDelete }
    });
    return data;
};

export const restoreParameterVersion = async (versionId) => {
    const { data } = await api.post(`/live/parameter-versions/${versionId}/restore`);
    return data;
};

export const updateVersionStats = async (versionId) => {
    const { data } = await api.post(`/live/parameter-versions/${versionId}/update-stats`);
    return data;
};

// Account Preferences (계좌 환경설정)
export const getAccountPreferences = async () => {
    const { data } = await api.get('/accounts/preferences');
    return data;
};

export const updateLastSelectedStrategy = async (strategyId) => {
    const { data } = await api.put('/accounts/preferences/strategy', { strategy_id: strategyId });
    return data;
};

export const updateLastSelectedProfile = async (profileId) => {
    const { data } = await api.put('/accounts/preferences/profile', { profile_id: profileId });
    return data;
};

export const updateWatchlist = async (lastSymbol, savedSymbols) => {
    const payload = {};
    if (lastSymbol !== undefined) payload.last_symbol = lastSymbol;
    if (savedSymbols !== undefined) payload.saved_symbols = savedSymbols;
    const { data } = await api.put('/accounts/preferences/watchlist', payload);
    return data;
};

// NOTE: updateSymbolCompareSettings, updateExecutionMode removed
// These are now managed at the profile level via /api/v1/live/profiles endpoints


// ═══════════════════════════════════════════════════════════════════════════════
// Telegram Notification Settings (Per Account)
// ═══════════════════════════════════════════════════════════════════════════════

export const getTelegramSettings = async (accountId) => {
    const { data } = await api.get(`/accounts/${accountId}/telegram`);
    return data;
};

export const updateTelegramSettings = async (accountId, settings) => {
    // settings: { bot_token, chat_id, enabled, notify_trades, notify_ai_eval, notify_errors }
    const { data } = await api.put(`/accounts/${accountId}/telegram`, settings);
    return data;
};

export const testTelegramConnection = async (accountId) => {
    const { data } = await api.post(`/accounts/${accountId}/telegram/test`);
    return data;
};

// ═══════════════════════════════════════════════════════════════════════════════
// Account Management API
// ═══════════════════════════════════════════════════════════════════════════════

export const getAccounts = async () => {
    const { data } = await api.get('/accounts/');
    return data;
};

// ═══════════════════════════════════════════════════════════════════════════════
// Strategy Profile API (Profile-Centric Architecture)
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * Get all profiles for current user
 * @param {string} strategyName - Optional filter by strategy
 */
export const getProfiles = async (strategyName = '') => {
    const params = strategyName ? { strategy_name: strategyName } : {};
    const { data } = await api.get('/live/profiles', { params });
    return data;
};

/**
 * Get a single profile by ID with full configuration
 */
export const getProfile = async (profileId) => {
    const { data } = await api.get(`/live/profiles/${profileId}`);
    return data;
};

/**
 * Create a new profile
 * @param {Object} profile - { name, description, strategy_name, rank_configs, execution_mode, rank_weights, initial_capital, is_paper }
 */
export const createProfile = async (profile) => {
    const { data } = await api.post('/live/profiles', profile);
    return data;
};

/**
 * Update an existing profile
 * @param {string} profileId
 * @param {Object} updates - Partial profile object
 */
export const updateProfile = async (profileId, updates) => {
    const { data } = await api.put(`/live/profiles/${profileId}`, updates);
    return data;
};

/**
 * Delete a profile (soft delete by default)
 * @param {string} profileId
 * @param {boolean} hardDelete - If true, permanently deletes
 */
export const deleteProfile = async (profileId, hardDelete = false) => {
    const { data } = await api.delete(`/live/profiles/${profileId}`, {
        params: { hard_delete: hardDelete }
    });
    return data;
};

// ==========================================
// Strategy Lab API
// ==========================================
export const getStrategyRequests = (status) =>
    api.get('/strategy-lab/requests', { params: status ? { status } : {} }).then(r => r.data);
export const createStrategyRequest = (req) =>
    api.post('/strategy-lab/requests', req).then(r => r.data);
export const getStrategyRequest = (id) =>
    api.get(`/strategy-lab/requests/${id}`).then(r => r.data);
export const updateStrategyRequest = (id, data) =>
    api.put(`/strategy-lab/requests/${id}`, data).then(r => r.data);
export const deleteStrategyRequest = (id) =>
    api.delete(`/strategy-lab/requests/${id}`).then(r => r.data);
export const activateStrategy = (requestId) =>
    api.post(`/strategy-lab/requests/${requestId}/activate`).then(r => r.data);
export const strategyLabChat = (message, sessionId = null, strategyId = null) =>
    api.post('/strategy-lab/chat', { message, session_id: sessionId, strategy_id: strategyId }, { timeout: 610000 }).then(r => r.data);

export const updateStrategyVisibility = async (strategyId, isPublic) => {
    const { data } = await api.patch(`/strategies/${strategyId}/visibility`, { is_public: isPublic });
    return data;
};
