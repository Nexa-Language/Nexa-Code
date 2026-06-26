# VALUE_REPORT — Nexa 让 agent/harness 开发省了多少？（价值实证）

> 2026-06-25。Phase 9 最终交付。诚实度量，不夸大。所有行数实测 `wc -l`。
> 唯一翻译源 `refs/claude-code-ts/`。本移植是 **CC 核心子集**的忠实移植 + Textual 原生 UI。

## 1. 核心结论（一句话）

> **用 Nexa，2468 行 harness（.nx）+ 242 行 UI（Textual）= 一个日常可用的 near-CC coding agent；同等核心功能 CC 用了约 26905 行 TS——压缩约 9.9×。** Nexa 把「写一个能跑的、带工具/多轮/权限/hooks/子 agent 的 coding agent」从**数万行胶水框架**压缩到**两千多行声明式 .nx**。

## 2. 度量（实测 wc -l）

### 本项目（Nexa harness + 原生 UI）
| 部分 | 行数 | 内容 |
|---|---|---|
| Nexa harness | **2468** | `src/*.nx` + `src/tools/*.nx`（agent + 14 工具 + 20 命令 + harness 六元组 + 权限 + context + headless 引擎） |
| 原生 UI | **242** | `ui/app.py`（Textual TUI：banner+消息流+输入+工具 panel+权限 modal+主题+键位） |
| **总计** | **2710** | Nexa 负责引擎，Textual 负责 UI |

### CC 等价 TS 层（核心 agent 逻辑，实测对应文件）
| 层 | 行数 | 文件 |
|---|---|---|
| turn 循环/会话/API | 7002 | query.ts + QueryEngine.ts + services/api/claude.ts |
| 工具引擎/注册/接口 | 3055 | services/tools/toolExecution.ts + tools.ts + Tool.ts |
| context + system prompt | 2609 | context.ts + constants/prompts.ts + system.ts + utils/claudemd.ts |
| 权限核心 | 2045 | permissions/permissionSetup.ts + permissionsLoader.ts + shellRuleMatching.ts |
| 代表性工具×7 | 4793 | FileRead/Edit/Write/Bash/Grep/Glob/Notebook 主文件 |
| 代表性命令×13 | 721 | help/clear/compact/model/cost/status/context/config/vim/fast/rewind/resume/exit |
| **agent-logic 小计** | **20225** | （不含 UI） |
| REPL UI（Ink/React） | 6680 | screens/REPL.tsx |
| **CC 等价总计** | **26905** | logic + UI |

### 压缩比
| 层 | CC TS | 本项目 | 倍数 | 缩减 |
|---|---|---|---|---|
| agent-logic（harness） | 20225 | 2468 (Nexa) | **~8.2×** | 87.8% |
| UI | 6680 (Ink) | 242 (Textual) | **~27.6×** | 96.4% |
| 总计 | 26905 | 2710 | **~9.9×** | 89.9% |

> **诚实边界**：这是**核心子集移植**的对比，非逐功能 1:1。CC 的对应文件含本移植未复制的能力（流式降级/重试变体、microcompact 分区、bashSecurity/readOnlyValidation/pathValidation 的 5000+ 行细分规则、IDE/web hooks、Ink 全套 UI 组件等）。CC REPL.tsx(6680) 是功能完备的 Ink/React TUI；本项目 UI(242) 只覆盖核心交互。故压缩比反映**方向真实**（Nexa 确实大幅压缩 agent/harness 胶水），但**非功能等价的严格 1:1**。

## 3. 解放点（Nexa 让 agent 开发省了什么）

| CC（需手写） | Nexa（runtime/语言提供） | 省了多少 |
|---|---|---|
| turn 循环（query.ts 2057 + QueryEngine 1365 ≈ 3400 行 while-True + tool_use + 多轮 + 压缩） | `NexaAgent.run()` 内置 ReAct 循环 | **不手写循环**，核对语义对齐即可 |
| 工具派发 + schema（toolExecution.ts 1831 + 手写 JSON Schema） | `execute_tool` + `@tool fn` 自动生成 OpenAI schema | **声明即 schema**，无手写 JSON |
| 流式（query/claude 流式适配） | runtime streaming + P-RUN-1 补丁 | env 门控，零胶水 |
| agent 定义（CC 的 QueryEngine/tools 装配） | `agent X {prompt, model, uses}` 3 行声明 | 声明式 |
| 权限/HITL 钩子 | P-RUN-2 PreToolUse/PostToolUse 单一咽喉点 | 一个 register_tool_hook |
| harness 六元组（E/T/C/S/L/V） | 语言原语 autoloop/with_context/snapshot/verify/reflect | 原语级 |

