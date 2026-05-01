// Overwritten at container startup by docker-entrypoint.sh
// In local dev (vite dev), VITE_CLERK_PUBLISHABLE_KEY is used as fallback
window.ENV = {
  CLERK_PUBLISHABLE_KEY: "",
};
