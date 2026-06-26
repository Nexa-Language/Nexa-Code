# Nexa Engine Code Review

Date: 2026-06-26

Scope reviewed: `src/*.nx`, `src/tools/*.nx`, generated `src/main.py` where needed, `ui-ink/src/*` for JSON-event/UI coupling, and CC reference source under `D:\code\nexa\refs\claude-code-ts`.

Verification used during review:

- `nexa build src/main.nx --harness=warn` passed with known harness warnings only.
- Headless H-lane matrix was executed separately; see `TEST_EXECUTION_REPORT.md`.
- `python!` escaping was searched across `.nx`; no actionable residual double-backslash Python string bug was found.

## HIGH

### H1. Bash uses the first `bash` on PATH and cannot operate on Windows paths

Evidence:

- Nexa source: `src/tools/bash.nx:38-43` selects `shutil.which('bash')` and runs `[bash, -c, command]`.
- Failing E2E: `Read -> Edit -> Bash cat "D:\...\e2e.txt"` edited the file but Bash returned `cat: 'D:\...\e2e.txt': No such file or directory`.
- Output also included WSL startup garbage on successful commands, so the selected shell is not a clean Git Bash/MSYS path for this project.
- CC reference handles Windows path conversion: `refs/claude-code-ts/src/utils/windowsPaths.ts:125-138`; Bash permissions also convert cwd on Windows at `refs/claude-code-ts/packages/builtin-tools/src/tools/BashTool/bashPermissions.ts:2149`.

Impact:

- Any model-generated Bash command using paths from Read/Edit/Write will fail on Windows.
- The tool returns misleading stderr noise even when exit code is 0.
- This breaks the core Claude Code workflow: read/edit, then run a verification command.

Fix suggestion:

- Prefer a known compatible shell on Windows, or translate Windows paths to the selected shell dialect before execution.
- Use the CC `windowsPathToPosixPath` behavior as the reference.
- Add an E2E regression: create a file under `D:\...`, edit it, then `cat`/`test -f` it through Bash.

### H2. UserPromptSubmit hooks cannot block or modify prompt execution

Evidence:

- `src/main.nx:87-93` calls `run_hook_event('UserPromptSubmit', '', prompt)` and ignores the returned text.
- `src/harness.nx:236-238` represents non-zero hook exits as a `[hook ... BLOCKED]` string, but `run_one_turn` does not stop or surface it as a blocking result.
- CC hook lifecycle treats hook feedback as user-facing and can block/alter flow; this port only executes and discards the result for prompt-submit.

Impact:

- Safety hooks that should block a prompt do not block the agent turn.
- Users may believe hooks are enforced when only tool hooks are effectively blocking.

Fix suggestion:

- Make `run_hook_event` return structured status: `ok | blocked | error`.
- In `run_one_turn`, stop before auto-compact/model call if UserPromptSubmit returns a blocking result.
- Emit the hook result into JSON events so Ink can render it.

### H3. Permission model can be bypassed by direct exported tool calls

Evidence:

- Permission enforcement is registered as a `PreToolUse` hook in `src/permissions.nx:162-187`.
- Individual tool functions such as `Bash` do not enforce permission internally (`src/tools/bash.nx:19-20`).
- Generated `src/main.py` exports callable functions; direct import and call bypasses the tool registry and hooks.
- Test result: after `set_permission_mode('plan')`, direct `Bash('printf should_not_run', ...)` executed and returned `should_not_run`.

Impact:

- Normal agent calls through the registry are protected, but any headless integration or test harness that imports `src/main.py` can bypass deny/plan rules.
- This matters because this project exposes a headless engine/API surface, not only a closed TUI.

Fix suggestion:

- Expose a single guarded `execute_tool` API for headless usage.
- Make direct tool functions private/internal in generated output where possible, or add a shared guard inside every mutating tool.
- Add tests for both registry-path enforcement and direct-call rejection.

### H4. MCP stdio calls can hang indefinitely

