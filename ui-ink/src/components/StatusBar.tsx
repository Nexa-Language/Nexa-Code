import React from 'react';
import { Box, Text } from 'ink';
import type { State } from '../state.js';
import type { Theme } from '../theme.js';
export function StatusBar({ state, theme }: { state: State; theme: Theme }): React.JSX.Element {
  const stopped = ['failed', 'cancelled', 'timed_out', 'budget_exhausted'].includes(state.status);
  return (
    <Box flexDirection="column" borderStyle="single" borderColor={theme.line} paddingX={1}>
      <Text>
        <Text bold color={stopped ? theme.danger : theme.accent}>
          {state.status}
        </Text>{' '}
        · {state.model} · <Text color={state.mode === 'bypass' ? theme.warning : theme.muted}>{state.mode}</Text>
      </Text>
      <Text color={theme.muted}>
        {state.tokens} tokens · {state.elapsed.toFixed(1)}s · {state.calls || 'no calls yet'}
      </Text>
      <Text color={theme.muted} wrap="truncate-middle">
        {state.cwd} · {state.sessionId.slice(0, 12)}
      </Text>
    </Box>
  );
}
