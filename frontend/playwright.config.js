// Playwright config for AI-centric frontend smoke tests.
// Runs against the live PM2 dev server on :5173 — read-only, no manipulation of live sessions.
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
    testDir: './tests/e2e',
    timeout: 30000,
    expect: { timeout: 5000 },
    fullyParallel: false,    // Sequential to keep load on the live backend predictable
    forbidOnly: true,
    retries: 1,
    workers: 1,
    reporter: [
        ['list'],
        ['json', { outputFile: 'tests/e2e/__results__/report.json' }],
    ],
    use: {
        baseURL: process.env.E2E_BASE_URL || 'http://localhost:5173',
        trace: 'retain-on-failure',
        screenshot: 'only-on-failure',
        video: 'off',
        // Headless Chromium with no GPU — works in WSL.
        launchOptions: { args: ['--no-sandbox', '--disable-gpu'] },
    },
    projects: [
        {
            name: 'chromium',
            use: { ...devices['Desktop Chrome'] },
        },
    ],
    outputDir: 'tests/e2e/__results__/artifacts',
});
