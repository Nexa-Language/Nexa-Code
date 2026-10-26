# Open Programs in Nexa Code 3.0

Nexa Code offers an explicit Open Programs terminal alongside the existing 2.4 conversation workflow. The engine and Ink use Nexa v3.0.0 at `274379606e53c90d2d25774f6bb8984c777d0759`. Checking, compilation, evidence, runtime activities and patch application use the native SDK.

## Launch

```bash
./nexa-cc.sh --cwd /absolute/repository \
  --program maintain.nx --environment compiler-environment.json \
  --state .nexa/open-programs.sqlite3 --program-id maintain \
  --max-model-calls 4 --max-tokens 20000 --timeout 120
```

The same flags work with `uv run nexa-code-engine` or `nexa-cc-engine.sh` for JSON Lines clients. Paths are relative to `--cwd`. `--program-id` defaults to the source filename stem; `--state` defaults to `.nexa/open-programs.sqlite3`. `--docker-context` selects an existing Docker context. Keep the source, environment, state database and `.nx.lock` file together when restoring a workspace. Model budgets apply to each explicit operation; build and run are separate operations.

An environment binds a fixed OCI image, capabilities, deterministic checks and an optional model/provider. Credentials stay in the provider's configured environment variables. Native Open Programs use that environment instead of the conversation-mode `--model`, `--provider`, `--mode` or `--session` options. Startup and `/check` make zero model requests and start no OCI containers. A source file needs `language "3.0"`.

Before build, execution, Author resolve, proposal inspection, grant, apply or runtime resume, Code reloads the environment through Nexa and compares its semantic digest with the session's environment. A changed checker, image, capability or provider binding produces `environment_changed`; missing or invalid configuration produces `environment_unavailable`. Restart the client to load the intended environment, then rebuild and regenerate/review evidence as needed. Existing proposals still pass through native policy checks. JSON formatting alone does not invalidate the session. `/check`, `/status`, exact cancellation and patch recovery remain available.

For a credential-free first program, save this as `hello.nx`:

```nexa
language "3.0"
program Hello {
    goal answer() -> Int {
        stage runtime
        intent "Return 42"
        implementation value 42
    }
}
```

Save this as `compiler-environment.json`:

```json
{
  "image": "python@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704"
}
```

Launch with `--program hello.nx`, then enter `/build` and `/run answer`. Running the supplied implementation requires Docker and the pinned image. The UI displays errors for unavailable OCI, missing model configuration, exhausted budgets and rejected evidence.

## Commands

| Command | Behavior |
| --- | --- |
| `/check` | Native frontend diagnostics, source digest, goals and open obligations; zero model/OCI execution. |
| `/draft` | Store the checked source with the displayed draft revision as CAS. |
| `/build` | Build the checked source snapshot and activate the resulting native revision. |
| `/locked` | Replay the matching `.nx.lock` artifact with zero model calls. |
| `/revise` | Explicitly build/activate the edited source using the displayed draft revision as CAS. |
| `/run <goal> [JSON]` | Execute the explicitly named goal using the active, checked revision. |
| `/resolve <goal> [JSON]` | Resolve the named draft goal through AuthorProtocol; author activity stays separate from runtime activity. Checked source must have the same program semantics as the selected draft. Use `/draft` or `/build` after changing its intent; a mismatch creates no activity or model request. |
| `/maintain {"paths":["calc.py"],"request":"Fix add"}` | Snapshot exactly the selected repository paths, run the maintenance handler, then show the proposal, diff and evidence. JSON can also include `event` and an imported `capsule_id`. |
| `/status` | Refresh draft/active revisions, activities, effects, pending source sync and saved proposal/grant IDs. |
| `/cancel <runtime\|author> <activity-id>` | Cancel only the selected native activity. The resulting persistent state is displayed. |
| `/answer <clarification-id> <answer>` | Append the author answer to the stored draft and prepare an intent-only source diff. |
| `/sync <sync-id>` | Review the displayed diff and confirm `y` to synchronize the source with exact source digest and revision CAS. |
| `/reject-sync <sync-id>` | Keep the intent diff pending; build/run remain blocked until it is resolved. |
| `/proposal <proposal-id>` | Read the exact stored proposal and re-evaluate its current evidence. |
| `/approve <proposal-id> <actor>` | Ask for `y/n` confirmation of the displayed proposal; issue its exact, expiring native grant. |
| `/apply <proposal-id> <grant-id> [resume]` | Recheck native identity, evidence, grant and workspace baseline before applying. `resume` explicitly resumes a recovered interrupted apply. |
| `/recover <proposal-id>` | Inspect/reconcile the runtime's patch journal without authorizing a fresh application. |
| `/resume` | Recover stopped runtime activities/effects. Unknown external effects remain blocked for native reconciliation. |
| `/import <path>` | Import a native capsule, displaying its digest. |
| `/export {"path":"repair.json","activity_id":"...","source":"origin","creator":"name","license":"MIT"}` | Export an accepted runtime activity with explicit provenance. Export uses exclusive creation. |
| `/help`, `/exit` | List commands or close the host and request cancellation of its own exact activities. |

