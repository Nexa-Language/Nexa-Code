# Test Execution Report

Date: 2026-06-26

Scope: headless engine/tool tests, slash commands, E2E flows, harness behavior, and JSON-events command smoke. No source code was modified.

## Environment

- Project: `D:\code\nexa\claude-code-port`
- Working Python used for engine import: `D:\software\anaconda3\python.exe`
- Default `python` on PATH is still unsafe for this project because it resolves to an environment with dependency/ABI issues.
- Direct `import src.main` is also unsafe: `src` resolves to `D:\code\nexa\nexa-lang\src`. Tests loaded `claude-code-port\src\main.py` by file path.
- Build check: `nexa build src/main.nx --harness=warn` passed with existing harness warnings only.

## Summary

Executed matrix:

- Main H-lane script: 60 checks, 57 pass, 3 fail.
- Additional WebFetch normal-path check: pass (`https://example.com`, HTTP 200).
- Additional JSON-events `/help` smoke: pass (`ready`, `command_result`, `session_end`).

Failures:

1. `Grep` invalid regex returns empty output.
2. E2E `Read -> Edit -> Bash verify` fails on Windows path.
3. Direct-call permission bypass: plan mode does not block direct `Bash(...)` invocation.

Important warning reproduced:

- Hook subprocess decoding emitted `UnicodeDecodeError: 'gbk' codec can't decode byte 0xff...`, even though the hook blocking test returned a blocking result.

## Tool Matrix

| Tool | Cases Executed | Result | Notes |
| --- | --- | --- | --- |
| Read | normal, empty file, binary reject, large gate, offset EOF | PASS | Normal output includes cat-style line numbers; trailing newline counted as blank line. |
| Write | create new file, existing file without Read | PASS | Existing file correctly rejects without prior Read. |
| Edit | replace, without Read, duplicate old_string, CRLF normalization | PASS | Edit works; result snippet line labels are zero-based. |
| Bash | `printf ok`, timeout, E2E cat Windows path | FAIL partial | Simple echo passes but includes WSL stderr noise; Windows path E2E fails. |
| Grep | content search, invalid regex | FAIL partial | Content search passes; invalid regex returns empty string. |
| Glob | matching pattern, no match | PASS | Sorted file list returned; no match returns `No files found`. |
| NotebookEdit | replace cell, missing notebook | PASS | Replace clears outputs. |
| TodoWrite | valid todo, multiple in_progress rejection | PASS | Enforces one in-progress item. |
| EnterPlanMode | enter plan mode | PASS | Mode set and instruction returned. |
| ExitPlanMode | exit plan mode | PASS | Mode returned to default. |
| VerifyPlan | false verification | PASS | Returns failed verification text. |
| WebFetch | invalid URL, `https://example.com` | PASS | Normal path returned HTTP 200 and page text. |
| WebSearch | query notice | PASS as stub | Tool is a configured stub, not a faithful search backend. |
| MCP tools | no config/resources/read/auth guidance | PASS no-config | Real MCP server behavior not covered; hang risk found in source review. |
| Agent | missing prompt | PASS partial | Full subagent run was not executed to avoid real model calls. |

## Command Matrix

21 slash command invocations were executed through `run_command`:

| Command | Result |
| --- | --- |
| `/help` | PASS |
| `/clear` | PASS |
| `/compact` | PASS (`No messages to compact`) |
| `/model` | PASS |
| `/model glm-test` | PASS |
| `/cost` | PASS partial (message count only) |
| `/status` | PASS |
| `/context` | PASS |
| `/config` | PASS |
| `/vim` | PASS |
| `/fast` | PASS |
| `/rewind 1` | PASS |
| `/resume` | PASS partial/stub |
| `/init` | PASS (`__AS_PROMPT__:` sentinel) |
| `/doctor` | PASS |
| `/add-dir <tmp>` | PASS |
| `/memory` | PASS |
| `/permissions` | PASS |
| `/agents` | PASS partial |
| `/mcp` | PASS |
| `/exit` | PASS (`__CC_EXIT__`) |

Notes:

- `/resume`, `/cost`, and `/agents` are honest partial ports, not full CC parity.
- JSON-events command smoke also passed:

```json
{"type": "ready", "model": "glm-5.1"}
{"type": "command_result", "name": "/help", "result": "Available commands:\n  /help - Show help ..."}
{"type": "session_end"}
```

## E2E Scenarios

### Read -> Edit -> Bash Verify

Result: FAIL.

Observed output excerpt:

```text
READ=     1->before
     2->
EDIT=The file D:\code\nexa\claude-code-port\.omx\nexa-final-hlane-1782438588\e2e.txt has been updated (1 occurrence):
     0after
     1
BASH=[stderr]
w\0s\0l\0: ... WSL ... localhost ...
cat: 'D:\code\nexa\claude-code-port\.omx\nexa-final-hlane-1782438588\e2e.txt': No such file or directory

[exit code: 1]
```

Root cause:

- `src/tools/bash.nx:38-43` picks a PATH `bash` that does not understand Windows `D:\...` paths.
- There is no Windows path translation layer before executing shell commands.

### Plan Mode Interception

Registry-path behavior: PASS in prior harness testing; mutating tools are blocked when executed through the tool registry.

Direct function call behavior: FAIL.

Observed output:

```text
should_not_run
[stderr]
w\0s\0l\0: ... WSL ... localhost ...
[exit code: 0]
```

Root cause:

- Permission enforcement is hook-based (`src/permissions.nx:162-187`).
- Direct imports/calls of generated functions bypass `PreToolUse`.

## Harness Tests

| Harness Area | Result | Evidence |
| --- | --- | --- |
| auto-compact trigger | PASS | `compacted (2000 tokens -> summary, kept last 4 msgs)` |
| session save + resume | PASS | saved and loaded `.omx\nexa-final-hlane-1782438588\session.jsonl` |
| hooks blocking | PASS with warning | returned `[hook exit 7 BLOCKED (exit 7)] stderr:` |
| hook decoding | FAIL risk | Python emitted GBK `UnicodeDecodeError` from subprocess reader thread |
| verify_output pass/fail | PASS | returned expected `PASS` and `FAIL` strings |
| run_turn_safe retry de-dupe | PASS | one transient failure retried; final messages contained one user entry |
| JSON-events command path | PASS | `/help` returned structured `command_result` |

## Raw Failure Cases

### Grep Invalid Regex

Expected: visible invalid-regex error.

Actual:

```text
<empty string>
```

Root cause:

- `src/tools/grep.nx:90-93` ignores `rg` non-zero return code and stderr when stdout is empty.

### Bash Windows Path

Expected: Bash can verify an edited file.

Actual:

```text
cat: 'D:\code\nexa\claude-code-port\.omx\nexa-final-hlane-1782438588\e2e.txt': No such file or directory
[exit code: 1]
```

Root cause:

- Shell dialect/path mismatch; see `CODE_REVIEW_NEXA_ENGINE.md` H1.

### Direct Permission Bypass

Expected: plan mode blocks Bash.

Actual:

```text
should_not_run
[exit code: 0]
```

Root cause:

- Test intentionally called `Bash(...)` directly instead of the registry. This exposes a headless/API bypass, not necessarily the normal agent path.

## Not Fully Covered

- Full `Agent` subagent run was not executed because it makes a real model call.
- Real MCP server behavior was not executed because no `.mcp.json` server was configured.
- Permission modal visual approval was not accepted or denied against a real Write tool call to avoid writing through the UI.
