# Minimal image; Node 18+ has global fetch. Egress uses the host routing table
# (split-tunnel WireGuard on the host applies to container traffic by default).
FROM node:22-alpine

WORKDIR /app

# Use image's built-in `node` user (GID 1000 already exists on node:alpine).
COPY --chown=node:node app.mjs ./

USER node

CMD ["node", "app.mjs"]
