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

// Pages that should be GONE (no /strategies, /live, /strategy-lab).
const DEAD_ROUTES = ['/strategies', '/live', '/emergency/manual', '/strategy-lab'];

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

// Workflow Visualization tests — CIO-20260408-016 Level 2
test.describe('Workflow Visualization (CIO-20260408-016)', () => {

    test('/workflow route renders heading', async ({ page }) => {
        const errors = captureConsoleErrors(page);
        await page.goto('/workflow', { waitUntil: 'networkidle' });
        await expect(page.getByRole('heading', { name: 'Agent Workflow — Live Execution' })).toBeVisible({ timeout: 15000 });
        expect(errors, `Console errors: ${errors.join('\n')}`).toEqual([]);
    });

    test('/workflow shows Workflow nav link', async ({ page }) => {
        const errors = captureConsoleErrors(page);
        await page.goto('/', { waitUntil: 'networkidle' });
        const navLink = page.locator('a[href="/workflow"]');
        await expect(navLink).toBeVisible();
        await expect(navLink).toHaveText('Workflow');
        expect(errors, `Console errors: ${errors.join('\n')}`).toEqual([]);
    });

    test('/workflow summary bar shows Window / gap_signals / auditions', async ({ page }) => {
        const errors = captureConsoleErrors(page);
        await page.goto('/workflow', { waitUntil: 'networkidle' });
        await expect(page.getByRole('heading', { name: 'Agent Workflow — Live Execution' })).toBeVisible({ timeout: 15000 });
        // Use summary-bar span (text-gray-500) to avoid strict-mode collision with nav label
        await expect(page.locator('span.text-gray-500', { hasText: 'Window:' }).first()).toBeVisible({ timeout: 10000 });
        await expect(page.locator('span.text-gray-500', { hasText: 'gap_signals:' }).first()).toBeVisible({ timeout: 10000 });
        await expect(page.locator('span.text-gray-500', { hasText: 'auditions:' }).first()).toBeVisible({ timeout: 10000 });
        expect(errors, `Console errors: ${errors.join('\n')}`).toEqual([]);
    });

    test('/workflow has 3 window selector buttons with 7d active', async ({ page }) => {
        const errors = captureConsoleErrors(page);
        await page.goto('/workflow', { waitUntil: 'networkidle' });
        await expect(page.getByRole('heading', { name: 'Agent Workflow — Live Execution' })).toBeVisible({ timeout: 15000 });
        await expect(page.locator('button', { hasText: '1d' }).first()).toBeVisible();
        await expect(page.locator('button', { hasText: '7d' }).first()).toBeVisible();
        await expect(page.locator('button', { hasText: '30d' }).first()).toBeVisible();
        const btn7d = page.locator('button', { hasText: '7d' }).first();
        await expect(btn7d).toHaveClass(/bg-blue-600/);
        expect(errors, `Console errors: ${errors.join('\n')}`).toEqual([]);
    });

    test('/workflow ReactFlow canvas renders', async ({ page }) => {
        const errors = captureConsoleErrors(page);
        await page.goto('/workflow', { waitUntil: 'networkidle' });
        await expect(page.getByRole('heading', { name: 'Agent Workflow — Live Execution' })).toBeVisible({ timeout: 15000 });
        const flowPane = page.locator('.react-flow').first();
        await expect(flowPane).toBeVisible({ timeout: 10000 });
        const attribution = page.locator('.react-flow__attribution');
        await expect(attribution).toHaveCount(0);
        expect(errors, `Console errors: ${errors.join('\n')}`).toEqual([]);
    });

    test('/workflow Legend block shows 5 node types', async ({ page }) => {
        const errors = captureConsoleErrors(page);
        await page.goto('/workflow', { waitUntil: 'networkidle' });
        await expect(page.getByRole('heading', { name: 'Agent Workflow — Live Execution' })).toBeVisible({ timeout: 15000 });
        await expect(page.getByText('Legend')).toBeVisible({ timeout: 10000 });
        await expect(page.getByText('trigger')).toBeVisible();
        await expect(page.getByText('agent', { exact: true })).toBeVisible();
        await expect(page.getByText('router')).toBeVisible();
        await expect(page.getByText('data store')).toBeVisible();
        await expect(page.getByText('file')).toBeVisible();
        expect(errors, `Console errors: ${errors.join('\n')}`).toEqual([]);
    });

    test('/workflow Recent Timeline section is visible', async ({ page }) => {
        const errors = captureConsoleErrors(page);
        await page.goto('/workflow', { waitUntil: 'networkidle' });
        await expect(page.getByRole('heading', { name: 'Agent Workflow — Live Execution' })).toBeVisible({ timeout: 15000 });
        const timelineHeading = page.getByText(/Recent Timeline/);
        const noActivity = page.getByText('No activity in the selected window');
        await expect(timelineHeading.or(noActivity)).toBeVisible({ timeout: 10000 });
        expect(errors, `Console errors: ${errors.join('\n')}`).toEqual([]);
    });

    test('/workflow has NO manual action buttons', async ({ page }) => {
        const errors = captureConsoleErrors(page);
        await page.goto('/workflow', { waitUntil: 'networkidle' });
        await expect(page.getByRole('heading', { name: 'Agent Workflow — Live Execution' })).toBeVisible({ timeout: 15000 });
        const forbiddenTexts = ['실행', '중지', '재시작', 'Stop', 'Submit', 'Save', 'Delete'];
        for (const text of forbiddenTexts) {
            const btn = page.getByRole('button', { name: new RegExp(text, 'i') });
            await expect(btn, `No action button with text: ${text}`).toHaveCount(0);
        }
        expect(errors, `Console errors: ${errors.join('\n')}`).toEqual([]);
    });

    test('Workflow API /api/v1/workflow/executions/recent responds 200 with required keys', async ({ request }) => {
        const r = await request.get('/api/v1/workflow/executions/recent?days=7');
        expect(r.status()).toBe(200);
        const body = await r.json();
        expect(body).toHaveProperty('time_range');
        expect(body).toHaveProperty('totals');
        expect(body).toHaveProperty('node_stats');
        expect(body).toHaveProperty('edge_flow');
        expect(body).toHaveProperty('timeline');
        expect(body.totals).toHaveProperty('gap_signals_in_window');
        expect(body.totals).toHaveProperty('auditions_in_window');
    });

    test('/organization ReactFlow regression after Workflow addition', async ({ page }) => {
        const errors = captureConsoleErrors(page);
        await page.goto('/organization', { waitUntil: 'networkidle' });
        await expect(page.getByRole('heading', { name: /조직도|Organization/i })).toBeVisible({ timeout: 10000 });
        const flowPane = page.locator('.react-flow').first();
        await expect(flowPane).toBeVisible({ timeout: 10000 });
        expect(errors, `Console errors: ${errors.join('\n')}`).toEqual([]);
    });

    test('/audition regression — Strategy Audition System still intact', async ({ page }) => {
        const errors = captureConsoleErrors(page);
        await page.goto('/audition', { waitUntil: 'networkidle' });
        await expect(page.getByRole('heading', { name: 'Strategy Audition System' })).toBeVisible({ timeout: 15000 });
        await expect(page.getByText('Graduated', { exact: true })).toBeVisible({ timeout: 10000 });
        await expect(page.getByText('Eliminated', { exact: true })).toBeVisible({ timeout: 10000 });
        expect(errors, `Console errors: ${errors.join('\n')}`).toEqual([]);
    });
});


