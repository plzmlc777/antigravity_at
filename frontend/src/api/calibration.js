// Calibration API client — SISDS Phase 7 (CIO-017).
// Read-only. Calibration records are written by paper-scheduler and live-monitor.
import axios from 'axios';

const api = axios.create({ baseURL: '/api/v1', timeout: 10000 });

export async function fetchCalibrationSummary() {
    const { data } = await api.get('/calibration/summary');
    return data;
}

export async function fetchCalibrationTrend({ months = 6 } = {}) {
    const { data } = await api.get('/calibration/trend', { params: { months } });
    return data;
}

export async function fetchCalibrationRecent({ days = 30, limit = 50 } = {}) {
    const { data } = await api.get('/calibration/records/recent', { params: { days, limit } });
    return data;
}

export async function fetchWorstStrategies({ limit = 10 } = {}) {
    const { data } = await api.get('/calibration/worst-strategies', { params: { limit } });
    return data;
}
