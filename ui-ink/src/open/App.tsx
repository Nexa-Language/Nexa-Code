import React, { useEffect, useRef, useState } from 'react';
import { Box, Text, useApp, useInput } from 'ink';
import { Engine, type EngineOptions } from '../engine.js';
import { Composer } from '../components/Composer.js';
import { themes } from '../theme.js';
import { initialOpenState, nativeCommand, OPEN_HELP, reduceOpenEvent, type OpenState } from './state.js';

const theme = themes.graphite;
export function OpenPanel({ state }: { state: OpenState }): React.JSX.Element {
  return (
    <Box flexDirection="column" gap={1}>
      <Box flexDirection="column">
        <Text bold color={theme.accent}>
          N / NEXA CODE · OPEN PROGRAMS 3.0
        </Text>
        <Text>
          {state.programId} · {state.status}
        </Text>
        <Text color={theme.muted}>
          {state.busy
            ? 'Operation in progress · /status /check /cancel available'
            : state.ready
              ? 'Ready for native command'
              : 'Connecting to native host'}
        </Text>
        <Text>
          Draft {state.sourceRevision ?? 'not stored'}
          {'\n'}Active {state.activeRevision ?? 'not built'}
        </Text>
        {state.snapshot && (
          <Text color={theme.muted}>
            Budget: {state.snapshot.budget.max_model_calls} model calls · {state.snapshot.budget.max_tokens} tokens ·{' '}
            {state.snapshot.budget.timeout_seconds}s{'\n'}Environment: {state.snapshot.environment}
          </Text>
        )}
      </Box>
      {state.snapshot?.check.program?.goals.map((goal) => (
        <Box key={goal.name} flexDirection="column">
          <Text bold>
            {goal.name} · {goal.stage} ·{' '}
            {state.snapshot!.check.obligations.includes(goal.name) ? 'open obligation' : 'implementation supplied'}
          </Text>
          <Text>{goal.intent}</Text>
          <Text color={theme.muted}>
            Checks: {goal.checks.join(', ') || 'typecheck'} · Reviews: {goal.reviews.length}
          </Text>
        </Box>
      ))}
      {state.snapshot?.check.diagnostics.map((item, index) => (
        <Text key={index} color={theme.danger}>
          {item.code} at {item.span.line}:{item.span.column}: {item.message}
        </Text>
      ))}
      {state.activities.map((item) => (
        <Box key={`${item.domain}:${item.activity_id}`} flexDirection="column">
          <Text>
            {item.domain} · {item.goal} · {item.state} · {item.activity_id}
          </Text>
          <Text color={theme.muted}>Revision {item.revision}</Text>
          {item.result?.clarification && (
            <Text color={theme.accent}>
              Clarification {item.request_id}: {item.result.clarification}
            </Text>
          )}
        </Box>
      ))}
      {state.snapshot?.effects.map((item) => (
        <Text key={item.operation_id} color={theme.danger}>
          Effect {item.state}: {item.operation_id} · reconcile through Nexa before execution
        </Text>
      ))}
      {state.snapshot?.proposals.map((item) => (
        <Text key={item.proposal_id}>
          Saved proposal: /proposal {item.proposal_id} · activity {item.activity_id}
        </Text>
      ))}
      {state.snapshot?.grants.map((item) => (
        <Text key={item.grant_id}>
          Saved grant {item.grant_id} · proposal {item.proposal_id} ·{' '}
          {item.revoked ? 'revoked' : new Date(item.expires_at * 1000).toISOString()}
        </Text>
      ))}
      {state.sync && (
        <Box borderStyle="single" borderColor={theme.accent} flexDirection="column">
          <Text bold>SOURCE INTENT REVIEW · {state.sync.state}</Text>
          <Text>{state.sync.diff}</Text>
          <Text>Sync ID {state.sync.sync_id}</Text>
          <Text>
            Confirm: /sync {state.sync.sync_id}
            {'\n'}Keep pending: /reject-sync {state.sync.sync_id}
          </Text>
        </Box>
      )}
      {state.snapshot?.source_recovery?.map((item) => (
        <Text key={item.original_path} color={theme.muted}>
          Source recovery {item.state}: {item.original_path}
          {'\n'}
          Staged file: {item.temporary_path}
          {'\n'}
          Preserve concurrent edits here before retrying source sync.
        </Text>
      ))}
      {state.proposal && (
        <Box borderStyle="single" borderColor={theme.accent} flexDirection="column">
          <Text bold>
            PATCH REVIEW · {state.proposal.admission.accepted ? 'accepted; permission required' : 'evidence blocked'}
          </Text>
          <Text>
            Proposal {state.proposal.proposal_id}
            {'\n'}Baseline {state.proposal.baseline_digest}
            {'\n'}Paths {state.proposal.scope.join(', ')}
          </Text>
          <Text>{state.proposal.diff}</Text>
          {state.proposal.evidence.map((item) => (
            <Text key={item.evidence_id}>
              {item.record.requirement}: {item.record.passed ? 'passed' : 'failed'} · {item.validity.validity} ·{' '}
              {item.evidence_id}
            </Text>
          ))}
          <Text>Grant exact proposal: /approve {state.proposal.proposal_id} &lt;your name&gt;</Text>
          {state.grant?.proposalId === state.proposal.proposal_id && (
            <Text>
              Apply: /apply {state.grant.proposalId} {state.grant.grantId}
            </Text>
          )}
        </Box>
      )}
      {state.logs.slice(-12).map((line, index) => (
        <Text key={index}>{line}</Text>
      ))}
    </Box>
  );
}

