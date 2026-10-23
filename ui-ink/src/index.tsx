import React from 'react';
import { render } from 'ink';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';
import { App } from './App.js';

if (Number(process.versions.node.split('.')[0]) < 20) throw new Error('Nexa Code requires Node.js 20 or later');
const { values } = parseArgs({
  options: {
    cwd: { type: 'string', default: process.cwd() },
    session: { type: 'string' },
    model: { type: 'string' },
    provider: { type: 'string', default: 'chat' },
    fixture: { type: 'string' },
    mode: { type: 'string', default: 'default' },
  },
});
if (!process.stdin.isTTY) {
  process.stderr.write(
    'Interactive UI requires a TTY. Use uv run nexa-code-engine --cwd <workspace> for JSON Lines mode.\n',
  );
  process.exitCode = 1;
} else {
  const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
  render(
    <App
      options={{
        projectRoot,
        cwd: path.resolve(values.cwd!),
        permissionMode: values.mode,
        session: values.session,
        model: values.model,
        provider: values.provider,
        fixture: values.fixture ? path.resolve(values.fixture) : undefined,
      }}
    />,
    { exitOnCtrlC: false },
  );
}
