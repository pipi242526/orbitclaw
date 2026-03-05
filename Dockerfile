FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_SYSTEM_PYTHON=1 \
    PIP_NO_CACHE_DIR=1

# Runtime deps: Node.js 20 (for WhatsApp bridge), git/curl/certs.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates curl git xz-utils; \
    arch="$(dpkg --print-architecture)"; \
    case "${arch}" in \
      amd64) node_arch="x64" ;; \
      arm64) node_arch="arm64" ;; \
      *) echo "unsupported arch: ${arch}" >&2; exit 1 ;; \
    esac; \
    node_dist_url="https://nodejs.org/dist/latest-v20.x"; \
    node_tar="$(curl -fsSL "${node_dist_url}/SHASUMS256.txt" | awk -v a="linux-${node_arch}.tar.xz" '$2 ~ a {print $2; exit}')"; \
    test -n "${node_tar}"; \
    curl -fsSLO "${node_dist_url}/${node_tar}"; \
    curl -fsSL "${node_dist_url}/SHASUMS256.txt" | grep " ${node_tar}\$" | sha256sum -c -; \
    tar -xJf "${node_tar}" -C /usr/local --strip-components=1 --no-same-owner; \
    rm -f "${node_tar}"; \
    node --version; \
    npm --version; \
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
