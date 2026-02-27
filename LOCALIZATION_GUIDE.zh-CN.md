# nanobot 本土化二开：工具与技能治理指南（中文）

本文档面向 `codex/dev` 分支，目标是先把工具与技能治理做稳，再逐步替换/新增更符合个人习惯的能力。

## 1. 当前已支持的治理能力（本分支）

目前已经具备以下配置能力（无需改整体框架）：

- `tools.enabled`：内置工具白名单（空列表表示全部启用）
- `tools.aliases`：工具别名映射（`alias -> target`），支持内置工具和 MCP 工具
- `tools.web.search.provider`：搜索后端选择（`exa_mcp` / `disabled`）
- `profiles.active` + `profiles.items`：场景配置档（`cn_dev / research / offline`）
- `tools.mcpServers`：配置 MCP 服务器
- `tools.mcpEnabledServers` / `tools.mcpDisabledServers`：MCP 服务端过滤
- `tools.mcpEnabledTools` / `tools.mcpDisabledTools`：MCP 工具过滤（支持原名 / 包装名 / `server.tool`）
- `skills.disabled`：技能黑名单（从上下文隐藏）
- 技能元信息识别：`requires_cli / requires_env / requires_network / category / lang`

另外：

- `web_search` 已支持 Exa MCP 兼容别名（主代理 + 子代理）
- `nanobot status` 已增强工具/技能诊断（缺 API key、MCP 命令缺失、过滤状态等）
- `nanobot doctor` 已支持修复导向诊断（问题原因 + 修复建议）
- 聊天内命令 `/model`：按会话切换模型（不改全局默认）
- 配置支持 `${ENV_VAR}` 占位符，且会自动读取 `~/.nanobot/.env` / `~/.nanobot/env/*.env`
- 运行目录已收口：`~/.nanobot/config.json`、`~/.nanobot/.env`、`~/.nanobot/env/`、`~/.nanobot/mcp/`、`~/.nanobot/skills/`

## 2. 当前内置工具盘点（Built-in Tools）

内置工具（可通过 `tools.enabled` 控制）：

- `read_file`：读取文件
- `write_file`：写入文件
- `edit_file`：按补丁/编辑方式修改文件
- `list_dir`：列目录内容
- `exec`：执行 shell 命令
- `web_search`：联网搜索（当前统一走 Exa MCP）
- `web_fetch`：抓取网页并提取正文（增强版 Readability + HTML fallback + 二进制内容提示）
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

### 4.0.1 推荐的密钥维护方式（统一 env 文件）

适合你这种第三方 API 平台、多模型切换场景：

- 把 API Base / Key 放到 `~/.nanobot/.env` 或 `~/.nanobot/env/*.env`
- `config.json` 中用 `${ENV_VAR}` 占位符引用
- 这样切换平台和轮换 key 不需要改主配置文件

示例：

```json
{
  "providers": {
    "custom": {
      "apiBase": "${MY_API_BASE}",
      "apiKey": "${MY_API_KEY}"
    }
  }
}
```

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
        "url": "https://mcp.exa.ai/mcp?tools=web_search_exa,get_code_context_exa&exaApiKey=${EXA_API_KEY}"
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
        "url": "https://mcp.exa.ai/mcp?tools=web_search_exa,get_code_context_exa&exaApiKey=${EXA_API_KEY}"
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

说明：发布给他人使用时，建议要求用户自己申请 Exa Key，并在 `~/.nanobot/.env`（或 `~/.nanobot/env/*.env`）里设置 `EXA_API_KEY`。

说明：

- `docloader` 用于图片、PDF、Word、PPT、Excel 等附件解析
- 使用 `doc_read` / `image_read` 别名可以保持稳定调用习惯
- `github` skill 建议保留（依赖 `gh`，但比 GitHub MCP 更轻）

### 4.1.2 第三阶段：WebUI 工具策略联动

`MCP & Skills` 页面已支持可视化编辑以下项（不必手改 JSON）：

- 内置工具白名单（`tools.enabled`，支持“全部启用”）
- 工具别名（`tools.aliases`，每行 `alias = target`）
- MCP 服务/工具过滤（`mcpEnabled*` / `mcpDisabled*`）

这意味着你可以在 WebUI 完成“启用哪些工具 + 别名映射 + MCP 过滤”的一次性联调，再用 JSON 作为兜底高级编辑器。

### 4.1.3 第三阶段：页面拆分 + 新手友好 + 多语言

WebUI 已按职责拆分为独立页面：

- `MCP`：MCP 服务器状态、模板库安装、隐私说明
- `Skills`：技能启用/禁用、技能包一键应用
- （已简化）工具细粒度策略建议直接改 `config.json`，不再作为新手主入口

