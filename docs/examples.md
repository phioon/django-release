# Fictional consumers

## Migrations-only consumers (v3)

[Bookshop](../tests/fixtures/bookshop-migrations.json) and
[Observatory](../tests/fixtures/observatory-migrations.json) are independent,
fictional v3 consumers with separate repositories and Railway targets. Their
policies have only a Maintenance target and migration receipt identity, with no
application or ACL policy fields. The example command `python manage.py
migrate_release` is consumer-implemented; this action supplies no Django command.

Each command acquires its database lock, applies and verifies the reviewed
migration graph, and prints the strict [receipt v2](configuration.md#migration-receipt-v2)
only after its work completes. Consumers can implement their own provisioning
and permission checks, but those policies are not part of the generic receipt.
Use the [v3 push workflow](../README.md#quickstart) without cancellation or skips;
the database lock provides migration serialization.

For example, after Maintenance succeeds, rerunning the same push workflow submits
another deployment at the same SHA and requires that new ID's receipt. After a
lost submission response, the current invocation fails without an internal
resubmit; a new invocation checks transient activity and submits fresh work.
A receipt from the earlier UUID cannot pass the new check, even for the same SHA.
Partial non-atomic migration repairs remain developer-owned outside this workflow.

## Legacy consumers (v1/v2)

The following record categories, ACL identifiers and rerun examples belong only
to the legacy modes. They remain compatible and are not required by v3.

The legacy offline suite uses two independent applications:

| Consumer | Repository | Record categories | ACL identifier |
| --- | --- | --- | --- |
| Bookshop | `example-bookshop/bookshop` | `bookshop-release-schema`, `bookshop-release-application` | `bookshop-acl-v1` |
| Observatory | `example-observatory/observatory` | `observatory-release-schema`, `observatory-release-application` | `observatory-acl-v1` |

Their complete policies are [bookshop.json](../tests/fixtures/bookshop.json) and
[observatory.json](../tests/fixtures/observatory.json). All service/project IDs are
fictional. They use the same controller without shared tokens, targets, records,
or application-specific database policy. In your caller workflow, also use distinct
concurrency groups such as `bookshop-production-release` and
`observatory-production-release`.

Bookshop's schema command might verify the application's tables and its reporting
role. Observatory might have a different set of tables and no reporting role.
The shared action knows neither policy. Each consumer's reviewed command must
verify its entire migration graph and ACL policy before emitting its receipt.
The fixture command `python manage.py release_schema` is illustrative; no such
management command is supplied here.

## Emitting the result (all modes)

After all checks have succeeded, your own Python maintenance command can serialize
its verified result in this form:

```python
# verified_result contains actual verified bindings and every required receipt
# field from docs/configuration.md. This is the final output step, not the checks.
print("DJANGO_RELEASE_RESULT " + json.dumps(verified_result, separators=(",", ":")), flush=True)
```

Emit exactly one line. Do not print success in an exception handler or before the
transaction/checks complete. Use receipt v2 for policy v3 and the unchanged
full ACL receipt v1 for legacy policies v1/v2. Do not rely on the log line to prove the command's
correctness: test your database behavior separately. If schema changes have been
committed but permission checks fail, exit nonzero without a success receipt and
use the recovery procedure.

## Legacy rerun examples

If Schema Maintenance succeeded and the job stopped after storing the application's
returned deployment ID, a rerun observes that ID. It does not submit the app again.
If Railway accepted the schema request but the response was lost, the record has
only the intent. A rerun stops even if one same-SHA deployment is visible. This
protects the consumer from repeating work whose outcome is unknown.

Run the fictional checks with `python3 -B scripts/run_tests.py` using
Python 3.11. They make no network calls and do not need Railway or GitHub secrets.
They prove source behavior under simulated responses, not hosted readiness.

## Private-action download check

The upstream action repository is public. This section applies only if you maintain
a private action repository or private copy. In that action repository's Actions
settings, allow access by the intended caller repositories. The caller's allowed-actions
policy must also permit the action and its complete pinned commit. Available sharing
choices depend on your organization and GitHub plan.

GitHub supplies a managed, short-lived installation credential to download an
allowed private action. Do not add a personal access token or cross-repository
download secret. The caller's release `GITHUB_TOKEN` and Railway token are separate
runtime inputs; neither is needed for the download check below.

Before installing provider secrets, create a temporary workflow like this in the
caller. Replace `example-private/django-release` with the actual private action
repository, and `REVIEWED_ACTION_COMMIT_SHA` with its reviewed full commit. Leave
the deliberately nonexistent policy path absent from the caller repository.

```yaml
name: Private action download check
on:
  workflow_dispatch:
permissions:
  contents: read
jobs:
  download:
    runs-on: ubuntu-24.04
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1
        with:
          ref: ${{ github.sha }}
          persist-credentials: false
      - uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97
        with:
          python-version: '3.11'
      - uses: example-private/django-release@REVIEWED_ACTION_COMMIT_SHA
        with:
          policy: .github/action-download-probe-does-not-exist.json
          github-token: download-probe-no-token
          railway-token: download-probe-no-token
```

This is an intentionally failing smoke test. Successful download and execution
produce the controller message `django-release blocked:
policy-must-be-committed-regular-blob`. Confirm that exact reason in the action
step's log. A red job alone proves nothing: an action-resolution error or a different
controller error is not a passing download check. The absent committed policy
stops processing before any GitHub API or Railway request; both input values are
inert placeholders. Remove the temporary workflow after the observed download
check, then qualify the actual release workflow and provider prerequisites before
binding real secrets. Download access alone does not establish deployment authority.
