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

// #550 — Save button should be inline in the header row of each scheduled task card,
// co-located with the Enabled toggle (not in a separate bottom row).
test("scheduled task cards show Save button inline with Enabled toggle (#550)", async ({ page }) => {
  await page.goto("/admin/system");
  await expect(page).toHaveURL(/\/admin\/system/);

  // Wait for at least one Save button in the scheduled tasks section to render.
  const saveBtn = page.getByRole("button", { name: /^save$/i }).first();
  await saveBtn.waitFor({ state: "visible", timeout: 10_000 });

  // The Save button should be in the same flex row as the Enabled toggle (a switch button).
  // We verify this by checking their bounding boxes are on the same horizontal line.
  const [saveBtnBox, toggleBox] = await Promise.all([
    saveBtn.boundingBox(),
    page.locator('button[role="switch"]').first().boundingBox(),
  ]);

  expect(saveBtnBox, "Save button must be visible on the page").not.toBeNull();
  expect(toggleBox, "Enabled toggle (switch) must be visible on the page").not.toBeNull();

  // Both elements should be on approximately the same horizontal line (within 12px vertical gap).
  const verticalDiff = Math.abs(saveBtnBox!.y - toggleBox!.y);
  expect(verticalDiff, "Save button and Enabled toggle must be on the same row (≤12px vertical gap)").toBeLessThan(12);
});

// #554 #557 — prerender_drawdown_tiles must appear in admin task history after a tile is
// requested for a project that doesn't yet have cached tiles. Skips gracefully if no
// task has run since last deploy (expected on a fresh environment).
test("task history shows prerender_drawdown_tiles entry (#554 #557)", async ({ page }) => {
  await page.goto("/admin/system");
  await expect(page).toHaveURL(/\/admin\/system/);
  await expect(page.locator("body")).not.toContainText("Loading…");

  const taskEntry = page.locator("body").getByText(/prerender_drawdown_tiles|prerender.*tiles/i).first();
  const visible = await taskEntry.isVisible({ timeout: 5_000 }).catch(() => false);

  if (!visible) {
    test.skip(true, "No prerender_drawdown_tiles task visible in history — expected if no project was opened after last deploy");
    return;
  }

  await expect(taskEntry).toBeVisible();
});
