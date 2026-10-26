export type Result = {
  status: 'accepted' | 'blocked' | 'rejected' | 'cancelled';
  goal_name: string;
  output_json: string;
  reason: string;
  clarification: string;
  model_calls: number;
  input_tokens: number;
  output_tokens: number;
  evidence: unknown[];
};
export type Activity = {
  activity_id: string;
  program_id: string;
  revision: string;
  goal: string;
  state: string;
  result: Result | null;
  request_id?: string;
};
export type SourceSync = { sync_id?: string; revision: string; diff: string; state: string; source_digest: string };
export type Snapshot = {
  program_id: string;
  source_revision: string | null;
  active_revision: string | null;
  source_digest: string;
  environment: string;
  state_path: string;
  check: {
    program: {
      name: string;
      goals: Array<{
        name: string;
        intent: string;
        stage: string;
        checks: string[];
        reviews: string[];
        implementation: unknown;
      }>;
    } | null;
    obligations: string[];
    diagnostics: Array<{ code: string; message: string; span: { line: number; column: number } }>;
  };
  budget: { max_model_calls: number; max_tokens: number; timeout_seconds: number };
  runtime_activities: Activity[];
  author_activities: Activity[];
  pending_sync: SourceSync | null;
  source_recovery?: Array<{ sync_id: string; state: string; original_path: string; temporary_path: string }>;
  effects: Array<{ operation_id: string; state: string }>;
  proposals: Array<{ proposal_id: string; revision: string; activity_id: string }>;
  grants: Array<{ proposal_id: string; grant_id: string; expires_at: number; revoked: boolean }>;
};
export type Proposal = {
  proposal_id: string;
  diff: string;
  baseline_digest: string;
  scope: string[];
  task_id: string;
  admission: { accepted: boolean; reasons: string[]; evidence_digests: string[] };
  evidence: Array<{
    evidence_id: string;
    record: { requirement: string; passed: boolean; kind: string };
    validity: { validity: string; reasons: string[] };
  }>;
};
type NativeBase = {
  version: 1;
  sequence: number;
  session_id: null;
  run_id: null;
  call_id: null;
  program_id: string;
  request_id: string | null;
  source_revision: string | null;
  active_revision: string | null;
};
export type OpenEvent = NativeBase &
  (
    | { type: 'open_ready' | 'open_status'; snapshot: Snapshot; capabilities: string[] }
    | {
        type: 'open_activity';
        domain: 'runtime' | 'author';
        activity_id: string;
        object_digest: string;
        activity: Activity;
      }
    | { type: 'open_result'; domain: 'runtime'; activity_id: string; result: Result }
    | ({ type: 'open_proposal' } & Proposal)
    | {
        type: 'open_grant';
        proposal_id: string;
        grant_id: string;
        grant: { actor: string; scope: string[]; expires_at: number };
      }
    | {
        type: 'open_applied';
        proposal_id: string;
        grant_id?: string;
        result: { state: string; reason: string; written: string[]; preserved: unknown[] };
      }
    | { type: 'open_source_sync'; sync_id: string; sync: SourceSync }
    | { type: 'open_capsule'; capsule_id: string; path: string; action: 'import' | 'export' }
  );

