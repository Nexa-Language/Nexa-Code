# Improvement Roadmap V3

Date: 2026-06-26
Basis: `CC_REAL_UX_SPEC.md` and `DYNAMIC_INTERACTION_GAPS.md`. Priority is ranked by user-perceived impact x implementation difficulty. This is a planning document only; no code was changed.

## P0: Needed For Daily-Driver Feel

| Priority | Change | CC Evidence | Layer | Rough Work |
| --- | --- | --- | --- | --- |
| P0.1 | Add structured turn status events: phase verb, spinner state, elapsed time, interrupt key, token in/out delta, optional tip, optional next todo | V1 00:00.46-00:02.57; V2 01:55.37-02:00.40 | `src/main.nx` JSON protocol, agent/harness callbacks, `ui-ink/src/index.tsx` active row | 2-4 days |
| P0.2 | Replace top static status with CC-like bottom footer/statusline: permission mode, Shift+Tab cycle, token count, IDE/editor hints, interrupt hint | V1 00:00.38; V2 01:12.73-01:14.57 | Ink UI + permission mode state + statusline config | 2-3 days |
| P0.3 | Make tool lifecycle id-based and stateful: `Waiting`, `Running`, `Completed`, `Denied`, `Errored`; update the same row in place | V2 01:59.62-02:00.41; V1 00:01.26 | tool hooks, JSON events, Ink tool rows | 2-4 days |
| P0.4 | Implement real cancellation instead of UI-only ESC: send cancel to engine/turn id, stop streaming/tool wait, report interrupted state | V1 uses `ctrl+c`; V2 uses `esc`; both show active interrupt affordance | Engine process/turn control + Ink input | 2-5 days |
| P0.5 | Surface permission mode and Shift+Tab cycling; keep current inline modal but add visible mode state and mode-changing behavior | V1/V2 bypass footer; D3 permission docs | Ink input/footer + `set_permission_mode` bridge | 1-2 days |
| P0.6 | Add startup metadata card with version, tips, recent activity, model/account/org/cwd | V1 00:00.33; V2 01:12.67 | Ink startup component + engine/session metadata | 2-3 days |

## P1: Makes The Port Feel Like Claude Code

| Priority | Change | CC Evidence | Layer | Rough Work |
| --- | --- | --- | --- | --- |
| P1.1 | Todo/progress lane: emit todo updates, show `Next:` in active row, add `ctrl+t` todo panel | V1 00:02.57 | `TodoWrite`, JSON protocol, Ink panel | 2-3 days |
| P1.2 | Rich slash command overlay: keyboard navigation, categories, aliases, custom commands, command descriptions, completion semantics | D2; video gap still needs focused `/` recording | `ui-ink/src/commands.ts`, command registry, Ink overlay | 3-5 days |
| P1.3 | Session resume and rewind pickers instead of text placeholders/numeric-only rewind | V2 resume/continue tip 05:13.87 and 07:09.92 | session storage, `/resume`, `/rewind`, Ink picker | 4-7 days |
| P1.4 | Prompt editor ergonomics: ghost suggestion, history navigation, multiline/editor handoff (`ctrl+g`) | V1 00:00.38; V2 01:12.73-01:14.57 | Ink input component | 2-4 days |
| P1.5 | Permission prompt parity pass after acquiring non-bypass recording: richer options, persistent allow/deny, precise copy/layout | D3 plus observed bypass footer | permissions + Ink modal | 2-4 days after evidence |
| P1.6 | Skill lifecycle UI: show skill load, source, available commands/tools, success/failure as first-class rows | V1 `Skill(notebooklm)` at 00:01.26 | skill tool + JSON events + Ink rows | 2-3 days |
| P1.7 | MCP manager/resource/tool UI instead of only text JSON management | D4; command code at `src/commands.nx:470-507` | command subsystem + Ink panels + MCP tools | 4-7 days |

## P2: Polish And Completeness

| Priority | Change | CC Evidence | Layer | Rough Work |
| --- | --- | --- | --- | --- |
| P2.1 | Interactive tool-result expansion/copy/scroll for folded outputs | V2 external panel/toggle pattern at 07:20.69+ | Ink focused rows/panels | 2-3 days |
| P2.2 | Custom statusline support from config/command | D7 | statusline config loader + Ink footer | 2-5 days |
| P2.3 | `/agents` manager/editor with source/provenance and built-in/custom agents | D5 | command subsystem + Ink picker | 3-6 days |
| P2.4 | `/plugin` marketplace flow: list/install/enable/disable/details | D3 plugin management docs | command subsystem + plugin registry + Ink panels | 1-2 weeks |
| P2.5 | Hosted/share-style `/share` or clear local/share distinction with confirmation UI | D2; current local export at `src/commands.nx:420-438` | share/export command + Ink confirmation | 2-5 days |
| P2.6 | Error taxonomy: distinguish engine stderr, permission denial, hook block, tool failure, unsupported terminal, user cancel | V2 real-terminal warning at 07:13.68; D6 hooks | JSON error schema + UI renderers | 2-4 days |
| P2.7 | Color/spacing final tuning against real terminal recordings after event parity exists | V1/V2 style | Ink styling | 1-2 days |

## Recommended Sequence

1. Protocol first: add event types for `turn_status`, `tool_status`, `token_usage`, `todo_status`, `permission_mode`, and `tip`.
2. Footer and active row second: move the live state to a bottom CC-like statusline and render the dynamic turn row.
3. Tool lifecycle third: id-based in-place updates for `Waiting` -> `Running` -> result.
4. Startup card fourth: metadata-rich first screen.
5. Command/panel work fifth: todos, slash overlay, resume/rewind, MCP, agents, plugins.

## Acceptance Checks For The Next Dev Round

- A long Bash/tool run visibly changes from waiting to running to result without adding duplicate tool cards.
- During a long response, the UI shows elapsed time and token deltas, not just a generic spinner.
- The footer always shows current permission mode and Shift+Tab changes it.
- A TodoWrite call updates a visible `Next:` line and `ctrl+t` panel.
- `/resume` and `/rewind` no longer merely explain that CC has a picker; they open an actual picker or clearly scope a minimum viable picker.
- Startup within a real terminal shows the same information density as V1/V2: version, tips, recent activity, model/account/org, cwd, and permission mode.

## Evidence Gaps To Close Before Pixel Polish

1. Capture a non-bypass Claude Code permission prompt in a real terminal.
2. Capture slash-command popup navigation from typing `/` through arrow/Tab/Enter.
3. Capture `/agents`, `/plugin`, `/share`, MCP resource/tool usage, and custom statusline rendering.

Until those are captured, avoid hard-coding exact prompt/menu copy; implement the protocol and layout capacity first.
