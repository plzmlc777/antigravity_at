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

// Response Interceptor
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

        console.error(`[API Error]`, error);
        return Promise.reject(error);
    }
);

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

// Strategy Result Persistence
export const saveStrategyResult = async (tabId, type, resultData) => {
    // type: 'backtest' | 'optimization'
    const { data } = await api.post(`/strategy-results/${tabId}/${type}`, { data: resultData });
    return data;
};

export const getStrategyResults = async (tabId) => {
    // Increase timeout for large backtest results (especially integrated)
    const { data } = await api.get(`/strategy-results/${tabId}`, { timeout: 30000 });
    return data;
};

export const setupInterceptors = (onUnauth) => {
    api.interceptors.response.use(
        (response) => response,
        (error) => {
            if (error.response && error.response.status === 401) {
                if (onUnauth) onUnauth();
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

export const getLiveStatus = async () => {
    const { data } = await api.get('/live/status');
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

export const liquidateLiveBot = async (sessionId) => {
    const { data } = await api.post(`/live/liquidate/${sessionId}`);
    return data;
};

export const getAccumulatedStats = async (symbols = [], strategyName = '') => {
    const symbolsParam = symbols.join(',');
    const strategyParam = strategyName ? `&strategy_name=${encodeURIComponent(strategyName)}` : '';
    const { data } = await api.get(`/live/accumulated-stats?symbols=${symbolsParam}${strategyParam}`);
    return data;
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

export const getMarketDataStatus = async (symbol, params = {}) => {
    const { data } = await api.get(`/market-data/status/${symbol}`, { params });
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

export const updateWatchlist = async (lastSymbol, savedSymbols) => {
    const payload = {};
    if (lastSymbol !== undefined) payload.last_symbol = lastSymbol;
    if (savedSymbols !== undefined) payload.saved_symbols = savedSymbols;
    const { data } = await api.put('/accounts/preferences/watchlist', payload);
    return data;
};

export const updateSymbolCompareSettings = async (settings) => {
    const { data } = await api.put('/accounts/preferences/symbol-compare', { symbol_compare_settings: settings });
    return data;
};

export const updateExecutionMode = async (mode) => {
    const { data } = await api.put('/accounts/preferences/execution-mode', { execution_mode: mode });
    return data;
};
