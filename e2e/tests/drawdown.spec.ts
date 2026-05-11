import { test, expect } from "../fixtures";

// Verifies drawdown tile rendering end-to-end for project detail pages.
// Covers QA gaps from PRs #552 (R2 cache), #573 (project tiles), #575 (column slicing).

const TILE_ROW_COUNT = 100; // must match backend TILE_ROW_COUNT and frontend constant
const TILE_COL_COUNT = 200; // must match backend TILE_COL_COUNT and frontend constant

async function getFirstProjectHref(page: import("@playwright/test").Page): Promise<string | null> {
  await page.goto("/projects");
  const link = page.locator("a[href^='/projects/']").first();
  if (!(await link.isVisible({ timeout: 5_000 }).catch(() => false))) return null;
  return link.getAttribute("href");
}

// ---------------------------------------------------------------------------
// Request parameters
// ---------------------------------------------------------------------------

test("drawdown tile requests carry correct row/col parameters (#573 #575)", async ({ page }) => {
  const href = await getFirstProjectHref(page);
  if (!href) {
    test.skip(true, "No projects available for this user");
    return;
  }
  const projectId = href.split("/").pop()!;

  const tileUrls: string[] = [];
  page.on("response", (r) => {
    if (r.url().includes(`/api/projects/${projectId}/drawdown`)) {
      tileUrls.push(r.url());
    }
  });

  await page.goto(href);
  await page.waitForTimeout(4_000);

  if (tileUrls.length === 0) {
    test.skip(true, "No drawdown tiles were requested — project may have no draft");
    return;
  }

  const firstUrl = new URL(tileUrls[0]);
  expect(firstUrl.searchParams.get("row_count"), "row_count must be TILE_ROW_COUNT").toBe(String(TILE_ROW_COUNT));
  expect(firstUrl.searchParams.get("col_count"), "col_count must be TILE_COL_COUNT").toBe(String(TILE_COL_COUNT));
  expect(firstUrl.searchParams.has("start_row"), "start_row param must be present").toBe(true);
  expect(firstUrl.searchParams.has("start_col"), "start_col param must be present").toBe(true);
  expect(parseInt(firstUrl.searchParams.get("start_row")!), "start_row must align to tile boundary").toBe(
    Math.floor(parseInt(firstUrl.searchParams.get("start_row")!) / TILE_ROW_COUNT) * TILE_ROW_COUNT,
  );
});

// ---------------------------------------------------------------------------
// Response shape
// ---------------------------------------------------------------------------

test("drawdown tile response is 200 image/png with metadata headers (#573)", async ({ page }) => {
  const href = await getFirstProjectHref(page);
  if (!href) {
    test.skip(true, "No projects available for this user");
    return;
  }
  const projectId = href.split("/").pop()!;

  const tileResponseP = page.waitForResponse(
    (r) => r.url().includes(`/api/projects/${projectId}/drawdown`) && r.status() === 200,
    { timeout: 15_000 },
  );

  await page.goto(href);
  const resp = await tileResponseP;
  const headers = resp.headers();

  expect(resp.status()).toBe(200);
  expect(headers["content-type"]).toContain("image/png");

  // Metadata headers the frontend relies on to position tiles
  expect(headers["x-pixels-per-row"], "X-Pixels-Per-Row must be present").toBeTruthy();
  expect(headers["x-total-cols"], "X-Total-Cols must be present").toBeTruthy();
  expect(headers["x-total-rows"], "X-Total-Rows must be present").toBeTruthy();
  expect(headers["x-start-row"], "X-Start-Row must be present").toBeTruthy();
  expect(headers["x-row-count"], "X-Row-Count must be present").toBeTruthy();

  expect(parseInt(headers["x-pixels-per-row"]), "X-Pixels-Per-Row must be positive").toBeGreaterThan(0);
  expect(parseInt(headers["x-total-cols"]), "X-Total-Cols must be positive").toBeGreaterThan(0);
  expect(parseInt(headers["x-row-count"]), "X-Row-Count must be ≤ TILE_ROW_COUNT").toBeLessThanOrEqual(TILE_ROW_COUNT);
});

// ---------------------------------------------------------------------------
// Column-slice headers (#575)
// ---------------------------------------------------------------------------

