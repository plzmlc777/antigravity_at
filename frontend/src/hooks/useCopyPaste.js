import { useState, useCallback } from 'react';

/**
 * useCopyPaste - Strategy parameter and optimization settings copy/paste.
 */
export const useCopyPaste = ({
    configList, setConfigList, activeTab, parameterSchema,
    symbolCompareConfig, setSymbolCompareConfig,
    setIsDirty, setIsSymbolCompareDirty, addLog,
    extractParamNames
}) => {
    const [copiedParams, setCopiedParams] = useState(null);
    const [copyPasteFeedback, setCopyPasteFeedback] = useState(null);
    const [copiedOptSettings, setCopiedOptSettings] = useState(null);
    const [optCopyPasteFeedback, setOptCopyPasteFeedback] = useState(null);

    const getStrategyParamNames = useCallback(
        () => extractParamNames(parameterSchema),
        [extractParamNames, parameterSchema]
    );

    const handleCopyParams = useCallback(() => {
        let currentCfg;
        let sourceLabel;

        if (activeTab === -3) {
            currentCfg = symbolCompareConfig || configList[0] || {};
            sourceLabel = 'Symbol Compare';
        } else if (activeTab >= 0 && configList[activeTab]) {
            currentCfg = configList[activeTab];
            sourceLabel = currentCfg.tabName || `Tab ${activeTab + 1}`;
        } else {
            return;
        }

        if (!currentCfg) return;

        const paramsToCopy = {};
        const strategyParams = getStrategyParamNames();
        strategyParams.forEach(key => {
            if (key in currentCfg) {
                paramsToCopy[key] = currentCfg[key];
            }
        });

        setCopiedParams({
            params: paramsToCopy,
            sourceTab: sourceLabel,
            sourceSymbol: currentCfg.symbol || 'Multi',
            timestamp: Date.now()
        });

        setCopyPasteFeedback('copied');
        setTimeout(() => setCopyPasteFeedback(null), 2000);
        addLog(`📋 Parameters copied from ${sourceLabel}`, 'info');
    }, [activeTab, configList, symbolCompareConfig, getStrategyParamNames, addLog]);

    const handlePasteParams = useCallback(() => {
        if (!copiedParams) return;

        if (activeTab === -3) {
            const baseConfig = symbolCompareConfig || configList[0] || {};
            const newConfig = { ...baseConfig };
            Object.keys(copiedParams.params).forEach(key => {
                newConfig[key] = copiedParams.params[key];
            });
            setSymbolCompareConfig(newConfig);
            setIsSymbolCompareDirty(true);
            setCopyPasteFeedback('pasted');
            setTimeout(() => setCopyPasteFeedback(null), 2000);
            addLog(`📥 Parameters pasted from ${copiedParams.sourceTab} (${copiedParams.sourceSymbol})`, 'info');
            return;
        }

        if (activeTab < 0 || !configList[activeTab]) return;

        const newList = [...configList];
        const currentItem = { ...newList[activeTab] };
        Object.keys(copiedParams.params).forEach(key => {
            currentItem[key] = copiedParams.params[key];
        });
        newList[activeTab] = currentItem;
        setConfigList(newList);
        setIsDirty(true);
        setCopyPasteFeedback('pasted');
        setTimeout(() => setCopyPasteFeedback(null), 2000);
        addLog(`📥 Parameters pasted from ${copiedParams.sourceTab} (${copiedParams.sourceSymbol})`, 'info');
    }, [copiedParams, activeTab, configList, symbolCompareConfig, setConfigList, setSymbolCompareConfig, setIsDirty, setIsSymbolCompareDirty, addLog]);

    const handleCopyOptSettings = useCallback(() => {
        let currentCfg;
        let sourceLabel;

        if (activeTab === -3) {
            currentCfg = symbolCompareConfig || configList[0] || {};
            sourceLabel = 'Symbol Compare';
        } else if (activeTab >= 0 && configList[activeTab]) {
            currentCfg = configList[activeTab];
            sourceLabel = currentCfg.tabName || `Rank ${activeTab + 1}`;
        } else {
            return;
        }

        if (!currentCfg) return;

        const optEnabled = currentCfg.optEnabled || {};
        const optValues = currentCfg.optValues || {};
        const optCount = Object.values(optEnabled).filter(Boolean).length;

        setCopiedOptSettings({
            optEnabled,
            optValues,
            sourceTab: sourceLabel,
            timestamp: Date.now()
        });

        setOptCopyPasteFeedback('copied');
        setTimeout(() => setOptCopyPasteFeedback(null), 2000);
        addLog(`📋 Opt settings copied from ${sourceLabel} (${optCount} params)`, 'info');
    }, [activeTab, configList, symbolCompareConfig, addLog]);

    const handlePasteOptSettings = useCallback(() => {
        if (!copiedOptSettings) return;

        if (activeTab === -3) {
            const baseConfig = symbolCompareConfig || configList[0] || {};
            const newConfig = {
                ...baseConfig,
                optEnabled: { ...copiedOptSettings.optEnabled },
                optValues: { ...copiedOptSettings.optValues }
            };
            setSymbolCompareConfig(newConfig);
            setIsSymbolCompareDirty(true);
            setOptCopyPasteFeedback('pasted');
            setTimeout(() => setOptCopyPasteFeedback(null), 2000);
            const optCount = Object.values(copiedOptSettings.optEnabled).filter(Boolean).length;
            addLog(`📥 Opt settings pasted from ${copiedOptSettings.sourceTab} (${optCount} params)`, 'info');
            return;
        }

        if (activeTab < 0 || !configList[activeTab]) return;

        const newList = [...configList];
        const currentItem = {
            ...newList[activeTab],
            optEnabled: { ...copiedOptSettings.optEnabled },
            optValues: { ...copiedOptSettings.optValues }
        };
        newList[activeTab] = currentItem;
        setConfigList(newList);
        setIsDirty(true);
        setOptCopyPasteFeedback('pasted');
        setTimeout(() => setOptCopyPasteFeedback(null), 2000);
        const optCount = Object.values(copiedOptSettings.optEnabled).filter(Boolean).length;
        addLog(`📥 Opt settings pasted from ${copiedOptSettings.sourceTab} (${optCount} params)`, 'info');
    }, [copiedOptSettings, activeTab, configList, symbolCompareConfig, setConfigList, setSymbolCompareConfig, setIsDirty, setIsSymbolCompareDirty, addLog]);

    return {
        copiedParams, copyPasteFeedback,
        copiedOptSettings, optCopyPasteFeedback,
        handleCopyParams, handlePasteParams,
        handleCopyOptSettings, handlePasteOptSettings,
        getStrategyParamNames
    };
};