同时新增：

- 语言切换：默认英文（`lang=en`），可切换中文（`lang=zh-CN`）
- 隐私保护：MCP URL 展示自动脱敏（`apiKey/token/secret/password`）
- 新手模板：
  - MCP 模板库：Exa / Docloader 一键安装
  - 技能包：Starter / Developer / Minimal
  - 技能导入：支持从 `https://.../SKILL.md` URL 直接导入到全局技能目录

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

### 4.4 导出目录与统一导出工具（轻量）

默认导出目录是 `~/.nanobot/exports`，可通过配置改到你自己的路径：

```json
{
  "tools": {
    "filesHub": {
      "exportsDir": "/data/nanobot-exports"
    }
  }
}
```

建议：

- 用 `export_file` 统一导出结果文件（`txt/md/json/docx`）
- 用 `files_hub(scope=\"exports\")` 做列表与清理
- 输入（`media`）和输出（`exports`）分离，避免误删原件

### 4.5 第一阶段/第二阶段新增：资源优化 + 语言本土化

本轮新增了两类高收益低成本参数，默认即可用，也可在 WebUI 的 `Models & APIs` 页面直接调：

```json
{
  "agents": {
    "defaults": {
      "replyLanguage": "auto",
      "autoReplyFallbackLanguage": "zh-CN",
      "crossLingualSearch": true,
      "maxHistoryChars": 32000,
      "maxMemoryContextChars": 12000,
      "maxBackgroundContextChars": 22000,
      "maxInlineImageBytes": 400000,
      "autoCompactBackground": true,
      "systemPromptCacheTtlSeconds": 20,
      "sessionCacheMaxEntries": 16,
      "gcEveryTurns": 12
    }
  }
}
```

说明：

- `maxHistoryChars` / `maxMemoryContextChars`：直接控制请求上下文体积，降低 token 消耗
- `maxBackgroundContextChars` + `autoCompactBackground`：自动压缩背景信息（优先提取结构信号，再截断）
- `maxInlineImageBytes`：超大图片不再内联 base64，避免一次请求爆 token，改走 `image_read`
- `systemPromptCacheTtlSeconds`：短 TTL 缓存系统提示，减少重复 IO/拼装开销
- `sessionCacheMaxEntries` + `gcEveryTurns`：长期运行时自动回收内存
- `autoReplyFallbackLanguage`：当语言检测不明确时使用回退语言，默认中文；国际用户改为 `en/ja/ko` 即可

### 4.3 聊天内控制服务器 Claude Code（tmux 模式，可选）

> 适合你这种“在 TG/聊天里发指令，让服务器上的 Claude Code 持续执行”的场景。

```json
{
  "tools": {
    "claudeCode": {
      "enabled": true,
      "command": "claude",
      "tmuxCommand": "tmux",
      "sessionPrefix": "cc_",
      "captureLines": 120,
      "maxOutputChars": 12000
    }
  }
}
```

说明：

- 默认是关闭的（`enabled=false`），需要显式开启
- 依赖本机命令：`tmux`、`claude`
- 建议配合 `tmux` skill 和新的 `claude-code` skill 一起使用（提高工具调用稳定性）
- 聊天中可让机器人使用 `claude_code` 工具执行：
  - `start`（启动会话）
  - `send`（发送任务）
  - `status` / `tail`（查看进度）
  - `stop`（结束会话）

## 5. 替换建议（优先级从高到低）

### 5.1 优先替换：搜索与网页抽取

1. `web_search`（已完成统一）
- 当前方案：Exa MCP
- 建议主方案：Exa MCP（搜索 + code context）
- 本分支已移除 Brave 搜索回退，仅保留 Exa MCP 搜索

2. `web_fetch`（已做内置增强，可继续补强）
- 当前 `web_fetch` 已重写增强：内容类型识别、HTML 抽取回退、结构化返回、二进制内容提示
- 当前阶段建议继续保留内置 `web_fetch` 作为默认路径，再按需补充“Fetch/文档解析类 MCP”（轻量）
- 后续若有明确动态网页操作需求，再增加 Playwright MCP（按 profile 启用）
- 做法：先新增 MCP 工具，再用 `tools.aliases` 暴露 `web_fetch_plus`，观察使用频率后再决定是否替换默认 `web_fetch`

轻量示例（推荐先保留内置 `web_fetch`）：

```json
{
  "tools": {
    "aliases": {
      "web_fetch_plus": "mcp_fetch_fetch"
    }
  }
}
```

路由建议：

- 先 `web_fetch`
- 失败/内容缺失再 `web_fetch_plus`
- 仍不行再考虑 Playwright 类工具（不要默认常开）

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

## 6. 技能治理（当前已支持 + 建议用法）

