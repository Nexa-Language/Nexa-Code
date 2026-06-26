// engine.ts — subprocess 桥：spawn Nexa 引擎，JSON 行协议
// P0 Fix 1: 正确 Python 检测 + stderr 可见 + 退出报错不静默
// Phase 15 H3: turn_status / thinking 事件 + H5: set_mode 事件 + H6: 语义分离
import { spawn, ChildProcessWithoutNullStreams, execSync } from "node:child_process";
import * as path from "node:path";
import * as readline from "node:readline";

export type EngineEvent =
  | { type: "ready"; model: string }
  | { type: "assistant_token"; content: string }
  | { type: "tool_call"; name: string; args: unknown }
  | { type: "tool_result"; name: string; result: string }
  | { type: "permission_request"; request_id: number; tool: string; args: string }
  | { type: "command_result"; name: string; result: string }
  | { type: "done"; reply: string }
  | { type: "error"; message: string }
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
    } as Record<string, string>;
    this.proc = spawn(pyExe, ["src/main.py"], {
      cwd: opts.projectRoot, env, stdio: ["pipe", "pipe", "pipe"],
    });
    this.rl = readline.createInterface({ input: this.proc.stdout });
    this.rl.on("line", (line) => {
      try {
        const ev = JSON.parse(line) as EngineEvent;
        this.onEvent(ev);
      } catch { /* non-JSON ignored */ }
    });
    this.proc.stderr.on("data", (data: Buffer) => {
      const text = data.toString("utf-8").trim();
      if (text) this.stderrBuf.push(text);
    });
    this.proc.on("exit", (code) => {
      if (code !== 0 && code !== null) {
        const stderr = this.stderrBuf.join("\n").slice(-500);
        this.onEvent({ type: "error", message: `Engine exited (code ${code}): ${stderr}` });
      }
      this.onExit();
    });
  }

  send(obj: unknown): void { this.proc.stdin.write(JSON.stringify(obj) + "\n"); }
  sendMessage(content: string): void { this.send({ type: "message", content }); }
  sendCommand(name: string): void { this.send({ type: "command", name }); }
  sendPermissionResponse(requestId: number, approved: boolean): void {
    this.send({ type: "permission_response", request_id: requestId, approved });
  }
  // Phase 15 H5: send mode change to engine
  sendSetMode(mode: string): void { this.send({ type: "set_mode", mode }); }
  sendExit(): void { this.send({ type: "exit" }); }
  close(): void { try { this.proc.kill(); } catch { /* noop */ } }
}
