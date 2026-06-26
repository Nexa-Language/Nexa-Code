# Nexa Claude Code Port - UX, Test, and Improvement Audit

Date: 2026-06-26; evidence captured 2026-06-25

Scope: visual/interaction comparison against installed Claude Code `2.1.191`, test-system design, improvement planning, and code review for `D:\code\nexa\claude-code-port`.

Primary visual evidence:

- `D:\code\nexa\claude-code-port\.omx\artifacts\ux-comparison-initial.png`

## Verification Performed

| Check | Result |
|---|---|
| `nexa build src/main.nx --harness=warn` with UTF-8 stdout | PASS; only known `T-004` / `X-002` warnings |
| `bun run tsc --noEmit` in `ui-ink` | PASS |
| Installed Claude Code | `claude --version` = `2.1.191` |
| Nexa Ink initial PTY frame | Renders, then exits because child engine fails under default `python` |
| Claude Code initial PTY frame | Renders real welcome card/status/input/hook output |
| JSON event mode through `nexa run` | Emits `ready -> session_end`; compile logs share stdout with events |
| Direct `python src/main.py` | FAIL under default PATH: `ModuleNotFoundError: No module named 'pydantic'` |

Important environment finding: `where python` resolves first to `D:\msys64\mingw64\bin\python.exe`, while Nexa dependencies are under the Python environment used by `nexa`. `ui-ink/src/engine.ts` currently spawns plain `python`, so the Ink app can flash and quit with no visible error.

## UX Gap List

| Element | Claude Code behavior | Nexa port behavior | Gap | Severity | Fix layer |
|---|---|---|---|---|---|
| Startup reliability | Starts into stable TUI and surfaces startup warnings | Ink child process can fail before `ready`; stderr is swallowed | User sees blank/flash exit | HIGH | UI Ink |
| Startup screen | Rich welcome card with version, tips, whats-new, cwd, model/effort, session hook output | Small custom status bar + logo + tip | First impression is clearly not CC | MED | UI Ink |
| Status line | Dense bottom status: model, project, tokens/cost/time, permission/effort; truncates to width | Top bordered status wraps at 80 cols (`Claude` / `Code`, cwd split) | Layout breaks at common terminal widths | HIGH | UI Ink |
| Input state | Prompt remains integrated with footer/status and command affordances | `TextInput` only; no disabled state while busy | Can submit while turn/permission is active | HIGH | UI Ink + protocol |
| Permission protocol | Permission requests have IDs and resolve only matching responses (`pipePermissionRelay.ts`) | `_ask()` reads next stdin line, accepts any JSON without type/id | A prompt can be consumed as a deny response and lost | HIGH | Engine Nexa + UI Ink |
| Permission modal keys | Explicit option handling, escape/cancel semantics | Any key except lowercase `y` denies | Accidental denial on arrows/Enter/uppercase Y | MED | UI Ink |
| Permission visual context | Dialog appears inside scroll flow; messages remain visible and scroll is repinned | Permission state replaces message log with status+modal only | User loses context while approving | MED | UI Ink |
| Tool lifecycle display | Tool renderer knows resolved/queued/waiting states, progress, tags, full tool-specific summaries | Regex-scraped `tool_call`/`tool_result`; result truncated to 300 chars before UI | Fragile and lossy; long Read/Bash results cannot be inspected | HIGH | Engine Nexa + UI Ink |
| Tool result folding | CC has structured rendering, truncation, collapsed defaults, progress messages | UI truncates display to 160 chars, no expand/collapse | File/result content either too hidden or too noisy depending layer | HIGH | Both |
| Streaming/cancel | `AbortController`; ESC/Ctrl+C preserves partial text and interrupts active turn | No cancel event; `busy` has no abort path | ESC pause/abort missing | HIGH | Both |
| Slash command suggestions | Command suggestion overlay with fuzzy matching, descriptions, selected row | Placeholder says `/command`; no overlay/autocomplete | Obvious CC interaction missing | HIGH | UI Ink, command metadata from engine |
| Double ESC/history | CC has history/search/selector flows and escape handling | Not implemented in Ink | Missing learned CC shortcut | MED | UI Ink + session state |
| File content display | Tool renderers summarize/truncate with terminal-width awareness | Tool result is 300 chars in protocol and 160 chars in UI | Read large file is not CC-like and not inspectable | HIGH | Both |
| Color/glyph portability | CC switches `BLACK_CIRCLE` per platform and uses terminal-aware widths | Port hardcodes `⏺`; screenshot rendering showed tofu risk | Windows/Linux glyph mismatch risk | LOW | UI Ink |
| Error visibility | Fatal errors are user-facing | Non-JSON stdout ignored; stderr swallowed; exit closes app | Debuggability is poor | HIGH | UI Ink |
| JSON protocol purity | Event protocol should be machine-only | `nexa run` mixes build/run logs with JSON events | Automated UI/protocol tests brittle unless spawning built engine cleanly | MED | Runner/tooling |

