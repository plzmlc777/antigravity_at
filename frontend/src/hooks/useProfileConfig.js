import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { getProfiles, getProfile, createProfile, updateProfile, deleteProfile, getAccountPreferences, updateLastSelectedProfile } from '../api/client';
import { STORAGE_KEYS } from '../constants/strategies';

// ═══════════════════════════════════════════════════════════════════════════════
// localStorage Draft Utilities
// ═══════════════════════════════════════════════════════════════════════════════
const getDraftKey = (profileId) => `${STORAGE_KEYS.DRAFT_PREFIX}${profileId}`;
const DRAFT_MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000; // 7 days

/**
 * useProfileConfig - Profile-centric strategy configuration hook
 *
 * Replaces useStrategyConfig with profile-based storage.
 * Profiles are the single source of truth for strategy configurations.
 *
 * Key features:
 * 1. Profile list management (load, select, create, update, delete)
 * 2. configList extracted from selected profile's rank_configs
 * 3. Dirty state tracking (current vs original)
 * 4. Backward compatible interface with useStrategyConfig
 */
export const useProfileConfig = ({
    selectedStrategy = null,
    defaultConfig = {},
    generateUUID = () => crypto.randomUUID(),
    onLog = null, // Optional callback for logging: (message, level) => void
    accountId = null, // Active account ID for backward compatibility
}) => {
    // Ref to hold the latest onLog callback
    const onLogRef = useRef(onLog);
    onLogRef.current = onLog;

    // Helper to log messages (stable reference)
    const log = useCallback((message, level = 'info') => {
        console.log(`[useProfileConfig] ${message}`);
        if (onLogRef.current) onLogRef.current(`[Profile] ${message}`, level);
    }, []);

    // Profile List State
    const [profiles, setProfiles] = useState([]);
    const [selectedProfileId, setSelectedProfileId] = useState(null);
    const [selectedProfile, setSelectedProfile] = useState(null);

    // Config State (from selected profile)
    const [configList, setConfigList] = useState([]);
    const [originalConfigList, setOriginalConfigList] = useState([]); // For dirty checking

    // Symbol Compare Settings (from profile)
    const [symbolCompareSettings, setSymbolCompareSettings] = useState(null);
    const [originalSymbolCompareSettings, setOriginalSymbolCompareSettings] = useState(null);

    // UI State
    const [isLoaded, setIsLoaded] = useState(false);
    const [isProfilesLoading, setIsProfilesLoading] = useState(true);
    const [error, setError] = useState(null);
    const [saveStatus, setSaveStatus] = useState('idle'); // idle | saving | saved | error

    // Profile metadata state (for editing)
    const [profileMeta, setProfileMeta] = useState({
        name: '',
        description: '',
        strategy_name: '',
        execution_mode: 'parallel',
        initial_capital: 10000000,
        is_paper: true,
        rank_weights: null
    });
    const [originalProfileMeta, setOriginalProfileMeta] = useState(null);

    const isMountedRef = useRef(true);
    const selectedStrategyRef = useRef(selectedStrategy);
    const defaultConfigRef = useRef(defaultConfig);

    // Update refs
    useEffect(() => {
        selectedStrategyRef.current = selectedStrategy;
        defaultConfigRef.current = defaultConfig;
    }, [selectedStrategy, defaultConfig]);

    // Backward compatible scope object (for useStrategyConfig compatibility)
    const scope = useMemo(() => ({
        strategyId: profileMeta.strategy_name || selectedStrategy?.id || null,
        accountId: accountId // Use provided accountId for backward compatibility
    }), [profileMeta.strategy_name, selectedStrategy?.id, accountId]);

    /**
     * Generate dynamic default config from strategy schema
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
     * Create a default empty rank config
     */
    const createDefaultRankConfig = useCallback((rank = 0) => {
        return {
            ...getDynamicDefaultConfig(),
            rank,
            is_active: true,
            tabName: `Rank ${rank + 1}`,
            uuid: generateUUID(),
            optEnabled: {},
            optValues: {},
            selected_version_id: null // Explicitly reset version to Custom
        };
    }, [getDynamicDefaultConfig, generateUUID]);

    /**
     * Transform profile's rank_configs to UI configList format
     */
    const transformProfileToConfigList = useCallback((profile) => {
        if (!profile?.rank_configs || profile.rank_configs.length === 0) {
            return [createDefaultRankConfig(0)];
        }

        const dynamicDefault = getDynamicDefaultConfig();

        // Get valid parameter names from strategy schema for sanitization
        const schema = selectedStrategyRef.current?.parameter_schema;
        const validParamNames = new Set(
            schema?.fields?.map(f => f.key || f.name) || []
        );

        return profile.rank_configs.map((rankCfg, index) => {
            // Merge with defaults
            const merged = { ...dynamicDefault, ...rankCfg };

            // Ensure required fields
            if (!merged.uuid) merged.uuid = generateUUID();
            if (merged.rank === undefined) merged.rank = index;
            if (merged.is_active === undefined) merged.is_active = true;
            if (!merged.tabName) merged.tabName = `Rank ${index + 1}`;

            // Sanitize optEnabled: remove keys that are not valid strategy parameter names
            if (merged.optEnabled && validParamNames.size > 0) {
                const sanitized = {};
                let hadInvalid = false;
                for (const [key, val] of Object.entries(merged.optEnabled)) {
                    if (validParamNames.has(key)) {
                        sanitized[key] = val;
                    } else {
                        hadInvalid = true;
                        console.warn(`[useProfileConfig] Removed invalid optEnabled key: '${key}' in ${merged.tabName}`);
                    }
                }
                if (hadInvalid) {
                    merged.optEnabled = sanitized;
                }
            }

            return merged;
        });
    }, [getDynamicDefaultConfig, createDefaultRankConfig, generateUUID]);

    /**
     * Transform UI configList to profile's rank_configs format
     */
    const transformConfigListToRankConfigs = useCallback((configs) => {
        return configs.map((cfg, index) => ({
            ...cfg,
            rank: index
        }));
    }, []);

    /**
     * Transform UI config to DB format (for legacy syncStrategyConfigsSelective API)
     * @param {Object} uiConfig - UI config object
     * @param {number} index - Tab index
     */
    const transformUiToDbConfig = useCallback((uiConfig, index) => {
        return {
            tab_id: uiConfig.uuid,
            account_id: scope.accountId,
            strategy_id: scope.strategyId,
            rank: index,
            is_active: uiConfig.is_active !== false,
            tab_name: uiConfig.tabName || `Rank ${index + 1}`,
            config_json: uiConfig
        };
    }, [scope]);

    /**
     * Check if there are unsaved changes
     */
    const isDirty = useMemo(() => {
        if (!originalConfigList || originalConfigList.length === 0) {
            return configList.length > 0;
        }

        // Compare configList
        const configChanged = JSON.stringify(configList) !== JSON.stringify(originalConfigList);

        // Compare profile metadata
        const metaChanged = originalProfileMeta
            ? JSON.stringify(profileMeta) !== JSON.stringify(originalProfileMeta)
            : false;

        // Compare Symbol Compare settings
        const symbolCompareChanged = JSON.stringify(symbolCompareSettings) !== JSON.stringify(originalSymbolCompareSettings);

        return configChanged || metaChanged || symbolCompareChanged;
    }, [configList, originalConfigList, profileMeta, originalProfileMeta, symbolCompareSettings, originalSymbolCompareSettings]);

    // ═══════════════════════════════════════════════════════════════════════════
    // localStorage Draft Functions (must be declared before auto-save useEffect)
    // ═══════════════════════════════════════════════════════════════════════════

    /**
     * Save draft to localStorage (auto-called on state changes)
     */
    const saveDraft = useCallback((profileId, configs, meta, symbolCompare) => {
        if (!profileId) return;
        try {
            const draft = {
                configList: configs,
                profileMeta: meta,
                symbolCompareSettings: symbolCompare,
                timestamp: Date.now()
            };
            localStorage.setItem(getDraftKey(profileId), JSON.stringify(draft));
        } catch (e) {
            console.warn('[useProfileConfig] Failed to save draft:', e);
        }
    }, []);

    /**
     * Load draft from localStorage (returns null if expired or not found)
     */
    const loadDraft = useCallback((profileId) => {
        if (!profileId) return null;
        try {
            const raw = localStorage.getItem(getDraftKey(profileId));
            if (!raw) return null;

            const draft = JSON.parse(raw);

            // Expiration check (7 days)
            if (Date.now() - draft.timestamp > DRAFT_MAX_AGE_MS) {
                localStorage.removeItem(getDraftKey(profileId));
                console.log('[useProfileConfig] Draft expired, removed:', profileId);
                return null;
            }

            return draft;
        } catch (e) {
            console.warn('[useProfileConfig] Failed to load draft:', e);
            localStorage.removeItem(getDraftKey(profileId));
            return null;
        }
    }, []);

    /**
     * Clear draft from localStorage
     */
    const clearDraft = useCallback((profileId) => {
        if (!profileId) return;
        try {
            localStorage.removeItem(getDraftKey(profileId));
            console.log('[useProfileConfig] Draft cleared:', profileId);
        } catch (e) {
            console.warn('[useProfileConfig] Failed to clear draft:', e);
        }
    }, []);

    // ═══════════════════════════════════════════════════════════════════════════
    // Auto-save Draft to localStorage (300ms debounce)
    // ═══════════════════════════════════════════════════════════════════════════
    const draftTimerRef = useRef(null);

    useEffect(() => {
        // Only auto-save when dirty and profile is selected
        if (!isDirty || !selectedProfileId || !isLoaded) return;

        // Clear previous timer
        if (draftTimerRef.current) clearTimeout(draftTimerRef.current);

        draftTimerRef.current = setTimeout(() => {
            saveDraft(selectedProfileId, configList, profileMeta, symbolCompareSettings);
        }, 300);

        return () => {
            if (draftTimerRef.current) clearTimeout(draftTimerRef.current);
        };
    }, [isDirty, selectedProfileId, isLoaded, configList, profileMeta, symbolCompareSettings, saveDraft]);

    /**
     * Load all profiles and optionally find last used profile ID
     * Returns { profiles, autoSelectedId } for init() to handle state setting
     */
    const loadProfiles = useCallback(async (strategyFilter = '', autoSelectLast = false) => {
        setIsProfilesLoading(true);
        log(`Loading profiles (autoSelectLast=${autoSelectLast})...`);
        try {
            const result = await getProfiles(strategyFilter);
            if (!isMountedRef.current) return { profiles: [] };

            const profileList = result.data || [];
            setProfiles(profileList);
            log(`Loaded ${profileList.length} profiles`);

            // Find last used profile ID if requested
            if (autoSelectLast && profileList.length > 0) {
                try {
                    const prefs = await getAccountPreferences();
                    const lastProfileId = prefs?.last_selected_profile_id;
                    log(`DB last_selected_profile_id: ${lastProfileId || 'null'}`);

                    if (lastProfileId) {
                        const targetProfile = profileList.find(p => p.id === lastProfileId);
                        if (targetProfile) {
                            log(`Found last used profile: ${targetProfile.name}`, 'success');
                            return { profiles: profileList, autoSelectedId: lastProfileId };
                        } else {
                            log(`Profile ID ${lastProfileId} not found in list`, 'error');
                        }
                    }

                    // Fallback: check localStorage
                    const localStorageProfileId = localStorage.getItem('lastSelectedProfileId');
                    log(`localStorage lastSelectedProfileId: ${localStorageProfileId || 'null'}`);
                    if (localStorageProfileId) {
                        const targetProfile = profileList.find(p => p.id === localStorageProfileId);
                        if (targetProfile) {
                            log(`Found profile from localStorage: ${targetProfile.name}`, 'success');
                            // Migrate to DB
                            updateLastSelectedProfile(localStorageProfileId).catch(e =>
                                log(`Failed to migrate to DB: ${e.message}`, 'error')
                            );
                            return { profiles: profileList, autoSelectedId: localStorageProfileId };
                        }
                    }
                } catch (e) {
                    log(`Failed to load preferences: ${e.message}`, 'error');
                }
            }

            return { profiles: profileList };
        } catch (e) {
            log(`Failed to load profiles: ${e.message}`, 'error');
            setError(e);
            return { profiles: [] };
        } finally {
            if (isMountedRef.current) {
                setIsProfilesLoading(false);
            }
        }
    }, [log]);

    /**
     * Select and load a profile
     */
    const selectProfile = useCallback(async (profileId) => {
        if (!profileId) {
            // Clear selection
            setSelectedProfileId(null);
            setSelectedProfile(null);
            setConfigList([]);
            setOriginalConfigList([]);
            setSymbolCompareSettings(null);
            setOriginalSymbolCompareSettings(null);
            setProfileMeta({
                name: '',
                description: '',
                strategy_name: selectedStrategyRef.current?.id || '',
                execution_mode: 'parallel',
                initial_capital: 10000000,
                is_paper: true,
                rank_weights: null
            });
            setOriginalProfileMeta(null);
            setIsLoaded(true);
            return;
        }

        setIsLoaded(false);
        try {
            const profile = await getProfile(profileId);
            if (!isMountedRef.current) return;

            setSelectedProfileId(profileId);
            setSelectedProfile(profile);

            // Save last selected profile to DB and localStorage
            localStorage.setItem('lastSelectedProfileId', profileId);
            updateLastSelectedProfile(profileId).catch(e =>
                console.warn('[useProfileConfig] Failed to save last selected profile:', e)
            );

            // Extract configList from rank_configs
            const configs = transformProfileToConfigList(profile);
            setConfigList(configs);
            setOriginalConfigList(JSON.parse(JSON.stringify(configs))); // Deep copy

            // Set profile metadata
            const meta = {
                name: profile.name || '',
                description: profile.description || '',
                strategy_name: profile.strategy_name || '',
                execution_mode: profile.execution_mode || 'parallel',
                initial_capital: profile.initial_capital || 10000000,
                is_paper: profile.is_paper !== false,
                rank_weights: profile.rank_weights || null
            };
            setProfileMeta(meta);
            setOriginalProfileMeta(JSON.parse(JSON.stringify(meta)));

            // Set Symbol Compare settings
            // If null, initialize from Rank 0 for independent Symbol Compare tab settings
            let compareSettings = profile.symbol_compare_settings;
            // Migration: unwrap legacy nested structure {config: {...}, selectedSymbols, results, ...}
            if (compareSettings && compareSettings.config && !compareSettings.symbol && !compareSettings.interval) {
                const { config: nestedConfig, ...rest } = compareSettings;
                compareSettings = { ...nestedConfig, ...rest };
                console.log('[useProfileConfig] Migrated legacy nested symbolCompareSettings to flat structure');
            }
            if (!compareSettings && configs.length > 0) {
                const rank0 = configs[0];
                compareSettings = {
                    ...rank0,
                    optEnabled: rank0.optEnabled || {},
                    optValues: rank0.optValues || {},
                    tabName: 'Symbol Compare'
                };
                console.log('[useProfileConfig] Initialized symbolCompareSettings from Rank 0');
            }
            setOriginalSymbolCompareSettings(compareSettings ? JSON.parse(JSON.stringify(compareSettings)) : null);

            // Check for localStorage draft and apply if exists
            const draft = loadDraft(profileId);
            if (draft) {
                console.log('[useProfileConfig] Found draft for profile, applying...');
                if (draft.configList) setConfigList(draft.configList);
                if (draft.profileMeta) setProfileMeta(draft.profileMeta);
                if (draft.symbolCompareSettings !== undefined) setSymbolCompareSettings(draft.symbolCompareSettings);
                // Original values stay as DB values → isDirty will be true
            } else {
                setSymbolCompareSettings(compareSettings || null);
            }

            console.log('[useProfileConfig] Profile loaded:', profile.name, 'with', configs.length, 'ranks', 'symbolCompare:', !!compareSettings, 'hasDraft:', !!draft);
        } catch (e) {
            console.error('[useProfileConfig] Failed to load profile:', e);
            setError(e);
        } finally {
            if (isMountedRef.current) {
                setIsLoaded(true);
            }
        }
    }, [transformProfileToConfigList, loadDraft]);

    /**
     * Create a new profile (for New Profile wizard)
     */
    const initNewProfile = useCallback((strategyId) => {
        setSelectedProfileId(null);
        setSelectedProfile(null);

        const defaultRank = createDefaultRankConfig(0);
        setConfigList([defaultRank]);
        setOriginalConfigList([]);

        // Clear Symbol Compare settings for new profile
        setSymbolCompareSettings(null);
        setOriginalSymbolCompareSettings(null);

        setProfileMeta({
            name: '',
            description: '',
            strategy_name: strategyId,
            execution_mode: 'parallel',
            initial_capital: 10000000,
            is_paper: true,
            rank_weights: null
        });
        setOriginalProfileMeta(null);
        setIsLoaded(true);

        console.log('[useProfileConfig] New profile initialized for strategy:', strategyId);
    }, [createDefaultRankConfig]);

    /**
     * Create and save a new profile with default config (atomic operation)
     * Unlike initNewProfile + saveProfileAs, this avoids React async state issues
     */
    const createNewProfile = useCallback(async (name, description, strategyId) => {
        setSaveStatus('saving');

        try {
            // Create default rank config directly (not from state)
            const defaultRank = createDefaultRankConfig(0);

            const profileData = {
                name,
                description: description || '',
                strategy_name: strategyId,
                rank_configs: [defaultRank],
                execution_mode: 'parallel',
                rank_weights: null,
                initial_capital: 10000000,
                is_paper: true
            };

            const result = await createProfile(profileData);
            console.log('[useProfileConfig] New profile created:', name, result);

            // Update local state
            if (result.data?.id) {
                setSelectedProfileId(result.data.id);
                setSelectedProfile(result.data);
                setConfigList([defaultRank]);
                setOriginalConfigList(JSON.parse(JSON.stringify([defaultRank])));
                setProfileMeta({
                    name,
                    description: description || '',
                    strategy_name: strategyId,
                    execution_mode: 'parallel',
                    initial_capital: 10000000,
                    is_paper: true,
                    rank_weights: null
                });
                setOriginalProfileMeta({
                    name,
                    description: description || '',
                    strategy_name: strategyId,
                    execution_mode: 'parallel',
                    initial_capital: 10000000,
                    is_paper: true,
                    rank_weights: null
                });
            }

            setSaveStatus('saved');
            await loadProfiles();

            setTimeout(() => {
                if (isMountedRef.current) setSaveStatus('idle');
            }, 2000);

            return result;
        } catch (e) {
            console.error('[useProfileConfig] Failed to create new profile:', e);
            setSaveStatus('error');
            setError(e);
            throw e;
        }
    }, [createDefaultRankConfig, loadProfiles]);

    /**
     * Save current profile (update existing or create new)
     */
    const saveProfile = useCallback(async (name = null) => {
        setSaveStatus('saving');

        try {
            // Ensure symbolCompareSettings is initialized from Rank 0 if null
            let effectiveSymbolCompareSettings = symbolCompareSettings;
            if (!effectiveSymbolCompareSettings && configList.length > 0) {
                const rank0 = configList[0];
                effectiveSymbolCompareSettings = {
                    ...rank0,
                    optEnabled: rank0.optEnabled || {},
                    optValues: rank0.optValues || {},
                    tabName: 'Symbol Compare'
                };
                console.log('[useProfileConfig] Initialized symbolCompareSettings from Rank 0 before save');
                // Update state so UI reflects this
                setSymbolCompareSettings(effectiveSymbolCompareSettings);
            }

            const profileData = {
                name: name || profileMeta.name,
                description: profileMeta.description,
                strategy_name: profileMeta.strategy_name,
                rank_configs: transformConfigListToRankConfigs(configList),
                execution_mode: profileMeta.execution_mode,
                rank_weights: profileMeta.rank_weights,
                initial_capital: profileMeta.initial_capital,
                is_paper: profileMeta.is_paper,
                symbol_compare_settings: effectiveSymbolCompareSettings
            };

            let result;
            if (selectedProfileId) {
                // Update existing
                result = await updateProfile(selectedProfileId, profileData);
                console.log('[useProfileConfig] Profile updated:', result);
                // Update selectedProfile with latest data
                setSelectedProfile(prev => prev ? { ...prev, ...profileData } : null);
            } else {
                // Create new
                if (!profileData.name) {
                    throw new Error('Profile name is required');
                }
                result = await createProfile(profileData);
                console.log('[useProfileConfig] Profile created:', result);

                // Update selected profile ID and object
                if (result.data?.id) {
                    setSelectedProfileId(result.data.id);
                    setSelectedProfile({ ...profileData, id: result.data.id });

                    // Force new reference for symbolCompareSettings to trigger React re-render
                    if (symbolCompareSettings) {
                        setSymbolCompareSettings(JSON.parse(JSON.stringify(symbolCompareSettings)));
                    }
                }
            }

            // Update original state (no longer dirty)
            setOriginalConfigList(JSON.parse(JSON.stringify(configList)));
            setOriginalProfileMeta(JSON.parse(JSON.stringify(profileMeta)));
            setOriginalSymbolCompareSettings(symbolCompareSettings ? JSON.parse(JSON.stringify(symbolCompareSettings)) : null);

            // Clear localStorage draft (no longer needed after DB save)
            clearDraft(selectedProfileId || result?.data?.id);

            setSaveStatus('saved');

            // Refresh profiles list
            await loadProfiles();

            setTimeout(() => {
                if (isMountedRef.current) setSaveStatus('idle');
            }, 2000);

            return result;
        } catch (e) {
            console.error('[useProfileConfig] Failed to save profile:', e);
            setSaveStatus('error');
            setError(e);
            throw e;
        }
    }, [selectedProfileId, profileMeta, configList, symbolCompareSettings, transformConfigListToRankConfigs, loadProfiles, clearDraft]);

    /**
     * Save as new profile (always creates new)
     */
    const saveProfileAs = useCallback(async (newName, newDescription = '') => {
        setSaveStatus('saving');

        try {
            // Ensure symbolCompareSettings is initialized from Rank 0 if null
            let effectiveSymbolCompareSettings = symbolCompareSettings;
            if (!effectiveSymbolCompareSettings && configList.length > 0) {
                const rank0 = configList[0];
                effectiveSymbolCompareSettings = {
                    ...rank0,
                    optEnabled: rank0.optEnabled || {},
                    optValues: rank0.optValues || {},
                    tabName: 'Symbol Compare'
                };
                console.log('[useProfileConfig] Initialized symbolCompareSettings from Rank 0 before Save As');
            }

            const profileData = {
                name: newName,
                description: newDescription || profileMeta.description,
                strategy_name: profileMeta.strategy_name,
                rank_configs: transformConfigListToRankConfigs(configList),
                execution_mode: profileMeta.execution_mode,
                rank_weights: profileMeta.rank_weights,
                initial_capital: profileMeta.initial_capital,
                is_paper: profileMeta.is_paper,
                symbol_compare_settings: effectiveSymbolCompareSettings
            };

            const result = await createProfile(profileData);
            console.log('[useProfileConfig] Profile saved as:', newName, result);

            // Switch to new profile
            if (result.data?.id) {
                setSelectedProfileId(result.data.id);
                // Update selectedProfile with the new profile data
                const newProfile = {
                    ...profileData,
                    id: result.data.id,
                    name: newName,
                    description: newDescription || profileMeta.description
                };
                setSelectedProfile(newProfile);
                setProfileMeta(prev => ({ ...prev, name: newName, description: newDescription }));

                // Update symbolCompareSettings with new reference to trigger React re-render
                // Use effectiveSymbolCompareSettings which may have been initialized from Rank 0
                setSymbolCompareSettings(JSON.parse(JSON.stringify(effectiveSymbolCompareSettings)));
            }

            // Update original state
            setOriginalConfigList(JSON.parse(JSON.stringify(configList)));
            setOriginalProfileMeta(JSON.parse(JSON.stringify({ ...profileMeta, name: newName, description: newDescription })));
            setOriginalSymbolCompareSettings(effectiveSymbolCompareSettings ? JSON.parse(JSON.stringify(effectiveSymbolCompareSettings)) : null);

            // Clear draft for old profile, new profile starts clean
            clearDraft(selectedProfileId);

            setSaveStatus('saved');
            await loadProfiles();

            setTimeout(() => {
                if (isMountedRef.current) setSaveStatus('idle');
            }, 2000);

            return result;
        } catch (e) {
            console.error('[useProfileConfig] Failed to save profile as:', e);
            setSaveStatus('error');
            setError(e);
            throw e;
        }
    }, [profileMeta, configList, symbolCompareSettings, transformConfigListToRankConfigs, loadProfiles, selectedProfileId, clearDraft]);

    /**
     * Delete current profile
     */
    const deleteCurrentProfile = useCallback(async (hardDelete = false) => {
        if (!selectedProfileId) {
            console.warn('[useProfileConfig] No profile selected to delete');
            return;
        }

        try {
            await deleteProfile(selectedProfileId, hardDelete);
            console.log('[useProfileConfig] Profile deleted:', selectedProfileId);

            // Clear selection
            setSelectedProfileId(null);
            setSelectedProfile(null);
            setConfigList([]);
            setOriginalConfigList([]);

            // Refresh profiles list
            await loadProfiles();
        } catch (e) {
            console.error('[useProfileConfig] Failed to delete profile:', e);
            setError(e);
            throw e;
        }
    }, [selectedProfileId, loadProfiles]);

    /**
     * Discard changes (revert to original)
     */
    const discardChanges = useCallback(() => {
        if (originalConfigList.length > 0) {
            setConfigList(JSON.parse(JSON.stringify(originalConfigList)));
        }
        if (originalProfileMeta) {
            setProfileMeta(JSON.parse(JSON.stringify(originalProfileMeta)));
        }
        // Restore Symbol Compare settings
        setSymbolCompareSettings(originalSymbolCompareSettings ? JSON.parse(JSON.stringify(originalSymbolCompareSettings)) : null);
        // Clear localStorage draft
        clearDraft(selectedProfileId);
        console.log('[useProfileConfig] Changes discarded');
    }, [originalConfigList, originalProfileMeta, originalSymbolCompareSettings, selectedProfileId, clearDraft]);

    /**
     * Initialize on mount - load profiles and auto-select last used
     */
    useEffect(() => {
        isMountedRef.current = true;

        const init = async () => {
            log('Initializing profile config...');
            const result = await loadProfiles('', true); // autoSelectLast = true
            log(`loadProfiles returned: autoSelectedId=${result?.autoSelectedId || 'none'}, profiles=${result?.profiles?.length || 0}`);

            // If a profile was auto-selected, load its full data
            if (result?.autoSelectedId) {
                try {
                    log(`Loading full profile data for ID: ${result.autoSelectedId}`);
                    const profile = await getProfile(result.autoSelectedId);
                    if (!isMountedRef.current) return;

                    log(`Setting state for profile: ${profile.name}`, 'success');

                    // Extract configList from rank_configs
                    const configs = transformProfileToConfigList(profile);

                    // Set profile metadata
                    const meta = {
                        name: profile.name || '',
                        description: profile.description || '',
                        strategy_name: profile.strategy_name || '',
                        execution_mode: profile.execution_mode || 'parallel',
                        initial_capital: profile.initial_capital || 10000000,
                        is_paper: profile.is_paper !== false,
                        rank_weights: profile.rank_weights || null
                    };

                    // Set Symbol Compare settings
                    // If null, initialize from Rank 0 for independent Symbol Compare tab settings
                    let compareSettings = profile.symbol_compare_settings;
                    // Migration: unwrap legacy nested structure
                    if (compareSettings && compareSettings.config && !compareSettings.symbol && !compareSettings.interval) {
                        const { config: nestedConfig, ...rest } = compareSettings;
                        compareSettings = { ...nestedConfig, ...rest };
                        log('Migrated legacy nested symbolCompareSettings to flat structure');
                    }
                    if (!compareSettings && configs.length > 0) {
                        const rank0 = configs[0];
                        compareSettings = {
                            ...rank0,
                            optEnabled: rank0.optEnabled || {},
                            optValues: rank0.optValues || {},
                            tabName: 'Symbol Compare'
                        };
                        log('Initialized symbolCompareSettings from Rank 0');
                    }

                    // Set original state from DB
                    setSelectedProfileId(result.autoSelectedId);
                    setSelectedProfile(profile);
                    setOriginalConfigList(JSON.parse(JSON.stringify(configs)));
                    setOriginalProfileMeta(JSON.parse(JSON.stringify(meta)));
                    setOriginalSymbolCompareSettings(compareSettings ? JSON.parse(JSON.stringify(compareSettings)) : null);

                    // Check for localStorage draft and apply if exists
                    const draft = loadDraft(result.autoSelectedId);
                    if (draft) {
                        log('Found draft for auto-loaded profile, applying...');
                        setConfigList(draft.configList || configs);
                        setProfileMeta(draft.profileMeta || meta);
                        setSymbolCompareSettings(draft.symbolCompareSettings !== undefined ? draft.symbolCompareSettings : (compareSettings || null));
                    } else {
                        setConfigList(configs);
                        setProfileMeta(meta);
                        setSymbolCompareSettings(compareSettings || null);
                    }
                    setIsLoaded(true);

                    log(`Auto-loaded: ${profile.name}, selectedProfileId=${result.autoSelectedId}, symbolCompare=${!!compareSettings}, hasDraft=${!!draft}`, 'success');
                } catch (e) {
                    log(`Failed to auto-load profile: ${e.message}`, 'error');
                    setIsLoaded(true);
                }
            } else {
                log(`No auto-select. Profiles loaded: ${result?.profiles?.length || 0}`);
                setIsLoaded(true);
            }
        };

        init();

        return () => {
            isMountedRef.current = false;
        };
    }, [log, loadProfiles, transformProfileToConfigList, loadDraft]); // Include stable deps

    // ═══════════════════════════════════════════════════════════════════════════════
    // Backward Compatible Interface (matches useStrategyConfig)
    // ═══════════════════════════════════════════════════════════════════════════════

    /**
     * Legacy saveConfigs - saves to current profile
     */
    const saveConfigs = useCallback(async () => {
        if (selectedProfileId) {
            return saveProfile();
        } else {
            console.warn('[useProfileConfig] saveConfigs called but no profile selected. Use saveProfile with name.');
            return false;
        }
    }, [selectedProfileId, saveProfile]);

    /**
     * Legacy initDefaultList
     */
    const initDefaultList = useCallback(() => {
        const defaultTab = createDefaultRankConfig(0);
        setConfigList([defaultTab]);
    }, [createDefaultRankConfig]);

    return {
        // ═══════════════════════════════════════════════════════════════════════════
        // Profile Management (New)
        // ═══════════════════════════════════════════════════════════════════════════
        profiles,
        selectedProfileId,
        selectedProfile,
        isProfilesLoading,
        loadProfiles,
        selectProfile,
        initNewProfile,
        createNewProfile, // Atomic create + save (avoids async state issues)
        saveProfile,
        saveProfileAs,
        deleteCurrentProfile,
        discardChanges,
        clearDraft, // Clear localStorage draft for a profile

        // Profile Metadata
        profileMeta,
        setProfileMeta,

        // Symbol Compare Settings (프로필별 저장)
        symbolCompareSettings,
        setSymbolCompareSettings,

        // Dirty State
        isDirty,

        // ═══════════════════════════════════════════════════════════════════════════
        // Backward Compatible Interface (from useStrategyConfig)
        // ═══════════════════════════════════════════════════════════════════════════
        configList,
        setConfigList,
        isLoaded,
        isConfigLoaded: isLoaded, // Alias
        needsInit: !selectedProfileId && configList.length === 0,
        setNeedsInit: () => {}, // No-op for compatibility
        error,
        saveStatus,
        scope, // Backward compatible scope object

        // Actions
        saveConfigs,
        reloadConfigs: loadProfiles,
        initDefaultList,

        // Transformers
        getDynamicDefaultConfig,
        transformProfileToConfigList,
        transformConfigListToRankConfigs,
        transformUiToDbConfig, // Legacy API compatibility
    };
};

export default useProfileConfig;
