# Security Policy

**Language / 语言**: [English](SECURITY.md) | [简体中文](SECURITY.zh-CN.md)

---

## Quick Start Hardening

If you only do 6 things before production, do these:

1. Set `allowFrom` for every enabled channel (empty means allow-all).
2. Protect runtime files: `~/.lunaeclaw` = `700`, secrets/config = `600`.
3. Run as non-root user.
4. If WhatsApp bridge is enabled, set non-empty `channels.whatsapp.bridgeToken`.
5. Minimize tool exposure (`tools.enabled`, optional `tools.restrictToWorkspace=true`).
6. Run dependency audit (`pip-audit`, `npm audit`).

---

## Scope

This policy applies to:

- `lunaeclaw` Python runtime (gateway, WebUI, channels, tools)
- bundled WhatsApp bridge (`bridge/`)
- default data directory: `~/.lunaeclaw`

## Security Reality Check (Current Behavior)

| Area | Current behavior | Operational risk |
| --- | --- | --- |
| Channel auth | `allowFrom` empty means open access (`BaseChannel.is_allowed`) | unauthorized users can interact with bot |
| WebUI auth | path-token URL, token stored at `~/.lunaeclaw/webui.path-token` | leaked token gives UI access |
| Health endpoint | `/healthz` reachable without token | low-risk endpoint discovery |
| Shell tool (`exec`) | deny-pattern guard + timeout, not OS sandbox | still risky under broad host permissions |
| File tools | traversal protection + optional workspace restriction | broad host permissions still increase blast radius |

## 10-Minute Baseline Hardening

### 1) Restrict channel access

Example:

```json
{
  "channels": {
    "telegram": {
      "enabled": true,
      "token": "${TELEGRAM_BOT_TOKEN}",
      "allowFrom": ["123456789"]
    }
  }
}
```

### 2) Lock file permissions

```bash
chmod 700 ~/.lunaeclaw
chmod 600 ~/.lunaeclaw/config.json
chmod 600 ~/.lunaeclaw/.env
```

### 3) Use env placeholders for secrets

Store values in env files or secret manager, keep config as `${ENV_VAR}` references.

### 4) Harden WhatsApp bridge when enabled

Facts from code (`bridge/src/server.ts`):

- binds to `127.0.0.1`
- supports optional token auth (`BRIDGE_TOKEN` / `channels.whatsapp.bridgeToken`)
- auth state stored in `~/.lunaeclaw/whatsapp-auth`

Set strict permissions:

```bash
chmod 700 ~/.lunaeclaw/whatsapp-auth
```

### 5) Minimize tool surface

- keep `tools.enabled` minimal
- consider `tools.restrictToWorkspace=true`
- avoid enabling risky tools unless required

### 6) Patch dependencies continuously

Python:

```bash
pip install pip-audit
pip-audit
```

Node.js bridge:

```bash
cd bridge
npm audit
npm audit fix
```

## Deployment Profiles

### Profile A: Docker Compose (preferred)

- run gateway + webui in containerized services
- expose only required ports
- bind one dedicated host runtime directory via `LUNAECLAW_HOST_DATA_DIR`

### Profile B: Bare metal / VM

- dedicated service user
- strict `700/600` permissions
- host firewall for inbound ports
- central log collection

### Profile C: Windows operators

- prefer WSL2 or Docker Desktop
- avoid long-running privileged admin-shell deployment

## Incident Response Runbook

1. Revoke compromised API keys.
2. Stop gateway, WebUI, and bridge.
3. Review logs and channel access events.
4. Rotate all secrets in env/config references.
5. Patch dependencies and redeploy from clean artifacts.
6. Report details to maintainers.

## Vulnerability Reporting

Report privately:

1. Do **not** post exploit details in public issues.
2. Use GitHub private security advisory, or email `xubinrencs@gmail.com`.
3. Include version/commit, steps to reproduce, impact, and optional fix direction.

Target response time: **within 48 hours**.

## Known Limitations

- no built-in global message rate limiter
- open-by-default channel policy unless `allowFrom` is configured
- secrets can still end up in plain text if operators choose config-only storage
- `exec` safety is pattern-based guard, not full sandbox isolation
- security logging exists but is not a full SIEM pipeline

## Pre-Deployment Checklist

- [ ] strict `allowFrom` configured for all enabled channels
- [ ] runtime permissions hardened (`700/600`)
- [ ] non-root runtime user enforced
- [ ] WhatsApp bridge token set (if enabled)
- [ ] dependency audits completed (`pip-audit`, `npm audit`)
- [ ] log monitoring and alerting in place
- [ ] rollback procedure documented and tested

## Update Notes

Last updated: **2026-03-05**
