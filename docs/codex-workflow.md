# Codex contributor setup

This guide covers development tooling, not release-controller behavior or deployment
authority. Public product contracts remain in this repository. The baseline is
[Vibe Coding Toolkit Prompt 12 at `790a895`](https://github.com/soumatheusgomes/vibe-coding-toolkit/blob/790a895304e0c08b70a5b215c9d334f1c86b816c/docs/prompts/12-existing-project-setup.md),
its [Codex guide](https://github.com/soumatheusgomes/vibe-coding-toolkit/blob/790a895304e0c08b70a5b215c9d334f1c86b816c/docs/tools/15-codex-workflow.md),
and the [Vibe Setup v0.1.0 delegation policy](../.codex/delegation-brief.md).
Resolve and compare newer upstream revisions before updating this integration.

## Configure and review

Use Python 3.11+, Git and a Codex client supporting native subagents and hooks.
Check the installed version and actual tools; a command line binary bundled with
the App is not evidence of execution in the App or VS Code extension. Preserve existing model, effort,
provider, authentication, permissions and unrelated hooks. No proxy or additional
API billing is needed. Use relevant installed skills without duplicating global
plugins. Project skills live in `.agents/skills/`; inspect their instructions when
they apply. Context7, Graphify and other machine integrations require their own
observed discovery and execution, not merely files in the repository.

If `.codex/config.toml` does not exist, copy `.codex/config.example.toml` to it.
Otherwise merge the supported agents settings after reviewing the existing file;
keep an explicit positive `max_concurrent_threads_per_session` limit. The local
configuration is ignored by Git. Its native skill selector requests disabling the
retired legacy `project-onboarding` procedure. Its files are preserved unchanged
under `.agents/retired/project-onboarding/`, outside the discoverable skill root.
Do not invoke or restore the retired procedure during routine setup. Verify that
a fresh client excludes it; existing sessions may retain an older skill catalog.
Do not overwrite custom settings or copy credentials.

Review `.codex/hooks.json`, `.codex/hooks/subagents.py` and
[the delegation contract](../.codex/delegation-brief.md). Trust the project and exact
hook definitions through the client's supported review surface. CLI provides
`/hooks`. New or changed definitions remain skipped until trusted. Review scripts
again when their contents change; definition trust is not a script-integrity check.
Inspect all active sources to avoid duplicate handlers. Do not bypass trust or edit
trust records directly. Restart a session only when needed to load changes.

Follow [the contributor lifecycle](../AGENTS.md#vibe-task-lifecycle) for verified
worktrees, recoverable setup, authorized PR delivery and post-merge cleanup.
Ordinary tasks use the installed helper without repeating complete onboarding.
Assign each worker a role and separate specialty from the installed contract;
these labels never select a native profile or change execution settings. Unknown
roles are rejected; custom nonempty specialties need their own assessment evidence.
The [optional display adapter](../.codex/native-display.md) is installed inert.
Reuse an already qualified user-level integration; do not add another wrapper.

Before each spawn, write the exact bounded JSON declaration to the root
`.codex-delegations/<task_name>.json` and use that native task name. Include exactly
one project-root-relative declaration pointer in the native task message. The child
reads the record and compares objective, writable scope, dependencies and checks
with its assignment. Missing, ambiguous, unsafe, unreadable or inconsistent
pointers/records block work. Compare trusted native identity when available, using
the final component of a canonical task path; a mismatch blocks work. If trusted
identity is unavailable, continue only the authorized declared scope and report
`native identity binding unverified` in `risks`; never infer identity from freeform
text. The coordinator checks actual spawn name, declaration, observed read and diff.
Git and Graphify ignore these transient inputs; keep them out of other archives too. Opaque native messages
remain untouched; the hook cannot prove message/record agreement or worker access.
The safe file reader requires POSIX directory-relative opens (macOS/Linux); other
platforms need separate qualification and are denied when those calls are unsupported.

The guard checks bounded declaration JSON before intercepted native spawns, adds
procedure context at SubagentStart, and requests at most one report correction at
SubagentStop. It accepts blocked reports. It does not enforce ownership, read-only
access, time limits, truthful checks, review quality or task completion. Hook command
failures and uninstrumented tools can leave a path unguarded. Use native permissions,
explicit file ownership, verified evidence and independent review alongside hooks.

## Verify behavior and maintain

Run the offline commands in [CONTRIBUTING](../CONTRIBUTING.md); they include guard
regressions. In a disposable trusted project, check one dispatch without a valid declaration is denied
before a child starts; a valid bounded reader executes; a missing report causes only
one correction; and unrelated tools still work. Verify the App and VS Code extension
separately when used; retain CLI checks as supporting evidence. Include cancellation
and failed-hook behavior. Record the actual versions, source
hashes, observed tool events and unrun cases. Installation is not qualification.

For security work, use [Prompt 13 at the pinned revision](https://github.com/soumatheusgomes/vibe-coding-toolkit/blob/790a895304e0c08b70a5b215c9d334f1c86b816c/docs/prompts/13-security-review.md)
against an exact baseline or diff, read-only by default, with a private redacted
report. Use [Prompt 14](https://github.com/soumatheusgomes/vibe-coding-toolkit/blob/790a895304e0c08b70a5b215c9d334f1c86b816c/docs/prompts/14-harness-evaluation.md)
for behavior cases. For a concrete harness failure, compare one disposable native
candidate using [Prompt 15](https://github.com/soumatheusgomes/vibe-coding-toolkit/blob/790a895304e0c08b70a5b215c9d334f1c86b816c/docs/prompts/15-harness-improvement.md),
with frozen inputs, the same client/model/authentication and existing permissions.
No external benchmark, recurring trial, production probing or paid service is implied.

Requalify affected cases after client/schema, hook, skill or instruction changes.
Preserve custom files and compare exact differences on reapplication. To roll back,
remove only these three subagent event groups and their unused handler/contract;
preserve unrelated hooks and existing preferences. No deployment or release follows
from a successful local tooling test.
