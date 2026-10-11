# How it works

The action runs inside your GitHub Actions job. Its fixed Python controller talks
to Railway, and only in legacy modes to GitHub. It does not start a controller service, store its own
database, execute configurable shell hooks, or supply a reusable workflow.

## V3: one fresh migration attempt

Policy v3 `migrations-only` is the primary mode:

1. Scan the exact candidate Git tree for unsupported Railway config files. Verify
   the committed policy, index/worktree identity, trusted push event, workflow and
   exact checkout SHA before any provider request.
2. Preflight only Schema Maintenance against the policy's source, target and process
   expectations. Wait within a fixed bound while a transient deployment exists.
3. Submit a fresh Maintenance deployment with `commitSha` equal to the push SHA.
   Keep the returned UUID for this invocation. An uncertain mutation ends the
   invocation; no internal second submission occurs.
4. Query that exact UUID and validate project, environment, service and source SHA.
   On `SUCCESS` or `REMOVED`, require the strict current
   [migration receipt v2](configuration.md#migration-receipt-v2). Provider failures,
   malformed responses, conflicting results and timeouts fail the CI job.
5. Railway's other native services can proceed through their independently
   configured Wait for CI. The action makes no application calls.

Every subsequent invocation repeats this sequence, including after prior success,
failure, missing receipt, lost response or cancellation at the same SHA. Earlier
records and receipts never authorize current success. There is no GitHub client,
run/history lookup, deployment record write, predecessor reconciliation or cached
success in this path. Source SHA preflight does not reject a retry or demand that
the event SHA still be the branch head.

The transient activity query is a bounded existence check (`first: 1`) for the
Maintenance target, excluding known terminal statuses and retained `SUCCESS`.
No lifetime deployment history is paginated. The exact-attempt observer uses
[Railway's direct deployment query](https://docs.railway.com/integrations/api/manage-deployments#get-a-single-deployment).
Both the active wait and the current attempt have at most 240 polls, five seconds
apart; request time adds to the total. HTTP requests have 30-second timeouts and
are not automatically repeated. The workflow's timeout is the outer bound.

The log read is scoped to the returned ID and limited to fewer than 500 lines;
a full window cannot establish completeness. Results are limited to 4 KiB and
must have exactly the versioned fields. Logs are read only for `SUCCESS` or
`REMOVED`, never during the build/queue wait. A missing receipt keeps polling;
malformed, duplicate, contradictory or mismatched results fail immediately.

Railway [retains Success after a zero-exit process](https://docs.railway.com/deployments/deployment-actions).
That status cannot permanently lock retries, but it also does not prove a process
has exited. Activity checks and submission are not atomic. A fresh submission
may replace or interrupt an older Maintenance process; they are not a distributed
lock. The consumer must serialize migration work in its database, keep migrations
compatible with serving code and handle partial non-atomic failures outside the
action. The startup schema gate is also consumer-owned containment, not proof of
successful orchestration or a generic implementation supplied here.

Protect the required `push` workflow against path skips, conditional success and
cancellation. The [README](../README.md#quickstart) explains the Wait for CI
conclusion rules and keeps Maintenance independent of the native-service wait.
The fixed receipt verifies migrations only. Database permissions, provisioning
and actual serving readiness require separate consumer evidence.

## Legacy modes

The remaining sections describe **unchanged policies v1/v2 only**. Their ledger,
ACL receipts and resume-without-resubmission rules do not apply to v3.

## One commit, two phases (legacy)

This sequence is policy version 1 and remains unchanged. Explicit version-2
`schema-only` mode performs steps 1–4, with step 3 checking only Schema Maintenance.
It makes no application-provider calls and appends no application intent. Both
GitHub history categories and their continuity checks remain active, including
blocking on unresolved legacy application submissions. The historical application
UUID in the policy binds those records without granting provider authority.
Application deployment and startup readiness belong to the consumer in that mode.

1. Scan the exact candidate commit for `railway.toml` and `railway.json` anywhere,
   rejecting either name before any provider request. Read the policy's exact
   committed blob, rejecting changed/staged files and all symlink components;
   validate it, the checkout, push event and actual GitHub run attempt.
2. Inspect the consumer's GitHub deployment records and their predecessor links.
   Any unresolved earlier release blocks a new release.
3. Verify both Railway services' dashboard settings match the policy, with no
   config-file override and native autodeploy disabled.
   Store a schema submission intent in GitHub **before** asking Railway to deploy.
4. Submit Schema Maintenance at the exact push SHA. Store the returned deployment
   ID as a status and read it back before continuing. Observe that same ID, source,
   and target. Accept only a successful/removed one-shot deployment with exactly
   one matching full migration/ACL success receipt.
5. Check the branch and record ownership again. Create the application intent,
   submit that exact SHA, retain its returned ID, and observe its success.

Each successful version-1 release submits the application once. A failed or
unresolved version-1 release may submit it zero times. Version-2 schema-only
execution never submits the application. A rerun resumes observation of a durably recorded
ID or uses a verified terminal record; it does not repeat the submission. The
action does not automatically retry HTTP requests.

The branch checks narrow the window for stale work. GitHub's branch update and
Railway's submission are not an atomic transaction. Caller serialization and the
absence of other deployment writers are prerequisites, not guarantees supplied by
these API checks. A branch may advance immediately after the last check; migrations
must remain compatible with the version still serving.

## GitHub records (legacy)

The only categories are `<consumer>-release-schema` and
`<consumer>-release-application`. They are labels on GitHub Deployments, not extra
Railway services. A payload records format version, repository/consumer, SHA,
workflow, run/attempt, provider target, policy digest, deployments observed before
submission, and both predecessor heads. Statuses retain the returned provider ID
and verified or failed result. [Configuration](configuration.md#release-records)
defines the formats.

The newest record in each category is the continuity head. The controller checks
the two newest records, their immediate predecessor links and terminal predecessor
statuses; it separately searches the candidate SHA and rejects duplicates. A
record for the application must also point to a verified schema record with the
same SHA and policy digest. A
terminal predecessor is a checkpoint certifying that this controller previously
validated its ancestry. Older records remain intact. The controller does not need
every old Actions run to remain available, but every active intent must still have
an accessible, matching run attempt. A checkpoint cannot be appended by this
controller while a predecessor is unresolved.

These are trusted workflow records, not cryptographic attestations. A writer with
the caller's deployment permission can tamper with them. Restrict that permission
and preserve the record history. Do not import unrelated records into these
categories, change identities in place, or invent success statuses manually.

## Bounded observation (legacy)

The candidate-tree scan streams NUL-delimited paths with Git replacement objects
disabled. It checks directory entries too, and stops at 50,000 paths, 4,000,000
bytes of output, or 30 seconds. A partial or unavailable scan cannot establish
that Railway's automatically discovered configuration files are absent. Dashboard
configuration, null config bindings, and hosted qualification remain required.

GitHub reads intentionally request the two latest category records and at most two
records for the candidate SHA; a second SHA record is already ambiguous. Direct
predecessor reads check continuity, rather than pretending that a truncated list
is the complete historical ledger. Status history must fit below 20 entries per
record. Railway history follows all pages up to 10 pages of 100 deployments; a
remaining next page, repeated cursor, duplicate deployment, malformed response,
or exhausted rate allowance stops the release. The controller does not prune
history to bypass these limits.

Result extraction requires fewer than 500 returned log lines, at most one success
or failure result in total, and a result of at most 4 KiB. It rejects a full log window because completeness is
unknown. Keep maintenance output bounded and never print database credentials.
There are at most 240 polls, five seconds apart, per phase; request duration adds
to elapsed time. The caller's job timeout is the outer limit. Cancellation after
an intent was written can leave an unresolved record.

Observation selects the exact durably submitted UUID from those bounded listings.
Its bound `FAILED`, `CRASHED` or `SKIPPED` status records failure even with unrelated
post-baseline deployments. Schema Maintenance can also establish failure with one
strict [bound failure result](configuration.md#maintenance-failure-result), including
when provider status says `SUCCESS`. Success still requires no unrelated deployment
after the baseline and the unchanged full success receipt. Missing or inconclusive
exact evidence remains unresolved; another deployment cannot replace it. Reruns
observe the same UUID, while a terminal failed SHA requires a new reviewed commit.

## Qualification in every mode

Source and offline tests establish the implemented checks and simulated recovery
behavior. A real release additionally needs qualified GitHub/Railway permissions,
provider response shapes, exact-SHA behavior, retained logs, database roles, and
maintenance semantics. Railway status is not an application health probe. Observe
serving readiness through your application's own operational check.
