# foodguidecanada MCP server over HTTP, with the datasets baked into the image.
#
#   docker build -t foodguide-mcp .
#   docker run --rm -p 127.0.0.1:8000:8000 --read-only --tmpfs /tmp --memory 512m foodguide-mcp
#   endpoint: http://127.0.0.1:8000/mcp
#
# Lessons from running containers on a real server: pinned base image, non-root user, read-only
# root filesystem, a memory limit, published on loopback only (put TLS and auth in front for other
# people), and no network at run time (the data is fetched once, at build time).
#
# python:3.12-slim-bookworm, pinned by digest (2026-11-02).
FROM python:3.12-slim-bookworm@sha256:e697c81897302a4c4333bade000d98038fbb21eb064f8ee1fd42d02ebcd9d337

LABEL org.opencontainers.image.source="https://github.com/Aryan-Jhaveri/mcp-foodguidecanada" \
      org.opencontainers.image.description="Canada's Food Guide MCP server (HTTP) with offline data" \
      org.opencontainers.image.licenses="MIT"

# Which release of the datasets to bake in (the Data refresh workflow publishes them).
ARG DATA_TAG=data-latest

RUN useradd --create-home --uid 10001 app
WORKDIR /src
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir '.[mcp]' && rm -rf /src

USER app
ENV FOODGUIDE_DATA_DIR=/home/app/data \
    MCP_TRANSPORT=http \
    HOST=0.0.0.0 \
    PORT=8000 \
    PYTHONUNBUFFERED=1
# Downloads from GitHub over HTTPS and checks every file against the release manifest.
RUN foodguide data fetch --tag "${DATA_TAG}" && foodguide data status | head -3

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/mcp/', timeout=4).status == 200 else 1)"
CMD ["foodguide-mcp"]
