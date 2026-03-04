<div align="center">
  <img src="assets/orbitclaw-banner.svg" alt="OrbitClaw banner" width="920" />

# OrbitClaw

**面向 Telegram 优先自动化与本地运维的轻量 Agent 运行时**

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

## 项目定位

OrbitClaw 是独立维护的二次开发运行时，目标是：

- 中文使用习惯友好，Telegram 优先
- 小机器（1C1G）也能稳定跑
- MCP/技能可插拔，核心回路不过度膨胀
- WebUI + CLI 配置和诊断闭环

## 目录

- [基本功能](#基本功能)
- [快速开始](#快速开始)
- [模型配置示例](#模型配置示例)
- [MCP 推荐接入](#mcp-推荐接入)
- [运行目录结构](#运行目录结构)
- [后续开发路线（未完成）](#后续开发路线未完成)
- [治理文档](#治理文档)
- [上游归因](#上游归因)

## OrbitClaw 优势亮点

### 1) 面向真实场景，不是演示型项目

- 默认策略围绕日常聊天自动化（尤其 Telegram）优化
- 出错时优先返回可执行修复建议，而不是仅抛异常文本
- 输出后处理策略可减少工具调用细节外泄

### 2) 轻量优先

- 默认参数针对 1C1G 主机可持续运行
- 队列/超时/上下文预算都可显式配置
- 可选能力保持可选，避免核心路径臃肿

### 3) 可维护性更强

- 核心回路和扩展点分层，降低后续改动风险
- MCP/技能主要通过配置与 aliases 管理，替换成本低
- 诊断与测试已纳入日常开发闭环（`status`、`doctor`、pytest）

### 4) 中文优先但不锁死

- 中文默认体验优先
- 文档双语与 UI i18n 结构已就位，后续扩语种成本更可控

## 基本功能

### 1) 机器人核心能力（优先级最高）

- 统一消息处理主循环与命令路由
- 统一输出后处理（语言统一、输出去泄露、失败修复建议）
- 上下文预算控制（history/memory/background/inline media）
- 队列上限与超时机制，提升可预测性

### 2) 工具与技能

- 内置网页检索/抓取、文件读写、Shell 执行等能力
- `tools.aliases` 支持上层习惯不变、底层工具可替换
- MCP 过滤器支持精细启停与暴露控制

### 3) 多渠道适配

- 默认推荐 Telegram
- 支持 Discord / Feishu / DingTalk / QQ / Slack / WhatsApp / Email / Mochat
- 渠道层负责协议映射，业务逻辑尽量收敛到核心层

### 4) 运维与诊断

- `orbitclaw status` / `orbitclaw doctor`
- WebUI 管理模型、渠道、MCP、技能、媒体
- Docker 部署与共享数据目录一致性检查

## 快速开始

### 1) 安装

```bash
git clone <your-orbitclaw-repo-url>
cd orbitclaw
pip install -e .
```

### 2) 初始化

```bash
orbitclaw onboard
```

### 3) 启动 gateway

```bash
orbitclaw gateway
```

### 4) 启动 WebUI

```bash
orbitclaw webui --host 0.0.0.0 --port 18791
```

WebUI 使用路径密钥访问（不弹账号密码框）。

## 模型配置示例

编辑 `/Users/<you>/.orbitclaw/config.json`：

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

密钥写入 `/Users/<you>/.orbitclaw/.env`：

```bash
OPENAI_API_KEY=sk-xxx
```

## MCP 推荐接入

可参考中文 MCP 聚合清单：

- [Awesome-MCP-ZH](https://github.com/yzfly/Awesome-MCP-ZH?tab=readme-ov-file)

建议接入策略：

1. 只装当前任务必需的 MCP，避免臃肿
2. 用 `tools.aliases` 固定常用入口（`doc_read`、`image_read`、`code_search`）
3. 每次新增 MCP 后跑一次 `orbitclaw doctor`
4. 记录资源影响，再决定是否默认启用

建议提示词模板：

```text
请按“最小暴露”原则接入 MCP <name>：
1) 仅开启必要 tools
2) 为常用能力建立 aliases
3) 默认禁用非必要能力
4) 输出配置 diff、健康检查结果和回滚步骤
```

## 运行目录结构

```text
orbitclaw/
├── orbitclaw/          # 运行时核心
├── assets/             # 品牌资源
├── docs/public/        # 可公开文档
├── release/            # 仅公开 baseline
├── scripts/            # 脚本与质量工具
└── tests/public/       # 公开回归最小集
```

关键运行目录：

- `/Users/<you>/.orbitclaw/config.json`
- `/Users/<you>/.orbitclaw/.env`
- `/Users/<you>/.orbitclaw/env/`
- `/Users/<you>/.orbitclaw/workspace`
- `/Users/<you>/.orbitclaw/mcp`
- `/Users/<you>/.orbitclaw/skills`
- `/Users/<you>/.orbitclaw/media`
- `/Users/<you>/.orbitclaw/exports`

## 后续开发路线（未完成）

以下项先不打勾，完成后再改为 `[x]`：

- [ ] 按可单测职责继续拆分大文件（`cli/commands.py`、`channels/mochat.py`、`channels/feishu.py`）
- [ ] 渠道管理保持集中，但协议映射与核心业务进一步分层
- [ ] 发布工程完善（新仓库 main 发版、CI 分支/Tag 闸门）
- [ ] 依赖瘦身方案（默认最小安装 + 可选渠道扩展）
- [ ] WebUI 交互整理与视觉升级（在核心机器人稳定后进行）
- [ ] MCP 推荐库与一键接入说明继续完善
- [ ] 先持续打磨机器人核心能力，再扩展渠道能力

## 治理文档

- 公开治理文档：`docs/public/governance/README.zh-CN.md`
- 安全策略：`SECURITY.md`
- 发布指南：`docs/public/governance/PUBLISHING.md`
- 开源边界规则：`docs/public/governance/OPEN_SOURCE_RULES.md`
- Lint 基线：`release/lint-baseline.txt`
- 公开白名单：`PUBLIC_WHITELIST.md`

## 上游归因

本项目基于 [HKUDS/nanobot](https://github.com/HKUDS/nanobot) 二次开发，并遵循 MIT 兼容许可。

- 归因详情：`NOTICE`
- 许可证：`LICENSE`