Evidence:

- `src/tools/mcp.nx:56-60` writes a JSON-RPC request and blocks on `_proc.stdout.readline()` with no timeout.
- The `Popen` itself has no communication deadline; only final `wait(timeout=3)` runs after a response path.

Impact:

- A misbehaving MCP server can hang the whole agent turn.
- This is worse than returning an MCP error because it can strand the UI with no progress.

Fix suggestion:

- Wrap stdout reads with a timeout using a reader thread, `selectors` where available, or `asyncio`.
- Kill the MCP child process on timeout and return a structured error.
- Include stderr tail in the error.

### H5. JSON-events mode still drops runtime stderr during turns

Evidence:

- UI engine now buffers process stderr in `ui-ink/src/engine.ts:65-74`.
- But engine runtime redirects stderr to `_NullStream` while executing commands/messages in `src/main.nx:198` and `src/main.nx:207`.
- `_NullStream` is defined at `src/main.nx:171-175`.

Impact:

- Exceptions, warnings, hook stderr, and tool diagnostics emitted during a turn can vanish before `engine.ts` can report them.
- This is the same family as the previous P0 "stderr swallowed" bug, only one layer deeper.

Fix suggestion:

- Replace `_NullStream` with a stream that emits `{"type":"stderr","content":...}` or appends to an error/debug event.
- Keep stdout JSON-clean, but never discard stderr silently.

## MED

### M1. Grep invalid regex is silently reported as no matches when `rg` exists

Evidence:

- `src/tools/grep.nx:87-98` returns `''` whenever `rg` stdout is empty, without checking `returncode` or stderr.
- Test: `Grep('[', path, output_mode='content')` returned `""`; expected an invalid-regex error.
- Python fallback would return `Invalid regex` at `src/tools/grep.nx:105-108`, but it is bypassed when `rg` is available.

Fix suggestion:

- If `rg.returncode not in (0, 1)`, return stderr or normalize it to `Invalid regex: ...`.
- Treat return code 1 as "no matches" only.

### M2. Hook config loading and matcher semantics are much simpler than CC

Evidence:

- `src/harness.nx:200-210` stops at the first settings file containing `hooks` instead of merging enabled setting sources.
- `src/harness.nx:217-222` matches by removing `*` and checking substring against the tool name.
- CC has a richer hook config/matcher pipeline; the local comments cite `utils/hooks.ts`.

Impact:

- User, project, and local hooks do not combine correctly.
- Matchers such as `Bash(rm:*)`, structured tool filters, or event-specific matching can behave incorrectly.

Fix suggestion:

- Merge hooks across all enabled settings sources using CC source order.
- Parse matcher syntax rather than substring-matching stripped patterns.

### M3. Hook subprocess decoding is locale-dependent and throws GBK exceptions

Evidence:

- `src/harness.nx:234` uses `subprocess.run(..., text=True)` with no `encoding` or `errors`.
- During test execution, Python emitted `UnicodeDecodeError: 'gbk' codec can't decode byte 0xff...` from a subprocess reader thread.

Impact:

- Hook stderr/stdout can produce noisy background exceptions or lose diagnostics on Windows.

Fix suggestion:

- Use `encoding='utf-8', errors='replace'` consistently, as `Bash` already does at `src/tools/bash.nx:42-43`.

### M4. Default session path can collide across projects with the same basename

Evidence:

- `src/harness.nx:105-108` saves default sessions under `~/.claude/projects/<basename(cwd)>/session-*.jsonl`.
- CC reference `sessionStorage.ts` encodes a project transcript path from the project identity, not just basename.

Impact:

- `D:\work\foo` and `D:\archive\foo` share the same session namespace.

Fix suggestion:

- Encode the absolute project path into the transcript directory, matching CC's session storage behavior.

### M5. Permission rule matching only checks one generic arg value

Evidence:

