# Contributor automation guide

This repository owns a small composite GitHub Action and fixed Railway controller.
Read README.md, docs/configuration.md and docs/security-recovery.md before changes.
Preserve versioned records, strict source/target bindings and uncertain outcomes.
Never infer submission attribution from time, SHA, image or a matching listing.
Use fictional examples only. Never author Django migrations or run makemigrations.
Do not add dependencies, arbitrary hooks, a service, or a provider framework.
Keep public product documentation beside its implementation. Update affected docs
and run the checks in CONTRIBUTING.md. Consequential authority/recovery changes
require independent review. Source changes grant no deployment, secret, repository
settings, publication, or cleanup authority. Preserve other contributors' edits.

## Codex development workflow

Use the [Codex setup and validation guide](docs/codex-workflow.md) for native
subagents, project hooks, applicable skills and repeatable local qualification.
Follow the [bounded delegation contract](.codex/delegation-brief.md) for each
native dispatch. Write the declaration before spawning and include exactly one
project-root-relative `.codex-delegations/<task_name>.json` pointer in the task
message. The child must read it and compare objective, writable scope, dependencies
and checks with its assignment. Missing, ambiguous, unsafe, unreadable or
inconsistent pointers/records block work. Compare trusted native task identity
when available (the final component of a canonical task path); mismatches block
work. If trusted identity is unavailable, continue only the authorized declared
scope and report `native identity binding unverified` in `risks`; do not infer
identity from freeform text. Keep one writer per file and reviewers read-only. Preserve the
client model, provider, authentication and explicit permission limits. A hook
checks structure on intercepted events; it does not grant authority, isolate
filesystem writes or verify a report's truth. Check actual diffs and test evidence.

Use the repository's existing offline checks. Read relevant instructions/code,
define acceptance, preserve data and user changes, and document changed contracts.
Confirm an interrupted worker stopped before taking over. Check actual files and
processes when resuming a handoff. Continue independent authorized work around a
blocker, but respect cancellation and finite limits. Use independent review for
nontrivial changes, and record any gaps. Publication needs task-specific authority.

## Delegation policy

Read the [delegation policy](.codex/delegation-brief.md) before choosing local or
native execution. The main agent is Coordinator; each worker has an explicit role
and separate specialty. Prefer local execution only when enabled routing, existing
approval, matching assessment evidence and safe capacity permit the complete task.
Otherwise retain authorized native execution. Unknown roles are rejected; a custom,
nonempty specialty is allowed but remains **Not assessed** without matching evidence.
Role labels never select a native profile or change model, reasoning, provider,
authentication or permissions. Preserve these settings and all explicit user limits.
The [optional native display adapter](.codex/native-display.md) only fills absent
or null `agent_role`; any supplied value wins. Installing its files does not
activate it. Reuse an already qualified shared integration without adding wrappers;
actual badge delivery needs separate client evidence.

## Vibe task lifecycle

Use the reviewed installed Vibe Setup helper at
`$HOME/.codex/skills/vibe-setup/workflow.py` and its adjacent `task-lifecycle.md`.
Resolve the installed skill's actual path if this location differs; do not copy
its helper into this repository. Normal tasks use the helper directly, without
repeating full onboarding. Read `.codex/vibe-workflow.toml`: lifecycle and cleanup
default ON; preserve independent `enabled=false` and `auto_cleanup=false` choices.

Inspect first. Unless opted out, create or adopt a linked worktree and require
`start` to return `implementation=worktree_verified` before editing. Use its
returned command and worker roots; a failed verification never permits primary
checkout edits. Preview setup with `inspect --task-id`, apply the reviewed plan,
and resume the same operation after interruption. With lifecycle disabled, use
the reviewed component installer and ordinary authorized delivery instead.

Follow the installed lifecycle contract for `sync` and `resume`, under the
repository's publication authority. Stop writers and supply explicit files plus
current checks and independent review. Plan at most four routine checkpoints or one per
phase. READY, reopen and blocker events reuse existing milestones without
consuming that budget; refreshed inputs require a fresh READY event and current
gates. PRs start draft `[BLOCKED]`; `[READY]` requires current local/remote
checks, review and non-draft status. Withdraw READY before further edits, preserve
human content, reconcile uncertain results and never auto-merge. Publication
failure means “blocked; PR update pending”, with a concrete next action.

Cleanup follows the installed lifecycle contract after observed terminal PR state.
Remote deletion and worktree removal have independent opt-outs; preserve both and
`auto_cleanup=false`. Merged tasks permit eligible cleanup; closed-unmerged tasks
retain their worktrees, while recorded supersession can permit removal. Keep local
branch refs. Verify ownership, stopped writers, clean files and remote absence
before removal when enabled. Managed worktrees require native archive preflight
and their native owner; queued archival stays pending until absence is verified.
Reuse existing cleanup and supersession operations without legacy tools or polling.
For required companion PRs, use `check-completion` with every required Vibe task
before claiming overall completion. Installation, discovery and execution remain
separate evidence.

## Vibe worker selection

The project owner authorized full applicable Vibe adoption on 2026-10-23, including
explicit difficulty-based worker selection. Read the installed Vibe Setup
`delegation-brief.md` and the matching project copy before delegating. The
`[worker_selection]` section in `.codex/vibe-workflow.toml` records this choice
independently of lifecycle and cleanup preferences. Do not silently fall back to
an older PHIOON inheritance-only policy.

Keep the Coordinator's model, reasoning, provider, authentication and permissions
unchanged. Classify the task's difficulty and risk; use deterministic tools or the
Coordinator when delegation adds no value. Prefer approved, assessed local models
within their exact scope and capacity. Otherwise select a qualified native model
and reasoning pair through supported controls. A full-history fork inherits
settings; explicit selection requires fresh context and supported overrides.
Record the selection reason, qualification reference, requested and observed
settings, outcomes and fallback cause privately. Availability or a successful
model-control probe does not establish task competence or savings. Missing matching
qualification retains the authorized inherited route and must be reported as a
qualification gap. This adoption does not authorize new model assessments, paid
benchmarks, providers, billing, local approvals or plugin releases.

Use the installed Vibe lifecycle and security contracts as current authority:
worktree verification, bounded publication checkpoints, independent cleanup
preferences, supersession, cross-repository completion and proportional security
validation apply under their existing gates. At each readiness, release or explicit
security gate, inspect Trail of Bits updates and bind required checks and review
to the exact snapshot. Release preflight remains required with lifecycle disabled.
Task startup does not independently trigger a security audit. Preserve manual
merging, existing product checks, user customizations and needed legacy evidence.

Before native dispatch, put the declaration at the active harness root owning the
executing hook, not whichever repository is the current command directory. Name
that root and the software worktree separately in the message; include exactly
one harness-root-relative declaration pointer. An umbrella chat uses the umbrella
root; a direct repository chat uses that repository's harness root. Verify actual
client loading and worker settings separately from installation. Keep primary
activation and requested-client qualification pending until observed.
