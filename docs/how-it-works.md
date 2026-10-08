# How it works

The action runs inside your GitHub Actions job. Its fixed Python controller talks
only to GitHub and Railway. It does not start a controller service, store its own
database, execute configurable shell hooks, or supply a reusable workflow.

## One commit, two phases

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

Each successful release submits the application once. A failed or unresolved
release may submit it zero times. A rerun resumes observation of a durably recorded
ID or uses a verified terminal record; it does not repeat the submission. The
action does not automatically retry HTTP requests.

The branch checks narrow the window for stale work. GitHub's branch update and
Railway's submission are not an atomic transaction. Caller serialization and the
absence of other deployment writers are prerequisites, not guarantees supplied by
these API checks. A branch may advance immediately after the last check; migrations
must remain compatible with the version still serving.

## GitHub records

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

## Bounded observation

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

Receipt extraction requires fewer than 500 returned log lines, one receipt, and a
receipt of at most 4 KiB. It rejects a full log window because completeness is
unknown. Keep maintenance output bounded and never print database credentials.
There are at most 240 polls, five seconds apart, per phase; request duration adds
to elapsed time. The caller's job timeout is the outer limit. Cancellation after
an intent was written can leave an unresolved record.

## What success establishes

Source and offline tests establish the implemented checks and simulated recovery
behavior. A real release additionally needs qualified GitHub/Railway permissions,
provider response shapes, exact-SHA behavior, retained logs, database roles, and
maintenance semantics. Railway status is not an application health probe. Observe
serving readiness through your application's own operational check.
