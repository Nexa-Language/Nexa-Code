# ROADMAP_V2 — Nexa 版 Claude Code（日常可用 + harness 完整 + 证明 Nexa 价值）

> 2026-06-25 重新定位。本文是**后续所有开发的权威规划**，覆盖 Phase 6-10。若与本目录早期文档（PORT_PLAN.md 等）冲突，以本文为准。
> 进度：Phase 0-5 + 收尾加固已完成（2063 行核心 agent 子集，能跑）。本文规划的是**下一阶段：从「核心子集能跑」升级到「日常可用 + harness 生产级 + 原生 UI + 价值实证」**。

---

## 0. 最终目标（重新定位）

> 用 Nexa 构建一个**日常开发可用、接近 Claude Code 体验**的 coding agent；**harness 全 Nexa、完整（H=(E,T,C,S,L,V) 生产级）**；**UI 用原生**（Textual）。最终用「**少量 Nexa 代码 + 少量时间，做出 near-CC 的日常 agent**」证明 **Nexa 是有价值的语言**——能大幅降低 agent/harness 开发的繁琐度。

## 1. 混合架构原则（铁律，不可破）

| 层 | 用什么 | 理由 |
|---|---|---|
| **harness / agent 编排**（turn 循环、工具、工具派发、权限、上下文、钩子、状态、验证、子 agent、plan、MCP 客户端） | **必须 Nexa（.nx）** | 这是 Nexa 要证明能解放的部分；用原生冒充 = 失败 |
| **UI / 平台**（终端渲染、流式打字、diff、语法高亮、主题、keybindings、IDE、web、computer-use） | **允许原生** | 本就不是 harness（真 CC 也是 engine 与 Ink/React UI 分离）；用原生不叫蒙混 |

> 一句话：**Nexa 负责「agent 怎么想/怎么做」，原生负责「怎么显示/怎么交互」**。

## 2. 关键架构决策（已拍板）

1. **UI 选型 = Python Textual**（同 Python runtime，import 引擎零摩擦，rich 生态足够）。
2. **headless 引擎 + 原生 UI 外壳**：Nexa 这边只保留 headless agent 引擎（agent+工具+harness，暴露 run-one-turn + 流式回调 API）；Textual TUI 是前端，import 引擎、驱动、渲染。和真 CC 的 engine/UI 分离一致。
3. **「harness 完整」验收 = H=(E,T,C,S,L,V) 六元组生产级**：auto-compact 真自动、session 真 /resume、hooks 用户可配、verify 真校验、autoloop 真重试、file history 完整。

## 3. 阶段规划（Phase 6-10）

### Phase 6 — Harness 完整化（全 Nexa）+ headless 铺垫
把六元组补到生产级，源头是 `refs/claude-code-ts/src/`：
- **E 执行**：autoloop 真重试/abort/timeout（读 `query.ts` 重试降级 + AbortController 语义）+ GLM 1213/限流捕获退避重试。
- **C 上下文**：auto-compact 真·自动触发（接近 token 上限自动摘要，读 `query.ts`/`QueryEngine.ts` compaction 触发 + microcompact）。
- **S 状态**：session 跨重启真 /resume（读 CC session store/transcript 持久化）+ file history snapshots 完整（Edit staleness 已有 `_CCPORT_READ_STATE`，补全）。
- **L 生命周期**：用户可配置 hooks——4 事件(PreToolUse/PostToolUse/UserPromptSubmit/Stop)经 `settings.json` 驱动（读 CC hooks 配置格式），非仅内部。
- **V 验证**：verify 输出校验（读 CC verify/evaluation）。
- **headless 铺垫（末项）**：`main.nx` 的 `flow main` 拆成「headless 引擎（暴露 run-one-turn + 流式回调）」+「REPL 驱动」，为 Phase 8 Textual UI 铺路。
- 验收：六元组生产级 + headless API 可用；每项 build+GLM 实跑 + PORT_TRACE 登记。

### Phase 7 — 日常开发功能补齐（全 Nexa）
- 高频命令：/init /doctor /add-dir /memory /permissions /agents /mcp（读 `src/commands/<name>/` 忠实移植）。
- auto-compact 默认开；流式默认开（P-RUN-1）；错误/重试加固。
- 验收：开发者天天用的基础功能齐 + 长会话不崩。

### Phase 8 — 原生 UI 外壳（Textual，混合）
- 用 Python Textual 写 TUI 前端：import Phase 6 的 headless Nexa 引擎，驱动 agent、渲染流式打字/diff/语法高亮/主题/keybindings/工具调用展示/权限确认。
- 对齐 `REPL.tsx` 的交互（用 Textual 实现，非 Ink）。
- **边界严守**：UI 用原生 Textual；agent/harness 不改用原生（引擎仍是 Nexa 编译产物）。
- 验收：界面接近 CC 体验，不再「丑」；harness 仍 100% Nexa（可审计：UI 文件不含 agent 逻辑）。

### Phase 9 — 价值实证（证明 Nexa 有用）
- 度量：Nexa harness 行数 + Textual UI 行数 + 开发时间 → 对比 CC 同功能工作量。
- Demo：日常编码场景端到端。
- 报告：诚实结论「Nexa 让 agent/harness 开发省了多少代码/时间」，不夸大。

