# nanobot 本土化二开：工具与技能治理指南（中文）

本文档面向 `codex/dev` 分支，目标是先把工具与技能治理做稳，再逐步替换/新增更符合个人习惯的能力。

## 1. 当前已支持的治理能力（本分支）

目前已经具备以下配置能力（无需改整体框架）：

- `tools.enabled`：内置工具白名单（空列表表示全部启用）
- `tools.aliases`：工具别名映射（`alias -> target`），支持内置工具和 MCP 工具
- `tools.web.search.provider`：搜索后端选择（`auto | brave | exa_mcp | disabled`）
- `tools.mcpServers`：配置 MCP 服务器
- `tools.mcpEnabledServers` / `tools.mcpDisabledServers`：MCP 服务端过滤
- `tools.mcpEnabledTools` / `tools.mcpDisabledTools`：MCP 工具过滤（支持原名 / 包装名 / `server.tool`）
- `skills.disabled`：技能黑名单（从上下文隐藏）

另外：

- `web_search` 已支持 Exa MCP 兼容别名（主代理 + 子代理）
- `nanobot status` 已增强工具/技能诊断（缺 API key、MCP 命令缺失、过滤状态等）

## 2. 当前内置工具盘点（Built-in Tools）

内置工具（可通过 `tools.enabled` 控制）：

- `read_file`：读取文件
- `write_file`：写入文件
- `edit_file`：按补丁/编辑方式修改文件
- `list_dir`：列目录内容
- `exec`：执行 shell 命令
- `web_search`：联网搜索（当前可选 Brave / Exa MCP）
- `web_fetch`：抓取网页并提取正文（Readability）
- `message`：给用户/渠道发送消息
- `spawn`：启动子代理执行任务
- `cron`：定时任务（提醒/任务）

动态工具层：

- MCP 工具会被注册为 `mcp_<server>_<tool>`
- 现在可以通过 `tools.aliases` 给 MCP 工具起稳定名字（例如把 `mcp_exa_web_search_exa` 映射成 `web_search`）

## 3. 当前内置技能盘点（Skills）

仓库自带技能（`nanobot/skills/*/SKILL.md`）：

- `memory`：双层记忆（`MEMORY.md` + `HISTORY.md`），常驻技能
- `cron`：围绕 `cron` 工具的调度与任务用法说明
- `github`：基于 `gh` CLI 的 GitHub 操作（依赖 `gh`）
- `tmux`：交互式 CLI/TUI 场景的 tmux 远程操控（依赖 `tmux`）
- `summarize`：URL/文件/视频转摘要与提取（依赖 `summarize` CLI）
- `weather`：天气查询（依赖 `curl`，无需 API key）
- `clawhub`：技能搜索与安装（公共技能仓库）
- `skill-creator`：创建/更新技能的规范与流程

建议按依赖可用性分层管理：

- 常驻：`memory`
- 常用：`github`、`cron`
- 条件启用：`tmux`、`summarize`、`clawhub`
- 场景型：`weather`、`skill-creator`

## 4. 推荐配置模板（以你当前方向为主）

### 4.0 当前推荐栈（轻量优先，适合你的项目）

我建议的默认选择（当前阶段）：

- `web_search`：`exa_mcp`（你已确定）
- `web_fetch` 增强方向：**Fetch/文档解析方向**（先不上 Playwright）
- GitHub 能力：**保留 `github` skill + `gh` CLI**（最轻、最稳）
- 附件分析：新增 `attachment-analyzer` skill（配合文档/图片 MCP）

为什么不先上 Playwright：

- 运行时更重（浏览器、依赖、维护成本）
- 你当前更急的是聊天附件（图片/PDF/Word/PPT/表格）解析与反馈
- 等明确出现“动态网页操作/表单自动化”刚需，再按 profile 增量启用

### 4.1 中文开发默认（Exa 搜索 + 精简技能）

