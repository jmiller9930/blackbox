# NDE Studio — React build + Express API placeholders
FROM node:20-bookworm-slim AS build
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY index.html vite.config.ts tsconfig.json tsconfig.node.json ./
COPY public ./public
COPY src ./src
RUN npm run build

# Trixie glibc aligns with Ubuntu 24.04+ training hosts; bookworm's glibc is too old for host-built --copies Python.
FROM node:24-trixie-slim AS runtime
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=3999
ENV NDE_DATA_ROOT=/data/NDE
ENV REPO_MOUNT=/repo

# Host-copied /data/NDE/.venv-train/bin/python is invoked from this container; slim omits libexpat.
RUN apt-get update && apt-get install -y --no-install-recommends libexpat1 \
  && rm -rf /var/lib/apt/lists/*

COPY package.json ./
RUN npm install --omit=dev --no-audit --no-fund express@^4.21.0 multer@^1.4.5-lts.2

COPY --from=build /app/dist ./dist
COPY server.mjs ./

EXPOSE 3999
CMD ["node", "server.mjs"]
