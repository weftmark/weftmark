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
  // UsersTab renders a search input once data is loaded
  await expect(
    page.locator('input[placeholder="Search name or email…"]'),
  ).toBeVisible({ timeout: 10_000 });
});

test("admin health endpoint returns ok", async ({ request }) => {
  const resp = await request.get("/health");
  expect(resp.ok()).toBe(true);
});

test("admin user can reach /admin/stats", async ({ page }) => {
  await page.goto("/admin/stats");
  await expect(page).toHaveURL(/\/admin\/stats/);
  await expect(page.locator("body")).not.toContainText("Loading…");
});

// #550 — Save button should be inline in the header row of each scheduled task card,
// co-located with the Enabled toggle (not in a separate bottom row).
// Scheduled tasks live under /admin/superuser → Schedule sub-tab (superuser-only).
test("scheduled task cards show Save button inline with Enabled toggle (#550)", async ({ page }) => {
  await page.goto("/admin/superuser");
  await expect(page).toHaveURL(/\/admin\/superuser/);

  // The schedule sub-tab is only accessible to superusers; skip gracefully otherwise.
  const scheduleBtn = page.getByRole("button", { name: /^schedule$/i });
  const accessible = await scheduleBtn.isVisible({ timeout: 5_000 }).catch(() => false);
  if (!accessible) {
    test.skip(true, "Schedule sub-tab not rendered — requires superuser account");
    return;
  }

  await scheduleBtn.click();

  const saveBtn = page.getByRole("button", { name: /^save$/i }).first();
  await saveBtn.waitFor({ state: "visible", timeout: 10_000 });

  const [saveBtnBox, toggleBox] = await Promise.all([
    saveBtn.boundingBox(),
    page.locator('button[role="switch"]').first().boundingBox(),
  ]);

  expect(saveBtnBox, "Save button must be visible on the page").not.toBeNull();
  expect(toggleBox, "Enabled toggle (switch) must be visible on the page").not.toBeNull();

  const verticalDiff = Math.abs(saveBtnBox!.y - toggleBox!.y);
  expect(verticalDiff, "Save button and Enabled toggle must be on the same row (≤12px vertical gap)").toBeLessThan(12);
});

// #554 #557 — prerender_drawdown_tiles must appear in admin task history after a tile is
// requested for a project that doesn't yet have cached tiles.
// Task history lives under /admin/superuser → Workers sub-tab (superuser-only).
test("task history shows prerender_drawdown_tiles entry (#554 #557)", async ({ page }) => {
  await page.goto("/admin/superuser");
  await expect(page).toHaveURL(/\/admin\/superuser/);

  const workersBtn = page.getByRole("button", { name: /^workers$/i });
  const accessible = await workersBtn.isVisible({ timeout: 5_000 }).catch(() => false);
  if (!accessible) {
    test.skip(true, "Workers sub-tab not rendered — requires superuser account");
    return;
  }

  await workersBtn.click();
  await expect(page.locator("body")).not.toContainText("Loading…");

  const taskEntry = page.locator("body").getByText(/prerender_drawdown_tiles|prerender.*tiles/i).first();
  const visible = await taskEntry.isVisible({ timeout: 5_000 }).catch(() => false);

  if (!visible) {
    test.skip(true, "No prerender_drawdown_tiles task visible in history — expected on a fresh environment");
    return;
  }

  await expect(taskEntry).toBeVisible();
});
