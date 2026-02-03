import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { getStrategyConfigs, syncStrategyConfigsSelective } from '../api/client';
import { createConfigScope, isValidScope } from '../types/ConfigScope';

/**
 * useStrategyConfig - 전략 설정 로딩을 위한 중앙 집중화된 커스텀 훅
 *
 * 핵심 목적:
 * 1. ConfigScope(accountId + strategyId) 변경 시 자동으로 설정을 다시 로드
 * 2. 로딩/에러 상태를 한 곳에서 관리
 * 3. DB → UI 데이터 변환 로직 중앙 집중화
 * 4. 계좌 중심 전환 시 의존성 관리 용이
 */
export const useStrategyConfig = ({
    selectedStrategy,
    accountId = null,
    defaultConfig = {},
    generateUUID = () => crypto.randomUUID(),
}) => {
    const [configList, setConfigList] = useState([]);
    const [isLoaded, setIsLoaded] = useState(false);
    const [needsInit, setNeedsInit] = useState(false);
    const [error, setError] = useState(null);
    const [saveStatus, setSaveStatus] = useState('idle');

    const isMountedRef = useRef(true);

    // ConfigScope 생성 - accountId와 strategyId를 항상 함께 관리
    const scope = useMemo(() => {
        return createConfigScope(accountId, selectedStrategy?.id);
    }, [accountId, selectedStrategy?.id]);

    // Refs for stable references
    const selectedStrategyRef = useRef(selectedStrategy);
    const scopeRef = useRef(scope);
    const defaultConfigRef = useRef(defaultConfig);

    // Update refs when values change
    useEffect(() => {
        selectedStrategyRef.current = selectedStrategy;
        scopeRef.current = scope;
        defaultConfigRef.current = defaultConfig;
    }, [selectedStrategy, scope, defaultConfig]);

    /**
     * 동적 기본 설정 생성
     */
    const getDynamicDefaultConfig = useCallback(() => {
        let dynamicDefault = { ...defaultConfigRef.current };
        const schema = selectedStrategyRef.current?.parameter_schema;

        if (schema?.fields && schema.fields.length > 0) {
            schema.fields.forEach(field => {
                const key = field.key || field.name;
                if (field.default !== undefined) {
                    dynamicDefault[key] = field.default;
                }
            });
        }

        return dynamicDefault;
    }, []);

    /**
     * DB 응답을 UI Config 형식으로 변환
     */
    const transformDbToUiConfig = useCallback((dbConfig) => {
        const dynamicDefault = getDynamicDefaultConfig();
        let configData = dbConfig.config_json || {};
        let mergedCfg = { ...dynamicDefault, ...configData };

        mergedCfg.rank = dbConfig.rank;
        mergedCfg.is_active = dbConfig.is_active === false ? false : true;
        mergedCfg.tabName = dbConfig.tab_name;
        mergedCfg.uuid = dbConfig.tab_id;

        Object.keys(dynamicDefault).forEach(key => {
            if (key === 'from_date' || key === 'uuid') return;
            const val = mergedCfg[key];
            const defaultVal = dynamicDefault[key];
            if ((val === "" || val === null || val === undefined) && defaultVal !== "") {
                mergedCfg[key] = defaultVal;
            }
        });

        if (!mergedCfg.uuid) mergedCfg.uuid = generateUUID();

        return mergedCfg;
    }, [getDynamicDefaultConfig, generateUUID]);

    /**
     * UI Config를 DB 저장 형식으로 변환
     * @param {Object} uiConfig - UI 설정 객체
     * @param {number} index - 탭 인덱스
     * @param {ConfigScope} configScope - 계좌 + 전략 컨텍스트 (선택적, 없으면 현재 scope 사용)
     */
    const transformUiToDbConfig = useCallback((uiConfig, index, configScope = null) => {
        const currentScope = configScope || scopeRef.current;
        return {
            tab_id: uiConfig.uuid,
            account_id: currentScope.accountId,
            strategy_id: currentScope.strategyId,
            rank: index,
            is_active: uiConfig.is_active !== false,
            tab_name: uiConfig.tabName || `Rank ${index + 1}`,
            config_json: uiConfig
        };
    }, []);

    /**
     * 기본 탭 초기화
     */
    const initDefaultList = useCallback(() => {
        console.log("[useStrategyConfig] Creating default Rank 1 tab");
        const defaultTab = {
            ...getDynamicDefaultConfig(),
            is_active: true,
            tabName: "Rank 1",
            uuid: generateUUID(),
            optEnabled: {},
            optValues: {}
        };
        setConfigList([defaultTab]);
    }, [getDynamicDefaultConfig, generateUUID]);

    /**
     * 설정 저장
     */
    const saveConfigs = useCallback(async (configs = configList) => {
        const currentScope = scopeRef.current;

        if (!isValidScope(currentScope) || configs.length === 0) {
            console.warn("[useStrategyConfig] Cannot save: invalid scope or empty configs", currentScope);
            return false;
        }

        console.log(`[useStrategyConfig] Saving ${configs.length} configs for scope:`, currentScope);
        setSaveStatus('saving');

        try {
            const configsToSave = configs.map((cfg, index) =>
                transformUiToDbConfig(cfg, index, currentScope)
            );

            await syncStrategyConfigsSelective(currentScope.strategyId, configsToSave, true);

            setSaveStatus('saved');
            console.log("[useStrategyConfig] Configs saved successfully");

            setTimeout(() => {
                if (isMountedRef.current) setSaveStatus('idle');
            }, 2000);

            return true;
        } catch (e) {
            console.error("[useStrategyConfig] Failed to save configs:", e);
            setSaveStatus('error');
            setError(e);
            return false;
        }
    }, [configList, transformUiToDbConfig]);

    /**
     * 핵심 useEffect - ConfigScope 변경 시 설정 로드
     */
    useEffect(() => {
        isMountedRef.current = true;

        // ConfigScope 유효성 검사
        if (!scope.strategyId) {
            // 전략이 없으면 대기
            return;
        }

        // accountId가 없으면 디폴트로 초기화
        if (!scope.accountId) {
            console.log("[useStrategyConfig] No accountId in scope, initializing with default config");
            const defaultTab = {
                ...getDynamicDefaultConfig(),
                is_active: true,
                tabName: "Rank 1",
                uuid: generateUUID(),
                optEnabled: {},
                optValues: {}
            };
            setConfigList([defaultTab]);
            setNeedsInit(true);
            setIsLoaded(true);
            return;
        }

        // DB에서 설정 로드
        const loadConfigs = async () => {
            console.log(`[useStrategyConfig] Loading configs for scope:`, scope);
            setIsLoaded(false);
            setError(null);

            try {
                const savedList = await getStrategyConfigs(scope.strategyId);

                if (!isMountedRef.current) return;

                if (savedList && savedList.length > 0) {
                    console.log("[useStrategyConfig] API response:", savedList.length, "configs");
                    const migratedList = savedList.map(transformDbToUiConfig);
                    setConfigList(migratedList);
                } else {
                    console.log("[useStrategyConfig] DB empty, initializing with default config");
                    const defaultTab = {
                        ...getDynamicDefaultConfig(),
                        is_active: true,
                        tabName: "Rank 1",
                        uuid: generateUUID(),
                        optEnabled: {},
                        optValues: {}
                    };
                    setConfigList([defaultTab]);
                    setNeedsInit(true);
                }
            } catch (e) {
                console.error("[useStrategyConfig] Failed to load configs:", e);
                setError(e);
                if (isMountedRef.current) {
                    console.log("[useStrategyConfig] API error, initializing with default config");
                    const defaultTab = {
                        ...getDynamicDefaultConfig(),
                        is_active: true,
                        tabName: "Rank 1",
                        uuid: generateUUID(),
                        optEnabled: {},
                        optValues: {}
                    };
                    setConfigList([defaultTab]);
                    setNeedsInit(true);
                }
            } finally {
                if (isMountedRef.current) setIsLoaded(true);
            }
        };

        loadConfigs();

        return () => {
            isMountedRef.current = false;
        };
    }, [scope, transformDbToUiConfig, getDynamicDefaultConfig, generateUUID]);

    return {
        // State
        configList,
        setConfigList,
        isLoaded,
        needsInit,
        setNeedsInit,
        error,
        saveStatus,

        // ConfigScope
        scope,  // 현재 scope 노출

        // Actions
        saveConfigs,
        reloadConfigs: () => {},
        initDefaultList,

        // Transformers
        getDynamicDefaultConfig,
        transformDbToUiConfig,
        transformUiToDbConfig
    };
};

export default useStrategyConfig;
