import { test, expect } from "@playwright/test";

// Runs under the "unauthenticated" project — no stored auth state

test("unauthenticated visit to /home redirects to /login", async ({ page }) => {
  await page.goto("/home");
  await expect(page).toHaveURL(/\/login/, { timeout: 10_000 });
});

test("unauthenticated visit to /drafts redirects to /login", async ({ page }) => {
  await page.goto("/drafts");
  await expect(page).toHaveURL(/\/login/, { timeout: 10_000 });
});

test("unauthenticated visit to /projects redirects to /login", async ({ page }) => {
  await page.goto("/projects");
  await expect(page).toHaveURL(/\/login/, { timeout: 10_000 });
});

test("login page renders Clerk sign-in form", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByLabel(/email address/i)).toBeVisible();
});

test("root redirects unauthenticated users to landing page", async ({ page }) => {
  await page.goto("/");
  // Landing page should be visible — not redirected to /home
  await expect(page).not.toHaveURL(/\/home/);
});

// #549 — SVG favicon (#551)
test("favicon link element is present in page head (#551)", async ({ page }) => {
  await page.goto("/");
  const href = await page.locator('link[rel="icon"]').getAttribute("href");
  expect(href, "favicon <link rel=icon> must have an href").toBeTruthy();
  expect(href, "favicon must be an SVG file").toMatch(/\.svg$/i);
});

test("favicon SVG file resolves with correct content-type (#551)", async ({ page }) => {
  await page.goto("/");
  const href = await page.locator('link[rel="icon"]').getAttribute("href");
  if (!href) {
    test.skip(true, "No favicon link found");
    return;
  }
  const resp = await page.request.get(href);
  expect(resp.ok(), `favicon at ${href} must return 200`).toBe(true);
  expect(resp.headers()["content-type"], "favicon must be served as SVG").toContain("svg");
});
