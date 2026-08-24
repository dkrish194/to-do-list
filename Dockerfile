FROM nginx:1.27-alpine

RUN apk add --no-cache gettext   # provides envsubst

COPY index.html style.css app.js config.js.template /usr/share/nginx/html/
COPY nginx.conf /etc/nginx/nginx.conf
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

ENV BACKEND_URL=http://localhost:5000
ENV FRONTEND_VERSION=v1.0.0
ENV FRONTEND_COLOR=#4F46E5
ENV FRONTEND_COLOR_NAME=indigo

EXPOSE 8080
ENTRYPOINT ["/docker-entrypoint.sh"]
