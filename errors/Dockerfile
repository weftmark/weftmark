FROM node:20-alpine AS build
WORKDIR /build

# Copy only what the CSS build needs
COPY errors/ ./errors/
COPY frontend/src/theme.css ./frontend/src/theme.css

# Install Tailwind CLI + tailwindcss at /build/node_modules so the @import
# "tailwindcss" in input.css resolves via Node module lookup from /build/errors/
RUN npm install @tailwindcss/cli@^4.3.0 tailwindcss@^4.3.0
RUN node_modules/.bin/tailwindcss -i ./errors/input.css -o ./errors/styles.css

FROM nginx:alpine
COPY --from=build /build/errors/404.html /usr/share/nginx/html/
COPY --from=build /build/errors/500.html /usr/share/nginx/html/
COPY --from=build /build/errors/styles.css /usr/share/nginx/html/
COPY errors/nginx.conf /etc/nginx/conf.d/default.conf
