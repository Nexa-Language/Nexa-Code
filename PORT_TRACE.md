# PORT_TRACE — 移植组件 → claude-code-ts 源文件 映射

> **审计抓手**：本移植目录下每个组件都必须在此登记一行。无登记 = 不算移植 = 违规（见 README 铁律）。
> 忠实度：`full`（行为完全对齐）/ `partial`（核心对齐、部分省略，注明）/ `stub`（占位，待补）/ `out-of-scope`（平台层/原生，显式跳过）。

## Phase 1 — 核心框架  ✅ 完成（build + GLM 实跑验证通过，2026-06-24）

| Nexa 组件 | claude-code-ts 源 | 忠实度 | 备注 |
|---|---|---|---|
| `src/agents.nx` : `agent Coder`（system prompt） | `src/constants/system.ts:10`（PREFIX）+ `prompts.ts:178-402`（intro/system/doing-tasks/actions/tools/communication 6 静态段）+ `cyberRiskInstruction.ts:24` + `prompts.ts:126`（hooks 段） | **full** | 1a。PREFIX + 6 段逐字移植；工具名常量(Read/Edit/Write/Bash/...)代入；MACRO.ISSUES_EXPLAINER='' |
| `src/context.nx` : `get_git_status`/`get_claude_md`/`get_current_date`/`get_env_info`/`build_user_context` | `src/context.ts:36-188`（getGitStatus/getSystemContext/getUserContext）+ `src/utils/claudemd.ts`（getClaudeMds 层级核心）+ `src/constants/prompts.ts:604-711`（computeSimpleEnvInfo/getShellInfoLine/getUnameSR）+ `common.ts`（getLocalISODate） | **partial** | 1b。git/日期逐字段对齐（含截断 1000+"2k characters"文案）；CLAUDE.md 层级移植 user+project(cwd 向上)，managed(/etc)+.claude/rules/*.md 暂缓；Anthropic 产品行(env 营销)省略注明。GLM 实跑：CLAUDE.md(5186 字符)+date 正确注入 |
| `src/permissions.nx` : `init_permissions`（PreToolUse 钩子） | `src/utils/permissions/permissionsLoader.ts:46-145`（规则加载）+ `shellRuleMatching.ts:43-184`（exact/prefix`:*`/wildcard`*`）+ `permissionSetup.ts`（deny>allow>ask 决策） | **partial** | 1c。核心匹配引擎+决策序+Bash 通配/前缀移植；经 P-RUN-2 钩子(execute_tool:250 wrapper)接入。GLM 实测：deny(stub_bash rm:*)/allow(stub_read_file)/ask(stub_write_file) 三路径全验证。未含：多 settings 源合并、permission mode(default/plan/bypass/auto)、per-tool formatToolInput |
| `src/query_mapping.nx`（映射文档） | `src/query.ts:460,495,752,248,759,558-728` + `QueryEngine.ts` | **mapping** | 1d。CC turn 循环语义映射到 NexaAgent.run(agent.py:487)，逐项核对(见文件头映射表)。**不手写循环**。差异：流式需 P-RUN-1(NEXA_STREAM_TOOLS)，abort/microcompact 后续 |
| `src/main.nx` : `flow main`（REPL 循环） | `src/screens/REPL.tsx:3967-4036`（onSubmit：/命令派发 | user→query→render）+ `638`(onExit) + `commands/exit` | **partial** | 1e。移植核心交互 loop：input→(/help /exit /quit | agent run)→std.ui render→exit。Ink 全套 UI(Messages/流式 spinner/权限确认 JSX)为平台层，Phase 1 只对齐交互 LOOP。GLM 实跑：read→tool call→reply→render→/exit 干净退出(exit 0) |
| `src/stub_tools.nx`（占位） | —（真工具 Phase 2） | **stub** | Phase 1 骨架验证用占位工具 stub_read_file/write_file/bash；真 FileReadTool(1175)等 Phase 2 先读源再移植 |



## Phase 2 — 核心工具（逐个，先读真源再写）  ✅ 完成（build + GLM 实跑验证通过，2026-06-25）

| Nexa 工具 | claude-code-ts 源 | 忠实度 | 备注 |
|---|---|---|---|
| `src/tools/read.nx` : `Read` | `FileReadTool/prompt.ts:5,10-49` + `limits.ts:18,65` + `FileReadTool.ts:226-242,459-492,494-649,796-1078` + `file.ts:290-319`(addLineNumbers) + `files.ts:5-112`(BINARY) | **full**(text)+partial | text: offset/limit/cat-n(→)/256KB 门/25000token 门/空短提示/binary 拒/device 拒/ENOENT。image(png/jpg/jpeg/gif/webp)+pdf: 检测+读取忠实，**多模态视觉注入受 Nexa 字符串工具限制返回 base64+说明**。GLM 实跑：读 agents.nx 正确 |
| `src/tools/edit.nx` : `Edit` | `FileEditTool/constants.ts:2,10-11` + `prompt.ts:4-28` + `types.ts:6-19` + `FileEditTool.ts:134-345,371-465` | **full** | exact 替换 / replace_all / old_string 唯一性 / 必须 Read(staleness "unexpectedly modified") / 空 old_string 建新文件 / 同串拒绝 / 行尾归一化匹配。readFileState 经 globals() 共享。单测：唯一替换/not-found 正确 |
| `src/tools/write.nx` : `Write` | `FileWriteTool/prompt.ts:3-17` + `FileWriteTool.ts:53-61,150-211,213-260` | **full** | 新建直接写 / 现有文件必须 Read+未改动 / 父目录 mkdir / 覆盖写。单测：新建文件正确 |
| `src/tools/bash.nx` : `Bash` | `BashTool/prompt.ts:31-33,333` + `BashTool.tsx:298-322,397-419` + `timeouts.ts:2-3`(120000/600000) + `outputLimits.ts:3-4`(30000) + `utils.ts:133-163`(formatOutput) | **partial** | command 执行 / timeout(默认120s,clamp≤600s) / stdout+stderr / 输出截断(30000+"... [N lines truncated] ...") / exit code。run_in_background=true：partial(同步执行+注明，异步后台任务子系统未移植)。shell:bash 走 PATH。GLM 实跑：echo→phase2_done 正确 |
| `src/tools/grep.nx` : `Grep` | `GrepTool/prompt.ts:4-17` + `GrepTool.ts:30-87,101-138,307-396` + `ripgrep.js` | **full** | pattern/path/glob/output_mode(content/files_with_matches/count)/-A/-B/-C/-n/-i/--type/head_limit(默认250)/offset/multiline；优先调系统 rg，不可用降级 Python re；VCS 排除。单测：content 模式匹配正确 |
| `src/tools/glob.nx` : `Glob` | `GlobTool/prompt.ts:1-7` + `GlobTool.ts:23-32,41-47,151-185` + `glob.js` | **full** | glob 模式(** 递归) / 按 mtime 倒序 / limit 100 截断 / 路径相对 cwd / "No files found"。单测：*.nx 匹配正确 |
| `src/tools/notebook.nx` : `NotebookEdit` | `NotebookEditTool/constants.ts:2` + `prompt.ts:1-3` + `NotebookEditTool.ts:30-57,297-372,374-436` | **full** | replace/insert(after)/delete / cell_id 定位(id/数字索引/默认0) / replace 清 execution_count+outputs / cell_type 切换 / 越界 replace→insert / 写回 indent 1。单测：cell replace 正确 |
| _(已移除)_ `stub_tools.nx` | — | — | Phase 1 占位工具已删除；agent `uses` 改绑 7 个真工具 |

**Phase 2 并行修复（review 反馈）**：
- ① 工具名对齐 system prompt：agent `uses Read, Edit, Write, Bash, Glob, Grep, NotebookEdit`（移除 stub_xxx）。✅
- ② permissions.nx 钩子幂等：改查 `TOOL_HOOKS['PreToolUse']` 是否已含 `__name__=='_pre_tool_use'` 的 cb（不依赖闭包同一性、不用自定义函数属性）。✅ 实测 re-init 报 "already installed"。
- ③ permission modes：补 **default**（Read/Glob/Grep 默认 allow；Edit/Write/Bash/NotebookEdit deny>allow>ask）+ **plan**（只读 Read/Glob/Grep allow；改动类拒）。`set_permission_mode`/`NEXA_PERMISSION_MODE` env。✅ 实测 plan 模式 Bash 被拒。
- 真工具经 P-RUN-2 PreToolUse 钩子接入真权限规则（规则名用真工具名）。✅ 实测 deny(Bash rm:*)/allow(Read/Bash echo)/ask(Write)。

| _(已并入上表 NotebookEdit)_ notebook_edit | `packages/builtin-tools/src/tools/NotebookEditTool/` | full | 见 `src/tools/notebook.nx` |

## Phase 3 — 命令（逐个）  ✅ 完成 + 深化（2026-07-09）
### 命令深化记录（partial → full）
| 命令 | CC 源 | 深化前 | 深化后 |
|---|---|---|---|
| /compact | compact.ts:411-660 + prompt.ts:293-340 | 一句话摘要 | **full**: CC 9-section prompt + formatCompactSummary(strip analysis) + 保留近4条 + getCompactUserSummaryMessage framing |
| /permissions | permissions/permissions.tsx + permissionSetup.ts | display-only | **full**: add/remove/list 子命令 |
| /config | commands/config/ + settings.ts:309,416,812 | cat settings.json | **full**: get/set/list + 多源合并 + 持久化 |
| /resume | commands/resume/resume.tsx | stub | **partial**: session list + load by path（交互 picker 是 UI 层） |
| /hooks | commands/hooks/hooks.tsx | display-only | **full**: add/remove/test/list + 多源合并 + 持久化 |
| /model | commands/model/model.tsx | 显示字符串 | **full**: 运行时切换 + 持久化 secrets.nxs + 列可用模型 |
| /rewind | commands/rewind/rewind.ts | 数值回退 | **full**: list/search/numeric rewind |
| Bash | BashTool.tsx:440-470 | subprocess+危险检测 | **full**: + sleep detection (对齐 detectBlockedSleepPattern) |
| /clear | clear/conversation.ts:70-281 | reset messages | **full**: SessionEnd hook + resetCostState + fileHistory.clear + readFileState.clear + regenerateSessionId + SessionStart hook（clearConversation 完整状态清理） |
| /cost | cost/cost.ts + cost-tracker.ts:229 formatTotalCost | 消息数 | **full**: 真实 API usage(_CCPORT_USAGE/_CCPORT_COST_STATE,main.nx monkey-patch 累积) + 每模型 input/output 分项 + context window% + 模型名（对齐 formatTotalCost/formatModelUsage） |
| /status | status/status.tsx(Settings>Status) | cwd/model/git | **full**: + mode + tool count + session elapsed + auto-compact%（Status 面板字段对齐；UI 是平台层，文本适配） |
| /export | export/export.tsx | markdown 导出 | **full**: plain text .txt（renderMessagesToPlainText 非 markdown）+ extractFirstPrompt/sanitizeFilename/formatTimestamp 智能文件名 + args 直写 |
| /copy | copy/copy.tsx | Windows clip | **full**: collectRecentAssistantTexts(跳 tool-use-only) + /copy N 回溯 + clipboard best-effort + temp 文件双写 fallback |
| /review | review.ts (LOCAL_REVIEW_PROMPT, type=prompt) | git diff dump | **full**: 忠实移植为 prompt 命令（__AS_PROMPT__ → agent 跑 gh pr list/view/diff + 结构化 review：correctness/conventions/perf/test/security） |
| /pr | commit-push-pr.ts (type=prompt, Git Safety Protocol) | git push+gh subprocess | **full**: 忠实移植为 prompt 命令（agent 执行 branch→commit→push→gh pr create/edit + Git Safety Protocol + 短 title 规则） |
| /undo | (CC 无 /undo 命令) fileHistory.ts analogue | 单快照恢复 | **full**: + /undo list 列 tracked files + 快照数；LIFO 恢复（fileHistory checkpoint 恢复语义） |
| /git | (CC 无 /git 命令，CC 用原生 git via Bash) | 子命令拼 CLI | **partial(自创)**: 扩充子命令(add/restore/checkout/fetch/rebase) + unknown 处理；诚实标注非 CC 源 |
| /env | env/index.ts | Python/Platform/Model/Git | **full**: ## Runtime(platform/cwd/pid/python/session/model) + ## Environment Variables(允许前缀 CLAUDE_/FEATURE_/ANTHROPIC_/NEXA_/...) + secret 脱敏(token/password/api_key/auth→XXXX…XX (N chars)) |
| /version | version.ts | VERSION+工具数 | **full**: `v{VERSION}` + "version this session is running" + runtime 工具数（对齐 CC version.ts） |
| /history | history.ts | role+content | **full**: formatEntryType([PROMPT]/[AI]/[TOOL>]) + 截断 200 + --last N（CC 是 pipe 子会话；Nexa 适配主会话） |
| /session | session.tsx | 基础信息 | **full**: id/start/elapsed/messages/model/mode/cwd + CC remote QR 标注（CC 是 remote 专用，Nexa 适配本地） |
| /usage | usage.tsx(Settings→Usage) | est tokens | **full**: unified /cost+/stats — real API tokens(_CCPORT_USAGE) + 每模型分项(_CCPORT_COST_STATE) + context chars + window%；/stats 别名→/usage |

| Nexa 命令 | claude-code-ts 源 | 忠实度 | 备注 |
|---|---|---|---|
| `src/commands.nx` : `run_command` 派发器 + 13 handler | `src/commands/*/index.ts` + 实现 | — | 经 main.nx flow 派发（对齐 REPL.tsx:3967-4036 onSubmit 命令分支） |
| `/help` | `commands/help/index.ts` + `help.tsx`(HelpV2) | **full** | 列出可用命令+描述 |
| `/clear` | `commands/clear/clear.ts` + `conversation.ts:130,160` | **full** | reset messages→[system] + 清 readFileState（对齐 clearConversation 核心） |
| `/compact [instructions]` | `commands/compact/compact.ts`(compactConversation) | **partial** | 调模型摘要旧消息→替换为 summary（核心对齐；CC 的 microcompact/分区算法/sessionMemory 未含） |
| `/model` | `commands/model/model.tsx` | **partial** | 显示当前模型；切换经 secrets.nxs（CC 是交互菜单 UI） |
| `/cost` | `commands/cost→usage` | **partial** | 显示会话消息数；详细 token/成本核算（analytics 子系统）未移植 |
| `/status` | `commands/status/status.tsx`(Settings>Status) | **full** | cwd/model/git branch/messages |
| `/context` | `commands/context` | **full** | 复用 context.nx build_user_context 显示 env/git/CLAUDE.md/date |
| `/config` | `commands/config/config.tsx` | **full** | 显示 .claude/settings.*.json 内容 |
| `/vim` | `commands/vim/vim.ts` | **full** | 切换 editorMode normal↔vim（存 _CCPORT_GLOBAL_CONFIG） |
| `/fast` | `commands/fast/fast.tsx` | **partial** | 切换 fastMode 标志；Opus 专属，GLM 下无模型效果（注明） |
| `/rewind <n>` | `commands/rewind/rewind.ts` | **partial** | 数值回退丢弃末尾 n 轮（CC 是消息 picker UI） |
| `/resume` | `commands/resume` | **stub** | 返回说明：会话存储+transcript resume 是平台子系统，Phase 3 未移植 |
| `/exit` | `commands/exit/exit.tsx`(gracefulShutdown) | **full** | 返回 `__CC_EXIT__` 哨兵，flow 据此退出 |

**GLM 端到端验证**：REPL 中 agent 回复 + `/status` + `/help` + `/exit` 交替正确（命令经 flow 的 run_command 派发，与 agent turn 并存）。

## Phase 4 — 高级  ✅ 完成（build + GLM 实跑验证通过，2026-06-25）

| Nexa 工具 | claude-code-ts 源 | 忠实度 | 备注 |
|---|---|---|---|
| `src/tools/todo.nx` : `TodoWrite` | `TodoWriteTool/prompt.ts:144-180` + `TodoWriteTool.ts:13-17,58-61,65-114` | **full** | todos(JSON) 解析 / 状态 pending/in_progress/completed / 至多一 in_progress / 全完成清空 / 结果文案逐字 / 无权限检查(always allow)。GLM 实跑：agent 调 TodoWrite 创建 2 项列表 |
| `src/tools/agent.nx` : `Agent`(legacy Task) | `AgentTool/constants.ts:1-2` + `builtInAgents.ts` + `built-in/*` + `AgentTool.tsx/runAgent.ts` + `prompts.ts:713`(DEFAULT_AGENT_PROMPT) | **partial→full(核心)** | subagent_type/prompt/description → 创建隔离上下文子 NexaAgent(fresh messages)→ .run(prompt)（turn 循环映射 NexaAgent.run，**不手写循环**）→ 返回报告。工具集：general-purpose=全工具；Explore=只读。GLM 实跑：sub-explore 调 Glob 列出 12 文件并报告。fork/SendMessage续跑/coordinator/memory 未含(partial) |
| `src/tools/plan.nx` : `EnterPlanMode`/`ExitPlanMode`/`VerifyPlan` | `EnterPlanModeTool/prompt.ts:4-50`+`EnterPlanModeTool.ts:77-124` / `ExitPlanModeTool/prompt.ts:6-23`+`ExitPlanModeV2Tool.ts` / `VerifyPlanExecutionTool.ts:7-92` | **full** | EnterPlanMode(0参)→转 plan 权限模式+只读探索指令；ExitPlanMode(0参)→退回 default+请求批准；VerifyPlan→verified/failed 文案。对齐 Phase 1 permission plan mode |
| `src/tools/mcp.nx` : `MCPTool`/`ListMcpResources`/`ReadMcpResource`/`McpAuth` + `_mcp_call`/`_mcp_load_config` helper | `MCPTool/MCPTool.ts` / `ListMcpResourcesTool/*` / `ReadMcpResourceTool/prompt.ts+ts:22-27` / `McpAuthTool/McpAuthTool.ts:38-85` | **partial→full(协议)** | stdio JSON-RPC 2.0 客户端(initialize→initialized→method)；MCPTool→tools/call；List→resources/list；Read→resources/read；McpAuth→OAuth 说明。配置读 .mcp.json mcpServers。无配置时优雅返回。真 MCP 调用需配置 server |
| `src/tools/web.nx` : `WebFetch`/`WebSearch` | `WebFetchTool/prompt.ts:1-46`+`WebFetchTool.ts:26-32` / `WebSearchTool/prompt.ts+ts:15-45` | **partial** | WebFetch: urllib 抓取+HTTP→HTTPS+HTML剥离(script/style+标签)+截断（full 抓取核心；二级模型 prompt 处理由主 agent 代行）；WebSearch: stub——需搜索 API 后端(Anthropic/Brave)本运行时无 |

**接线**：新工具加入 agent Coder `uses`（TodoWrite/Agent/EnterPlanMode/ExitPlanMode/VerifyPlan/WebFetch/WebSearch）；经 P-RUN-2 PreToolUse 钩子接权限——TodoWrite/Enter/Exit/Verify/WebSearch 只读默认 allow，Agent/WebFetch/MCP* 走 ask（规则名用真工具名）。
**GLM 端到端验证**：TodoWrite 创建列表；Agent 派生子 agent(explore)调 Glob 报告；EnterPlanMode 转 plan 模式（ListMcpResources 随后被 plan 模式正确拦截）。

## Phase 5 — 显式超范围（平台层 / 原生模块）  ✅ 标注完成（2026-06-25）

> 这些是**平台原生模块/独立应用**，非 Nexa（一门编译到 Python 的 DSL）能表达——需要原生 OS API、GUI 框架、浏览器、移动运行时或独立 web 栈。本移植**显式跳过**，不假装。每条注明 claude-code-ts 对应位置。

| 组件 | claude-code-ts 位置 | out-of-scope 原因 |
|---|---|---|
| IDE bridge (VSCode/JetBrains) | `vscode-ide-bridge/`（辅助目录）+ `src/ide/` | 需 IDE 扩展宿主(LSP/extension API)，非 DSL 能表达 |
| web / claude.ai | `packages/remote-control-server/`（自托管 RCS+Web UI）、`packages/cloud-artifacts/`（CF Worker）、`shared-web-ui/` | 独立 web 应用栈(React/Vite/Radix/Cloudflare)，非 CLI 核心 |
| 完整 OAuth | `packages/mcp-client/` OAuth + `src/utils/auth.ts` + `McpAuthTool` | 需浏览器 redirect 回调 + token 持久化；McpAuth 工具已移植为「提示」(Phase 4) |
| computer-use (NAPI) | `packages/@ant/computer-use-mcp/` + `computer-use-input/` + `computer-use-swift/` | 原生键鼠/截图(NAPI FFI，per-platform darwin/win32/linux backend)，非 DSL 能表达 |
| chrome (Claude in Chrome) | `packages/@ant/claude-for-chrome-mcp/` | Chrome 扩展原生消息协议，独立 MCP server |
| weixin | `packages/weixin/` | 微信集成，平台原生 |
| mobile | (无独立包，走 React Native/移动桥) | 移动运行时，非 CLI |
| audio (NAPI) | `packages/audio-capture-napi/` | 原生音频捕获 NAPI 模块 |
| image-processor (NAPI) | `packages/image-processor-napi/` | 原生图像处理 NAPI 模块 |
| color-diff / modifiers / url-handler (NAPI) | `packages/color-diff-napi/`、`modifiers-napi/`、`url-handler-napi/` | 原生 NAPI 模块（颜色/修饰键/URL scheme） |
| Ink UI 框架 | `packages/@ant/ink/` | 自定义 Ink(forked React 终端框架)；本移植用 std.ui 文本输出替代，非全功能 TUI |
| ACP / 远程协作 | `packages/acp-link/` | ACP 协议 WebSocket 桥接，独立服务 |
| voice mode | `src/` voice（push-to-talk，需 Anthropic OAuth） | 需音频 I/O + OAuth，平台层 |

> **判定标准**：凡依赖原生 OS API（NAPI/FFI）、GUI/Web/移动框架、浏览器、独立服务进程、或 provider OAuth 浏览器流的，均为平台层，非「编译到 Python 的 agent DSL」职责。本移植对标 **CC 核心逻辑层**（prompt/context/permissions/turn-loop/tools/commands/agent），非全量 567K 行（含 vendor/IDE/web/platform，水分大）。


## Phase 6 — Harness 完整化（全 Nexa）+ headless 铺垫  ✅ 完成（build + GLM 实跑，2026-06-25）

> ROADMAP_V2：harness 必须 Nexa（不原生冒充）。`src/harness.nx` 补 H=(E,T,C,S,L,V) 的 E/C/S/L/V（T 在 tools/）；`main.nx` headless 拆分。

| Nexa 组件 | claude-code-ts 源 | 忠实度 | 备注 |
|---|---|---|---|
| `harness.nx` : `run_turn_safe` (E) | `query.ts:890-1208`(attemptWithFallback) + `agent.py:630`(仅 timeout 重试) | **partial** | 包 Coder.run 加 GLM 1213/429/overloaded/timeout/connection 分类 + 指数退避重试。GLM 实跑经 run_one_turn |
| `harness.nx` : `auto_compact_if_needed` (C) | `services/compact/autoCompact.ts:62-143` + `query.ts:558-728` | **partial** | chars/4 估 token，超阈值(默认24000)摘要旧消息(留近4轮)；microcompact 分区算法未含 |
| `harness.nx` : `save/load/list_sessions` + `snapshot/restore_file` (S) | `utils/sessionStorage.ts:248,782-826` + `fileHistory.ts` | **partial** | transcript→~/.claude/projects/<dir>/session-*.jsonl；file history 备份/回退。单测全过 |
| `harness.nx` : `run_hook_event` (L) | `utils/hooks.ts:77-101,200`(HookEvent) + settings hooks 字段 | **full** | 4 事件 settings.json 驱动；matcher+command+$CC_HOOK_INPUT env+非零exit阻断。实测 HOOK_FIRED_hello/STOP_HOOK_OK |
| `harness.nx` : `verify_output` (V) | Nexa verify 原语 + CC verification-agent(VERIFICATION_AGENT) | **partial** | 类型/等值校验原语；语义校验映射 verification-agent |
| `main.nx` : `run_one_turn` + flow main 拆分 (headless) | `REPL.tsx`(engine/UI 分离) + `query.ts`(turn 编排) | **mapping** | 引擎=run_one_turn(L+C+E 单 turn API，供 Phase 8 原生 UI)；REPL driver=flow main 可替换。GLM 实跑 "Engine ok" |


---
**迁移日志**（每次推进追加）：
- [Phase 0] 建目录 + 护栏文档 + 重定位 claude-code-nx + 完成 context.ts 源码精读。
- [Phase 1 ✅ 2026-06-24] 核心框架五件全完成，逐件「先读 claude-code-ts 源 → 翻译 Nexa → 头注释标注源 → 登记 → build + GLM 实跑」：
  - 1a 真 system prompt（agents.nx）：PREFIX + 6 静态段逐字移植，full。
  - 1b 真 context（context.nx）：git 快照(截断1000+"2k"文案)/CLAUDE.md 层级(user+project)/date/env，partial。
  - 1c 真权限模型（permissions.nx）：allow/deny/ask + exact/prefix/wildcard + deny>allow>ask，经 P-RUN-2 PreToolUse 钩子接入，GLM 三路径验证，partial。
  - 1d turn 循环映射（query_mapping.nx）：CC query.ts ↔ NexaAgent.run 逐项核对，不手写循环，mapping。
  - 1e REPL 骨架（main.nx）：onSubmit 交互 loop + std.ui render，GLM 端到端跑通(工具派发+权限+多轮+干净退出)，partial。
  - **端到端 GLM 验证通过**：agent 用真 system prompt 启动 → 读 test_phase1.txt(stub_read_file,权限 allow 放行) → 返回内容回复 → /exit 退出(exit 0)。权限 deny(stub_bash rm:*)/ask(stub_write_file) 单测全过。
- [Phase 1 踩坑·Nexa codegen 行为记录（Phase 2 复用）]
  - **Q-CG-1**：flow 条件里的 `or`/`and` 链（如 `a==x or b==y`）codegen 会串行化成 AST dict 字面量（生成非法 Python `if (a==x {'type':...} b==y)`）。**规避**：复合布尔一律移进 `python!` helper（如 `is_exit_command`），flow 条件只留单比较/单函数调用。与 P-CMP-1(else-if) 同类，是 codegen 表达式串行化的通病。
  - **Q-CG-2**：`flow_main` 末尾 codegen 固定 emit `return result`——若 flow 未定义 `result` 会 `NameError`(且仅在 flow 正常走完末尾触发，循环内 break 不触发)。**规避**：flow 末尾加 `result = "done";`。
  - **Q-RUN-1**：`python!` 换行——单 `\n`(单反斜杠)=真换行；双 `\\n`=字面 `\n`。字节级实证(stub_tools 用单 \n 正确，context 误用双 \\n 出字面)。**规则**：python! 里一律单 `\n`。
  - **Q-RUN-2**：`std.ui.input` 走 prompt_toolkit，Windows bash(MSYS, TERM=xterm-256color)非 TTY 报 `NoConsoleScreenBufferError`。**规避**：REPL 输入改用 Nexa 内建 `input()`(→纯 Python input)，输出仍用 std.ui(banner/agent_reply 在该环境正常)。
  - validator 误报 T-004/X-002 依旧（已知，`--harness=warn` 忽略）。
- [Phase 2 ✅ 2026-06-25] 7 个核心工具全部忠实移植（先读完整 TS 源→翻译→头注释标源→登记→build+GLM）：
  - Read（read.nx）：text offset/limit/cat-n(→)/256KB门/25000token门/binary拒/ENOENT；image/pdf 检测+读取（多模态注入受运行时限制，partial）；notebook cells。GLM 实跑通过。
  - Edit（edit.nx）：exact/replace_all/唯一性/必须Read/staleness/空串建文件，full。
  - Write（write.nx）：新建/必须Read+未改动/mkdir/覆盖，full。
  - Bash（bash.nx）：执行/timeout(120s,clamp600s)/stdout+stderr/截断30000/exit；run_in_background 同步执行(partial)，partial。
  - Grep（grep.nx）：ripgrep 全参数+输出模式+head_limit=250，rg 不可用降级 Python re，full。
  - Glob（glob.nx）：glob 模式/mtime 排序/limit100/相对化，full。
  - NotebookEdit（notebook.nx）：replace/insert/delete/cell_id 定位/清outputs/越界→insert，full。
  - **stub 全部移除**；agent `uses` 改绑 7 真工具（对齐 system prompt 工具名）。
  - **GLM 端到端验证**：agent 用真 Read 读 agents.nx→正确识别 7 工具；用真 Bash(echo)→phase2_done；权限 allow/deny/ask + default/plan mode 全验证。
  - 并行修复①②③：工具名对齐 / 钩子幂等(TOOL_HOOKS 查 __name__) / permission modes(default+plan)。
- [Phase 2 踩坑·Nexa codegen 行为记录]
  - **Q-CG-3**：@tool fn 的默认参数（`offset: number = 0`）codegen 有 bug——既不生成 Python def 默认值，又把该参数从 schema properties 整个丢弃（`inspect.signature` 无默认 + schema 无 offset 属性）。**结论：Nexa 此版本不支持真正的可选工具参数**。**规避**：所有工具参数声明为 required（无默认），body 内把 falsy(0/""/False) 当 CC 默认值处理（如 offset 0→1）。代价：schema 把 CC 的可选参数标为 required——登记为已知限制。GLM 实测：required 参数 GLM 会全传（Read 的 offset/limit/pages、Bash 的 timeout/run_in_background 均正确发送）。
  - **Q-RUN-3**：Windows 上 `subprocess(executable=SHELL)` 不可靠——git-bash 的 SHELL=/usr/bin/bash 是 MSYS 内部路径，Windows python 无法执行（exit 126 "/c: Is a directory"）。**规避**：Bash 工具用 `shutil.which('bash')` 取 PATH 里的 bash，以 `[bash,'-c',cmd]` 执行；无 bash 才降级 shell=True。
- [Phase 3 前置 ✅ Q-RUN-1 转义修复 2026-06-25] 审计所有 python! 块的双反斜杠转义。**确认 bug 并修复**：bash.nx(7处)、edit.nx(9处含 CRLF 死代码 `content.replace('\\r\\n','\\n')`)、write.nx(死代码 _nlines 直接删)、read.nx:103(image note) 的 `\\n`/`\\r` 全改单反斜杠（运行期为真换行/CR）。正则里的 `\\\\`（permissions/grep，字面反斜杠）保留。**回归测试**：造真实 CRLF 文件→Read→Edit→成功（之前是死代码必失败）；Bash 输出现在真换行（`'a\nb\n\n[exit code: 0]'`）。
- [Phase 3 ✅ 2026-06-25] 13 个高频斜杠命令忠实移植（先读 src/commands/<name>/ 完整源→翻译行为→头注释标源→登记→build+GLM）：
  - `src/commands.nx`：`run_command` 派发器（python! 内 dict 派发 13 handler）。full：help/clear/status/context/config/vim/exit。partial：compact(摘要核心，无分区算法)/model(显示，菜单 UI)/cost(消息数，无 analytics)/fast(标志，Opus 专属)/rewind(数值回退，无 picker UI)。stub：resume(会话存储平台子系统)。
  - 命令经 main.nx flow 的 run_command 接入（对齐 REPL.tsx onSubmit 命令分支）；exit 经 `__CC_EXIT__` 哨兵。
  - **GLM 端到端**：REPL 中 agent turn + /status + /help + /exit 交替正确。
- [Phase 3 踩坑] 无新 codegen bug；复用既有铁律（单 \n / 复合布尔在 python! / 嵌套 if-else / flow 末尾 result="done"）。
- [Phase 4 ✅ 2026-06-25] 高级工具忠实移植（先读 packages/builtin-tools/src/tools/<X>/ 全源→翻译→头注释标源→登记→build+GLM）：
  - TodoWrite（todo.nx）：todos JSON/状态约束/全完成清空/结果文案逐字，full。GLM 实跑通过。
  - Agent（agent.nx）：子 agent 映射 NexaAgent(fresh 隔离上下文)→.run()（不手写循环），explore=只读/general=全工具。GLM 实跑：sub-explore 调 Glob 报告。partial(fork/memory 未含)。
  - Plan（plan.nx）：EnterPlanMode/ExitPlanMode(0参,转 plan/default 模式)+VerifyPlan，full。
  - MCP（mcp.nx）：stdio JSON-RPC 客户端(initialize→initialized→method)+MCPTool/List/Read/Auth，partial→full(协议)；配置读 .mcp.json。
  - Web（web.nx）：WebFetch(urllib+HTTP→HTTPS+HTML剥离) full(抓取)；WebSearch stub(无搜索后端)。
  - 接线：Coder uses 加 7 新工具；权限只读类 allow / 改动网络类 ask。
- [Phase 4 踩坑·复发 Q-RUN-1 + 新坑]
  - **Q-RUN-1 复发（已修）**：web.nx(6处:正则反引用 `\\1`/`\\t`/`\\s`/`\\n`) 与 mcp.nx(2处:JSON-RPC 定界符 `\\n`) 初版又误用双反斜杠→字面。**全部改单反斜杠**，字节级 od 验证（`</\1>` 单反引用、`'\n'` 真换行）。WebFetch 剥离 CSS 验证通过。教训：正则反向引用/字符类转义同样是「单反斜杠=真」，与 `\n` 同理。
  - **Q-CG-4（@tool 描述内层双引号）**：todo.nx 描述含 `{\"content\":...}`，Nexa STRING_LITERAL 不认 `\"` 转义→parse 报 `No terminal matches 'c'`。**规避**：@tool 描述内不出现双引号（改无引号 JSON 示例或单引号）。
  - **Q-RUN-4（NexaAgent.tools 期望 schema 而非函数）**：子 agent 传 `[Read,Glob]`(函数)→ "function is not JSON serializable"。codegen 给 Coder 传的是 `[__tool_X_schema,...]`(schema 字典)，执行才经 LOCAL_TOOLS 查函数。**规避**：子 agent tools 传 `__tool_X_schema` schema 对象。
  - **Q-RUN-5（撇号转义 `\\'`）**：agent.nx/mcp.nx 单引号串里撇号误写 `\\'`(双)→.py `\\'`→Python 把 `\\`当字面、`'`闭合串→unterminated。**规避**：含撇号的 Python 串用双引号 `"..."`（撇号免转义）。
- [Phase 5 ✅ 2026-06-25 收尾] 修复 + out-of-scope 标注 + 权限补齐 + 最终统计 + 结论 + 补丁建议：
  - **必修修复**：mcp.nx notifications/initialized 帧定界 `\\n`→`\n`（双→单，MCP 帧曾断裂）；**MCP 端到端回归通过**（echo server: initialize→initialized→tools/call/resources 全响应）。
  - **真·零残留转义审计**：permissions.nx 通配转义代码用 `chr(92)`/`chr(0)` 重写（消除所有反斜杠源码歧义）；终审生成 .py 非-raw 双反斜杠 = **0**。
  - **out-of-scope 标注**（Phase 5 段）：IDE/web/OAuth/computer-use/chrome/weixin/mobile/audio/image-processor/NAPI/Ink/ACP/voice 逐条标 out-of-scope + 注 `packages/@ant/*` 位置。
  - **权限补齐**：bypass(全放行)/auto(ask 自动批准) mode + 多 settings 源合并(user/project/local)；现支持 default/plan/bypass/auto 4 模式。实测全过。
  - **最终统计 + 结论**：见 `FINAL_REPORT.md`（Nexa 移植 2062 行 vs CC 全仓 711K / 核心层 623K / 平台 79K；核心子集移植；Nexa 解放 agent 编排层）。
  - **P-CMP-4 补丁建议**：python! 双反斜杠转义 lint/codegen 告警（登记 NEXA_PATCHES.md，仅建议不改 nexa-lang）。
- [收尾加固 ✅ 2026-06-25 最终收口]
  - **文档同步**：permissions.nx 头注释/工具描述/标题过时（仍写「default/plan 两 mode、未含 bypass/auto」）→ 改为 4 模式(default/plan/bypass/auto)+多源，与 body 一致。
  - **全量自审**：通读 src/*.nx + src/tools/*.nx——所有文件 Ported-from 源标注齐全且准确（CC 源未变，行号稳定）；无真实 TODO/FIXME/过时标记（agents.nx 的 `TODO_WRITE_TOOL_NAME` 是常量名误报，context.nx/todo.nx 是准确 partial 注记）；PORT_TRACE 14 行覆盖全部用户面工具（plan/mcp/web 多工具文件按行分组，内部 _mcp_* helper 不登记）；partial/stub 标注如实。
  - **端到端 GLM 回归**（auto 模式）：Read _target.txt → Edit(hello→bonjour，auto 批准执行) → Bash(cat 验证) → 文件实际改为 `greeting=bonjour` + agent 报告；另测 TodoWrite + EnterPlanMode/ExitPlanMode 模式转移动作（注：plan 工具会覆盖运行时 mode，这是单全局 mode 的已知简化）；/status /exit 正常。**核心链路无回归**。
- [Phase 6 ✅ 2026-06-25 Harness 完整化（全 Nexa）+ headless 铺垫] 按 ROADMAP_V2，harness 全 Nexa（不原生冒充）。`src/harness.nx` 补 E/C/S/L/V 五维 + `main.nx` headless 拆分：
  - **E 执行**（`run_turn_safe`）：包 Coder.run() 加 GLM 瞬态错误(1213 prompt 未接收 / 429 限流 / overloaded / timeout / connection)分类 + 指数退避重试(2,4,8…cap30s)。源：query.ts:890-1208 attemptWithFallback + agent.py:630(仅 timeout 重试→补 GLM 错误)。GLM 实跑经 run_one_turn 验证。
  - **C 上下文**（`auto_compact_if_needed`）：估算 token(chars/4)，超阈值(默认 24000)摘要旧消息(保留近 4 轮)。源：autoCompact.ts:62-143(AUTOCOMPACT_BUFFER=13000/getAutoCompactThreshold) + query.ts:558-728。单测：空会话正确跳过。
  - **S 状态**（`save_session`/`load_session`/`list_sessions`/`snapshot_file`/`restore_file_snapshot`）：transcript 持久化到 ~/.claude/projects/<dir>/session-*.jsonl + file history snapshots(编辑前备份/回退)。源：sessionStorage.ts:248,782-826 + fileHistory.ts。单测：save/list/load-missing/snapshot 全过。
  - **L 生命周期**（`run_hook_event`）：4 事件(PreToolUse/PostToolUse/UserPromptSubmit/Stop)经 .claude/settings.json hooks 配置驱动(读 hooks.ts getHooksConfig 格式)，matcher 匹配工具、command 类型、$CC_HOOK_INPUT env 注入、非零 exit 阻断。**实测**：UserPromptSubmit echo → `HOOK_FIRED_hello`(env 注入)；Stop → `STOP_HOOK_OK`。
  - **V 验证**（`verify_output`）：输出校验原语(string/number/boolean/non-empty/等值)。源：Nexa verify 原语 + CC verification-agent 模式(VERIFICATION_AGENT)。单测：PASS/FAIL 正确。
  - **headless 拆分**（`run_one_turn` 引擎 + flow main REPL 驱动）：引擎编排 L(UserPromptSubmit)+C(compact)+E(safe-run)，暴露单 turn API 供 Phase 8 原生 UI 调用；流式经 runtime stdout(P-RUN-1)。GLM 实跑：run_one_turn → "Engine ok" + Stop hook。
- [Phase 6 踩坑]
  - **Q-CG-5（flow 字符串字面量必须双引号）**：flow 层用单引号 `'Stop'` → lark 报 `No terminal matches '''`。Nexa flow STRING_LITERAL 仅认双引号 `"..."`（单引号只在 python! 内合法=Python）。**规避**：flow 字符串一律双引号。
  - **Q-CG-6（@tool fn 闭合 `}` 易漏）**：多 @tool fn 文件，python! `"""` 后的 `}` 闭合易漏（harness.nx 8/9 漞）→ 下个 @tool 处 parse 错。**规避**：写完每个 fn 核对 `"""` 后有 `}`。
- [Phase 7 ✅ 2026-06-25 日常开发功能补齐（全 Nexa）]
  - **必修修复**：`run_turn_safe` 重试去重——agent.py:454 调 LLM 前已 append user msg，1213 重试会重复。except 分支重试前检查 `Coder.messages[-1]` 是否本次 user msg，若是 `pop()`。**回归通过**（mock 1213：重试后 user msg=1，无重复）。
  - **7 命令**（commands.nx run_command 派发）：/init(init.ts NEW_INIT_PROMPT, local-prompt→agent 写 CLAUDE.md，经 `__AS_PROMPT__:` 哨兵 + flow strip_prefix 路由 run_one_turn)；/doctor(doctor.tsx Doctor→文本诊断:model/cwd/secrets/settings/MCP/规则/mode/python)；/add-dir< path>(add-dir)；/memory(memory.tsx→CLAUDE.md 层级文件列表)；/permissions(permissions.tsx→allow/deny/ask 规则+mode)；/agents(agents.tsx→Coder+内置子 agent)；/mcp(mcp.tsx→.mcp.json server 列表)。6 文本命令单测全过；/init GLM 路由验证（agent 收到 prompt 开写）。
  - **auto-compact 默认开**：run_one_turn 每轮调 auto_compact_if_needed(0)（默认阈值 ~24K token）。
  - **流式默认开**：Coder `stream: true`；带工具流式需 `NEXA_STREAM_TOOLS=1`（P-RUN-1 补丁，README/agents.nx 文档说明）。GLM 实跑流式 + 命令路由无回归。
  - **辅助**：main.nx 加 strip_prefix helper；flow 命令分支路由 `__AS_PROMPT__`→run_one_turn；/help 列出 7 新命令。
- [Phase 7 踩坑] 无新 codegen bug；复用 Q-CG-5（flow 字符串双引号——`__AS_PROMPT__:` 等哨兵用双引号）。
- [Phase 8 ✅ 2026-06-25 原生 UI 外壳（Python Textual，混合架构）] `ui/app.py`（242 行，纯 UI，无 agent 逻辑）：
  - 引擎 = Nexa 编译产物（src/main.py 的 run_one_turn/run_command/init_permissions/seed_context/build_user_context）；UI import 驱动渲染。
  - **边界铁律守住**：grep ui/*.py 确认无 turn 循环/execute_tool/_decide/LLM 调用/钩子注册（CLEAN）。
  - 交互：Header(banner) + RichLog(消息流: rich markdown 回复 + 工具调用 panel) + Input + Footer；/ 命令经 run_command 派发（含 `__AS_PROMPT__`→run_one_turn、`__CC_EXIT__`→退出）；权限 ask 经引擎侧 `_CCPORT_ASK_HANDLER` 回调 → Textual AskModal y/N（跨线程 push_screen+Event）；工具调用经 stdout 捕获实时渲染；深/浅主题（self.dark toggle，键 t）；Ctrl+C 退出 / ↑↓ 历史 / Esc 取消 worker。
  - 引擎调用在 worker 线程（`run_worker(_job, thread=True)`）避免 UI 冻结；stdout 经 `_LineStream` 按行捕获 → call_from_thread 渲染。
  - **验证**：① pilot stub 测试——compose(input/msglog/header) + worker + 工具 panel + reply markdown 全通（stub_ran=1/tool_lines=1/replies=1）；② 权限 modal pilot——modal_up=True, ans=y（跨线程 y/N）；③ **真实 GLM 端到端 pilot**——「读 _t.txt」→ agent 调 Read（tool_calls_rendered=1）→ 回复 "The content of _t.txt is phase8 tui e2e content"。
  - 引擎侧改动（permissions.nx）：ask 路径加 `_CCPORT_ASK_HANDLER` 钩子（UI 可插拔，非 agent 逻辑）。
- [Phase 8 踩坑] **Q-UI-1（Textual run_worker 传参）**：`run_worker(self._engine_impl, text, thread=True)` → worker 报 `_engine_impl() missing 'text'`（Textual 8.x worker 不透传方法参数）。**规避**：用闭包 `_job = lambda: self._engine_impl(text)`，run_worker 跑无参闭包。
- [Phase 10 ✅ 2026-06-25 换模型 glm-5.2（调通）+ 全功能修通 + 错误加固]
  - **换模型 glm-5.2 调通（根因=端点）**：glm-5.2 是 Coding 模型，配额在**专属 Coding 端点** `https://open.bigmodel.cn/api/coding/paas/v4`（非通用 `paas/v4`）。通用端点对 glm-5.x 报 `code 1113 余额不足`（误判，实为端点错）。切 coding 端点 + 新 key 后 glm-5.2 OK（`GLM52_READY`，26 reasoning_tokens——推理模型）。
  - secrets.nxs：BASE_URL=coding 端点 + MODEL_NAME=glm-5.2；agents.nx/main.nx/agent.nx model 全 glm-5.2。
  - **glm-5.2 经 Nexa 引擎调通**：`GLM52_ENGINE_OK`；多工具(Read+Edit+Bash，val=old→new 实改) + 流式(NEXA_STREAM_TOOLS=1) + /status 显示 `Model: glm-5.2`。glm-5.2（1M 上下文/128K 输出，coding SOTA，对齐 Opus 级）质量明显优于 glm-4-flash。
  - **/model 真运行时切换**：`/model <name>` 设 Coder.model + 清 _client 缓存，下一轮生效（实测 glm-4-flash↔glm-5.2）。
  - **/mcp 真连**：echo MCP server + .mcp.json → MCPTool tools/call `echo: {"x":1}`。
  - **/compact 真压**：13 消息→GLM 摘要→3 消息(sys+summary+ack)。
  - **/resume 跨进程**：save→list_sessions→load 恢复 3 消息。
  - **流式默认开**：agents.nx stream:true + README NEXA_STREAM_TOOLS=1。
  - **20 命令全测 PASS**（19 文本 + /compact GLM）；**14+ 工具全测 PASS**（auto execute_tool 全可读无崩溃 + Agent/MCP×4 已验证 + glm-5.2 下 Read/Edit/Bash 工具调用）。
  - **错误加固**：run_turn_safe 对余额(1113)/鉴权(401)错误**不重试**；工具异常均返回可读错误字符串。
  - **最终验收**：build Success + 转义 0 残留 + glm-5.2 端到端(Read+Edit+Bash→回复→/status→/exit，流式)。
