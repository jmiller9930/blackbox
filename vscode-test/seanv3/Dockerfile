# Binance HTTPS must use the HOST routing table — compose sets network_mode:host (VPN/README.md).
# No WireGuard/Proton inside the image.
FROM node:22-alpine

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install --omit=dev && npm cache clean --force

# Use image's built-in `node` user (GID 1000 already exists on node:alpine).
COPY --chown=node:node \
  app.mjs backfill.mjs paper_analog.mjs wallet_connect.mjs funding_guards.mjs \
  jupiter_3_sean_policy.mjs jupiter_4_sean_policy.mjs jupiter_mc_test_policy.mjs jupiter_mc2_policy.mjs jupiter_policy_runtime.mjs \
  sean_lifecycle.mjs sean_ledger.mjs decision_ledger.mjs sean_engine.mjs report.mjs jupiter_web.mjs jupiter_web_auth.mjs ./
COPY --chown=node:node static/ ./static/

USER node

# node:sqlite requires --experimental-sqlite (Node 22+).
CMD ["node", "--experimental-sqlite", "app.mjs"]
