declare global {
  interface Window {
    ENV?: {
      CLERK_PUBLISHABLE_KEY?: string;
    };
  }
}

export const clerkPublishableKey: string =
  window.ENV?.CLERK_PUBLISHABLE_KEY || import.meta.env.VITE_CLERK_PUBLISHABLE_KEY || "";

export const clerkKeyMissing = !clerkPublishableKey;