- `src/permissions.nx:121-133` extracts a single value from `command | file_path | path | notebook_path | pattern`.
- This cannot faithfully match tool-specific inputs for MCP, WebFetch, ListMcpResources, ReadMcpResource, or multi-arg cases.
- Real CC has tool-specific permission input formatting and Bash-specific matcher logic.

Impact:

- Rules can appear configured but fail to match the intended input.
- The local `.claude/settings.local.json` includes Nexa-only tool names; real CC warned that `MCPTool` and `McpAuth` match no known tool during the visual run.

Fix suggestion:

- Add per-tool permission input normalization.
- Validate rules against known Nexa tool names separately from CC tool names.

### M6. Agent tool hardcodes `glm-5.1`

Evidence:

- `src/tools/agent.nx:57-62` creates subagents with `model='glm-5.1'`.
- `/model` changes `Coder.model` in `src/commands.nx:113-124`, but subagents do not inherit it.

Impact:

- Parent and subagent can silently use different models after a runtime model switch.

Fix suggestion:

- Inherit `Coder.model` unless `subagent_type` explicitly specifies a model.

### M7. Auto-compact threshold is inconsistent with the advertised GLM context

Evidence:

- `src/harness.nx:69` defaults to `24000` estimated tokens.
- `ui-ink/src/index.tsx:24` uses `CTX_LIMIT = 200000`.
- `src/harness.nx:62-64` references CC's `contextWindow - 13000` model but then uses a much lower constant.

Impact:

- Long sessions may compact far earlier than necessary, losing useful context.

Fix suggestion:

- Derive threshold from runtime context window minus buffer, not a fixed 24k.

### M8. WebSearch remains a stub

Evidence:

- `src/tools/web.nx:60-69` returns a notice that no search backend is configured.

Impact:

- It is registered as one of the 14 tools, but not faithful to CC WebSearch behavior.

Fix suggestion:

- Either wire a backend or mark WebSearch as unavailable/deferred so the agent does not rely on it.

## LOW

### L1. Edit result snippets use zero-based line labels

Evidence:

- `src/tools/edit.nx:98-105` enumerates `_lines` with `_n` starting at 0.
- Test output showed `0qux bar`.

Impact:

- Editing succeeds, but output differs from CC-style line displays and can confuse users.

Fix suggestion:

- Render 1-based line numbers, preferably using the same `addLineNumbers` formatting as Read.

### L2. Read counts trailing newline as an extra empty line

Evidence:

- `src/tools/read.nx:131-134` uses `.read().split('\n')`.
- Test output for a three-line file ending in newline showed four numbered lines.

Impact:

- Usually harmless, but line counts in offset-shorter messages can differ from user expectations.

Fix suggestion:

- Confirm exact CC behavior; if CC does not count the terminal blank, use `splitlines()` with newline preservation rules.

### L3. NotebookEdit says absolute path is required but accepts relative paths

Evidence:

- Tool description at `src/tools/notebook.nx:17` says `notebook_path must be an absolute path`.
- Implementation resolves relative paths at `src/tools/notebook.nx:25-26`.

Impact:

- Minor contract mismatch.

Fix suggestion:

- Either enforce absolute paths or update the description.

### L4. Structured JSON tool events are improved, but duplicate registration is not guarded

Evidence:

- `src/main.nx:123-133` registers `_tool_pre` and `_tool_post` each time `run_json_events()` is entered.

Impact:

- In the current process shape this is usually once, but repeated entry in a long-lived embedding can duplicate events.

Fix suggestion:

- Add the same idempotency pattern used by `init_permissions()` at `src/permissions.nx:182-187`.

## Positive Notes

- JSON tool events no longer rely on stdout regex scraping: `src/main.nx:123-133` emits structured `tool_call` and `tool_result` via hooks.
- `python!` escaping looks clean after the previous fix pass; no obvious residual double-backslash runtime bug was found in `.nx` files.
- Core Read/Write/Edit/Notebook/Todo behavior is materially stronger than the Ink-only layer previously reviewed.
