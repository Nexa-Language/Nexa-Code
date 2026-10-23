import React from 'react';
import { Box, Text } from 'ink';
import type { Entry } from '../state.js';
import type { Theme } from '../theme.js';
import { Markdown } from './Markdown.js';
export function Conversation({
  entries,
  expanded,
  theme,
}: {
  entries: Entry[];
  expanded: boolean;
  theme: Theme;
}): React.JSX.Element {
  return (
    <Box flexDirection="column" gap={1}>
      {entries.slice(-24).map((entry, index) => (
        <Box key={`${entry.callId ?? index}-${entry.kind}`} flexDirection="column">
          <Text bold color={entry.kind === 'error' ? theme.danger : entry.kind === 'user' ? theme.accent : theme.muted}>
            {entry.kind === 'user'
              ? 'YOU'
              : entry.kind === 'assistant'
                ? 'NEXA'
                : entry.kind === 'artifact'
                  ? 'ARTIFACT'
                  : entry.kind.toUpperCase()}
            {entry.name ? ` · ${entry.name}` : ''}
            {entry.kind === 'tool'
              ? ` · ${entry.success === undefined ? 'running' : entry.success ? 'completed' : 'failed'}`
              : ''}
          </Text>
          {entry.kind === 'tool' && (
            <Text color={theme.muted} wrap="wrap">
              {JSON.stringify(entry.args)}
            </Text>
          )}
          <Markdown theme={theme} text={expanded ? entry.text : entry.text.split('\n').slice(0, 12).join('\n')} />
          {!expanded && entry.text.split('\n').length > 12 && (
            <Text color={theme.muted}>… Ctrl+O shows full output · /export saves history</Text>
          )}
        </Box>
      ))}
    </Box>
  );
}
