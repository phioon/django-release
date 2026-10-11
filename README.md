# Django release

A small GitHub composite action that runs Django migrations on Railway and
verifies the result for the exact push commit. The primary contract is policy
version 3, `mode: "migrations-only"`: every invocation starts a fresh **Schema
Maintenance** deployment, including a retry of the same SHA. It succeeds only
when that attempt produces a matching migration receipt.

Your push workflow runs Maintenance independently of Railway's Wait for CI.
After the workflow passes, Railway can deploy your other native services with
Wait for CI enabled. This action has no application deployment calls in v3, no
GitHub deployment ledger, and no historical-success shortcut. Policy versions
1 and 2 retain their [legacy behavior](docs/configuration.md#policy-format-1).

The consumer supplies the maintenance command: acquire a database lock, apply the
reviewed migration graph, verify it, and emit the receipt after the command's work
completes. Database roles, least-privilege grants and provisioning remain consumer
responsibilities. The generic receipt verifies migrations; it does not certify
permissions or serving health. No database credentials enter the action.
See the [consumer database role pattern](docs/security-recovery.md#consumer-database-roles)
for migrator/runtime separation and future-object default privileges.

## Before you start

You need:

- A reviewed migration command safe to run again, with database serialization and
  changes compatible with the currently serving code. The action does not create
  migrations, install a Django command, repair migration history, or grant permissions.
- A private, one-shot Railway Schema Maintenance service in the intended project
  and environment. Disable its native autodeploy and Wait for CI so it can run
  while the workflow is in progress. Use one replica, restart policy `NEVER`, no
  healthcheck, no pre-deploy command, and no HTTP domains or TCP proxies.
- Reviewed Maintenance dashboard configuration with `config: null`. The candidate
  repository must contain no `railway.toml` or `railway.json` anywhere: Railway
  can discover these files even without an explicit config-file binding.
- A Railway project token scoped to the environment, stored as a GitHub Actions
  secret. It can reach multiple services; it is not a service-scoped credential.
  Never put it in service variables.
- A trusted push workflow, Python 3.11, and a reviewed full commit SHA of this
  action. Protect the workflow, policy, maintenance command and migrations with
  your repository's review rules.

Qualify the API, exact-SHA build behavior, service isolation, migration command,
locking and receipt logs on disposable infrastructure before production. Offline
source tests do not establish deployed behavior.

## Quickstart

1. Copy [the fictional migrations-only policy](tests/fixtures/bookshop-migrations.json)
   to `.github/django-release.json`. Replace the identities and process expectations
   with your reviewed settings. The example `migrate_release` command is one **you
   must implement**. Commit the policy; modified, staged, untracked and symlinked
   policies are rejected. See the [configuration contract](docs/configuration.md#policy-format-3-migrations-only).
2. Implement and test the [migration receipt](docs/configuration.md#migration-receipt-v2),
   including identity checks and database locking. Resolve permissions and
   provisioning through your consumer's own reviewed process.
3. Save this workflow at the exact policy `workflow` path. Replace
   `REVIEWED_ACTION_COMMIT_SHA` with a reviewed 40-character commit.

```yaml
name: Migrations
on:
  push:
    branches: [main]
permissions:
  contents: read
jobs:
  migrations:
    runs-on: ubuntu-24.04
    timeout-minutes: 45
    environment: production
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1
        with:
          ref: ${{ github.sha }}
          persist-credentials: false
      - uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97
        with:
          python-version: '3.11'
      - uses: phioon/django-release@REVIEWED_ACTION_COMMIT_SHA
        with:
          policy: .github/django-release.json
          railway-token: ${{ secrets.RAILWAY_PROJECT_TOKEN }}
```

Run this required workflow on every `main` push. Do not add path filters,
conditional skips, `continue-on-error`, or a concurrency group that cancels queued
runs. Database locking belongs in Maintenance. Enable native deployment and
**Wait for CI on the other services**, keeping Maintenance independent of that
wait to avoid a circular dependency.

Railway evaluates workflow conclusions: skipped or neutral runs do not block,
and a cancelled run can be ignored when another workflow on the commit passes.
See [Railway's Wait for CI rules](https://docs.railway.com/deployments/github-autodeploys#wait-for-ci).
Qualify this behavior and keep the migration workflow required and non-cancelling.
A consumer-owned, read-only startup schema gate provides containment when native
deployment proceeds without the required migrations. This action does not implement
that gate or verify application health.

## Failure and retry

A failed, unknown, cancelled or timed-out invocation does not pass the migration
check. A new workflow invocation submits another exact-SHA Maintenance deployment;
it never reuses an earlier receipt. The controller does not repeat a mutation
within an invocation when its response is uncertain.

Before submission it waits for transient Maintenance deployments within a fixed
bound. Retained `SUCCESS` deployments do not veto a retry, because successful
one-shot processes can keep that status after exit. This check is not proof that
all processes have exited. A fresh Railway deployment may interrupt an older
process; the consumer's lock serializes database work but cannot prevent that
interruption. Inspect partial non-atomic migrations and repair them through a
reviewed developer procedure outside the workflow. See [recovery](docs/security-recovery.md).

## Legacy compatibility and more

Version 1 deploys schema then application. Version 2 `schema-only` submits only
Maintenance but keeps the legacy GitHub history, ACL receipt and recovery rules.
Their reruns observe existing IDs; those rules do not apply to version 3. Existing
records remain untouched and unread by v3. Adopting v3 requires an explicit
reviewed policy and receipt change.

- [How it works](docs/how-it-works.md): current attempts, observation bounds and legacy behavior.
- [Configuration](docs/configuration.md): strict versioned policy and receipt contracts.
- [Security and recovery](docs/security-recovery.md): privileges, failure handling and upgrades.
- [Examples](docs/examples.md): fictional consumers and private-action download qualification.
- [Contributing](CONTRIBUTING.md) and [security reporting](SECURITY.md).

The code and associated documentation are available under the [MIT License](LICENSE).
