import { test, expect } from "../fixtures";
import path from "path";

// Runs under the "authenticated" project

test("drafts list page loads", async ({ page }) => {
  await page.goto("/drafts");
  await expect(page).toHaveURL(/\/drafts/);
  await expect(page.locator("body")).not.toContainText("Loading…");
});

test("upload a WIF file and confirm draft appears", async ({ page }) => {
  await page.goto("/drafts");

  const uploadResponse = page.waitForResponse(
    (r) => r.url().includes("/api/drafts") && r.request().method() === "POST",
  );

  // Open the upload modal (there may be two "New Draft" buttons — header and empty-state)
  await page.getByRole("button", { name: "New Draft" }).first().click();
  await expect(page.locator("h2").filter({ hasText: "New Draft" })).toBeVisible();

  // Fill in the required name field
  await page.getByLabel(/draft name/i).fill("E2E Test Draft");

  // Set the file directly on the file input (no file-chooser dialog needed)
  await page.locator('input[type="file"]').setInputFiles(
    path.join(__dirname, "../fixtures/sample.wif"),
  );

  // Submit — button becomes enabled once name + file are set
  await page.getByRole("button", { name: "Upload" }).click();

  const response = await uploadResponse;
  expect(response.status()).toBe(200);

  // Draft card should appear after upload
  await expect(page.locator("[data-testid='draft-card']").first()).toBeVisible({
    timeout: 10_000,
  });
});

test("draft detail page renders a preview image", async ({ page }) => {
  await page.goto("/drafts");

  const firstDraft = page.locator("[data-testid='draft-card']").first();
  if (!(await firstDraft.isVisible().catch(() => false))) {
    test.skip(true, "No drafts available — run the upload test first");
    return;
  }
  await firstDraft.click();
  await expect(page).toHaveURL(/\/drafts\/.+/);

  const preview = page.locator("[data-testid='draft-preview-img']");
  await expect(preview).toBeVisible({ timeout: 15_000 });
  const loaded = await preview.evaluate(
    (img) => (img as HTMLImageElement).naturalWidth > 0,
  );
  expect(loaded).toBe(true);
});
