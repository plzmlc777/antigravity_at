import { useState, useEffect } from 'react';
import { getAllSessions } from '../api/client';

/**
 * useProfileLock - Detects if a profile is in use by active live sessions.
 * Polls every 30s. Returns isProfileLocked boolean.
 */
export const useProfileLock = ({ selectedProfileId, profileName }) => {
    const [isProfileLocked, setIsProfileLocked] = useState(false);

    useEffect(() => {
        if (!selectedProfileId) {
            setIsProfileLocked(false);
            return;
        }

        let cancelled = false;

        const checkLock = async () => {
            try {
                const sessions = await getAllSessions({ includeStopped: false, limit: 100 });
                if (cancelled) return;
                const activeSessions = (sessions || []).filter(
                    s => s.status === 'RUNNING' || s.status === 'PAUSED'
                );
                // Match by profile_id (robust) or fall back to profile_name
                const locked = activeSessions.some(
                    s => (s.profile_id && s.profile_id === selectedProfileId)
                        || (!s.profile_id && s.profile_name && s.profile_name === profileName)
                );
                setIsProfileLocked(locked);
            } catch (err) {
                console.warn('[useProfileLock] Failed to check profile lock:', err);
            }
        };

        checkLock();
        const interval = setInterval(checkLock, 30000);

        return () => {
            cancelled = true;
            clearInterval(interval);
        };
    }, [selectedProfileId, profileName]);

    return { isProfileLocked };
};
