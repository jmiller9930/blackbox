#!/bin/sh
set -e
# Prefer operator-provided certs (Let's Encrypt, internal PKI) mounted at /etc/nginx/ssl/host/.
# Filenames match certbot defaults. Falls back to image self-signed (lab).
HOST_SSL=/etc/nginx/ssl/host
if [ -f "$HOST_SSL/fullchain.pem" ] && [ -f "$HOST_SSL/privkey.pem" ]; then
  cp "$HOST_SSL/fullchain.pem" /etc/nginx/ssl/active.crt
  cp "$HOST_SSL/privkey.pem" /etc/nginx/ssl/active.key
  chmod 644 /etc/nginx/ssl/active.crt
  chmod 600 /etc/nginx/ssl/active.key
else
  cp /etc/nginx/ssl/self.crt /etc/nginx/ssl/active.crt
  cp /etc/nginx/ssl/self.key /etc/nginx/ssl/active.key
fi
exec nginx -g "daemon off;"
