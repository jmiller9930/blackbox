# Minimal image; Node 18+ has global fetch. Egress uses the host routing table
# (split-tunnel WireGuard on the host applies to container traffic by default).
FROM node:22-alpine

WORKDIR /app

RUN addgroup -g 1000 app && adduser -D -u 1000 -G app app
COPY --chown=app:app app.mjs ./

USER app

CMD ["node", "app.mjs"]
