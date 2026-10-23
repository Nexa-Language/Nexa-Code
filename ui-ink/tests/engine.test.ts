import assert from 'node:assert/strict';
import test from 'node:test';
import { Engine } from '../src/engine.js';
import type { EngineEvent } from '../src/protocol.js';

function fixture(script: string, timeout = 3000): Promise<EngineEvent[]> {
  return new Promise((resolve, reject) => {
    const events: EngineEvent[] = [];
    const deadline = setTimeout(() => reject(new Error('Child did not close')), 6500);
    new Engine(
      (event) => events.push(event),
      () => {
        clearTimeout(deadline);
        resolve(events);
      },
      {
        projectRoot: process.cwd(),
        cwd: process.cwd(),
        startupTimeout: timeout,
        command: { executable: process.execPath, args: ['-e', script] },
      },
    );
  });
}
test('malformed subprocess output raises protocol error and closes child', async () => {
  const events = await fixture(
    "console.log('not json');process.stdin.resume();process.stdin.on('data',()=>process.exit(0))",
  );
  assert(events.some((event) => event.type === 'error' && event.code === 'PROTOCOL_ERROR'));
});
test('signal exit is visible', async () => {
  const events = await fixture("process.kill(process.pid,'SIGTERM')");
  assert(events.some((event) => event.type === 'error' && event.message.includes('SIGTERM')));
});
test('startup timeout cleans up an unresponsive child', async () => {
  const events = await fixture("process.stdin.resume();process.stdin.on('data',()=>process.exit(0))", 20);
  assert(events.some((event) => event.type === 'error' && event.code === 'STARTUP_TIMEOUT'));
});
