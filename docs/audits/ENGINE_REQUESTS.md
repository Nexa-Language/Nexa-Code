# Engine Requests From UI Polish

Date: 2026-06-26

The UI layer did not modify `src/*.nx` or `src/tools/*.nx`. These requests describe protocol gaps that prevent closer Claude Code parity.

## P0 - Cancellation

- Add a JSON input event such as `{ "type": "cancel", "turn_id": "..." }`.
- Emit a terminal event such as `{ "type": "turn_status", "phase": "interrupted" }`.
- Current UI behavior can only stop local busy/stream rendering; the engine may continue running.

## P0 - Persistent Permission Choices

- Support permission responses beyond boolean allow/deny, e.g. `{ "type": "permission_response", "request_id": 1, "decision": "allow_once|deny|allow_session|allow_rule" }`.
- Return the resulting permission mode/rule update so the footer can show the durable state.
- Current UI maps `a` to allow-once and warns that persistence is missing.

## P0 - Tool IDs And Status Updates

- Include a stable `tool_call_id` on `tool_call` and `tool_result`.
- Emit intermediate status, e.g. `tool_status: waiting|running|completed|failed`.
- Current UI updates the latest pending tool row, which is fragile for concurrent/background tools.

## P1 - Usage And Statusline Data

- Emit real token in/out, cost, current model, permission mode, cwd/worktree, and optional statusline text.
- Current UI estimates tokens from character counts and hard-codes statusline layout.

## P1 - Todo / Background Task Events

- Emit structured todo/task events from TodoWrite and TaskCreate/Update/List.
- Needed for CC-like `ctrl+t to show todos`, `Next: ...`, and "background agents completed" notifications.

## P1 - Startup Hook / Statusline Blocks

- Emit or expose startup hook output as a first-class UI event rather than assistant text.
- Include recent sessions/activity and "What's new" data if available.
- Real Claude Code v2.1.193 displayed a `SessionStart:startup` block, "No previous sessions found", an observations URL, a model/cwd/token/cost/time statusline, and `← for agents`.

## P2 - Exit Gesture

- Provide a UI/engine contract for idle Ctrl-C behavior: first Ctrl-C shows "Press Ctrl-C again to exit", second exits.
- Ink currently uses `/exit`/process interrupt for smoke testing and does not model the two-step idle exit confirmation.

## P1 - Slash Command Registry

- Expose a structured command registry event containing command name, source/plugin label, description, aliases, and availability.
- Real Claude Code slash popup includes plugin/skill commands such as `/oh-my-claudecode:ralplan`, source labels like `(superpowers)`, and wrapped descriptions.
- Current UI can only list the static commands in `ui-ink/src/commands.ts`.

## P1 - Trust And Config Warnings

- Surface workspace trust/config warnings as structured startup events before the prompt.
- Real Claude Code printed ignored permission entries and unknown permission ask rules before drawing the TUI.
- Current UI has no way to know these warnings unless the engine forwards them.

## P2 - Active Interrupt / Resume IDs

- When a running command/turn is interrupted, emit whether the turn was cancelled, cleared, or resumable.
- Include a resume id when available, matching real Claude Code's `claude --resume <id>` hint.