export function OpenApp({ options }: { options: EngineOptions }): React.JSX.Element {
  const { exit } = useApp();
  const [state, setState] = useState(() => initialOpenState(options.programId!));
  const [input, setInput] = useState('');
  const [confirmation, setConfirmation] = useState<Record<string, unknown> | null>(null);
  const engine = useRef<Engine | null>(null);
  const current = useRef(state);
  current.current = state;
  useEffect(() => {
    engine.current = new Engine(
      (event) => setState((value) => reduceOpenEvent(value, event)),
      () => exit(),
      options,
    );
    const timer = setInterval(() => {
      if (
        current.current.ready &&
        current.current.activities.some((item) => ['running', 'pending'].includes(item.state))
      )
        engine.current?.send({ type: 'open_status', program_id: options.programId });
    }, 1500);
    return () => {
      clearInterval(timer);
      engine.current?.stop();
    };
  }, []);
  const send = (request: Record<string, unknown>): void => {
    const control = ['open_cancel', 'open_status', 'open_check'].includes(String(request.type));
    const requestId = engine.current?.send(request) ?? null;
    if (!control)
      setState((value) => ({ ...value, busy: true, pendingRequest: requestId, status: String(request.type).slice(5) }));
  };
  useInput((value, key) => {
    if (confirmation) {
      if (value === 'y') {
        send(confirmation);
        setConfirmation(null);
      }
      if (value === 'n' || key.escape) setConfirmation(null);
    } else if (key.ctrl && value === 'c') engine.current?.stop();
  });
  const submit = (value: string): void => {
    setInput('');
    if (value.trim() === '/exit') {
      engine.current?.stop();
      return;
    }
    if (value.trim() === '/help') {
      setState((state) => ({ ...state, logs: [...state.logs, OPEN_HELP] }));
      return;
    }
    try {
      const request = nativeCommand(value, state);
      if (state.busy && !['open_cancel', 'open_status', 'open_check'].includes(String(request.type)))
        throw new Error('An operation is active; use /cancel with its domain and exact activity ID');
      if (request.type === 'open_grant' || (request.type === 'open_sync' && request.confirmed === true))
        setConfirmation(request);
      else send(request);
    } catch (error) {
      setState((state) => ({ ...state, logs: [...state.logs, String(error)] }));
    }
  };
  return (
    <Box flexDirection="column" paddingX={1} gap={1}>
      <OpenPanel state={state} />
      <Text color={theme.muted}>
        /help lists native commands · cancellation requires the selected domain + activity ID
      </Text>
      {confirmation ? (
        <Box borderStyle="single" flexDirection="column">
          <Text bold>
            Confirm{' '}
            {confirmation.type === 'open_grant' ? 'grant for the reviewed proposal' : 'write the reviewed intent diff'}?
          </Text>
          <Text>{String(confirmation.proposal_id ?? confirmation.sync_id)} · y confirm / n return</Text>
        </Box>
      ) : (
        <Composer value={input} onChange={setInput} onSubmit={submit} enabled={state.ready} theme={theme} vim="" />
      )}
    </Box>
  );
}
