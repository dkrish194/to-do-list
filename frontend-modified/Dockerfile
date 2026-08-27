FROM nginx:1.27-alpine

RUN apk add --no-cache gettext   # provides envsubst

COPY index.html style.css app.js config.js.template /usr/share/nginx/html/
COPY nginx.conf.template /etc/nginx/nginx.conf.template
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh \
 && chmod -R o+rX /usr/share/nginx/html

ENV BACKEND_PROXY_HOST=todo-backend:5000
ENV FRONTEND_VERSION=v1.0.0
ENV FRONTEND_COLOR=#4F46E5
ENV FRONTEND_COLOR_NAME=indigo
ENV NGINX_PORT=8081

EXPOSE 8081
ENTRYPOINT ["/docker-entrypoint.sh"]
