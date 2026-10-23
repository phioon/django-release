---
name: project-onboarding
description: Set up, inspect, update or repair the portable Agent Workflow for an existing GitHub project in Codex, using a reviewed project definition and explicit local bindings.
---

Use the locally supplied, reviewed Agent Workflow checkout. Read its
`docs/onboarding.md` before preparing setup; an installed copy of this skill has
[the onboarding contract](references/onboarding.md). Do not download code, create
repositories/accounts/credentials, or enroll repositories through discovery.

Inspect the existing project's instructions, configuration and skills. Establish
one explicit single- or multi-repository boundary, approved workflow revision,
project policy, machine paths and credential environment references. Keep the
portable definition reviewable; machine bindings and secrets do not belong in it.
A consumer with an existing controller uses its fixed trusted onboarding bridge.

Run the isolated onboarding launcher with `inspect`, then `preview`. Present the
complete concrete preview, including owned file changes and the approval digest.
Apply only after the user explicitly approves that preview. Approval to inspect
or discuss setup is not approval to change instructions or create state. Use
`apply --plan <preview.json> --approval <approved-digest>` from the same pinned
checkout. A digest binds the review; it does not authenticate who approved it.

If interrupted, preserve the journal and partial output and resume the same plan.
If files or pins changed, follow the actionable error; never discard custom files,
restore old state snapshots, silently select a legacy workflow, or initialize a
second authority. Updates and compatible rollback need a new preview and approval.
Existing consumer authorities and profile remain with their owning controller.

After apply, run the generated local startup helper in the project. It validates
and loads the pinned runtime and reports project/task ownership context. Then use
a fresh Codex thread for an ordinary project request and verify that the root
instruction binding invokes startup without requiring the user to name this skill.
Skill matching alone does not establish automatic startup. Report installation,
fresh-thread behavior and any later activation separately.