// SISDS Phase 1 State Machine frontend tests (CIO-20260410-001)
test.describe("SISDS Phase 1 Stage Distribution (CIO-20260410-001)", () => {

    test("/audition SISDS Stage Distribution section is visible", async ({ page }) => {
        const errors = captureConsoleErrors(page);
        await page.goto("/audition", { waitUntil: "networkidle" });
        await expect(page.getByRole("heading", { name: "Strategy Audition System" })).toBeVisible({ timeout: 15000 });
        await expect(page.getByText("SISDS Stage Distribution")).toBeVisible({ timeout: 10000 });
        await expect(page.getByText("CIO-017 Phase 1")).toBeVisible({ timeout: 10000 });
    });

    test("/audition shows all 6 stage cards", async ({ page }) => {
        const errors = captureConsoleErrors(page);
        await page.goto("/audition", { waitUntil: "networkidle" });
        await expect(page.getByRole("heading", { name: "Strategy Audition System" })).toBeVisible({ timeout: 15000 });
        await expect(page.getByText("SISDS Stage Distribution")).toBeVisible({ timeout: 10000 });
        for (const stage of ["birth", "sandbox", "paper", "live", "retired", "legacy"]) {
            await expect(page.getByText(stage, { exact: true })).toBeVisible({ timeout: 10000 });
        }
    });

    test("/audition legacy=8 retired=2 via API snapshot", async ({ page }) => {
        await page.goto("/audition", { waitUntil: "networkidle" });
        await expect(page.getByText("SISDS Stage Distribution")).toBeVisible({ timeout: 10000 });
        const resp = await page.evaluate(async () => {
            const r = await fetch("/api/v1/strategy-audition/stats/by-stage");
            return r.json();
        });
        const legacyTotal = Object.values(resp.distribution?.legacy || {}).reduce((a, b) => a + b, 0);
        const retiredTotal = Object.values(resp.distribution?.retired || {}).reduce((a, b) => a + b, 0);
        expect(legacyTotal).toBe(8);
        expect(retiredTotal).toBe(2);
    });

    test("/audition pool table has Stage column header", async ({ page }) => {
        await page.goto("/audition", { waitUntil: "networkidle" });
        await expect(page.locator("table")).toBeVisible({ timeout: 15000 });
        const stageHeader = page.locator("table thead th", { hasText: "Stage" });
        await expect(stageHeader).toBeVisible({ timeout: 10000 });
    });

    test("/audition pool table rows have StageBadge slash separator", async ({ page }) => {
        await page.goto("/audition", { waitUntil: "networkidle" });
        await expect(page.locator("table tbody tr").first()).toBeVisible({ timeout: 15000 });
        const stageCells = page.locator("table tbody td span.font-mono").filter({ hasText: "/" });
        await expect(stageCells.first()).toBeVisible({ timeout: 10000 });
    });

    test("/audition existing columns retained (Birth + Stage)", async ({ page }) => {
        await page.goto("/audition", { waitUntil: "networkidle" });
        await expect(page.locator("table")).toBeVisible({ timeout: 15000 });
        await expect(page.locator("table thead th", { hasText: "Birth" })).toBeVisible({ timeout: 10000 });
        await expect(page.locator("table thead th", { hasText: "Stage" })).toBeVisible({ timeout: 10000 });
    });

    test("Stage API stats/by-stage returns 200 with all 6 stages", async ({ request }) => {
        const r = await request.get("/api/v1/strategy-audition/stats/by-stage");
        expect(r.status()).toBe(200);
        const body = await r.json();
        expect(body).toHaveProperty("total");
        expect(body).toHaveProperty("distribution");
        expect(body).toHaveProperty("stages");
        expect(body).toHaveProperty("statuses");
        for (const stage of ["birth", "sandbox", "paper", "live", "retired", "legacy"]) {
            expect(body.distribution).toHaveProperty(stage);
        }
        const legacyTotal = Object.values(body.distribution.legacy || {}).reduce((a, b) => a + b, 0);
        const retiredTotal = Object.values(body.distribution.retired || {}).reduce((a, b) => a + b, 0);
        expect(legacyTotal).toBe(8);
        expect(retiredTotal).toBe(2);
    });

    test("/audition summary cards Graduated+Eliminated still present", async ({ page }) => {
        await page.goto("/audition", { waitUntil: "networkidle" });
        await expect(page.getByRole("heading", { name: "Strategy Audition System" })).toBeVisible({ timeout: 15000 });
        await expect(page.getByText("Graduated", { exact: true })).toBeVisible({ timeout: 10000 });
        await expect(page.getByText("Eliminated", { exact: true })).toBeVisible({ timeout: 10000 });
    });

    test("/audition has NO manual action buttons after SISDS addition", async ({ page }) => {
        await page.goto("/audition", { waitUntil: "networkidle" });
        await expect(page.getByRole("heading", { name: "Strategy Audition System" })).toBeVisible({ timeout: 15000 });
        const actionTexts = ["Transition", "Submit", "Save", "Run"];
        for (const text of actionTexts) {
            const btn = page.getByRole("button", { name: new RegExp(text, "i") });
            await expect(btn).toHaveCount(0);
        }
    });

    test("/workflow regression after SISDS addition", async ({ page }) => {
        const errors = captureConsoleErrors(page);
        await page.goto("/workflow", { waitUntil: "networkidle" });
        await expect(page.getByRole("heading", { name: "Agent Workflow — Live Execution" })).toBeVisible({ timeout: 15000 });
        expect(errors).toEqual([]);
    });

    test("/organization regression after SISDS addition", async ({ page }) => {
        const errors = captureConsoleErrors(page);
        await page.goto("/organization", { waitUntil: "networkidle" });
        await expect(page.getByRole("heading", { name: /조직도|Organization/i })).toBeVisible({ timeout: 10000 });
        const flowPane = page.locator(".react-flow").first();
        await expect(flowPane).toBeVisible({ timeout: 10000 });
        expect(errors).toEqual([]);
    });
});

