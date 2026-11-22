FROM node:26-alpine AS build
WORKDIR /build

# Copy only what the CSS build needs
COPY errors/ ./errors/
COPY frontend/src/theme.css ./frontend/src/theme.css

# Install Tailwind CLI + tailwindcss at /build/node_modules so the @import
# "tailwindcss" in input.css resolves via Node module lookup from /build/errors/
RUN npm install @tailwindcss/cli@^4.3.0 tailwindcss@^4.3.0
RUN node_modules/.bin/tailwindcss -i ./errors/input.css -o ./errors/styles.css

# Inline the generated CSS into both HTML files so the pages have no external
# asset dependencies. A root-relative /styles.css href causes a MIME mismatch
# when Traefik serves the error HTML and the browser fetches the stylesheet
# from the frontend nginx, which doesn't host that file.
RUN node -e " \
  const fs = require('fs'); \
  const css = fs.readFileSync('./errors/styles.css', 'utf8'); \
  const tag = '<link rel=\"stylesheet\" href=\"/styles.css\" />'; \
  const inline = '<style>' + css + '</style>'; \
  for (const f of ['404.html', '500.html']) { \
    const p = './errors/' + f; \
    fs.writeFileSync(p, fs.readFileSync(p, 'utf8').replace(tag, inline)); \
  } \
"

# Pinned by version + digest so the shipped image is reproducible. Dependabot (docker, /errors)
# bumps the digest when the same version is rebuilt (Alpine/nginx CVE fixes) and the tag when
# a new stable release ships; odd (mainline) minors are ignored in .github/dependabot.yml.
# A merge to dev that touches errors/ publishes :dev-latest (publish-error-container.yml).
FROM nginx:1.30.7-alpine@sha256:caf4e1e032a20f9c3c5e28fc7f25ffd768ad8677b4975c54193075997b3a97e3
COPY --from=build /build/errors/404.html /usr/share/nginx/html/
COPY --from=build /build/errors/500.html /usr/share/nginx/html/
COPY errors/nginx.conf /etc/nginx/conf.d/default.conf
