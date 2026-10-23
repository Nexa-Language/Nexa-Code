import React from 'react';
import { Box, Text } from 'ink';
import type { Theme } from '../theme.js';
export function Markdown({ text, theme }: { text: string; theme: Theme }): React.JSX.Element {
  let code = false;
  return (
    <Box flexDirection="column">
      {text.split('\n').map((line, index) => {
        if (line.startsWith('```')) {
          code = !code;
          return (
            <Text key={index} color={theme.muted}>
              {line}
            </Text>
          );
        }
        const color = code
          ? line.startsWith('+')
            ? theme.success
            : line.startsWith('-')
              ? theme.danger
              : undefined
          : undefined;
        return (
          <Text key={index} color={color} bold={!code && /^#{1,4} /.test(line)} wrap="wrap">
            {line || ' '}
          </Text>
        );
      })}
    </Box>
  );
}
