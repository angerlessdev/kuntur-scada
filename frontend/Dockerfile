# syntax=docker/dockerfile:1
# Kuntur SCADA web console. Build from the repository root: docker build -f frontend/Dockerfile .

FROM node:22-alpine AS build
# The same npm that wrote package-lock.json (see packageManager in package.json)
RUN npm install -g npm@11.6.2 --no-audit --no-fund
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# nginx as a non-root user, listening on 8080
FROM nginxinc/nginx-unprivileged:1.27-alpine
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist/kuntur-web/browser /usr/share/nginx/html
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --retries=3 CMD wget -q -O /dev/null http://127.0.0.1:8080/ || exit 1
