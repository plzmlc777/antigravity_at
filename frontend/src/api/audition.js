// Strategy Audition API client — SAS Phase 4 (CIO-015).
// Read-only. No mutations from the frontend per feedback_no_manual_frontend_controls.
import axios from 'axios';

const api = axios.create({ baseURL: '/api/v1', timeout: 10000 });

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