Model acceptance creates a proposal. The grant and application are separate explicit user actions. Conversation-mode tool rules, bypass and call IDs have no authority over native patches. An expired grant, changed active revision, changed repository file or stale/revoked evidence produces a visible rejection.

## Drafts, source edits and recovery

The UI displays `Draft` and `Active` revision IDs separately. Runtime activities stay pinned to their own revision, while AuthorProtocol operates on a draft. One mutating operation runs in the client at a time; `/check`, `/status` and exact-ID `/cancel` remain available while it is active.

An author answer changes stored intent before changing the `.nx` file. Code writes a durable sync record before submitting the answer, locates the intent string only inside the native goal span, and checks that the complete replacement ProgramIR matches the clarified draft. Parameters named `intent`, comments and original LF/CRLF bytes are preserved outside the replaced string. After confirmation, the source is written with a digest check and the native revision is committed with CAS. User edits and rejected syncs keep build/run blocked. An answer made by another client is detected through native revision/events; finish that client's source synchronization before building from Code.

Before moving a source file, a separate durable write-intent records its recovery directory, preserving the original `SourceSync` record format and IDs. Startup, `/check`, `/status` and `/sync` recover interrupted filesystem stages. A missing source is restored from its recorded original using a no-replace link; an existing user file is preserved. `/sync` still needs explicit confirmation to complete the native revision. This covers process death between retiring the original and installing the new file, as well as interruption after the file or revision was committed.

`/status` and the native panel expose `source_recovery` entries with `original_path`, `temporary_path`, `state` and `sync_id`. Recovery files live beside the source in `.nexa-intent-<id>/`: `original` retains the previous inode, including writes from an editor that already had it open; `replacement` is the staged file and may already have been cleaned up. Code preserves originals after successful sync. Keep these directories with the state database during recovery. Once the relevant editors are closed and any retained edits have been saved or reconciled, these recovery directories may be manually archived or removed. Conflicting copies require review before retrying the pending diff; rejecting and reconfirming the same diff does not discard them. Recovery never overwrites a recreated source or follows a replacement symlink. Old pre-fix crashes without a recorded write-intent require manual restoration of their retained file; Code reports `source_recovery_required` instead of guessing which random backup belongs to the source.

Build passes a checked snapshot to native `ProgramSession.activate`, so an editor save cannot substitute different source into the compile. A changed live file after compilation returns `source_conflict`; refresh and review the source before continuing. Runtime creation also verifies the exact revision before resolving a candidate.

Activities are restored by resolving native event object digests, then reading each exact ID through `RuntimeController.activity`. Restarting Code shows activities created by other processes. Close cancels activities owned by this host; it leaves unrelated activities unchanged. A stalled worker produces an unclean shutdown result. Check native state before recovering an interrupted controller.

## JSON Lines extension

Transport version remains `1`. Native mode announces `open_ready` with the `open_programs_3` capability; legacy startup continues to announce `ready`. Native requests are strict `open_*` types defined in `nexa_code/open_protocol.py`; events are validated by `open_events.py` and `ui-ink/src/open/protocol.ts`.

```json
{"version":1,"request_id":"check-1","type":"open_check","program_id":"maintain"}
{"version":1,"request_id":"cancel-1","type":"open_cancel","program_id":"maintain","domain":"runtime","activity_id":"selected-native-id"}
```

Native events carry `program_id`, `source_revision`, `active_revision` and `request_id`; activity events add `domain`, `activity_id` and `object_digest`. Proposal/grant events carry their own IDs. Legacy `session_id`, `run_id` and `call_id` stay null in native events. Check the source digest and draft revision returned by status before sending `open_build`, `open_run`, `open_resolve`, `open_draft` or `open_revise`. `open_run` also accepts an explicit `capsule_id`.

## Reproducible verification

```bash
uv run pytest -q
docker pull python@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704
NEXA_CODE_OCI=1 uv run pytest -q -m oci
uv run python scripts/pty_open_smoke.py
```

The OCI fixture supplies one recorded model proposal, executes its candidate and repository regression check inside the pinned image, and asserts zero model calls for check/locked replay. It covers explicit grant, apply, capsule, stale evidence, expired grants, workspace drift and environment changes in a long-lived client. Process-death tests exit inside source writes and then launch the actual host to verify recovery. The PTY harness drives the actual built Ink UI and engine. See [native PTY evidence](evidence/ink-open-pty.txt) and the [2.4 compatibility PTY](evidence/ink-pty.txt).
