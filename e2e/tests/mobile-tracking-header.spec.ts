import { test, expect } from "@playwright/test";

// Covers #1168 — tracking mode on mobile portrait stacked AppLayout's own
// mobile bar (hamburger + feedback) on top of the page's full toolbar,
// wasting vertical space. They're now combined into one row on this route
// only: hamburger | project name | overflow menu (everything else).
//
// Two "Open navigation" buttons exist in the DOM at once below lg (one in
// the compact header, one added to the standard toolbar for the sm..lg
// gap) — only one is CSS-visible at a given width. getByLabel() matches by
// DOM presence, not visibility, so tests below scope to the visible one
// explicitly rather than relying on count() alone.

const MOBILE = { width: 412, height: 915 };
const visibleHamburger = (page: import("@playwright/test").Page) =>
  page.locator('button[aria-label="Open navigation"]:visible');

async function getFirstActiveTrackingHref(page: import("@playwright/test").Page): Promise<string | null> {
  await page.goto("/projects");
  const link = page.locator("a[href^='/projects/']").first();
  await expect(link).toBeVisible({ timeout: 10_000 });
  const href = await link.getAttribute("href");
  return href ? `${href}/track` : null;
}

test("tracking mode shows exactly one visible mobile nav bar (combined header)", async ({ page }) => {
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

  // AppLayout's own mobile bar must be suppressed here — only the compact
  // header's hamburger should be visible, not two stacked bars.
  await expect(visibleHamburger(page)).toHaveCount(1);
});

test("non-tracking pages keep AppLayout's own mobile bar", async ({ page }) => {
  await page.setViewportSize(MOBILE);
  await page.goto("/home");
  await expect(page.getByLabel("Open navigation")).toBeVisible({ timeout: 10_000 });
  await expect(page.getByLabel("Open navigation")).toHaveCount(1);
  await expect(page.getByLabel("Send feedback")).toBeVisible();
});

// Regression for a gap this fix introduced: AppLayout's mobile bar (which
// used to cover any width below lg/1024px) is fully suppressed on /track,
// but the compact header only replaces it below sm/640px. Tablet-portrait
// widths (e.g. ~820px) sit in that sm..lg gap — the sidebar is still an
// overlay there (not static until lg), so the standard toolbar must supply
// its own hamburger for that range or the sidebar becomes unreachable.
test("tablet-portrait width (sm..lg gap) still has a working hamburger", async ({ page }) => {
  await page.setViewportSize({ width: 820, height: 1180 });
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

  const hamburger = visibleHamburger(page);
  await expect(hamburger).toHaveCount(1);
  await hamburger.click();
  await expect(page.getByRole("link", { name: /dashboard/i })).toBeVisible();
});
