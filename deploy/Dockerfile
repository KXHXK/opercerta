FROM node:24-alpine3.24 AS web-build

WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM caddy:2.11.4-alpine

COPY deploy/Caddyfile /etc/caddy/Caddyfile
COPY --from=web-build /web/dist /srv
