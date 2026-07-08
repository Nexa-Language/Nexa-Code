// engine.ts — subprocess 桥：spawn Nexa 引擎，JSON 行协议
// P0 Fix 1: 正确 Python 检测 + stderr 可见 + 退出报错不静默
// Phase 15 H3: turn_status / thinking 事件 + H5: set_mode 事件 + H6: 语义分离
import { spawn, ChildProcessWithoutNullStreams, execSync } from "node:child_process";
import * as path from "node:path";
import * as readline from "node:readline";
import { existsSync } from "node:fs";

export type EngineEvent =
  | { type: "ready"; model: string }
  | { type: "assistant_token"; content: string }
  | { type: "tool_call"; name: string; args: unknown }
  | { type: "tool_result"; name: string; result: string }
  | { type: "permission_request"; request_id: number; tool: string; args: string }
  | { type: "command_result"; name: string; result: string }
  | { type: "model_list"; current: string; models: Array<{ name: string; available?: boolean; description?: string }> }
  | { type: "session_list"; sessions: Array<{ path: string; title?: string; updated_at?: string; msg_count?: number }> }
  | { type: "done"; reply: string }
  | { type: "error"; message: string }
  | { type: "info"; message: string }
  | { type: "usage"; input?: number; output?: number; total?: number; cumulative_input?: number; cumulative_output?: number; estimated?: boolean }
  | { type: "session_end" }
  // Phase 15 H3: structured turn status (thinking phases)
  | { type: "turn_status"; phase: string; tool?: string; elapsed?: number; tokens_in?: number; tokens_out?: number }
  // Phase 15 H5: permission mode change
  | { type: "mode_changed"; mode: string };

function detectPython(): string {
  if (process.env.NEXA_PYTHON) return process.env.NEXA_PYTHON;
  try {
    const py = execSync('python -c "import sys; print(sys.executable)"', {
      encoding: "utf-8", timeout: 5000,
    }).trim();
    execSync(`"${py}" -c "import pydantic"`, { encoding: "utf-8", timeout: 5000, stdio: "pipe" });
    return py;
  } catch { return "python"; }
}

export class Engine {
  private proc: ChildProcessWithoutNullStreams;
  private rl: readline.Interface;
  private stderrBuf: string[] = [];
  private startupTimer: NodeJS.Timeout | null = null;
  private ready = false;

  constructor(
    private onEvent: (e: EngineEvent) => void,
    private onExit: () => void,
    opts: { projectRoot: string; permissionMode?: string }
  ) {
    const pyExe = detectPython();
    const env: Record<string, string> = {
      ...process.env,
      NEXA_JSON_EVENTS: "1",
      NEXA_PERMISSION_MODE: opts.permissionMode || "default",
      NEXA_QUIET: "1",
      NEXA_STREAM_TOOLS: "1",
      PYTHONUNBUFFERED: "1",
      PYTHONIOENCODING: "utf-8",
    } as Record<string, string>;
    // Method A: use wrapper script for robust env setup (conda/shell) + -u unbuffered
    // Method B (fallback): direct python -u spawn
    const isWin = process.platform === "win32";
    const wrapperScript = isWin ? "nexa-cc-engine.cmd" : "nexa-cc-engine.sh";
    const wrapperPath = path.join(opts.projectRoot, wrapperScript);
    const useWrapper = existsSync(wrapperPath);
    const spawnCmd = useWrapper
      ? wrapperPath
      : pyExe;
    const spawnArgs = useWrapper
      ? [opts.permissionMode || "default"]
      : ["-u", "src/main.py"];
    this.proc = spawn(spawnCmd, spawnArgs, {
      cwd: opts.projectRoot, env,
      stdio: ["pipe", "pipe", "pipe"],
      shell: useWrapper,
    });
    this.rl = readline.createInterface({ input: this.proc.stdout });
    this.rl.on("line", (line) => {
      try {
        const ev = JSON.parse(line) as EngineEvent;
        if (ev.type === "ready") { this.ready = true; if (this.startupTimer) clearTimeout(this.startupTimer); }
        this.onEvent(ev);
      } catch { /* non-JSON ignored */ }
    });
    this.proc.stderr.on("data", (data: Buffer) => {
      const text = data.toString("utf-8").trim();
      if (text) this.stderrBuf.push(text);
    });
    this.proc.on("exit", (code) => {
      if (this.startupTimer) clearTimeout(this.startupTimer);
      if (code !== 0 && code !== null) {
        const stderr = this.stderrBuf.join("\n").slice(-500);
        this.onEvent({ type: "error", message: `Engine exited (code ${code}): ${stderr}` });
      }
      this.onExit();
    });
    // Startup timeout: nexa runtime import takes ~30s; allow 90s before giving up
    this.startupTimer = setTimeout(() => {
      if (!this.ready) {
        this.onEvent({ type: "error", message: "Engine startup timeout (90s). The Nexa runtime takes ~30s to import. Check that Python + pydantic are installed." });
        this.close();
      }
    }, 90000);
  }

  send(obj: unknown): void { this.proc.stdin.write(JSON.stringify(obj) + "\n"); }
  sendMessage(content: string): void { this.send({ type: "message", content }); }
  sendCommand(name: string): void { this.send({ type: "command", name }); }
  sendPermissionResponse(requestId: number, approved: boolean, decision?: string): void {
    this.send({ type: "permission_response", request_id: requestId, approved, decision: decision || (approved ? "allow_once" : "deny") });
  }
  // Phase 15 H5: send mode change to engine
  sendSetMode(mode: string): void { this.send({ type: "set_mode", mode }); }
  sendCancel(): void { this.send({ type: "cancel" }); }
  sendExit(): void { this.send({ type: "exit" }); }
  close(): void { try { this.proc.kill(); } catch { /* noop */ } }
}
