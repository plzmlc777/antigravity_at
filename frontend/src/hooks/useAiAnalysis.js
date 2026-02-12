import { useState, useEffect, useCallback } from 'react';
import { getAiModels as apiGetAiModels, getAiKeyStatus, runAiAnalysis as apiRunAiAnalysis } from '../api/strategies';

/**
 * useAiAnalysis - AI model selection and optimization result analysis.
 */
export const useAiAnalysis = ({ heavyOptStatus, heavyOptTaskId, addLog }) => {
    const [aiAnalysisLoading, setAiAnalysisLoading] = useState(false);
    const [aiAnalysisResult, setAiAnalysisResult] = useState(null);
    const [showAiAnalysisModal, setShowAiAnalysisModal] = useState(false);
    const [aiModels, setAiModels] = useState([]);
    const [selectedAiModel, setSelectedAiModel] = useState('');

    const fetchAiModels = useCallback(async () => {
        try {
            const modelsData = await apiGetAiModels();
            setAiModels(modelsData.models || []);
            const statusData = await getAiKeyStatus();
            setSelectedAiModel(statusData.ai_model || modelsData.default || '');
        } catch (err) {
            console.error('Failed to fetch AI models:', err);
        }
    }, []);

    useEffect(() => {
        fetchAiModels();
    }, [fetchAiModels]);

    const runAiAnalysis = useCallback(async (modelOverride = null) => {
        if (!heavyOptStatus?.csv_file) {
            addLog('No CSV file available for AI analysis', 'error');
            return;
        }

        setAiAnalysisLoading(true);
        setAiAnalysisResult(null);
        const modelToUse = modelOverride || selectedAiModel;
        const modelName = aiModels.find(m => m.id === modelToUse)?.name || modelToUse;
        addLog(`Starting AI analysis with ${modelName}...`, 'info');

        try {
            const analysisData = await apiRunAiAnalysis({
                csv_filename: heavyOptStatus.csv_file,
                strategy_id: 'DipMartingaleStrategy',
                user_question: null,
                model: modelToUse || undefined
            });

            setAiAnalysisResult(analysisData);
            setShowAiAnalysisModal(true);
            addLog(`AI analysis completed: ${analysisData.total_rows?.toLocaleString()} rows analyzed`, 'success');
        } catch (err) {
            console.error('AI analysis error:', err);
            const msg = err.response?.data?.detail || err.message;
            addLog(`AI analysis failed: ${msg}`, 'error');
            setAiAnalysisResult({ error: msg });
        } finally {
            setAiAnalysisLoading(false);
        }
    }, [heavyOptStatus, selectedAiModel, aiModels, addLog]);

    return {
        aiAnalysisLoading, aiAnalysisResult, setAiAnalysisResult,
        showAiAnalysisModal, setShowAiAnalysisModal,
        aiModels, selectedAiModel, setSelectedAiModel,
        fetchAiModels, runAiAnalysis
    };
};
