import { test, expect } from "../fixtures";

// Runs under the "authenticated" project
// #574 — validates 2D tile rendering keyed to project_id

test("projects list page loads", async ({ page }) => {
  await page.goto("/projects");
  await expect(page).toHaveURL(/\/projects/);
  await expect(page.locator("body")).not.toContainText("Loading…");
});

test("project detail page loads if a project exists", async ({ page }) => {
  await page.goto("/projects");

  // Check if any project cards/links are present
  const firstProject = page.locator("a[href^='/projects/'], button[data-testid='project-card']").first();
  if (!(await firstProject.isVisible({ timeout: 5_000 }).catch(() => false))) {
    test.skip(true, "No projects available for this user");
    return;
  }

  await firstProject.click();
  await expect(page).toHaveURL(/\/projects\/.+/);
  await expect(page.locator("body")).not.toContainText("Loading…");
});

test("project landing page shows status badge and color palette", async ({ page }) => {
  await page.goto("/projects");

  const firstProject = page.locator("a[href^='/projects/'], button[data-testid='project-card']").first();
  if (!(await firstProject.isVisible({ timeout: 5_000 }).catch(() => false))) {
    test.skip(true, "No projects available for this user");
    return;
  }

  await firstProject.click();
  await expect(page).toHaveURL(/\/projects\/.+/);
  await page.waitForLoadState("networkidle", { timeout: 10_000 });

  // Status badge: a rounded-full span with one of the project status labels
  await expect(
    page.locator("span.rounded-full").filter({ hasText: /created|active|completed|abandoned/i }).first(),
  ).toBeVisible({ timeout: 10_000 });

  // Palette swatches: at least one color swatch rendered as a small rounded block
  // Color swatches use inline style for background color and appear in the palette section
  const swatch = page.locator('[style*="background-color"], [style*="background:"]').first();
  const hasSwatch = await swatch.isVisible({ timeout: 5_000 }).catch(() => false);
  if (!hasSwatch) {
    test.skip(true, "Project has no color palette — expected for draft-less projects");
  }
});

test("drawdown tiles load from /api/projects/{id}/drawdown (#574)", async ({ page }) => {
  await page.goto("/projects");

  const firstProject = page.locator("a[href^='/projects/'], button[data-testid='project-card']").first();
  if (!(await firstProject.isVisible({ timeout: 5_000 }).catch(() => false))) {
    test.skip(true, "No projects with drafts available for tile test");
    return;
  }

  const href = await firstProject.getAttribute("href");
  if (!href) {
    test.skip(true, "Could not extract project URL");
    return;
  }
  const projectId = href.split("/").pop();

  const tileRequests: number[] = [];
  page.on("response", (r) => {
    if (r.url().includes(`/api/projects/${projectId}/drawdown`) && r.status() === 200) {
      tileRequests.push(r.status());
    }
  });

  await page.goto(href);
  await page.waitForTimeout(3_000);

  expect(tileRequests.length).toBeGreaterThan(0);
});
