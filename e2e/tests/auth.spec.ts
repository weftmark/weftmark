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
