// index.tsx - Ink/React UI polish loop.
// UI-only boundary: subprocess bridge + rendering/input only. No agent loop, tool
// execution, permission decision, or LLM calls live here.
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { render, Box, Text, useApp, useInput, useStdin } from "ink";
import TextInput from "ink-text-input";
import Spinner from "ink-spinner";
import * as path from "node:path";
import { execSync } from "node:child_process";
import { Engine, EngineEvent } from "./engine.ts";
import { COMMANDS } from "./commands.ts";
import type { Command } from "./commands.ts";

const ORANGE = "#D77757";
const ORANGE_2 = "#ff9966";
const BLUE = "#8fb7ff";
const VIOLET = "#b1b9ff";
const GREY = "#999999";
const DIM = "#8a8275";
const RED = "#ff6b6b";
const GREEN = "#9ece6a";
const WARN = "#f4bf75";
const BLACK_CIRCLE = "⏺";
const HOOK = "⎿";
const TEARDROP = "✻";
const META_DIR = (import.meta as any).dir as string;
const PROJECT_ROOT = path.resolve(META_DIR, "..", "..");
const HOME_DIR = process.env.HOME || process.env.USERPROFILE || "";
const PROJECT_NAME = path.basename(PROJECT_ROOT);
const PROJECT_DISPLAY = PROJECT_ROOT.replace(HOME_DIR, "~");

type ToolStatus = "waiting" | "running" | "resolved" | "error" | "denied";
type Entry =
  | { kind: "user"; text: string }
  | { kind: "assistant"; text: string }
  | { kind: "tool"; id: number; name: string; args: unknown; result: string | null; status: ToolStatus; expanded: boolean }
  | { kind: "system"; text: string; tone?: "info" | "success" | "warning" }
  | { kind: "error"; message: string; source: "engine" | "tool" | "ui" };

const MODES = ["default", "plan", "bypass", "auto"] as const;
type PermMode = typeof MODES[number];
const MODE_COLORS: Record<PermMode, string> = {
  default: GREY,
  plan: BLUE,
  bypass: RED,
  auto: ORANGE_2,
};

function terminalWidth(): number {
  return process.stdout.columns || 100;
}

function truncateMiddle(s: string, maxLen: number): string {
  if (s.length <= maxLen) return s;
  const keep = Math.max(1, maxLen - 3);
  return s.slice(0, Math.ceil(keep * 0.5)) + "..." + s.slice(-Math.floor(keep * 0.5));
}

function estimateTokens(text: string): number {
  return Math.max(0, Math.ceil(text.length / 4));
}

function stringifyValue(value: unknown, maxLen = 180): string {
  let raw: string;
  if (typeof value === "string") raw = value;
  else {
    try {
      raw = JSON.stringify(value);
    } catch {
      raw = String(value);
    }
  }
  return raw.length > maxLen ? raw.slice(0, maxLen - 1) + "…" : raw;
}

function argEntries(args: unknown): [string, string][] {
  let obj = args;
  if (typeof args === "string") {
    try {
      obj = JSON.parse(args);
    } catch {
      return [["args", args]];
    }
  }
  if (obj && typeof obj === "object" && !Array.isArray(obj)) {
    return Object.entries(obj as Record<string, unknown>).map(([k, v]) => [k, stringifyValue(v, 240)]);
  }
  return [["args", stringifyValue(obj, 240)]];
}

function isProblemText(text: string): boolean {
  return /\b(error|failed|denied|not found|traceback|exception|exit code|old_string|permission)\b/i.test(text);
}

function statusFromResult(result: string): ToolStatus {
  if (/\bpermission\b.*\bdenied\b/i.test(result)) return "denied";
  if (isProblemText(result)) return "error";
  return "resolved";
}

function commandScore(input: string, command: Command): number {
  const q = input.toLowerCase();
  const name = command.name.toLowerCase();
  const haystack = `${command.name} ${command.desc}`.toLowerCase();
  if (!q || q === "/") return 100 - name.length;
  if (name === q) return 1000;
  if (name.startsWith(q)) return 700 - name.length;
  let qi = 0;
  for (const ch of haystack) {
    if (ch === q[qi]) qi += 1;
    if (qi >= q.length) break;
  }
  return qi === q.length ? 300 - haystack.length : -1;
}

function commandMatches(input: string): Command[] {
  return COMMANDS
    .map((command) => ({ command, score: commandScore(input, command) }))
    .filter((x) => x.score >= 0)
    .sort((a, b) => b.score - a.score || a.command.name.localeCompare(b.command.name))
    .map((x) => x.command)
    .slice(0, 9);
}

