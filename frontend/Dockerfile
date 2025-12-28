# Build stage - optimized for caching
FROM node:20-slim AS build-stage

WORKDIR /app

# Copy package files first for better caching
COPY package*.json ./

# Use npm ci for faster, reproducible builds
RUN npm ci --only=production=false

# Copy source code
COPY . .

# Build with production optimizations
ARG VITE_API_URL=http://localhost:8000
ARG VITE_API_TOKEN=secret-token
ENV VITE_API_URL=$VITE_API_URL
ENV VITE_API_TOKEN=$VITE_API_TOKEN

RUN npm run build

# Production stage - minimal nginx alpine
FROM nginx:stable-alpine

# Copy custom nginx config for SPA routing
COPY --from=build-stage /app/dist /usr/share/nginx/html

# Add nginx config for React Router
RUN echo 'server { \
    listen 80; \
    location / { \
        root /usr/share/nginx/html; \
        index index.html; \
        try_files $uri $uri/ /index.html; \
    } \
}' > /etc/nginx/conf.d/default.conf

# Run as non-root user
RUN chown -R nginx:nginx /usr/share/nginx/html && \
    chown -R nginx:nginx /var/cache/nginx && \
    chown -R nginx:nginx /var/log/nginx && \
    touch /var/run/nginx.pid && \
    chown -R nginx:nginx /var/run/nginx.pid

USER nginx

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://localhost:80 || exit 1

CMD ["nginx", "-g", "daemon off;"]
