# Native Codex delegation contract

Use native subagents with the active client's model, reasoning, provider and
authentication. Before dispatch, the coordinator creates a plain JSON declaration
at the active harness root's `.codex-delegations/<task_name>.json`. This directory
is beside
`.codex`, outside the protected configuration directory. `task_name` must contain
1–64 lowercase ASCII letters, digits or underscores and match the native spawn's
`task_name` exactly. Formats without that visible field are explicitly unsupported
and denied; the hook does not fall back to interpreting the message.

The hook validates declaration structure only. It does not inspect, decrypt or
rewrite the native message. A valid file does **not** prove that its content
matches the message, that the child can identify itself or that the worker read
or followed the declaration. The coordinator must check those conditions.
`SubagentStart` instructs the worker to require one exact coordinator-supplied
declaration pointer in its native task message: harness-root-relative
`.codex-delegations/<task_name>.json`, where the name matches `[a-z0-9_]{1,64}`.
The worker reads that record and compares objective, writable scope, dependencies
and checks with the assigned task. A missing, ambiguous, unsafe, unreadable or
inconsistent pointer/record means `blocked` without task work.

When trusted host metadata exposes the worker's native task identity, compare it
with the record. For canonical `/root/reader`, use final component `reader`;
a mismatch blocks work. Some isolated children do not receive caller-bound
identity metadata. When it is unavailable, do not fabricate identity from freeform
text: continue only the authorized declared scope and report
`native identity binding unverified` in the existing `risks` field. The explicit
pointer is a coordinator task instruction, not identity attestation. The
coordinator independently checks the actual native spawn name, exact declaration,
observed read and resulting diff. Missing host identity alone is not a new task gate.
Actual behavior still requires a real client fixture.

## Prepare each dispatch

1. Identify the active harness root that owns the executing
   `.codex/hooks/subagents.py`. Create its ordinary `.codex-delegations` directory
   beside `.codex`; do not use a symlink. This can be a non-Git coordination root
   above the software repository, rather than that repository's Git root.
2. Choose a native task name, such as `parser_fix`. Write the complete declaration
   below into `.codex-delegations/parser_fix.json` as **raw JSON**, without Markdown
   fences. Finish writing before dispatch; keep it unchanged until the worker ends.
3. Call the native spawn tool with `task_name: "parser_fix"`. Its task message
   must name the harness root and include exactly one declaration pointer, for example:
   `Harness root: <absolute harness root>. Read .codex-delegations/parser_fix.json before work.`
   Name the software repository and command directory separately. State the base
   of writable/read paths and resource paths in existing `context`/`instructions`.
   Changing directory for software work must not reinterpret the declaration pointer.
   Keep model/provider/authentication and permissions under native control.
4. Verify the actual native spawn name and declaration, the child's observed read,
   and its actual diff/checks/report. Compare trusted child identity when available;
   otherwise retain the explicit unverified-binding risk. A structurally valid
   record or report is not evidence of successful work.

The coordinator owns these transient inputs, avoids task-name reuse between
active workers and excludes them from publication using the setup recipe.
The hook does not write, consume or delete records, track timestamps or freshness,
create a ledger or schedule retries. Old valid records can still pass validation;
the coordinator remains responsible for their relevance and cleanup. Do not place
credentials or secrets in declarations.

For an umbrella guard at `workspace/.codex/hooks/subagents.py`, a service task reads
`workspace/.codex-delegations/name.json`, while software checks run in
`workspace/service`. Declare paths such as `service/src/parser.py` as relative to
the harness root. A standalone service guard instead uses
`workspace/service/.codex-delegations/name.json`. Inspect the client's active hook
sources if both guards might load; matching hooks accumulate. Do not mirror records
or fall back to another declaration root. The examples below assume the software
repository and harness root coincide, with all paths relative to that root.

A writer's `.codex-delegations/parser_fix.json`:

```json
{
  "objective": "Fix the parser's empty-list regression.",
  "context": "Read src/parser.py and tests/test_parser.py. Empty lists currently fail.",
  "instructions": "Read local instructions. Preserve other input handling and unrelated edits.",
  "allowed_files": ["src/parser.py", "tests/test_parser.py"],
  "mutable_resources": [],
  "dependencies": [],
  "acceptance": ["Empty lists parse; existing validation remains intact."],
  "checks": ["python3 -m unittest discover -s tests"],
  "read_only": false,
  "budget": {"minutes": 15, "attempts": 2}
}
```

An independent reader's `.codex-delegations/parser_review.json` for native
`task_name: "parser_review"`:

```json
{
  "objective": "Review the parser change for regressions.",
  "context": "Read the working diff, src/parser.py and tests/test_parser.py.",
  "instructions": "Read local instructions. Report actionable findings with locations; make no writes. Avoid checks that create artifacts.",
  "allowed_files": [],
  "mutable_resources": [],
  "dependencies": ["The writer has stopped and supplied its exact revision or diff."],
  "acceptance": ["Review connected callers, validation, tests and semantic documentation impact."],
  "checks": ["Inspect the changed branch and relevant callers; report evidence and any checks not run."],
  "read_only": true,
  "budget": {"minutes": 10, "attempts": 1}
}
```

## Declaration schema

The object contains exactly the fields shown. Duplicate keys, comments,
non-finite numbers, extra fields and trailing commas are rejected. `objective`,
`context` and `instructions` are nonblank strings. `allowed_files`,
`mutable_resources`, `dependencies`, `acceptance` and `checks` are string arrays;
only `acceptance` and `checks` must be nonempty. All strings have at most 4,096
characters; each array has at most 64 entries. The file is at most 128 KiB.

