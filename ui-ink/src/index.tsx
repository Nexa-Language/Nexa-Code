import React from 'react';
import { render } from 'ink';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';
import { App } from './App.js';
import { OpenApp } from './open/App.js';

if (Number(process.versions.node.split('.')[0]) < 20) throw new Error('Nexa Code requires Node.js 20 or later');
const { values } = parseArgs({
  options: {
    cwd: { type: 'string', default: process.cwd() },
    session: { type: 'string' },
    model: { type: 'string' },
    provider: { type: 'string', default: 'chat' },
    fixture: { type: 'string' },
    mode: { type: 'string', default: 'default' },
    program: { type: 'string' },
    environment: { type: 'string' },
    state: { type: 'string' },
    'program-id': { type: 'string' },
    'docker-context': { type: 'string' },
    'max-model-calls': { type: 'string' },
    'max-tokens': { type: 'string' },
    timeout: { type: 'string' },
  },
});
if (values.program && (values.mode !== 'default' || values.session || values.model))
  throw new Error('Open Programs use their compiler environment; omit legacy --mode, --session and --model flags');
if (!process.stdin.isTTY) {
  process.stderr.write(
    'Interactive UI requires a TTY. Use uv run nexa-code-engine --cwd <workspace> for JSON Lines mode.\n',
  );
  process.exitCode = 1;
} else {
  const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
  const Interface = values.program ? OpenApp : App;
  const workspace = path.resolve(values.cwd!);
  render(
    <Interface
      options={{
        projectRoot,
        cwd: path.resolve(values.cwd!),
        permissionMode: values.mode,
        session: values.session,
        model: values.model,
        provider: values.provider,
        fixture: values.fixture ? path.resolve(values.fixture) : undefined,
        program: values.program ? path.resolve(workspace, values.program) : undefined,
        programEnvironment: values.environment ? path.resolve(workspace, values.environment) : undefined,
        state: values.state ? path.resolve(workspace, values.state) : undefined,
        programId: values['program-id'] ?? (values.program ? path.basename(values.program, '.nx') : undefined),
        dockerContext: values['docker-context'],
        maxModelCalls: values['max-model-calls'],
        maxTokens: values['max-tokens'],
        timeout: values.timeout,
      }}
    />,
    { exitOnCtrlC: false },
  );
}
