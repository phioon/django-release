# Django release

A small GitHub composite action that runs your Django schema preparation on
Railway and verifies its exact-commit result. Policy version 1 then submits your
serving application at that commit. Explicit version-2 `schema-only` mode leaves
application deployment to your platform. Your workflow controls when it runs and
which credentials it receives.

Django migrations describe changes to your database. Deploying code that needs a
new table before creating that table can break startup. This action separates the
work: a private, short-lived **Schema Maintenance** service applies reviewed
migrations and checks database permissions; the normal application deploys only
after that service produces a verified success receipt in version 1. In schema-only
mode, your independently deployed application needs its own read-only startup
compatibility gate; this action neither implements that gate nor checks serving health.

The application uses a limited database role for its everyday queries. Maintenance
uses a more privileged role because changing tables and granting permissions need
extra authority. Keep those credentials separate. The action itself receives no
database password and does not generate migrations or implement your permissions.

## Before you start

The quickstart below describes the unchanged version-1 two-service mode. For
native application deployments, use the [version-2 schema-only contract](docs/configuration.md#policy-format-2-schema-only)
and its upgrade/recovery requirements. Only Schema Maintenance is a provider
target in that mode; disable native autodeploy on that service. Preserve the
consumer, workflow, concurrency group and both historical deployment categories.

This first delivery supplies source and offline tests. It is not evidence of a
working deployment in your account. Qualify the Railway API operations, service
settings, receipt logs, database permissions, and actual serving health in a
disposable environment before enabling the workflow for production.

You need:

- A Django application whose reviewed migrations and permission changes remain
  compatible with the currently serving version.
- Two separate Railway services in one project/environment: private, one-shot
  Schema Maintenance and the serving application. Disable native autodeploy on
  both. Configure their process settings in Railway's dashboard, with no config-file
  override (`config: null`). The candidate commit must have no `railway.toml` or
  `railway.json` anywhere, including nested service roots: Railway can discover
  these files automatically even without an explicit binding. Use one replica
  each, no pre-deploy commands and no TCP proxies.
- Your own tested maintenance command that serializes database work, migrates the
  complete migration graph, reconciles and verifies the full ACL policy, and emits
  the [versioned receipt](docs/configuration.md#maintenance-receipt). ACL means the
  database's access-control permissions. A zero exit code alone is insufficient.
- A Railway project token for that environment, stored as a GitHub Actions secret.
  It can cover multiple services; it is not a service-scoped token. Do not put it
  in either service's variables.
- A trusted push workflow, Python 3.11, and a reviewed full commit SHA of this
  action. Protect workflow, policy, maintenance code, and migration changes through
  your repository's review rules.

## Quickstart

1. Copy [the fictional bookshop policy](tests/fixtures/bookshop.json) to
   `.github/django-release.json` in your application repository. Replace every
   identity and process expectation with your reviewed dashboard settings. Keep
   `config: null` for both services; this version does not support Railway config
   files anywhere in the candidate repository. Remove legacy default config files
   after moving their reviewed settings to the dashboard. Commit the policy with
   the application changes. The action rejects
   untracked, changed, staged, or symlinked policy files. The reference
   command `release_schema` is a command **you must implement**; this action does
   not install it. See [configuration](docs/configuration.md).
2. Implement and test maintenance and its receipt on a disposable database. Check
   the service isolation and recovery checklist in [security and recovery](docs/security-recovery.md).
3. Add the workflow below after those prerequisites are verified. Replace
   `REVIEWED_ACTION_COMMIT_SHA` with a real reviewed 40-character commit. The
   placeholder deliberately does not select an unreviewed release.

```yaml
name: Release
on:
  push:
    branches: [main]
permissions:
  contents: read
  actions: read
  deployments: write
concurrency:
  group: bookshop-production-release
  cancel-in-progress: false
jobs:
  release:
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
          github-token: ${{ secrets.GITHUB_TOKEN }}
          railway-token: ${{ secrets.RAILWAY_PROJECT_TOKEN }}
```

The caller's GitHub environment, timeout, concurrency, token scope, and review
requirements remain visible here. `actions: read` lets the action validate the
repository, workflow, branch, SHA, run, and attempt behind a release record. Each
consumer needs its own concurrency group, policy, provider token and records.

This action repository is public. If you host a private copy, first follow the
[private-action access and download check](docs/examples.md#private-action-download-check)
before adding provider secrets. GitHub manages the action-download credential;
you do not need a personal access token.

After setup, a reviewed push to `main` is the routine release trigger. A failed or
uncertain release stops. Rerunning never repeats an unattributed submission.
Inspect the two GitHub deployment categories and follow the recovery guide; do
not delete evidence to unlock a retry. A successful provider deployment status
still requires your own serving-readiness check.

Maintenance may emit a strict, identity-bound
[failure result](docs/configuration.md#maintenance-failure-result) with only the
stage `migration` or `consumer-verification`. Exact recorded failures remain
attributable even when unrelated deployments interfere; success under interference
still stops. A terminal failed SHA requires a new reviewed commit, while an
unresolved rerun observes its already recorded deployment.

## Learn more

- [How the action works](docs/how-it-works.md): ordering, records, reruns and limits.
- [Configuration reference](docs/configuration.md): every input and data contract.
- [Security, recovery and upgrades](docs/security-recovery.md): privileges and failures.
- [Examples](docs/examples.md): two independent fictional consumers and receipts.
- [Contributing](CONTRIBUTING.md) and [security reporting](SECURITY.md).

The code and associated documentation are available under the [MIT License](LICENSE).
