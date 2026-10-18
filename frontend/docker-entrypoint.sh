#!/bin/sh
set -eu

if [ "${SIRI_STATUS_ENABLED:-false}" = "true" ]; then
    enabled=1
else
    enabled=0
fi

awk -v enabled="$enabled" '
    /# SIRI_STATUS_ACCESS_BLOCK_START/ {
        in_block = 1
        if (!enabled) {
            print "    location = /api {"
            print "        return 404;"
            print "    }"
            print ""
            print "    location ^~ /api/ {"
            print "        return 404;"
            print "    }"
            print ""
            print "    location = /status {"
            print "        return 404;"
            print "    }"
        }
        next
    }
    /# SIRI_STATUS_ACCESS_BLOCK_END/ {
        in_block = 0
        next
    }
    !in_block { print }
' /etc/nginx/default.conf.template > /etc/nginx/conf.d/default.conf

exec nginx -g 'daemon off;'
