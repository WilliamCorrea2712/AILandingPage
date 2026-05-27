# ============================================================
# Frontend Dockerfile — AI Landing Page Generator
# Node.js 20 + Nuxt 3 — Multi-stage build
# ============================================================

# ------------------------------------
# Stage 1: deps — install all dependencies
# ------------------------------------
FROM node:20-alpine AS deps

# Install libc compatibility layer (needed by some native modules)
RUN apk add --no-cache libc6-compat

WORKDIR /app

# Copy package manifests first for better layer caching
COPY package.json package-lock.json* ./

# Install all dependencies (including devDependencies needed for build)
RUN npm ci --frozen-lockfile

# ------------------------------------
# Stage 2: builder — build the Nuxt 3 app
# ------------------------------------
FROM node:20-alpine AS builder

RUN apk add --no-cache libc6-compat

WORKDIR /app

# Copy installed node_modules from deps stage
COPY --from=deps /app/node_modules ./node_modules

# Copy full source
COPY . .

# Build arguments for public runtime config
ARG NUXT_PUBLIC_API_URL=http://api:8000
ENV NUXT_PUBLIC_API_URL=${NUXT_PUBLIC_API_URL}

# Run nuxt prepare (generates .nuxt types) then build
RUN npm run build

# ------------------------------------
# Stage 3: runner — minimal production image
# ------------------------------------
FROM node:20-alpine AS runner

RUN apk add --no-cache libc6-compat

# Create non-root user for security
RUN addgroup --system --gid 1001 nodejs \
    && adduser --system --uid 1001 nuxtjs

WORKDIR /app

# Copy only the built output and production dependencies
COPY --from=builder --chown=nuxtjs:nodejs /app/.output ./

USER nuxtjs

# Nuxt 3 listens on port 3000 by default
EXPOSE 3000

ENV NODE_ENV=production \
    PORT=3000 \
    HOST=0.0.0.0

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD wget -qO- http://localhost:3000/ || exit 1

# Start the Nuxt 3 server (output/server/index.mjs is the standalone entry point)
CMD ["node", "server/index.mjs"]
