# claude-code-port — 用 Nexa 忠实移植 Claude Code

> 本目录是 **Claude Code 的 Nexa 忠实移植**（源码驱动）。
> 唯一翻译源：`../refs/claude-code-ts/`（泄露 TS 原版）。详细规划见 `PORT_PLAN.md`。

## ⛔ 铁律（防止重蹈「自由发挥」覆辙）

本目录下**每一个** `.nx` 组件必须遵守：

1. **必须标注源文件**：文件头注释写明 `# Ported from <claude-code-ts 相对路径>[:行范围]`。无源文件出处的代码**违规**。
2. **先读源再写**：写任何组件前，先打开对应 claude-code-ts 源文件读完，理解真实行为，再翻译。
3. **不得新增 CC 没有的功能**：CC 源里没有的，不发明。发现 Nexa 表达不了的真 CC 功能 → 登记到 `PORT_TRACE.md` 标 `out-of-scope`，**不要**用自创近似冒充。
4. **行为对齐源码**：字段、阈值、文案、边界都要对齐源码（例：git status 截断 1000 字符、FileRead 的 offset/limit/图片/PDF）。
5. **登记 PORT_TRACE.md**：每完成一个组件，在 `PORT_TRACE.md` 加一行映射。**无登记 = 不算移植**。

## 与 `claude-code-nx/` 的关系（必须区分）

- `../claude-code-nx/`：**前一次「自由发挥」的产物**，已重定位为「Nexa 进阶示例 + 能力验证」，**不是** Claude Code 移植。可借鉴 Nexa 写法，但其工具/命令行为**不作为本移植的依据**——依据只有 claude-code-ts 源码。
- 本目录 `claude-code-port/`：**唯一的忠实移植**。不混用、不继承 claude-code-nx 的「自创」实现。

## 2 个 runtime 补丁（暂不提 PR）

移植会用到学长 Nexa runtime 的 2 个 opt-in 补丁（在 `../nexa-lang/src/runtime/`，登记在 `../claude-code-nx/NEXA_PATCHES.md`）：
- P-RUN-2：`execute_tool` 的 PreToolUse/PostToolUse 钩子（CC 的 toolHooks 对应）。
- P-RUN-1：带工具的流式输出（CC 的 streaming tool exec 对应）。
两者 opt-in、零回归。是否提 PR 给学长**待定**（用户暂缓）。

## 当前进度
- [x] Phase 0：隔离 + 护栏（本 README + PORT_PLAN.md + PORT_TRACE.md）+ 重定位 claude-code-nx
- [x] **Phase 1：核心框架（真 system prompt + 真 context + 真权限模型 + REPL 骨架）** — 2026-06-24，build + GLM 实跑端到端验证通过（详见 PORT_TRACE.md）
- [x] **Phase 2：核心工具（Read/Edit/Write/Bash/Grep/Glob/NotebookEdit，逐个忠实）** — 2026-06-25，7 工具全部移植、stub 移除、build + GLM 实跑验证通过（详见 PORT_TRACE.md）
- [x] **Phase 3：斜杠命令（13 高频命令忠实移植）** — 2026-06-25，含 Q-RUN-1 转义必修修复 + Edit CRLF 回归；build + GLM 实跑验证通过（详见 PORT_TRACE.md）
- [x] **Phase 4：高级工具（TodoWrite/Agent/Plan×3/MCP×4/Web×2 忠实移植）** — 2026-06-25，含 Q-RUN-1 复发修复（web/mcp 转义）；build + GLM 实跑验证通过（详见 PORT_TRACE.md）
- [x] **Phase 5：收尾（必修修复 + out-of-scope 标注 + 权限 4 模式 + 最终统计 + FINAL_REPORT + P-CMP-4 建议）** — 2026-06-25；核心移植收尾（详见 FINAL_REPORT.md）

**核心移植完成。** 2062 行 Nexa 忠实覆盖 CC 的 prompt/context/permission/loop/tools/commands/agent/plan/mcp 核心子集；平台层显式 out-of-scope。结论见 [FINAL_REPORT.md](FINAL_REPORT.md)。
- [ ] Phase 3：命令（逐个忠实）
- [ ] Phase 4：高级（Task/MCP/Plan/TodoWrite）
- [ ] Phase 5：平台层（显式超范围）

## 运行方式（Phase 11：Ink/React UI —— CC 亲儿子技术栈，推荐）
```bash
cd claude-code-port/ui-ink
bun install                 # ink + react + ink-text-input
bun start                   # = bun run src/index.tsx（需真终端，raw mode 输入）
```
- 视觉还原 CC：橙边 StatusBar(Model|cwd|●working/○idle) + MessageLog(用户 dim + assistant● + ⏺工具 call/result ⎿) + 底部 PromptInput + 权限 y/N modal + 流式逐字；主题 Claude Orange #D77757 / Blue #5769F7 / 暖暗底。
- 架构：UI(Ink/React) ↔ JSON 事件管道 ↔ Nexa 引擎(subprocess `python src/main.py`，NEXA_JSON_EVENTS=1)。**ui-ink/ 无 agent 逻辑**（边界 CLEAN）。

## 运行方式（Phase 8：Textual TUI —— backup 方案 A）
```bash
cd claude-code-port
pip install textual rich          # UI 依赖（harness 仍是 Nexa，不原生冒充）
nexa build src/main.nx --harness=warn
python ui/app.py                  # 或 textual run ui/app.py
```
- TUI：Header(banner) + 消息流(rich markdown 回复 + 工具调用 panel) + 输入框 + 状态栏。
- 输入 prompt → 引擎 run_one_turn；`/` 开头 → run_command（含 /init 路由 agent）；权限 ask 弹 y/N modal。
- 键位：Ctrl+C 退出 · ↑↓ 历史 · Esc 取消 · t 切深/浅主题。
- **架构边界**：`ui/` 只渲染+调引擎 API，**无 agent 逻辑**（grep 可验：无 turn 循环/execute_tool/permission _decide/LLM 调用）。引擎是 Nexa 编译产物（src/main.py）。
- 旧 std.ui REPL 仍可用：`printf 'prompt\n/exit\n' | nexa run src/main.nx`。

## 运行方式（Phase 1 std.ui REPL）
```bash
cd claude-code-port
nexa build src/main.nx --harness=warn      # 编译（T-004/X-002 为 validator 误报，忽略）
nexa run src/main.nx                        # 交互 REPL（需 secrets.nxs 的 GLM key）
# 或非交互：printf 'your prompt\n/exit\n' | nexa run src/main.nx
```
- 流式（对齐 query.ts streamingToolExecution）：agent 默认 `stream: true`；带工具流式需 `NEXA_STREAM_TOOLS=1 nexa run src/main.nx`（启用 P-RUN-1 补丁；否则带工具时降级非流式）。
- auto-compact：每轮自动检查（run_one_turn → auto_compact_if_needed，默认阈值 ~24K token 触发摘要）。
- E 重试：run_turn_safe 对 GLM 1213/429/overloaded/timeout/connection 指数退避重试（重试前去重 user 消息）。
- 权限规则：写 `.claude/settings.local.json` 的 `permissions.{allow,deny,ask}`（无文件时用演示默认：allow=stub_read_file / deny=stub_bash(rm:*) / ask=stub_write_file,stub_bash）。
