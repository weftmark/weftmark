import { test, expect } from "../fixtures";

// Runs under the "admin" project (storageState: .auth/admin.json)

test("admin user can reach /admin/users", async ({ page }) => {
  await page.goto("/admin/users");
  await expect(page).toHaveURL(/\/admin\/users/);
  await expect(page.locator("body")).not.toContainText("Loading…");
});

test("admin user sees user list rendered", async ({ page }) => {
  await page.goto("/admin/users");
  await expect(page).toHaveURL(/\/admin\/users/);
  // Page heading confirms the right section loaded
  await expect(
    page.locator("h1, h2").filter({ hasText: /users/i }).first(),
  ).toBeVisible({ timeout: 10_000 });
});

test("admin health endpoint returns ok", async ({ request }) => {
  const resp = await request.get("/health");
  expect(resp.ok()).toBe(true);
});

test("admin user can reach /admin/system", async ({ page }) => {
  await page.goto("/admin/system");
  await expect(page).toHaveURL(/\/admin\/system/);
  await expect(page.locator("body")).not.toContainText("Loading…");
});
