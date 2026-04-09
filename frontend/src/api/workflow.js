// Workflow execution aggregation API client — CIO-20260408-016 Level 2.
// Read-only. Frontend only renders; no workflow state mutations from UI.
import axios from 'axios';

const api = axios.create({ baseURL: '/api/v1', timeout: 10000 });

export async function fetchRecentExecutions({ days = 7 } = {}) {
    const { data } = await api.get('/workflow/executions/recent', { params: { days } });
    return data;
}