### 6.1 使用 `profiles` 切换场景（已支持）

当前分支已支持：

- `profiles.active`：当前生效 profile 名称
- `profiles.items.<name>.tools`：工具相关覆盖项（作为默认值）
- `profiles.items.<name>.skills`：技能相关覆盖项（作为默认值）

覆盖顺序（重要）：

1. `profiles.items[active]` 先作为基础配置
2. 顶层 `tools` / `skills` 再覆盖 profile（顶层优先）

这样你可以：

- 用 profile 管理“场景基线”
- 用顶层字段做个人常驻修正
- 避免每次切场景都手工改很多字段

### 6.2 给技能增加可用性元信息（渐进式）

你当前部分技能已经在 `metadata.nanobot.requires.bins` 中写了依赖（例如 `gh`/`tmux`/`summarize`）。

建议继续统一：

- `requires.bins`
- `requires.env`
- `requires.network`
- `os`
- `category`
- `lang`

## 7. 发布前固定回归（推荐）

本分支已提供轻量回归脚本：

```bash
./scripts/release_smoke.sh
```

会检查：

- 核心模块语法/编译
- 重点测试（语言策略、文件管理、导出、网页抓取）
- 可选运行态检查（若本机 PATH 里有 `nanobot`，会执行 `status/doctor`）

当前已支持解析这些字段并用于自动隐藏/诊断（缺依赖时）；
建议后续继续给新增技能补齐元信息，保证 `status` / `doctor` 输出更准确。

## 6.3 `doctor` 命令（建议优先用来排障）

```bash
nanobot doctor
```

`doctor` 会优先检查：

- 搜索后端是否可用（Exa MCP）
- `docloader` 是否缺 `uvx`
- alias 配置是否无效
- profile 是否引用了不存在的条目
- 技能依赖是否缺失（例如 `gh`、`tmux`、`summarize`）

适合你这种“工具和技能经常替换”的二开场景。

## 6.4 聊天内切换模型（已支持）

在对话中直接发送：

- `/model`：查看当前会话生效模型
- `/model custom/xxx`：切换当前会话模型（不影响全局）
- `/model reset`：恢复默认模型

这对你使用第三方 API 平台特别实用：同一个机器人会话里可以快速测试不同模型，而不用改配置重启。

## 6.5 本地 Web 管理界面（已支持，轻量版）

启动命令：

```bash
nanobot webui
```

默认地址（仅本机监听）：

```text
http://127.0.0.1:18791/
```

可选认证（建议在非本机监听时开启）：

```bash
nanobot webui --path-token your_random_path_token
```

当前第一版页面（偏配置管理，不是聊天前端）：

- Dashboard：健康分、资源雷达、Token 预算雷达、可操作诊断建议
- Models & APIs：管理 `providers.endpoints`（多接口、多模型、类型）
- Channels：多渠道配置 JSON 编辑器（统一管理 TG/Discord/Feishu/...）
- MCP & Skills：MCP 概览、推荐 Exa+docloader 一键写入、技能启用/禁用

适合你的场景：

- 经常切换第三方 API 平台与模型
- 想集中管理渠道/MCP/技能，而不是手工改 JSON
- 仍然保持“项目不臃肿”（不引入重前端构建）

## 6.6 发布前烟测（Sprint 4）

除了 `./scripts/release_smoke.sh`，建议增加一轮 Docker 端到端烟测：

```bash
./tests/test_docker.sh
```

这轮会验证：

- `docker compose` 启停是否正常
- 容器内 `nanobot onboard/status/doctor`
- WebUI 路径密钥是否已生成
- `/{path_token}/healthz` 与仪表盘关键字段是否可访问

如果这一步失败，优先先修复容器运行路径，再考虑功能层问题。

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
- 适合 nanobot：继续增强 `nanobot status` / `nanobot doctor`，把“缺什么、如何修”说清楚

4. MCP 市场/注册表（发现与安装体验）
- 灵感：把“可用 MCP 工具”从 scattered README 变成可搜索目录
- 适合 nanobot：后续加 `nanobot mcp list/recommend`（先做只读推荐，不急着自动安装）

## 8. 推荐下一步开发路线（按你的方向）

1. 做 `tools.aliases` 的高阶能力（已支持基础版）
- 可考虑支持 alias chain 检测、冲突策略、只读别名标记

2. 继续增强 `nanobot doctor`
- 重点输出（下一阶段）：
- API key 缺失
- CLI 缺失（`gh`、`tmux`、`summarize` 等）
- MCP server 不可达 / 被过滤
- 技能依赖不满足

3. 继续完善 `profiles`
- 当前已支持 `active + items`
- 下一步可补 profile 切换命令/模板导出

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
