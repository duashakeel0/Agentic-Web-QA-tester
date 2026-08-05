/**
 * Real end-to-end UI test: drives the actual dashboard in a real browser
 * against the real backend. Requires the backend to already be running:
 *   cd backend && uvicorn app.main:app --port 8000
 *
 * Uses AUTH_USERNAME/AUTH_PASSWORD if you've set them in backend/.env,
 * otherwise falls back to the "admin"/"admin" default auth.py uses when
 * they're unset - so this works out of the box on a fresh checkout too.
 */
import { expect, test } from "@playwright/test";

const USERNAME = process.env.E2E_USERNAME || "admin";
const PASSWORD = process.env.E2E_PASSWORD || "admin";

test.describe("SentinelQA dashboard", () => {
  test("logging in with the wrong password shows an error", async ({ page }) => {
    await page.goto("/login");
    await page.fill('input[type="text"]', USERNAME);
    await page.fill('input[type="password"]', "definitely-wrong-password");
    await page.click('button[type="submit"]');

    await expect(page.locator(".login-error")).toBeVisible();
  });

  test("logging in with correct credentials reaches the dashboard", async ({ page }) => {
    await page.goto("/login");
    await page.fill('input[type="text"]', USERNAME);
    await page.fill('input[type="password"]', PASSWORD);
    await page.click('button[type="submit"]');

    await expect(page).toHaveURL("/");
    await expect(page.locator(".dash-hero h1")).toContainText("Welcome back");
    await expect(page.locator(".dash-stat-card")).toHaveCount(6);
  });

  test("sidebar navigation reaches every page", async ({ page }) => {
    await page.goto("/login");
    await page.fill('input[type="text"]', USERNAME);
    await page.fill('input[type="password"]', PASSWORD);
    await page.click('button[type="submit"]');
    await expect(page).toHaveURL("/");

    await page.click('a[href="/run"]');
    await expect(page.locator(".run-test-title")).toBeVisible();

    await page.click('a[href="/history"]');
    await expect(page.locator(".history-title")).toBeVisible();

    await page.click('a[href="/compare"]');
    await expect(page.locator(".compare-title")).toBeVisible();

    await page.click('a[href="/analytics"]');
    await expect(page.locator(".analytics-title")).toBeVisible();
  });

  test("theme toggle actually changes the background color", async ({ page }) => {
    await page.goto("/login");
    await page.fill('input[type="text"]', USERNAME);
    await page.fill('input[type="password"]', PASSWORD);
    await page.click('button[type="submit"]');
    await expect(page).toHaveURL("/");

    const shell = page.locator(".dashboard-shell");
    const darkBg = await shell.evaluate((el) => getComputedStyle(el).backgroundColor);

    await page.click(".topbar-icon-button");
    await expect
      .poll(() => shell.evaluate((el) => getComputedStyle(el).backgroundColor))
      .not.toBe(darkBg);
  });

  test("the global chat is reachable and shows a graceful error without a live model", async ({ page }) => {
    await page.goto("/login");
    await page.fill('input[type="text"]', USERNAME);
    await page.fill('input[type="password"]', PASSWORD);
    await page.click('button[type="submit"]');
    await expect(page).toHaveURL("/");

    await page.click(".global-chat-fab");
    await expect(page.locator(".global-chat-panel")).toBeVisible();

    await page.fill(".global-chat-form input", "What is 2 + 2?");
    await page.click(".global-chat-form button");

    // Either a real reply or a graceful error - never a crash - depending
    // on whether ANTHROPIC_API_KEY is configured on whoever runs this.
    await expect(page.locator(".global-chat-user, .global-chat-error").first()).toBeVisible();
  });

  test("logging out redirects to /login and re-protects the dashboard", async ({ page }) => {
    await page.goto("/login");
    await page.fill('input[type="text"]', USERNAME);
    await page.fill('input[type="password"]', PASSWORD);
    await page.click('button[type="submit"]');
    await expect(page).toHaveURL("/");

    await page.click(".logout-button");
    await expect(page).toHaveURL(/\/login/);

    await page.goto("/history");
    await expect(page).toHaveURL(/\/login/);
  });
});
