import { test, expect } from "../fixtures";
import path from "path";

// Runs under the "authenticated" project.
// Targets the eqauser fixture loom (seeded, see e2e/credentials) rather than
// creating a new one -- NewLoomModal has many conditional required fields
// depending on loom type, not worth reproducing here.
const SEEDED_LOOM_ID = "c45670c9-5341-4902-a654-0d2ab34e380b";

test.describe("Loom profile photo — resize/cancel workflow (#1053, #1079)", () => {
  test("uploading an oversized photo shows the resize/cancel prompt, and cancel dismisses it", async ({ page }) => {
    await page.goto(`/looms/${SEEDED_LOOM_ID}`);
    await expect(page.locator("body")).not.toContainText("Loading…");

    await page.locator('input[type="file"]').first().setInputFiles(
      path.join(__dirname, "../fixtures/oversized-test.png"),
    );

    const prompt = page.getByText(/over the 5 MB limit/i);
    await expect(prompt).toBeVisible();

    await page.getByRole("button", { name: /cancel/i }).first().click();
    await expect(prompt).not.toBeVisible();
  });

  test("resizing an oversized photo uploads successfully", async ({ page }) => {
    await page.goto(`/looms/${SEEDED_LOOM_ID}`);
    await expect(page.locator("body")).not.toContainText("Loading…");

    await page.locator('input[type="file"]').first().setInputFiles(
      path.join(__dirname, "../fixtures/oversized-test.png"),
    );
    await expect(page.getByText(/over the 5 MB limit/i)).toBeVisible();

    const uploadResponse = page.waitForResponse(
      (r) => r.url().includes("/photo") && ["POST", "PUT"].includes(r.request().method()),
    );
    await page.getByRole("button", { name: /resize.*upload/i }).click();

    const response = await uploadResponse;
    expect(response.ok()).toBe(true);

    // Prompt should be gone and no error shown after a successful resize+upload
    await expect(page.getByText(/over the 5 MB limit/i)).not.toBeVisible();
    await expect(page.getByText(/resize failed|upload failed/i)).not.toBeVisible();
  });

  test("uploading a normal-sized photo does not show the resize prompt", async ({ page }) => {
    await page.goto(`/looms/${SEEDED_LOOM_ID}`);
    await expect(page.locator("body")).not.toContainText("Loading…");

    const uploadResponse = page.waitForResponse(
      (r) => r.url().includes("/photo") && ["POST", "PUT"].includes(r.request().method()),
    );
    await page.locator('input[type="file"]').first().setInputFiles(
      path.join(__dirname, "../fixtures/small-test.png"),
    );

    const response = await uploadResponse;
    expect(response.ok()).toBe(true);
    await expect(page.getByText(/over the 5 MB limit/i)).not.toBeVisible();
  });
});
