import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { getProfiles, getProfile, createProfile, updateProfile, deleteProfile, getAccountPreferences, updateLastSelectedProfile } from '../api/client';

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

        return profile.rank_configs.map((rankCfg, index) => {
            // Merge with defaults
            const merged = { ...dynamicDefault, ...rankCfg };

            // Ensure required fields
            if (!merged.uuid) merged.uuid = generateUUID();
            if (merged.rank === undefined) merged.rank = index;
            if (merged.is_active === undefined) merged.is_active = true;
            if (!merged.tabName) merged.tabName = `Rank ${index + 1}`;

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

        return configChanged || metaChanged;
    }, [configList, originalConfigList, profileMeta, originalProfileMeta]);

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

            console.log('[useProfileConfig] Profile loaded:', profile.name, 'with', configs.length, 'ranks');
        } catch (e) {
            console.error('[useProfileConfig] Failed to load profile:', e);
            setError(e);
        } finally {
            if (isMountedRef.current) {
                setIsLoaded(true);
            }
        }
    }, [transformProfileToConfigList]);

    /**
     * Create a new profile (for New Profile wizard)
     */
    const initNewProfile = useCallback((strategyId) => {
        setSelectedProfileId(null);
        setSelectedProfile(null);

        const defaultRank = createDefaultRankConfig(0);
        setConfigList([defaultRank]);
        setOriginalConfigList([]);

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
            const profileData = {
                name: name || profileMeta.name,
                description: profileMeta.description,
                strategy_name: profileMeta.strategy_name,
                rank_configs: transformConfigListToRankConfigs(configList),
                execution_mode: profileMeta.execution_mode,
                rank_weights: profileMeta.rank_weights,
                initial_capital: profileMeta.initial_capital,
                is_paper: profileMeta.is_paper
            };

            let result;
            if (selectedProfileId) {
                // Update existing
                result = await updateProfile(selectedProfileId, profileData);
                console.log('[useProfileConfig] Profile updated:', result);
            } else {
                // Create new
                if (!profileData.name) {
                    throw new Error('Profile name is required');
                }
                result = await createProfile(profileData);
                console.log('[useProfileConfig] Profile created:', result);

                // Update selected profile ID
                if (result.data?.id) {
                    setSelectedProfileId(result.data.id);
                }
            }

            // Update original state (no longer dirty)
            setOriginalConfigList(JSON.parse(JSON.stringify(configList)));
            setOriginalProfileMeta(JSON.parse(JSON.stringify(profileMeta)));

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
    }, [selectedProfileId, profileMeta, configList, transformConfigListToRankConfigs, loadProfiles]);

    /**
     * Save as new profile (always creates new)
     */
    const saveProfileAs = useCallback(async (newName, newDescription = '') => {
        setSaveStatus('saving');

        try {
            const profileData = {
                name: newName,
                description: newDescription || profileMeta.description,
                strategy_name: profileMeta.strategy_name,
                rank_configs: transformConfigListToRankConfigs(configList),
                execution_mode: profileMeta.execution_mode,
                rank_weights: profileMeta.rank_weights,
                initial_capital: profileMeta.initial_capital,
                is_paper: profileMeta.is_paper
            };

            const result = await createProfile(profileData);
            console.log('[useProfileConfig] Profile saved as:', newName, result);

            // Switch to new profile
            if (result.data?.id) {
                setSelectedProfileId(result.data.id);
                setProfileMeta(prev => ({ ...prev, name: newName, description: newDescription }));
            }

            // Update original state
            setOriginalConfigList(JSON.parse(JSON.stringify(configList)));
            setOriginalProfileMeta(JSON.parse(JSON.stringify({ ...profileMeta, name: newName })));

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
    }, [profileMeta, configList, transformConfigListToRankConfigs, loadProfiles]);

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
        console.log('[useProfileConfig] Changes discarded');
    }, [originalConfigList, originalProfileMeta]);

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

                    // Set all state together
                    setSelectedProfileId(result.autoSelectedId);
                    setSelectedProfile(profile);
                    setConfigList(configs);
                    setOriginalConfigList(JSON.parse(JSON.stringify(configs)));
                    setProfileMeta(meta);
                    setOriginalProfileMeta(JSON.parse(JSON.stringify(meta)));
                    setIsLoaded(true);

                    log(`Auto-loaded: ${profile.name}, selectedProfileId=${result.autoSelectedId}`, 'success');
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
    }, [log, loadProfiles, transformProfileToConfigList]); // Include stable deps

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

        // Profile Metadata
        profileMeta,
        setProfileMeta,

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
