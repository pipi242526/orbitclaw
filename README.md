<div align="center">
  <img src="assets/orbitclaw-banner.svg" alt="OrbitClaw banner" width="920" />

# OrbitClaw

**Practical lightweight agent runtime for Telegram-first automation and local ops**

<p>
  <img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/License-MIT-16a34a?style=flat" alt="License" />
  <img src="https://img.shields.io/badge/Version-0.1.1-0ea5e9?style=flat" alt="Version" />
  <img src="https://img.shields.io/badge/Profile-1C1G%20friendly-0f766e?style=flat" alt="Profile" />
  <img src="https://img.shields.io/badge/Status-Release%20Candidate-f97316?style=flat" alt="Status" />
</p>

**Language / 语言**: [English](README.md) | [简体中文](README.zh-CN.md)

</div>

---

## Why This Exists

OrbitClaw is an independently maintained secondary-development runtime built for:

- Chinese-first daily usage, Telegram-first operations
- low and predictable resource usage on small hosts
- clear extension boundaries for channels, MCP, and skills
- practical WebUI + CLI workflow for deployment and maintenance

## Table of Contents

- [Core Capabilities](#core-capabilities)
- [Quick Start](#quick-start)
- [Provider Configuration Example](#provider-configuration-example)
- [MCP Recommendations](#mcp-recommendations)
- [Runtime Layout](#runtime-layout)
- [Development Roadmap (Open)](#development-roadmap-open)
- [Governance](#governance)
- [Upstream Attribution](#upstream-attribution)

## OrbitClaw Advantages

### 1) Built for real usage, not demos

- default behavior is tuned for practical chat operations (especially Telegram)
- errors are returned with actionable fix hints, not raw stack noise
- output policy reduces tool-detail leakage in user-facing replies

### 2) Lightweight by default

- designed around 1C1G-friendly runtime budgets
- queue caps, timeout caps, and context budgets are first-class config fields
- optional integrations stay optional instead of bloating core paths

### 3) Better long-term maintainability

- core loop and extension points are separated by design
- MCP/skill changes can be done through config and aliases
- diagnostics + tests are integrated into daily workflow (`status`, `doctor`, pytest)

### 4) Chinese-first but not locale-locked

- Chinese UX defaults for common usage paths
- bilingual docs and i18n-ready UI structure for future language expansion

## Core Capabilities

### 1) Bot Runtime (priority)

- unified chat processing loop with command routing
- unified output post-processing (language + safe output + failure guidance)
- session and context budget controls (history, memory, background, inline media)
- queue and timeout limits for predictable behavior under load

### 2) Tools and Skills

- built-in tools for web fetch/search, file operations, shell execution
- alias mapping (`tools.aliases`) to swap underlying tools without changing prompt habits
- MCP filters (`mcp_enabled_servers/tools`, `mcp_disabled_servers/tools`) for precise exposure control

### 3) Multi-channel adapters

- Telegram recommended as default channel
- additional adapters: Discord / Feishu / DingTalk / QQ / Slack / WhatsApp / Email / Mochat
- adapters map protocol differences; runtime behavior stays in core logic

### 4) Ops and diagnostics

- `orbitclaw status` + `orbitclaw doctor`
- WebUI for models/APIs, channels, MCP, skills, media
- Docker deployment with shared runtime directory requirements

## Quick Start

### 1) Install

```bash
git clone <your-orbitclaw-repo-url>
cd orbitclaw
pip install -e .
```

### 2) Bootstrap

```bash
orbitclaw onboard
```

### 3) Start gateway

```bash
orbitclaw gateway
```

### 4) Start WebUI

```bash
orbitclaw webui --host 0.0.0.0 --port 18791
```

WebUI is protected by a path token (no username/password popup).

## Provider Configuration Example

Edit `/Users/<you>/.orbitclaw/config.json`:

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

Put secrets in `/Users/<you>/.orbitclaw/.env`:

```bash
OPENAI_API_KEY=sk-xxx
```

## MCP Recommendations

For Chinese MCP discovery and category browsing, use:

- [Awesome-MCP-ZH](https://github.com/yzfly/Awesome-MCP-ZH?tab=readme-ov-file)

Recommended integration style in OrbitClaw:

1. keep runtime lean: install only task-relevant MCP servers
2. map stable aliases in `tools.aliases` (`doc_read`, `image_read`, `code_search`)
3. verify with `orbitclaw doctor` after each MCP addition
4. record resource impact before keeping it enabled by default

Prompt template for adding a new MCP safely:

```text
Add MCP server "<name>" with minimum required tools only.
Then add aliases for common tasks and keep all other tools disabled by default.
Finally, run a health check and report config diff + rollback steps.
```

## Runtime Layout

```text
orbitclaw/
├── orbitclaw/          # runtime core
├── assets/             # brand assets
├── docs/public/        # publishable docs
├── release/            # public baseline only
├── scripts/            # quality and release scripts
└── tests/public/       # public regression subset
```

Key runtime paths:

- `/Users/<you>/.orbitclaw/config.json`
- `/Users/<you>/.orbitclaw/.env`
- `/Users/<you>/.orbitclaw/env/`
- `/Users/<you>/.orbitclaw/workspace`
- `/Users/<you>/.orbitclaw/mcp`
- `/Users/<you>/.orbitclaw/skills`
- `/Users/<you>/.orbitclaw/media`
- `/Users/<you>/.orbitclaw/exports`

## Development Roadmap (Open)

These are intentionally unchecked; mark them only when done.

- [ ] Split large modules by testable responsibilities (`cli/commands.py`, `channels/mochat.py`, `channels/feishu.py`)
- [ ] Keep channels centralized for management while separating protocol mapping from runtime business logic
- [ ] Improve release engineering flow (`main`-only product release, stronger CI branch/tag gates)
- [ ] Dependency slimming plan (default minimal install + optional channel extras)
- [ ] WebUI visual cleanup and interaction polish (after core bot behavior milestones)
- [ ] Expand MCP recommendation library and one-click install guidance
- [ ] Continue core-bot reliability passes before new channel features

## Governance

- Public governance docs: `docs/public/governance/README.md`
- Security policy: `SECURITY.md`
- Publishing guide: `docs/public/governance/PUBLISHING.md`
- Open-source boundary rules: `docs/public/governance/OPEN_SOURCE_RULES.md`
- Lint baseline: `release/lint-baseline.txt`
- Public whitelist: `PUBLIC_WHITELIST.md`

## Upstream Attribution

This project is based on [HKUDS/nanobot](https://github.com/HKUDS/nanobot) and distributed under MIT-compatible terms.

- details: `NOTICE`
- license: `LICENSE`
