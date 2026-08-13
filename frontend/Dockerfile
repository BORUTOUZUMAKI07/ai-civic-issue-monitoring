FROM node:22-bookworm AS deps

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund && npm install --no-save lightningcss-linux-x64-gnu@1.32.0 @tailwindcss/oxide-linux-x64-gnu@4.3.0 @unrs/resolver-binding-linux-x64-gnu@1.12.2

# ---------- BUILDER STAGE ----------
FROM node:22-bookworm AS builder

WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

ENV NODE_ENV=production
RUN npm run build -- --webpack

# ---------- RUNTIME STAGE (standalone) ----------
FROM node:22-bookworm-slim AS runner

RUN useradd -m -u 1000 nodeuser
WORKDIR /app
ENV NODE_ENV=production HOSTNAME=0.0.0.0 PORT=3000

COPY --from=builder --chown=nodeuser:nodeuser /app/.next/standalone ./
COPY --from=builder --chown=nodeuser:nodeuser /app/.next/static ./.next/static
COPY --from=builder --chown=nodeuser:nodeuser /app/public ./public

USER nodeuser
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD node -e "require('http').get({hostname:'0.0.0.0',port:3000,path:'/',timeout:3000},r=>process.exit(r.statusCode!==200?1:0)).on('error',()=>process.exit(1))"
CMD ["node", "server.js"]