`allowed_files` means **writable** files; read inputs belong in `context` or
`instructions`. `mutable_resources` names other owned writable resources, such
as a disposable service or port. Keep ownership disjoint; the coordinator owns
shared configuration, lockfiles and integration. `read_only` is a JSON boolean:
`true` requires both writable arrays empty; `false` requires at least one writable
file or resource. These declarations are instructions, not access controls;
contradictory prose and actual writes require coordinator review.

`budget` contains exactly integer `minutes` (1–120) and integer `attempts` (1–5).
Booleans and fractions do not count. These are declared guardrail bounds, not a
wall-clock or attempt scheduler; the worker and coordinator must honor them.

## Final report

The final message contains exactly one standalone, unindented JSON fence tagged
`delegation-report` or `json`. Both tags use the same exact schema and limits.
Multiple accepted fences, including one of each tag, are ambiguous and rejected;
plain unfenced JSON is not accepted. Examples inside outer backtick or tilde
fences do not count. The object
has exactly `status`, `summary`, `changed_files`, `checks`, `risks`, `blockers`
and `next_action`. `status` is `done`, `blocked` or `needs_context`;
`summary` and `next_action` are nonblank strings. Other fields are string arrays
using the declaration's entry and string limits. Only `checks` must be nonempty:
record each command/procedure, actual result and evidence, or say it was not run
and why. Empty arrays mean none. A blocked report is valid:

```delegation-report
{
  "status": "blocked",
  "summary": "The coordinator supplied no exact declaration pointer.",
  "changed_files": [],
  "checks": ["Declaration read: not performed; no exact pointer was supplied. No task work performed."],
  "risks": ["Native identity binding unverified."],
  "blockers": ["Missing explicit declaration pointer."],
  "next_action": "Coordinator supplies the exact safe harness-root-relative record path."
}
```

## Hook behavior and limits

Merge supplied `.codex/hooks.json` entries without replacing existing hooks.
Copy `.codex/hooks/subagents.py` into the project and this contract to
`.codex/delegation-brief.md`. The commands use Python 3.11+ as `python3` and a
quoted Git-root path, supporting starts inside subdirectories. Explicit non-Git
installation uses the quoted absolute script path for that harness root, including
when its command runs from a nested child Git repository. The safe reader
requires POSIX directory-relative opens, `O_NOFOLLOW`, `O_DIRECTORY` and
`O_NONBLOCK`; unsupported platforms are denied. The declaration directory and
leaf file cannot be symlinks; nonregular files, including FIFOs, are denied
without waiting for a writer. Declaration paths derive from the executing script's
own harness root, not the software Git root, payload `cwd` or session working directory.

Review and trust hook definitions through the client's supported UI; never
write trust hashes. Changed definitions may require renewed trust. Roll back by
removing only these three entries and their unused script/contract, preserving
other hooks. Handle transient declarations separately; see the setup recipe.

- `PreToolUse` matches complete names `spawn_agent`, `Agent`,
  `collaboration.spawn_agent`, `collaborationspawn_agent`,
  `multi_agent_v1spawn_agent` and `multi_agent_v2spawn_agent`. Configuration and
  handler use the same anchored pattern. Canonical/compatibility names follow
  official source; defensive flattened variants reflect namespace concatenation.
  These names alone do not prove actual host interception. Unrelated suffix
  names are ignored. The hook validates the visible `tool_input.task_name` and
  its declaration. Missing, unreadable, oversized, malformed or contradictory
  declarations produce a fixed supported `permissionDecision: deny` without
  echoing input. Valid declarations emit `{}`. It never approves permissions,
  inspects the native message, rewrites input or changes model/provider/auth.
- `SubagentStart` supplies the pointer/read procedure and final-report instructions
  through supported `additionalContext`. It cannot veto a start, inspect/decrypt
  the task message or establish identity binding. Missing host identity requires
  an explicit unverified-binding report, while a bad declaration pointer blocks work.
- `SubagentStop` checks the final report's structure only. An invalid report
  in either accepted fence with `stop_hook_active: false` requests one correction
  via `decision: block`.
  A subsequent `true` flag always emits `{}`; missing or invalid retry flags also
  emit `{}` to avoid loops. No transcript is read or claim verified.

Stdin and the declaration file each have a 128 KiB limit plus one detection byte.
Malformed configured PreToolUse input is denied. Start/Stop parse failures,
oversized input, non-object payloads and missing/non-string event names emit
`{}`. Full host envelopes are not validated: an object naming Start receives
context; Stop with an explicit false retry flag requests correction if needed.
Unknown events and unrelated tools are no-ops. The handler performs only bounded
input reads and the named declaration read: no network, subprocesses, transcript
reads, state writes or raw input logging. Hook commands resolve Git root without
changing Git state. Their three-second timeout depends on host enforcement.
Interpreter/startup failures, skipped/untrusted hooks, unsupported paths and host
errors may leave the tool unguarded. This is **not globally fail-closed**.

From the template root, run:

```sh
python3 -m unittest discover -s tests -p test_subagents.py -v
```

Tests use disposable projects and three-second subprocess timeouts. They cover
missing/invalid declarations, strict JSON/schema, bounds, traversal, symlinks,
nonregular files/FIFOs, opaque-message preservation, readers/writers, unrelated
tools, both report tags, ambiguous fences and Start/Stop behavior. They establish
local guard behavior, not actual
CLI/Desktop interception, native child identity, message binding, worker reading,
result truth, sandbox enforcement or host failure semantics. Those conditions
need separate real-client fixtures before claiming enforcement or completion.
