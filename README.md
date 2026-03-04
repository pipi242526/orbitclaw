<div align="center">
  <img src="assets/lunaeclaw-banner.svg" alt="LunaeClaw banner" width="920" />

# LunaeClaw

**Production-minded multi-channel agent runtime**

<p>
  <img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/Node.js-20%2B-339933?style=flat&logo=nodedotjs&logoColor=white" alt="Node.js" />
  <img src="https://img.shields.io/badge/License-MIT-16a34a?style=flat" alt="License" />
  <img src="https://img.shields.io/badge/Version-0.1.1-0ea5e9?style=flat" alt="Version" />
</p>

**Language / 语言**: [English](README.md) | [简体中文](README.zh-CN.md)

</div>

---

<div align="center">

[Overview](#overview) • [Install](#install) • [Platform Support](#platform-support) • [Channel Support](#channel-support) • [Directory Trees](#directory-trees) • [Operations](#operations) • [Security Baseline](#security-baseline)

</div>

## Overview

LunaeClaw is built for operators who need an agent runtime they can actually deploy and maintain, not just demo.

| What you get | Why it matters |
| --- | --- |
| `lunaeclaw gateway` | Long-running service loop for real traffic |
| `lunaeclaw webui` | Visual config and diagnostics without rewriting JSON by hand |
| Multi-channel adapters | One runtime across Telegram/Discord/Feishu/DingTalk/QQ/Slack/WhatsApp/Email/Mochat |
| MCP + Skills + aliases | Keep workflows customizable without forking core logic |
| `status` + `doctor` | Fast diagnostics when something breaks |

> [!TIP]
> No channel is hardcoded as “the only first-class path”. Enable only what your deployment needs.

## Install

### Choose your path

| Scenario | Recommendation |
| --- | --- |
| Local development (macOS/Linux) | `uv sync --extra dev` |
| Windows workstation | WSL2 + Ubuntu + `uv` |
| Server / NAS / homelab | Docker Compose |
| Minimal editable install | `pip install -e .` |

### Local development (macOS/Linux)

Prerequisites: Python `3.11+`, `uv`; Node.js `20+` only if enabling WhatsApp bridge.

```bash
git clone <your-repo-url>
cd OrbitClaw
uv sync --extra dev
uv run lunaeclaw onboard
uv run lunaeclaw gateway
# another shell
uv run lunaeclaw webui --host 0.0.0.0 --port 18791
```

### Windows via WSL2 (recommended)

```bash
# inside Ubuntu (WSL2)
sudo apt update
sudo apt install -y curl git python3 python3-venv python3-pip
curl -LsSf https://astral.sh/uv/install.sh | sh

git clone <your-repo-url>
cd OrbitClaw
uv sync --extra dev
uv run lunaeclaw onboard
uv run lunaeclaw gateway
```

### Docker Compose (server-friendly)

```bash
git clone <your-repo-url>
cd OrbitClaw
mkdir -p ./.lunaeclaw-data
docker compose up -d --build lunaeclaw-gateway lunaeclaw-webui
docker compose logs -f --tail=200
```

Default ports:

- Gateway `18790`
- WebUI `18791`

### Minimal editable install

```bash
git clone <your-repo-url>
cd OrbitClaw
pip install -e .
lunaeclaw onboard
lunaeclaw gateway
```

### First provider config

`~/.lunaeclaw/config.json`

```json
{
  "providers": {
    "endpoints": {
      "openai": {
        "type": "openai_compatible",
        "apiBase": "https://api.openai.com/v1",
        "apiKey": "${OPENAI_API_KEY}",
        "models": ["gpt-4o-mini", "gpt-4.1-mini"]
      }
    }
  },
  "agents": {
    "defaults": {
      "model": "openai/gpt-4o-mini",
      "temperature": 0.1
    }
  }
}
```

`~/.lunaeclaw/.env`

```bash
OPENAI_API_KEY=sk-xxx
```

Run a health check:

```bash
lunaeclaw doctor
```

## Platform Support

> Current CI is `ubuntu-latest`. Other environments are supported by dependency/runtime design and common operator usage; always run `lunaeclaw doctor` after setup.

| Platform | Status | Best install path | Notes |
| --- | --- | --- | --- |
| Linux server (x86_64/arm64) | Recommended | Docker Compose | Predictable production footprint |
| macOS (Apple Silicon/Intel) | Recommended | Local `uv` | Best DX for iteration |
| Windows | Supported (WSL2 recommended) | WSL2 + Ubuntu | Native Windows shell is not primary path |
| NAS/homelab | Recommended | Docker Compose | Host-mounted data directory simplifies backup |

## Channel Support

| Channel | Runtime requirement | Key config fields |
| --- | --- | --- |
| Telegram | Python runtime | `channels.telegram.token`, `allowFrom` |
| Discord | Python runtime | `channels.discord.token`, `allowFrom` |
| Feishu | Python runtime | `channels.feishu.appId`, `appSecret`, `allowFrom` |
| DingTalk | Python runtime | `channels.dingtalk.clientId`, `clientSecret`, `allowFrom` |
| QQ | Python runtime | `channels.qq.appId`, `secret`, `allowFrom` |
| Slack | Python runtime | `channels.slack.botToken`, `appToken` |
| WhatsApp | Python + Node.js bridge (`bridge/`, Node 20+) | `channels.whatsapp.bridgeUrl`, optional `bridgeToken`, `allowFrom` |
| Email | Python + IMAP/SMTP | `channels.email.imap*`, `smtp*`, `allowFrom`, `consentGranted` |
| Mochat | Python runtime | `channels.mochat.baseUrl`, `clawToken`, `allowFrom` |

## Directory Trees

### Repository tree

```text
OrbitClaw/
├── lunaeclaw/              # runtime source (app/core/capabilities/platform/services)
├── bridge/                 # WhatsApp Node.js bridge
├── tests/public/           # public regression tests
├── docs/public/            # publishable governance docs
├── scripts/                # quality/release helper scripts
├── docker-compose.yml      # local production-like deployment
├── Dockerfile              # runtime image build
└── pyproject.toml          # package metadata + dependencies
```

### Runtime data tree

```text
~/.lunaeclaw/
├── config.json
├── .env
├── env/
├── workspace/
├── mcp/
├── skills/
├── media/
├── exports/
└── bridge/                 # copied/compiled WhatsApp bridge runtime
```

## Operations

```bash
# overall runtime status
lunaeclaw status

# config/runtime diagnostics
lunaeclaw doctor

# per-channel config status
lunaeclaw channels status

# WhatsApp bridge login flow
lunaeclaw channels login
```

## Security Baseline

Before exposing the runtime to real users:

- configure `allowFrom` on every enabled channel (empty list means open access)
- set file permissions: `~/.lunaeclaw` as `700`, config/env as `600`
- run with a non-root user
- if WhatsApp is enabled, set `channels.whatsapp.bridgeToken`
- apply [SECURITY.md](SECURITY.md)

## Acknowledgements

- Upstream foundation: [HKUDS/nanobot](https://github.com/HKUDS/nanobot)
- Core libraries used heavily: `litellm`, `pydantic`, `python-telegram-bot`, `websockets`, `@whiskeysockets/baileys`

Thanks to upstream and ecosystem maintainers.

## License

MIT. See [LICENSE](LICENSE).
