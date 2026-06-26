# Dynamic Interaction Gaps

Date: 2026-06-26
Scope: Compare real Claude Code dynamic UX evidence in `CC_REAL_UX_SPEC.md` against current implementation in `ui-ink/src/index.tsx`, `ui-ink/src/engine.ts`, `ui-ink/src/commands.ts`, `src/main.nx`, `src/commands.nx`, `src/permissions.nx`, and selected tool files. No code was modified.

## Implementation Baseline

- Ink UI status bar is a top bordered box with `cc`, model, cwd, context percent, and spinner: `ui-ink/src/index.tsx:71-87`.
- Tool rows use `⏺`, tool name, compact args, and folded `⎿` result lines: `ui-ink/src/index.tsx:89-115`.
- Message log prints user rows as `> text`, assistant rows as `● text`, and streaming with a block cursor: `ui-ink/src/index.tsx:118-130`.
- Slash overlay filters `COMMANDS` by prefix and displays up to 8 commands in a bordered panel: `ui-ink/src/index.tsx:135-151`, `ui-ink/src/commands.ts:8-28`.
- Permission modal is inline, round-bordered, y/n/esc only: `ui-ink/src/index.tsx:153-180`.
- UI handles JSON events from engine, including `assistant_token`, `tool_call`, `tool_result`, `permission_request`, `command_result`, `error`: `ui-ink/src/index.tsx:197-219`.
- Engine spawns Python/Nexa in JSON-events mode and parses stdout lines as JSON: `ui-ink/src/engine.ts:45-64`.
- JSON-events mode emits structured hooks for tool calls/results and permission requests: `src/main.nx:121-169`.
- Permission model implements mode + deny/allow/ask ordering and plan/bypass/auto behavior: `src/permissions.nx:137-180`.

## High Severity Gaps

### H1. Startup screen is missing the real CC welcome card

- CC ground truth: full-width orange `Claude Code vX` startup card with tips, recent activity, welcome message, model/account/org, cwd. V1 00:00.33; V2 01:12.67.
- Port behavior: initial log contains only `{ kind: "logo" }`, then renders a local `LogoBanner`; top status bar is separate. `ui-ink/src/index.tsx:186`, `ui-ink/src/index.tsx:267-280`.
- Gap: port likely starts in a generic app frame instead of the CC onboarding/state card. Missing version, tips, recent activity, account/org, and cwd-centered layout.
- Suggested fix: implement a startup card component fed by engine/session metadata; include recent sessions/activity and first-use tips.
- Layer: Ink UI plus engine metadata event.

### H2. Status/footer is structurally inverted and underpowered

- CC ground truth: footer/statusline lives at bottom and carries permission mode, Shift+Tab mode cycle, IDE integration, token count, edit shortcut, interrupt controls, elapsed time, token delta. V1 00:00.38; V2 01:12.73-01:14.57 and 01:58.64-02:00.40.
- Port behavior: status is top border box with model/cwd/ctx/spinner only. `ui-ink/src/index.tsx:71-87`, rendered before log at `ui-ink/src/index.tsx:267`.
- Gap: the highest-frequency CC information is missing or placed differently. Current ctx percent is local char estimate, not CC-like live token/cost/permission state.
- Suggested fix: move status/footer below input or split top title from bottom live footer; add permission mode, Shift+Tab cycling, token counters, IDE state, interrupt shortcut, elapsed time.
- Layer: Ink UI + engine event protocol + permission state.

### H3. Thinking state lacks CC's dynamic phase model

- CC ground truth: animated phase verbs (`Warping`, `Sussing`, `Baking`, etc.), interrupt hint, elapsed seconds/minutes, `ctrl+o to show thinking`, token deltas, tips, and `Next:` todo appear in the active work row. V1 00:00.46-00:02.57; V2 01:55.37-02:00.40.
- Port behavior: only a small dots spinner in status bar while `busy`; no phase verb, elapsed timer, token delta, thought toggle, or next todo. `ui-ink/src/index.tsx:72-85`, `ui-ink/src/index.tsx:190`, `ui-ink/src/index.tsx:257`.
- Gap: work does not feel alive or diagnosable during long tool/LLM turns.
- Suggested fix: add `turn_status` events with phase label, elapsed, token in/out, thought availability, next todo, and tip. Render as an active row above input.
- Layer: Engine protocol + Ink UI.

### H4. Tool lifecycle is too coarse for real CC

- CC ground truth: tool row lifecycle shows `Waiting...`, `Running...`, then result, with status updates in-place while thinking continues. V2 01:59.62-02:00.41; V1 00:01.26.
- Port behavior: `tool_call` creates a row with `result: null`; result appears only on `tool_result`. No status enum or in-place running/waiting state. `ui-ink/src/index.tsx:201-209`; `src/main.nx:135-139`.
- Gap: users cannot tell whether a tool is queued, running, blocked by permission, or completed. Long-running tools look static until result.
- Suggested fix: expand protocol to `tool_status` or include phase in `tool_call`/`tool_result`; update existing row by id, not "last pending tool".
- Layer: Engine protocol + tool registry hooks + Ink UI.

