// AI-centric frontend smoke suite.
// Verifies every surviving route loads, key DOM landmarks render, no console errors,
// and that demoted manual-trading routes are gone. Read-only — never clicks the kill switch.
import { test, expect } from '@playwright/test';

const ROUTES = {
    mission: '/',
    organization: '/organization',
    decisions: '/decisions',
    knowledge: '/knowledge',
};

// Pages that require login — we don't have a JWT in the smoke suite,
// so we expect them to redirect to /login (also a valid render path).
const AUTH_ROUTES = ['/settings'];

// Pages that should be GONE (no /manual, /strategies, /live, /strategy-lab).
const DEAD_ROUTES = ['/manual', '/strategies', '/live', '/emergency/manual', '/strategy-lab'];

/** Attach console listener that ignores benign noise. */
function captureConsoleErrors(page) {
    const errors = [];
    page.on('console', msg => {
        if (msg.type() !== 'error') return;
        const text = msg.text();
        // Ignore: 401s from auth-required endpoints (expected w/o login),
        // websocket connection failures (live data not always streaming),
        // React DevTools install hint, vite HMR ping noise.
        if (/401|websocket|React DevTools|vite|favicon/i.test(text)) return;
        errors.push(text);
    });
    page.on('pageerror', err => errors.push(`PAGEERROR: ${err.message}`));
    return errors;
}

