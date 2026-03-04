---
name: claude-code
description: 在聊天中通过 claude_code 工具控制服务器里的 Claude Code（tmux 会话模式）
metadata:
  orbitclaw:
    requires:
      bins: [tmux, claude]
      network: false
    category: ops
    lang: zh
---

# Claude Code 会话控制（tmux）

当用户要在聊天里控制服务器上的 Claude Code 时，优先使用 `claude_code` 工具，不要直接使用 `exec` 拼装 tmux 命令。

## 推荐流程

1. `start`
- 启动一个新会话（建议有业务语义的 session 名）
- 必要时指定 `working_dir`

2. `send`
- 发送任务/继续指令给 Claude Code
- 默认提交（Enter）

3. `tail` / `status`
- 查看最近输出、判断是否完成/卡住/报错

4. `stop`
- 任务结束后关闭会话（避免长期占用）

## 调用建议

- 会话名简短清晰，例如：`repo_fix`, `docs_sync`, `release_check`
- 长任务先 `start` 再多次 `send`/`tail`，不要频繁重复启动新会话
- 若用户问“进度如何”，优先 `status`（必要时带输出预览）或 `tail`
- 若输出很多，优先让 Claude Code 聚焦更小范围再继续

## 失败处理

- `tmux_not_found`：提示安装 `tmux`
- `claude_command_not_found`：提示安装 Claude Code CLI 或检查 `tools.claudeCode.command`
- `session_not_found`：先 `list` 或重新 `start`
- `invalid_working_dir`：改用工作区内路径（如果启用了工作区限制）

## 示例（工具意图）

- 启动：`action=start, session=repo_fix, working_dir=/path/to/repo`
- 发送任务：`action=send, session=repo_fix, prompt=请检查测试失败并修复`
- 查看输出：`action=tail, session=repo_fix, lines=120`
- 结束：`action=stop, session=repo_fix`
