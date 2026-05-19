import { test as base, expect } from "@playwright/test";
import { clerkSetup, setupClerkTestingToken } from "@clerk/testing/playwright";

// Extend the base page fixture to install Clerk's FAPI interceptor before each test.
// Sessions created via @clerk/testing require __clerk_testing_token on every Clerk
// FAPI request (including session validation) to bypass bot detection. Without this
// the stored session from global.setup.ts is rejected and the user sees "Approval pending".
// clerkSetup() fetches a fresh short-lived testing token; setupClerkTestingToken() installs
// a route handler that appends it to all Clerk frontend-API requests in this context.
export const test = base.extend<{ page: typeof base.prototype["page"] }>({
  page: async ({ page }, use) => {
    await clerkSetup();
    await setupClerkTestingToken({ page });
    await use(page);
  },
});

export { expect };
