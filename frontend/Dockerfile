FROM nginx:1.27-alpine

ARG MAPLIBRE_VERSION=5.24.0

COPY nginx.conf /etc/nginx/default.conf.template
COPY docker-entrypoint.sh /usr/local/bin/echogtfs-nginx-entrypoint.sh

RUN chmod +x /usr/local/bin/echogtfs-nginx-entrypoint.sh

COPY index.html /usr/share/nginx/html/
COPY css/ /usr/share/nginx/html/css/
COPY js/  /usr/share/nginx/html/js/

RUN wget -O /usr/share/nginx/html/css/maplibre-gl.css \
        https://unpkg.com/maplibre-gl@${MAPLIBRE_VERSION}/dist/maplibre-gl.css \
 && wget -O /usr/share/nginx/html/js/maplibre-gl.js \
        https://unpkg.com/maplibre-gl@${MAPLIBRE_VERSION}/dist/maplibre-gl.js

ENTRYPOINT ["sh", "/usr/local/bin/echogtfs-nginx-entrypoint.sh"]