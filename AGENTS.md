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

## Shared Vibe workflow

When the user explicitly adopts an enclosing coordination workspace, inherit its
common Vibe instructions as described here. Otherwise retain this repository's
standalone workflow below. Explicitly read the coordination workspace's
`AGENTS.md` and `.codex/delegation-brief.md` before Vibe task work. Codex does
not automatically load guidance above a Git root. For the primary checkout, the
coordination workspace is its parent. In a linked worktree, use `git rev-parse
--path-format=absolute --git-common-dir` to locate the primary checkout's `.git`
directory, then its parent workspace; do not use the temporary worktree's
parent. If the expected shared files are unavailable, report the gap before
dependent workflow actions; do not silently substitute an older local copy.

The coordination workspace owns shared lifecycle, cleanup, delegation and
security procedures. Those instructions supersede older Vibe procedure copies in
this repository and linked workflow pages. Repository-specific product rules,
tests, documentation ownership, publication authority and explicit user
constraints remain binding. Read this checkout's `.codex/vibe-workflow.toml` for
its own preferences and opt-outs. Inheritance does not enable worker selection
or local model routing, copy workspace settings, approve hooks, or change
model/provider/authentication. Keep hook commands and scripts local. Resolve
declarations from the guard's actual harness root: standalone repository chats
keep their own declaration root; workspace chats use the coordination workspace
guard's root. Shared policy is not shared runtime ownership. Preserve running
workers and other tasks' worktrees.

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
current checks and independent review. Plan at most four checkpoints or one sync
per phase. PRs start draft `[BLOCKED]`; `[READY]` requires current local/remote
checks, review and non-draft status. Withdraw READY before further edits, preserve
human content, reconcile uncertain results and never auto-merge. Publication
failure means “blocked; PR update pending”, with a concrete next action.

After all associated PRs are observed merged, cleanup defaults ON. Verify task
ownership and stopped writers, delete and verify eligible remote branches first,
then remove the exact clean worktree through its owner without force. Keep local
branch refs; preserve ambiguous, shared or dirty resources and explicit opt-outs.
Installation, client discovery and actual execution are separate evidence.
