# 工具与技能策略（中文个人化版）

> 目标：不改框架，仅调整工具/技能可用性与调用优先级；默认中文输出。

## 一、内置工具盘点（当前）

| 工具 | 默认状态 | 依赖 | 无依赖/无 API 时可用性 | 建议 |
|---|---|---|---|---|
| `read_file` | 启用 | 无 | ✅ 可用 | 保留 |
| `write_file` | 启用 | 无 | ✅ 可用 | 保留 |
| `edit_file` | 启用 | 无 | ✅ 可用 | 保留 |
| `list_dir` | 启用 | 无 | ✅ 可用 | 保留 |
| `exec` | 启用 | Shell 环境 | ✅ 可用 | 保留（高风险命令谨慎） |
| `web_fetch` | 启用 | 网络 | ⚠️ 网络受限时失败 | 保留 |
| `web_search` | 启用（可被配置禁用） | Brave Search API Key | ❌ 无 key 不可用 | 如无 key 建议禁用 |
| `message` | 启用 | 渠道配置 | ⚠️ CLI 下通常不需要 | 保留 |
| `spawn` | 启用 | 无 | ✅ 可用 | 保留（复杂任务再用） |
| `cron` | 按运行模式可用 | cron 服务 | ✅ 可用 | 保留 |
| MCP 工具 | 按配置动态加载 | MCP server + 可选认证 | ❌ 配置不完整不可用 | 无 API/无服务先禁用 |

## 二、内置技能盘点（当前）

| 技能 | 主要用途 | 关键依赖 | 无依赖时状态 | 建议 |
|---|---|---|---|---|
| `memory` | 记忆规范（always） | 无 | ✅ 可用 | 保留 |
| `cron` | 定时任务语义 | 无 | ✅ 可用 | 保留 |
| `weather` | 天气查询 | `curl` | ✅（通常可用） | 保留 |
| `github` | GitHub 自动化 | `gh` CLI | ❌ 无 `gh` 不可用 | 无需 GitHub 可禁用 |
| `tmux` | 交互式会话控制 | `tmux` | ❌ 无 `tmux` 不可用 | 不做多会话可禁用 |
| `summarize` | 链接/视频摘要 | `summarize` CLI + 对应模型 API | ❌ 常见为不可用 | 没装 CLI 或没 key 先禁用 |
| `clawhub` | 安装技能 | `npx` / Node.js | ⚠️ 无 Node 不可用 | 需要扩展技能时再启用 |
| `skill-creator` | 设计新技能 | 无硬依赖 | ✅ 可用 | 仅在创建技能时启用 |

## 三、配置策略（已支持）

### 1) 工具白名单（推荐）

在 `~/.nanobot/config.json` 中设置：

```json
{
  "tools": {
    "enabled": [
      "read_file",
      "write_file",
      "edit_file",
      "list_dir",
      "exec",
      "web_fetch",
      "message",
      "spawn",
      "cron"
    ]
  }
}
```

> `enabled` 为空表示默认全开。建议个人开发先使用白名单。

### 2) 技能黑名单

```json
{
  "skills": {
    "disabled": ["github", "tmux", "summarize", "clawhub"]
  }
}
```

### 3) 无 API 场景建议

- 无 Brave key：移除 `web_search`。
- 无 MCP 服务/API：不要配置 `tools.mcpServers`，或把依赖外部 API 的 server 先全部移除。
- 无 GitHub CLI：禁用 `github` 技能。
- 无 Node.js：暂不使用 `clawhub` 技能。

## 四、中文调用规范

- 对用户先中文解释再执行工具。
- 执行命令前说明一句目的。
- 输出默认中文；保留命令、路径、函数名原文。
