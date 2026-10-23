import React, { useEffect, useRef, useState } from 'react';
import { Box, Text, useInput } from 'ink';
import type { Theme } from '../theme.js';

type Props = {
  value: string;
  onChange: (value: string) => void;
  onSubmit: (value: string) => void;
  enabled: boolean;
  theme: Theme;
  vim: string;
};

export function Composer({ value, onChange, onSubmit, enabled, theme, vim }: Props): React.JSX.Element {
  const [cursor, setCursor] = useState(Array.from(value).length);
  const localValue = useRef(value);
  useEffect(() => {
    if (value !== localValue.current) setCursor(Array.from(value).length);
    localValue.current = value;
  }, [value]);
  const chars = Array.from(value);
  const position = Math.min(cursor, chars.length);
  const replace = (before: string[], added: string, after: string[]): void => {
    const next = before.join('') + added + after.join('');
    localValue.current = next;
    setCursor(before.length + Array.from(added).length);
    onChange(next);
  };
  useInput(
    (input, key) => {
      if (key.upArrow || key.downArrow || key.tab || key.escape) return;
      if (key.ctrl) {
        if (input === 'j') replace(chars.slice(0, position), '\n', chars.slice(position));
        if (input === 'a') setCursor(0);
        if (input === 'e') setCursor(chars.length);
        if (input === 'u') replace([], '', chars.slice(position));
        if (input === 'k') replace(chars.slice(0, position), '', []);
        if (input === 'w')
          replace(
            Array.from(
              chars
                .slice(0, position)
                .join('')
                .replace(/\s*\S+\s*$/, ''),
            ),
            '',
            chars.slice(position),
          );
        return;
      }
      if (key.return) {
        onSubmit(value);
        return;
      }
      if (key.leftArrow) {
        setCursor(Math.max(0, position - 1));
        return;
      }
      if (key.rightArrow) {
        setCursor(Math.min(chars.length, position + 1));
        return;
      }
      if (key.backspace || key.delete) {
        replace(chars.slice(0, Math.max(0, position - 1)), '', chars.slice(position));
        return;
      }
      if (!key.meta && input) replace(chars.slice(0, position), input, chars.slice(position));
    },
    { isActive: enabled },
  );
  return (
    <Box flexDirection="column">
      <Box>
        <Text color={theme.accent}>› </Text>
        {value ? (
          <Text>
            {chars.slice(0, position).join('')}
            <Text inverse={enabled}>{chars[position] ?? ' '}</Text>
            {chars.slice(position + 1).join('')}
          </Text>
        ) : (
          <Text color={theme.muted}>{enabled ? 'Ask Nexa, or / for commands' : 'Waiting for the current action…'}</Text>
        )}
      </Box>
      <Text color={theme.muted}>
        Enter send · Ctrl+J newline · Esc cancel · Ctrl+O details{vim ? ` · vim ${vim}` : ''}
      </Text>
    </Box>
  );
}
