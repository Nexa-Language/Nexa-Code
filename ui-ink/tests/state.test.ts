import assert from 'node:assert/strict';
import test from 'node:test';
import { initialState, reduceEvent } from '../src/state.js';
import type { EngineEvent } from '../src/protocol.js';

const base = { version: 1 as const, sequence: 1, session_id: 's', run_id: 'r', call_id: 'c' };
test('distinguishes cancellation, budget and tool failure from completion', () => {
  for (const status of ['cancelled', 'timed_out', 'budget_exhausted', 'failed']) {
    const state = reduceEvent(initialState('/tmp'), { ...base, type: 'done', reply: '', status, error: 'stop' });
    assert.equal(state.status, status);
    assert.equal(state.busy, false);
    assert.equal(state.entries.at(-1)?.kind, 'error');
  }
});
test('matches tool results by call ID, even for repeated tool names', () => {
  let state = initialState('/tmp');
  for (const id of ['a', 'b'])
    state = reduceEvent(state, { ...base, call_id: id, type: 'tool_call', name: 'Read', args: {} });
  state = reduceEvent(state, {
    ...base,
    call_id: 'a',
    type: 'tool_result',
    name: 'Read',
    result: 'first',
    success: true,
  });
  assert.equal(state.entries.find((e) => e.callId === 'a')?.text, 'first');
  assert.equal(state.entries.find((e) => e.callId === 'b')?.text, '');
});