```json
{
  "tools": {
    "enabled": ["read_file", "write_file", "edit_file", "list_dir", "exec", "web_search", "web_fetch", "message", "spawn"],
    "web": {
      "search": {
        "provider": "exa_mcp"
      }
    },
    "mcpServers": {
      "exa": {
        "url": "https://mcp.exa.ai/mcp?tools=web_search_exa,get_code_context_exa"
      }
    },
    "mcpEnabledServers": ["exa"],
    "mcpEnabledTools": ["web_search_exa", "get_code_context_exa"],
    "aliases": {
      "web_search": "mcp_exa_web_search_exa",
      "code_search": "mcp_exa_get_code_context_exa"
    }
  },
  "skills": {
    "disabled": ["tmux", "clawhub", "summarize"]
  }
}
```

### 4.1.1 中文开发默认（含附件解析 MCP，推荐）

> 在 4.1 的基础上增加文档/图片解析能力（低臃肿高收益）。

```json
{
  "tools": {
    "enabled": ["read_file", "write_file", "edit_file", "list_dir", "exec", "web_search", "web_fetch", "message", "spawn"],
    "web": {
      "search": {
        "provider": "exa_mcp"
      }
    },
    "mcpServers": {
      "exa": {
        "url": "https://mcp.exa.ai/mcp?tools=web_search_exa,get_code_context_exa"
      },
      "docloader": {
        "command": "uvx",
        "args": ["awslabs.document-loader-mcp-server@latest"],
        "env": {
          "FASTMCP_LOG_LEVEL": "ERROR"
        }
      }
    },
    "mcpEnabledServers": ["exa", "docloader"],
    "mcpEnabledTools": ["web_search_exa", "get_code_context_exa", "read_document", "read_image"],
    "aliases": {
      "web_search": "mcp_exa_web_search_exa",
      "code_search": "mcp_exa_get_code_context_exa",
      "doc_read": "mcp_docloader_read_document",
      "image_read": "mcp_docloader_read_image"
    }
  },
  "skills": {
    "disabled": ["tmux", "clawhub", "summarize", "weather"]
  }
}
```

说明：

- `docloader` 用于图片、PDF、Word、PPT、Excel 等附件解析
- 使用 `doc_read` / `image_read` 别名可以保持稳定调用习惯
- `github` skill 建议保留（依赖 `gh`，但比 GitHub MCP 更轻）

### 4.2 离线/受限环境（尽量不报错）

```json
{
  "tools": {
    "enabled": ["read_file", "write_file", "edit_file", "list_dir", "exec", "message", "spawn"],
    "web": {
      "search": {
        "provider": "disabled"
      }
    }
  },
  "skills": {
    "disabled": ["github", "tmux", "summarize", "clawhub", "weather"]
  }
}
```

## 5. 替换建议（优先级从高到低）

### 5.1 优先替换：搜索与网页抽取

1. `web_search`（已开始）
- 当前方案：Brave / Exa MCP
- 建议主方案：Exa MCP（搜索 + code context）
- 保留 Brave 作为 `auto` 模式回退

2. `web_fetch`（建议增强，不一定完全替换）
- 当前 `web_fetch` 基于 Readability，通用页面够用
- 当前阶段建议先补充“Fetch/文档解析类 MCP”（轻量）
- 后续若有明确动态网页操作需求，再增加 Playwright MCP（按 profile 启用）
- 做法：先新增 MCP 工具，再用 `tools.aliases` 暴露 `web_fetch_plus`，观察使用频率后再决定是否替换默认 `web_fetch`

### 5.2 优先新增：代码与文档类 MCP

1. 文档/知识检索 MCP
- 用于替代“普通网页搜索 + 手工点链接”的低效链路
- 适合场景：库文档、API 说明、版本变更、代码片段检索

2. 浏览器自动化 MCP（如 Playwright 类）
- 适合场景：登录后页面、动态渲染页面、表单流程
- 建议不要默认开给所有场景，先走 `mcpEnabledServers` 控制

3. 代码仓库/PR 操作 MCP（可选）
- 你当前已有 `github` 技能（`gh` CLI）已经很好用
- 若后续想降低 CLI 依赖，可新增 GitHub MCP 作为补充，不必立即替换

