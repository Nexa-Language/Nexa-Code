import React from 'react';
import { Box, Text } from 'ink';
import type { EngineEvent } from '../protocol.js';
import type { Theme } from '../theme.js';
import { Markdown } from './Markdown.js';
export function ApprovalPanel({
  approval,
  confirm,
  theme,
}: {
  approval: Extract<EngineEvent, { type: 'permission_request' }>;
  confirm: string;
  theme: Theme;
}): React.JSX.Element {
  return (
    <Box borderStyle="single" borderColor={theme.accent} paddingX={1} flexDirection="column">
      <Text bold color={theme.accent}>
        APPROVAL · {approval.tool}
      </Text>
      <Text>
        Run {approval.run_id} · Call {approval.call_id}
      </Text>
      <Text color={theme.muted}>Workspace: {approval.cwd}</Text>
      <Text color={theme.muted}>
        Policy: {approval.provenance} · {approval.mode}
      </Text>
      <Text>{JSON.stringify(approval.args, null, 2)}</Text>
      {approval.diff && <Markdown theme={theme} text={approval.diff} />}
      {confirm ? (
        <>
          <Text color={theme.warning}>
            Save an exact-arguments rule for {confirm === 'allow_rule' ? 'this workspace on disk' : 'this session'}?
          </Text>
          <Text>y confirm · n back</Text>
        </>
      ) : (
        <>
          <Text>y allow this call · n deny · s session rule · p persistent rule</Text>
          <Text color={theme.muted}>Rules match this tool, workspace and every displayed argument exactly.</Text>
        </>
      )}
    </Box>
  );
}