## Source-Level UX Parity Notes

The visual gap is not just styling. Claude Code has a stateful terminal UX stack; the port currently has a small one-file Ink shell around a coarse event bridge.

| Area | Reference evidence | Port evidence | Assessment |
|---|---|---|---|
| Footer/status composition | `D:\code\nexa\refs\claude-code-ts\src\components\PromptInput\PromptInputFooter.tsx`, `PromptInputFooterLeftSide.tsx`, `StatusLine.tsx` | `D:\code\nexa\claude-code-port\ui-ink\src\index.tsx:69` | HIGH: CC composes model, mode, task/team, hints, suggestions, status-line commands, token/cost/time; port flattens model/cwd/ctx/busy into one bordered top bar. |
| Assistant text rendering | `D:\code\nexa\refs\claude-code-ts\src\components\messages\AssistantTextMessage.tsx`, `AssistantToolUseMessage.tsx:36` | `D:\code\nexa\claude-code-port\ui-ink\src\index.tsx:108`, `index.tsx:168` | HIGH: port appends a newline on every `assistant_token`, so streaming becomes line-based instead of inline. |
| Tool state rendering | `AssistantToolUseMessage.tsx:136`, `:140`, `:155`, `:181` | `D:\code\nexa\claude-code-port\ui-ink\src\index.tsx:90` | HIGH: CC has queued/resolved/waiting states, loader, user-facing labels and tags; port slices raw JSON/result strings. |
| Permission dialog | `D:\code\nexa\refs\claude-code-ts\src\components\permissions\PermissionDialog.tsx:31`, `PermissionPrompt.tsx`, tool-specific request components | `D:\code\nexa\claude-code-port\ui-ink\src\index.tsx:125` | HIGH: CC presents option lists, feedback/cancel behavior, and tool-specific variants; port is boolean `y/n`. |
| Input state machine | `D:\code\nexa\refs\claude-code-ts\src\components\PromptInput\PromptInput.tsx` imports `useArrowKeyHistory`, `useDoublePress`, `useHistorySearch`, `useTypeahead`; later state blocks around lines 2028/2045/2079/2377/2386 | `D:\code\nexa\claude-code-port\ui-ink\src\index.tsx:224` | HIGH: port uses basic `ink-text-input`; history/search/paste/cursor parking/selection flows are missing. |
| Slash autocomplete | `PromptInputFooterSuggestions.tsx:26`, `:173`; `utils\suggestions\commandSuggestions.ts`; `PromptInputHelpMenu.tsx` | `D:\code\nexa\claude-code-port\ui-ink\src\index.tsx:227` | HIGH: no overlay, ghost completion, fuzzy command catalog, or help panel in port. |
| Startup/logo | `LogoV2\AnimatedAsterisk.tsx`, `LogoV2.tsx`, `Clawd.tsx` | `D:\code\nexa\claude-code-port\ui-ink\src\index.tsx:40` | MED: port has static logo/mascot; CC has animated/conditional startup surfaces and notices. |
| Spinner/cursor | `Spinner\SpinnerGlyph.tsx`; `BaseTextInput.tsx` | `D:\code\nexa\claude-code-port\ui-ink\src\index.tsx:79`, `:119` | MED: port uses generic spinner and block cursor; CC has reduced-motion/stalled/error-aware spinner semantics. |
| ESC/cancel | `D:\code\nexa\refs\claude-code-ts\src\screens\REPL.tsx:1133`, `:2510`, `:2546`, `:2625` | `D:\code\nexa\claude-code-port\ui-ink\src\index.tsx:126`, `:147` | HIGH: CC uses AbortController and layered ESC guards; port has no active-turn abort path. |
| Width-aware truncation | `PromptInputFooterSuggestions.tsx:81`, `:95`, `:173`; `AssistantToolUseMessage.tsx:155` | `D:\code\nexa\claude-code-port\ui-ink\src\index.tsx:97`, `:101`, `:139` | MED: port uses fixed char slices; CC uses terminal-width-aware truncation/folding. |
| Theme/glyph portability | `D:\code\nexa\refs\claude-code-ts\src\constants\figures.ts:4` switches `BLACK_CIRCLE` by platform | `D:\code\nexa\claude-code-port\ui-ink\src\index.tsx:17` | LOW: port hardcodes glyphs and colors, increasing Windows/Linux alignment/tofu risk. |

