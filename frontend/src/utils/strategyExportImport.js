/**
 * Strategy Export/Import Utilities
 *
 * File export (CSV, JSON) and import (JSON) utilities for the Strategies page.
 * Handles Blob creation, file download, validation, and parsing.
 */

import { STAT_COLUMNS, parseStatValue } from '../config/statsConfig';
import { convertSchemaToParamDefs } from '../constants/strategies';

// ==========================================
// Common Helpers
// ==========================================

/**
 * Escape a value for CSV output (quote and escape internal quotes).
 * @param {*} v - Value to escape
 * @returns {string} Quoted, escaped CSV cell
 */
export const csvEscape = (v) => `"${String(v == null ? '' : v).replace(/"/g, '""')}"`;

/**
 * Trigger a browser file download from a Blob.
 * @param {Blob} blob - File content
 * @param {string} filename - Download filename
 */
export const downloadBlob = (blob, filename) => {
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
};

/**
 * Read a File object and return its text content.
 * @param {File} file - DOM File object from input element
 * @returns {Promise<string>} File text content
 */
export const readFileAsText = (file) => {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = (event) => resolve(event.target.result);
        reader.onerror = () => reject(new Error('Failed to read file'));
        reader.readAsText(file);
    });
};

// ==========================================
// CSV Export
// ==========================================

/**
 * Export optimization results to CSV file.
 *
 * @param {Object} params
 * @param {Array} params.results - Optimization result rows
 * @param {Object} params.strategy - Selected strategy (for schema + ID)
 * @param {Object} params.currentConfig - Current config (for symbol)
 * @param {Array} [params.savedSymbols] - Saved symbols (for name lookup)
 * @returns {string|null} Filename on success, null on failure
 */
export const exportOptResultsToCSV = ({ results, strategy, currentConfig, savedSymbols }) => {
    if (!results || results.length === 0) return null;

    // Build headers: Rank + (Symbol) + Parameter columns + Stat columns + Score
    const paramDefs = convertSchemaToParamDefs(strategy?.parameter_schema);
    const paramHeaders = paramDefs.map(p => p.key);
    const statHeaders = STAT_COLUMNS.map(col => col.key);
    const hasSymbol = results.some(r => r.symbol);
    const headers = ['Rank', ...(hasSymbol ? ['Symbol', 'Name'] : []), ...paramHeaders, ...statHeaders, 'Score'];

    // Build rows
    const rows = results.map(result => {
        const paramValues = paramDefs.map(p => result[p.key] ?? '');
        const statValues = STAT_COLUMNS.map(col => {
            const dataKey = col.optKey || col.key;
            return result[dataKey] ?? '';
        });
        return [result.rank ?? '', ...(hasSymbol ? [result.symbol ?? '', result.symbolName ?? ''] : []), ...paramValues, ...statValues, result.score ?? ''];
    });

    const csvContent = [headers, ...rows]
        .map(row => row.map(v => csvEscape(v)).join(','))
        .join('\n');

    const BOM = '\uFEFF';
    const blob = new Blob([BOM + csvContent], { type: 'text/csv;charset=utf-8;' });
    const symbolPart = hasSymbol ? 'cross' : (currentConfig?.symbol || 'unknown');
    const filename = `optimization_${strategy?.id}_${symbolPart}_${new Date().toISOString().split('T')[0]}.csv`;
    downloadBlob(blob, filename);

    return filename;
};

/**
 * Export symbol comparison results to CSV.
 *
 * @param {Array} results - Stock compare result rows
 * @returns {string|null} Filename on success, null on failure
 */
export const exportCompareResultsToCSV = (results) => {
    if (!results || results.length === 0) return null;

    // Sort by score descending
    const sortedResults = [...results].sort((a, b) => b.score - a.score);

    // CSV header
    const headers = ['Rank', 'Symbol', 'Name', 'Total Return', 'Win Rate', 'Max DD', 'Trades', 'Profit Factor', 'Sharpe', 'Avg PnL', 'Score'];

    // CSV rows
    const rows = sortedResults.map((result, idx) => [
        idx + 1,
        result.symbol,
        result.name || '',
        parseStatValue(result.total_return) ?? result.total_return,
        parseStatValue(result.win_rate) ?? result.win_rate,
        parseStatValue(result.max_drawdown) ?? result.max_drawdown,
        result.total_trades,
        parseStatValue(result.profit_factor) ?? result.profit_factor,
        parseStatValue(result.sharpe_ratio) ?? result.sharpe_ratio,
        parseStatValue(result.avg_pnl) ?? result.avg_pnl,
        result.score?.toFixed(2) ?? ''
    ]);

    // Build CSV content
    const csvContent = [
        headers.join(','),
        ...rows.map(row => row.map(cell => {
            const str = String(cell);
            if (str.includes(',') || str.includes('"') || str.includes('\n')) {
                return `"${str.replace(/"/g, '""')}"`;
            }
            return str;
        }).join(','))
    ].join('\n');

    const blob = new Blob(['\uFEFF' + csvContent], { type: 'text/csv;charset=utf-8;' });
    const timestamp = new Date().toISOString().slice(0, 19).replace(/[:-]/g, '');
    const filename = `symbol_compare_${timestamp}.csv`;
    downloadBlob(blob, filename);

    return filename;
};