test("column-sliced drawdown response carries X-Start-Col and X-Col-Count headers (#575)", async ({ page }) => {
  const href = await getFirstProjectHref(page);
  if (!href) {
    test.skip(true, "No projects available for this user");
    return;
  }
  const projectId = href.split("/").pop()!;

  // Collect all tile responses — we need one that was served live (not cached) because
  // the R2 cached path omits X-Start-Col/X-Col-Count. Live renders always include them.
  const liveResponses: import("@playwright/test").Response[] = [];
  page.on("response", async (r) => {
    if (
      r.url().includes(`/api/projects/${projectId}/drawdown`) &&
      r.status() === 200 &&
      r.headers()["cache-control"] === "no-store"
    ) {
      liveResponses.push(r);
    }
  });

  await page.goto(href);
  await page.waitForTimeout(5_000);

  if (liveResponses.length === 0) {
    // All tiles were served from R2 cache — skip rather than fail.
    // Column-slice headers are only on live renders.
    test.skip(true, "All tiles served from cache; no live render to inspect for X-Start-Col header");
    return;
  }

  const h = liveResponses[0].headers();
  expect(h["x-start-col"], "X-Start-Col must be present on live column-sliced responses").toBeTruthy();
  expect(h["x-col-count"], "X-Col-Count must be present on live column-sliced responses").toBeTruthy();
  expect(parseInt(h["x-col-count"]), "X-Col-Count must be ≤ TILE_COL_COUNT").toBeLessThanOrEqual(TILE_COL_COUNT);
});

// ---------------------------------------------------------------------------
// Cache-Control correctness (#552)
// ---------------------------------------------------------------------------

test("cached drawdown tiles carry immutable Cache-Control (#552)", async ({ page }) => {
  const href = await getFirstProjectHref(page);
  if (!href) {
    test.skip(true, "No projects available for this user");
    return;
  }
  const projectId = href.split("/").pop()!;

  const cacheStatuses: string[] = [];
  page.on("response", (r) => {
    if (r.url().includes(`/api/projects/${projectId}/drawdown`) && r.status() === 200) {
      cacheStatuses.push(r.headers()["cache-control"] ?? "missing");
    }
  });

  await page.goto(href);
  await page.waitForTimeout(5_000);

  if (cacheStatuses.length === 0) {
    test.skip(true, "No drawdown tiles were requested");
    return;
  }

  // Every tile must be either immutable (R2 cache hit) or no-store (live render).
  // Neither should be missing, empty, or some other value.
  for (const cc of cacheStatuses) {
    expect(
      cc === "public, max-age=31536000, immutable" || cc === "no-store",
      `Unexpected Cache-Control: "${cc}"`,
    ).toBe(true);
  }
});

// ---------------------------------------------------------------------------
// Rendered tile dimensions (#573 — "correct size")
// ---------------------------------------------------------------------------

test("rendered drawdown tile pixel dimensions match response headers (#573)", async ({ page }) => {
  const href = await getFirstProjectHref(page);
  if (!href) {
    test.skip(true, "No projects available for this user");
    return;
  }
  const projectId = href.split("/").pop()!;

  let pixelsPerRow = 0;
  let rowCount = 0;
  let totalCols = 0;
  let colCount = 0;

  const tileResponseP = page.waitForResponse(
    (r) => r.url().includes(`/api/projects/${projectId}/drawdown`) && r.status() === 200,
    { timeout: 15_000 },
  );

  await page.goto(href);
  const resp = await tileResponseP;
  const h = resp.headers();

  pixelsPerRow = parseInt(h["x-pixels-per-row"] ?? "0");
  rowCount = parseInt(h["x-row-count"] ?? "0");
  totalCols = parseInt(h["x-total-cols"] ?? "0");
  // For a column-sliced live render, X-Col-Count is the tile width in threads.
  // For a cached full-width tile, fall back to X-Total-Cols.
  colCount = parseInt(h["x-col-count"] ?? String(totalCols));

  if (pixelsPerRow === 0 || rowCount === 0 || colCount === 0) {
    test.skip(true, "Could not read tile dimension headers");
    return;
  }

  const expectedHeight = rowCount * pixelsPerRow;
  const expectedWidth = colCount * pixelsPerRow;

  // Wait for at least one blob img to be rendered in the drawdown container
  const blobImg = page.locator("img[src^='blob:']").first();
  await blobImg.waitFor({ state: "visible", timeout: 10_000 });

  const dims = await blobImg.evaluate((el) => ({
    w: (el as HTMLImageElement).naturalWidth,
    h: (el as HTMLImageElement).naturalHeight,
  }));

  expect(dims.w, "tile naturalWidth must be positive").toBeGreaterThan(0);
  expect(dims.h, "tile naturalHeight must be positive").toBeGreaterThan(0);
  expect(dims.h, `tile height must equal X-Row-Count(${rowCount}) × X-Pixels-Per-Row(${pixelsPerRow})`).toBe(expectedHeight);
  expect(dims.w, `tile width must equal col_count(${colCount}) × X-Pixels-Per-Row(${pixelsPerRow})`).toBe(expectedWidth);
});