## Test System Design

Use three lanes:

- `H` headless: import compiled `src/main.py` functions where possible, or run JSON-lines engine in a controlled Python environment.
- `P` PTY/interactive: real terminal runs for std REPL, Ink, and Textual.
- `V` visual: screenshot baselines for terminal UI states.

### P0 Test Harnesses

1. `tests/headless/`
   - Build once with UTF-8 environment.
   - Import or spawn engine using the same Python environment as `nexa`.
   - Assert deterministic tool, command, permission, and harness contracts.

2. `tests/protocol/`
   - Spawn JSON event engine without compile logs in stdout.
   - Assert event order and payload shape: `ready`, `assistant_token`, `tool_call`, `tool_result`, `permission_request`, `command_result`, `done`, `error`, `session_end`.
   - Include request IDs for permission once implemented.

3. `tests/pty/`
   - Use a PTY driver to run `bun start`, `python ui/app.py`, and the std REPL.
   - Drive `/help`, `/exit`, permission approve/deny, ESC, slash suggestions.

4. `tests/visual/`
   - Capture fixed-size terminal screenshots for: startup, slash overlay, tool call, long result folded, permission dialog, streaming cursor, error screen.
   - Keep a Claude Code reference capture and a Nexa capture per state.

### Tool Matrix

| Tool | Required cases | Lane |
|---|---|---|
| `Read` | normal text, offset/limit, empty, large gate, binary reject, image/pdf note, ENOENT | H |
| `Write` | new file, nested mkdir, overwrite after Read, stale/no-Read rejection | H |
| `Edit` | exact replace, replace_all, CRLF, duplicate reject, stale reject, create via empty old_string | H |
| `Bash` | stdout/stderr, exit code, timeout, truncation, unicode, background flag | H |
| `Grep` | content/files/count, context flags, case, glob/type, invalid regex, rg fallback | H |
| `Glob` | recursive match, mtime ordering, 100 cap, no match | H |
| `NotebookEdit` | replace/insert/delete, cell id/index, clear outputs, invalid notebook | H |
| `TodoWrite` | valid list, all-complete clear, invalid status, >1 in_progress | H |
| `Agent` | general child, explore read-only, child failure | H |
| `Plan` tools | enter/exit modes, verify success/failure | H |
| `MCP*` | mock stdio server, list/read/call/auth, spawn/no-response/errors | H |
| `WebFetch` | HTTPS, HTTP error, invalid scheme, timeout/truncation | H |
| `WebSearch` | backend missing and empty query | H |

### Command Matrix

All 20 slash commands should have headless tests via `run_command`: `/help`, `/clear`, `/compact`, `/model`, `/cost`, `/status`, `/context`, `/config`, `/vim`, `/fast`, `/rewind`, `/resume`, `/init`, `/doctor`, `/add-dir`, `/memory`, `/permissions`, `/agents`, `/mcp`, `/exit`/`/quit`.

Additional PTY/visual coverage: `/help`, `/model`, `/permissions`, `/mcp`, `/init`, `/exit`, slash overlay navigation, and command execution while busy.

### E2E Scenarios

