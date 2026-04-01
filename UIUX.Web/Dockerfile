# Stateless static image — HTTPS on 443 in-container; map host 443 -> container 443.
FROM nginx:1.27-alpine

RUN apk add --no-cache openssl \
    && mkdir -p /etc/nginx/ssl \
    && openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
        -keyout /etc/nginx/ssl/self.key \
        -out /etc/nginx/ssl/self.crt \
        -subj "/CN=blackbox-ui-dev" \
        -addext "subjectAltName=DNS:localhost,DNS:blackbox.greyllc.net,DNS:clawbot.a51.corp,IP:127.0.0.1,IP:172.20.2.161"

COPY nginx/default.conf /etc/nginx/conf.d/default.conf
COPY index.html login.html internal.html anna.html internal-plan.html internal-users.html account-settings.html consumer.html guide.html docs.html docs-anna-language.html docs-system-usage.html docs-ui-context.html docs-web-architecture.html forgot-password.html reset-password.html verify-email.html register.html 404.html styles.css app.js /usr/share/nginx/html/
COPY assets /usr/share/nginx/html/assets/
COPY content /usr/share/nginx/html/content/
