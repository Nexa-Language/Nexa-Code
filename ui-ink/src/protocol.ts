export const PROTOCOL_VERSION = 1;
type Base = { version: 1; sequence: number; session_id: string | null; run_id: string | null; call_id: string | null };
export type Approval = {
  type: 'permission_request';
  tool: string;
  args: Record<string, unknown>;
  cwd: string;
  provenance: string;
  mode: string;
  diff: string;
};
export type EngineEvent =
  | OpenEvent
  | (Base &
      (
        | { type: 'ready'; model: string; cwd: string; mode: string; migration: string[] }
        | { type: 'session_info'; cwd: string; model: string; mode: string; checkpoint: string | null }
        | { type: 'session_history'; messages: Array<{ role: 'user' | 'assistant'; content: string }> }
        | { type: 'assistant_token'; content: string }
        | { type: 'tool_call'; name: string; args: Record<string, unknown> }
        | { type: 'tool_result'; name: string; result: string; success: boolean }
        | Approval
        | { type: 'command_result'; name: string; result: string }
        | { type: 'model_list'; current: string; models: Array<{ name: string }> }
        | { type: 'session_list'; sessions: Array<{ id: string; title: string; model: string; created_at: number }> }
        | { type: 'done'; reply: string; status: string; error: string | null }
        | { type: 'error'; code: string; message: string }
        | { type: 'info'; message: string }
        | { type: 'mode_changed'; mode: string }
        | { type: 'session_end'; clean: boolean; reason: string }
        | { type: 'runtime_event'; event: Record<string, unknown> }
        | {
            type: 'run_state';
            status: string;
            error: string | null;
            model_calls: number;
            tool_calls: number;
            elapsed: number;
            usage: { input_tokens: number; output_tokens: number };
            limits: Record<string, unknown>;
          }
        | {
            type: 'artifact';
            artifact_id?: string;
            name?: string;
            path?: string;
            characters?: number;
            preview?: string;
          }
        | {
            type: 'question';
            questions: Array<{ question: string; options?: Array<{ label: string; description?: string }> }>;
          }
        | { type: 'ui_setting'; name: string; value: string }
        | { type: 'request_completed'; request_id: string }
      ));

function object(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}
export function parseEvent(line: string): EngineEvent {
  if (Buffer.byteLength(line) > 2_000_000) throw new Error('Event exceeds 2 MB');
  const value: unknown = JSON.parse(line);
  if (!object(value) || value.version !== 1 || !Number.isSafeInteger(value.sequence) || Number(value.sequence) < 1)
    throw new Error('Invalid protocol envelope/version');
  for (const key of ['session_id', 'run_id', 'call_id'])
    if (value[key] !== null && typeof value[key] !== 'string') throw new Error(`Invalid ${key}`);
  if (typeof value.type === 'string' && value.type.startsWith('open_')) return parseOpenEvent(value);
  const required: Record<string, string[]> = {
    ready: ['model', 'cwd', 'mode'],
    session_info: ['cwd', 'model', 'mode'],
    session_history: [],
    assistant_token: ['content'],
    tool_call: ['name'],
    tool_result: ['name', 'result'],
    permission_request: ['tool', 'cwd', 'provenance', 'mode', 'diff'],
    command_result: ['name', 'result'],
    model_list: ['current'],
    session_list: [],
    done: ['reply', 'status'],
    error: ['code', 'message'],
    info: ['message'],
    mode_changed: ['mode'],
    session_end: ['reason'],
    runtime_event: [],
    run_state: ['status'],
    artifact: [],
    question: [],
    ui_setting: ['name', 'value'],
    request_completed: ['request_id'],
  };
  if (typeof value.type !== 'string' || !(value.type in required)) throw new Error('Unknown event type');
  for (const key of required[value.type]!)
    if (typeof value[key] !== 'string') throw new Error(`Invalid ${value.type}.${key}`);
  if (
    ['tool_call', 'permission_request'].includes(value.type) &&
    (!object(value.args) || !value.call_id || !value.run_id)
  )
    throw new Error('Invalid call parameters/identity');
  if (value.type === 'tool_result' && (typeof value.success !== 'boolean' || !value.call_id))
    throw new Error('Invalid tool result');
  if (value.type === 'runtime_event' && (!object(value.event) || typeof value.event.event !== 'string'))
    throw new Error('Invalid runtime event');
  if (
    value.type === 'run_state' &&
    (!object(value.usage) ||
      typeof value.usage.input_tokens !== 'number' ||
      typeof value.usage.output_tokens !== 'number' ||
      !object(value.limits))
  )
    throw new Error('Invalid run state');
  if (value.type === 'session_end' && typeof value.clean !== 'boolean') throw new Error('Invalid shutdown result');
  if (
    value.type === 'session_history' &&
    (!Array.isArray(value.messages) ||
      value.messages.some(
        (item) =>
          !object(item) || !['user', 'assistant'].includes(String(item.role)) || typeof item.content !== 'string',
      ))
  )
    throw new Error('Invalid session history');
  if (value.type === 'artifact') {
    for (const key of ['artifact_id', 'name', 'path', 'preview'])
      if (value[key] !== undefined && typeof value[key] !== 'string') throw new Error('Invalid artifact');
  }
  if (value.type === 'run_state')
    for (const key of ['elapsed', 'model_calls', 'tool_calls'])
      if (typeof value[key] !== 'number' || !Number.isFinite(value[key])) throw new Error('Invalid run counter');
  if (
    value.type === 'ready' &&
    (!Array.isArray(value.migration) || value.migration.some((item) => typeof item !== 'string'))
  )
    throw new Error('Invalid migration notices');
  if (
    value.type === 'model_list' &&
    (!Array.isArray(value.models) || value.models.some((item) => !object(item) || typeof item.name !== 'string'))
  )
    throw new Error('Invalid model list');
  if (
    value.type === 'session_list' &&
    (!Array.isArray(value.sessions) ||
      value.sessions.some(
        (item) =>
          !object(item) ||
          typeof item.id !== 'string' ||
          typeof item.title !== 'string' ||
          typeof item.model !== 'string' ||
          typeof item.created_at !== 'number',
      ))
  )
    throw new Error('Invalid session list');
  if (
    value.type === 'question' &&
    (!Array.isArray(value.questions) ||
      value.questions.some(
        (item) =>
          !object(item) ||
          typeof item.question !== 'string' ||
          (item.options !== undefined &&
            (!Array.isArray(item.options) ||
              item.options.some((option) => !object(option) || typeof option.label !== 'string'))),
      ))
  )
    throw new Error('Invalid question');
  return value as EngineEvent;
}
import { parseOpenEvent, type OpenEvent } from './open/protocol.js';
