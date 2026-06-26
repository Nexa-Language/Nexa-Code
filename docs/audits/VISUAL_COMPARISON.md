# Visual Comparison

Date: 2026-06-26

Scope: supplemental UX comparison for tool display, permission prompt, streaming output, and slash command UX.

Evidence basis:

- Real Nexa Ink PTY launch with `NEXA_PYTHON=D:\software\anaconda3\python.exe`.
- Real Claude Code `--print --output-format stream-json --include-partial-messages` run for a Read tool call.
- Source-backed rendering from CC reference components under `D:\code\nexa\refs\claude-code-ts`.
- Source-backed rendering from current `ui-ink/src/index.tsx` and `ui-ink/src/engine.ts`.

Important limitation:

- The real CC stream-json run was heavily polluted by local global hooks and stopped at the configured budget before `tool_result`. It did prove a live `Read` `tool_use`, but not the final result rendering.
- Nexa Ink in PTY rendered the first screen, but text input submission duplicated suffixes (`/help` -> `/helpelp`, `/exit` -> `/exitxit`), so slash-command visual behavior was captured as a bug rather than a clean scenario.

## 1. Tool Call Display

![Tool call comparison](.omx/artifacts/visual-tool-call-comparison.png)

Severity: MED.

Findings:

- CC side: live stream-json emitted `tool_use` with `name=Read` and the requested `file_path`; UI source renders tool usage through `AssistantToolUseMessage` / collapsed read-search components.
- Nexa side: `ToolView` renders raw JSON args and truncates result to 160 chars (`ui-ink/src/index.tsx:90-102`).
- Gap: Nexa does not have CC's tool-specific compact label/result grouping; long Read output becomes a flat truncated line.

Recommendation:

- Add tool-specific formatters for `Read`, `Edit`, `Bash`, `Grep`, and `Glob`.
- Preserve expandable/collapsed result groups instead of hard-truncating tool output.

## 2. Permission Prompt

![Permission comparison](.omx/artifacts/visual-permission-comparison.png)

Severity: HIGH.

Findings:

- CC permission UI uses tool-specific permission request components and richer choices such as allow once, always allow, and deny with guidance.
- Nexa `PermissionModal` is binary: `[y] allow` or `[n / esc] deny` (`ui-ink/src/index.tsx:125-151`).
- Nexa modal replaces the whole log view while permission is active (`ui-ink/src/index.tsx:211-219`), so the user loses surrounding conversation context.

Recommendation:

- Keep the message log visible behind/above the modal.
- Add permission options that map to persistent allow rules.
- Use tool-specific permission summaries for Write/Edit/Bash.

## 3. Streaming Output

![Streaming comparison](.omx/artifacts/visual-streaming-comparison.png)

Severity: MED.

Findings:

- CC stream-json emitted incremental `content_block_delta` / `input_json_delta` events.
- Nexa appends a newline for every `assistant_token` (`ui-ink/src/index.tsx:168`), then renders streaming text at `ui-ink/src/index.tsx:118-120`.
- Gap: token-level newline can turn normal prose into stair-step output and increase vertical jitter.

Recommendation:

- Append token content as-is, not `content + "\n"`.
- Render a cursor/spinner at the current end of the same flowing text line.

## 4. Slash Command UX

![Slash command comparison](.omx/artifacts/visual-slash-command-comparison.png)

Severity: HIGH.

Findings:

- CC has a slash-command overlay/picker path in `REPL.tsx` and `FullscreenLayout` rather than a plain text field.
- Nexa currently only has a `TextInput` placeholder (`ui-ink/src/index.tsx:228`).
- Live Nexa PTY evidence:
  - First screen rendered.
  - Status bar wrapped the cwd awkwardly (`...\u` on one line, `-ink` on the next).
  - `/help` was submitted as `/helpelp`.
  - `/exit` was submitted as `/exitxit`; I had to clean up with Ctrl+C.

Recommendation:

- Add a real slash-command suggestion overlay.
- Fix TextInput/PTY submission duplication before comparing command UX further.
- Constrain status bar segments so cwd truncates predictably instead of wrapping into the next line.

## 5. Cross-Cutting Visual Risks

Severity: MED.

- The Nexa status bar is not width-stable; long cwd/model text breaks layout.
- Raw JSON args are useful for debugging but visually noisy for users.
- Permission request protocol has `request_id`, which is good, but UI states are too modal and narrow.
- Real CC run showed global hooks can dominate visual/stream output; Nexa's own JSON mode still discards internal turn stderr at `src/main.nx:198` and `src/main.nx:207`, so the UI may fail silently in a different way.
