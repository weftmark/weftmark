#!/bin/sh
set -e
printf 'window.ENV = { CLERK_PUBLISHABLE_KEY: "%s", SENTRY_DSN: "%s" };\n' \
  "${CLERK_PUBLISHABLE_KEY}" "${SENTRY_DSN}" \
  > /usr/share/nginx/html/env-config.js
exec nginx -g 'daemon off;'
