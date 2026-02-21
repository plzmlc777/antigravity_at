/**
 * Strategy Parameter Utilities
 *
 * Pure utility functions for strategy parameter parsing and
 * default config generation. Zero DOM or React dependencies.
 */

import { getParameterDefaults, getDefaultCapital, getDefaultDays } from '../constants/exchanges';

/**
 * Parse comma-separated optimization value strings into typed arrays.
 * Handles time strings ("09:00"), intervals ("1m", "5m"), and numbers.
 *
 * @param {string} valStr - Comma-separated string like "0.1, 0.2, 0.3"
 * @returns {Array<number|string>} Parsed values
 */
export const parseValues = (valStr) => {
    if (!valStr) return [];
    return valStr.split(',').map(v => {
        const trimmed = v.trim();
        // Do not parse as number if it looks like a time string (has colon)
        if (trimmed.includes(':')) return trimmed;

        // Do not parse as number if it looks like an interval (e.g., "1m", "5m", "1h", "1d")
        if (/^\d+[a-zA-Z]+$/.test(trimmed)) return trimmed;

        const num = parseFloat(trimmed);
        return isNaN(num) ? trimmed : num;
    }).filter(v => v !== "");
};

/**
 * Build a dynamic default config from a strategy's parameter_schema.
 * Falls back to the provided defaultConfig if schema is empty.
 *
 * @param {Object|null} strategy - Strategy object with parameter_schema
 * @param {string} currentSymbol - Current symbol code
 * @param {Object} defaultConfig - Fallback config (from constants/strategies.js)
 * @returns {Object} Config object with defaults from schema
 */
export const buildDynamicDefaultConfig = (strategy, currentSymbol, defaultConfig, exchangeName = null) => {
    if (!strategy || !strategy.parameter_schema) {
        return defaultConfig;
    }

    const schema = strategy.parameter_schema;
    if (!schema.fields || schema.fields.length === 0) {
        return defaultConfig;
    }

    // Start from defaultConfig to inherit from_date, to_date, etc.
    const dynamicDefault = {
        ...defaultConfig,
        interval: "30m",
        symbol: currentSymbol,
        is_active: true,
        tabName: "Rank 1"
    };

    schema.fields.forEach(field => {
        const key = field.key || field.name;
        if (field.default !== undefined) {
            dynamicDefault[key] = field.default;
        }
    });

    // Apply exchange-specific overrides (capital, days, parameter defaults)
    if (exchangeName) {
        dynamicDefault.initial_capital = getDefaultCapital(exchangeName);
        const exchangeDays = getDefaultDays(exchangeName);
        dynamicDefault.days = exchangeDays;
        const fromDate = new Date();
        fromDate.setDate(fromDate.getDate() - exchangeDays);
        dynamicDefault.from_date = fromDate.toISOString().split('T')[0];
        const overrides = getParameterDefaults(exchangeName);
        if (overrides) {
            Object.assign(dynamicDefault, overrides);
        }
    }

    return dynamicDefault;
};

/**
 * Build dynamic optimization default ranges from strategy schema.
 * Applies exchange-specific overrides when provided.
 *
 * @param {Object|null} strategy - Strategy object with parameter_schema
 * @param {Object} defaultOptValues - Fallback values (from constants/strategies.js)
 * @param {Object|null} exchangeOptOverrides - Exchange-specific opt range overrides (from getOptRangeDefaults)
 * @returns {Object} Map of paramKey -> defaultOptRange string
 */
export const buildDynamicOptValues = (strategy, defaultOptValues, exchangeOptOverrides = null) => {
    if (!strategy || !strategy.parameter_schema) {
        return defaultOptValues;
    }

    const schema = strategy.parameter_schema;
    if (!schema.fields || schema.fields.length === 0) {
        return defaultOptValues;
    }

    const dynamicOptValues = {};
    schema.fields.forEach(field => {
        const key = field.key || field.name;
        if (field.defaultOptRange !== undefined) {
            dynamicOptValues[key] = field.defaultOptRange;
        }
    });

    // Apply exchange-specific overrides (e.g., Binance crypto ranges)
    if (exchangeOptOverrides) {
        Object.assign(dynamicOptValues, exchangeOptOverrides);
    }

    return dynamicOptValues;
};

/**
 * Extract parameter names from a strategy's schema.
 *
 * @param {Object|null} schema - parameter_schema object with .fields array
 * @returns {string[]} Array of parameter key names
 */
export const getStrategyParamNames = (schema) => {
    if (!schema?.fields) return [];
    return schema.fields.map(f => f.key || f.name);
};

/**
 * Coerce config values to proper types based on parameter_schema.
 * Fixes string-typed numbers from CSV round-trips (e.g., "14" → 14, "0.2" → 0.2).
 *
 * @param {Object} config - Config object with potentially string-typed values
 * @param {Object|null} schema - parameter_schema with .fields array
 * @returns {Object} New config with properly typed values
 */
export const coerceConfigTypes = (config, schema) => {
    if (!config || !schema?.fields) return config;

    const coerced = { ...config };
    const fieldMap = {};
    schema.fields.forEach(f => {
        fieldMap[f.key || f.name] = f;
    });

    for (const [key, val] of Object.entries(coerced)) {
        const field = fieldMap[key];
        if (!field || val == null) continue;

        if (field.type === 'number' && typeof val === 'string') {
            const num = Number(val);
            if (!isNaN(num)) coerced[key] = num;
        }
    }

    return coerced;
};
