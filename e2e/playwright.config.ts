import { defineConfig, devices } from "@playwright/test";
import dotenv from "dotenv";
import path from "path";

dotenv.config({ path: path.resolve(__dirname, ".env") });

export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [["html", { open: "never" }], ["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL || "http://localhost:3000",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "on-first-retry",
    extraHTTPHeaders: {
      ...(process.env.CF_ACCESS_CLIENT_ID && {
        "CF-Access-Client-Id": process.env.CF_ACCESS_CLIENT_ID,
        "CF-Access-Client-Secret": process.env.CF_ACCESS_CLIENT_SECRET!,
      }),
    },
  },
  projects: [
    // Setup project: signs in via real UI and saves storageState for each role.
    // This ensures __client_uat is written natively by Clerk (not zeroed out
    // as happens with @clerk/testing's setActive() in test mode).
    {
      name: "setup",
      testMatch: /global\.setup\.ts/,
    },

    // Authenticated tests: load stored session so Clerk can sync on each page load.
    {
      name: "authenticated",
      use: {
        ...devices["Desktop Chrome"],
        storageState: path.join(__dirname, ".auth/user.json"),
      },
      testIgnore: [/admin\.spec\.ts/, /auth\.spec\.ts/],
      dependencies: ["setup"],
    },
    {
      name: "admin",
      use: {
        ...devices["Desktop Chrome"],
        storageState: path.join(__dirname, ".auth/admin.json"),
      },
      testMatch: /admin\.spec\.ts/,
      dependencies: ["setup"],
    },
    {
      name: "unauthenticated",
      use: { ...devices["Desktop Chrome"] },
      testMatch: /auth\.spec\.ts/,
    },
  ],
});
