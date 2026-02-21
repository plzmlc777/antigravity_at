import { DEFAULT_INITIAL_CAPITAL } from './exchanges';

/**
 * Live Trading Constants
 *
 * Centralized constants for Live Trading functionality.
 * All hardcoded values should be defined here.
 */

import { PlayCircle, PauseCircle, StopCircle, AlertTriangle } from 'lucide-react';

// ==========================================
// LocalStorage Keys
// ==========================================
export const STORAGE_KEYS = {
    EXECUTION_MODE: 'live.executionMode',
    LAST_SESSION_GROUP: 'live.lastSessionGroup',
    PANEL_COLLAPSED: 'live.panelCollapsed',
    SHOW_ALL_SESSIONS: 'live.showAllSessions',
};

// ==========================================
// Session Status (synced with backend SessionStatus enum)
// ==========================================
export const SESSION_STATUS = {
    RUNNING: 'RUNNING',
    PAUSED: 'PAUSED',
    STOPPED: 'STOPPED',
    ERROR: 'ERROR',
};

// ==========================================
// Status Display Configuration
// ==========================================
export const STATUS_CONFIG = {
    [SESSION_STATUS.RUNNING]: {
        color: 'text-green-400',
        bgColor: 'bg-green-500/20',
        borderColor: 'border-green-500/50',
        icon: PlayCircle,
        label: '실행 중',
        priority: 1,
        canDelete: false,
        canResume: false,
    },
    [SESSION_STATUS.PAUSED]: {
        color: 'text-yellow-400',
        bgColor: 'bg-yellow-500/20',
        borderColor: 'border-yellow-500/50',
        icon: PauseCircle,
        label: '일시 정지',
        priority: 2,
        canDelete: false,
        canResume: true,
    },
    [SESSION_STATUS.STOPPED]: {
        color: 'text-gray-400',
        bgColor: 'bg-gray-500/20',
        borderColor: 'border-gray-500/50',
        icon: StopCircle,
        label: '정지됨',
        priority: 3,
        canDelete: true,
        canResume: true,
    },
    [SESSION_STATUS.ERROR]: {
        color: 'text-red-400',
        bgColor: 'bg-red-500/20',
        borderColor: 'border-red-500/50',
        icon: AlertTriangle,
        label: '오류',
        priority: 4,
        canDelete: true,
        canResume: true,
    },
};

// ==========================================
// Execution Modes
// ==========================================
export const EXECUTION_MODE = {
    EXCLUSIVE: 'exclusive',
    PARALLEL: 'parallel',
};

// ==========================================
// Default Values
// ==========================================
export const DEFAULTS = {
    INITIAL_CAPITAL: DEFAULT_INITIAL_CAPITAL,
    IS_PAPER_MODE: true,
    AUTO_START: false,
    EXECUTION_MODE: EXECUTION_MODE.EXCLUSIVE,
    POLL_INTERVAL_MS: 5000,
    SESSION_LIMIT: 100,
};

// ==========================================
// API Timeouts (ms)
// ==========================================
export const API_TIMEOUTS = {
    SHORT: 5000,
    MEDIUM: 15000,
    LONG: 30000,
};

export default {
    STORAGE_KEYS,
    SESSION_STATUS,
    STATUS_CONFIG,
    EXECUTION_MODE,
    DEFAULTS,
    API_TIMEOUTS,
};
