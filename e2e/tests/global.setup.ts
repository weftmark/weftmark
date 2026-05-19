import { test as setup, type Page } from "@playwright/test";
import path from "path";

const userFile = path.join(__dirname, "../.auth/user.json");
const adminFile = path.join(__dirname, "../.auth/admin.json");

const BASE_URL = process.env.E2E_BASE_URL || "http://localhost:3000";
const CLERK_SECRET_KEY = process.env.CLERK_SECRET_KEY!;

// Clerk's Backend API returns a sign-in URL that auto-logs in the user.
// This bypasses the Clerk UI entirely, avoiding Google Workspace domain detection
// that redirects @weftmark.com addresses to Google OAuth instead of the password step.
async function getSignInUrl(userId: string): Promise<string> {
  const resp = await fetch("https://api.clerk.com/v1/sign_in_tokens", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${CLERK_SECRET_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ user_id: userId }),
  });
  if (!resp.ok) {
    const err = await resp.text();
    throw new Error(`Clerk sign-in token failed (${resp.status}): ${err}`);
  }
  const data = await resp.json();
  // Clerk returns e.g. https://verified-anchovy-95.accounts.dev/sign-in?__clerk_ticket=...
  // Append redirect_url so Clerk sends us back to the app after sign-in.
  return `${data.url}&redirect_url=${encodeURIComponent(`${BASE_URL}/home`)}`;
}

async function signIn(page: Page, userId: string) {
  const signInUrl = await getSignInUrl(userId);
  // Extract the ticket and present it on the app's own login page.
  // Clerk's frontend SDK on the app domain handles __clerk_ticket natively,
  // avoiding cross-domain session sync issues that arise from navigating to accounts.dev.
  const ticket = new URL(signInUrl).searchParams.get("__clerk_ticket")!;
  await page.goto(`${BASE_URL}/login?__clerk_ticket=${ticket}`);
  await page.waitForURL(/\/(home|admin|pending)/, { timeout: 30_000 });

  // Handle EulaGate if shown on first sign-in
  const eulaVisible = await page
    .getByText("WeftMark Terms of Service")
    .isVisible()
    .catch(() => false);

  if (eulaVisible) {
    const scrollContainer = page.locator("div.overflow-y-auto").first();
    await scrollContainer.evaluate((el: HTMLElement) => { el.scrollTop = el.scrollHeight; });
    await page.getByRole("checkbox").check();
    await page.getByRole("button", { name: /I Accept the Terms of Service/i }).click();
    await page.waitForURL(/\/(home|admin)/, { timeout: 10_000 });
  }
}

setup("authenticate as regular user", async ({ page }) => {
  await signIn(page, process.env.E2E_USER_ID!);
  await page.context().storageState({ path: userFile });
});

setup("authenticate as admin user", async ({ page }) => {
  await signIn(page, process.env.E2E_ADMIN_ID!);
  await page.context().storageState({ path: adminFile });
});