### Phase 10（可选）— 覆盖扩展
更多 builtin-tools / commands（视需要）。

## 4. 全程铁律（不变）
源码驱动（唯一源 claude-code-ts）/ CC 没有的不发明 / harness 必须 Nexa 不原生冒充 / 绝不搬 claude-code-nx 自创 / python! 单 `\n` / 复合布尔进 python! helper / else-if 嵌套 / flow 末尾 result / 每 agent 显式 uses / 每组件头注释标源 + 登记 PORT_TRACE / 平台层显式 out-of-scope。

## 5. 进度日志
- [x] Phase 0-5 + 收尾加固：核心 agent 子集（2063 行）完成，能跑。
- [x] **Phase 6：Harness 完整化（全 Nexa）+ headless 铺垫** — 2026-06-25。`harness.nx` 补 E/C/S/L/V 生产级（run_turn_safe GLM 退避重试 / auto_compact / session resume+file history / 用户可配 4 事件 hooks / verify）+ `main.nx` headless 拆分（run_one_turn 引擎 + REPL 驱动）。全 Nexa，build+GLM 实跑验证。详见 PORT_TRACE.md Phase 6。
- [x] **Phase 7：日常开发功能补齐（全 Nexa）** — 2026-06-25。必修 run_turn_safe 重试去重（回归通过）；7 命令 /init /doctor /add-dir /memory /permissions /agents /mcp；auto-compact 每轮默认开；流式默认开（stream:true + NEXA_STREAM_TOOLS=1）。build+GLM 实跑验证。详见 PORT_TRACE.md Phase 7。
- [x] **Phase 8：原生 UI 外壳（Textual，混合）** — 2026-06-25。`ui/app.py`（242 行纯 UI，无 agent 逻辑）import Nexa 引擎驱动渲染：Header+RichLog(markdown+工具 panel)+Input+Footer；/命令派发；权限 y/N modal；主题；Ctrl+C/↑↓/Esc 键位；worker 线程不冻 UI。边界核对 CLEAN；pilot stub + 权限 modal + **真实 GLM 端到端（读文件→Read→展示→回复）全通过**。详见 PORT_TRACE.md Phase 8。
- [x] **Phase 9：价值实证（最终交付）** — 2026-06-25。实测度量：Nexa harness 2468 + UI 242 = **2710 行** vs CC 等价层 ~26905 行 TS（**压缩 ~9.9×**，agent-logic 8.2×/UI 27.6×）。双 UI demo（Textual TUI + std.ui REPL）跑同一「读→编辑→bash」场景全通，证明两 UI 驱动同一 Nexa 引擎。`VALUE_REPORT.md` 给出诚实结论+解放点+边界+3 upstream 补丁价值。详见 VALUE_REPORT.md。
- **🎉 核心交付完成（Phase 0-9）**：一个日常可用、harness 全 Nexa、UI 原生 Textual 的 near-CC coding agent。Phase 10（扩覆盖）可选。
- [x] **Phase 10：换模型 glm-5.2（调通）+ 全功能修通 + 错误加固** — 2026-06-25。**glm-5.2 调通**（根因=端点：Coding 模型需专属 `coding/paas/v4` 端点，通用端点误报 1113）；secrets 切 coding 端点+glm-5.2，引擎调通 + 多工具(Read/Edit/Bash)+流式验证；/model 真运行时切换 /mcp 真连 /compact 真压 /resume 跨进程 /流式默认开 全修通；20 命令+14 工具全测 PASS；错误加固（余额/鉴权不重试、工具异常可读不崩）。详见 PORT_TRACE.md Phase 10。
- [x] **Phase 11：换 glm-5.1 + Ink/React UI 还原 CC** — 2026-06-25。glm-5.1 调通；引擎加 **JSON 事件模式**（Nexa I/O 层，stdin/stdout JSON 协议）；**ui-ink/ Ink/React UI**（CC 亲儿子技术栈，278 行 TS）：StatusBar+MessageLog(⏺工具)+PromptInput+权限 modal+流式+Claude 主题(Orange/Blue/暖暗底)，subprocess+JSON 管道驱动 Nexa 引擎。typecheck CLEAN + Ink 渲染 CC 风格帧 + TS↔JSON↔Python 桥端到端通；边界 CLEAN；Textual UI 保留 backup。详见 PORT_TRACE.md Phase 11。
- [x] **Phase 12：UI 深度还原 CC 动态交互 + 修 bug** — 2026-06-25。深入读 CC Ink 代码(✻/⏺/Spinner/Clawd/权限框)后精准还原：✻ logo+小螃蟹 mascot+spinner(dots,生命周期)+⏺ToolName→⎿result+权限 dialog(框+参数)+ctx%底栏+流式▋；修 Bash Windows GBK 编码崩/note 泄漏/WebFetch 可读/agent 自认 Claude Code(跳过全局 OMC CLAUDE.md)。typecheck+边界 CLEAN。详见 PORT_TRACE.md Phase 12。
- [ ] Phase 7-10：见上。
- [自主优化 轮次 1-3 ✅ 2026-07-08] 稳定性：run_turn_safe 180s 硬超时 + PostToolUse 重复检测(≥3次注入换思路反馈) + escape 审计。34/34 工具测试无退步。
