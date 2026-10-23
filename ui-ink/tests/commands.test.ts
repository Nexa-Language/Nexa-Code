import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { COMMANDS } from '../src/commands.js';
test('command menu retains every published legacy name and alias', () => {
  const names: string[] = JSON.parse(
    readFileSync(new URL('../../tests/fixtures/legacy-commands.json', import.meta.url), 'utf8'),
  );
  assert.deepEqual(COMMANDS.map((item) => item.name.slice(1)).sort(), names.sort());
});
