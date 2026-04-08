// Agents/Skills/Decisions metadata API client.
// Uses the global axios instance from ./client.js so request logging + auth headers
// (none required for these endpoints) stay consistent.
import axios from 'axios';

// Standalone instance: these endpoints are no-auth read-only metadata, and we want
// them to keep working even when the user is not logged in (Mission Control = home).
const meta = axios.create({ baseURL: '/api/v1', timeout: 8000 });

export const fetchAgents = () => meta.get('/agents').then(r => r.data);
export const fetchAgent = (name) => meta.get(`/agents/${name}`).then(r => r.data);
export const fetchAgentActivity = (sinceHours = 24) =>
  meta.get('/agents/activity', { params: { since_hours: sinceHours } }).then(r => r.data);

export const fetchSkills = () => meta.get('/skills').then(r => r.data);
export const fetchSkill = (name) => meta.get(`/skills/${name}`).then(r => r.data);

export const fetchDecisions = ({ limit = 50, offset = 0, kind } = {}) =>
  meta.get('/decisions', { params: { limit, offset, kind } }).then(r => r.data);
export const fetchDecision = (id) => meta.get(`/decisions/${id}`).then(r => r.data);

export const fetchStrategyCandidates = () =>
  meta.get('/strategy-candidates').then(r => r.data);
export const fetchStrategyCandidate = (filename) =>
  meta.get(`/strategy-candidates/${filename}`).then(r => r.data);

export const fetchMetaLearnings = () => meta.get('/meta-learnings').then(r => r.data);
export const fetchAuthorizedSessions = () => meta.get('/whitelist/sessions').then(r => r.data);

// Approvals queue
export const fetchApprovals = (status = 'pending') =>
  meta.get('/approvals', { params: { status } }).then(r => r.data);
export const resolveApproval = (id, decision, note) =>
  meta.post(`/approvals/${id}/resolve`, { decision, note }).then(r => r.data);
export const createApproval = (body) =>
  meta.post('/approvals', body).then(r => r.data);

// Existing no-auth monitor endpoints (reused by Mission Control header).
export const fetchMonitorSessions = () =>
  meta.get('/live/monitor/sessions').then(r => r.data);
export const fetchGoalProgress = () =>
  meta.get('/live/monitor/goal/progress').then(r => r.data);