### H5. Permission UI is lower fidelity and missing mode cycling

- CC ground truth: recordings show bypass permission footer and Shift+Tab cycling. Official docs confirm allow/deny/ask permissions and managed policy surfaces. V1 00:00.33; V2 01:12.67; D3.
- Port behavior: engine starts with `permissionMode: "default"` and modal accepts only y/n/esc. `ui-ink/src/index.tsx:224`, `ui-ink/src/index.tsx:153-180`; mode logic exists in `src/permissions.nx:137-160`.
- Gap: no visible/current permission mode footer, no Shift+Tab cycle, no persistent allow/deny choices, no per-tool rich affordances. Exact CC modal still needs a non-bypass video, but port is already missing the observed bypass/mode footer.
- Suggested fix: expose permission mode state to UI, implement Shift+Tab cycling, render footer state, add richer options after verifying a non-bypass recording.
- Layer: Ink input handling + engine command/event + permissions.

### H6. Streaming protocol lacks semantic separation

- CC ground truth: assistant text, thought marker, tool status, tips, token counters, and todo next-step are separate visual lanes. V2 01:58.64-02:00.40.
- Port behavior: all non-tool stdout becomes `assistant_token`; stderr becomes `[stderr]` errors. `src/main.nx:171-184`, `src/main.nx:218-220`.
- Gap: token stream cannot distinguish assistant prose from thought/status/tips/todo. UI cannot reproduce CC dynamic feel without regex-like scraping later.
- Suggested fix: emit structured events: `assistant_delta`, `thinking_status`, `tip`, `todo_status`, `token_usage`, `tool_status`.
- Layer: Engine event protocol.

## Medium Severity Gaps

### M1. Slash command menu exists but is not CC-equivalent

- CC ground truth: official docs define a rich slash command system; actual popup needs targeted video validation. D2.
- Port behavior: prefix-only filtering, fixed 8 visible items, no command categories, no keyboard navigation handling visible for arrows/tab, and no custom/user/project command loading. `ui-ink/src/index.tsx:135-151`, `ui-ink/src/index.tsx:195`, `ui-ink/src/index.tsx:241-250`, `ui-ink/src/commands.ts:8-28`.
- Gap: enough for discovery, not enough for CC-style interactive command selection.
- Suggested fix: add selected-row navigation, descriptions, aliases, custom command sources, command execution previews.
- Layer: Ink UI + command registry.

### M2. Prompt editing/keyboard affordances are incomplete

- CC ground truth: footer advertises `ctrl+g`/`ctrl-g` edit in Vim; V2 shows ghost suggestion before typing. V1 00:00.38; V2 01:12.73.
- Port behavior: TextInput placeholder says `prompt or /command`; no ghost example, editor handoff, history browsing, or multiline editor mode. `ui-ink/src/index.tsx:279-280`.
- Gap: basic input works but misses daily-driver ergonomics.
- Suggested fix: add ghost suggestion, editor handoff, history navigation, multiline mode, and footer hints.
- Layer: Ink input UI.

### M3. Interrupt semantics do not match observed versions

- CC ground truth: V1 says `ctrl+c to interrupt`; V2 says `esc to interrupt`; long turns advertise the active key in status row. V1 00:00.46; V2 01:55.37.
- Port behavior: ESC sets busy false locally and appends `Interrupted`, but does not signal engine/process cancellation. `ui-ink/src/index.tsx:229-238`.
- Gap: UI can claim interruption while engine continues running; no version/context-specific key hint.
- Suggested fix: add cancellable turn id and engine cancel message; render current interrupt key in active status row.
- Layer: Engine protocol + Ink input.

### M4. Todo/progress display is hidden from UI

- CC ground truth: V1 shows `ctrl+t to show todos` and `Next: Create notebook...` during work at 00:02.57.
- Port behavior: `TodoWrite` exists and stores `_CCPORT_TODOS`, but UI has no todo event or panel. `src/tools/todo.nx:19-57`; `ui-ink/src/index.tsx:197-219`.
- Gap: agent planning/progress exists only as tool text, not as live UI.
- Suggested fix: emit todo updates and render compact next-step footer plus `ctrl+t` todo panel.
- Layer: Todo tool + engine protocol + Ink UI.

### M5. Long result rendering is folded but not interactive

- CC ground truth: tool output can stay compact under `⎿`, but external/panel flows can be opened/toggled (`[Enter] Toggle panel` in V2 Deciduous TUI at 07:20.69+).
- Port behavior: folds after 3 lines with static "... more lines" note. `ui-ink/src/index.tsx:93-111`.
- Gap: no keyboard expansion/collapse, copy, scroll, or full output view.
- Suggested fix: add row focus and expand/collapse; preserve raw output separately.
- Layer: Ink UI.

### M6. Command implementations often report text instead of launching CC-like UI