- [Phase 11 ✅ 2026-06-25 换 glm-5.1 + Ink/React UI 还原 CC]
  - **换模型 glm-5.1**：secrets MODEL_NAME=glm-5.1（coding 端点不变）；agents/main/agent 全 glm-5.1。验证 `GLM51_OK`。
  - **引擎 JSON 事件模式**（main.nx `run_json_events` @tool fn，Nexa 全 I/O 层）：stdin 读 JSON(message/command/exit/permission_response)，stdout 发 JSON 事件(ready/assistant_token/tool_call/tool_result/permission_request/command_result/done/error/session_end)。permission 经 `_CCPORT_ASK_HANDLER` emit+等 stdin。tool_call/result 由引擎 stdout 的 _debug_print 标记解析。实测：ready→tool_call(Read+args)→tool_result→done 全对。与 std.ui REPL 并存（flow main 按 NEXA_JSON_EVENTS 分支）。
  - **Ink/React UI**（ui-ink/，278 行 TS，CC 亲儿子技术栈）：engine.ts(subprocess+JSON 协议)+index.tsx(App+组件)。组件对齐 CC：StatusBar(Model|cwd|●working/○idle，橙边)+MessageLog(用户 dim+assistant●+⏺工具call/result ⎿)+PromptInput(底部>)+PermissionModal(居中 y/N)+流式 assistant_token 逐字。主题 Claude Orange #D77757 / Blue #5769F7 / 暖暗底。subprocess 启 python src/main.py，JSON 管道。
  - **验证**：bun install OK + typecheck CLEAN + **Ink 渲染 CC 风格帧**(橙边 StatusBar Model:glm-5.1|cwd|idle + MessageLog + 输入框) + **TS↔JSON↔Python 桥端到端**(Engine 收 ready→done，reply INK_BRIDGE_OK)。边界 CLEAN（ui-ink/ 无工具执行/权限决策/LLM/agent 实例化）。
  - **Textual UI 保留**（ui/app.py 方案 A backup；ui-ink/ 方案 B）。
