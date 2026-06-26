# Claude Code Real Dynamic UX Spec

Date: 2026-06-26
Scope: Real Claude Code terminal interaction, observed from public terminal recordings plus official docs. This is a UX ground truth for `claude-code-port`; it is not based on local PTY screenshots.

## Evidence Set

| ID | Source | Type | Used For |
| --- | --- | --- | --- |
| V1 | [asciinema 767284](https://asciinema.org/a/767284) | Real terminal recording, Claude Code v2.1.4 | Startup card, permission-mode footer, prompt, thinking spinner, Skill tool lifecycle, todo hint, background agents |
| V2 | [asciinema 761574](https://asciinema.org/a/761574) | Real terminal recording, Claude Code v2.0.67 | Startup card, prompt typing, status/footer, Bash tool lifecycle, token counters, long-running turn, task/decision TUI handoff |
| D1 | [Interactive mode docs](https://docs.anthropic.com/en/docs/claude-code/interactive-mode) | Official docs | Keyboard and interactive behavior confirmation |
| D2 | [Slash commands docs](https://docs.anthropic.com/en/docs/claude-code/slash-commands) | Official docs | Slash command surface and command categories |
| D3 | [Settings docs](https://docs.anthropic.com/en/docs/claude-code/settings) | Official docs | Settings, permissions, plugin/skill/agent/mcp surfaces |
| D4 | [MCP docs](https://docs.anthropic.com/en/docs/claude-code/mcp) | Official docs | MCP configuration and runtime usage |
| D5 | [Subagents docs](https://docs.anthropic.com/en/docs/claude-code/sub-agents) | Official docs | Task/subagent behavior and `/agents` surface |
| D6 | [Hooks docs](https://docs.anthropic.com/en/docs/claude-code/hooks) | Official docs | Hook event model and blocking semantics |
| D7 | [Statusline docs](https://docs.anthropic.com/en/docs/claude-code/statusline) | Official docs | Custom statusline concept |

Timestamp note: asciinema v3 stores frame delays, so timestamps below are accumulated playback time. Permission prompts were not observed in V1/V2 because both recordings use bypass/skip-permissions mode; permission behavior is therefore documented as official-doc-backed rather than video-observed.

## A. Startup Flow

1. Claude Code enters an alternate-screen-like live terminal render almost immediately, then draws a full-width orange bordered welcome card. V1 shows `Claude Code v2.1.4` at 00:00.33; V2 shows `Claude Code v2.0.67` at 01:12.67.
2. The startup card is not a tiny banner. It is a two-column card: left side has a centered welcome message and Claude mark; right side has "Tips for getting started" and "Recent activity". V1 00:00.33 and V2 01:12.67.
3. The card includes account/model/context identity: model (`Opus 4.5`), plan (`Claude Max`), organization/account text, and cwd (`~/tmp` in V1, `~/code/fizzler` in V2). V1 00:00.33; V2 01:12.67.
4. The permission mode footer appears as part of the first usable screen: `bypass permissions on (shift+tab to cycle)` in orange/red, with token count in some layouts. V1 00:00.33; V2 01:12.67.
5. There is no separate long loading screen in these recordings. The transition is card -> live prompt in under roughly one second once the command is active. V1 00:00.33-00:00.38; V2 01:12.67-01:12.73.

## B. Input Interaction

1. The prompt is a single chevron-style input row. V1 uses `❯`; V2 uses `>`. The active cursor is a reverse-video block on the next editable character. V1 00:00.38; V2 01:13.45-01:14.57.
2. Empty input can show a ghost suggestion. V2 displays `Try "create a util logging.py that..."` at 01:12.73 before the user starts typing.
3. The input row is framed by long horizontal separators, not a boxed multiline text input. V2 repeatedly redraws the separators while the user types at 01:13.45-01:14.57.
4. The footer remains visible while typing. It may show permission mode, IDE integration (`/ide for Windsurf`), token count, and edit-in-editor hint (`ctrl+g` / `ctrl-g`). V1 00:00.38; V2 01:12.73-01:14.57.
5. Slash commands are an interactive command surface, not only text commands. Official slash-command docs identify the built-in/custom command model; videos did not capture a slash menu directly, so the dynamic menu shape should be verified in a future recording focused on `/`.

## C. Agent Response Flow

1. On Enter, the input stays visible but the active status line switches into a spinner/thinking row. V1 changes to `Warping... (ctrl+c to interrupt)` at 00:00.46; V2 changes to `Sussing... (esc to interrupt...)` at 01:55.37.
2. Spinner glyphs animate through multiple symbols (`✢`, `✳`, `✶`, `✻`, `*`, `·`, etc.) and the verb changes by phase/session (`Warping`, `Sussing`, `Baking`, `Mustering`, `Burrowing`). V1 00:00.46-00:00.70; V2 01:55.37-01:56.96 and 07:08.05-07:13.57.
3. Thought visibility is surfaced inline. V2 shows `Thought for 1s (ctrl+o to show thinking)` before/alongside the spinner at 01:58.64 and later.
4. Token direction/counter updates during long turns. V2 shows `↓ 101 tokens`, `↓ 152 tokens`, later `↑ 7.4k tokens` and `↓ 7.5k tokens`. V2 01:58.85-02:00.40 and 07:09.92-07:13.57.
5. Tips can be attached to the active work row with an `⎿ Tip:` prefix, e.g. resume hints or image paste hints. V2 02:36.81 and 05:13.87; V1 00:02.57.

## D. Tool Call Lifecycle

1. Tool calls use a compact two-symbol grammar:
   - `⏺ ToolName(args)` for the call
   - `⎿ Status/result` for lifecycle/result
2. Calls appear inline in the transcript while thinking continues. V1 shows `⏺ Skill(notebooklm)` with `⎿ Initializing...` then success at 00:01.26. V2 shows `⏺ Bash(deciduous init --claude)` with `⎿ Waiting...` then `⎿ Running...` at 01:59.62-01:59.66.
3. Long-running tools keep updating their status without creating a new card each frame. V2 keeps the same Bash call alive while token counts and spinner update at 01:59.62-02:00.40.
4. Tool output can be summarized inline under `⎿`. V2 shows a Bash result beginning `Initializing Deciduous for Claude Code...` at 02:00.41.
5. Multiple tools are presented in sequence with preserved rhythm: assistant line -> tool call -> status/result -> next assistant/tool. V2 task-building sequence spans repeated `Bash(deciduous add ...)` calls from 03:48.82 through 06:44.57.
6. Skills are first-class runtime tools. V1 shows `Skill(notebooklm)` loading at 00:01.26, then the agent uses that loaded skill to drive later workflow.

## E. Permission Interaction

1. V1/V2 run with bypass permissions, so they show the footer state instead of a prompt: `⏵⏵ bypass permissions on (shift+tab to cycle)`. V1 00:00.33; V2 01:12.67.
2. The permission mode is switchable from the footer with `shift+tab to cycle`. V1/V2 both show this affordance.
3. Official settings/permissions docs define allow/deny/ask permissions, managed settings, and permission-related tool naming. Therefore the permission prompt should be modeled as part of the same live message flow, preserving context while awaiting approval, with deny/allow/ask decisions grounded in tool name and arguments.
4. Because no public recording in this evidence set captured a non-bypass prompt, exact prompt copy/button layout remains lower-confidence and should be validated with a targeted recording.

## F. Status Bar / Footer

1. Claude Code's footer is more than a model/cwd display. It carries permission mode, Shift+Tab mode cycling, IDE integration, token count, editor shortcut, and active work controls. V1 00:00.38; V2 01:12.73-01:14.57.
2. During work, the active status row shows interrupt key, elapsed time, thought visibility shortcut, token counters, and sometimes next todo. V1 00:02.57; V2 01:58.64-02:00.40.
3. The footer can include contextual tips. V2 shows `Run claude --continue or claude --resume to resume a conversation` during a long run at 05:13.87 and 07:09.92.
4. The docs expose a statusline customization feature, so the footer/statusline should be treated as an extensible data surface, not hard-coded static text.

## G. Special Interactions

1. Interrupt key changed/varies by context/version: V1 frequently says `ctrl+c to interrupt`; V2 says `esc to interrupt` during turns. V1 00:00.46; V2 01:55.37.
2. `ctrl+o` opens/thinking visibility. V2 shows `ctrl+o to show thinking` at 01:58.64.
3. `ctrl+t` opens todos/progress. V1 shows `ctrl+t to show todos` plus `Next: Create notebook...` at 00:02.57.
4. `ctrl+g` / `ctrl-g` edits the prompt in Vim/editor. V1 00:00.38; V2 01:14+ footer.
5. Resume/continue is a first-class flow, shown as contextual tips during long sessions. V2 05:13.87 and 07:09.92.
6. External full-screen tools may require a real terminal; Claude detects and tells the user to run them directly. V2 says the Deciduous TUI needs a real terminal at 07:13.68.

## H. Visual Style

1. Background is pure black or near-black terminal. Primary brand orange is used for the startup border, spinner, tool bullet, and permission/bypass footer.
2. Secondary cyan/blue is used for input separators and some interactive hints, while gray/dim text carries tips, cwd/account, and low-priority metadata. V2 01:12.73-01:14.57.
3. The interface favors horizontal separators and inline rows over nested panels. The only large framed structure in the recordings is the startup card and external TUI.
4. Message separation comes from glyphs, indentation, color, and whitespace rhythm rather than heavy boxes around every message.
5. Tool and status glyphs are semantically meaningful: `⏺` for assistant/tool action, `⎿` for child status/result, `∴` for thought marker, animated star/dot glyphs for ongoing thinking.

## Open Evidence Gaps

1. Need a real recording of non-bypass permission prompts.
2. Need a focused recording of slash-command popup navigation (`/`, arrow keys, Tab/Enter behavior).
3. Need a focused recording of `/agents`, `/plugin`, `/share`, MCP tool selection, and custom statusline rendering.
