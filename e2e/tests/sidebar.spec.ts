import { test, expect } from "@playwright/test";

// Covers #1161 — Settings highlighted but didn't expand on project detail pages
// because the rail-collapsed submenu is gated by !desktopCollapsed while the
// toggle only flipped local expand state, never lifting the collapse.

test("Settings nav expands the collapsed rail on project detail pages (#1161)", async ({ page }) => {
  await page.goto("/projects");
  const link = page.locator("a[href^='/projects/']").first();
  await expect(link).toBeVisible({ timeout: 10_000 });
  const href = await link.getAttribute("href");
  if (!href) {
    test.skip(true, "No projects available for this user");
    return;
  }

  await page.goto(href);
  const settingsButton = page.getByRole("button", { name: /settings/i });
  await expect(settingsButton).toBeVisible({ timeout: 15_000 });

  const aside = page.locator("aside");
  await expect(aside).toHaveClass(/lg:w-14/);

  await settingsButton.click();

  await expect(aside).toHaveClass(/lg:w-60/);
  await expect(page.getByRole("link", { name: /appearance/i })).toBeVisible();
});
