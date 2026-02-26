import { useState, useCallback } from 'react';
import { recalculateOptimizationScores } from '../api/strategies';
import { normalizeStats } from '../config/statsConfig';
import { coerceConfigTypes } from '../utils/strategyParamUtils';
import { SCORE_WEIGHT_PRESETS } from '../constants/strategies';

/**
 * useScoreWeights - Per-tab score weight management with profile persistence.
 */
export const useScoreWeights = ({
    activeTab, configList, setConfigList,
    symbolCompareConfig, setSymbolCompareConfig,
    completedOptTaskId, heavyOptTaskId,
    currentConfig,
    optResults, setOptResults,
    selectedStrategy, savedSymbols, addLog
}) => {
    const [scoreWeightsMap, setScoreWeightsMap] = useState({});
    const scoreWeights = scoreWeightsMap[activeTab] || SCORE_WEIGHT_PRESETS.balanced;
    const [isRecalculating, setIsRecalculating] = useState(false);
    const [showWeightPanel, setShowWeightPanel] = useState(false);

    // Persist score weights to profile config (triggers dirty state)
    const persistScoreWeights = useCallback((newWeights) => {
        if (activeTab >= 0) {
            setConfigList(prev => {
                const updated = [...prev];
                if (updated[activeTab]) {
                    updated[activeTab] = { ...updated[activeTab], score_weights: newWeights };
                }
                return updated;
            });
        } else if (activeTab === -3) {
            setSymbolCompareConfig(prev => prev ? { ...prev, score_weights: newWeights } : prev);
        }
    }, [activeTab, setConfigList, setSymbolCompareConfig]);

    const handleWeightChange = useCallback((key, value) => {
        const current = scoreWeightsMap[activeTab] || SCORE_WEIGHT_PRESETS.balanced;
        const newWeights = { ...current, [key]: parseFloat(value) || 0 };
        setScoreWeightsMap(prev => ({ ...prev, [activeTab]: newWeights }));
        persistScoreWeights(newWeights);
    }, [activeTab, scoreWeightsMap, persistScoreWeights]);

    const applyWeightPreset = useCallback((presetName) => {
        const newWeights = SCORE_WEIGHT_PRESETS[presetName];
        setScoreWeightsMap(prev => ({ ...prev, [activeTab]: newWeights }));
        persistScoreWeights(newWeights);
    }, [activeTab, persistScoreWeights]);

    const recalculateScores = useCallback(async () => {
        // Try in-memory task IDs first, then fall back to profile-persisted task ID
        const taskId = completedOptTaskId || heavyOptTaskId || currentConfig?.lastOptTaskId;
        if (!taskId) {
            addLog('No optimization task to recalculate (run optimization first)', 'error');
            return;
        }

        setIsRecalculating(true);
        try {
            addLog(`Recalculating scores with weights: Return=${scoreWeights.return_weight}, Sharpe=${scoreWeights.sharpe_weight}, Stability=${scoreWeights.stability_weight}, MDD=${scoreWeights.mdd_weight}`, 'info');

            const response = await recalculateOptimizationScores(taskId, scoreWeights, 50);

            if (response && response.results) {
                const schema = selectedStrategy?.parameter_schema;
                const formatted = response.results.map((item, idx) => {
                    const stats = normalizeStats(item);
                    const typedCfg = coerceConfigTypes(item.config, schema);
                    return {
                        ...typedCfg,
                        ...stats,
                        symbol: item.symbol || item.config?.symbol || '',
                        symbolName: savedSymbols?.find(s => s.code === (item.symbol || item.config?.symbol))?.name || '',
                        return: stats.total_return,
                        cycles: stats.total_cycles,
                        score: item.score,
                        full_config: typedCfg,
                        rank: item.rank > 0 ? item.rank : (idx + 1)
                    };
                });

                setOptResults(formatted);
                addLog(`Recalculated! Top 50 from ${response.total_rows} total results`, 'success');
            }
        } catch (err) {
            console.error('Recalculate error:', err);
            addLog(`Recalculation failed: ${err.response?.data?.detail || err.message}`, 'error');
        } finally {
            setIsRecalculating(false);
        }
    }, [completedOptTaskId, heavyOptTaskId, currentConfig?.lastOptTaskId, scoreWeights, selectedStrategy, savedSymbols, setOptResults, addLog]);

    // Initialize scoreWeightsMap from loaded profile data
    const initScoreWeightsFromProfile = useCallback((configs, symCompareConfig) => {
        const restoredWeights = {};
        if (configs) {
            configs.forEach((cfg, idx) => {
                if (cfg?.score_weights) restoredWeights[idx] = cfg.score_weights;
            });
        }
        if (symCompareConfig?.score_weights) {
            restoredWeights[-3] = symCompareConfig.score_weights;
        }
        setScoreWeightsMap(restoredWeights);
    }, []);

    return {
        scoreWeightsMap, setScoreWeightsMap,
        scoreWeights, isRecalculating, showWeightPanel, setShowWeightPanel,
        handleWeightChange, applyWeightPreset, recalculateScores,
        initScoreWeightsFromProfile
    };
};
