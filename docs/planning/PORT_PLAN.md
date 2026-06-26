# PORT_PLAN：用 Nexa 忠实移植 Claude Code（源码驱动）

> 目标：以 **claude-code-ts**（泄露的 TS 原版，567,898 行）为**唯一翻译源**，用 Nexa 忠重重写 Claude Code。
> **铁律（防「自由发挥」）**：移植目录下**每个** `.nx` 组件，必须在文件头注释里**标注它对应 claude-code-ts 的哪个源文件**（路径 + 关键行）。CC 没有的功能**不得新增**；行为必须以源码为准（先读源码再写）。无源码出处的代码 = 违规。

---

## 0. 为什么是「源码驱动」而非「自由发挥」

前一次尝试（`../claude-code-nx/`，1356 行）是**凭印象扩展学长骨架**，不是移植——行为与真 CC 差距巨大（自创 read_file ~30 行 vs 真版 FileReadTool.ts 1175 行）。该项目已**重新定位为「Nexa 进阶示例」**，与本次忠实移植**严格分离**（不同目录、不同文档、不同命名）。

本次必须：**每写一个组件，先打开对应 claude-code-ts 源文件读完，再翻译其真实行为。**

---

## 1. 关键架构认知：CC 架构 → Nexa 映射

CC 的核心循环/工具派发/流式，**Nexa runtime 已提供**（`NexaAgent.run()` 的 while-True 工具循环、`execute_tool`、streaming）。所以忠实移植 = **把 CC 架构映射到 Nexa runtime，并忠实补齐 Nexa 不给的部分**——不是逐行翻 query.ts 的 2057 行。

| CC 源文件（行数） | 职责 | Nexa 对应 | 移植策略 |
|---|---|---|---|
| `src/query.ts` (2057) | 主 turn 循环（发→流→tool_calls→执行→循环） | **`NexaAgent.run()` 已提供** | 映射：核对 NexaAgent 循环语义与 CC 一致（流式/tool_call/continue）。不重写循环。 |
| `src/QueryEngine.ts` (1365) | 会话状态/压缩/归档 | `NexaAgent.messages` + `_compact_context` | 映射会话状态与压缩。 |
| `src/services/api/claude.ts` (3580) | API 客户端（Anthropic SDK） | Nexa 用 OpenAI 兼容 SDK（任 provider） | 映射 provider 抽象；CC 用 Anthropic、Nexa 用 OpenAI-compat，行为对齐。 |
| `src/services/tools/toolExecution.ts` (1831) | 工具执行（权限→执行→格式化） | `execute_tool` + P-RUN-2 钩子 | 忠实复刻执行语义（权限检查→执行→结果格式）。 |
| `src/Tool.ts` (802) | 工具接口/契约 | Nexa `@tool fn` | 每个 CC 工具 → 一个 @tool fn，行为对齐源码。 |
| **`src/context.ts` (189)** | 系统/用户上下文组装 | `init` 阶段注入 system 消息 | **Phase 1 忠实移植**（见 §3）。 |
| `src/constants/system.ts` / `prompts.ts` | 真 system prompt | agent 的 prompt | **Phase 1 忠实移植**（真 CC 人格/指令）。 |
| `src/utils/permissions/` (~5000 非测试) | 真权限模型（allow/deny/ask 规则） | （前作的 in-tool `_perm_check` **不忠实**，弃用） | **Phase 1 忠实移植**核心规则匹配。 |
| `src/screens/REPL.tsx` (6680) | 交互 REPL（Ink UI） | `flow main` + `std.ui` | 映射 REPL 循环 + 渲染。 |
| `src/commands/*` (~144) | 斜杠命令 | 命令派发 | **Phase 3 逐个忠实移植**。 |
| `packages/builtin-tools/src/tools/*` (~60) | 真工具实现 | @tool fn | **Phase 2 逐个忠实移植**。 |

---

## 2. 阶段规划

### Phase 0 — 隔离与护栏（本次完成）
- 现 `claude-code-nx/` 重定位为「Nexa 进阶示例 + 能力验证」（改 README/文档，**去 CC 移植叙事**）。
- 新建 `claude-code-port/`（本目录）专做忠实移植，带护栏规则 + `PORT_TRACE.md`（组件→源文件映射）。
- 2 个 runtime 补丁（P-RUN-1/2）**暂不提 PR**（待定），但记录其存在（它们让 Nexa 具备了 CC 需要的钩子/流式能力）。

### Phase 1 — 核心框架（忠实，无真实工具，用 stub 验证骨架）
**目标**：一个跑在 Nexa 上的 agent，带**真 CC 的 system prompt + 真上下文组装 + 真权限模型 + REPL**，但工具先用 stub。这是「骨架」，对应 CC 的 query/QueryEngine/context/permissions/REPL 这一层。

