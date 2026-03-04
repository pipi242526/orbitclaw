<div align="center">
  <img src="assets/lunaeclaw-banner.svg" alt="LunaeClaw banner" width="920" />

# LunaeClaw

**更适合真实部署的多渠道 Agent Runtime**

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

[项目概览](#项目概览) • [安装方式](#安装方式) • [平台支持](#平台支持) • [渠道支持](#渠道支持) • [目录树](#目录树) • [运维命令](#运维命令) • [安全基线](#安全基线)

</div>

## 项目概览

LunaeClaw 面向的是“要上线、要维护、要排障”的场景，不是只跑 demo 的脚手架。

| 你会得到什么 | 为什么实用 |
| --- | --- |
| `lunaeclaw gateway` | 长时运行主循环，适合真实流量 |
| `lunaeclaw webui` | 可视化配置与诊断，不必反复手改 JSON |
| 多渠道适配层 | 一套 runtime 统一接 Telegram/Discord/Feishu/DingTalk/QQ/Slack/WhatsApp/Email/Mochat |
| MCP + Skills + aliases | 业务扩展更灵活，不必频繁改核心代码 |
| `status` + `doctor` | 出问题时快速定位 |

> [!TIP]
> 不绑定单一渠道。你可以只开必要能力，保持系统干净、可控。

## 安装方式

### 先选路线

| 场景 | 推荐 |
| --- | --- |
| 本地开发（macOS/Linux） | `uv sync --extra dev` |
| Windows 工作站 | WSL2 + Ubuntu + `uv` |
| 服务器 / NAS / homelab | Docker Compose |
| 最小可用安装 | `pip install -e .` |

### macOS / Linux 本地开发

前置条件：Python `3.11+`、`uv`；若要启用 WhatsApp bridge，再安装 Node.js `20+`。

```bash
git clone <your-repo-url>
cd LunaeClaw
uv sync --extra dev
uv run lunaeclaw onboard
uv run lunaeclaw gateway
# 另开终端
uv run lunaeclaw webui --host 0.0.0.0 --port 18791
```

### Windows（推荐 WSL2）

```bash
# 在 WSL2 的 Ubuntu 中执行
sudo apt update
sudo apt install -y curl git python3 python3-venv python3-pip
curl -LsSf https://astral.sh/uv/install.sh | sh

git clone <your-repo-url>
cd LunaeClaw
uv sync --extra dev
uv run lunaeclaw onboard
uv run lunaeclaw gateway
```

### 服务器 / NAS（推荐 Docker Compose）

```bash
git clone <your-repo-url>
cd LunaeClaw
mkdir -p ./.lunaeclaw-data
docker compose up -d --build lunaeclaw-gateway lunaeclaw-webui
docker compose logs -f --tail=200
```

默认端口：

- Gateway `18790`
- WebUI `18791`

### 最小可用（editable 安装）

```bash
git clone <your-repo-url>
cd LunaeClaw
pip install -e .
lunaeclaw onboard
lunaeclaw gateway
```

### 首次 Provider 配置

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

做一次健康检查：

```bash
lunaeclaw doctor
```

## 平台支持

> 目前 CI 只跑 `ubuntu-latest`。其它环境依赖链路是通的，但安装后请务必执行 `lunaeclaw doctor`。

| 平台 | 状态 | 推荐安装路径 | 备注 |
| --- | --- | --- | --- |
| Linux 服务器（x86_64/arm64） | 推荐 | Docker Compose | 生产稳定性最好 |
| macOS（Apple Silicon / Intel） | 推荐 | 本地 `uv` | 开发体验最佳 |
| Windows | 支持（建议 WSL2） | WSL2 + Ubuntu | 原生 Windows shell 非主路径 |
| NAS / homelab | 推荐 | Docker Compose | 宿主机挂载便于备份 |

## 渠道支持

| 渠道 | 运行时要求 | 关键配置字段 |
| --- | --- | --- |
| Telegram | Python runtime | `channels.telegram.token`, `allowFrom` |
| Discord | Python runtime | `channels.discord.token`, `allowFrom` |
| Feishu | Python runtime | `channels.feishu.appId`, `appSecret`, `allowFrom` |
| DingTalk | Python runtime | `channels.dingtalk.clientId`, `clientSecret`, `allowFrom` |
| QQ | Python runtime | `channels.qq.appId`, `secret`, `allowFrom` |
| Slack | Python runtime | `channels.slack.botToken`, `appToken` |
| WhatsApp | Python + Node.js bridge（`bridge/`，Node 20+） | `channels.whatsapp.bridgeUrl`, 可选 `bridgeToken`, `allowFrom` |
| Email | Python + IMAP/SMTP | `channels.email.imap*`, `smtp*`, `allowFrom`, `consentGranted` |
| Mochat | Python runtime | `channels.mochat.baseUrl`, `clawToken`, `allowFrom` |

## 目录树

### 仓库目录

```text
LunaeClaw/
├── lunaeclaw/              # 运行时代码（app/core/capabilities/platform/services）
├── bridge/                 # WhatsApp Node.js bridge
├── tests/public/           # 对外回归测试
├── docs/public/            # 可公开治理文档
├── scripts/                # 质量与发布脚本
├── docker-compose.yml      # 本地近生产部署
├── Dockerfile              # 运行镜像构建
└── pyproject.toml          # 依赖与打包元数据
```

### 运行时目录

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
└── bridge/                 # 拷贝并构建后的 WhatsApp bridge
```

## 运维命令

```bash
# 查看整体状态
lunaeclaw status

# 配置与运行时诊断
lunaeclaw doctor

# 渠道配置状态
lunaeclaw channels status

# WhatsApp 登录流程（扫码）
lunaeclaw channels login
```

## 安全基线

上线前至少完成：

- 每个启用渠道都配置 `allowFrom`（空列表 = 默认放行）
- `~/.lunaeclaw` 设为 `700`，配置/密钥文件设为 `600`
- 非 root 用户运行
- 启用 WhatsApp 时设置 `channels.whatsapp.bridgeToken`
- 按 [SECURITY.md](SECURITY.md) 执行加固

## 致谢

- 上游基础项目：[HKUDS/nanobot](https://github.com/HKUDS/nanobot)
- 核心依赖库：`litellm`、`pydantic`、`python-telegram-bot`、`websockets`、`@whiskeysockets/baileys`

感谢上游和生态维护者。

## 许可证

MIT，见 [LICENSE](LICENSE)。
