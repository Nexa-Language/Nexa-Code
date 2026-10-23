# Architecture and JSON Lines protocol

```text
Ink / React
  Engine transport → validated events → reducer → components
        │ protocol v1, stdin/stdout
Python host
  explicit workspace → compile/load .nx → Session / Policy / services
        │ execute / continue_run / checkpoint approval
Nexa 2.4
  provider loop → RunState → tool dispatcher → SQLite / artifacts
```

`src/agents.nx` and `src/tools/*.nx` are the authoritative definitions. `loader.py` compiles them per changed source signature, binds handlers and computes a definition digest. A wheel bundles the same sources under `nexa_code/definitions/`.

`Session` organizes runs, workspace, immutable historical tool metadata, approvals, snapshots and accumulated usage. Nexa owns model requests, continuation, budgets and journal recovery. `Policy` supplies decisions for runtime-paused exact calls. `tool_services.py` owns application effects, managed processes and read-only research runs. `mcp_tools.py` delegates transport and connection cleanup to the MCP SDK.

The input thread remains available for cancellation and answers while one worker handles a task. Shutdown signals cancellation, drains process cleanup, waits for the worker and emits `session_end`. Cleanup failures carry an error/unclean status. The UI reports malformed events, signal/nonzero exits and startup deadlines; it escalates a stalled exit from protocol request to TERM/KILL.

## Protocol v1

Each request is one UTF-8 JSON object followed by newline, up to 2 MB. `version: 1`, nonempty `request_id` and known `type` are required. `nexa_code/protocol.py` validates requests.

| Type | Additional fields |
| --- | --- |
| `message` | `content` string |
| `command` | `name` string, e.g. `/status` |
| `approve` | `run_id`, `call_id`, `decision`: `allow_once`, `deny`, `allow_session` or `allow_rule` |
| `resume` | `session_id` |
| `resolve` | `run_id`, `call_id`, `content` observed evidence, `success` boolean |
| `set_mode` | `mode`; `confirmed: true` for bypass |
| `answer` | `call_id`, `content` |
| `cancel`, `exit` | No additional fields |

```json
{"version":1,"request_id":"user-1","type":"message","content":"Inspect the repository"}
```

Events include `version`, increasing `sequence`, `type`, and nullable `session_id`, `run_id`, `call_id`. `request_completed` carries the request ID. Key events are `ready`, `session_info`, `session_history`, `assistant_token`, `runtime_event`, `tool_call`, `tool_result`, `permission_request`, `run_state`, `done`, `artifact`, `question`, `error` and `session_end`. `ui-ink/src/protocol.ts` contains the discriminated event union and validates each envelope/payload.

Approval carries the actual argument object, cwd, policy provenance, mode and diff. Its answer must match the pending call. The host saves the decision before resuming through Nexa. A question is a separate user-input event tied to the active call ID.

`done.status` preserves completed, cancelled, timed_out, budget_exhausted or failed. Unknown effects remain `started` journal entries until reconciliation. UI errors and stop states remain visible; exact IDs match results even for repeated tool names.

## Verification seams

`FixtureProvider` implements the public provider interface and is injected only through explicit test code or `--fixture`. Tests run the real compiler, runtime, file tools and process transport with deterministic responses/delays/usage. The POSIX PTY harness drives built Ink. Wheel smoke imports an isolated installation and loads bundled definitions. CI uses an explicit runtime revision and lockfiles.
