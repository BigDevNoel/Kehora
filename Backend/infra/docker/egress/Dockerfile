# Sandbox egress proxy (ADR-0008): the only route out of the internal sandbox network.
# Allows CONNECT/HTTP only to domains in /etc/tinyproxy/filter; everything else is denied.
FROM alpine:3.24.3
RUN apk add --no-cache tinyproxy
COPY tinyproxy.conf /etc/tinyproxy/tinyproxy.conf
COPY filter /etc/tinyproxy/filter
EXPOSE 8888
USER tinyproxy
CMD ["tinyproxy", "-d", "-c", "/etc/tinyproxy/tinyproxy.conf"]
