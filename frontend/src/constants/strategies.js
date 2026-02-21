/**
 * Strategy Constants
 *
 * Centralized constants for Strategy functionality.
 * Single Source of Truth for strategy-related configurations.
 */

// ==========================================
// Config Hash Utility (for preset identification)
// ==========================================
export const createConfigHash = (params) => {
    const str = JSON.stringify(params, Object.keys(params).sort());
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
        hash = ((hash << 5) - hash) + str.charCodeAt(i);
        hash |= 0;
    }
    return Math.abs(hash).toString(36).padStart(8, '0').slice(0, 12);
};

// ==========================================
// UUID Generation
// ==========================================
export const generateUUID = () => {
    if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID();
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
        var r = Math.random() * 16 | 0, v = c == 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
};

// ==========================================
// Parameter Definitions (Single Source of Truth)
// All strategy parameters defined here.
// ==========================================
export const PARAM_DEFINITIONS = [
    {
        key: 'start_time',
        label: 'Start Time',
        type: 'select',
        defaultValue: "09:00",
        defaultOptRange: "09:00, 09:30, 10:00",
        options: Array.from({ length: 14 }).map((_, i) => {
            const h = 9 + Math.floor(i / 2);
            const m = i % 2 === 0 ? "00" : "30";
            return `${h.toString().padStart(2, '0')}:${m}`;
        }),
        placeholder: '09:00, 09:30'
    },
    { key: 'delay_minutes', label: 'Delay (min)', type: 'number', defaultValue: 60, defaultOptRange: "30, 60, 90", placeholder: '5, 10, 15' },
    { key: 'direction', label: 'Direction', type: 'select', defaultValue: "fall", defaultOptRange: "rise, fall", options: ['rise', 'fall'], placeholder: 'rise, fall' },
    { key: 'target_percent', label: 'Target (%)', type: 'number', defaultValue: 0.2, defaultOptRange: "0.1, 0.2, 0.3, 0.5", placeholder: '1, 2, 3' },
    { key: 'max_loss_percent', label: 'Stop Loss (%)', type: 'number', defaultValue: 10, defaultOptRange: "3, 5, 10", placeholder: '2, 3, 5' },
    { key: 'trailing_start_percent', label: 'Trail Start (%)', type: 'number', defaultValue: 1, defaultOptRange: "0.5, 1.0, 1.5", placeholder: '3, 5' },
    { key: 'trailing_stop_percent', label: 'Trail Stop (%)', type: 'number', defaultValue: 0, defaultOptRange: "0, 0.2, 0.5", placeholder: '1, 2' },
    {
        key: 'stop_time',
        label: 'Stop Time',
        type: 'select',
        defaultValue: "15:00",
        defaultOptRange: "14:30, 15:00, 15:20",
        options: Array.from({ length: 48 }).map((_, i) => {
            const h = Math.floor(i / 2);
            const m = i % 2 === 0 ? "00" : "30";
            return `${h.toString().padStart(2, '0')}:${m}`;
        }),
        placeholder: '15:00, 15:20'
    }
];

import { DEFAULT_INITIAL_CAPITAL } from './exchanges';

// ==========================================
// Default Config Generation
// ==========================================
export const generateDefaultConfig = () => {
    const oneYearAgo = new Date();
    oneYearAgo.setFullYear(oneYearAgo.getFullYear() - 1);
    const defaultFromDate = oneYearAgo.toISOString().split('T')[0];
    const yesterday = new Date(Date.now() - 86400000);
    const defaultToDate = yesterday.toISOString().split('T')[0];

    const config = {
        initial_capital: DEFAULT_INITIAL_CAPITAL,
        from_date: defaultFromDate,
        to_date: defaultToDate,
        interval: "1m",
        symbol: "005930",
        betting_strategy: "fixed",
        uuid: null
    };

    PARAM_DEFINITIONS.forEach(p => {
        config[p.key] = p.defaultValue;
    });

    return config;
};

export const DEFAULT_CONFIG = generateDefaultConfig();

// ==========================================
// Default Optimization Values
// ==========================================
export const generateDefaultOptValues = () => {
    const opts = {};
    PARAM_DEFINITIONS.forEach(p => {
        opts[p.key] = p.defaultOptRange;
    });
    return opts;
};

export const DEFAULT_OPT_VALUES = generateDefaultOptValues();

// ==========================================
// Schema-to-ParamDefs Converter
// ==========================================
export const convertSchemaToParamDefs = (schema) => {
    if (!schema || !schema.fields) return PARAM_DEFINITIONS;

    const fields = schema.fields;
    const fieldArray = Array.isArray(fields) ? fields : Object.values(fields);

    return fieldArray.map(field => {
        const key = field.key || field.name;
        const def = {
            key,
            label: field.label || key,
            type: field.type || 'text',
            defaultValue: field.default || field.defaultValue,
            defaultOptRange: field.defaultOptRange || '',
            placeholder: field.placeholder || '',
            visible_when: field.visible_when || null
        };

        if (field.type === 'select' && field.options) {
            def.options = field.options;
        } else if (field.type === 'time') {
            def.type = 'select';
            def.options = Array.from({ length: 48 }).map((_, i) => {
                const h = Math.floor(i / 2);
                const m = i % 2 === 0 ? "00" : "30";
                return `${h.toString().padStart(2, '0')}:${m}`;
            });
        }

        return def;
    });
};

// ==========================================
// UUID Helpers for Persistence
// ==========================================
export const getIntegratedUUID = (profileId) => `integrated-${profileId || 'unknown'}`;
export const getCrossOptUUID = (profileId) => `cross-opt-${profileId || 'unknown'}`;

// ==========================================
// Score Weight Presets
// ==========================================
export const SCORE_WEIGHT_PRESETS = {
    balanced: {
        return_weight: 1.0,
        sharpe_weight: 1.2,
        stability_weight: 1.0,
        mdd_weight: 1.5,
        avg_pnl_weight: 1.0,
        win_rate_weight: 0.0,
        recent_10_weight: 0.0,
        profit_factor_weight: 0.0,
        accel_weight: 0.0,
        trades_weight: 0.0,
        activity_weight: 0.0
    },
    return_focused: {
        return_weight: 2.0,
        sharpe_weight: 0.5,
        stability_weight: 0.0,
        mdd_weight: 0.5,
        avg_pnl_weight: 1.5,
        win_rate_weight: 0.5,
        recent_10_weight: 0.0,
        profit_factor_weight: 0.5,
        accel_weight: 0.0,
        trades_weight: 0.0,
        activity_weight: 0.0
    },
    stability_focused: {
        return_weight: 0.5,
        sharpe_weight: 1.5,
        stability_weight: 2.0,
        mdd_weight: 2.0,
        avg_pnl_weight: 0.5,
        win_rate_weight: 0.5,
        recent_10_weight: 0.0,
        profit_factor_weight: 0.0,
        accel_weight: 0.0,
        trades_weight: 0.5,
        activity_weight: 0.0
    }
};

// ==========================================
// LocalStorage Keys
// ==========================================
export const STORAGE_KEYS = {
    ACTIVE_TAB: 'strategyViewActiveTab',
    HEAVY_OPT_TASK_ID: 'heavyOptTaskId',
    LAST_STRATEGY_ID: 'lastStrategyId',
    DRAFT_PREFIX: 'strategy_draft_',
};
