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
