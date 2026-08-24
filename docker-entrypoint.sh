#!/bin/sh
set -e

: "${BACKEND_URL:=http://localhost:5000}"
: "${FRONTEND_VERSION:=v1.0.0}"
: "${FRONTEND_COLOR:=#4F46E5}"
: "${FRONTEND_COLOR_NAME:=indigo}"

envsubst '${BACKEND_URL} ${FRONTEND_VERSION} ${FRONTEND_COLOR} ${FRONTEND_COLOR_NAME}' \
  < /usr/share/nginx/html/config.js.template \
  > /usr/share/nginx/html/config.js

exec nginx -g 'daemon off;'
