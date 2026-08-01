FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

ARG VITE_API_BASE_URL=http://127.0.0.1:8000/api/v1
ARG VITE_CREATOR_DEFAULT_USERNAME=creator
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL} \
    VITE_CREATOR_DEFAULT_USERNAME=${VITE_CREATOR_DEFAULT_USERNAME}

RUN npm run build

FROM nginxinc/nginx-unprivileged:1.27-alpine AS runtime

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget --quiet --spider http://127.0.0.1:8080/healthz || exit 1
