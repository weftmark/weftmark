FROM node:24-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .

# Vite bakes VITE_* vars at build time — pass them as build args.
# CLERK_PUBLISHABLE_KEY is intentionally excluded here; it is injected
# at container startup via docker-entrypoint.sh so the image is key-agnostic.
ARG VITE_API_URL=""
ARG VITE_APP_ENV="dev"
ARG VITE_DEV_BANNER_COLOR=""
ARG VITE_CLERK_SIGN_IN_URL="/login"
ARG VITE_CLERK_SIGN_UP_URL="/register"
ARG VITE_CLERK_SIGN_IN_FALLBACK_REDIRECT_URL="/home"
ARG VITE_CLERK_SIGN_UP_FALLBACK_REDIRECT_URL="/home"
ARG VITE_SENTRY_ENV=""
ENV VITE_API_URL=$VITE_API_URL
ENV VITE_APP_ENV=$VITE_APP_ENV
ENV VITE_SENTRY_ENV=$VITE_SENTRY_ENV
ENV VITE_DEV_BANNER_COLOR=$VITE_DEV_BANNER_COLOR
ENV VITE_CLERK_SIGN_IN_URL=$VITE_CLERK_SIGN_IN_URL
ENV VITE_CLERK_SIGN_UP_URL=$VITE_CLERK_SIGN_UP_URL
ENV VITE_CLERK_SIGN_IN_FALLBACK_REDIRECT_URL=$VITE_CLERK_SIGN_IN_FALLBACK_REDIRECT_URL
ENV VITE_CLERK_SIGN_UP_FALLBACK_REDIRECT_URL=$VITE_CLERK_SIGN_UP_FALLBACK_REDIRECT_URL

RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh
ENTRYPOINT ["/docker-entrypoint.sh"]
