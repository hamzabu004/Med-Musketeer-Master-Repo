# Traefik with its routes baked in (no bind mount): dynamic/ for development, public/ for
# compose.public.yaml.
FROM traefik:v3.7.16
COPY dynamic.yml /etc/traefik/dynamic/dynamic.yml
COPY public.yml /etc/traefik/public/public.yml
