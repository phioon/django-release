# Configuration reference

The policy selects the contract; only `policy` and `railway-token` are required for v3:

| Input | Meaning |
| --- | --- |
| `policy` | Normalized relative path to a regular JSON file committed at the exact event SHA; all symlinks are refused. |
| `github-token` | Required only for legacy v1/v2: contents read, actions read, deployments write. Unused in v3. |
| `railway-token` | Project token scoped to the configured Railway environment. |

The runner must provide Python 3.11 and Git. The action supports GitHub.com and the
fixed Railway GraphQL endpoint; GitHub Enterprise Server and other providers are
not implemented. Use a Linux runner with descriptor-relative, no-symlink file
opens; the examples use GitHub-hosted Ubuntu. It has no action outputs. Its exit status indicates success or a
failed invocation. Version 3 uses the current provider attempt and receipt; only
legacy v1/v2 retain GitHub deployment records.

## Policy format 3: migrations-only

[policy-v3.schema.json](../schemas/policy-v3.schema.json) is the primary contract.
[Bookshop migrations](../tests/fixtures/bookshop-migrations.json) is a complete
fictional example. All listed fields are required. Unknown fields, duplicate
JSON keys, wrong types, incompatible versions and oversized input fail before
provider mutation.

| Field | Meaning |
| --- | --- |
| `format_version` | Integer `3`, independent of the action or receipt version. |
| `mode` | Exactly `"migrations-only"`. |
| `repository` | Exact trusted `owner/repository`. |
| `branch` | Trusted push branch, normally `main`. |
| `workflow` | Exact workflow path, such as `.github/workflows/release.yml`. |
| `consumer` | Lowercase consumer identity for the receipt. |
| `project_id`, `environment_id` | Exact Railway target UUIDs. |
| `schema` | The Schema Maintenance service expectation object below. |

There is no application target, historical application UUID or `acl_policy`.
The schema object requires exactly `service_id` (UUID), `name`, `config` (null),
`root_directory`, `start_command`, `healthcheck_path` (null), `restart_policy`
(`"NEVER"`) and `public_http` (false). Preflight compares the service name,
project/environment/service IDs, repository source, root directory and process
settings. Railway must report no image source, pre-deploy command, HTTP domains,
TCP proxies or config-file override, one replica and disabled native autodeploy.
The provider config binding may be null or the literal empty string; the policy
must use null. A null provider root is normalized to `/`. Disable Maintenance's
Wait for CI separately; this setting is a consumer qualification requirement.

The policy must be a regular committed blob at the exact `GITHUB_SHA`, with
matching index, worktree bytes and executable mode and no symlink components.
Use a normalized relative path; absolute paths, traversal, redundant separators,
untracked files and staged/working changes are refused. The controller parses
verified commit bytes, never a later reread of the working file. It validates
push event, repository, branch, workflow path, run/attempt identifiers and checkout
SHA locally. No GitHub API or branch-head lookup occurs in v3. Each trusted push
SHA is executed even if the branch has subsequently advanced.

As in the legacy modes, the exact candidate tree must contain no `railway.toml`
or `railway.json` anywhere. The bounded scan and dashboard-only requirements
below apply to v3 as well. Native service configuration and all consumer database
permissions remain outside the action's authority.

Each invocation waits for transient Maintenance deployments, submits exactly once
at the event SHA, then observes only the returned UUID using Railway's direct
`deployment(id: ...)` query. The active check uses a target-filtered `first: 1`
query excluding `SUCCESS`, `FAILED`, `CRASHED`, `REMOVED` and `SKIPPED`, without a
lifetime-history scan. `SUCCESS` may remain after a one-shot exits; it is not an
activity lock or a cached result. A prior receipt never satisfies the new attempt.
Failed/unknown submissions are not internally retried; another invocation starts
fresh after the activity check. V3 neither reads nor writes legacy GitHub records.

## Migration receipt v2

Policy v3 requires [receipt-v2.schema.json](../schemas/receipt-v2.schema.json).
The consumer emits exactly one `DJANGO_RELEASE_RESULT ` line with this strict
JSON shape **after its command's work has completed successfully**:

```json
{
  "format_version": 2,
  "repository": "example-bookshop/bookshop",
  "consumer": "bookshop",
  "source_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "project_id": "11111111-1111-4111-8111-111111111111",
  "environment_id": "12222222-2222-4222-8222-222222222222",
  "service_id": "13333333-3333-4333-8333-333333333333",
  "deployment_id": "55555555-5555-4555-8555-555555555555",
  "migrations_verified": true
}
```

These values are fictional. Obtain and verify actual source and provider identities
inside the consumer command; do not copy an example into a success printer.
`migrations_verified` means the complete expected migration graph is applied.
Emit success only after all work the consumer command requires has passed, including
its own permission checks if present. This receipt makes no generic ACL,
provisioning or runtime-health claim, and contains no `acl_verified` or `acl_policy`.
Receipt v1 remains unchanged and is required by legacy policies v1/v2.

Success requires exact target, SHA and returned deployment ID, provider status
`SUCCESS` or `REMOVED`, and this matching current receipt. `FAILED`, `CRASHED` and
`SKIPPED` fail before reading logs, even if a success-looking receipt exists.
Unknown/cancelled states fail. Build/queue states keep polling without reading
logs. A receipt alone cannot pass a non-successful deployment. A removed deployment
without the receipt cannot pass either.

The log window must contain fewer than 500 lines and a result at most 4 KiB.
Missing results keep polling to the fixed timeout. Malformed, duplicate,
wrong-version, wrong-identity or extra-field receipts fail. Any
`DJANGO_RELEASE_FAILURE ` marker fails v3, including the legacy failure-v1
consumer diagnostic. Mixed success and failure cannot pass. These checks do not
implement migrations, database locking, permissions or developer repair procedures.

## Policy format 1

**Legacy compatibility only.** The remainder of this section describes v1.

[policy-v1.schema.json](../schemas/policy-v1.schema.json) is the executable field
contract. [Bookshop](../tests/fixtures/bookshop.json) is a complete example.
All defined fields are required; unknown fields, duplicate JSON keys, incompatible
versions, wrong types and oversized values fail before provider mutation.

The policy must be a regular blob in `GITHUB_SHA`, at a normalized relative path
such as `.github/django-release.json`. Absolute paths, `..`, redundant `./` or
slashes, symlink files/directories, untracked files, staged changes and modified
working copies are rejected. The index, working bytes and file mode must match
the committed blob. The controller parses the verified committed bytes rather
than reopening the working file, so a later edit cannot change the release policy.
Commit legitimate policy changes and release their new SHA.

| Field | Meaning |
| --- | --- |
| `format_version` | Integer `1`, not the action's release version. |
| `repository` | Exact `owner/repository` of the caller. |
| `branch` | Trusted push branch, normally `main`. |
| `workflow` | Exact workflow path, such as `.github/workflows/release.yml`. |
| `consumer` | Unique lowercase record prefix within the caller repository. |
| `project_id`, `environment_id` | Railway target UUIDs. |
| `schema`, `application` | Separate service expectation objects, described below. |
| `acl_policy` | Consumer-defined, bounded identifier for the complete ACL policy the receipt verifies. |

Each service object requires `service_id` (UUID), `name`, `config` (always JSON
`null` in version 1), `root_directory`, `start_command`, `healthcheck_path` (string or null),
`restart_policy` (`NEVER`, `ON_FAILURE`, or `ALWAYS`), and `public_http` (boolean).
These are expected provider settings: the action compares them and does not run
the command locally or change those settings. Railway must report your repository
as the source, no image source, no pre-deploy command, one replica, disabled native
autodeploy, no config-file override, and no TCP proxies. A null Railway root
directory is normalized to `/`.

Configure both services in Railway's dashboard. Non-null legacy `config` paths
are unsupported in version 1: matching dashboard values cannot prove effective
settings when a config file can override them. Before adoption, move your reviewed
process settings to the dashboard and remove the service's config-file binding.
Railway may report an absent binding as `railwayConfigFile: null` or the literal
empty string `""`; the action accepts exactly those two provider representations.
Whitespace, nonempty paths and other types are rejected. Your committed policy
must still use `config: null`. Qualify the resulting deployment settings in a
disposable environment. This action neither reads legacy Railway config files
nor performs that migration for you.

