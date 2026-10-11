# Security, recovery and upgrades

## V3 security boundary

Use policy v3 `migrations-only` for the primary migration gate. It validates the
trusted push/workflow/checkout and committed policy locally, then addresses only
the configured Railway Schema Maintenance service. It makes no GitHub API call
and needs no GitHub run-read or deployment-write permission. The checkout still
needs contents read. A Railway project token remains environment-scoped and can
reach other services; the controller's target restriction is not provider-enforced
service isolation. Keep that token out of service variables.

Use a private one-shot Maintenance service with disabled native autodeploy and
Wait for CI, reviewed dashboard process settings, no config-file override, one
replica and restart policy `NEVER`. The exact commit cannot contain `railway.toml`
or `railway.json` anywhere. Protect workflow, policy, migrations, command and action
pin through review. Use separate migration and runtime credentials. Consumers own
least-privilege database grants, ownership, provisioning, TLS and database tests;
v3 neither implements those policies nor claims to verify them in its receipt.

The consumer command must hold an appropriate database lock through migration
work, apply and verify the complete expected migration graph, and emit one fully
bound receipt after all its required work passes. If its own permissions checks
are required, they must also pass before success. Ordinary app startup must use
its limited role and must not migrate or repair the database.

Configure other native services with Wait for CI. The migration workflow must run
on every trusted push, with no path skips, conditional skips, `continue-on-error`
or concurrency cancellation of queued runs. Railway's
[Wait for CI rules](https://docs.railway.com/deployments/github-autodeploys#wait-for-ci)
allow skipped/neutral runs and can ignore a cancelled workflow when another one
passed. Qualify those settings and use a consumer-owned read-only startup schema
gate to contain missing migrations. The action does not supply that gate, verify
native service settings or establish serving health.

Before production, qualify exact-SHA submissions, direct deployment-ID reads,
the bounded transient-state filter, receipt retention, consumer locks, command
semantics and native Wait for CI behavior on disposable infrastructure. Official
[Railway API guidance](https://docs.railway.com/integrations/api/manage-deployments)
and [CLI schema](https://github.com/railwayapp/cli/blob/master/src/gql/schema.json)
support the query shapes; offline fixtures cannot prove hosted permissions,
provider stability or database correctness.

## Consumer database roles

A common consumer pattern uses `db_migrator_user` to create and change schema,
and `db_runtime_user` for the application's defined table access. Configure their
credentials in the appropriate Railway services; do not pass them to this action.
Choose the runtime privileges from the application's actual requirements.

For a uniform access policy, consumer provisioning can configure PostgreSQL
default privileges for objects subsequently created by the migrator role. The
defaults belong to the role actually creating the objects, are not inherited
from its memberships, and do not update existing objects. Existing-table grants,
schema access and sequence privileges need their own reviewed scopes. See
[PostgreSQL default privileges](https://www.postgresql.org/docs/current/sql-alterdefaultprivileges.html).
Applications with more restricted roles or per-table access need a corresponding
consumer policy instead of a universal `GRANT ALL` rule. This product supplies
no grant executor or role-provisioning helper.

## V3 failure and retry

Any failed, unknown or timed-out attempt fails CI. Workflow cancellation does not
verify migration success or undo database changes. A retry is a **new invocation**
that submits a new exact-SHA Maintenance deployment; no earlier receipt, failure
record or release status decides its success. The controller never repeats an
uncertain submission within the same invocation and never discovers/adopts an
ID by time, SHA, image or listing.

| Situation | Response |
| --- | --- |
| Event, workflow, checkout, committed policy or target mismatch | Fix the binding or reviewed configuration. Invalid preflight cannot mutate Railway. |
| Transient Maintenance deployment remains active | The bounded wait fails before submission. Investigate the existing process, then invoke the workflow again. |
| Submission response is lost, malformed or unavailable | This invocation fails. An earlier process may exist; a subsequent invocation performs the bounded activity check and submits fresh work. |
| Exact deployment has `FAILED`, `CRASHED`, `SKIPPED` or an unknown/cancelled state | Fail even if a success-looking receipt exists. Investigate consumer work before another invocation. |
| Missing receipt or current-attempt observation timeout | Fail CI. Restore read access or fix the consumer command; the next invocation executes again. |
| Malformed, duplicate, contradictory or wrong-target/SHA/ID receipt | Fail CI. Correct the command or binding, never accept an older receipt. |
| Migration or consumer permission check fails | Inspect the database and correct the consumer problem. A same-SHA retry is permitted when appropriate and executes the command again. Code changes require a new reviewed SHA. |

The activity check excludes retained `SUCCESS` because one-shots can keep that
status after exit. This is not process-exit proof. A new deployment may stop or
replace an older process, including after a lost response. The database lock
serializes work but cannot prevent provider interruption, make non-atomic
migrations atomic, or repair partially applied changes. Developers own those
repairs outside the workflow. There is no automatic migration-history editing,
schema rollback, role creation, app deployment, or recovery loop.

Inspect provider logs and database state privately. The controller prints fixed
reason codes and suppresses raw remote diagnostics. Never publish tokens,
connection strings, environment dumps or raw logs in an issue.

## Adopting v3 from a legacy policy

Adoption is an explicit reviewed change to policy v3, receipt v2, the action pin
and the caller workflow. Remove legacy application/history/ACL fields from the
policy and remove unused GitHub token input and run/deployment permissions.
Review native service settings, Maintenance independence, the consumer lock and
startup containment before activation. Finish or contain outstanding old work
operationally; v3 does not resume it or reconcile predecessor records. Preserve
old records as evidence: v3 leaves them untouched and does not read them. A v3
success certifies only the newly submitted attempt, not historical resolution.

Do not downgrade to an older pin expecting it to understand v3. Review consumer
fixtures and database behavior for every upgrade. Non-atomic repairs and
permissions/provisioning remain consumer decisions outside the action.

## Legacy v1/v2 boundary and recovery

The remaining operational rules apply **only to legacy policies v1/v2**. Their
GitHub ledger, ACL receipt, history admission and no-resubmission semantics remain
unchanged. They are not the v3 failure/retry contract.

### Establish the legacy boundary before activation

Keep the serving application's database role limited to its required queries.
Schema Maintenance gets the separate migrator role needed to change schema and
reconcile permissions. Avoid broad superuser authority. The consumer owns actual
PostgreSQL ownership, grants, default privileges, TLS, locking and tests. Ordinary
application startup must not run migrations. No database credentials enter the
GitHub action; the provider token must not enter either service's variables.

A Railway project token is scoped to an environment and may reach multiple
services there. Review that blast radius. Policy version 1 constrains calls to
the configured two targets; version-2 schema-only calls only Schema Maintenance.
Neither is provider-enforced service isolation.

Protect the release workflow, policy, action pin, migrations and maintenance
command. Give deployment write permission only to trusted release automation and
serialize all release writers for a consumer. Disable provider-native autodeploy
on both services for version 1, or only Schema Maintenance for version-2 schema-only.
The consumer owns native application deployments and a read-only startup
compatibility gate in schema-only mode. Use reviewed dashboard configuration with
no config-file override on both targets for version 1, or on Schema Maintenance
for schema-only mode. Schema-only preflight never inspects application settings.
Remove committed `railway.toml` and `railway.json` files from all
locations, including nested service roots; Railway's automatic discovery can
override dashboard settings even when the explicit binding is null. Both legacy modes
scan the exact candidate tree and refuses these names anywhere before any provider
request. A bounded or unavailable scan also stops the release. The policy itself
must be committed at the event SHA, without
staged or working changes or symlink components; the action parses only those
verified committed bytes. Avoid external/manual deployment writers on the
controller-owned targets. GitHub deployment
records are evidence from trusted writers, not tamper-proof storage. A compromised
workflow or stolen token can defeat these boundaries.

Before enabling a production push trigger, qualify on disposable infrastructure:

- Exact-SHA source/build behavior and the configured Railway queries/mutation.
- Separate schema/application role credentials, private schema service, TLS,
  backward-compatible migrations, full ACL checks and database serialization.
- The maintenance command's complete success receipt and bounded retained logs.
- GitHub run-attempt read access, deployment record/status writes and rereads,
  action download at the full pinned SHA, and absence of other release writers
  on controller-owned targets.
- For version 1, a schema-success then single application-submission sequence,
  recorded IDs, and independent observation of serving readiness.
- For schema-only mode, one exact-SHA Maintenance submission/receipt and zero
  application-provider calls. Separately qualify native application triggers,
  Wait for CI behavior, startup compatibility and serving readiness. Native
  deployments may be queued or running independently; a schema-only result does
  not establish their submission, cancellation or health.

The fixed controller uses Railway GraphQL operations including
`serviceInstanceDeployV2`, `deployments`, and `deploymentLogs`. Offline fixtures
exercise the expected shapes; they do not guarantee provider API stability,
permissions, retention, or hosted semantics. Preflight checks selected settings,
not all effective container/environment behavior. No deployment activation is
implied by merging this repository.

### When a legacy release stops

The controller prints a fixed reason code and suppresses raw provider diagnostics.
Inspect GitHub deployment records and provider state privately. Never publish
tokens, connection strings, environment dumps or raw logs in an issue.

| Situation or reason | Next step |
| --- | --- |
| `wrong-workflow-context`, `unbound-workflow-run`, checkout mismatch | Correct repository/branch/workflow/permissions or checkout binding. No provider mutation is authorized by invalid context. |
| Policy path, blob, index or checkout mismatch | Commit the intended policy, check out that exact push SHA, and use a normalized path to a regular file. Avoid generated or edited policy files in the release job. |
| Config drift or enabled native autodeploy on a controller-owned target | Reconcile reviewed service settings and exclusive release ownership before retrying. Schema-only checks only Schema Maintenance. |
| `committed-railway-config-not-supported` | Move the reviewed legacy settings to the dashboard and remove all committed `railway.toml`/`railway.json` paths in a new reviewed commit; confirm null config bindings and qualify hosted behavior. |
| Candidate-tree path, size, time, or read failure | Inspect repository size and local Git availability. The action cannot prove config-file absence from an incomplete scan; do not bypass the check or silently raise its limits. |
| Schema migration/ACL failure | Version 1 has not submitted the application. Schema-only makes no application submission in any outcome; native applications may independently be queued or running, so inspect their state separately. Inspect the migration ledger and actual grants; correct forward. |
| `submission-unattributed-no-resubmit`, intent without a returned ID | Stop. Preserve the intent. A lost response might still have started a deployment. This action cannot resolve or resubmit it. |
| Recorded ID, observation timeout or missing receipt | Resume observation of that same ID after fixing read access or investigating the consumer result. Do not create another deployment. |
| Exact recorded ID has `FAILED`, `CRASHED`, `SKIPPED`, or one valid bound `DJANGO_RELEASE_FAILURE` result | The controller records that ID failed even if unrelated deployments appeared. Inspect consumer state, correct forward and use a new reviewed SHA. Same-SHA reruns do not resubmit. |
| Success with an unrelated post-baseline deployment | Remains unresolved and cannot authorize application submission. Investigate interference; never adopt the other deployment or delete evidence. |
| Version-1 application failure after schema success, or independently observed native application failure | Schema remains changed. Keep/observe the previous serving version if available, resolve the failure, and ship a new reviewed commit. Schema-only does not observe or record native application outcomes. |
| `prior-release-unresolved`, ambiguous/duplicate records or broken continuity | Reconcile the precise evidence through a reviewed recovery procedure. Never delete a record to make the history look empty. |
| Stale branch | No new submission from that stale check. An already recorded ID can still be observed. Release the current reviewed commit after prior outcomes are resolved. |
| History/status/log bound or rate-limit failure | Preserve evidence and investigate the bound or available reads. There is no automatic pruning or history reset. |

An initial provider/network failure may print `remote-response-unknown` or
`provider-response-unknown`. If an intent exists, treat the outcome as uncertain
even when no deployment appears in the current listing. A rerun with no durable
returned ID refuses. The same SHA, nearby creation time, same image, or a single
matching listing is **not** authoritative attribution. This version has no manual
adoption input; resolving an uncertain submission needs a separately reviewed
procedure supported by independent provider evidence. It must not invent a success
status or loosen these rules.

A successful migration followed by ACL failure may require the consumer's
least-privileged reconciliation command. A missing role may require separately
authorized consumer bootstrap recovery; the controller never creates roles or
supplies that authority. A bound `consumer-verification` failure may follow
committed migrations, so do not infer rollback or readiness from the failure.
Use a new reviewed SHA after a terminal failure. Partially applied non-atomic migrations
need migration-specific recovery. Cancelling a job cannot undo database writes.
There is no automatic schema rollback, image rollback, or native-autodeploy
reenablement. If the previous app cannot serve against the new schema, contain
access and recover forward; provider retention alone does not prove availability.

### Legacy upgrades and vulnerability response

For a version-1 to schema-only cutover, retain the workflow and concurrency
identity, consumer prefix, both deployment categories, and exact historical
application service UUID. Confirm both old history heads are terminal first.
No unresolved application record is silently abandoned; no application provider
lookup or submission is permitted by the new mode. The controller can still
observe an already attributed schema-only deployment or use its verified record
on a rerun. A lost submission response without a durable returned ID remains
blocked. Native application health and the safety of additive, backward-compatible
schema changes require independent consumer qualification.

Pin a full reviewed 40-character action commit. Upgrade through a reviewed PR that
changes that pin, verifies policy/receipt compatibility, and runs your consumer
fixtures and database checks. Tags do not silently update pinned consumers.

Account for unresolved release records before an upgrade. The candidate action
must understand their versions and safely resume them, or stop before mutation.
Never discard records, reinterpret unknown outcomes as fresh work, or downgrade
to code unable to read the current format. Use a compatible secure pin or a
separately reviewed read-only recovery investigation.

For a vulnerability, identify affected pinned consumers, contain their workflows
as appropriate, preserve unresolved evidence, and issue reviewed full-SHA fixes.
Follow [SECURITY.md](../SECURITY.md) for reporting. A code rollback is only usable
when secure and compatible; database/application recovery still moves forward.