test.describe('AI-centric frontend smoke', () => {

    test('Mission Control loads with KPI banner + KillSwitch button', async ({ page }) => {
        const errors = captureConsoleErrors(page);
        await page.goto(ROUTES.mission, { waitUntil: 'networkidle' });

        // Title / heading
        await expect(page.getByRole('heading', { name: 'Mission Control' })).toBeVisible();

        // KPI banner tiles
        await expect(page.getByText('월 복리 KPI')).toBeVisible();
        await expect(page.getByText('활성 세션')).toBeVisible();

        // Emergency kill switch — only manual write surface
        await expect(page.getByRole('button', { name: /ALL STOP/ })).toBeVisible();

        // 24h decision timeline section
        await expect(page.getByText('24h 결정 타임라인')).toBeVisible();

        expect(errors, `Console errors: ${errors.join('\n')}`).toEqual([]);
    });

    test('Organization (Agent Org Chart) renders React Flow nodes', async ({ page }) => {
        const errors = captureConsoleErrors(page);
        await page.goto(ROUTES.organization, { waitUntil: 'networkidle' });

        // Page heading
        await expect(page.getByRole('heading', { name: /조직도|Organization/i })).toBeVisible({ timeout: 10000 });

        // React Flow root pane should appear
        const flowPane = page.locator('.react-flow').first();
        await expect(flowPane).toBeVisible();

        expect(errors, `Console errors: ${errors.join('\n')}`).toEqual([]);
    });

    test('Decision Timeline loads with tabs', async ({ page }) => {
        const errors = captureConsoleErrors(page);
        await page.goto(ROUTES.decisions, { waitUntil: 'networkidle' });

        // Tab labels
        await expect(page.getByText('결정 로그')).toBeVisible();
        await expect(page.getByText('승인 대기열')).toBeVisible();

        expect(errors, `Console errors: ${errors.join('\n')}`).toEqual([]);
    });

    test('Knowledge Base loads with candidate filter buttons', async ({ page }) => {
        const errors = captureConsoleErrors(page);
        await page.goto(ROUTES.knowledge, { waitUntil: 'networkidle' });

        await expect(page.getByRole('heading', { name: 'Knowledge Base' })).toBeVisible();
        // Filter buttons
        await expect(page.getByRole('button', { name: /^전체/ })).toBeVisible();
        await expect(page.getByRole('button', { name: /^FAIL \(/ })).toBeVisible();

        expect(errors, `Console errors: ${errors.join('\n')}`).toEqual([]);
    });

    test('Auth-protected routes redirect or render gracefully', async ({ page }) => {
        for (const route of AUTH_ROUTES) {
            const errors = captureConsoleErrors(page);
            const resp = await page.goto(route, { waitUntil: 'domcontentloaded' });
            expect(resp.status(), `${route} status`).toBeLessThan(500);
            // Give SPA router a moment to settle (auth redirect or initial render).
            await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
            const url = page.url();
            const onLogin = url.includes('/login');
            const bodyText = (await page.locator('body').textContent().catch(() => '')) || '';
            expect(onLogin || bodyText.trim().length > 50, `${route} did not render (url=${url})`).toBe(true);
            expect(errors, `${route} console errors: ${errors.join('\n')}`).toEqual([]);
        }
    });

    test('Demoted manual-trading routes are gone', async ({ page }) => {
        // SPA: dead routes fall through to whatever the catch-all renders.
        // We assert: no <h1>Mission Control</h1> hijacked, no JS error, eventual settle.
        for (const route of DEAD_ROUTES) {
            const errors = captureConsoleErrors(page);
            const resp = await page.goto(route, { waitUntil: 'domcontentloaded' });
            expect(resp.status(), `${route} status`).toBeLessThan(500);

            // The deleted views should NOT have left any "manual order" text behind
            const body = await page.locator('body').textContent();
            expect(body, `${route} should not contain 매뉴얼 주문 UI`).not.toMatch(/Manual Trading Execution|매뉴얼 매수|매뉴얼 매도|EMERGENCY MANUAL MODE/);

            expect(errors, `${route} console errors: ${errors.join('\n')}`).toEqual([]);
        }
    });

    test('Backend agents-meta endpoints respond from frontend proxy', async ({ request }) => {
        // The frontend dev server proxies /api → backend; this catches CORS/proxy regressions.
        const r1 = await request.get('/api/v1/agents');
        expect(r1.status()).toBe(200);
        const agents = await r1.json();
        expect(Array.isArray(agents)).toBe(true);
        expect(agents.length).toBeGreaterThan(10);

        const r2 = await request.get('/api/v1/live/monitor/sessions');
        expect(r2.status()).toBe(200);

        const r3 = await request.get('/api/v1/system/version');
        expect(r3.status()).toBe(200);
        const version = await r3.json();
        expect(version.version).toMatch(/^\d+\.\d+\.\d+/);
    });

    test('Emergency kill switch endpoint exists and requires auth', async ({ request }) => {
        // CRITICAL: do NOT trigger the actual stop. We only verify the endpoint registration
        // by confirming it returns 401 without a token (vs 404 which would mean missing route).
        const r = await request.post('/api/v1/live/emergency-stop');
        expect([401, 403], `expected auth-required, got ${r.status()}`).toContain(r.status());
    });
});

// Audition page tests — CIO-20260408-015 Phase 4
test.describe('Audition page (CIO-20260408-015)', () => {

    test('/audition route renders Strategy Audition System heading', async ({ page }) => {
        const errors = captureConsoleErrors(page);
        await page.goto('/audition', { waitUntil: 'networkidle' });
        await expect(page.getByRole('heading', { name: 'Strategy Audition System' })).toBeVisible({ timeout: 15000 });
        expect(errors, `Console errors: ${errors.join('\n')}`).toEqual([]);
    });

    test('/audition shows navigation link 오디션 in navbar', async ({ page }) => {
        const errors = captureConsoleErrors(page);
        await page.goto('/', { waitUntil: 'networkidle' });
        const navLink = page.locator('a[href="/audition"]');
        await expect(navLink).toBeVisible();
        await expect(navLink).toHaveText('오디션');
        expect(errors, `Console errors: ${errors.join('\n')}`).toEqual([]);
    });

    test('/audition summary cards: Graduated and Eliminated visible', async ({ page }) => {
        const errors = captureConsoleErrors(page);
        await page.goto('/audition', { waitUntil: 'networkidle' });
        await expect(page.getByRole('heading', { name: 'Strategy Audition System' })).toBeVisible({ timeout: 15000 });
        await expect(page.getByText('Graduated', { exact: true })).toBeVisible({ timeout: 10000 });
        await expect(page.getByText('Eliminated', { exact: true })).toBeVisible({ timeout: 10000 });
        expect(errors, `Console errors: ${errors.join('\n')}`).toEqual([]);
    });

    test('/audition pool table shows 10 entries', async ({ page }) => {
        const errors = captureConsoleErrors(page);
        await page.goto('/audition', { waitUntil: 'networkidle' });
        await expect(page.locator('table')).toBeVisible({ timeout: 15000 });
        const rows = page.locator('table tbody tr');
        await expect(rows).toHaveCount(10, { timeout: 10000 });
        expect(errors, `Console errors: ${errors.join('\n')}`).toEqual([]);
    });

    test('/audition Graveyard section visible', async ({ page }) => {
        const errors = captureConsoleErrors(page);
        await page.goto('/audition', { waitUntil: 'networkidle' });
        await expect(page.getByText("Graveyard — 탈락 풀", { exact: true })).toBeVisible({ timeout: 15000 });
        await expect(page.getByText('총 탈락')).toBeVisible({ timeout: 10000 });
        expect(errors, `Console errors: ${errors.join('\n')}`).toEqual([]);
    });

    test('/audition has NO manual action buttons (READ-ONLY)', async ({ page }) => {
        const errors = captureConsoleErrors(page);
        await page.goto('/audition', { waitUntil: 'networkidle' });
        await expect(page.getByRole('heading', { name: 'Strategy Audition System' })).toBeVisible({ timeout: 15000 });
        const actionTexts = ['승급', '탈락', '부활', '삭제', '초기화', 'Run', 'Submit', 'Save'];
        for (const text of actionTexts) {
            const btn = page.getByRole('button', { name: new RegExp(text, 'i') });
            await expect(btn, `No button with text "${text}" should exist`).toHaveCount(0);
        }
        expect(errors, `Console errors: ${errors.join('\n')}`).toEqual([]);
    });

    test('Audition API endpoints respond via frontend proxy', async ({ request }) => {
        const r1 = await request.get('/api/v1/strategy-audition?status=all&limit=50');
        expect(r1.status()).toBe(200);
        const list = await r1.json();
        expect(Array.isArray(list)).toBe(true);
        expect(list.length).toBe(10);

        const r2 = await request.get('/api/v1/strategy-audition/stats/weekly?weeks=8');
        expect(r2.status()).toBe(200);
        const stats = await r2.json();
        expect(stats).toHaveProperty('total_by_status');
        expect(stats.total_by_status.graduated).toBeGreaterThanOrEqual(8);
        expect(stats.total_by_status.eliminated).toBeGreaterThanOrEqual(2);

        const r3 = await request.get('/api/v1/strategy-audition/stats/graveyard');
        expect(r3.status()).toBe(200);
        const graveyard = await r3.json();
        expect(graveyard).toHaveProperty('total_eliminated');
        expect(graveyard.total_eliminated).toBeGreaterThanOrEqual(2);
    });
});