Railway can also discover `railway.toml` or `railway.json` automatically when the
explicit config-file binding is null. Version 1 therefore rejects **any committed
path anywhere in the candidate repository** with either exact basename, including
nested service roots and unrelated directories. Remove these legacy files in the
reviewed candidate after transferring their settings to the dashboard. Similar
names such as `railway.toml.example` are allowed; they are not these default names.
The action inspects the exact `GITHUB_SHA` tree with Git replacement objects
disabled, before any provider request. It streams at most 50,000 paths (including
directories), 4,000,000 bytes of path output, and 30 seconds. Exceeding any bound,
an unavailable tree, or incomplete output stops the release; it never assumes
that an incomplete scan proved the files absent.

Schema Maintenance must have `public_http: false`, `healthcheck_path: null`, and
`restart_policy: "NEVER"`. The two service IDs must differ. With `public_http:
false`, any service/custom HTTP domain fails preflight; `true` allows HTTP domains
without claiming that a particular domain or route is healthy. Private network,
database TLS, role separation, build behavior and effective credentials need
separate consumer qualification; the controller cannot infer them from these fields.

Policy changes at an existing SHA are rejected by a canonical JSON SHA-256 digest.
Target identity changes require a separately reviewed record transition; do not
rename a consumer prefix to evade unresolved records. There are no environment
variable substitutions, secret fields, optional command hooks or automatic defaults.

## Policy format 2: schema-only

**Legacy compatibility only.** V2 retains the history and ACL contract.

[policy-v2.schema.json](../schemas/policy-v2.schema.json) requires
`format_version: 2` and `mode: "schema-only"`. Keep the version-1 repository,
branch, workflow, consumer, project/environment, schema and ACL-policy fields.
Replace `application` with `historical_application_service_id`: the exact UUID
from the prior version-1 application policy, or JSON `null` only for a consumer
that has never had application records. There are no application process settings
in this policy. Unknown or omitted fields fail validation.

This mode preflights, lists, submits and observes **only Schema Maintenance** at
the exact event SHA. It makes zero application-provider calls, including reads.
Native application deployment settings and serving health are consumer-owned.
The candidate-tree prohibition and all schema-service isolation requirements
remain in force. Native applications must safely wait for their own required
migrations and effective runtime ACLs without migration credentials or writes;
Maintenance and startup checks need compatible database serialization.

Upgrades preserve both GitHub deployment categories, historical service identities
and `previous_heads`. Keep the existing workflow path and concurrency group.
The controller still validates the old application's terminal history and schema
predecessor; it never recreates, deletes, or rewrites those records. A missing or
different historical application UUID cannot bypass existing records. Any
unresolved legacy application outcome blocks schema-only execution, including a
candidate with the same SHA. Resolve it through the original release's reviewed
recovery procedure before cutover. An unresolved earlier schema outcome also
blocks the new candidate. A changed policy cannot resume an existing same-SHA
schema intent because its policy digest differs.

Record and receipt formats remain version 1, independently of policy version.
New schema-only records retain both prior heads and the version-2 policy digest.
Older action pins reject policy version 2: do not downgrade or change identities
to evade history. New native application deployments create no action-owned
application records and are not represented as application verification success.

## Maintenance receipt

This receipt-v1 section applies only to legacy policies v1/v2.

The consumer's maintenance process emits one single-line JSON object after its
full migration graph and ACL checks pass, prefixed by `DJANGO_RELEASE_RESULT `.
[receipt-v1.schema.json](../schemas/receipt-v1.schema.json) defines its fields:

```json
{
  "format_version": 1,
  "repository": "example-bookshop/bookshop",
  "consumer": "bookshop",
  "source_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "project_id": "11111111-1111-4111-8111-111111111111",
  "environment_id": "12222222-2222-4222-8222-222222222222",
  "service_id": "13333333-3333-4333-8333-333333333333",
  "deployment_id": "55555555-5555-4555-8555-555555555555",
  "migrations_verified": true,
  "acl_verified": true,
  "acl_policy": "bookshop-acl-v1"
}
```

The example IDs and SHA are fictional. The real process must obtain and verify its
actual source and provider identities; never copy these constants into a success
printer. It must exit nonzero on migration or ACL failure and must not emit a
success receipt prematurely. `migrations_verified` means the complete expected
migration graph is applied. `acl_verified` means the complete consumer policy
passed, including unwanted privilege checks, not just that one grant succeeded.
The action compares every field to the expected policy and returned deployment.
Malformed, duplicate, contradictory, wrong-target, wrong-SHA, or missing receipts
cannot authorize application submission. Logs and process exit alone cannot supply
the meaning of these checks; your command and database tests must establish it.

