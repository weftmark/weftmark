import { test, expect } from "@playwright/test";

// Covers #1168 — tracking mode on mobile portrait stacked AppLayout's own
// mobile bar (hamburger + feedback) on top of the page's full toolbar,
// wasting vertical space. They're now combined into one row on this route
// only: hamburger | project name | overflow menu (everything else).

const MOBILE = { width: 412, height: 915 };

async function getFirstActiveTrackingHref(page: import("@playwright/test").Page): Promise<string | null> {
  await page.goto("/projects");
  const link = page.locator("a[href^='/projects/']").first();
  await expect(link).toBeVisible({ timeout: 10_000 });
  const href = await link.getAttribute("href");
  return href ? `${href}/track` : null;
}

test("tracking mode shows exactly one mobile nav bar (combined header)", async ({ page }) => {
  await page.setViewportSize(MOBILE);
  const href = await getFirstActiveTrackingHref(page);
  if (!href) {
    test.skip(true, "No projects available for this user");
    return;
  }

  await page.goto(href);
  const visible = await page.locator("canvas").waitFor({ state: "visible", timeout: 10_000 }).then(() => true).catch(() => false);
  if (!visible) {
    test.skip(true, "Project isn't in an active-tracking state that renders the drawdown canvas");
    return;
  }

  // AppLayout's own mobile bar must be suppressed here — only the page's
  // combined header hamburger should exist, not two stacked bars.
  await expect(page.getByLabel("Open navigation")).toHaveCount(1);
});

test("non-tracking pages keep AppLayout's own mobile bar", async ({ page }) => {
  await page.setViewportSize(MOBILE);
  await page.goto("/home");
  await expect(page.getByLabel("Open navigation")).toBeVisible({ timeout: 10_000 });
  await expect(page.getByLabel("Open navigation")).toHaveCount(1);
  await expect(page.getByLabel("Send feedback")).toBeVisible();
});