| Scenario | Assertions | Lane |
|---|---|---|
| Read -> Edit -> Bash verify | final file content, tool event sequence, no stale write | H |
| Write -> Read -> Grep | file creation and discoverability | H |
| `/init` | sentinel route, `CLAUDE.md` creation path | H/P |
| Plan mode | read-only tools allowed; write/bash denied; exit restores mode | H |
| Permission modes | default/plan/bypass/auto across write/bash/web/mcp | H |
| MCP mock server | initialize + tools/list + tools/call + resources/list/read | H |
| Ink interaction | prompt -> tool event -> permission modal -> final reply | P/V |
| Long Read visual | result folded by default and expandable | P/V |
| ESC cancel | partial assistant preserved; engine abort observed | P/V |

## Improvement Plan

### P0 - Must Fix

| Work | Layer | Effort | Expected effect |
|---|---|---|---|
| Make Ink engine startup reliable: use the correct Python/Nexa runner and surface stderr/errors in UI | UI Ink | S | App stops flashing/blank-exiting; errors actionable |
| Disable prompt submission while busy or implement a request queue | UI Ink | S | Prevent lost prompts and stdin protocol corruption |
| Add permission request IDs and make `_ask()` accept only `permission_response` for the active ID | Engine Nexa + UI Ink | M | Safe permission flow; matches CC pipe relay semantics |
| Replace stdout regex scraping with structured tool lifecycle events from the runtime/tool hook boundary | Engine Nexa | M/L | Stable JSON bridge; full tool payloads; reliable UI |
| Add protocol smoke tests for startup, exit, permission, and long tool results | Tests | M | Prevent regressions in the bridge |

### P1 - Should Fix

| Work | Layer | Effort | Expected effect |
|---|---|---|---|
| Implement slash command suggestion overlay with descriptions and keyboard navigation | UI Ink | M | Major CC feel improvement |
| Add ESC cancel/abort path from UI to engine; preserve partial streaming text | Both | M/L | Matches core CC control behavior |
| Add width-aware status/footer layout; move dense session info to bottom and truncate cwd | UI Ink | S/M | Stops wrapping; closer to CC |
| Implement fold/expand for long tool results and file reads | Both | M | Solves file content crowding |
| Keep message log visible while permission dialog is open | UI Ink | S | Approval context preserved |
| Fix permission modal key handling (`y/Y`, `n/N`, `escape`, ignore others) | UI Ink | XS | Prevents accidental denials |

### P2 - Polish

| Work | Layer | Effort | Expected effect |
|---|---|---|---|
| More faithful welcome card with tips/whats-new/session info | UI Ink | M | Better first impression |
| Platform-aware glyphs (`⏺` vs `●`) and font fallback guidance | UI Ink | S | Fewer tofu/alignment issues |
| Visual regression baselines against Claude Code for startup/tool/permission states | Tests | M | Quantifies parity over time |
| Performance counters for render latency, token/cost/time status | UI Ink + harness | M | Better daily-use feedback |

## Code Review Findings

1. HIGH: `ui-ink/src/engine.ts` ignores malformed stdout, swallows stderr, and exits immediately on child exit. This hid the reproduced `pydantic` startup failure.

2. HIGH: `ui-ink/src/index.tsx` accepts input while busy; `src/main.nx` `_ask()` reads the same stdin stream as normal requests. A second prompt can become an implicit permission deny.

3. MEDIUM: `PermissionModal` treats any key except lowercase `y` as deny, despite UI copy saying only `n / esc` deny.

4. MEDIUM: JSON event protocol is not genuinely structured for tool activity; it scrapes human log lines and truncates tool results to 300 chars.

Boundary assessment: `ui-ink/` mostly respects the architecture boundary (render/process management only; no agent/tool execution logic), but the JSON bridge is too fragile to be the long-term contract.

## Upstream Nexa Patch Assessment

- P-RUN-1 streaming/tool event support: high value. The port currently scrapes stdout because native structured events are missing or not exposed.
- P-RUN-2 hooks: high value. Permission/UI integration depends on reliable PreToolUse/PostToolUse boundaries.
- P-CMP-4 `python!` escaping lint: high value. `PORT_TRACE.md` documents repeated regressions around `\n`, regex, and JSON delimiters; tests should pin this.

## Recommended Next Step

Implement P0 in this order:

1. Fix Ink startup/error visibility.
2. Make stdin single-flight safe and permission responses request-scoped.
3. Add protocol smoke tests.
4. Replace tool stdout scraping with direct structured events.
5. Only then iterate on visual parity features like slash overlay and folded tool results.
