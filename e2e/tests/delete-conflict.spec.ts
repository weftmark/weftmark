import { test, expect } from "../fixtures";

// Runs under the "authenticated" project.
// Both eqauser's seeded draft and seeded loom are linked to the seeded
// "EQA Fixture Project", so attempting to delete either always hits the
// 409 conflict path. We only ever cancel out of the confirm-force-delete
// state -- never actually force-delete -- so the fixture project survives
// for other tests / runs.
const SEEDED_DRAFT_ID = "86e64447-378d-4ac5-9a06-644bb0a24351";
const SEEDED_LOOM_ID = "c45670c9-5341-4902-a654-0d2ab34e380b";
// The panel renders each blocking project as "· <name>" list items; matching
// that exact bullet form avoids colliding with the project name shown
// elsewhere on the page (e.g. the related-projects list).
const FIXTURE_PROJECT_BULLET = "· EQA Fixture Project";

test.describe("Delete-conflict panel (#1053, shared DeleteConflictPanel)", () => {
  test("draft delete shows the conflict panel naming the blocking project, and cancel dismisses it", async ({ page }) => {
    await page.goto(`/drafts/${SEEDED_DRAFT_ID}`);
    await expect(page.locator("body")).not.toContainText("Loading…");

    await page.getByRole("button", { name: /danger zone/i }).click();
    await page.getByRole("button", { name: /^delete draft$/i }).click();
    await page.getByRole("button", { name: /^confirm delete$/i }).click();

    await expect(page.getByText(/used by 1 active project/i)).toBeVisible();
    await expect(page.getByText(FIXTURE_PROJECT_BULLET)).toBeVisible();

    await page.getByRole("button", { name: /force delete/i }).click();
    await expect(page.getByRole("button", { name: /^confirm force delete$/i })).toBeVisible();

    await page.getByRole("button", { name: /^cancel$/i }).click();
    await expect(page.getByText(/used by 1 active project/i)).not.toBeVisible();

    // Fixture must survive: reload and confirm the draft is still there.
    await page.reload();
    await expect(page.locator("body")).not.toContainText("Loading…");
    await expect(page).toHaveURL(new RegExp(SEEDED_DRAFT_ID));
  });

  test("loom delete shows the conflict panel naming the blocking project, and cancel dismisses it", async ({ page }) => {
    await page.goto(`/looms/${SEEDED_LOOM_ID}`);
    await expect(page.locator("body")).not.toContainText("Loading…");

    await page.getByRole("button", { name: /danger zone/i }).click();
    await page.getByRole("button", { name: /^delete loom$/i }).click();
    await page.getByRole("button", { name: /^confirm delete$/i }).click();

    await expect(page.getByText(/used by 1 active project/i)).toBeVisible();
    await expect(page.getByText(FIXTURE_PROJECT_BULLET)).toBeVisible();

    await page.getByRole("button", { name: /force delete/i }).click();
    await expect(page.getByRole("button", { name: /^confirm force delete$/i })).toBeVisible();

    await page.getByRole("button", { name: /^cancel$/i }).click();
    await expect(page.getByText(/used by 1 active project/i)).not.toBeVisible();

    // Fixture must survive: reload and confirm the loom is still there.
    await page.reload();
    await expect(page.locator("body")).not.toContainText("Loading…");
    await expect(page).toHaveURL(new RegExp(SEEDED_LOOM_ID));
  });
});