→ **数千行 TS 胶水 → 数百行 .nx**。最显著：turn 循环（~3400 行 → 映射不写）+ 工具 schema（手写 → 自动生成）。

## 4. 边界（Nexa 不解放、用了原生 / 显式 out-of-scope）

- **UI**：Textual（242 行）——本就不是 harness（真 CC 也是 engine 与 Ink/React UI 分离）。用原生不叫蒙混。
- **平台层（out-of-scope，非 DSL 能表达）**：IDE bridge / web(claude.ai+RCS) / 完整 OAuth / computer-use(NAPI) / chrome / weixin / mobile / audio / image-processor / NAPI 模块 / Ink 全套 / ACP / voice。对应 CC `packages/@ant/*`、`*-napi`、`weixin`、`cloud-artifacts`、`remote-control-server`、`acp-link`（~79K 行）。

## 5. 开发效率

- **累计**：Phase 0-8 共 9 阶段，产出 2468 行 .nx + 242 行 UI = **2710 行**，覆盖 CC 核心 agent 子集（prompt/context/permission 4-mode/turn-loop/14 工具/20 命令/子 agent/plan/MCP/harness 六元组/headless 引擎/Textual TUI）。
- **对比**：从零写等价 TS agent 框架（turn 循环 + 工具派发 + schema + 流式 + 权限 + hooks + 多 agent）需 **数万行 + 显著更多时间**（仅 query.ts+QueryEngine+toolExecution+claude.ts 就 7002 行，且不含工具实现）。
- **轮次**：每 Phase 逐件「读 CC 源→翻译→build→GLM 验证→登记」，闭环可审计（PORT_TRACE 全登记）。

## 6. 给学长的 3 个 upstream 补丁（独立有价值）

| 补丁 | 文件 | 价值 | 可合并性 |
|---|---|---|---|
| **P-RUN-1**（带工具流式） | `agent.py:514` | CC 核心 UX（带工具 agent 流式）；env 门控 opt-in，零回归 | 高 |
| **P-RUN-2**（工具钩子 PreToolUse/PostToolUse） | `tools_registry.py:230` | 解锁权限/审计/HITL 的单一咽喉点；opt-in 默认 no-op | 高 |
| **P-CMP-4**（python! 双反斜杠转义 lint/codegen 告警） | compiler/lint | 消除本项目反复踩的 footgun（Q-RUN-1，复发 4 次）；DX 改进 | 高 |

三者均 opt-in、零默认行为变化，建议作为独立 PR。

## 7. Demo 证据（双 UI 驱动同一 Nexa 引擎，真实 GLM，非空口）

场景：**读 _demo.txt → Edit(old→new) → Bash(cat 验证)**。
- **Textual TUI**（`python ui/app.py` pilot）：tools called = `[Read, Edit, Bash]`（3 工具 panel 渲染），reply = "final content: count=10 label=new"，文件实际 `label=old→new`。
- **std.ui REPL**（`nexa run src/main.nx`）：Edit+Bash 工具调用 + reply "label=new"，文件实际改。
- → **两种 UI 驱动同一个 Nexa 引擎**，同场景都端到端跑通（引擎 100% Nexa，UI 可替换）。

## 8. 局限（诚实）

- **核心子集，非全量**：46 个 builtin-tools / ~124 命令未移植；权限的 5000+ 行细分规则、microcompact 分区、模型降级、AbortController 精细化、session 元数据等 partial。
- **工具参数只能标量**（Nexa @tool fn 无 array/object/可选默认；Q-CG-3）→ 复杂 schema 用 JSON 字符串传。
- **多模态受限**：图片/PDF 检测+读取忠实，但字符串工具无法注入多模态 image block。
- **GLM 后端**：用 glm-4-flash 验证（免费档，偶发 1213/限流，已加退避重试）；非 Anthropic 原版模型。
- **平台层全缺**：UI/IDE/web/NAPI/OAuth 非 DSL 职责（显式 out-of-scope）。

---

**一句话**：Nexa 不是万能——平台/UI 仍需原生——但在「agent 怎么想/怎么做」这一层，它把 Claude Code 级别的 coding agent 从**数万行胶水**压到**两千多行声明式代码**，证明了一门 **Harness Native Agent DSL** 的真实价值。
