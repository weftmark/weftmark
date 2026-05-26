declare global {
  interface Window {
    ENV?: {
      CLERK_PUBLISHABLE_KEY?: string;
      SENTRY_DSN_REACT?: string;
    };
  }
}

export const clerkPublishableKey: string =
  globalThis.window?.ENV?.CLERK_PUBLISHABLE_KEY || import.meta.env.VITE_CLERK_PUBLISHABLE_KEY || "";

export const clerkKeyMissing = !clerkPublishableKey;

export const sentryDsn: string = globalThis.window?.ENV?.SENTRY_DSN_REACT || import.meta.env.VITE_SENTRY_DSN_REACT || "";
