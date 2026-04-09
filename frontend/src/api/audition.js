// Strategy Audition API client — SAS Phase 4 (CIO-015) + SISDS (CIO-017).
// Read-only EXCEPT for promote/reject actions (the only user-facing mutations).
import axios from 'axios';

const api = axios.create({ baseURL: '/api/v1', timeout: 10000 });

// Inject auth token if available
api.interceptors.request.use((config) => {
    const token = localStorage.getItem('token');
    if (token) config.headers.Authorization = `Bearer ${token}`;
    return config;
});

export async function fetchAuditionList({ status = 'all', category = null, week = null, limit = 100 } = {}) {
    const params = { status, limit };
    if (category) params.category = category;
    if (week) params.week = week;
    const { data } = await api.get('/strategy-audition', { params });
    return data;
}

export async function fetchAuditionStats({ weeks = 4 } = {}) {
    const { data } = await api.get('/strategy-audition/stats/weekly', { params: { weeks } });
    return data;
}

export async function fetchGraveyardStats() {
    const { data } = await api.get('/strategy-audition/stats/graveyard');
    return data;
}

// ── SISDS Phase 1: stage-machine endpoints (CIO-017) ──

export async function fetchStageStats() {
    const { data } = await api.get('/strategy-audition/stats/by-stage');
    return data;
}

export async function fetchByStage({ stage = null, stage_status = null, limit = 100 } = {}) {
    const params = { limit };
    if (stage) params.stage = stage;
    if (stage_status) params.stage_status = stage_status;
    const { data } = await api.get('/strategy-audition/by-stage', { params });
    return data;
}

export async function fetchTransitionHistory(strategyId) {
    const { data } = await api.get(`/strategy-audition/${strategyId}/history`);
    return data;
}

// ── SISDS Phase 5: Live promotion (CIO-017) ──
// These are the ONLY user-facing mutations in the entire SISDS pipeline.

export async function promoteToLive(strategyId) {
    const { data } = await api.post(`/strategy-audition/${strategyId}/promote-to-live`);
    return data;
}

export async function rejectPromotion(strategyId) {
    const { data } = await api.post(`/strategy-audition/${strategyId}/reject-promotion`);
    return data;
}
