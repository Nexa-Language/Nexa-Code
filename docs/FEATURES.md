# Tool and command inventory

The source baseline exposes **50 public tool definitions** and **50 command names/aliases**. The former Coder list included 46 of those tools; the 2.4 loader exposes all 50, including the four MCP entries. The command fixture was extracted from the prior dispatcher and is checked against both the host and UI menu. Counts include aliases. Each tool schema has an executable handler and passes through runtime approval and policy before execution.

## Tools

| Names | Current implementation / compatibility | Evidence or remaining limit |
| --- | --- | --- |
| Read, Edit, Write, MultiEdit | Local text operations, read state/staleness checks, existing-file snapshots. | File read/write, atomic multi-edit failure, stale edit and restart/undo regressions. Read images return metadata; PDF extraction is an existing manual-tool requirement. |
| Glob, Grep | Pattern search and ripgrep/Python fallback. Outside paths and search scopes containing external symlinks require approval. | Policy path/link regressions; all schemas loaded. Grep fallback has a smaller option set than ripgrep. |
| NotebookEdit | Read/replace/insert/delete notebook cells. | Real notebook read/edit regression. |
| Bash, PowerShell | Managed command processes, deadline and cancellation; Bash supports managed background jobs. | Bash file verification, cancellation, timeout, bounded large stdout/stderr and group cleanup. PowerShell requires that executable; Windows needs platform validation. |
| REPL, Sleep, Monitor | Managed Python process; bounded cancellable sleep; current-host process result retrieval. | Offline REPL and background deadline/drain tests. Jobs end with the host. |
| TodoWrite, TaskCreate, TaskUpdate, TaskList, TaskGet | Session task/todo records copied into checkpoints. | Task/todo and metadata isolation regressions. |
| Agent | Isolated read-only research through Nexa execute, child checkpoint and parent usage attribution. | Real fixture child run, counted usage, parent checkpoint restore. All old subagent labels use this research scope. |
| AskUserQuestion | Validated question event, call-bound answer, cancel/deadline. | Malformed options regression and typed UI parsing. |
| EnterPlanMode, ExitPlanMode, VerifyPlan | Explicit plan/default transitions and verification checklist output. | Plan transitions and deny-before-allow policy tests. VerifyPlan records supplied evidence, without independently running tests. |
| WebFetch, WebSearch | Cancellable bounded HTTP fetch / DuckDuckGo Instant Answer API. | Offline GET deadline/cancel and response bounds; WebFetch live test is opt-in. Remote search availability requires integration verification. |
| RemoteTrigger | Approved JSON webhook POST; lost/rejected response preserves an unknown result for reconciliation. | Offline simulated response loss verifies started journal and blocked continuation. Live webhook integration is opt-in. |
| MCPTool, ListMcpResources, ReadMcpResource, McpAuth | Official MCP SDK stdio/HTTP calls; connection cleanup; explicit auth guidance. | Offline stdio tool/resource server and process cleanup pass. HTTP/OAuth integration is unverified; browser OAuth is unavailable and resource listing currently returns one page per server. |
| SearchExtraTools, ExecuteExtraTool | Search actual exposed schemas; delegate through the same dispatcher and nested deny policy. | Inventory and nested deny tests; malformed inner JSON remains recoverable. |
| Skill, DiscoverSkills | Read local skill definitions and discover installed files. | Schema/path policy checks. Global skill paths require approval; returned files are context, not independent authority. |
| Config | Validated host settings bridge for theme/editorMode and next-turn budgets. | Invalid values rejected; restart loads saved settings. Credentials remain in runtime configuration. |
| PushNotification, TerminalCapture | Managed OS notification/capture commands. | Process layer tested offline; GUI permissions/platform effects require integration validation. Windows capture returns setup guidance. |
| EnterWorktree, ExitWorktree | Explicit Git worktree add/remove without force; selected host cwd stays fixed. | Schema and managed process path checked. Git mutation requires approval; existing branch/dirty-worktree errors remain visible. |
| LocalMemoryRecall, Brief, Goal | Session memory lookup, local brief file and goal records. | Checkpoint metadata regression; existing file-based brief behavior retained. |
| CtxInspect | Environment/context summary. | Schema load and context bootstrap exercised. |
| SendMessage, ListPeers | Local mailbox and peer registry reporting. | Registry persistence covered by metadata boundary. Distributed ACP peer transport is unavailable. |
| CronCreate, CronDelete, CronList | Session schedule registry. | Schema/load compatibility; scheduler execution remains unavailable and is stated in results. |
| Artifact, ReviewArtifact, SendUserFile | Runtime content-addressed artifacts, retrieval and local file references. | Artifact content/identity tested; references remain local, with no automatic upload. |

