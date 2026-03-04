FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_SYSTEM_PYTHON=1 \
    PIP_NO_CACHE_DIR=1

# Runtime deps: Node.js 20 (for WhatsApp bridge), git/curl/certs.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates curl git gnupg; \
    mkdir -p /etc/apt/keyrings; \
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
      | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg; \
    echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" \
      > /etc/apt/sources.list.d/nodesource.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends nodejs; \
    apt-get purge -y --auto-remove gnupg; \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Cache Python dependencies separately from source changes.
COPY pyproject.toml README.md README.zh-CN.md LICENSE NOTICE ./
RUN mkdir -p lunaeclaw bridge; \
    touch lunaeclaw/__init__.py; \
    uv pip install --system --no-cache .; \
    rm -rf lunaeclaw bridge

# Copy full project and install runtime package.
COPY lunaeclaw/ lunaeclaw/
COPY bridge/ bridge/
RUN uv pip install --system --no-cache .

# Validate bridge build during image build (keeps runtime predictable).
RUN npm --prefix bridge install && npm --prefix bridge run build && npm cache clean --force

# Persistent runtime directory.
RUN mkdir -p /root/.lunaeclaw

EXPOSE 18790 18791

ENTRYPOINT ["lunaeclaw"]
CMD ["status"]