- **1a 真 system prompt**：读 `src/constants/system.ts`、`prompts.ts`、`systemPromptSections.ts`，把真 CC 的系统提示（人格、工具使用规范、安全规则…）忠实搬进 agent 的 prompt。
- **1b 真上下文组装**（移植 `src/context.ts`）：`getGitStatus`（branch / main branch / `git status --short` 截断 1000 字符 / 最近 5 条 commit / user.name）+ `getUserContext`（CLAUDE.md 层级 via `claudemd.ts` + 当前日期）。**逐字段对齐 context.ts**。
- **1c 真权限模型核心**：读 `permissions/permissionSetup.ts`、`permissionsLoader.ts`、规则匹配，移植「settings 规则 → allow/deny/ask」的核心（非全部 5000 行，先核心 rule matching）。
- **1d turn 循环映射**：核对 `NexaAgent.run()` 的循环语义对齐 `query.ts`（流式、tool_call、多轮、压缩）。补差异。
- **1e REPL 骨架**：`flow main` + `std.ui`，输入→agent→渲染，对齐 REPL.tsx 的交互（先核心，UI 细节后补）。
- **验收**：agent 用真 system prompt + 真 git/CLAUDE.md 上下文启动；权限模型对 stub 工具生效；多轮流式工作。每个组件头注释标注源文件。

### Phase 2 — 核心工具（忠实，逐个）
按 CC 工具逐个移植，**每个先读真 TS 源再写**：
- 顺序建议：FileReadTool (1175) → FileEditTool → FileWriteTool → BashTool → GrepTool → GlobTool → NotebookEditTool。
- 每个 @tool fn 头注释标注：`# Ported from packages/builtin-tools/src/tools/<X>/<X>.ts`。
- 行为对齐源码（FileReadTool 的 offset/limit/图片/PDF/二进制/行号/编码… 都要照源码实现，不再简化）。

### Phase 3 — 命令（忠实，逐个）
- 读 `src/commands/<cmd>/`，逐个移植真行为（/help /clear /compact /model /cost /resume …），头注释标注源目录。

### Phase 4 — 高级（Task/Agent、MCP、Plan、TodoWrite 等）
- 对应 CC 的 AgentTool/MCPTool/EnterPlanModeTool/TodoWriteTool 等，逐个忠实移植。

### Phase 5 — 平台层（明确超范围或后置）
- IDE bridge / web / 完整 OAuth / computer-use / weixin/chrome：这些是**原生模块/扩展**，非 Nexa 能表达，**本移植显式跳过**，在 `PORT_TRACE.md` 标注「out-of-scope (platform-native)」。

---

## 3. Phase 1 首件：`context.ts` 忠实移植要点（已读源码）

`src/context.ts`（189 行）产出两部分，注入 system 消息：
- **`getSystemContext`** → `{ gitStatus }`：
  - `getGitStatus()`：并发取 `branch`、`getDefaultBranch()`、`git status --short`（>1000 字符截断 + 提示）、`git log --oneline -n 5`、`git config user.name`；拼成「This is the git status at the start of the conversation... / Current branch / Main branch / Git user / Status / Recent commits」。非 git 仓库返回 null。
- **`getUserContext`** → `{ claudeMd, currentDate }`：
  - `claudeMd`：`getClaudeMds(filterInjectedMemoryFiles(getMemoryFiles()))`（CLAUDE.md 层级发现，见 `claudemd.ts` 1476 行——Phase 1 移植其核心：cwd+父目录+`--add-dir` 发现 + 注入式 memory 文件）。
  - `currentDate`：`Today's date is <ISO>.`。
- 忠实要点：**字段、截断阈值（1000）、文案、缓存语义（per-conversation memoize）**都要对齐。

---

## 4. 移植进度追踪：`PORT_TRACE.md`

每个移植组件登记一行：`<nexa 文件:符号>` ← `<claude-code-ts 源文件:行范围>` + 忠实度（full/partial/stub）+ 备注。**无登记 = 不算移植**。这是「防自由发挥」的可审计抓手。

---

## 5. 估算（诚实，随进度更新）

- Phase 1（核心框架）：Nexa 约 **300–600 行**（大量靠 runtime 映射，真正要写的是 context/prompt/permission/REPL）。
- Phase 2（核心 7 工具，忠实）：Nexa 约 **800–2000 行**（真行为多，如 FileReadTool 的图片/PDF）。
- Phase 3（命令）：视移植数量，每命令 ~10–50 行。
- 全量到「核心+工具+高频命令」实用级：**~2k–5k 行 Nexa**；到「全功能含平台层」无上限（且平台层非 Nexa 能表达）。
- 对照：官方 567,898 行 TS（含 vendor/IDE/web，水分大）；本移植只对标**核心逻辑层**。
