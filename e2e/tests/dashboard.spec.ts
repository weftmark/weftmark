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
