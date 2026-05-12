import { test as setup, type Page } from "@playwright/test";
import path from "path";

const userFile = path.join(__dirname, "../.auth/user.json");
const adminFile = path.join(__dirname, "../.auth/admin.json");

async function signIn(page: Page, email: string, password: string) {
  await page.goto("/login");

  // Wait for Clerk's embedded <SignIn> component to render the email field
  const emailField = page.getByLabel(/email address/i).first();
  await emailField.waitFor({ state: "visible", timeout: 15_000 });
  await emailField.fill(email);

  // Click Continue to advance to password step
  await page.getByRole("button", { name: /continue/i }).first().click();

  // Wait for password field (two-step flow)
  const passwordField = page.getByLabel(/^password$/i).first();
  await passwordField.waitFor({ state: "visible", timeout: 10_000 });
  await passwordField.fill(password);
  await page.getByRole("button", { name: /continue|sign in/i }).first().click();

  // Wait for redirect to authenticated area
  await page.waitForURL(/\/(home|admin|pending)/, { timeout: 20_000 });

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
  await signIn(page, process.env.E2E_USER_EMAIL!, process.env.E2E_USER_PASSWORD!);
  await page.context().storageState({ path: userFile });
});

setup("authenticate as admin user", async ({ page }) => {
  await signIn(page, process.env.E2E_ADMIN_EMAIL!, process.env.E2E_ADMIN_PASSWORD!);
  await page.context().storageState({ path: adminFile });
});
