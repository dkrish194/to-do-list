#!/bin/sh
set -e

: "${BACKEND_PROXY_HOST:=backend:5000}"
: "${FRONTEND_VERSION:=v1.0.0}"
: "${FRONTEND_COLOR:=#4F46E5}"
: "${FRONTEND_COLOR_NAME:=indigo}"
: "${NGINX_PORT:=8081}"

envsubst '${FRONTEND_VERSION} ${FRONTEND_COLOR} ${FRONTEND_COLOR_NAME}' \
  < /usr/share/nginx/html/config.js.template \
  > /usr/share/nginx/html/config.js

# IMPORTANT: only substitute these two here. nginx.conf.template also
# contains nginx's OWN variables like $remote_addr, $status, $host, $uri -
# passing an explicit variable list (instead of bare `envsubst`) stops those
# from being wiped out to empty strings.
envsubst '${NGINX_PORT} ${BACKEND_PROXY_HOST}' \
  < /etc/nginx/nginx.conf.template \
  > /etc/nginx/nginx.conf

echo "Starting nginx on port ${NGINX_PORT}, proxying /api and /version to ${BACKEND_PROXY_HOST}"
exec nginx -g 'daemon off;'
