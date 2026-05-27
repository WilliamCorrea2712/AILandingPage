# =============================================================================
# Nginx Dockerfile — AI Landing Page Generator
# Based on nginx:alpine for a minimal, secure image
# =============================================================================

FROM nginx:alpine

# Remove the default nginx configuration
RUN rm /etc/nginx/conf.d/default.conf

# Copy custom nginx configuration
COPY nginx.conf /etc/nginx/nginx.conf

# Copy security headers include file
COPY conf.d/security_headers.conf /etc/nginx/conf.d/security_headers.conf

# Create directory for SSL certificates (populated at runtime via volume or secrets)
RUN mkdir -p /etc/nginx/ssl

# Expose HTTP and HTTPS ports
EXPOSE 80 443

# Health check — verify nginx is serving requests
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://localhost/health || exit 1

# Use the default nginx entrypoint (starts nginx in the foreground)
CMD ["nginx", "-g", "daemon off;"]
