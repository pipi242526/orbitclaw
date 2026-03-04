# 安全策略

**Language / 语言**: [English](SECURITY.md) | [简体中文](SECURITY.zh-CN.md)

---

## 快速加固（上线前先做这 6 件事）

1. 所有启用渠道都配置 `allowFrom`（空列表 = 默认放行）。
2. 收紧权限：`~/.lunaeclaw` 设为 `700`，配置/密钥文件设为 `600`。
3. 使用非 root 用户运行。
4. 启用 WhatsApp bridge 时，设置非空 `channels.whatsapp.bridgeToken`。
5. 最小化工具暴露面（`tools.enabled`，可选 `tools.restrictToWorkspace=true`）。
6. 做依赖安全扫描（`pip-audit`、`npm audit`）。

---

## 适用范围

本策略适用于：

- `lunaeclaw` Python runtime（gateway / WebUI / channels / tools）
- 内置 WhatsApp bridge（`bridge/`）
- 默认运行目录 `~/.lunaeclaw`

## 当前安全现状（代码层面的真实行为）

| 模块 | 当前行为 | 运维风险 |
| --- | --- | --- |
| 渠道认证 | `allowFrom` 为空时默认放行（`BaseChannel.is_allowed`） | 未授权用户可能直接使用机器人 |
| WebUI 认证 | path-token URL，token 保存在 `~/.lunaeclaw/webui.path-token` | token 泄露即管理面泄露 |
| 健康检查接口 | `/healthz` 无 token 可访问 | 有低风险探测面 |
| Shell 工具 `exec` | 危险模式拦截 + 超时，不是 OS 沙箱 | 主机权限过大时仍有执行风险 |
| 文件工具 | 有路径穿越防护，可选工作区限制 | 主机权限过宽会放大风险面 |

## 10 分钟基线加固

### 1) 收紧渠道入口

示例：

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

### 2) 收紧目录和文件权限

```bash
chmod 700 ~/.lunaeclaw
chmod 600 ~/.lunaeclaw/config.json
chmod 600 ~/.lunaeclaw/.env
```

### 3) 密钥放环境变量

配置文件优先使用 `${ENV_VAR}` 占位，真实密钥存 env 或外部 secret manager。

### 4) 启用 WhatsApp 时加固 bridge

来自代码（`bridge/src/server.ts`）的事实：

- bridge 只绑定 `127.0.0.1`
- 支持可选 token 鉴权（`BRIDGE_TOKEN` / `channels.whatsapp.bridgeToken`）
- 认证状态目录为 `~/.lunaeclaw/whatsapp-auth`

建议权限：

```bash
chmod 700 ~/.lunaeclaw/whatsapp-auth
```

### 5) 最小化工具暴露面

- `tools.enabled` 仅保留必要工具
- 可选开启 `tools.restrictToWorkspace=true`
- 高风险工具按需启用

### 6) 依赖持续打补丁

Python：

```bash
pip install pip-audit
pip-audit
```

Node bridge：

```bash
cd bridge
npm audit
npm audit fix
```

## 部署档位建议

### 档位 A：Docker Compose（优先）

- gateway + webui 容器化
- 只暴露必要端口
- 用 `LUNAECLAW_DATA_DIR` 统一挂载数据目录

### 档位 B：裸机 / VM

- 专用服务用户
- 严格 `700/600` 权限
- 主机防火墙限制入站
- 日志集中采集

### 档位 C：Windows 运维

- 推荐 WSL2 或 Docker Desktop
- 避免管理员高权限 shell 长期运行

## 事件响应 Runbook

1. 立即吊销已泄露 API Key。
2. 停止 gateway、WebUI、bridge。
3. 排查日志与渠道访问记录。
4. 轮换全部密钥与凭据引用。
5. 升级依赖后从干净构建重新部署。
6. 向维护者同步事件细节。

## 漏洞报告

请走私密渠道：

1. 不要在公开 Issue 暴露利用细节。
2. 使用 GitHub 私有安全通道，或邮件 `xubinrencs@gmail.com`。
3. 提供版本/commit、复现步骤、影响评估、可选修复方向。

目标响应：**48 小时内**。

## 当前限制

- 暂无内置全局消息限流
- 若不配置 `allowFrom`，渠道默认开放
- 若仅靠 config 保存，密钥可能明文落盘
- `exec` 是模式拦截，不是完整沙箱
- 安全日志可用，但不是 SIEM 级能力

## 上线前检查清单

- [ ] 所有启用渠道已配置严格 `allowFrom`
- [ ] 权限已收紧（`~/.lunaeclaw` 为 `700`，配置/密钥文件为 `600`）
- [ ] 已强制非 root 运行
- [ ] 启用 WhatsApp 时已设置 bridge token
- [ ] 已完成 `pip-audit` 和 `npm audit`
- [ ] 已配置日志监控与告警
- [ ] 已准备并演练回滚流程

## 更新说明

最后更新：**2026-03-05**
