import React from 'react';
import assert from 'node:assert/strict';
import test from 'node:test';
import { PassThrough } from 'node:stream';
import { render } from 'ink';
import { ApprovalPanel } from '../src/components/ApprovalPanel.js';
import { StatusBar } from '../src/components/StatusBar.js';
import { initialState } from '../src/state.js';
import { themes } from '../src/theme.js';
import { OpenPanel } from '../src/open/App.js';
import { initialOpenState, reduceOpenEvent } from '../src/open/state.js';

test('narrow and wide approval panels retain exact identity, arguments and policy scope', async () => {
  for (const width of [36, 100])
    for (const theme of Object.values(themes)) {
      const stream = new PassThrough();
      let output = '';
      stream.on('data', (chunk) => (output += String(chunk)));
      const stdout = Object.assign(stream, { columns: width, rows: 60, isTTY: false }) as unknown as NodeJS.WriteStream;
      const instance = render(
        <ApprovalPanel
          theme={theme}
          confirm=""
          approval={{
            version: 1,
            sequence: 1,
            type: 'permission_request',
            session_id: 's',
            run_id: 'run123',
            call_id: 'call123',
            tool: 'Write',
            cwd: '/tmp/project',
            args: { file_path: 'a.txt', content: 'hello' },
            provenance: 'exact call requires approval',
            mode: 'default',
            diff: '-old\n+new',
          }}
        />,
        { stdout, debug: true, patchConsole: false },
      );
      await new Promise((resolve) => setTimeout(resolve, 30));
      instance.unmount();
      assert.match(output, /call123/);
      assert.match(output, /hello/);
      assert.match(output, /Workspace/);
      assert.match(output, /persistent/);
    }
});
test('budget exhaustion has a visible terminal status', async () => {
  const stream = new PassThrough();
  let output = '';
  stream.on('data', (chunk) => (output += String(chunk)));
  const instance = render(
    <StatusBar theme={themes.graphite} state={{ ...initialState('/tmp'), status: 'budget_exhausted' }} />,
    {
      stdout: Object.assign(stream, { columns: 80 }) as unknown as NodeJS.WriteStream,
      debug: true,
      patchConsole: false,
    },
  );
  await new Promise((resolve) => setTimeout(resolve, 20));
  instance.unmount();
  assert.match(output, /budget_exhausted/);
});

test('native command readiness waits for the exact request completion', async () => {
  const busy = { ...initialOpenState('demo'), ready: true, busy: true, pendingRequest: 'grant-request' };
  const completion = {
    version: 1 as const,
    sequence: 3,
    session_id: null,
    run_id: null,
    call_id: null,
    type: 'request_completed' as const,
    request_id: 'status-request',
  };
  assert.equal(reduceOpenEvent(busy, completion).busy, true);
  const ready = reduceOpenEvent(busy, { ...completion, request_id: 'grant-request' });
  assert.equal(ready.busy, false);
  for (const [state, expected] of [
    [busy, 'Operation in progress'],
    [ready, 'Ready for native command'],
  ] as const) {
    const stream = new PassThrough();
    let output = '';
    stream.on('data', (chunk) => (output += String(chunk)));
    const instance = render(<OpenPanel state={state} />, {
      stdout: Object.assign(stream, { columns: 100 }) as unknown as NodeJS.WriteStream,
      debug: true,
      patchConsole: false,
    });
    await new Promise((resolve) => setTimeout(resolve, 20));
    instance.unmount();
    assert.match(output, new RegExp(expected));
  }
});