function formatDuration(totalSeconds: number): string {
  if (totalSeconds < 60) return `${totalSeconds}s`;
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}m${seconds}s`;
}

function readGitBranch(): string {
  try {
    return execSync("git rev-parse --abbrev-ref HEAD", {
      cwd: PROJECT_ROOT,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
    }).trim();
  } catch {
    return "";
  }
}

function readGitDirty(): boolean {
  try {
    return execSync("git status --porcelain", {
      cwd: PROJECT_ROOT,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
    }).trim().length > 0;
  } catch {
    return false;
  }
}

type InlinePart = { kind: "plain" | "code" | "bold" | "italic"; text: string };

function inlineParts(text: string): InlinePart[] {
  const parts: InlinePart[] = [];
  let i = 0;
  const pushPlain = (value: string) => {
    if (value) parts.push({ kind: "plain", text: value });
  };

  while (i < text.length) {
    if (text[i] === "`") {
      const end = text.indexOf("`", i + 1);
      if (end > i + 1) {
        parts.push({ kind: "code", text: text.slice(i + 1, end) });
        i = end + 1;
        continue;
      }
    }
    if (text.startsWith("**", i)) {
      const end = text.indexOf("**", i + 2);
      if (end > i + 2) {
        parts.push({ kind: "bold", text: text.slice(i + 2, end) });
        i = end + 2;
        continue;
      }
    }
    if (text[i] === "*") {
      const end = text.indexOf("*", i + 1);
      if (end > i + 1) {
        parts.push({ kind: "italic", text: text.slice(i + 1, end) });
        i = end + 1;
        continue;
      }
    }
    const next = ["`", "*"].map((ch) => text.indexOf(ch, i + 1)).filter((idx) => idx >= 0).sort((a, b) => a - b)[0];
    const end = next ?? text.length;
    pushPlain(text.slice(i, end));
    i = end;
  }
  return parts;
}

function InlineText({ text, color }: { text: string; color?: string }) {
  const pieces = inlineParts(text);
  return (
    <Text color={color}>
      {pieces.map((piece, idx) => {
        if (piece.kind === "code") {
          return <Text key={idx} color={BLUE}>{piece.text}</Text>;
        }
        if (piece.kind === "bold") {
          return <Text key={idx} bold>{piece.text}</Text>;
        }
        if (piece.kind === "italic") {
          return <Text key={idx} italic>{piece.text}</Text>;
        }
        return <Text key={idx}>{piece.text}</Text>;
      })}
    </Text>
  );
}

function isDiffLanguage(lang: string): boolean {
  return /^(diff|patch|udiff)$/i.test(lang.trim());
}

function codeLineColor(lang: string, line: string): string {
  if (!isDiffLanguage(lang)) return VIOLET;
  if (/^@@/.test(line)) return BLUE;
  if (/^(diff --git|index |--- |\+\+\+ )/.test(line)) return DIM;
  if (/^\+/.test(line)) return GREEN;
  if (/^-/.test(line)) return RED;
  return DIM;
}

function markdownTableCells(line: string): string[] | null {
  const trimmed = line.trim();
  if (!trimmed.startsWith("|") || !trimmed.includes("|", 1)) return null;
  const cells = trimmed.split("|").slice(1, trimmed.endsWith("|") ? -1 : undefined).map((cell) => cell.trim());
  return cells.length > 1 ? cells : null;
}

function isMarkdownTableSeparator(cells: string[]): boolean {
  return cells.every((cell) => /^:?-{3,}:?$/.test(cell.replace(/\s/g, "")));
}

function MarkdownTable({ rows }: { rows: string[][] }) {
  const widths = rows.reduce<number[]>((acc, row) => {
    row.forEach((cell, idx) => {
      acc[idx] = Math.max(acc[idx] || 0, cell.length);
    });
    return acc;
  }, []);
  return (
    <Box flexDirection="column">
      {rows.map((row, rowIdx) => (
        <Text key={rowIdx}>
          {row.map((cell, cellIdx) => (
            <React.Fragment key={cellIdx}>
              <Text color={rowIdx === 0 ? BLUE : undefined}>{cell.padEnd(widths[cellIdx] || cell.length)}</Text>
              {cellIdx < row.length - 1 && <Text color={DIM}> │ </Text>}
            </React.Fragment>
          ))}
        </Text>
      ))}
    </Box>
  );
}

