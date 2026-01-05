import { useState, useEffect, useCallback, useRef } from 'react';
import axios from 'axios';
import { getStrategyConfigs, syncStrategyConfigs } from '../api/client';

// Constants
const SYNC_DEBOUNCE_MS = 5000; // 5 seconds for DB auto-save
const LOCAL_DEBOUNCE_MS = 500;  // 0.5 seconds for LocalStorage

export const useConfigPersistence = (selectedStrategy, configList, setConfigList) => {
    const [isConfigLoaded, setIsConfigLoaded] = useState(false);
    const [lastSyncedAt, setLastSyncedAt] = useState(null);
    const [syncStatus, setSyncStatus] = useState('idle'); // idle, syncing, error, saved

    const saveTimerRef = useRef(null);
    const localSaveTimerRef = useRef(null);
    const isInitialLoadRef = useRef(true);

    // 1. Initial Load (Hybrid Strategy)
    useEffect(() => {
        if (!selectedStrategy) return;

        const loadConfigs = async () => {
            const storageKey = `strategyConfig_${selectedStrategy.id}_v2`;
            const localData = localStorage.getItem(storageKey);
            let localConfigs = null;
            let localTimestamp = 0;

            // Step A: Load LocalStorage (Instant UI)
            if (localData) {
                try {
                    localConfigs = JSON.parse(localData);
                    // Check if localConfigs has a timestamp (we need to start storing this)
                    // For now, assume local is fresh if it exists
                    setConfigList(localConfigs);
                    setIsConfigLoaded(true);
                } catch (e) {
                    console.error("Local config parse error", e);
                }
            }

            // Step B: Fetch DB (Background)
            try {
                const dbData = await getStrategyConfigs();
                // Check if DB data is relevant for this strategy (assuming getting all?)
                // Actually the API returns items. We need to filter or if the API is specific?
                // The API `getStrategyConfigs` currently returns a flat list of StrategyConfigs.
                // We need to map them to the current structure.

                // Note: Current API implementation might return ALL configs or filtered. 
                // Let's assume it returns standard format.

                if (dbData && dbData.length > 0) {
                    // Convert DB DTO to Frontend Config
                    const dbConfigs = dbData.map(item => ({
                        ...item.config_json,
                        uuid: item.tab_id,
                        rank: item.rank,
                        is_active: item.is_active,
                        tabName: item.tab_name,
                        _updated_at: item.updated_at // Store DB timestamp
                    })).sort((a, b) => a.rank - b.rank); // Trust DB rank

                    // Logic: Conflict Resolution
                    // If we have local data, we should compare. 
                    // Since we don't track local timestamp strictly yet, we'll adopt a simple rule:
                    // If DB has data and Local was empty, use DB.
                    // If both exist, for now, we might prefer Local if it was recently modified?
                    // BUT per the plan: "App Start / Refresh: Fetch latest data from DB"
                    // So we should update Local with DB if DB is authoritative.

                    // However, to prevent data loss (Refresh Trap), we need to be careful.
                    // Let's assume on a fresh load, DB is the source of truth unless we have a specific "Unsaved" flag.
                    // Impl simplified: Load DB, update State, Save to Local.

                    setConfigList(dbConfigs);
                    localStorage.setItem(storageKey, JSON.stringify(dbConfigs));
                    setIsConfigLoaded(true);
                } else if (!localConfigs) {
                    // No DB, No Local -> Default handled by parent (initDefaultList)
                    setIsConfigLoaded(true); // Allow parent to init
                }
            } catch (e) {
                console.error("DB Fetch failed", e);
                // Fallback to Local (already loaded)
                if (!localConfigs) setIsConfigLoaded(true);
            }
        };

        loadConfigs();
        isInitialLoadRef.current = false;
    }, [selectedStrategy]);

    // 2. LocalStorage Debounced Save
    useEffect(() => {
        if (!selectedStrategy || !isConfigLoaded || configList.length === 0) return;
        if (isInitialLoadRef.current) return;

        if (localSaveTimerRef.current) clearTimeout(localSaveTimerRef.current);

        localSaveTimerRef.current = setTimeout(() => {
            const storageKey = `strategyConfig_${selectedStrategy.id}_v2`;
            localStorage.setItem(storageKey, JSON.stringify(configList));
            // console.log("Saved to LocalStorage");
        }, LOCAL_DEBOUNCE_MS);

        return () => clearTimeout(localSaveTimerRef.current);
    }, [configList, selectedStrategy, isConfigLoaded]);

    // 3. DB Debounced Sync
    useEffect(() => {
        if (!selectedStrategy || !isConfigLoaded || configList.length === 0) return;

        // Don't auto-save on initial load immediately unless changed
        // We'll rely on user interaction to trigger this effect.

        if (saveTimerRef.current) clearTimeout(saveTimerRef.current);

        saveTimerRef.current = setTimeout(() => {
            saveToDB();
        }, SYNC_DEBOUNCE_MS);

        return () => clearTimeout(saveTimerRef.current);
    }, [configList, selectedStrategy, isConfigLoaded]);

    const saveToDB = useCallback(async (currentList = configList) => {
        if (!selectedStrategy) return;
        setSyncStatus('syncing');

        try {
            // Convert Frontend Config to DB DTO
            const dtos = currentList.map((cfg, idx) => ({
                tab_id: cfg.uuid,
                rank: idx, // Use array index as Order
                is_active: cfg.is_active !== false,
                tab_name: cfg.tabName || `Rank ${idx + 1}`,
                config_json: {
                    ...cfg,
                    uuid: undefined, // Remove redundant keys if needed
                    tabName: undefined,
                    is_active: undefined,
                    _updated_at: undefined
                }
            }));

            await syncStrategyConfigs(dtos);
            setSyncStatus('saved');
            setLastSyncedAt(new Date());
            setTimeout(() => setSyncStatus('idle'), 2000);
        } catch (e) {
            console.error("DB Sync failed", e);
            setSyncStatus('error');
        }
    }, [configList, selectedStrategy]);

    return {
        isConfigLoaded,
        syncStatus,
        lastSyncedAt,
        saveNow: () => saveToDB(configList) // Manual Trigger
    };
};
