FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ARG VITE_API_BASE_URL=/api/v1
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
RUN npm run build
RUN (find src public -type f -print; printf '%s\n' package.json package-lock.json vite.config.ts nginx.conf) | sort | xargs sha256sum | sha256sum | awk '{print $1}' > /frontend-source.sha256

FROM nginxinc/nginx-unprivileged:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
COPY --from=build /frontend-source.sha256 /usr/share/nginx/html/frontend-source.sha256
EXPOSE 8080
