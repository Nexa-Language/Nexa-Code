import type { EngineEvent } from './protocol.js';
export type Entry = {
  kind: 'user' | 'assistant' | 'tool' | 'system' | 'error' | 'artifact';
  text: string;
  callId?: string;
  name?: string;
  args?: unknown;
  success?: boolean;
};
export type State = {
  cwd: string;
  model: string;
  mode: string;
  sessionId: string;
  status: string;
  busy: boolean;
  ready: boolean;
  streaming: string;
  entries: Entry[];
  tokens: number;
  elapsed: number;
  calls: string;
  approval: Extract<EngineEvent, { type: 'permission_request' }> | null;
  question: Extract<EngineEvent, { type: 'question' }> | null;
  picker: { kind: 'session' | 'model'; items: Array<{ label: string; value: string }> } | null;
};
export function initialState(cwd: string): State {
  return {
    cwd,
    model: 'connecting',
    mode: 'default',
    sessionId: '',
    status: 'starting',
    busy: false,
    ready: false,
    streaming: '',
    entries: [],
    tokens: 0,
    elapsed: 0,
    calls: '',
    approval: null,
    question: null,
    picker: null,
  };
}
export function reduceEvent(state: State, event: EngineEvent): State {
  const next = { ...state, sessionId: event.session_id ?? state.sessionId };
  const append = (entry: Entry): State => ({ ...next, entries: [...next.entries, entry] });
  switch (event.type) {
    case 'ready':
      return {
        ...next,
        ready: true,
        status: 'ready',
        model: event.model,
        cwd: event.cwd,
        mode: event.mode,
        entries: [...next.entries, ...event.migration.map((text) => ({ kind: 'system' as const, text }))],
      };
    case 'session_info':
      return {
        ...next,
        cwd: event.cwd,
        model: event.model,
        mode: event.mode,
        entries: [],
        streaming: '',
        approval: null,
        question: null,
        status: event.checkpoint ? 'saved' : 'ready',
      };
    case 'session_history':
      return { ...next, entries: event.messages.map((item) => ({ kind: item.role, text: item.content })) };
    case 'assistant_token':
      return { ...next, streaming: next.streaming + event.content };
    case 'tool_call':
      return append({ kind: 'tool', callId: event.call_id!, name: event.name, args: event.args, text: '' });
    case 'tool_result':
      return {
        ...next,
        entries: next.entries.map((entry) =>
          entry.callId === event.call_id ? { ...entry, text: event.result, success: event.success } : entry,
        ),
      };
    case 'permission_request':
      return { ...next, busy: false, approval: event, status: 'waiting_approval' };
    case 'question':
      return { ...next, question: event, status: 'waiting_answer' };
    case 'mode_changed':
      return { ...next, mode: event.mode };
    case 'run_state':
      return {
        ...next,
        status: event.status,
        elapsed: event.elapsed,
        tokens: event.usage.input_tokens + event.usage.output_tokens,
        calls: `${event.model_calls} model / ${event.tool_calls} tool`,
      };
    case 'runtime_event':
      return { ...next, status: String(event.event.event) };
    case 'done':
      return {
        ...next,
        busy: false,
        approval: null,
        question: null,
        status: event.status,
        streaming: '',
        entries: [
          ...next.entries,
          ...(event.reply ? [{ kind: 'assistant' as const, text: event.reply }] : []),
          ...(event.status !== 'completed'
            ? [{ kind: 'error' as const, text: `${event.status}: ${event.error ?? 'stopped'}` }]
            : []),
        ],
      };
    case 'error':
      return { ...append({ kind: 'error', text: `${event.code}: ${event.message}` }), busy: false };
    case 'info':
      return append({ kind: 'system', text: event.message });
    case 'artifact':
      return append({
        kind: 'artifact',
        name: event.name ?? event.artifact_id,
        text: event.path ?? `${event.artifact_id ?? ''} · ${event.characters ?? 0} characters`,
      });
    case 'command_result':
      return event.result ? append({ kind: 'system', text: event.result }) : next;
    case 'model_list':
      return {
        ...next,
        picker: { kind: 'model', items: event.models.map((item) => ({ label: item.name, value: item.name })) },
      };
    case 'session_list':
      return {
        ...next,
        picker: {
          kind: 'session',
          items: event.sessions.map((item) => ({ label: `${item.title} · ${item.model}`, value: item.id })),
        },
      };
    case 'session_end':
      return { ...next, ready: false, busy: false, status: 'disconnected' };
    case 'request_completed':
      return { ...next, busy: false };
    case 'ui_setting':
      return next;
  }
}
