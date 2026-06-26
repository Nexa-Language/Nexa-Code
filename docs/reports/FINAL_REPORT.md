# FINAL_REPORT — 用 Nexa 忠实移植 Claude Code（核心子集）

> 2026-06-25 收尾。本移植是 **CC 核心逻辑子集**的忠实移植，**非**全量逐行翻写。诚实列已移植/未移植/out-of-scope。

## 1. 范围声明（诚实）

- **唯一翻译源**：`refs/claude-code-ts/`（泄露 TS 原版）。
- **移植目标**：CC 的**核心 agent 逻辑层**——system prompt / context 组装 / 权限模型核心 / turn 循环（映射 runtime）/ 工具 / 命令 / 子 agent / plan mode / MCP 客户端。
- **非全量**：CC 仓库 711,295 行 `.ts/.tsx` 中，大量是**平台/UI/校验/安全/IDE**——本移植**显式不复制**（映射到 Nexa runtime、简化、或标 out-of-scope）。

## 2. 行数对比（实测 `cat|wc -l`）

| 层 | claude-code-ts 行数 | 本 Nexa 移植 | 关系 |
|---|---|---|---|
| 全仓库 `.ts/.tsx` | **711,295** | — | 含 vendor/IDE/web/platform，水分大 |
| 平台层（@ant/* + *-napi + weixin + cloud-artifacts + remote-control-server + acp-link） | **79,228** | — | **out-of-scope**（平台原生，Phase 5 标注） |
| 核心层（src/ + builtin-tools + agent-tools + mcp-client） | **623,264** | — | 含 REPL UI/query/bashSecurity/readOnlyValidation 等大文件，本移植**只对标其中 load-bearing 子集** |
| └ builtin-tools（60 工具） | 65,377 | — | 本移植移植 **14 个**（7 核心 + 7 高级），余 46 标未移植/部分 |
| **本 Nexa 移植（src/*.nx + src/tools/*.nx）** | — | **2,062** | 49 个 `python!` 块承载移植逻辑 |

> 注：prompt 中「567,898 行」为早期口径；本报告数字为实测（含 `src/` 全部 + 各 package，可能含部分生成/重复文件）。**结论不依赖精确行数**：本移植是核心子集，非全量。

## 3. 已移植 / 未移植 / out-of-scope

### ✅ 已移植（忠实，build + GLM 实跑验证）
| 组件 | 忠实度 | Nexa 文件 |
|---|---|---|
| 真 system prompt（PREFIX + 6 静态段） | full | `agents.nx` |
| 真 context（git status/CLAUDE.md 层级/date/env） | partial | `context.nx` |
| 真权限模型（allow/deny/ask + 4 mode + 多源 + 规则匹配） | partial | `permissions.nx` |
| turn 循环 | mapping | `query_mapping.nx`（映射 NexaAgent.run） |
| REPL 骨架 | partial | `main.nx` |
| 工具：Read/Edit/Write/Bash/Grep/Glob/NotebookEdit | full/partial | `tools/*.nx` |
| 工具：TodoWrite/Agent/EnterPlanMode/ExitPlanMode/VerifyPlan/MCP×4/WebFetch/WebSearch | full/partial | `tools/*.nx` |
| 命令：help/clear/compact/model/cost/status/context/config/vim/fast/rewind/resume/exit | full/partial/stub | `commands.nx` |

### ⚠️ 未移植（核心层内，后续可补）
- 其余 46 个 builtin-tools（TaskCreate/Update/List/Get、Cron×3、Skill、LSP、Config tool、SearchExtraTools/ExecuteExtraTool、WebSearch 真后端 等）。
- 其余 ~131 个 commands（/doctor、/init、/mcp、/agents、/plugin、/issue、/share 等）。
- 权限完整版（acceptEdits mode、per-tool formatToolInput、bashSecurity/readOnlyValidation/pathValidation 的 5000+ 行规则、sandbox）。
- microcompact/autocompact 分区算法、AbortController/重试降级、microcompact 按 tool_use_id 清理。
- 子 agent fork/SendMessage 续跑/coordinator/memory、verification agent 编排。
- session 存储/transcript resume（/resume 真）、file history snapshots、hooks 完整 4 事件管线（已有 PreToolUse/PostToolUse 钩子接入）。

### ⛔ out-of-scope（平台层，Phase 5 标注，非 Nexa 能表达）
IDE bridge / web(claude.ai+RCS+cloud-artifacts) / 完整 OAuth / computer-use(NAPI) / chrome / weixin / mobile / audio(NAPI) / image-processor(NAPI) / color-diff·modifiers·url-handler(NAPI) / Ink UI 全套 / ACP / voice mode。对应 `packages/@ant/*`、`*-napi`、`weixin`、`cloud-artifacts`、`remote-control-server`、`acp-link`。

## 4. 结论：Nexa 是否「解放 agent 编写」？

**是，针对核心 agent 逻辑显著解放，但有明确边界。**

### 解放点（runtime 已提供，移植不需手写）
1. **turn 循环**（CC `query.ts` 2057 行的 while-True + tool_call + 多轮 + 压缩）→ NexaAgent.run() 一行。本移植**不手写循环**，核对语义对齐即可。
2. **工具派发**（CC `toolExecution.ts` 1831 行的权限→执行→格式化）→ `execute_tool` + P-RUN-2 钩子。
3. **流式 / 多轮记忆 / 上下文压缩** → runtime 内置。
4. **工具 schema 自动生成** → `@tool fn` 声明即生成 OpenAI function schema（无需手写 JSON Schema）。
5. **agent 声明式定义** → `agent X {prompt, model, uses}` 三行定义一个带工具的 ReAct agent。

→ 一个带真 system prompt + 14 工具 + 13 命令 + 子 agent + plan mode + MCP 的 coding agent，**约 2000 行 Nexa** 即可表达（vs CC 核心层数十万行，含大量校验/UI/平台胶水）。

### 边界（Nexa 不解放、本移植的诚实代价）
1. **平台层全失**：UI/IDE/web/NAPI/OAuth 非 DSL 能表达——CC 这部分（~79K 行平台 + src/ 内 UI/bridge）本移植显式跳过。
2. **工具参数只能标量**（Q-CG-3）：Nexa @tool fn 参数仅 string/number/boolean，无 array/object/可选默认（codegen 有 bug）。复杂 schema（TodoWrite 的 todos 数组）只能 JSON 字符串传，且 CC 可选参数在本移植标为 required。
3. **多模态受限**：图片/PDF 检测+读取忠实，但字符串工具无法注入多模态 image block（返回 base64+说明）。
4. **转义 footgun**（Q-RUN-1/CG-4/RUN-4/5）：`python!` 双反斜杠 / 描述内双引号 / NexaAgent.tools 期望 schema / 撇号转义——这些是 Nexa 此版本的坑，本移植逐个规避并记录（建议学长 P-CMP-4 补丁）。

### 一句话
> Nexa 把「写一个能跑的、带工具和多轮的 coding agent」从**数千行胶水框架**压缩到**数百行声明式 .nx**——但它解放的是 **agent 编排/工具/循环**这一层；CC 的**平台、UI、安全校验、企业特性**仍需原生栈，非 DSL 职责。本移植证明：**核心 agent 逻辑可忠实移植到 Nexa，约 2000 行覆盖 CC 的 prompt/context/permission/loop/tools/commands/agent/plan/mcp 核心**。

## 5. 验证证据（GLM-4-flash 端到端，非空口）
- 真 system prompt + git/CLAUDE.md 上下文启动 ✅
- Read/Edit/Write/Bash/Grep/Glob/NotebookEdit 工具链（cat-n/CRLF/staleness/截断/ripgrep/mtime）✅
- TodoWrite 创建列表、Agent 派生子 agent(explore) 调 Glob 报告 ✅
- EnterPlanMode/ExitPlanMode/VerifyPlan + plan 模式拦截 ✅
- MCP stdio JSON-RPC 端到端（echo server: initialize→initialized→tools/call/resources）✅
- WebFetch live 抓取+HTML 剥离 ✅
- 权限 4 模式（default/plan/bypass/auto）+ deny>allow>ask + 钩子幂等 ✅
- 13 命令经 flow 派发 ✅
- **零残留转义 bug**（终审：生成 .py 非 raw 双反斜杠 = 0）✅
