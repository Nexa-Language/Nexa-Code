import assert from 'node:assert/strict';
import test from 'node:test';
import { parseEvent } from '../src/protocol.js';
import { nativeCommand, initialOpenState, reduceOpenEvent } from '../src/open/state.js';

const base = {
  version: 1,
  sequence: 1,
  session_id: null,
  run_id: null,
  call_id: null,
  program_id: 'demo',
  source_revision: 'draft',
  active_revision: 'active',
  request_id: 'request',
  object_digest: 'object-digest',
};

test('native events preserve distinct revisions and exact selected activities', () => {
  const first = parseEvent(
    JSON.stringify({
      ...base,
      type: 'open_activity',
      activity_id: 'selected',
      domain: 'runtime',
      activity: {
        activity_id: 'selected',
        program_id: 'demo',
        revision: 'active',
        goal: 'answer',
        state: 'pending',
        result: null,
      },
    }),
  );
  const second = parseEvent(
    JSON.stringify({
      ...base,
      sequence: 2,
      type: 'open_activity',
      activity_id: 'other',
      domain: 'author',
      activity: {
        activity_id: 'other',
        program_id: 'demo',
        revision: 'draft',
        goal: 'answer',
        state: 'running',
        request_id: '',
        result: null,
      },
    }),
  );
  let state = reduceOpenEvent(initialOpenState('demo'), first);
  state = reduceOpenEvent(state, second);
  assert.equal(state.activities.length, 2);
  assert.equal(state.sourceRevision, 'draft');
  assert.equal(state.activeRevision, 'active');
  assert.deepEqual(nativeCommand('/cancel runtime selected', state), {
    type: 'open_cancel',
    program_id: 'demo',
    domain: 'runtime',
    activity_id: 'selected',
  });
});

test('native protocol rejects legacy identity and malformed nested state', () => {
  assert.throws(() =>
    parseEvent(
      JSON.stringify({
        ...base,
        type: 'open_activity',
        run_id: 'legacy',
        activity_id: 'a',
        domain: 'runtime',
        activity: {},
      }),
    ),
  );
  assert.throws(() => parseEvent(JSON.stringify({ ...base, type: 'open_status', snapshot: {} })));
  assert.throws(() =>
    parseEvent(JSON.stringify({ ...base, type: 'open_grant', proposal_id: 'p', grant_id: 4, grant: {} })),
  );
});

test('command parsing requires explicit goal and exact native identities', () => {
  const state = {
    ...initialOpenState('demo'),
    sourceRevision: 'draft',
    activeRevision: 'active',
    sourceDigest: 'source',
  };
  assert.throws(() => nativeCommand('/run', state), /goal/);
  assert.throws(() => nativeCommand('/cancel', state), /domain/);
  assert.throws(() => nativeCommand('/approve proposal user', state), /review/);
  assert.throws(() => nativeCommand('/mode bypass', state), /Unknown/);
  assert.deepEqual(nativeCommand('/run answer {"x":2}', state), {
    type: 'open_run',
    program_id: 'demo',
    goal: 'answer',
    inputs: '{"x":2}',
    expected_revision: 'draft',
    source_digest: 'source',
  });
});

test('foreign program results cannot replace displayed native state', () => {
  const event = parseEvent(
    JSON.stringify({
      ...base,
      program_id: 'other',
      type: 'open_result',
      domain: 'runtime',
      activity_id: 'a',
      result: {
        status: 'accepted',
        goal_name: 'answer',
        model_calls: 0,
        input_tokens: 0,
        output_tokens: 0,
        output_json: '42',
        reason: '',
        clarification: '',
        evidence: [],
      },
    }),
  );
  const state = initialOpenState('demo');
  assert.deepEqual(reduceOpenEvent(state, event), state);
});

test('source recovery paths survive native status validation and state refresh', () => {
  const snapshot = {
    program_id: 'demo',
    source_revision: 'draft',
    active_revision: null,
    source_digest: 'source',
    environment: '/tmp/environment.json',
    state_path: '/tmp/state.db',
    check: { program: null, obligations: [], diagnostics: [] },
    budget: { max_model_calls: 0, max_tokens: 100, timeout_seconds: 10 },
    runtime_activities: [],
    author_activities: [],
    pending_sync: null,
    effects: [],
    proposals: [],
    grants: [],
    source_recovery: [
      {
        sync_id: 'sync',
        state: 'conflict',
        original_path: '/tmp/.nexa-intent-id/original',
        temporary_path: '/tmp/.nexa-intent-id/replacement',
      },
    ],
  };
  const event = { ...base, type: 'open_status', capabilities: [], snapshot };
  const state = reduceOpenEvent(initialOpenState('demo'), parseEvent(JSON.stringify(event)));
  assert.equal(state.snapshot?.source_recovery?.[0]?.original_path, snapshot.source_recovery[0]!.original_path);
  assert.throws(() =>
    parseEvent(JSON.stringify({ ...event, snapshot: { ...snapshot, source_recovery: [{ original_path: 1 }] } })),
  );
});
