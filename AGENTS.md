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