Tool definitions remain in `src/tools/*.nx`. Python services in `nexa_code/tool_services.py`, `processes.py` and `mcp_tools.py` supply platform integration. The offline inventory test checks the exact tool set, handlers and approval flags; behavior tests target the changed runtime, filesystem, policy, process and recovery boundaries. Platform/network rows above identify checks that need a separate environment.

## Slash commands

All names below are available through `/help` and the UI menu. Direct user commands are explicit requests; plan mode restricts mutation commands. Model-initiated tools always use the policy/approval boundary.

| Names | Current behavior / migration |
| --- | --- |
| /help | Complete command list. |
| /clear | New session; retain older checkpoints; clear session authorization and bypass. |
| /model | List configured models or create a new session with a chosen model. |
| /resume | Native session picker/ID, validated legacy JSONL import, and observed unknown-outcome resolution. |
| /cost, /usage, /stats | Accumulated parent/child tokens and calls. Currency prices are not configured. |
| /status, /session | Current session/run ID, runtime state, model, provider, cwd and mode. |
| /context | Current environment/instruction context preview. |
| /config | Validated get/set for theme, editorMode, timeout, max_model_calls and max_tool_calls. |
| /vim, /theme | Minimal insert/normal input mode and graphite/light themes. Persist defaults via /config. |
| /fast, /effort | Explain unsupported provider tuning; select a configured model instead. |
| /history, /recap, /summary | Stored message listing. |
| /rewind | Fork a selected message prefix as reviewed transcript context. |
| /compact | Create a new session from an explicit reviewed summary; automatic private-client compaction removed. |
| /exit, /quit | Cancel active work, clean managed resources and exit. |
| /init, /review, /pr, /commit | Task prompts through the same runtime, with exact tool approval for effects. |
| /doctor, /env, /login | Runtime/configuration/toolchain diagnostics; credential presence only. |
| /add-dir | Register an existing reference directory; outside-workspace tool approval remains required. |
| /memory | Inspect instruction paths or add local session memory. |
| /permissions | Modes, migration notices, exact rules and zero-based remove; scoped grants through approval panel. |
| /agents | Current Coder and read-only research scope. |
| /copy | Copy an assistant response to OS clipboard, with a local response-file fallback. |
| /export, /share | Export a local Markdown transcript; no automatic publication. |
| /undo | Restore prior file snapshots; /undo list shows available backups. |
| /git, /diff | Explicit managed Git invocation / diff without external diff/textconv execution. |
| /mcp | Inspect named transports and add/remove explicit server configurations. |
| /feedback, /bug | Save a local diagnostic report for review before sharing. |
| /keybindings, /terminal-setup | Show supported keyboard interactions. |
| /release-notes, /version | Candidate version and migration pointers. |
| /screenshot | Explicit OS capture service. |
| /install | Explicit uv add or pnpm add inside the selected workspace. |
| /plugin | Guidance to local skills, MCP and packages; marketplace unavailable. |
| /hooks | Manage/test named manual hooks; legacy automatic lifecycle hooks require migration. |

The legacy command set is frozen in `tests/fixtures/legacy-commands.json`. `tests/runtime/test_tools.py` and `ui-ink/tests/commands.test.ts` guard against dropping names. Runtime/session/policy tests cover command effects used in recovery and configuration; `scripts/pty_smoke.py` drives commands, approvals and cancellation through actual Ink.
