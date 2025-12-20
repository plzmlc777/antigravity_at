import axios from 'axios';
import { apiLogger } from '../utils/eventBus';

const api = axios.create({
    baseURL: '/api/v1',
    timeout: 5000,
});

// Request Interceptor
api.interceptors.request.use((config) => {
    const logId = Date.now();
    config.metadata = { logId, startTime: Date.now() };

    apiLogger.publish({
        id: logId,
        type: 'req',
        method: config.method.toUpperCase(),
        url: config.url,
        timestamp: new Date().toLocaleTimeString(),
        status: 'pending'
    });
    return config;
});

// Response Interceptor
api.interceptors.response.use(
    (response) => {
        const { logId, startTime } = response.config.metadata;
        const duration = Date.now() - startTime;

        apiLogger.publish({
            id: logId,
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

        apiLogger.publish({
            id: logId,
            type: 'err',
            method: config?.method?.toUpperCase() || 'UNKNOWN',
            url: config?.url || 'unknown',
            status: response?.status || 'ERR',
            message: error.message,
            timestamp: new Date().toLocaleTimeString(),
            isError: true
        });
        return Promise.reject(error);
    }
);

export const getStatus = async () => {
    const { data } = await api.get('/status');
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

export const placeManualOrder = async (order) => {
    const { data } = await api.post('/order/manual', order);
    return data;
};