- [Phase 11 踩坑] **Q-RUN-1 复发（已修）**：run_json_events 的 `_TC` 正则初版又用 `\\[`/`\\s`/`\\w`（双反斜杠）→ tool_call 解析失败(name=?)。改单反斜杠 `\[...\]\s*(\w+)` → tool_call 正确发射。教训再次印证 P-CMP-4 价值。
- [Phase 12 ✅ 2026-06-25 UI 深度还原 CC 动态交互 + 修 bug]
  - **深度研究**（读 CC Ink 代码，非截图）：constants/figures.ts:4-6(BLACK_CIRCLE '⏺' / TEARDROP_ASTERISK '✻' / SETTLED_GREY #999)、LogoV2/AnimatedAsterisk(✻ 启动 logo)+Clawd(螃蟹 mascot，象限字符 art)、Spinner/SpinnerGlyph(cycling chars 动画)、messages/AssistantToolUseMessage:140(⏺ ToolName → ⎿ result)、permissions/弹窗。
  - **Track A — Ink UI 深度还原**（ui-ink/ index.tsx，315 行）：✻ logo 启动画面(grey #999)+ 小螃蟹 mascot(▗▄▄▖/▟███▙/▜███▛)；spinner(ink-spinner dots，busy 生命周期 ready→done 驱动 start/stop)；⏺ ToolName(args)→⎿ result 缩进 dim（对齐 AssistantToolUseMessage）；权限弹窗(rounded box「✻ Claude wants to use [Tool]」+ 参数 key:value 列表 + y/N，非纯文字⚠)；流式 ▋ 光标；底栏 ctx%(token 估算/200K，>80% 变橙)；消息颜色(用户>/assistant●/工具⏺ 蓝/橙)。
  - **Track B — 引擎 bug 修**（Nexa）：① Bash Windows GBK UnicodeDecodeError → `subprocess.run(encoding='utf-8', errors='replace')`（中英混合 echo 不崩，实测「你好 hello 世界」正确）；② run_in_background note 泄漏移除（不再在 agent 可见输出加「[note: ... not ported]」）；③ WebFetch HTTP 错误可读（401/404/超时 → 「WebFetch HTTP error N」，不堆栈）；④ **agent 自我认知 = Claude Code**（系统 prompt 纯 CC；默认跳过全局 ~/.claude/CLAUDE.md——它是宿主 CC 会话的 OMC 编排层、非 port agent 配置，注入会污染身份；env NEXA_INCLUDE_GLOBAL_CLAUDE_MD=1 可开。实测 agent 答「我是 Claude Code，Anthropic 官方 CLI」，不提 OMC/Nexa）。
  - **验收**：Ink 渲染 ✻ logo+螃蟹+spinner StatusBar(ctx% ○idle)+⏺⎿+权限框；Bash 中英混合不崩；note 不泄漏；WebFetch 可读；agent 自认 Claude Code；typecheck CLEAN + 边界 CLEAN（ui-ink/ 无 agent 逻辑）+ 转义 0 残留。










