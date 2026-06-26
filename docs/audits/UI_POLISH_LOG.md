# UI Polish Log

Date: 2026-06-26

## Round 0 - Baseline

- Ran `nexa build src/main.nx`; first attempt failed on Windows console GBK encoding while printing an emoji, so it was retried with `PYTHONIOENCODING=utf-8` and completed successfully. Build emitted existing harness warnings about missing @tool return types; `.nx` files were not edited.
- Ran `cd ui-ink && bunx tsc --noEmit`; baseline passed before edits.
- Evidence reviewed:
  - Local real-terminal evidence: `docs/audits/CC_REAL_UX_SPEC.md`, asciinema 767284 and 761574 cached in `.omx/research`.
  - Official docs cached in `.omx/research/docs`: interactive mode, slash commands, settings, MCP, hooks, statusline, sub-agents.
  - Additional web search targets for this implementation pass: Claude Code permission prompts, slash popup/autocomplete, Bash/tool errors, and `old_string` edit failures.
- Live Claude Code comparison: `claude --version` reported `2.1.193 (Claude Code)`. A short `claude --dangerously-skip-permissions` launch showed the real startup card, What's new column, SessionStart hook block, bottom statusline with model/cwd/tokens/cost/time, bypass-permissions footer, `← for agents`, and `Press Ctrl-C again to exit`.

## Round 1-4 Combined UI Pass

Focus: permission/error UI, tool chain display, Markdown rendering, slash/footer/interrupt.

Changes implemented:

- Reworked `ui-ink/src/index.tsx` into clearer render-only components: startup card, message log, Markdown view, tool rows, permission dialog, error block, slash overlay, active row, and footer.
- Permission dialog now shows a CC-like "Claude wants to use TOOL" prompt, structured parameters, and `y` / `a` / `n` / `esc` options. `a` is represented as allow-once with a warning because persistent allow needs engine support.
- Tool rows now use `⏺` call rows and `⎿` child result/status rows, detect denied/error results, fold long output, and support pressing `x` to expand/fold the latest completed tool.
- Assistant text now goes through a lightweight Markdown renderer for headings, lists, blockquotes, inline code, fenced code blocks, and simple tables without adding dependencies.
- Slash command overlay now uses fuzzy/prefix matching, up/down selection, Tab completion, and includes additional slash commands supported by `src/commands.nx`.
- Footer now concentrates permission mode, model, cwd, token estimates, busy state, and Shift+Tab hint.
- Textual backup `ui/app.py` got matching permission copy/options and a red error panel.

Verification:

- `cd ui-ink && bunx tsc --noEmit` passed after the UI rewrite.
- `cd ui-ink && bun start` launched the Ink UI without crashing and rendered the startup card, loading input row, and footer.
- Live CC startup was run and exited with `/exit` after collecting the startup/statusline comparison.

Remaining gaps:

- Need true engine-side cancel for ESC; UI currently preserves partial output and labels local interruption.
- Need persistent permission "always allow" protocol support.
- Need id-based tool lifecycle (`Waiting` -> `Running` -> result) from the engine; UI currently infers from current events.
- Need real token/cost counts rather than UI-side estimates.
- Need additional live CC screenshots for non-bypass permissions and slash popup pixel parity.
- Startup parity still missing the real CC "What's new" feed, SessionStart hook block, `← for agents`, custom statusline rows, and double Ctrl-C exit prompt.

## Round 5 - Startup, Slash Popup, Statusline, Exit Hints

Focus: close gaps found by live Claude Code v2.1.193 startup/slash comparison.

New evidence:

- Live `claude --dangerously-skip-permissions` showed a trust/config warning before TUI when workspace trust had not been accepted.
- Real startup card persists after engine readiness and includes a `What's new` column, model/effort/billing, cwd, and a later `SessionStart:startup` block.
- Real footer/status area can be three rows: custom statusline with model/cwd/git/tokens/cost/time, mode row, bypass permission row with `← for agents`, and effort hint (`/effort`).
- Typing `/` opened an unboxed floating command list above the input. Rows show command name, source/plugin label such as `(oh-my-claudecode)` or `(superpowers)`, and dim wrapped descriptions.
- While a command was active, Esc displayed `Esc again to clear`; Ctrl-C during active command eventually exited and printed a `claude --resume <id>` hint.

Changes implemented:

- Startup card now stays visible after engine ready until the first real prompt/command submit, instead of disappearing on `ready`.
- Added a SessionStart-style context block under the startup card.
- Changed the startup right column from generic recent activity to a `What's new` feed.
- Footer is now multi-row and closer to the observed custom CC statusline: model/cwd/tokens/cost/time, mode row, permission row, `← for agents`, and `/effort` hint.
- Slash overlay is now an unboxed floating list with command name, source column, and description, matching the observed CC list more closely.
- Added idle Ctrl-C double-confirm intent in Ink (`Press Ctrl-C again to exit`) where raw input reaches the app.
- Added busy Esc two-step messaging: first Esc warns, second clears locally.

Verification:

- `cd ui-ink && bunx tsc --noEmit` passed.
- `cd ui-ink && bun start` rendered the updated startup card and multi-row statusline without crashing.

Remaining gaps:

- Real plugin/skill slash commands are not discoverable by UI without a command registry/event from the engine.
- Workspace trust warnings and config warning blocks are not surfaced through the engine JSON protocol.
- Active command interruption/resume IDs require engine/session support.
- Port statusline still estimates tokens/cost/time locally and does not know git branch or effort.

## Round 6 - Project Root and Git Statusline Alignment

Focus: remove the visible mismatch where the port shows `ui-ink/` as the working directory while real Claude Code presents the project root and git context.

New evidence:

- Live Claude Code v2.1.193 statusline showed project-oriented context rather than UI implementation cwd: project name/path, git branch with clean/dirty marker, model, token/cost/time fields, and permission/effort rows.
- The previous port startup/statusline used `process.cwd()`, so running from `ui-ink/` exposed the implementation folder instead of `D:\code\nexa\claude-code-port`.

Changes implemented:

- Added UI-only project metadata helpers in `ui-ink/src/index.tsx`.
- Startup card now displays the real project root derived from `import.meta.dir` (`claude-code-port`) rather than the `ui-ink` process cwd.
- Footer first row now mirrors the CC statusline shape more closely: model, project name, git branch, clean/dirty marker, token estimate, cost placeholder, and elapsed time.
- Footer permission row now keeps the shortened full project path as secondary context, closer to the observed CC custom statusline layout.
- Git branch and dirty state refresh every 10 seconds and fail closed; if git is unavailable, the UI simply omits the git segment instead of showing an error.
- After smoke testing at 80 columns, the first statusline row was compacted to avoid terminal wrapping: `model | project+git | tokens | elapsed`.

Verification:

- `cd ui-ink && bunx tsc --noEmit` passed.
- `cd ui-ink && bun start` smoke rendered the startup card and compact project/git statusline without crashing.

Remaining gaps:

- Token and cost remain estimates/placeholders until the engine emits real usage data.
- Effort/model source still needs engine/statusline protocol support for full parity.
- Exact CC workspace trust/config warning blocks still need engine events.
