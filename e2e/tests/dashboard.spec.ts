import { test, expect } from "../fixtures";

// Runs under the "authenticated" project

test("dashboard loads after sign-in", async ({ page }) => {
  await page.goto("/home");
  await expect(page).toHaveURL(/\/home/);
  await expect(page.locator("body")).not.toContainText("Loading…");
});

test("primary nav links are present", async ({ page }) => {
  await page.goto("/home");
  await expect(page.getByRole("link", { name: "Dashboard" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Equipment" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Drafts" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Projects" })).toBeVisible();
});

test("/settings/appearance loads", async ({ page }) => {
  await page.goto("/settings/appearance");
  await expect(page).toHaveURL(/\/settings\/appearance/);
  await expect(page.locator("body")).not.toContainText("Loading…");
});

test("non-admin user redirected from /admin to /unauthorized", async ({ page }) => {
  await page.goto("/admin/users");
  await expect(page).toHaveURL(/\/unauthorized/, { timeout: 10_000 });
});

test("yarn list page loads", async ({ page }) => {
  await page.goto("/yarn");
  await expect(page).toHaveURL(/\/yarn/);
  await expect(page.locator("body")).not.toContainText("Loading…");
});

test("yarn page has Add yarn button", async ({ page }) => {
  await page.goto("/yarn");
  await expect(page.getByRole("button", { name: /add yarn/i }).first()).toBeVisible();
});

test("Add yarn modal opens", async ({ page }) => {
  await page.goto("/yarn");
  await page.getByRole("button", { name: /add yarn/i }).first().click();
  await expect(page.locator("h2").filter({ hasText: /add yarn/i })).toBeVisible({ timeout: 5_000 });
});

test("equipment list page loads", async ({ page }) => {
  await page.goto("/looms");
  await expect(page).toHaveURL(/\/looms/);
  await expect(page.locator("body")).not.toContainText("Loading…");
});

test("equipment page has New loom button", async ({ page }) => {
  await page.goto("/looms");
  await expect(page.getByRole("button", { name: /new loom/i }).first()).toBeVisible();
});
