import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { createInterface, type Interface } from 'node:readline';
import { parseEvent, type EngineEvent } from './protocol.js';
export type { EngineEvent } from './protocol.js';

export type EngineOptions = {
  projectRoot: string;
  cwd: string;
  permissionMode?: string;
  session?: string;
  model?: string;
  provider?: string;
  fixture?: string;
  program?: string;
  programEnvironment?: string;
  state?: string;
  programId?: string;
  dockerContext?: string;
  maxModelCalls?: string;
  maxTokens?: string;
  timeout?: string;
  command?: { executable: string; args: string[] };
  startupTimeout?: number;
  environment?: NodeJS.ProcessEnv;
};
export class Engine {
  private proc: ChildProcessWithoutNullStreams;
  private reader: Interface;
  private timers: NodeJS.Timeout[] = [];
  private ready = false;
  private closed = false;
  private stopping = false;
  private sequence = 0;
  private diagnosticSequence = 1_000_000_000;
  private frameBytes = 0;

  constructor(
    private onEvent: (event: EngineEvent) => void,
    private onExit: (code: number | null, signal: NodeJS.Signals | null) => void,
    opts: EngineOptions,
  ) {
    const args = ['run', '--project', opts.projectRoot, '--no-sync', 'nexa-code-engine', '--cwd', opts.cwd];
    if (!opts.program) args.push('--mode', opts.permissionMode ?? 'default');
    if (opts.program) args.push('--program', opts.program);
    if (opts.programEnvironment) args.push('--environment', opts.programEnvironment);
    if (opts.state) args.push('--state', opts.state);
    if (opts.programId) args.push('--program-id', opts.programId);
    if (opts.dockerContext) args.push('--docker-context', opts.dockerContext);
    if (opts.maxModelCalls) args.push('--max-model-calls', opts.maxModelCalls);
    if (opts.maxTokens) args.push('--max-tokens', opts.maxTokens);
    if (opts.timeout) args.push('--timeout', opts.timeout);
    if (opts.provider) args.push('--provider', opts.provider);
    if (opts.session) args.push('--session', opts.session);
    if (opts.model) args.push('--model', opts.model);
    if (opts.fixture) args.push('--fixture', opts.fixture);
    this.proc = spawn(opts.command?.executable ?? process.env.NEXA_UV ?? 'uv', opts.command?.args ?? args, {
      cwd: opts.cwd,
      env: { ...process.env, ...opts.environment, PYTHONUNBUFFERED: '1', PYTHONIOENCODING: 'utf-8' },
      stdio: ['pipe', 'pipe', 'pipe'],
      shell: false,
    });
    this.proc.stdout.on('data', (chunk: Buffer) => {
      if (this.stopping) return;
      for (let offset = 0; offset < chunk.length; ) {
        const newline = chunk.indexOf(10, offset);
        const end = newline < 0 ? chunk.length : newline;
        this.frameBytes += end - offset;
        if (this.frameBytes > 2_000_000) {
          this.error('PROTOCOL_ERROR', 'Event exceeds 2 MB');
          this.stop();
          this.proc.stdout.pause();
          return;
        }
        if (newline >= 0) this.frameBytes = 0;
        offset = end + 1;
      }
    });
    this.reader = createInterface({ input: this.proc.stdout });
    this.reader.on('line', (line) => {
      try {
        const event = parseEvent(line);
        if (event.sequence <= this.sequence) throw new Error('Non-monotonic event sequence');
        this.sequence = event.sequence;
        if (event.type === 'ready' || event.type === 'open_ready') {
          this.ready = true;
          if (!this.stopping) this.clearTimers();
        }
        this.onEvent(event);
      } catch (error) {
        this.error('PROTOCOL_ERROR', String(error));
        this.stop();
      }
    });
    this.proc.stderr.on('data', (chunk: Buffer) =>
      this.error('ENGINE_DIAGNOSTIC', chunk.toString('utf8').slice(0, 4000)),
    );
    this.proc.stdin.on('error', (error) => {
      if (!this.stopping) this.error('TRANSPORT_ERROR', error.message);
    });
    this.proc.on('error', (error) => this.error('STARTUP_ERROR', error.message));
    this.proc.on('close', (code, signal) => {
      this.closed = true;
      this.clearTimers();
      this.reader.close();
      if (!this.ready || code !== 0)
        this.error('ENGINE_EXIT', `Engine exited: code=${code ?? 'none'} signal=${signal ?? 'none'}`);
      this.onExit(code, signal);
    });
    this.later(() => {
      if (!this.ready) {
        this.error('STARTUP_TIMEOUT', 'Engine did not become ready within the startup deadline');
        this.stop();
      }
    }, opts.startupTimeout ?? 30000);
  }
  private error(code: string, message: string): void {
    this.onEvent({
      version: 1,
      sequence: this.diagnosticSequence++,
      session_id: null,
      run_id: null,
      call_id: null,
      type: 'error',
      code,
      message,
    });
  }
  private later(callback: () => void, ms: number): void {
    const timer = setTimeout(callback, ms);
    timer.unref();
    this.timers.push(timer);
  }
  private clearTimers(): void {
    this.timers.forEach(clearTimeout);
    this.timers = [];
  }
  send(request: Record<string, unknown>): string {
    const requestId = randomUUID();
    if (this.closed || this.proc.stdin.destroyed) {
      this.error('TRANSPORT_CLOSED', 'Engine is no longer connected');
      return requestId;
    }
    this.proc.stdin.write(JSON.stringify({ version: 1, request_id: requestId, ...request }) + '\n');
    return requestId;
  }
  cancel(): void {
    this.send({ type: 'cancel' });
  }
  stop(): void {
    if (this.stopping || this.closed) return;
    this.stopping = true;
    this.send({ type: 'exit' });
    this.later(() => {
      if (!this.closed) {
        this.proc.kill('SIGTERM');
        this.later(() => {
          if (!this.closed) this.proc.kill('SIGKILL');
        }, 1000);
      }
    }, 4000);
  }
}