// ==========================================
// JSON Export
// ==========================================

/**
 * Export target assets (symbols) to JSON file.
 *
 * @param {Object} params
 * @param {Array} params.savedSymbols - Symbol array [{code, name}]
 * @param {string} params.accountName - Account name for metadata/filename
 * @returns {string|null} Filename on success, null on failure
 */
export const exportAssetsToJSON = ({ savedSymbols, accountName }) => {
    if (!savedSymbols || savedSymbols.length === 0) return null;

    const accountAlias = (accountName || 'Unknown').replace(/\s+/g, '_');

    const exportData = {
        type: 'target_assets',
        version: '1.0',
        exportedAt: new Date().toISOString(),
        accountName: accountName,
        symbols: savedSymbols
    };

    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
    const defaultName = `target_assets_${accountAlias}_${new Date().toISOString().split('T')[0]}`;
    const userInput = window.prompt('파일명을 입력하세요 (.json 자동 추가)', defaultName);
    if (userInput === null) return null;
    const baseName = userInput.trim() || defaultName;
    const filename = baseName.endsWith('.json') ? baseName : `${baseName}.json`;
    downloadBlob(blob, filename);

    return filename;
};

/**
 * Export strategy parameters to JSON file.
 *
 * @param {Object} params
 * @param {Object} params.config - The config object to extract params from
 * @param {string} params.sourceLabel - Tab label for filename
 * @param {string} params.accountName - Account name for metadata/filename
 * @param {string} params.strategyId - Strategy ID for metadata/filename
 * @param {string[]} params.paramNames - Whitelist of param names to export
 * @returns {string|null} Filename on success, null on failure
 */
export const exportParamsToJSON = ({ config, sourceLabel, accountName, strategyId, paramNames }) => {
    if (!config) return null;

    const accountAlias = (accountName || 'Unknown').replace(/\s+/g, '_');

    // Extract only strategy parameters
    const paramsToExport = {};
    paramNames.forEach(key => {
        if (key in config) {
            paramsToExport[key] = config[key];
        }
    });

    const exportData = {
        type: 'strategy_parameters',
        version: '1.0',
        exportedAt: new Date().toISOString(),
        accountName: accountName,
        strategyId: strategyId || 'unknown',
        params: paramsToExport
    };

    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
    const defaultName = `params_${accountAlias}_${strategyId || 'strategy'}_${sourceLabel}_${new Date().toISOString().split('T')[0]}`;
    const userInput = window.prompt('파일명을 입력하세요 (.json 자동 추가)', defaultName);
    if (userInput === null) return null;
    const baseName = userInput.trim() || defaultName;
    const filename = baseName.endsWith('.json') ? baseName : `${baseName}.json`;
    downloadBlob(blob, filename);

    return filename;
};

// ==========================================
// JSON Import Validation
// ==========================================

/**
 * Parse and validate an imported assets JSON string.
 *
 * @param {string} jsonString - Raw file content
 * @returns {{ ok: boolean, data?: Object, error?: string }}
 */
export const parseImportedAssets = (jsonString) => {
    try {
        const data = JSON.parse(jsonString);

        if (!data.type || data.type !== 'target_assets') {
            return { ok: false, error: 'Invalid file: missing or wrong "type" field (expected: target_assets)' };
        }
        if (!Array.isArray(data.symbols)) {
            return { ok: false, error: 'Invalid file: "symbols" must be an array' };
        }
        if (data.symbols.length === 0) {
            return { ok: false, error: 'Import file contains no symbols' };
        }

        return { ok: true, data };
    } catch (err) {
        return { ok: false, error: `Failed to parse JSON file: ${err.message}` };
    }
};

/**
 * Parse and validate an imported parameters JSON string.
 *
 * @param {string} jsonString - Raw file content
 * @returns {{ ok: boolean, data?: Object, error?: string }}
 */
export const parseImportedParams = (jsonString) => {
    try {
        const data = JSON.parse(jsonString);

        // Support two formats:
        // 1. Original: { type: 'strategy_parameters', params: {...} }
        // 2. Exported: { version: '...', strategy: '...', params: {...} }
        const isOriginalFormat = data.type === 'strategy_parameters';
        const isExportedFormat = data.version && data.strategy && data.params;

        if (!isOriginalFormat && !isExportedFormat) {
            return { ok: false, error: 'Invalid file format: expected "type: strategy_parameters" or exported format with "version", "strategy", and "params"' };
        }
        if (!data.params || typeof data.params !== 'object') {
            return { ok: false, error: 'Invalid file: "params" field is missing or invalid' };
        }
        if (Object.keys(data.params).length === 0) {
            return { ok: false, error: 'Import file contains no parameters' };
        }

        return { ok: true, data };
    } catch (err) {
        return { ok: false, error: `Failed to parse JSON file: ${err.message}` };
    }
};
