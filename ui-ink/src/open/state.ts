import type { EngineEvent } from '../protocol.js';
import type { Activity, Proposal, Snapshot, SourceSync } from './protocol.js';

export type OpenState = {
  programId: string;
  sourceRevision: string | null;
  activeRevision: string | null;
  sourceDigest: string;
  ready: boolean;
  busy: boolean;
  pendingRequest: string | null;
  snapshot: Snapshot | null;
  activities: Array<Activity & { domain: 'runtime' | 'author' }>;
  proposal: Proposal | null;
  grant: { proposalId: string; grantId: string } | null;
  sync: SourceSync | null;
  logs: string[];
  status: string;
};
export function initialOpenState(programId: string): OpenState {
  return {
    programId,
    sourceRevision: null,
    activeRevision: null,
    sourceDigest: '',
    ready: false,
    busy: false,
    pendingRequest: null,
    snapshot: null,
    activities: [],
    proposal: null,
    grant: null,
    sync: null,
    logs: [],
    status: 'starting',
  };
}
export function reduceOpenEvent(state: OpenState, event: EngineEvent): OpenState {
  if (event.type === 'error')
    return { ...state, logs: [...state.logs, `${event.code}: ${event.message}`], status: 'error' };
  if (event.type === 'request_completed')
    return event.request_id === state.pendingRequest ? { ...state, busy: false, pendingRequest: null } : state;
  if (event.type === 'session_end')
    return { ...state, ready: false, busy: false, status: event.clean ? 'closed' : event.reason };
  if (!('program_id' in event) || event.program_id !== state.programId) return state;
  const next = { ...state, sourceRevision: event.source_revision, activeRevision: event.active_revision };
  switch (event.type) {
    case 'open_ready':
    case 'open_status':
      return {
        ...next,
        ready: true,
        snapshot: event.snapshot,
        sourceDigest: event.snapshot.source_digest,
        sync: event.snapshot.pending_sync,
        activities: [
          ...event.snapshot.runtime_activities.map((item) => ({ ...item, domain: 'runtime' as const })),
          ...event.snapshot.author_activities.map((item) => ({ ...item, domain: 'author' as const })),
        ],
        status: event.snapshot.pending_sync ? 'source sync pending' : 'ready',
      };
    case 'open_activity':
      return {
        ...next,
        activities: [
          ...state.activities.filter((item) => item.activity_id !== event.activity_id || item.domain !== event.domain),
          { ...event.activity, domain: event.domain },
        ],
        status: `${event.domain} ${event.activity.state}`,
      };
    case 'open_result':
      return {
        ...next,
        status: event.result.status,
        logs: [
          ...state.logs,
          `${event.result.goal_name}: ${event.result.status} · ${event.result.model_calls} model calls · ${event.result.input_tokens + event.result.output_tokens} tokens\n${event.result.reason || event.result.output_json}`,
        ],
      };
    case 'open_proposal':
      return { ...next, proposal: event, grant: null, status: 'proposal awaiting review' };
    case 'open_grant':
      return {
        ...next,
        grant: { proposalId: event.proposal_id, grantId: event.grant_id },
        logs: [
          ...state.logs,
          `Grant ${event.grant_id} · expires ${new Date(event.grant.expires_at * 1000).toISOString()}`,
        ],
        status: 'grant issued; apply explicitly',
      };
    case 'open_applied':
      return {
        ...next,
        status: event.result.state,
        logs: [
          ...state.logs,
          `${event.result.state}: ${event.proposal_id}\n${event.result.reason || event.result.written.join(', ')}`,
        ],
      };
    case 'open_source_sync':
      return {
        ...next,
        sync: event.sync.state === 'applied' ? null : { ...event.sync, sync_id: event.sync_id },
        status: `source sync ${event.sync.state}`,
      };
    case 'open_capsule':
      return { ...next, logs: [...state.logs, `${event.action}: ${event.capsule_id}\n${event.path}`] };
  }
}

export const OPEN_HELP =
  '/check /draft /build /locked /revise /status /resume\n/run <goal> [JSON] · /resolve <goal> [JSON]\n/maintain {"paths":["file"],"request":"change"}\n/cancel <runtime|author> <activity-id>\n/answer <clarification-id> <answer>\n/sync <sync-id> · /reject-sync <sync-id>\n/proposal <id> · /approve <proposal-id> <actor>\n/apply <proposal-id> <grant-id> [resume] · /recover <proposal-id>\n/import <path> · /export {"path":"file","activity_id":"id","source":"origin","creator":"name","license":"MIT"} · /exit';

export function nativeCommand(input: string, state: OpenState): Record<string, unknown> {
  const [name, ...words] = input.trim().split(/\s+/);
  const rest = input.trim().slice(name!.length).trim();
  const base = { program_id: state.programId };
  const source = { expected_revision: state.sourceRevision, source_digest: state.sourceDigest };
  if (['/check', '/status', '/resume'].includes(name!)) return { type: `open_${name!.slice(1)}`, ...base };
  if (['/build', '/locked', '/revise', '/draft'].includes(name!))
    return { type: `open_${name!.slice(1)}`, ...base, ...source };
  if (name === '/run' || name === '/resolve') {
    if (!words[0]) throw new Error('Select an explicit goal');
    const inputs = rest.slice(words[0].length).trim() || '{}';
    JSON.parse(inputs);
    return { type: name === '/run' ? 'open_run' : 'open_resolve', ...base, ...source, goal: words[0], inputs };
  }
  if (name === '/maintain' || name === '/export') {
    const value: unknown = JSON.parse(rest);
    if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('Expected a JSON object');
    return {
      ...value,
      ...base,
      ...(name === '/maintain' ? source : {}),
      type: name === '/maintain' ? 'open_maintain' : 'open_export',
    };
  }
  if (name === '/cancel') {
    if (!['runtime', 'author'].includes(words[0] ?? '') || !words[1] || words.length !== 2)
      throw new Error('Select domain and exact activity ID');
    return { type: 'open_cancel', ...base, domain: words[0], activity_id: words[1] };
  }
  if (name === '/answer') {
    if (!words[0] || words.length < 2) throw new Error('Select clarification ID and answer');
    return {
      type: 'open_answer',
      ...base,
      ...source,
      clarification_id: words[0],
      answer: rest.slice(words[0].length).trim(),
    };
  }
  if (name === '/sync' || name === '/reject-sync') {
    if (!words[0] || words[0] !== state.sync?.sync_id) throw new Error('Review the exact pending source diff first');
    return { type: 'open_sync', ...base, sync_id: words[0], confirmed: name === '/sync' };
  }
  if (name === '/proposal' || name === '/recover') {
    if (!words[0]) throw new Error('Select proposal ID');
    return { type: name === '/proposal' ? 'open_proposal' : 'open_recover', ...base, proposal_id: words[0] };
  }
  if (name === '/approve') {
    if (words[0] !== state.proposal?.proposal_id || !words[1])
      throw new Error('First review this proposal diff/evidence, then supply your actor name');
    return {
      type: 'open_grant',
      ...base,
      proposal_id: words[0],
      actor: rest.slice(words[0].length).trim(),
      confirmed: true,
    };
  }
  if (name === '/apply') {
    if (!words[0] || !words[1] || words.length > 3 || (words[2] && words[2] !== 'resume'))
      throw new Error('Supply exact proposal and grant IDs, optionally resume');
    return { type: 'open_apply', ...base, proposal_id: words[0], grant_id: words[1], resume: words[2] === 'resume' };
  }
  if (name === '/import' && rest) return { type: 'open_import', ...base, path: rest };
  throw new Error('Unknown Open Programs command; /help lists commands');
}
