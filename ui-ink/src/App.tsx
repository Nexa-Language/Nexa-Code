import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Box, Text, useApp, useInput } from 'ink';
import { Engine, type EngineOptions } from './engine.js';
import { COMMANDS } from './commands.js';
import { initialState, reduceEvent, type State } from './state.js';
import { themes } from './theme.js';
import { ApprovalPanel } from './components/ApprovalPanel.js';
import { Conversation } from './components/Conversation.js';
import { Composer } from './components/Composer.js';
import { StatusBar } from './components/StatusBar.js';
import { Markdown } from './components/Markdown.js';

export function App({ options }: { options: EngineOptions }): React.JSX.Element {
  const { exit } = useApp();
  const [state, setState] = useState<State>(() => initialState(options.cwd));
  const [input, setInput] = useState('');
  const [expanded, setExpanded] = useState(false);
  const [themeName, setThemeName] = useState<'graphite' | 'light'>('graphite');
  const [selected, setSelected] = useState(0);
  const [confirm, setConfirm] = useState('');
  const [history, setHistory] = useState<string[]>([]);
  const [historyIndex, setHistoryIndex] = useState(-1);
  const [vim, setVim] = useState<'off' | 'insert' | 'normal'>('off');
  const engine = useRef<Engine | null>(null);
  const exitArmed = useRef(0);
  const theme = themes[themeName];
  const matches = useMemo(
    () =>
      input.startsWith('/') && !input.includes(' ')
        ? COMMANDS.filter((command) => command.name.includes(input)).slice(0, 8)
        : [],
    [input],
  );
  useEffect(() => setSelected(0), [input, state.picker?.kind]);
  useEffect(() => {
    engine.current = new Engine(
      (event) => {
        if (event.type === 'ui_setting') {
          if (event.name === 'theme') setThemeName(event.value === 'light' ? 'light' : 'graphite');
          if (event.name === 'vim')
            setVim((value) =>
              event.value === 'normal' ? 'off' : event.value === 'vim' ? 'insert' : value === 'off' ? 'insert' : 'off',
            );
        }
        setState((value) => reduceEvent(value, event));
      },
      () => exit(),
      options,
    );
    return () => engine.current?.stop();
  }, []);
  const send = (request: Record<string, unknown>): void => {
    setState((s) => ({ ...s, busy: true, approval: null, picker: null, streaming: '' }));
    engine.current?.send(request);
  };
  const approval = (decision: string): void => {
    if (state.approval)
      send({ type: 'approve', run_id: state.approval.run_id, call_id: state.approval.call_id, decision });
    setConfirm('');
  };
  const submit = (value: string): void => {
    if (!value.trim() || state.approval) return;
    if (value === '/exit' || value === '/quit') {
      engine.current?.stop();
      return;
    }
    if (state.question) {
      engine.current?.send({ type: 'answer', call_id: state.question.call_id, content: value });
      setState((s) => ({ ...s, question: null }));
      setInput('');
      return;
    }
    if (state.busy || !state.ready || state.picker) return;
    setHistory((values) => [...values, value]);
    setHistoryIndex(-1);
    setInput('');
    if (value.startsWith('/')) send({ type: 'command', name: value });
    else {
      setState((s) => ({ ...s, entries: [...s.entries, { kind: 'user', text: value }] }));
      send({ type: 'message', content: value });
    }
  };
  useInput((keyInput, key) => {
    if (key.ctrl && keyInput === 'c') {
      if (state.busy || state.approval || state.question) engine.current?.cancel();
      else if (Date.now() - exitArmed.current < 2000) engine.current?.stop();
      else {
        exitArmed.current = Date.now();
        setState((s) => ({ ...s, entries: [...s.entries, { kind: 'system', text: 'Press Ctrl+C again to exit' }] }));
      }
      return;
    }
    if (state.approval) {
      if (confirm) {
        if (keyInput === 'y') approval(confirm);
        if (keyInput === 'n' || key.escape) setConfirm('');
        return;
      }
      if (keyInput === 'y') approval('allow_once');
      if (keyInput === 'n' || key.escape) approval('deny');
      if (keyInput === 's') setConfirm('allow_session');
      if (keyInput === 'p') setConfirm('allow_rule');
      return;
    }
    if (key.escape) {
      if (state.busy || state.question) engine.current?.cancel();
      else if (state.picker) setState((s) => ({ ...s, picker: null }));
      else if (vim !== 'off') setVim('normal');
      else setInput('');
      return;
    }
    if (key.ctrl && keyInput === 'o') {
      setExpanded((v) => !v);
      return;
    }
    if (key.tab && key.shift && !state.busy) {
      const modes = ['default', 'plan', 'auto'];
      send({ type: 'set_mode', mode: modes[(modes.indexOf(state.mode) + 1) % modes.length] });
      return;
    }
    if (state.picker) {
      if (key.upArrow) setSelected((i) => Math.max(0, i - 1));
      if (key.downArrow) setSelected((i) => Math.min(state.picker!.items.length - 1, i + 1));
      if (key.return) {
        const item = state.picker.items[selected];
        if (item)
          send(
            state.picker.kind === 'session'
              ? { type: 'resume', session_id: item.value }
              : { type: 'command', name: '/model ' + item.value },
          );
      }
      return;
    }
    if (vim === 'normal') {
      if (keyInput === 'i' || keyInput === 'a') setVim('insert');
      if (keyInput === 'x') setInput((v) => v.slice(0, -1));
      return;
    }
    if (matches.length) {
      if (key.upArrow) setSelected((i) => Math.max(0, i - 1));
      if (key.downArrow) setSelected((i) => Math.min(matches.length - 1, i + 1));
      if (key.tab) setInput(matches[selected]!.name + ' ');
    } else if (!input || historyIndex >= 0) {
      if (key.upArrow && history.length) {
        const i = historyIndex < 0 ? history.length - 1 : Math.max(0, historyIndex - 1);
        setHistoryIndex(i);
        setInput(history[i]!);
      }
      if (key.downArrow && historyIndex >= 0) {
        const i = historyIndex + 1;
        setHistoryIndex(i >= history.length ? -1 : i);
        setInput(history[i] ?? '');
      }
    }
  });
  return (
    <Box flexDirection="column" paddingX={1} gap={1}>
      <Box flexDirection="column">
        <Text bold color={theme.accent}>
          N / NEXA CODE
        </Text>
        <Text color={theme.muted}>A deliberate workspace for code · Nexa 3.0 · 2.4 conversation mode</Text>
      </Box>
      {!state.entries.length && (
        <Text>
          Inspect a repository, make a focused change, and verify the result. /help lists commands; /resume restores a
          checkpoint.
        </Text>
      )}
      <Conversation entries={state.entries} expanded={expanded} theme={theme} />
      {state.streaming && <Markdown text={state.streaming} theme={theme} />}
      <StatusBar state={state} theme={theme} />
      {state.approval && <ApprovalPanel approval={state.approval} confirm={confirm} theme={theme} />}
      {state.question && (
        <Box flexDirection="column">
          {state.question.questions.map((q, i) => (
            <Text key={i}>
              {q.question}
              {q.options ? ' · ' + q.options.map((o) => o.label).join(' / ') : ''}
            </Text>
          ))}
        </Box>
      )}
      {state.picker && (
        <Box borderStyle="single" borderColor={theme.line} flexDirection="column">
          <Text bold>{state.picker.kind === 'session' ? 'Saved sessions' : 'Choose model'}</Text>
          {state.picker.items.length ? (
            state.picker.items.map((item, i) => (
              <Text key={item.value} color={i === selected ? theme.accent : theme.muted}>
                {i === selected ? '› ' : '  '}
                {item.label}
              </Text>
            ))
          ) : (
            <Text>No saved items. Esc returns to input.</Text>
          )}
        </Box>
      )}
      {!state.approval && (
        <Composer
          value={input}
          onChange={(value) => {
            setInput(value);
            setHistoryIndex(-1);
          }}
          onSubmit={submit}
          enabled={state.ready && (!state.busy || Boolean(state.question)) && !state.picker && vim !== 'normal'}
          theme={theme}
          vim={vim === 'off' ? '' : vim}
        />
      )}
      {matches.length > 0 && !state.busy && !state.approval && !state.picker && (
        <Box flexDirection="column">
          {matches.map((item, i) => (
            <Text key={item.name} color={i === selected ? theme.accent : theme.muted}>
              {i === selected ? '› ' : '  '}
              {item.name} {item.desc}
            </Text>
          ))}
        </Box>
      )}
    </Box>
  );
}
