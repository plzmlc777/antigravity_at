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

export const setSystemMode = async (mode) => {
    const { data } = await api.post('/system/mode', { mode });
    return data;
};

export const setAuthToken = (token) => {
    if (token) {
        api.defaults.headers.common['Authorization'] = `Bearer ${token}`;
    } else {
        delete api.defaults.headers.common['Authorization'];
    }
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
