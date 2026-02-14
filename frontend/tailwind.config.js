/** @type {import('tailwindcss').Config} */
export default {
    content: [
        "./index.html",
        "./src/**/*.{js,ts,jsx,tsx}",
    ],
    theme: {
        extend: {
            colors: {
                background: "hsl(var(--background))",
                foreground: "hsl(var(--foreground))",
                /* Semantic theme colors - use these in new code */
                't': {
                    'bg-base': 'var(--t-bg-base)',
                    'bg-card': 'var(--t-bg-card)',
                    'bg-surface': 'var(--t-bg-surface)',
                    'bg-surface-hover': 'var(--t-bg-surface-hover)',
                    'bg-input': 'var(--t-bg-input)',
                    'bg-nav': 'var(--t-bg-nav)',
                    'bg-overlay': 'var(--t-bg-overlay)',
                    'text': 'var(--t-text-primary)',
                    'text-secondary': 'var(--t-text-secondary)',
                    'text-tertiary': 'var(--t-text-tertiary)',
                    'text-muted': 'var(--t-text-muted)',
                    'text-faint': 'var(--t-text-faint)',
                    'border': 'var(--t-border)',
                    'border-subtle': 'var(--t-border-subtle)',
                },
            },
        },
    },
    plugins: [],
}
