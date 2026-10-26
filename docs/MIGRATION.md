# Migration to Nexa Code 3.0

Nexa Code `3.0.0.dev0` adds the explicit `--program` entry for [Open Programs](OPEN_PROGRAMS.md). Start a separate native database with `--state`; existing 2.4 conversations, checkpoint databases and approvals stay in their original paths. Native proposal grants are separately identified and never inherit legacy tool rules. The released Nexa 3.0 runtime contains the 2.4 compatibility compiler/runtime.

## Preserved 2.4 conversation workflow

The conversation entry uses the released Nexa v3.0.0 runtime in its 2.4 compatibility mode. The host loads `.nx` declarations through the public compiler, calls `NexaAgent.execute` for a task, and `continue_run` for the next settled user turn. Persisted state uses Nexa `RunState`, SQLite checkpoints, tool journals and artifacts. All 50 public tool names and 50 slash names/aliases remain discoverable; the [inventory](FEATURES.md) records behavior and limitations.

## Sessions and recovery

Each workspace stores `.nexa-code/sessions.sqlite3` plus `artifacts/` and `snapshots/`. Keep these together when backing up. `/resume` lists native sessions; `/resume <id>` restores the last parent checkpoint and conversation. Child research checkpoints contribute to usage and remain separate from the resumed parent. Display history shows up to 40 messages with 8,000 characters each; `/export` retains the full text transcript.

Completed, cancelled, timed-out, budget-exhausted and settled failed tasks can accept a new turn. Each turn has a new run ID and budget, with history/provider state linked through `parent_run_id`. Pending approval is checkpointed before a tool runs and survives process restart. Restoring a pending task preserves its original time budget; a long absence may exhaust it.

An interrupted external effect can have an unknown result. Inspect that effect first, then record observed evidence with `/resume resolve <call_id> success|failure <evidence>`. The runtime resumes the same task from that result. New turns and session switches stay blocked while a result remains unknown.

Changing model, provider or Agent/tool definitions starts a new session. `/model <name>` does this explicitly. A saved session with a different definition digest requires its matching version or reviewed transcript import.

## Legacy JSONL

`/resume /absolute/history.jsonl` validates a legacy transcript (maximum 10 MB), creates a new session and retains the original file. The import records its source path and format. Messages and tool records become quoted context for the current model/provider; old operations are never replayed. Incomplete tool pairings are retained as text with a migration notice. Invalid JSON/roles/content report the offending line and leave the original intact; inspect it in a text editor before retrying.

Legacy hooks and provider-private state are not imported into runtime checkpoints. `/history` and `/export` expose retained text. `/rewind <message-index>` forks reviewed history into a transcript session; `/compact <reviewed-summary>` creates a session from the supplied summary. Automatic model-based compaction was removed with the private provider loop.

## Permissions

| Input | Current behavior |
| --- | --- |
| `default` | Workspace-local read-only tools and matching explicit allow rules execute; other calls request approval. |
| `auto` | Uses explicit rules; unmatched calls still request approval. |
| `plan` | Read-only planning; mutations and shell execution stay denied even with an allow rule. |
| `bypass` | Requires `/permissions bypass confirm` in the current session; deny rules and runtime sandbox checks remain active. |
| `y` / allow once | Applies to the displayed run/call ID and arguments. |
| `s` / `p` | A second confirmation saves exact tool, workspace and argument equality for the session / persistent policy. |
| `/permissions remove <index>` | Revokes the zero-based displayed session or persistent rule. |

Rules persist in `.nexa-code/policy.json`. Native session switches and legacy imports clear session rules and exit bypass. The host reads deny rules from legacy `.claude/settings*.json` scopes; remove them at their source. Legacy broad allow entries appear as migration notices and require a scoped approval. `/add-dir` registers references; outside-workspace calls and global skills still require exact approval.

## Tools, processes and compatibility

- File tools retain read-before-write/staleness checks. Existing-file snapshots support `/undo`; a new file has no prior snapshot. Implicit auto-commits were removed. `/commit` is an explicit task subject to shell approval.
- `Bash`, `PowerShell`, REPL, platform commands and manual hooks use managed processes. Background jobs drain output continuously and enforce the shorter tool/run deadline. Each stream retains at most 128,000 characters with a truncation notice. `Monitor` reads/consumes results. Jobs stop with their host and are not restarted from checkpoints. POSIX children use process groups. Windows process-tree behavior needs platform validation.
- `Agent` creates a read-only Nexa run, shares the deny policy and contributes usage to the session. Previous subagent type labels use this research scope. Proposed mutations go through top-level approval.
- MCP uses the official SDK with owned connection lifetimes. Browser OAuth remains unavailable; `McpAuth` explains credential setup. Local stdio tools/resources and cleanup have offline coverage; remote HTTP needs integration validation.
- Cron tools retain a persisted schedule registry; scheduling is unavailable. `SendMessage` retains a local mailbox; distributed peers/ACP are unavailable. Tool results state these limits explicitly.
- `/hooks` manages named manual hooks. Review old hook commands before adding them; automatic lifecycle hooks are no longer installed through private runtime patches.
- `/fast` and `/effort` explain unsupported provider controls and direct users to `/model`. `/plugin` directs users to local skills, MCP and packages. `/login` runs configuration diagnostics.

`nexa-cc.sh/.bat`, `nexa-cc-engine.sh/.cmd` and `ui/app.py` retain launch paths using Node/uv. The engine wrapper accepts the legacy positional mode. An unversioned client adapter requires `--legacy-protocol`; legacy permission responses become allow-once or deny for the current pending call. New clients use v1. Earlier network-dependent scripts remain in `tests/legacy/` as historical references, outside default collection.
