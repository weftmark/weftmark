import { test, expect } from "../fixtures";

// Runs under the "authenticated" project.
// Exercises the shared TagFilterBar extracted from DraftsPage/ProjectsPage
// (#1053). eqauser's seeded fixtures have no tags by default, so this test
// tags the seeded draft via a direct authenticated API call (using the
// browser's own Clerk session token), drives the real filter UI, then
// restores the draft to its original tagless state in a `finally` so the
// fixture is left exactly as found.
const SEEDED_DRAFT_ID = "86e64447-378d-4ac5-9a06-644bb0a24351";
const TEST_TAG = "e2e-tag-filter";

async function patchDraftTags(page: import("@playwright/test").Page, tags: string[]) {
  await page.waitForFunction(() => Boolean((window as unknown as { Clerk?: { session?: unknown } }).Clerk?.session));
  return page.evaluate(
    async ({ draftId, tags: t }) => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const token = await (window as any).Clerk.session.getToken();
      const res = await fetch(`/api/drafts/${draftId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ tags: t }),
      });
      if (!res.ok) throw new Error(`PATCH tags failed: ${res.status}`);
    },
    { draftId: SEEDED_DRAFT_ID, tags },
  );
}

test.describe("Tag filter bar (#1053, shared TagFilterBar)", () => {
  test("clicking a tag filters drafts, and clear removes the filter", async ({ page }) => {
    await page.goto("/drafts");
    await expect(page.locator("body")).not.toContainText("Loading…");

    await patchDraftTags(page, [TEST_TAG]);
    try {
      await page.reload();
      await expect(page.locator("body")).not.toContainText("Loading…");
      await page.getByTestId("draft-card").first().waitFor({ state: "visible", timeout: 10_000 });

      const unfilteredCount = await page.getByTestId("draft-card").count();
      expect(unfilteredCount).toBeGreaterThan(1);

      const tagButton = page.getByRole("button", { name: TEST_TAG, exact: true });
      await expect(tagButton).toBeVisible();
      await tagButton.click();

      await expect(page.getByTestId("draft-card")).toHaveCount(1);

      const clearButton = page.getByRole("button", { name: "Clear", exact: true });
      await expect(clearButton).toBeVisible();
      await clearButton.click();
      await expect(clearButton).not.toBeVisible();
      await expect(page.getByTestId("draft-card")).toHaveCount(unfilteredCount);
    } finally {
      await patchDraftTags(page, []);
    }
  });
});
