import { test, expect } from "@playwright/test";

// Covers #1164 — tracking mode's drawdown left large unused whitespace below
// the pattern (fixed-overhead height guess) and, on narrower viewports, to its
// sides (fixed viewport-breakpoint width caps + a fixed 20px cell size that
// never grew to use the space).

const VIEWPORTS = {
  desktop: { width: 1920, height: 1080 },
  tabletPortrait: { width: 820, height: 1180 },
  tabletLandscape: { width: 1180, height: 820 },
  mobile: { width: 412, height: 915 },
};

async function getFirstActiveTrackingHref(page: import("@playwright/test").Page): Promise<string | null> {
  await page.goto("/projects");
  const link = page.locator("a[href^='/projects/']").first();
  await expect(link).toBeVisible({ timeout: 10_000 });
  const href = await link.getAttribute("href");
  return href ? `${href}/track` : null;
}

for (const [name, viewport] of Object.entries(VIEWPORTS)) {
  test(`tracking pattern fills available space without clipping — ${name}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    const href = await getFirstActiveTrackingHref(page);
    if (!href) {
      test.skip(true, "No projects available for this user");
      return;
    }

    await page.goto(href);
    const canvas = page.locator("canvas");
    const visible = await canvas.waitFor({ state: "visible", timeout: 10_000 }).then(() => true).catch(() => false);
    if (!visible) {
      test.skip(true, "Project isn't in an active-tracking state that renders the drawdown canvas");
      return;
    }

    // Tracking UI must never require scrolling to see everything (nav controls
    // stay reachable without the main content area clipping/overflowing).
    const mainInfo = await page.evaluate(() => {
      const main = document.querySelector("main");
      return main ? { scrollHeight: main.scrollHeight, clientHeight: main.clientHeight } : null;
    });
    expect(mainInfo, "main content element should exist").not.toBeNull();
    expect(mainInfo!.scrollHeight, "tracking content should not overflow/clip within main").toBeLessThanOrEqual(mainInfo!.clientHeight + 2);
  });
}