## Maintenance failure result

This bound failure-v1 recovery contract applies to legacy v1/v2. V3 treats any
failure marker as a failed invocation and writes no records.

A consumer may emit one single-line `DJANGO_RELEASE_FAILURE ` JSON object after
its trusted source and provider identity checks succeed. The strict
[failure-v1.schema.json](../schemas/failure-v1.schema.json) requires exactly
`format_version: 1`, `repository`, `consumer`, `source_sha`, `project_id`,
`environment_id`, `service_id`, `deployment_id`, and `stage`. The identity fields
have the same meaning and binding as the success receipt. `stage` is exactly
`migration` or `consumer-verification`; arbitrary messages, exception details,
credentials, and additional fields are forbidden. The failure certifies no ACL
policy or schema readiness. Setup/preflight failures before the consumer can
establish trusted stage evidence must not fabricate this result.

For example, using the fictional identities above:

```json
{
  "format_version": 1,
  "repository": "example-bookshop/bookshop",
  "consumer": "bookshop",
  "source_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "project_id": "11111111-1111-4111-8111-111111111111",
  "environment_id": "12222222-2222-4222-8222-222222222222",
  "service_id": "13333333-3333-4333-8333-333333333333",
  "deployment_id": "55555555-5555-4555-8555-555555555555",
  "stage": "consumer-verification"
}
```

The controller reads only the durably submitted deployment's bounded log window.
Exactly one valid, fully bound failure result records that deployment failed even
if the provider reports `SUCCESS` or unrelated deployments appeared after the
baseline. Duplicate success/failure lines, mixed success and failure, malformed
JSON, unknown fields or stages, and wrong identity remain unresolved. A provider
`FAILED`, `CRASHED` or `SKIPPED` state on the exact bound deployment independently
establishes failure without requiring logs. Unrelated deployments are never adopted.
After durably recording a provider failure, the controller attempts to read a valid
failure marker for a fixed `schema-migration-failed-forward-recovery-required` or
`schema-consumer-verification-failed-forward-recovery-required` diagnostic. Absent,
unavailable or invalid logs retain the failed record and the generic
`schema-forward-recovery-required` diagnostic. Record/status formats do not gain
a stage field; a later same-SHA rerun uses that terminal record and generic reason.
A known failure requires a new reviewed SHA; an unresolved rerun only observes
its existing UUID. Action inputs, policy v1/v2, success receipts and record/status
formats remain unchanged. Older action pins do not recognize failure results;
upgrade the controller before relying on them.

## Release records

Legacy v1/v2 only. V3 never reads, validates, rewrites or appends these records.

[record-v1.schema.json](../schemas/record-v1.schema.json) defines the immutable
deployment payload. It binds `format_version: 1`, `repository`, `consumer`, `phase`,
`source_sha`, `workflow`, integer `run_id` and `run_attempt`, all three target IDs,
`policy_sha256`, `before` (at most 1,000 unique provider deployment IDs), and
`previous_heads` (schema/application GitHub deployment IDs or null).

Only `github-actions[bot]` records/statuses are accepted. GitHub envelope metadata
can contain its normal additional API fields; the owned payload cannot. Active
records are checked against `/actions/runs/{run_id}/attempts/{run_attempt}` including
repository, head repository, branch, push event, workflow path and SHA.

Statuses use a compact versioned description within GitHub's description limit:

| Description | GitHub state | Meaning |
| --- | --- | --- |
| No status | — | Durable intent; submission outcome may be unknown. |
| `v1:submitted:<UUID>` | `in_progress` | Returned provider ID durably retained. |
| `v1:verified:<UUID>` | `success` | That ID passed phase checks. |
| `v1:failed:<UUID>` | `failure` | That ID was observed failed; recover forward. |
| `v1:stale:none` | `failure` | Branch advanced before provider call; no submission. |

A submitted status must precede verified/failed status and retain the same ID.
Contradictory histories fail closed. `log_url` binds the original intent's run;
a later attempt can observe the same ID without changing original ownership.
Statuses are append-only with `auto_inactive: false`. Never delete or rewrite
records as a recovery shortcut. Future unknown formats are refused before mutation.
