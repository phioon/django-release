# Reviewed local project setup

Use Python 3.11, Git, a POSIX host and an already available reviewed workflow
checkout. All input/output is English UTF-8 JSON or text. Run launchers in a fresh
process with `python3 -I -B`; workflow source must be clean, including ignored
files, at its exact full Git commit. No command downloads workflow code or
provisions repositories, accounts, credentials or teams.

## First use

Choose [one repository](single-project.json) or an explicit [multi-repository
boundary](multi-project.json). Replace every fictional repository, pin, model,
identity, command and policy choice through project review. Describe the smallest
accepted task, ownership, risk/review rules, checks and documentation authority in
the reviewed policy references. A JSON profile validates declarations; it cannot
establish that those decisions are sufficient or approved.

Keep the portable definition in the project's chosen reviewable policy home.
Prepare a separate local [bindings file](bindings.json), with canonical absolute
paths and no symlinks. Existing sources may have unrelated local changes; setup
preserves them. Runtime operations retain their own clean-source requirements.
The workflow, profile cache, task root, skill and control directory must not
collide with each other or with application checkouts. A multi-repository
source root is a non-Git workspace; every repository mapping is explicit. Existing
remotes must match the declared GitHub.com owner/name over HTTPS or SSH.

From the selected workflow checkout:

```sh
python3 -I -B scripts/onboard_project.py inspect --definition /local/project.json --bindings /local/bindings.json
python3 -I -B scripts/onboard_project.py preview --definition /local/project.json --bindings /local/bindings.json > /local/preview.json
```

Inspection and preview are read-only. The preview lists the complete definition,
policy, exact pins, explicit mappings, local paths, credential environment
reference, instruction/configuration/skill inventory (path, size and digest),
initial authority content or existing authority bindings, generated profile
receipt, and every owned file's exact before/after bytes. Secret environment
values are never read. Do not put secrets in instructions, definitions or role
text; those reviewed inputs may be shown in the preview.

Review the full preview and obtain explicit approval of its `approval` digest.
The caller provides that digest to apply; this binds exact reviewed bytes, it
does not authenticate the approver or replace the user's authorization.

```sh
python3 -I -B scripts/onboard_project.py apply --plan /local/preview.json --approval APPROVED_SHA256
```

`--preview`/`--approve` are aliases for `--plan`/`--approval`. The output identifies
`binding`, the generated local binding file. Setup does not commit application
changes, change Git identity, publish, merge, deploy, synchronize source branches
or remove user files.

## Definition and machine boundaries

A definition has exactly `project_version: 1`, `id`, `boundary` (`single` or
`multi`), `mode` (`independent` or `consumer`), `workflow_revision`, `repositories`
and `policy`. Each repository has `github` (`owner/name`), `remote` and `target`.
A single boundary has exactly one repository. A multi boundary is explicit even
when it temporarily has only one repository; no directory scan expands it.

Independent `policy` contains a complete runtime-v2 `profile` and a map of relative
text `artifacts` used by its template and role references. All artifact references
are local to that definition; unused artifacts and a second `profile.json`
authority are rejected. The profile ID and repository/remote/target/publication
mapping match the definition. It selects the built-in `github-v1` adapter and
explicit `profile-pairs`. Review the verification commands, permitted documentation
participants, branch prefix, role restrictions, expected publication creator and
commit identity. Model selections grant no permissions or runtime attestation.

Independent bindings have exactly `bindings_version: 1`, `project`, `workflow`,
`source_root`, `task_root`, `repositories`, `control_root`, `skill_path` and
`credential: {"environment": "VARIABLE_NAME"}`. `control_root` must initially be
new and isolated; setup creates private lifecycle/routing authorities only there.
The profile projection lives in `control_root/profiles/<commit>` and includes a
deterministic Git tree/commit, generated from the definition and workflow pin.
Its receipt binds definition digest, generator revision, output tree and commit.
Never edit that projection or use an application commit to pin it.

The onboarding skill is shared distribution. An absent skill can be installed at
the exact previewed `skill_path`, whose directory name is `project-onboarding`.
Identical existing files are reused, not claimed as project-owned state. Choose a
Codex-supported discoverable location, normally `~/.agents/skills/project-onboarding`;
an arbitrary fixture directory does not establish automatic skill discovery.
Other installed skills remain untouched. Differing shared skill bytes require a
separate explicit distribution upgrade, not an implicit project overwrite.

## Startup and task worktrees

Apply creates an owned local `AGENTS.override.md` containing existing root
`AGENTS.md` bytes plus a portable startup block. Source instructions are not
rewritten. Existing overrides at relevant roots/ancestors/nested paths stop setup
for explicit reconciliation. Review client fallback instruction filenames and size limits before approval.
Projects using only a custom fallback instruction file need explicit reconciliation
into the root AGENTS guidance first; the generated override copies AGENTS.md, not
arbitrary fallback files. The existing Git common directory receives local
`agent-workflow/startup.py` and `agent-workflow/binding.json`; `info/exclude` gains
only the reviewed ignore line. No machine-specific path is added to tracked
project instructions. Non-Git workspace roots get a local `.agent-workflow`
startup helper and the same instruction overlay.

Invoke the Git helper from a root or nested directory:

```sh
python3 -I -B "$(git rev-parse --path-format=absolute --git-common-dir)/agent-workflow/startup.py" --cwd "$PWD"
```

Or invoke the pinned onboarding entrypoint directly:

```sh
python3 -I -B /local/workflow/scripts/onboard_project.py startup --binding /local/control/binding.json --cwd /local/project/app
```

Startup verifies the complete installation and receipt, source/common Git
identities, authority identities and owned instruction bytes. It actually loads
the runtime and returns `status: current`, the project ID, runtime binding,
operating guide, policy references and `context`. Source contexts identify the
mapped repository or workspace. A task context additionally identifies the
registered task and current owner and checks the actual branch/worktree mapping.
An unregistered sibling worktree is refused. Startup reads an atomic task snapshot;
subsequent mutations revalidate ownership under the existing write locks.

New core-registered task worktrees receive an ignored owned override made from
the task's own baseline AGENTS file, even when the source setup was never committed.
The lifecycle record retains write intent and exact ownership hashes. Existing
task records are not retroactively enrolled. Task `sync` can refresh an already
owned overlay after AGENTS changes; customized overlays require reconciliation.
Closeout archives only a proven generated overlay, and preserves customized or
unexplained files. No application commit is required merely to get startup.

After source AGENTS changes, review/apply a new setup preview to refresh its
owned overlay. Startup stops on stale instructions, partial setup, mismatched
pins, replaced lock identity or wrong project; it never silently chooses another
workflow. Start a fresh Codex thread with an ordinary task request and verify the
helper invocation and returned project context. Then qualify a fresh registered
task thread. Instruction lookup, user/global overrides, client trust and size
limits still apply; successful setup does not prove a running client reloaded.

## Interrupted apply, updates and rollback

Apply checks the preview digest, re-observes repositories, instructions/config/
skills and existing state before writing, then records an approval-bound initialization intent beside `control_root`
before creating that destination and its durable journal. This intent supports
retry after interruption even before the first journal write; unexplained
pre-journal contents are refused. The preview includes its exact local path. The persistent setup lock serializes writers. Each mutation has
reviewed before/after bytes and saved intent; repeat the same apply command after
an interruption. Unexplained changes stop recovery and preserve partial output.
Do not create a replacement authority or delete the journal to bypass a conflict.
A completed repeat verifies the current installation and owned output.

New Darwin APFS identities bind the volume UUID and inode for repository/common
directories, authority directories/locks and the setup lock. Device renumbering
across a restart is accepted only for that versioned format; different volumes or
inodes are refused. Other POSIX hosts and verified non-APFS volumes retain exact
`[st_dev, st_ino]` pairs. Discovery errors stop setup; live lock descriptor checks
and symlink refusal remain in force.

Existing identities retain their recorded format during startup and updates.
Legacy pairs never gain UUID trust automatically, even when an inode is unchanged.
If a legacy binding fails after device renumbering, preserve all original receipts,
state and locks for separately reviewed continuity recovery and an explicit
successor installation. Ordinary onboarding offers no general recovery/rebinding
command and does not relocate an existing consumer installation binding.

To update, retain the control directory, repository boundary, authority paths,
lock identities and existing histories. Prepare a reviewed compatible definition
with the new workflow/profile inputs (and a new local workflow path if required),
then inspect/preview/apply again. Compatibility means the same closed project-v1
and runtime-v2 contracts, unchanged project mapping and selected route policy.
Route approval changes remain with their owning authority procedure. A new pin
alone does not authorize a schema migration, state relocation or consumer cutover.
Both old and new workflow sources must remain available for a rollback decision.

Compatible rollback uses the same preview/apply process with a retained approved
workflow/definition. Profiles may return to earlier compatible pins; task records,
assignments, authority JSON, lock inodes and additive setup history remain current.
Never restore an old register/routing snapshot. Existing evidence remains bound to
its original revisions; obtain current checks/reviews before continuing delivery.
The old preview cannot simply be replayed over a newer completed setup.

## Existing consumer bridge

An existing consumer uses its fixed pinned trusted entrypoint, not the independent
launcher. Its definition retains the common fields but `mode` is `consumer` and
`policy` has exactly `profile_revision`, `profile_file`, `adapter_revision`.
Consumer bindings have exactly `bindings_version: 1`, `project`, `installation`
(the existing executable installation JSON path), `control_root` and `skill_path`.
The mapped existing runtime-v2 profile and `consumer-v1` adapter must match the
reviewed pins. Keep immutable adapter/profile sources outside edited application
and task directories.

The consumer bootstraps its pinned code before importing onboarding and supplies
`bridge.validate(installation_path) -> runtime` plus
`bridge.command(binding_path) -> complete startup argv`. The common helper appends
`--cwd <directory>`. The bridge is trusted application code; JSON never names an
arbitrary Python module. Public functions are `inspect_project`, `preview`,
`apply(plan, approval)` and `startup(binding_path, cwd)`, each accepting the explicit
`bridge` keyword. The consumer can cache its validated runtime and reject changed
installation arguments. It retains all its policy, ownership and authority guards.

Consumer setup reuses existing profile/state/lock bytes and paths. It creates no
new consumer authorities or profile projection. Source delivery and qualification
of this bridge are separate from a consumer's default activation decision.
