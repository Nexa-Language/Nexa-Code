// index.tsx - Ink/React UI polish loop.
// UI-only boundary: subprocess bridge + rendering/input only. No agent loop, tool
// execution, permission decision, or LLM calls live here.
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { render, Box, Text, useApp, useInput, useStdin } from "ink";
import TextInput from "ink-text-input";
import Spinner from "ink-spinner";
import * as path from "node:path";
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
const CWD_FULL = process.cwd().replace(process.env.HOME || process.env.USERPROFILE || "", "~");

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

function InlineText({ text, color }: { text: string; color?: string }) {
  const pieces = text.split(/(`[^`]+`)/g);
  return (
    <Text color={color}>
      {pieces.map((piece, idx) => {
        if (piece.startsWith("`") && piece.endsWith("`")) {
          return <Text key={idx} color={BLUE}>{piece.slice(1, -1)}</Text>;
        }
        return <Text key={idx}>{piece}</Text>;
      })}
    </Text>
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
          <Text key={i} color={VIOLET}>{line || " "}</Text>
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
        <Text color={ORANGE} bold>Recent activity</Text>
        <Text dimColor>No recent activity in this UI shell</Text>
      </Box>
    </Box>
  );
}

function ToolView({ entry }: { entry: Extract<Entry, { kind: "tool" }> }) {
  const args = argEntries(entry.args);
  const argSummary = args.map(([k, v]) => `${k}: ${v}`).join(", ");
  const result = entry.result || "";
  const resultLines = result.split("\n");
  const foldAt = 6;
  const isLong = resultLines.length > foldAt || result.length > 900;
  const visible = entry.expanded || !isLong ? resultLines : resultLines.slice(0, foldAt);
  const color = entry.status === "error" ? RED : entry.status === "denied" ? WARN : BLUE;
  const statusLabel =
    entry.status === "waiting" ? "Waiting…" :
    entry.status === "running" ? "Running…" :
    entry.status === "denied" ? "Denied" :
    entry.status === "error" ? "Error" : "";

  return (
    <Box flexDirection="column" marginTop={1}>
      <Text>
        <Text color={ORANGE}>{BLACK_CIRCLE} </Text>
        <Text color={color} bold>{entry.name}</Text>
        {argSummary && <Text dimColor> {truncateMiddle(argSummary, Math.max(32, terminalWidth() - entry.name.length - 8))}</Text>}
      </Text>
      <Box marginLeft={2} flexDirection="column">
        {entry.result === null ? (
          <Text color={DIM}>{HOOK} <Text color={ORANGE}><Spinner type="dots" /></Text> {statusLabel || "Running…"}</Text>
        ) : (
          <>
            {visible.map((line, i) => (
              <Text key={i} color={entry.status === "error" ? RED : DIM}>
                {i === 0 ? `${HOOK} ` : "  "}
                {line.length > terminalWidth() - 6 ? line.slice(0, terminalWidth() - 7) + "…" : line || " "}
              </Text>
            ))}
            {isLong && !entry.expanded && (
              <Text color={DIM} italic>  … {resultLines.length - foldAt} more lines ({result.length} chars). Press x to expand latest tool.</Text>
            )}
            {isLong && entry.expanded && <Text color={DIM} italic>  showing full result. Press x to fold latest tool.</Text>}
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

function MessageLog({ entries, streaming }: { entries: Entry[]; streaming: string }) {
  return (
    <Box flexDirection="column" paddingX={1} flexGrow={1}>
      {entries.map((entry, i) => {
        if (entry.kind === "user") {
          return <Text key={i} color={DIM}>&gt; {entry.text}</Text>;
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

function SlashOverlay({ matches, selected }: { matches: Command[]; selected: number }) {
  if (matches.length === 0) return null;
  return (
    <Box flexDirection="column" borderStyle="single" borderColor={BLUE} paddingX={1} marginX={1}>
      {matches.map((c, i) => (
        <Box key={c.name}>
          <Text color={i === selected ? ORANGE : DIM}>{i === selected ? "▶ " : "  "}</Text>
          <Text bold color={i === selected ? ORANGE : BLUE}>{c.name.padEnd(13)}</Text>
          <Text color={i === selected ? GREY : DIM}>{truncateMiddle(c.desc, Math.max(24, terminalWidth() - 22))}</Text>
        </Box>
      ))}
      <Text dimColor>  ↑/↓ select · tab complete · enter run</Text>
    </Box>
  );
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
  return (
    <Box flexDirection="column" borderStyle="round" borderColor={ORANGE} paddingX={2} paddingY={1} marginX={2} marginY={1}>
      <Text>
        <Text color={ORANGE}>{TEARDROP} </Text>
        <Text bold>Claude wants to use </Text>
        <Text bold color={BLUE}>{tool}</Text>
      </Text>
      <Box flexDirection="column" marginLeft={2} marginTop={1}>
        {params.slice(0, 8).map(([key, value]) => (
          <Text key={key}>
            <Text color={DIM}>{key}: </Text>
            <Text>{truncateMiddle(value, Math.max(36, terminalWidth() - 18))}</Text>
          </Text>
        ))}
        {params.length > 8 && <Text dimColor>… {params.length - 8} more parameters</Text>}
      </Box>
      <Text> </Text>
      <Text>
        <Text color={GREEN}>y</Text><Text dimColor> allow  </Text>
        <Text color={ORANGE}>a</Text><Text dimColor> always allow  </Text>
        <Text color={RED}>n</Text><Text dimColor> deny  </Text>
        <Text color={DIM}>esc deny</Text>
      </Text>
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

function FooterBar({
  mode,
  model,
  cwd,
  busy,
  tokensIn,
  tokensOut,
  active,
}: {
  mode: PermMode;
  model: string;
  cwd: string;
  busy: boolean;
  tokensIn: number;
  tokensOut: number;
  active: string;
}) {
  return (
    <Box paddingX={1}>
      <Text color={MODE_COLORS[mode]} bold>{mode === "bypass" ? "⏵⏵ bypass permissions on" : mode}</Text>
      <Text dimColor> (shift+tab to cycle)</Text>
      <Text dimColor>  </Text>
      <Text color={BLUE}>{model}</Text>
      <Text dimColor> {cwd}</Text>
      <Text dimColor>  </Text>
      <Text color={GREY}>↓{tokensIn} ↑{tokensOut}</Text>
      {busy && <Text color={ORANGE}>  <Spinner type="dots" /> {active || "working"}</Text>}
      {!busy && <Text dimColor>  ○ idle</Text>}
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
  const nextToolId = useRef(1);
  const turnStartRef = useRef<number>(0);
  const engineRef = useRef<Engine | null>(null);

  const showSlash = input.startsWith("/") && !input.includes(" ") && !busy && !permission;
  const slashMatches = useMemo(() => showSlash ? commandMatches(input) : [], [input, showSlash]);

  useEffect(() => {
    setSlashSelected(0);
  }, [input]);

  const appendSystem = useCallback((text: string, tone: "info" | "success" | "warning" = "info") => {
    setEntries((es) => [...es, { kind: "system", text, tone }]);
  }, []);

  const handleEvent = useCallback((e: EngineEvent) => {
    switch (e.type) {
      case "ready":
        setModel(e.model);
        setShowStartup(false);
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
    if (key.tab && key.shift) {
      const idx = MODES.indexOf(permMode);
      const next = MODES[(idx + 1) % MODES.length];
      setPermMode(next);
      engineRef.current?.sendSetMode(next);
      return;
    }
    if (busy && key.escape) {
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
    if (!input && rawInput === "x") toggleLatestTool();
  });

  const submit = (value: string) => {
    if (busy || permission) return;
    const v = value.trim();
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
    if (!v) return;
    const eng = engineRef.current;
    if (v === "exit" || v === "/exit" || v === "/quit") {
      eng?.sendExit();
      setTimeout(() => exit(), 200);
      return;
    }
    setEntries((es) => [...es, { kind: "user", text: v }]);
    setBusy(true);
    setElapsed(0);
    setTokensIn(estimateTokens(v));
    setTokensOut(0);
    turnStartRef.current = Date.now();
    if (v.startsWith("/")) eng?.sendCommand(v);
    else eng?.sendMessage(v);
  };

  const cwdShort = truncateMiddle(CWD_FULL, Math.max(14, terminalWidth() - 72));
  const active = thinkTool || (thinkPhase ? thinkPhase : busy ? "thinking" : "");

  if (showStartup) {
    return (
      <Box flexDirection="column">
        <StartupCard model={model} cwd={CWD_FULL} />
        <Box borderStyle="single" borderColor={DIM} paddingX={1}>
          <Text color={ORANGE}>&gt; </Text>
          <Text dimColor>Loading engine…</Text>
        </Box>
        <FooterBar mode={permMode} model={model} cwd={cwdShort} busy={false} tokensIn={0} tokensOut={0} active="" />
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
      {showSlash && <SlashOverlay matches={slashMatches} selected={Math.min(slashSelected, Math.max(0, slashMatches.length - 1))} />}
      <ActiveRow busy={busy} thinkTool={thinkTool} thinkPhase={thinkPhase} elapsed={elapsed} tokensOut={tokensOut} />
      <Box borderStyle="single" borderColor={DIM} paddingX={1}>
        <Text color={ORANGE}>&gt; </Text>
        {isRawModeSupported ? (
          <TextInput
            value={input}
            onChange={setInput}
            onSubmit={submit}
            placeholder={busy ? "(working…)" : "Try \"create a util…\" or / for commands"}
          />
        ) : (
          <Text dimColor>(run in a real terminal)</Text>
        )}
      </Box>
      <FooterBar mode={permMode} model={model} cwd={cwdShort} busy={busy} tokensIn={tokensIn} tokensOut={tokensOut} active={active} />
    </Box>
  );
}

render(React.createElement(App));