// SISDS Phase 5 Live Promotion Flow tests (CIO-20260408-017)
test.describe("SISDS Phase 5 Live Promotion Flow (CIO-20260408-017)", () => {

    test("/audition LiveCandidatePanel hidden when no paper/waiting_human entries", async ({ page }) => {
        const errors = captureConsoleErrors(page);
        await page.goto("/audition", { waitUntil: "networkidle" });
        await expect(page.getByRole("heading", { name: "Strategy Audition System" })).toBeVisible({ timeout: 15000 });
        // panel only renders when candidates exist — verify it is NOT present
        const panel = page.getByText("Live 승급 후보 — 사용자 승인 필요");
        await expect(panel).toHaveCount(0);
        expect(errors, `Console errors: ${errors.join('\n')}`).toEqual([]);
    });

    test("/audition footer contains '유일한 예외' text", async ({ page }) => {
        const errors = captureConsoleErrors(page);
        await page.goto("/audition", { waitUntil: "networkidle" });
        await expect(page.getByRole("heading", { name: "Strategy Audition System" })).toBeVisible({ timeout: 15000 });
        await expect(page.getByText(/유일한 예외/)).toBeVisible({ timeout: 10000 });
        expect(errors, `Console errors: ${errors.join('\n')}`).toEqual([]);
    });

    test("/audition Stage Distribution still renders after Phase 5 changes", async ({ page }) => {
        const errors = captureConsoleErrors(page);
        await page.goto("/audition", { waitUntil: "networkidle" });
        await expect(page.getByRole("heading", { name: "Strategy Audition System" })).toBeVisible({ timeout: 15000 });
        await expect(page.getByText("SISDS Stage Distribution")).toBeVisible({ timeout: 10000 });
        for (const stage of ["birth", "sandbox", "paper", "live", "retired", "legacy"]) {
            await expect(page.getByText(stage, { exact: true })).toBeVisible({ timeout: 10000 });
        }
        expect(errors, `Console errors: ${errors.join('\n')}`).toEqual([]);
    });

    test("/audition summary cards intact after Phase 5 changes", async ({ page }) => {
        const errors = captureConsoleErrors(page);
        await page.goto("/audition", { waitUntil: "networkidle" });
        await expect(page.getByRole("heading", { name: "Strategy Audition System" })).toBeVisible({ timeout: 15000 });
        await expect(page.getByText("Graduated", { exact: true })).toBeVisible({ timeout: 10000 });
        await expect(page.getByText("Eliminated", { exact: true })).toBeVisible({ timeout: 10000 });
        expect(errors, `Console errors: ${errors.join('\n')}`).toEqual([]);
    });

    test("/audition pool table and Graveyard intact after Phase 5 changes", async ({ page }) => {
        const errors = captureConsoleErrors(page);
        await page.goto("/audition", { waitUntil: "networkidle" });
        await expect(page.locator("table")).toBeVisible({ timeout: 15000 });
        const rows = page.locator("table tbody tr");
        await expect(rows).toHaveCount(10, { timeout: 10000 });
        await expect(page.getByText("Graveyard — 탈락 풀", { exact: true })).toBeVisible({ timeout: 10000 });
        expect(errors, `Console errors: ${errors.join('\n')}`).toEqual([]);
    });

    test("promote-to-live endpoint returns 404 (not 500) for unknown id", async ({ request }) => {
        const r = await request.post("/api/v1/strategy-audition/test_id/promote-to-live");
        // 401 if auth required, 404 if not found — both acceptable, 500 is NOT
        expect(r.status(), `promote-to-live should not 500, got ${r.status()}`).not.toBe(500);
        expect([401, 403, 404], `expected 401/403/404, got ${r.status()}`).toContain(r.status());
    });

    test("reject-promotion endpoint returns 404 (not 500) for unknown id", async ({ request }) => {
        const r = await request.post("/api/v1/strategy-audition/test_id/reject-promotion");
        expect(r.status(), `reject-promotion should not 500, got ${r.status()}`).not.toBe(500);
        expect([401, 403, 404], `expected 401/403/404, got ${r.status()}`).toContain(r.status());
    });

    test("/workflow regression after Phase 5 changes", async ({ page }) => {
        const errors = captureConsoleErrors(page);
        await page.goto("/workflow", { waitUntil: "networkidle" });
        await expect(page.getByRole("heading", { name: "Agent Workflow — Live Execution" })).toBeVisible({ timeout: 15000 });
        expect(errors, `Console errors: ${errors.join('\n')}`).toEqual([]);
    });

    test("/organization regression after Phase 5 changes", async ({ page }) => {
        const errors = captureConsoleErrors(page);
        await page.goto("/organization", { waitUntil: "networkidle" });
        await expect(page.getByRole("heading", { name: /조직도|Organization/i })).toBeVisible({ timeout: 10000 });
        const flowPane = page.locator(".react-flow").first();
        await expect(flowPane).toBeVisible({ timeout: 10000 });
        expect(errors, `Console errors: ${errors.join('\n')}`).toEqual([]);
    });
});