function object(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}
function strings(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === 'string');
}
function result(value: unknown): boolean {
  return (
    object(value) &&
    ['accepted', 'blocked', 'rejected', 'cancelled'].includes(String(value.status)) &&
    ['goal_name', 'output_json', 'reason', 'clarification'].every((key) => typeof value[key] === 'string') &&
    ['model_calls', 'input_tokens', 'output_tokens'].every(
      (key) => typeof value[key] === 'number' && Number.isFinite(value[key]),
    ) &&
    Array.isArray(value.evidence)
  );
}
function activity(value: unknown): boolean {
  return (
    object(value) &&
    ['activity_id', 'program_id', 'revision', 'goal', 'state'].every((key) => typeof value[key] === 'string') &&
    (value.result === null || result(value.result))
  );
}
function sync(value: unknown): boolean {
  return object(value) && ['revision', 'diff', 'state', 'source_digest'].every((key) => typeof value[key] === 'string');
}
function snapshot(value: unknown): boolean {
  if (
    !object(value) ||
    !['program_id', 'source_digest', 'environment', 'state_path'].every((key) => typeof value[key] === 'string') ||
    !object(value.check) ||
    !object(value.budget)
  )
    return false;
  const report = value.check;
  return (
    [value.source_revision, value.active_revision].every((item) => item === null || typeof item === 'string') &&
    (report.program === null ||
      (object(report.program) &&
        Array.isArray(report.program.goals) &&
        report.program.goals.every(
          (goal) =>
            object(goal) &&
            ['name', 'intent', 'stage'].every((key) => typeof goal[key] === 'string') &&
            strings(goal.checks) &&
            strings(goal.reviews),
        ))) &&
    strings(report.obligations) &&
    Array.isArray(report.diagnostics) &&
    report.diagnostics.every(
      (item) =>
        object(item) &&
        typeof item.code === 'string' &&
        typeof item.message === 'string' &&
        object(item.span) &&
        Number.isInteger(item.span.line) &&
        Number.isInteger(item.span.column),
    ) &&
    ['max_model_calls', 'max_tokens', 'timeout_seconds'].every(
      (key) => typeof (value.budget as Record<string, unknown>)[key] === 'number',
    ) &&
    Array.isArray(value.runtime_activities) &&
    value.runtime_activities.every(activity) &&
    Array.isArray(value.author_activities) &&
    value.author_activities.every(activity) &&
    (value.pending_sync === null ||
      (sync(value.pending_sync) && typeof (value.pending_sync as Record<string, unknown>).sync_id === 'string')) &&
    (value.source_recovery === undefined ||
      (Array.isArray(value.source_recovery) &&
        value.source_recovery.every(
          (item) =>
            object(item) &&
            ['sync_id', 'state', 'original_path', 'temporary_path'].every((key) => typeof item[key] === 'string'),
        ))) &&
    Array.isArray(value.effects) &&
    value.effects.every(
      (item) => object(item) && typeof item.operation_id === 'string' && typeof item.state === 'string',
    ) &&
    Array.isArray(value.proposals) &&
    value.proposals.every(
      (item) =>
        object(item) && ['proposal_id', 'revision', 'activity_id'].every((key) => typeof item[key] === 'string'),
    ) &&
    Array.isArray(value.grants) &&
    value.grants.every(
      (item) =>
        object(item) &&
        typeof item.proposal_id === 'string' &&
        typeof item.grant_id === 'string' &&
        typeof item.expires_at === 'number' &&
        typeof item.revoked === 'boolean',
    )
  );
}
export function parseOpenEvent(value: Record<string, unknown>): OpenEvent {
  if (
    value.run_id !== null ||
    value.call_id !== null ||
    value.session_id !== null ||
    typeof value.program_id !== 'string' ||
    !value.program_id ||
    ![value.request_id, value.source_revision, value.active_revision].every(
      (item) => item === null || typeof item === 'string',
    )
  )
    throw new Error('Invalid native program/revision identity');
  let valid = false;
  switch (value.type) {
    case 'open_ready':
    case 'open_status':
      valid = snapshot(value.snapshot) && strings(value.capabilities);
      break;
    case 'open_activity':
      valid =
        ['runtime', 'author'].includes(String(value.domain)) &&
        typeof value.activity_id === 'string' &&
        typeof value.object_digest === 'string' &&
        activity(value.activity) &&
        (value.activity as Activity).activity_id === value.activity_id &&
        (value.activity as Activity).program_id === value.program_id;
      break;
    case 'open_result':
      valid = value.domain === 'runtime' && typeof value.activity_id === 'string' && result(value.result);
      break;
    case 'open_proposal':
      valid =
        ['proposal_id', 'diff', 'baseline_digest', 'task_id'].every((key) => typeof value[key] === 'string') &&
        strings(value.scope) &&
        object(value.admission) &&
        typeof value.admission.accepted === 'boolean' &&
        Array.isArray(value.evidence) &&
        value.evidence.every(
          (item) =>
            object(item) &&
            typeof item.evidence_id === 'string' &&
            object(item.record) &&
            typeof item.record.requirement === 'string' &&
            typeof item.record.passed === 'boolean' &&
            object(item.validity) &&
            typeof item.validity.validity === 'string',
        );
      break;
    case 'open_grant':
      valid =
        typeof value.proposal_id === 'string' &&
        typeof value.grant_id === 'string' &&
        object(value.grant) &&
        typeof value.grant.actor === 'string' &&
        strings(value.grant.scope) &&
        typeof value.grant.expires_at === 'number';
      break;
    case 'open_applied':
      valid =
        typeof value.proposal_id === 'string' &&
        object(value.result) &&
        typeof value.result.state === 'string' &&
        typeof value.result.reason === 'string' &&
        strings(value.result.written) &&
        Array.isArray(value.result.preserved);
      break;
    case 'open_source_sync':
      valid = typeof value.sync_id === 'string' && sync(value.sync);
      break;
    case 'open_capsule':
      valid =
        ['capsule_id', 'path'].every((key) => typeof value[key] === 'string') &&
        ['import', 'export'].includes(String(value.action));
      break;
  }
  if (!valid) throw new Error('Invalid native event payload');
  return value as OpenEvent;
}
