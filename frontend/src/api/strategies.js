/**
 * Strategy API Functions
 *
 * Centralized API calls for Strategies page.
 * Uses the shared `api` axios instance from client.js
 * (includes interceptors for logging, auth, error handling).
 *
 * Long-running operations override the default 5s timeout.
 */

import { api } from './client';

// Timeout for long-running operations (5 minutes)
const LONG_TIMEOUT = 300000;

// ==========================================
// Backtest
// ==========================================

/**
 * Run a single-symbol backtest
 */
export const runBacktest = async (strategyId, payload) => {
    const { data } = await api.post(`/strategies/${strategyId}/backtest`, payload, { timeout: LONG_TIMEOUT });
    return data;
};

/**
 * Run integrated portfolio backtest (multi-rank)
 */
export const runIntegratedBacktestApi = async (payload) => {
    const { data } = await api.post('/strategies/integrated-backtest', payload, { timeout: LONG_TIMEOUT });
    return data;
};

// ==========================================
// Heavy Optimization (Large-scale)
// ==========================================

/**
 * Start heavy optimization task
 */
export const startHeavyOptimization = async (strategyId, payload) => {
    const { data } = await api.post(`/strategies/heavy-optimize/${strategyId}`, payload, { timeout: LONG_TIMEOUT });
    return data;
};

/**
 * Poll heavy optimization status
 */
export const getHeavyOptimizationStatus = async (taskId) => {
    const { data } = await api.get(`/strategies/heavy-optimize/status/${taskId}`);
    return data;
};

/**
 * Cancel a running heavy optimization
 */
export const cancelHeavyOptimization = async (taskId) => {
    const { data } = await api.post(`/strategies/heavy-optimize/cancel/${taskId}`);
    return data;
};

/**
 * List heavy optimization tasks, optionally filtered by tab UUIDs
 */
export const listHeavyOptimizationTasks = async (tabIds) => {
    const params = tabIds?.length ? { tab_ids: tabIds.join(',') } : {};
    const { data } = await api.get('/strategies/heavy-optimize/list', { params });
    return data;
};

// ==========================================
// Market Data
// ==========================================

/**
 * Fetch symbol info (name, etc.)
 */
export const getSymbolInfo = async (symbol) => {
    const { data } = await api.get(`/market-data/info/${symbol}`);
    return data;
};

/**
 * Fetch/update market data for a symbol
 */
export const fetchMarketDataForSymbol = async (symbol, params = {}) => {
    const { data } = await api.post(`/market-data/fetch/${symbol}`, params, { timeout: LONG_TIMEOUT });
    return data;
};

// ==========================================
// AI Analysis
// ==========================================

/**
 * Fetch available AI models
 */
export const getAiModels = async () => {
    const { data } = await api.get('/accounts/ai-models');
    return data;
};

/**
 * Get AI key status (default model, etc.)
 */
export const getAiKeyStatus = async () => {
    const { data } = await api.get('/accounts/ai-key/status');
    return data;
};

/**
 * Run AI analysis on optimization CSV
 */
export const runAiAnalysis = async (payload) => {
    const { data } = await api.post('/ai/analyze', payload, { timeout: LONG_TIMEOUT });
    return data;
};

// ==========================================
// Strategy Results (Persistence)
// ==========================================

/**
 * Save strategy result (backtest or optimization) to DB
 */
export const saveStrategyResult = async (tabId, type, resultData) => {
    // type: 'backtest' | 'optimization'
    const { data } = await api.post(`/strategy-results/${tabId}/${type}`, { data: resultData }, { timeout: LONG_TIMEOUT });
    return data;
};

/**
 * Get strategy results by tab UUID
 */
export const getStrategyResults = async (tabId) => {
    const { data } = await api.get(`/strategy-results/${tabId}`, { timeout: 30000 });
    return data;
};

// ==========================================
// Market Data Status
// ==========================================

/**
 * Get market data availability status for a symbol
 */
export const getMarketDataStatus = async (symbol, params = {}) => {
    const { data } = await api.get(`/market-data/status/${symbol}`, { params });
    return data;
};

// ==========================================
// Score Recalculation
// ==========================================

/**
 * Recalculate optimization scores with adjusted weights
 */
export const recalculateOptimizationScores = async (taskId, weights, topN = 50) => {
    const { data } = await api.post('/strategies/recalculate-scores', {
        task_id: taskId,
        weights: weights,
        top_n: topN
    }, { timeout: 180000 });
    return data;
};

// ==========================================
// URL Helpers
// ==========================================

/**
 * Get download URL for heavy optimization CSV
 */
export const getHeavyOptDownloadUrl = (taskId) =>
    `/api/v1/strategies/heavy-optimize/download/${taskId}`;
