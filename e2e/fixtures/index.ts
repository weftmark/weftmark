// Auth is handled via storageState from global.setup.ts (real UI sign-in).
// The setup project writes __client_uat natively so Clerk can sync on each
// page load. No custom fixture is needed; re-export base helpers for imports.
export { test, expect } from "@playwright/test";