### 5.3 暂不建议优先做的替换

- 文件工具（`read_file`/`write_file`/`edit_file`/`list_dir`）
- `exec`
- `spawn`

原因：

- 这些是框架核心能力，替换风险高、收益有限
- 先做治理（白名单/别名/诊断/配置）性价比更高

## 6. 技能治理建议（下一阶段）

### 6.1 从“黑名单”升级到“配置档（profiles）”

建议新增概念（下一步可做）：

- `profiles.cn_dev`
- `profiles.offline`
- `profiles.research`

每个 profile 包含：

- `tools.enabled`
- `tools.aliases`
- `tools.web.search.provider`
- `tools.mcp*` 过滤项
- `skills.disabled`

这样可以一键切换“开发/离线/调研”模式。

### 6.2 给技能增加可用性元信息（渐进式）

你当前部分技能已经在 `metadata.nanobot.requires.bins` 中写了依赖（例如 `gh`/`tmux`/`summarize`）。

建议继续统一：

- `requires.bins`
- `requires.env`
- `requires.network`
- `os`
- `category`
- `lang`

之后可让 `nanobot status` / `doctor` 直接显示“技能不可用原因”。

## 7. 从外部项目借鉴的设计点（适合 nanobot）

以下不是“照搬”，而是提炼适合你这套二开路线的部分：

1. Continue（配置分层/工作区覆盖）
- 灵感：把规则、模型、工具、上下文源拆层管理，支持工作区级覆盖
- 适合 nanobot：未来把“个人默认配置”和“项目配置”分开（例如 `workspace/.nanobot.project.json`）

2. Cline（模式 + Hooks）
- 灵感：不同模式使用不同工具权限，并支持调用前后钩子
- 适合 nanobot：后续给 `exec` / `write_file` / `deploy` 类工具做 pre/post hook（审计、确认、日志）

3. OpenHands（集中设置入口）
- 灵感：模型、代理行为、沙箱、外部服务统一放在设置面板/入口
- 适合 nanobot：增强 `nanobot status` / 新增 `nanobot doctor`，把“缺什么、如何修”说清楚

4. MCP 市场/注册表（发现与安装体验）
- 灵感：把“可用 MCP 工具”从 scattered README 变成可搜索目录
- 适合 nanobot：后续加 `nanobot mcp list/recommend`（先做只读推荐，不急着自动安装）

## 8. 推荐下一步开发路线（按你的方向）

1. 做 `tools.aliases` 的高阶能力（已支持基础版）
- 可考虑支持 alias chain 检测、冲突策略、只读别名标记

2. 新增 `nanobot doctor`
- 重点输出：
- API key 缺失
- CLI 缺失（`gh`、`tmux`、`summarize` 等）
- MCP server 不可达 / 被过滤
- 技能依赖不满足

3. 做 `profiles`
- 这是你“本土化二开”的关键效率工具

4. 再做工具替换/新增
- 优先：搜索、网页抽取、文档检索
- 再考虑：浏览器自动化、GitHub MCP、知识库类 MCP

## 9. 外部参考（灵感来源）

- Continue 自定义总览：https://docs.continue.dev/customize/overview
- Continue 配置参考：https://docs.continue.dev/reference
- Cline 自定义总览：https://docs.cline.bot/features/customization/overview
- Cline Hooks：https://docs.cline.bot/features/hooks
- Cline MCP Marketplace：https://docs.cline.bot/mcp/mcp-marketplace
- OpenHands Settings：https://docs.all-hands.dev/usage/gui/settings
- awesome-mcp-servers（社区汇总）：https://github.com/punkpeye/awesome-mcp-servers

## 10. 维护建议（你这个仓库的工作方式）

建议以后固定在 `codex/dev` 上进行本土化二开：

- 新能力先做“可配置 + 可回退”
- 先新增工具，再观察，再决定是否替换默认
- 每次改动后跑 `nanobot status` 看诊断输出是否符合预期
- 用 `tools.aliases` 保持 prompt/习惯稳定，减少模型行为漂移
