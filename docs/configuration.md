# Configuration reference

All three action inputs are required:

| Input | Meaning |
| --- | --- |
| `policy` | Normalized relative path to a regular JSON file committed at the exact event SHA; all symlinks are refused. |
| `github-token` | Caller `GITHUB_TOKEN`: contents read, actions read, deployments write. |
| `railway-token` | Project token scoped to the configured Railway environment. |

The runner must provide Python 3.11 and Git. The action supports GitHub.com and the
fixed Railway GraphQL endpoint; GitHub Enterprise Server and other providers are
not implemented. Use a Linux runner with descriptor-relative, no-symlink file
opens; the examples use GitHub-hosted Ubuntu. It has no action outputs. Its exit status indicates success or a
blocked release; durable deployment records hold the identities and outcome.

## Policy format 1

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
Confirm the provider reports `railwayConfigFile: null` and qualify the resulting
deployment settings in a disposable environment. This action neither reads legacy
Railway config files nor performs that migration for you.

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

## Maintenance receipt

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

## Release records

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