// SISDS Phase 7 Calibration Dashboard tests (CIO-20260408-018)
test.describe("SISDS Phase 7 Calibration Dashboard (CIO-20260408-018)", () => {

    test("/calibration route renders Calibration Dashboard heading", async ({ page }) => {
        const errors = captureConsoleErrors(page);
        await page.goto('/calibration', { waitUntil: 'networkidle' });
        await expect(page.getByRole('heading', { name: 'Calibration Dashboard' })).toBeVisible({ timeout: 15000 });
        expect(errors, `Console errors: ${errors.join('\n')}`).toEqual([]);
    });

    test("/calibration NavBar shows CIR link", async ({ page }) => {
        const errors = captureConsoleErrors(page);
        await page.goto('/', { waitUntil: 'networkidle' });
        const navLink = page.locator('a[href="/calibration"]');
        await expect(navLink).toBeVisible();
        await expect(navLink).toHaveText('CIR');
        expect(errors, `Console errors: ${errors.join('\n')}`).toEqual([]);
    });

    test("/calibration shows 4 BigMetric cards", async ({ page }) => {
        const errors = captureConsoleErrors(page);
        await page.goto('/calibration', { waitUntil: 'networkidle' });
        await expect(page.getByRole('heading', { name: 'Calibration Dashboard' })).toBeVisible({ timeout: 15000 });
        await expect(page.getByText('System Health')).toBeVisible({ timeout: 10000 });
        await expect(page.getByText('Overall Avg Error')).toBeVisible({ timeout: 10000 });
        await expect(page.getByText('Recent 30d Error')).toBeVisible({ timeout: 10000 });
        await expect(page.locator('main').getByText('CIR', { exact: true })).toBeVisible({ timeout: 10000 });
        expect(errors, `Console errors: ${errors.join('\n')}`).toEqual([]);
    });

    test("/calibration no-data state: health=NO_DATA, dashes for metrics", async ({ page }) => {
        const errors = captureConsoleErrors(page);
        await page.goto('/calibration', { waitUntil: 'networkidle' });
        await expect(page.getByRole('heading', { name: 'Calibration Dashboard' })).toBeVisible({ timeout: 15000 });
        await expect(page.getByText('NO_DATA')).toBeVisible({ timeout: 10000 });
        const dashes = page.getByText('\u2014');
        await expect(dashes.first()).toBeVisible({ timeout: 10000 });
        expect(errors, `Console errors: ${errors.join('\n')}`).toEqual([]);
    });

    test("/calibration shows no-data message or empty chart without crash", async ({ page }) => {
        const errors = captureConsoleErrors(page);
        await page.goto('/calibration', { waitUntil: 'networkidle' });
        await expect(page.getByRole('heading', { name: 'Calibration Dashboard' })).toBeVisible({ timeout: 15000 });
        const body = await page.locator('body').textContent();
        expect(body.trim().length).toBeGreaterThan(50);
        const noRecords = page.getByText(/No calibration records yet|no calibration/i);
        const hasNoRecords = await noRecords.count() > 0;
        if (!hasNoRecords) {
            const dashboard = page.locator('text=Calibration Dashboard');
            await expect(dashboard).toBeVisible();
        }
        expect(errors, `Console errors: ${errors.join('\n')}`).toEqual([]);
    });

    test("/calibration footer shows READ-ONLY text", async ({ page }) => {
        const errors = captureConsoleErrors(page);
        await page.goto('/calibration', { waitUntil: 'networkidle' });
        await expect(page.getByRole('heading', { name: 'Calibration Dashboard' })).toBeVisible({ timeout: 15000 });
        await expect(page.locator('div.text-xs.text-gray-500').filter({ hasText: 'READ-ONLY' }).first()).toBeVisible({ timeout: 10000 });
        expect(errors, `Console errors: ${errors.join('\n')}`).toEqual([]);
    });

    test("Calibration API /api/v1/calibration/summary responds 200 with health key", async ({ request }) => {
        const r = await request.get('/api/v1/calibration/summary');
        expect(r.status()).toBe(200);
        const body = await r.json();
        expect(body).toHaveProperty('health');
    });

    test("Calibration API /api/v1/calibration/trend responds 200 with interpretation key", async ({ request }) => {
        const r = await request.get('/api/v1/calibration/trend');
        expect(r.status()).toBe(200);
        const body = await r.json();
        expect(body).toHaveProperty('interpretation');
    });

    test("/audition regression after Calibration addition", async ({ page }) => {
        const errors = captureConsoleErrors(page);
        await page.goto('/audition', { waitUntil: 'networkidle' });
        await expect(page.getByRole('heading', { name: 'Strategy Audition System' })).toBeVisible({ timeout: 15000 });
        await expect(page.getByText('Graduated', { exact: true })).toBeVisible({ timeout: 10000 });
        await expect(page.getByText('Eliminated', { exact: true })).toBeVisible({ timeout: 10000 });
        expect(errors, `Console errors: ${errors.join('\n')}`).toEqual([]);
    });

    test("/workflow regression after Calibration addition", async ({ page }) => {
        const errors = captureConsoleErrors(page);
        await page.goto('/workflow', { waitUntil: 'networkidle' });
        await expect(page.getByRole('heading', { name: 'Agent Workflow — Live Execution' })).toBeVisible({ timeout: 15000 });
        expect(errors, `Console errors: ${errors.join('\n')}`).toEqual([]);
    });

    test("/organization regression after Calibration addition", async ({ page }) => {
        const errors = captureConsoleErrors(page);
        await page.goto('/organization', { waitUntil: 'networkidle' });
        await expect(page.getByRole('heading', { name: /조직도|Organization/i })).toBeVisible({ timeout: 10000 });
        const flowPane = page.locator('.react-flow').first();
        await expect(flowPane).toBeVisible({ timeout: 10000 });
        expect(errors, `Console errors: ${errors.join('\n')}`).toEqual([]);
    });
});
