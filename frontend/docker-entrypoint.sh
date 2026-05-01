#!/bin/sh
set -e
printf 'window.ENV = { CLERK_PUBLISHABLE_KEY: "%s" };\n' "${CLERK_PUBLISHABLE_KEY}" \
  > /usr/share/nginx/html/env-config.js
exec nginx -g 'daemon off;'