- CC ground truth: `/rewind`, `/resume`, `/agents`, `/mcp`, `/plugin`, `/share` are user-facing surfaces; docs describe interactive systems for commands/plugins/MCP/subagents. D2-D5.
- Port behavior: `/rewind` says CC has a picker and only supports numeric rewind; `/resume` says not ported; `/agents` is static text; `/mcp` manages JSON via text output; `/share` writes local markdown. `src/commands.nx:208-230`, `src/commands.nx:294-329`, `src/commands.nx:420-507`.
- Gap: command names exist, but interaction and persistence semantics are not equivalent.
- Suggested fix: prioritize real session picker/resume, agent manager, MCP manager, and share flow as UI panels.
- Layer: Command subsystem + session storage + Ink panels.

## Low Severity Gaps

### L1. Brand colors are close but not dynamic

- CC ground truth: orange varies slightly by version/terminal; cyan/blue separators and dim gray metadata are common. V1/V2.
- Port behavior: constants approximate orange/blue/dim colors. `ui-ink/src/index.tsx` color usage around status/tool/input.
- Gap: acceptable, but startup card/footer placement matters more than exact hex.
- Suggested fix: tune after layout parity.
- Layer: Ink UI styling.

### L2. Error display is too generic

- CC ground truth: recordings show shell errors before CC and inline terminal/TUI constraints; docs imply clear blocked messages for managed policy. V2 07:13.68; D3/D6.
- Port behavior: `error` event is rendered as `[error] ...` system text. `ui-ink/src/index.tsx:218`.
- Gap: errors lack category, action, retry, and source.
- Suggested fix: structured `error` with severity/source/action; render inline with dim detail.
- Layer: Engine protocol + Ink UI.

## Functional Gaps

1. Background tasks/subagents:
   - Observed CC/real use: V1 ends with "Both background agents have completed" at ~late session; D5 documents subagents/Task tool.
   - Port: `TaskCreate/TaskUpdate/TaskList/TaskGet` exist as in-memory globals only. `src/tools/task.nx:1-68`.
   - Gap: no concurrent execution, no background agent lifecycle events, no UI notification, no persistence.

2. Skills:
   - Observed CC/real use: V1 loads `Skill(notebooklm)` at 00:01.26 and then uses it.
   - Port: skill tool file exists, but current UI has no first-class skill load/unload display beyond generic tool rows.
   - Gap: no skill discovery/installed-skill panel, no skill provenance, no specialized load lifecycle.

3. Todo live panel:
   - Observed CC/real use: V1 shows `ctrl+t to show todos` and `Next:` at 00:02.57.
   - Port: `TodoWrite` stores todos but UI never surfaces them. `src/tools/todo.nx:53-57`; `ui-ink/src/index.tsx:197-219`.

4. SearchExtraTools/ExecuteExtraTool:
   - Observed/official: CC docs/settings describe extra tools, MCP, skills, agents, plugin-provided customizations. D3-D6.
   - Port: simple TF substring search and direct execute exist. `src/tools/search_extra.nx:1-71`.
   - Gap: no deferred tool marketplace, trust boundary, descriptions with parameters, progress UI, or MCP/plugin source identity.

5. `/plugin`:
   - Official docs/settings describe `/plugin` for plugin marketplaces and install/enable/disable/detail flows. D3.
   - Port: `/plugin` is absent from `ui-ink/src/commands.ts:8-28` and dispatch map `src/commands.nx:536-545`.

6. `/share`:
   - Official command surface includes sharing/export concepts. D2.
   - Port: `/share` writes a local `shared-session-*.md` file. `src/commands.nx:420-438`.
   - Gap: no hosted/shareable link flow or confirmation UI.

7. `/agents`:
   - Official docs describe custom subagents and agent configuration. D5.
   - Port: static list only. `src/commands.nx:304-313`.
   - Gap: no agent picker/editor/source distinction.

8. MCP runtime:
   - Official docs describe connecting external servers/resources/tools. D4.
   - Port: text/JSON management only, and `/mcp` overlaps `_mcp` and `_mcp_manage`. `src/commands.nx:315-329`, `src/commands.nx:470-507`, dispatch uses `_mcp_manage` at `src/commands.nx:545`.
   - Gap: no interactive server health, resource browser, or tool-selection UI.

9. File history / rewind / resume:
   - Observed CC/real use: resume hints appear during long sessions. V2 05:13.87 and 07:09.92.
   - Port: file snapshots exist in harness, `/undo` exists elsewhere, `/rewind` is numeric, `/resume` not ported. `src/commands.nx:208-230`, `src/harness.nx:99-179`.
   - Gap: no CC-like picker, persisted session list, or visual rewind timeline.

10. Custom statusline:
   - Official docs expose statusline customization. D7.
   - Port: hard-coded status bar. `ui-ink/src/index.tsx:71-87`.
   - Gap: no statusline command/config integration.

## Highest-Confidence Fix Direction

The next development pass should not chase screenshots. It should first extend the JSON event protocol so UI can render the real CC lanes: startup metadata, turn status, tool status by id, token usage, todo status, permission mode, and tips. Once these events exist, Ink can be shaped to the observed terminal rhythms without brittle stdout scraping.
