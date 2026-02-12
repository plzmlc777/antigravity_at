import { useState, useCallback } from 'react';
import { getSymbolInfo } from '../api/strategies';
import {
    exportAssetsToJSON, exportParamsToJSON,
    parseImportedAssets, parseImportedParams, readFileAsText,
} from '../utils/strategyExportImport';

/**
 * useImportExport - Asset and parameter JSON import/export.
 */
export const useImportExport = ({
    configList, setConfigList, activeTab,
    symbolCompareConfig, setSymbolCompareConfig,
    setIsDirty, setIsSymbolCompareDirty,
    savedSymbols, setSavedSymbols, systemStatus,
    selectedStrategy, getStrategyParamNames, addLog
}) => {
    const [assetImportExportFeedback, setAssetImportExportFeedback] = useState(null);
    const [assetImportError, setAssetImportError] = useState('');
    const [paramImportExportFeedback, setParamImportExportFeedback] = useState(null);
    const [paramImportError, setParamImportError] = useState('');

    const handleExportAssets = useCallback(() => {
        if (!savedSymbols || savedSymbols.length === 0) {
            addLog('⚠️ No symbols to export', 'warn');
            return;
        }
        const filename = exportAssetsToJSON({ savedSymbols, accountName: systemStatus?.account_name });
        if (filename) {
            setAssetImportExportFeedback('exported');
            setTimeout(() => setAssetImportExportFeedback(null), 2000);
            addLog(`📤 Exported ${savedSymbols.length} symbols`, 'info');
        }
    }, [savedSymbols, systemStatus, addLog]);

    const handleImportAssets = useCallback(async (e) => {
        const file = e.target.files?.[0];
        if (!file) return;
        e.target.value = '';

        setAssetImportExportFeedback('importing');
        setAssetImportError('');

        try {
            const text = await readFileAsText(file);
            const result = parseImportedAssets(text);

            if (!result.ok) {
                setAssetImportError(result.error);
                setAssetImportExportFeedback('error');
                setTimeout(() => setAssetImportExportFeedback(null), 3000);
                addLog(`⚠️ ${result.error}`, 'error');
                return;
            }

            const data = result.data;
            const symbolsWithoutNames = data.symbols.map(s => ({
                code: s.code,
                name: s.name || ''
            }));
            setSavedSymbols(symbolsWithoutNames);
            addLog(`📥 Importing ${data.symbols.length} symbols...`, 'info');

            const DELAY_MS = 300;
            let fetchedCount = 0;

            for (let i = 0; i < data.symbols.length; i++) {
                const sym = data.symbols[i];
                if (sym.name) { fetchedCount++; continue; }

                try {
                    const infoData = await getSymbolInfo(sym.code);
                    if (infoData.name && infoData.name !== sym.code) {
                        setSavedSymbols(prev => prev.map(s =>
                            s.code === sym.code ? { ...s, name: infoData.name } : s
                        ));
                    }
                    fetchedCount++;
                } catch (err) {
                    console.warn(`Failed to fetch name for ${sym.code}:`, err.message);
                }

                if (i < data.symbols.length - 1) {
                    await new Promise(resolve => setTimeout(resolve, DELAY_MS));
                }
            }

            setAssetImportExportFeedback('imported');
            setTimeout(() => setAssetImportExportFeedback(null), 2000);
            addLog(`✅ Imported ${data.symbols.length} symbols (${fetchedCount} names fetched)`, 'info');
        } catch (err) {
            setAssetImportError(err.message);
            setAssetImportExportFeedback('error');
            setTimeout(() => setAssetImportExportFeedback(null), 3000);
            addLog(`⚠️ ${err.message}`, 'error');
        }
    }, [setSavedSymbols, addLog]);

    const handleExportParams = useCallback(() => {
        let currentCfg;
        let sourceLabel;

        if (activeTab === -3) {
            currentCfg = symbolCompareConfig || configList[0] || {};
            sourceLabel = 'SymbolCompare';
        } else if (activeTab >= 0 && configList[activeTab]) {
            currentCfg = configList[activeTab];
            sourceLabel = (currentCfg.tabName || `Tab${activeTab + 1}`).replace(/\s/g, '');
        } else {
            addLog('⚠️ No configuration to export', 'warn');
            return;
        }

        const filename = exportParamsToJSON({
            config: currentCfg,
            sourceLabel,
            accountName: systemStatus?.account_name,
            strategyId: selectedStrategy?.id,
            paramNames: getStrategyParamNames()
        });

        if (filename) {
            setParamImportExportFeedback('exported');
            setTimeout(() => setParamImportExportFeedback(null), 2000);
            addLog(`📤 Exported parameters from ${sourceLabel}`, 'info');
        }
    }, [activeTab, configList, symbolCompareConfig, systemStatus, selectedStrategy, getStrategyParamNames, addLog]);

    const handleImportParams = useCallback(async (e) => {
        const file = e.target.files?.[0];
        if (!file) return;
        e.target.value = '';

        setParamImportExportFeedback('importing');
        setParamImportError('');

        try {
            const text = await readFileAsText(file);
            const result = parseImportedParams(text);

            if (!result.ok) {
                setParamImportError(result.error);
                setParamImportExportFeedback('error');
                setTimeout(() => setParamImportExportFeedback(null), 3000);
                addLog(`⚠️ ${result.error}`, 'error');
                return;
            }

            const data = result.data;

            if (activeTab === -3) {
                const baseConfig = symbolCompareConfig || configList[0] || {};
                setSymbolCompareConfig({ ...baseConfig, ...data.params });
                setIsSymbolCompareDirty(true);
            } else if (activeTab >= 0 && configList[activeTab]) {
                const newList = [...configList];
                newList[activeTab] = { ...newList[activeTab], ...data.params };
                setConfigList(newList);
                setIsDirty(true);
            }

            setParamImportExportFeedback('imported');
            setTimeout(() => setParamImportExportFeedback(null), 2000);
            const strategyInfo = data.strategy ? ` from "${data.strategy}"` : '';
            const sourceInfo = data.sourceTab ? ` (${data.sourceTab})` : '';
            addLog(`📥 Imported parameters${strategyInfo}${sourceInfo} (${Object.keys(data.params).length} fields)`, 'info');
        } catch (err) {
            setParamImportError(err.message);
            setParamImportExportFeedback('error');
            setTimeout(() => setParamImportExportFeedback(null), 3000);
            addLog(`⚠️ ${err.message}`, 'error');
        }
    }, [activeTab, configList, symbolCompareConfig, setConfigList, setSymbolCompareConfig, setIsDirty, setIsSymbolCompareDirty, addLog]);

    return {
        assetImportExportFeedback, assetImportError,
        paramImportExportFeedback, paramImportError,
        handleExportAssets, handleImportAssets,
        handleExportParams, handleImportParams
    };
};
