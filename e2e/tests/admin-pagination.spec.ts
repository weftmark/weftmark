import { test, expect } from "../fixtures";

// Runs under the "admin" project (storageState: .auth/admin.json)
// Covers the shared Pager extracted from AdminPage.tsx's ServerEventsPanel and
// AuditLogTab (#1053 duplication cleanup). Both panels only render pagination
// controls once there's more than one page of data, so these gracefully skip
// on a fresh environment rather than depending on seeded event/audit volume.

test("server events pagination advances and retreats a page (#1053)", async ({ page }) => {
  await page.goto("/admin/services");
  await expect(page).toHaveURL(/\/admin\/services/);
  await expect(page.getByText("Server Events Log")).toBeVisible({ timeout: 10_000 });

  const nextBtn = page.getByRole("button", { name: "→" }).first();
  const hasPagination = await nextBtn.isVisible({ timeout: 5_000 }).catch(() => false);
  if (!hasPagination) {
    test.skip(true, "Not enough server events for pagination to render");
    return;
  }

  const pageLabel = page.getByText(/^Page \d+ of \d+$/).first();
  await expect(pageLabel).toHaveText(/^Page 1 of \d+$/);

  await nextBtn.click();
  await expect(pageLabel).toHaveText(/^Page 2 of \d+$/);

  const prevBtn = page.getByRole("button", { name: "←" }).first();
  await prevBtn.click();
  await expect(pageLabel).toHaveText(/^Page 1 of \d+$/);
});

test("audit log pagination advances and retreats a page (#1053)", async ({ page }) => {
  await page.goto("/admin/audit");
  await expect(page).toHaveURL(/\/admin\/audit/);
  await expect(page.getByText("Audit Log")).toBeVisible({ timeout: 10_000 });

  const nextBtn = page.getByRole("button", { name: "→" }).first();
  const hasPagination = await nextBtn.isVisible({ timeout: 5_000 }).catch(() => false);
  if (!hasPagination) {
    test.skip(true, "Not enough audit log entries for pagination to render");
    return;
  }

  const pageLabel = page.getByText(/^Page \d+ of \d+$/).first();
  await expect(pageLabel).toHaveText(/^Page 1 of \d+$/);

  await nextBtn.click();
  await expect(pageLabel).toHaveText(/^Page 2 of \d+$/);

  const prevBtn = page.getByRole("button", { name: "←" }).first();
  await prevBtn.click();
  await expect(pageLabel).toHaveText(/^Page 1 of \d+$/);
});
