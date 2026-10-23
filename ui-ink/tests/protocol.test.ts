import assert from 'node:assert/strict';
import test from 'node:test';
import { parseEvent } from '../src/protocol.js';

const envelope = { version: 1, sequence: 1, session_id: 's', run_id: null, call_id: null };
test('rejects malformed JSON, unknown versions and unvalidated event payloads', () => {
  for (const input of [
    'oops',
    '[]',
    '{}',
    JSON.stringify({ ...envelope, version: 2, type: 'ready' }),
    JSON.stringify({ ...envelope, type: 'done', reply: 42 }),
    JSON.stringify({ ...envelope, type: 'question', questions: [{ question: 'Pick', options: {} }] }),
  ]) {
    assert.throws(() => parseEvent(input));
  }
});
test('keeps exact approval call ID and parameters', () => {
  const event = parseEvent(
    JSON.stringify({
      ...envelope,
      type: 'permission_request',
      run_id: 'run',
      call_id: 'call',
      tool: 'Write',
      args: { file_path: 'hello', content: 'x' },
      cwd: '/tmp',
      provenance: 'exact',
      mode: 'default',
      diff: '',
    }),
  );
  assert.equal(event.call_id, 'call');
  assert.equal(event.run_id, 'run');
  if (event.type === 'permission_request') assert.deepEqual(event.args, { file_path: 'hello', content: 'x' });
});
