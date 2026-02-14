import React, { createContext, useContext, useState, useEffect } from 'react';

const THEMES = {
    'dark-bg': { label: '다크 백그라운드', description: '검은색 바탕 브라우저에 최적화' },
    'normal': { label: 'Normal', description: '일반 브라우저에 최적화된 표준 테마' },
};

const ThemeContext = createContext();

export const ThemeProvider = ({ children }) => {
    const [theme, setTheme] = useState(() => {
        return localStorage.getItem('ui-theme') || 'dark-bg';
    });

    useEffect(() => {
        localStorage.setItem('ui-theme', theme);
        document.documentElement.setAttribute('data-theme', theme);
    }, [theme]);

    // Set initial theme on mount
    useEffect(() => {
        document.documentElement.setAttribute('data-theme', theme);
    }, []);

    return (
        <ThemeContext.Provider value={{ theme, setTheme, themes: THEMES }}>
            {children}
        </ThemeContext.Provider>
    );
};

export const useTheme = () => {
    const ctx = useContext(ThemeContext);
    if (!ctx) throw new Error('useTheme must be used within ThemeProvider');
    return ctx;
};