function MarkdownView({ text }: { text: string }) {
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  const nodes: React.ReactNode[] = [];
  let inCode = false;
  let codeLang = "";
  let codeLines: string[] = [];

  const flushCode = () => {
    if (!inCode && codeLines.length === 0) return;
    nodes.push(
      <Box key={`code-${nodes.length}`} flexDirection="column" borderStyle="single" borderColor={DIM} paddingX={1} marginY={0}>
        {codeLang && <Text color={DIM}>{codeLang}</Text>}
        {codeLines.length === 0 ? <Text> </Text> : codeLines.map((line, i) => (
          <Text key={i} color={codeLineColor(codeLang, line)}>{line || " "}</Text>
        ))}
      </Box>
    );
    inCode = false;
    codeLang = "";
    codeLines = [];
  };

  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];
    const fence = line.match(/^```(.*)$/);
    if (fence) {
      if (inCode) flushCode();
      else {
        inCode = true;
        codeLang = fence[1].trim();
        codeLines = [];
      }
      continue;
    }
    if (inCode) {
      codeLines.push(line);
      continue;
    }
    if (!line.trim()) {
      nodes.push(<Text key={`blank-${i}`}> </Text>);
      continue;
    }
    const heading = line.match(/^(#{1,4})\s+(.+)$/);
    if (heading) {
      nodes.push(<Text key={i} color={ORANGE} bold>{heading[2]}</Text>);
      continue;
    }
    const quote = line.match(/^>\s?(.*)$/);
    if (quote) {
      nodes.push(<Text key={i} color={DIM}>│ <InlineText text={quote[1]} /></Text>);
      continue;
    }
    const firstTableCells = markdownTableCells(line);
    if (firstTableCells) {
      const tableRows: string[][] = [];
      let j = i;
      while (j < lines.length) {
        const cells = markdownTableCells(lines[j]);
        if (!cells) break;
        if (!isMarkdownTableSeparator(cells)) tableRows.push(cells);
        j += 1;
      }
      if (tableRows.length > 1) {
        nodes.push(<MarkdownTable key={`table-${i}`} rows={tableRows} />);
        i = j - 1;
        continue;
      }
    }
    if (line.includes("|") && line.trim().startsWith("|")) {
      const cells = line.split("|").slice(1, -1).map((c) => c.trim());
      if (cells.length > 1) {
        nodes.push(<Text key={i} color={i > 0 && /^[-:\s|]+$/.test(line) ? DIM : BLUE}>{cells.join("  │  ")}</Text>);
        continue;
      }
    }
    const bullet = line.match(/^(\s*)([-*]|\d+\.)\s+(.+)$/);
    if (bullet) {
      const indent = Math.min(6, Math.floor(bullet[1].length / 2) * 2);
      nodes.push(
        <Text key={i}>
          <Text dimColor>{" ".repeat(indent)}</Text>
          <Text color={DIM}>{bullet[2]} </Text>
          <InlineText text={bullet[3]} />
        </Text>
      );
      continue;
    }
    nodes.push(<InlineText key={i} text={line} />);
  }
  if (inCode) flushCode();
  return <Box flexDirection="column">{nodes}</Box>;
}

function StartupCard({ model, cwd }: { model: string; cwd: string }) {
  const width = terminalWidth();
  const leftWidth = Math.max(32, Math.min(54, Math.floor(width * 0.42)));
  return (
    <Box borderStyle="round" borderColor={ORANGE} paddingX={2} paddingY={1} flexDirection="row" marginBottom={1}>
      <Box flexDirection="column" width={leftWidth} marginRight={3}>
        <Text color={ORANGE} bold>Claude Code <Text color={GREY}>v2-style</Text></Text>
        <Text> </Text>
        <Text bold>Welcome back</Text>
        <Text color={ORANGE}>{TEARDROP}  {TEARDROP}  {TEARDROP}</Text>
        <Text> </Text>
        <Text dimColor>{model} · Nexa port</Text>
        <Text dimColor>{truncateMiddle(cwd, leftWidth - 2)}</Text>
      </Box>
      <Box flexDirection="column" flexGrow={1}>
        <Text color={ORANGE} bold>Tips for getting started</Text>
        <Text dimColor>Run /init to create a CLAUDE.md file with instructions</Text>
        <Text dimColor>Use / for commands, Shift+Tab for permission mode</Text>
        <Text> </Text>
        <Text color={ORANGE} bold>What's new</Text>
        <Text dimColor>Added /rewind-style recovery surface</Text>
        <Text dimColor>Improved tool and permission rendering</Text>
        <Text dimColor>/release-notes for more</Text>
      </Box>
    </Box>
  );
}

function StartupContextBlock() {
  return (
    <Box flexDirection="column" paddingX={2} marginBottom={1}>
      <Text>
        <Text color={DIM}>{HOOK}  SessionStart:startup says: </Text>
        <Text color={BLUE} bold>[claude-code-port] recent context</Text>
      </Text>
      <Text color={DIM}>   ────────────────────────────────────────────────────────────</Text>
      <Text dimColor>   No previous sessions found for this project yet.</Text>
      <Text color={BLUE}>   View Observations Live @ http://localhost:37777</Text>
    </Box>
  );
}

function normalizedResultLines(result: string): string[] {
  const normalized = result.replace(/\r\n/g, "\n").replace(/\n$/, "");
  return normalized ? normalized.split("\n") : [];
}

function truncateResultLine(line: string): string {
  const maxWidth = Math.max(24, terminalWidth() - 8);
  return line.length > maxWidth ? line.slice(0, maxWidth - 1) + "…" : line;
}

function findArg(args: [string, string][], keys: string[]): string {
  const lowered = keys.map((key) => key.toLowerCase());
  return args.find(([key]) => lowered.includes(key.toLowerCase()))?.[1] || "";
}

function toolCallLabel(name: string, args: [string, string][]): string {
  const lower = name.toLowerCase();
  const pathValue = findArg(args, ["file_path", "path", "notebook_path"]);
  const command = findArg(args, ["command", "cmd", "script"]);
  const pattern = findArg(args, ["pattern", "query"]);
  const primary =
    lower.includes("bash") || lower.includes("shell") ? command :
    lower.includes("grep") ? [pattern, pathValue].filter(Boolean).join(" in ") :
    lower.includes("glob") ? pattern || pathValue :
    pathValue || command || pattern;
  if (!primary) return name;
  const normalized = primary.replace(/\r\n/g, "\n");
  const lineCount = normalized.split("\n").length;
  const compact = normalized.replace(/\s+/g, " ").trim();
  const suffix = lineCount > 1 ? ` · ${lineCount} lines` : "";
  return `${name}(${truncateMiddle(compact, Math.max(18, terminalWidth() - name.length - 16))}${suffix})`;
}

function ToolView({ entry }: { entry: Extract<Entry, { kind: "tool" }> }) {
  const args = argEntries(entry.args);
  const argSummary = args.map(([k, v]) => `${k}: ${v}`).join(", ");
  const label = toolCallLabel(entry.name, args);
  const usedPrimaryLabel = label !== entry.name;
  const result = entry.result || "";
  const resultLines = normalizedResultLines(result);
  const foldAt = 6;
  const isLong = resultLines.length > foldAt || result.length > 900 || resultLines.some((line) => line.length > terminalWidth() * 2);
  const visible = entry.expanded || !isLong ? resultLines : resultLines.slice(0, foldAt);
  const hiddenLines = Math.max(0, resultLines.length - visible.length);
  const hiddenSummary = hiddenLines > 0 ? `+${hiddenLines} lines` : "long output";
  const color = entry.status === "error" ? RED : entry.status === "denied" ? WARN : BLUE;
  const resultColor = entry.status === "error" ? RED : entry.status === "denied" ? WARN : DIM;
  const statusLabel =
    entry.status === "waiting" ? "Waiting…" :
    entry.status === "running" ? "Running…" :
    entry.status === "denied" ? "Denied" :
    entry.status === "error" ? "Error" : "";

  return (
    <Box flexDirection="column" marginTop={1}>
      <Text>
        <Text color={ORANGE}>{BLACK_CIRCLE} </Text>
        <Text color={color} bold>{label}</Text>
        {argSummary && !usedPrimaryLabel && <Text dimColor> {truncateMiddle(argSummary, Math.max(32, terminalWidth() - entry.name.length - 8))}</Text>}
      </Text>
      <Box marginLeft={2} flexDirection="column">
        {entry.result === null ? (
          <Text color={DIM}>{HOOK} <Text color={ORANGE}><Spinner type="dots" /></Text> {statusLabel || "Running…"}</Text>
        ) : (
          <>
            {statusLabel && <Text color={resultColor}>{HOOK} {statusLabel}</Text>}
            {visible.length === 0 && !statusLabel && <Text color={DIM}>{HOOK} (No content)</Text>}
            {visible.map((line, i) => {
              const prefix = i === 0 && !statusLabel ? `${HOOK} ` : "  ";
              return (
                <Text key={i} color={resultColor}>
                  {prefix}
                  {truncateResultLine(line) || " "}
                </Text>
              );
            })}
            {isLong && !entry.expanded && (
              <Text color={DIM} italic>  … {hiddenSummary} ({result.length} chars, ctrl+o to expand)</Text>
            )}
            {isLong && entry.expanded && <Text color={DIM} italic>  showing full result ({resultLines.length} lines, ctrl+o to collapse)</Text>}
          </>
        )}
      </Box>
    </Box>
  );
}

function ErrorBlock({ message, source }: { message: string; source: string }) {
  return (
    <Box borderStyle="round" borderColor={RED} paddingX={1} flexDirection="column" marginY={1}>
      <Text color={RED} bold>{source === "engine" ? "Engine error" : source === "tool" ? "Tool error" : "UI error"}</Text>
      <Text color={RED}>{message}</Text>
    </Box>
  );
}

function UserMessage({ text }: { text: string }) {
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  const isMultiline = lines.length > 1;
  return (
    <Box flexDirection="column" marginTop={isMultiline ? 1 : 0}>
      {lines.map((line, idx) => (
        <Text key={idx} color={DIM}>
          <Text>{idx === 0 ? "> " : "  "}</Text>
          <Text>{line || " "}</Text>
        </Text>
      ))}
      {isMultiline && <Text color={DIM} italic>  {lines.length} line prompt</Text>}
    </Box>
  );
}

function MessageLog({ entries, streaming }: { entries: Entry[]; streaming: string }) {
  return (
    <Box flexDirection="column" paddingX={1} flexGrow={1}>
      {entries.map((entry, i) => {
        if (entry.kind === "user") {
          return <UserMessage key={i} text={entry.text} />;
        }
        if (entry.kind === "assistant") {
          return (
            <Box key={i} marginTop={1}>
              <Text color={ORANGE}>● </Text>
              <MarkdownView text={entry.text} />
            </Box>
          );
        }
        if (entry.kind === "tool") return <ToolView key={entry.id} entry={entry} />;
        if (entry.kind === "error") return <ErrorBlock key={i} message={entry.message} source={entry.source} />;
        const color = entry.tone === "warning" ? WARN : entry.tone === "success" ? GREEN : DIM;
        return <Text key={i} color={color} italic>{entry.text}</Text>;
      })}
      {streaming && (
        <Box marginTop={1}>
          <Text color={ORANGE}>● </Text>
          <MarkdownView text={streaming} />
          <Text color={ORANGE}>▋</Text>
        </Box>
      )}
    </Box>
  );
}

function SlashOverlay({ matches, selected, query }: { matches: Command[]; selected: number; query: string }) {
  const width = terminalWidth();
  const selectedCommand = matches[Math.min(selected, Math.max(0, matches.length - 1))];
  return (
    <Box flexDirection="column" paddingX={1} marginX={1}>
      <Text>
        <Text color={ORANGE} bold>Commands</Text>
        <Text dimColor> {matches.length > 0 ? `${selected + 1}/${matches.length}` : "0 matches"}</Text>
        {query.length > 1 && <Text dimColor> · filtering "{query.slice(1)}"</Text>}
      </Text>
      {matches.length === 0 ? (
        <Text dimColor>No slash commands match. Backspace to broaden the search.</Text>
      ) : (
        matches.map((c, i) => {
          const isSelected = i === selected;
          const source = c.source || "builtin";
          const descWidth = Math.max(18, width - (c.hint ? 58 : 38));
          return (
            <Text key={c.name}>
              <Text color={isSelected ? ORANGE : DIM}>{isSelected ? "› " : "  "}</Text>
              <Text color={isSelected ? ORANGE : DIM}>{c.name.padEnd(18)}</Text>
              <Text color={DIM}>{source.padEnd(12)}</Text>
              {c.hint && <Text color={isSelected ? BLUE : DIM}>{c.hint.padEnd(18)}</Text>}
              <Text color={isSelected ? GREY : DIM}>{truncateMiddle(c.desc, descWidth)}</Text>
            </Text>
          );
        })
      )}
      <Text dimColor>
        ↑/↓ navigate · tab complete
        {selectedCommand ? ` · enter ${selectedCommand.name}${selectedCommand.hint ? ` ${selectedCommand.hint}` : ""}` : " · enter keeps typing"}
      </Text>
    </Box>
  );
}

function PromptBox({
  input,
  enabled,
  busy,
  loadingText,
  onChange,
  onSubmit,
}: {
  input: string;
  enabled: boolean;
  busy: boolean;
  loadingText: string;
  onChange: (value: string) => void;
  onSubmit: (value: string) => void;
}) {
  const normalized = input.replace(/\r\n/g, "\n");
  const lineCount = normalized ? normalized.split("\n").length : 1;
  const hasContinuation = normalized.endsWith("\\");
  const showInputHint = enabled && (lineCount > 1 || hasContinuation);
  return (
    <Box borderStyle="single" borderColor={DIM} paddingX={1} flexDirection="column">
      <Box>
        <Text color={ORANGE}>&gt; </Text>
        {enabled ? (
          <TextInput
            value={input}
            onChange={onChange}
            onSubmit={onSubmit}
            placeholder={busy ? "(working…)" : "Try \"create a util…\" or / for commands"}
          />
        ) : (
          <Text dimColor>{loadingText}</Text>
        )}
      </Box>
      {showInputHint && (
        <Text dimColor>
          {"  "}
          {hasContinuation ? "newline pending" : `${lineCount} lines`}
          {" · Enter sends · Ctrl+J or \\+Enter adds a line"}
        </Text>
      )}
    </Box>
  );
}

function toolRisk(tool: string, params: [string, string][]): { color: string; label: string; hint: string } {
  const command = params.find(([key]) => /^(command|cmd|script)$/i.test(key))?.[1] || "";
  if (/bash|shell|powershell/i.test(tool)) {
    if (/\b(rm\s+-rf|del\s+\/[sq]|format\b|dd\s+if=|chmod\s+777|sudo\b|curl\b.*\|\s*(sh|bash)|powershell\b.*-enc)\b/i.test(command)) {
      return { color: RED, label: "destructive command", hint: "Review command, path, and side effects before allowing." };
    }
    return { color: WARN, label: "shell command", hint: "This can change files or run arbitrary local processes." };
  }
  if (/write|edit|notebookedit/i.test(tool)) {
    return { color: WARN, label: "file mutation", hint: "This may modify files in the current project." };
  }
  if (/read|grep|glob|ls/i.test(tool)) {
    return { color: BLUE, label: "read-only", hint: "This should only inspect local project data." };
  }
  return { color: ORANGE, label: "tool request", hint: "Check the tool input before proceeding." };
}

function PermissionModal({
  tool,
  args,
  onRespond,
}: {
  tool: string;
  args: string;
  onRespond: (decision: "allow" | "always" | "deny") => void;
}) {
  useInput((input, key) => {
    if (input === "y" || input === "Y") onRespond("allow");
    else if (input === "a" || input === "A") onRespond("always");
    else if (input === "n" || input === "N" || key.escape) onRespond("deny");
  });

  const params = argEntries(args);
  const risk = toolRisk(tool, params);
  return (
    <Box flexDirection="column" borderStyle="round" borderColor={risk.color} paddingX={2} paddingY={1} marginX={2} marginY={1}>
      <Text>
        <Text color={ORANGE}>{TEARDROP} </Text>
        <Text bold>Claude wants permission to use </Text>
        <Text bold color={BLUE}>{tool}</Text>
      </Text>
      <Text>
        <Text color={risk.color} bold>{risk.label}</Text>
        <Text dimColor> · {risk.hint}</Text>
      </Text>
      <Box flexDirection="column" marginLeft={2} marginTop={1}>
        <Text color={DIM}>Tool input</Text>
        {params.slice(0, 8).map(([key, value]) => (
          <Text key={key}>
            <Text color={DIM}>{key}: </Text>
            <Text>{truncateMiddle(value, Math.max(36, terminalWidth() - 18))}</Text>
          </Text>
        ))}
        {params.length > 8 && <Text dimColor>… {params.length - 8} more parameters</Text>}
      </Box>
      <Text> </Text>
      <Text bold>Do you want to proceed?</Text>
      <Text>
        <Text color={GREEN}>y</Text><Text dimColor> yes, allow once  </Text>
        <Text color={ORANGE}>a</Text><Text dimColor> yes, don't ask again*  </Text>
        <Text color={RED}>n</Text><Text dimColor> no  </Text>
        <Text color={DIM}>esc cancel</Text>
      </Text>
      <Text dimColor>* persistent allow needs engine support; this UI currently allows once.</Text>
    </Box>
  );
}

function ActiveRow({
  busy,
  thinkTool,
  thinkPhase,
  elapsed,
  tokensOut,
}: {
  busy: boolean;
  thinkTool: string;
  thinkPhase: string;
  elapsed: number;
  tokensOut: number;
}) {
  if (!busy) return null;
  const label = thinkTool || (thinkPhase === "thinking" ? "Thinking" : "Working");
  return (
    <Box paddingX={1}>
      <Text color={ORANGE}><Spinner type="dots" /></Text>
      <Text color={ORANGE}> {label}… </Text>
      <Text dimColor>(esc to interrupt</Text>
      {elapsed > 0 && <Text dimColor> · {elapsed}s</Text>}
      {tokensOut > 0 && <Text dimColor> · ↑ {tokensOut} tokens</Text>}
      <Text dimColor>)</Text>
    </Box>
  );
}

function ModeNotice({ mode }: { mode: PermMode }) {
  if (mode === "default") return null;
  const copy: Record<Exclude<PermMode, "default">, { label: string; detail: string }> = {
    plan: {
      label: "plan mode on",
      detail: "Claude should research and propose a plan before editing files.",
    },
    bypass: {
      label: "bypass permissions on",
      detail: "Tool calls may run without confirmation.",
    },
    auto: {
      label: "auto permissions on",
      detail: "Low-risk tool calls may proceed automatically.",
    },
  };
  const current = copy[mode];
  return (
    <Box paddingX={1}>
      <Text color={MODE_COLORS[mode]} bold>{mode === "plan" ? "⏸ " : mode === "bypass" ? "⏵⏵ " : "● "}{current.label}</Text>
      <Text dimColor> · {current.detail} Shift+Tab cycles modes.</Text>
    </Box>
  );
}

function FooterBar({
  mode,
  model,
  cwd,
  projectName,
  gitBranch,
  gitDirty,
  busy,
  tokensIn,
  tokensOut,
  active,
  sessionSeconds,
  exitArmed,
}: {
  mode: PermMode;
  model: string;
  cwd: string;
  projectName: string;
  gitBranch: string;
  gitDirty: boolean;
  busy: boolean;
  tokensIn: number;
  tokensOut: number;
  active: string;
  sessionSeconds: number;
  exitArmed: boolean;
}) {
  const footerWidth = Math.max(60, terminalWidth() - 2);
  const gitText = gitBranch ? ` | ${gitBranch}${gitDirty ? " *" : " ✓"}` : "";
  const projectText = truncateMiddle(`${projectName}${gitText}`, Math.max(18, footerWidth - 48));
  const pathText = truncateMiddle(cwd, Math.max(12, footerWidth - 52));
  return (
    <Box paddingX={1} flexDirection="column">
      {exitArmed && <Text color={WARN}>Press Ctrl-C again to exit</Text>}
      <Text>
        <Text color={BLUE}>🤖 {model}</Text>
        <Text dimColor> | 📁 {projectText}</Text>
        <Text dimColor> | ⚡ {tokensIn}/{tokensOut}</Text>
        <Text dimColor> | ⏱ {formatDuration(sessionSeconds)}</Text>
      </Text>
      <Text>
        <Text color={MODE_COLORS[mode]} bold>Ⓜ️ {mode}</Text>
        {busy && <Text color={ORANGE}>  <Spinner type="dots" /> {active || "working"}</Text>}
        {!busy && <Text dimColor>  ○ idle</Text>}
      </Text>
      <Text>
        <Text color={MODE_COLORS[mode]} bold>{mode === "bypass" ? "⏵⏵ bypass permissions on" : `${mode} permissions`}</Text>
        <Text dimColor> (shift+tab to cycle) · {pathText} · ← for agents</Text>
        <Text dimColor>                                           ◉ xhigh · /effort</Text>
      </Text>
    </Box>
  );
}

function App() {
  const { exit } = useApp();
  const { isRawModeSupported } = useStdin();
  const [showStartup, setShowStartup] = useState(true);
  const [entries, setEntries] = useState<Entry[]>([]);
  const [streaming, setStreaming] = useState("");
  const [input, setInput] = useState("");
  const [model, setModel] = useState("glm-5.1");
  const [busy, setBusy] = useState(false);
  const [permission, setPermission] = useState<{ requestId: number; tool: string; args: string } | null>(null);
  const [permMode, setPermMode] = useState<PermMode>("default");
  const [thinkPhase, setThinkPhase] = useState("");
  const [thinkTool, setThinkTool] = useState("");
  const [elapsed, setElapsed] = useState(0);
  const [tokensIn, setTokensIn] = useState(0);
  const [tokensOut, setTokensOut] = useState(0);
  const [slashSelected, setSlashSelected] = useState(0);
  const [engineReady, setEngineReady] = useState(false);
  const [history, setHistory] = useState<string[]>([]);
  const [historyIndex, setHistoryIndex] = useState<number | null>(null);
  const [sessionSeconds, setSessionSeconds] = useState(0);
  const [exitArmed, setExitArmed] = useState(false);
  const [escapeArmed, setEscapeArmed] = useState(false);
  const [gitBranch, setGitBranch] = useState("");
  const [gitDirty, setGitDirty] = useState(false);
  const nextToolId = useRef(1);
  const turnStartRef = useRef<number>(0);
  const appStartRef = useRef<number>(Date.now());
  const exitTimerRef = useRef<NodeJS.Timeout | null>(null);
  const draftBeforeHistoryRef = useRef("");
  const engineRef = useRef<Engine | null>(null);

  const showSlash = input.startsWith("/") && !input.includes(" ") && !input.includes("\n") && !busy && !permission;
  const slashMatches = useMemo(() => showSlash ? commandMatches(input) : [], [input, showSlash]);

  const handleInputChange = useCallback((value: string) => {
    setInput(value.replace(/\r\n/g, "\n"));
    setHistoryIndex(null);
  }, []);

  useEffect(() => {
    setSlashSelected(0);
  }, [input]);

  useEffect(() => {
    const refreshGit = () => {
      setGitBranch(readGitBranch());
      setGitDirty(readGitDirty());
    };
    refreshGit();
    const timer = setInterval(refreshGit, 10000);
    return () => clearInterval(timer);
  }, []);

  const appendSystem = useCallback((text: string, tone: "info" | "success" | "warning" = "info") => {
    setEntries((es) => [...es, { kind: "system", text, tone }]);
  }, []);

  const handleEvent = useCallback((e: EngineEvent) => {
    switch (e.type) {
      case "ready":
        setModel(e.model);
        setEngineReady(true);
        break;
      case "assistant_token":
        setStreaming((s) => s + e.content);
        setTokensOut((n) => n + estimateTokens(e.content));
        break;
      case "turn_status":
        setThinkPhase(e.phase || "");
        setThinkTool(e.tool || "");
        if (e.phase === "thinking" && turnStartRef.current === 0) turnStartRef.current = Date.now();
        if (e.phase === "idle") {
          turnStartRef.current = 0;
          setThinkPhase("");
          setThinkTool("");
        }
        if (typeof e.tokens_in === "number") setTokensIn(e.tokens_in);
        if (typeof e.tokens_out === "number") setTokensOut(e.tokens_out);
        break;
      case "tool_call":
        setStreaming((s) => {
          if (s.trim()) setEntries((es) => [...es, { kind: "assistant", text: s.trim() }]);
          return "";
        });
        setEntries((es) => [...es, {
          kind: "tool",
          id: nextToolId.current++,
          name: e.name,
          args: e.args,
          result: null,
          status: "running",
          expanded: false,
        }]);
        setThinkTool(e.name);
        break;
      case "tool_result":
        setEntries((es) => {
          const next = [...es];
          for (let i = next.length - 1; i >= 0; i -= 1) {
            const item = next[i];
            if (item.kind === "tool" && item.result === null) {
              const status = statusFromResult(e.result);
              next[i] = { ...item, result: e.result, status };
              if (status === "error") {
                next.splice(i + 1, 0, { kind: "error", source: "tool", message: e.result });
              }
              break;
            }
          }
          return next;
        });
        setThinkTool("");
        break;
      case "done":
        setStreaming((s) => {
          const text = (s.trim() || e.reply).trim();
          if (text) setEntries((es) => [...es, { kind: "assistant", text }]);
          return "";
        });
        setBusy(false);
        setThinkPhase("");
        setThinkTool("");
        turnStartRef.current = 0;
        break;
      case "permission_request":
        setPermission({ requestId: e.request_id, tool: e.tool, args: e.args });
        break;
      case "mode_changed":
        if (MODES.includes(e.mode as PermMode)) setPermMode(e.mode as PermMode);
        break;
      case "command_result":
        setEntries((es) => [...es, { kind: "assistant", text: e.result }]);
        setBusy(false);
        break;
      case "error":
        setEntries((es) => [...es, { kind: "error", source: "engine", message: e.message }]);
        setBusy(false);
        setThinkPhase("");
        setThinkTool("");
        break;
      case "session_end":
        exit();
        break;
    }
  }, [exit]);

  useEffect(() => {
    const eng = new Engine(handleEvent, () => exit(), { projectRoot: PROJECT_ROOT, permissionMode: "default" });
    engineRef.current = eng;
    return () => eng.close();
  }, [handleEvent, exit]);

  useEffect(() => {
    const timer = setInterval(() => setSessionSeconds(Math.floor((Date.now() - appStartRef.current) / 1000)), 1000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!busy) return;
    if (turnStartRef.current === 0) turnStartRef.current = Date.now();
    const timer = setInterval(() => setElapsed(Math.floor((Date.now() - turnStartRef.current) / 1000)), 1000);
    return () => clearInterval(timer);
  }, [busy]);

  const toggleLatestTool = useCallback(() => {
    setEntries((es) => {
      const next = [...es];
      for (let i = next.length - 1; i >= 0; i -= 1) {
        const item = next[i];
        if (item.kind === "tool" && item.result !== null) {
          next[i] = { ...item, expanded: !item.expanded };
          break;
        }
      }
      return next;
    });
  }, []);

  useInput((rawInput, key) => {
    if (permission) return;
    if (!busy && (rawInput === "\u0003" || (key.ctrl && rawInput === "c"))) {
      if (exitArmed) {
        engineRef.current?.sendExit();
        setTimeout(() => exit(), 100);
        return;
      }
      setExitArmed(true);
      if (exitTimerRef.current) clearTimeout(exitTimerRef.current);
      exitTimerRef.current = setTimeout(() => setExitArmed(false), 2500);
      return;
    }
    if (showSlash && slashMatches.length > 0) {
      if (key.upArrow) {
        setSlashSelected((i) => (i <= 0 ? slashMatches.length - 1 : i - 1));
        return;
      }
      if (key.downArrow) {
        setSlashSelected((i) => (i + 1) % slashMatches.length);
        return;
      }
      if (key.tab) {
        const selected = slashMatches[Math.min(slashSelected, slashMatches.length - 1)];
        if (selected) setInput(selected.name + " ");
        return;
      }
    }
    if (!busy && !showSlash && history.length > 0) {
      if (key.upArrow) {
        if (historyIndex === null) draftBeforeHistoryRef.current = input;
        const nextIndex = historyIndex === null ? history.length - 1 : Math.max(0, historyIndex - 1);
        setHistoryIndex(nextIndex);
        setInput(history[nextIndex]);
        return;
      }
      if (key.downArrow && historyIndex !== null) {
        const nextIndex = historyIndex + 1;
        if (nextIndex >= history.length) {
          setHistoryIndex(null);
          setInput(draftBeforeHistoryRef.current);
        } else {
          setHistoryIndex(nextIndex);
          setInput(history[nextIndex]);
        }
        return;
      }
    }
    if (!busy && key.ctrl && rawInput.toLowerCase() === "j") {
      setInput((s) => s + "\n");
      setHistoryIndex(null);
      return;
    }
    if (key.tab && key.shift) {
      const idx = MODES.indexOf(permMode);
      const next = MODES[(idx + 1) % MODES.length];
      setPermMode(next);
      engineRef.current?.sendSetMode(next);
      return;
    }
    if (busy && key.escape) {
      if (!escapeArmed) {
        setEscapeArmed(true);
        setEntries((es) => [...es, { kind: "system", tone: "warning", text: "Esc again to clear. Engine-side cancellation requires protocol support." }]);
        setTimeout(() => setEscapeArmed(false), 1800);
        return;
      }
      setEscapeArmed(false);
      setBusy(false);
      setThinkPhase("");
      setThinkTool("");
      turnStartRef.current = 0;
      setStreaming((s) => {
        if (s.trim()) setEntries((es) => [...es, { kind: "assistant", text: s.trim() + "  ⏸ Interrupted" }]);
        return "";
      });
      setEntries((es) => [...es, { kind: "system", tone: "warning", text: "Interrupted locally. Engine-side cancellation requires protocol support." }]);
      return;
    }
    if (!input && (rawInput === "x" || rawInput === "\u000f" || (key.ctrl && rawInput.toLowerCase() === "o"))) {
      toggleLatestTool();
    }
  });

  const submit = (value: string) => {
    if (busy || permission) return;
    const normalized = value.replace(/\r\n/g, "\n");
    if (normalized.endsWith("\\")) {
      setInput(normalized.slice(0, -1) + "\n");
      setHistoryIndex(null);
      return;
    }
    const v = normalized.trim();
    if (showSlash && slashMatches.length > 0) {
      const exact = COMMANDS.find((c) => c.name === v);
      if (!exact) {
        const selected = slashMatches[Math.min(slashSelected, slashMatches.length - 1)];
        if (selected) {
          setInput(selected.name + " ");
          return;
        }
      }
    }
    setInput("");
    setHistoryIndex(null);
    if (!v) return;
    setShowStartup(false);
    setExitArmed(false);
    const eng = engineRef.current;
    if (v === "exit" || v === "/exit" || v === "/quit") {
      eng?.sendExit();
      setTimeout(() => exit(), 200);
      return;
    }
    setHistory((items) => {
      const next = items[items.length - 1] === v ? items : [...items, v];
      return next.slice(-80);
    });
    setEntries((es) => [...es, { kind: "user", text: v }]);
    setBusy(true);
    setElapsed(0);
    setTokensIn(estimateTokens(v));
    setTokensOut(0);
    turnStartRef.current = Date.now();
    if (v.startsWith("/")) eng?.sendCommand(v);
    else eng?.sendMessage(v);
  };

  const cwdShort = truncateMiddle(PROJECT_DISPLAY, Math.max(14, terminalWidth() - 86));
  const active = thinkTool || (thinkPhase ? thinkPhase : busy ? "thinking" : "");

  if (showStartup) {
    return (
      <Box flexDirection="column">
        <StartupCard model={model} cwd={PROJECT_DISPLAY} />
        {engineReady && <StartupContextBlock />}
        {showSlash && <SlashOverlay matches={slashMatches} selected={Math.min(slashSelected, Math.max(0, slashMatches.length - 1))} query={input} />}
        <ModeNotice mode={permMode} />
        <PromptBox
          input={input}
          enabled={engineReady && isRawModeSupported}
          busy={false}
          loadingText="Loading engine…"
          onChange={handleInputChange}
          onSubmit={submit}
        />
        <FooterBar mode={permMode} model={model} cwd={cwdShort} projectName={PROJECT_NAME} gitBranch={gitBranch} gitDirty={gitDirty} busy={false} tokensIn={0} tokensOut={0} active="" sessionSeconds={sessionSeconds} exitArmed={exitArmed} />
      </Box>
    );
  }

  return (
    <Box flexDirection="column">
      <MessageLog entries={entries} streaming={streaming} />
      {permission && (
        <PermissionModal
          tool={permission.tool}
          args={permission.args}
          onRespond={(decision) => {
            if (decision === "always") {
              appendSystem("Always allow is not persistent yet; allowing this tool call once.", "warning");
              engineRef.current?.sendPermissionResponse(permission.requestId, true);
            } else {
              engineRef.current?.sendPermissionResponse(permission.requestId, decision === "allow");
            }
            setPermission(null);
          }}
        />
      )}
      {showSlash && <SlashOverlay matches={slashMatches} selected={Math.min(slashSelected, Math.max(0, slashMatches.length - 1))} query={input} />}
      <ActiveRow busy={busy} thinkTool={thinkTool} thinkPhase={thinkPhase} elapsed={elapsed} tokensOut={tokensOut} />
      <ModeNotice mode={permMode} />
      <PromptBox
        input={input}
        enabled={isRawModeSupported}
        busy={busy}
        loadingText="(run in a real terminal)"
        onChange={handleInputChange}
        onSubmit={submit}
      />
      <FooterBar mode={permMode} model={model} cwd={cwdShort} projectName={PROJECT_NAME} gitBranch={gitBranch} gitDirty={gitDirty} busy={busy} tokensIn={tokensIn} tokensOut={tokensOut} active={active} sessionSeconds={sessionSeconds} exitArmed={exitArmed} />
    </Box>
  );
}

render(React.createElement(App));
