import { test as setup, type Page } from "@playwright/test";
import { clerkSetup, clerk, setupClerkTestingToken } from "@clerk/testing/playwright";
import path from "path";

const userFile = path.join(__dirname, "../.auth/user.json");
const adminFile = path.join(__dirname, "../.auth/admin.json");

const BASE_URL = process.env.E2E_BASE_URL || "http://localhost:3000";

// Fetch a Clerk testing token once for the whole setup run.
// This token is appended to Clerk FAPI requests to bypass bot-detection/CAPTCHA.
// Reads CLERK_SECRET_KEY and CLERK_PUBLISHABLE_KEY from the environment.
setup.beforeAll(async () => {
  await clerkSetup();
});

async function signIn(page: Page, email: string) {
  // Navigate to the app first so Clerk's JS SDK is loaded on the right origin.
  await page.goto(`${BASE_URL}/home`);

  // Install the FAPI route interceptor that adds __clerk_testing_token to every
  // Clerk API request. Must be done before Clerk.loaded resolves.
  await setupClerkTestingToken({ page });

  // Wait for Clerk's SDK to initialise on this page.
  await clerk.loaded({ page });

  // Sign in via the Clerk JS API — no UI, no redirect, no cross-domain hop.
  // clerk.signIn looks up the user by email, creates a sign-in token via the
  // Clerk Backend API, then calls window.Clerk.client.signIn.create({ strategy: "ticket" })
  // and window.Clerk.setActive() inside the browser context.
  await clerk.signIn({ page, emailAddress: email });

  // Wait for AuthContext's /auth/me to complete and the authenticated app to render.
  // We can't use networkidle here because TanStack Query background refetches keep
  // the network active indefinitely. Instead wait for the sidebar nav to appear —
  // it only renders after isAuthenticated=true and the EULA gate is cleared.
  await page.waitForSelector("nav", { timeout: 15_000 }).catch(async () => {
    // Fallback: give the page more time if the selector isn't found immediately
    await page.waitForLoadState("load", { timeout: 10_000 }).catch(() => {});
  });

  console.log("[setup] URL after sign-in:", page.url());

  // If the EulaGate is blocking, accept the EULA now so tests don't see it.
  // Use waitFor (short timeout) instead of isVisible() so React has time to render
  // the gate after Clerk fires the session change event.
  const eulaVisible = await page
    .getByText("WeftMark Terms of Service")
    .waitFor({ state: "visible", timeout: 5_000 })
    .then(() => true)
    .catch(() => false);

  if (eulaVisible) {
    const scrollContainer = page.locator("div.overflow-y-auto").first();
    await scrollContainer.evaluate((el: HTMLElement) => { el.scrollTop = el.scrollHeight; });
    await page.getByRole("checkbox").check();
    await page.getByRole("button", { name: /I Accept the Terms of Service/i }).click();
    await page.waitForURL(/\/(home|admin)/, { timeout: 10_000 });
    await page.waitForLoadState("networkidle", { timeout: 10_000 });
  }
}

setup("authenticate as regular user", async ({ page }) => {
  await signIn(page, process.env.E2E_USER_EMAIL!);
  await page.context().storageState({ path: userFile });
});

setup("authenticate as admin user", async ({ page }) => {
  await signIn(page, process.env.E2E_ADMIN_EMAIL!);
  await page.context().storageState({ path: adminFile });
});
