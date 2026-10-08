# Contributing

Use Python 3.11 and Git. There are no third-party runtime or test dependencies.
Start with [how it works](docs/how-it-works.md) and the
[recovery contract](docs/security-recovery.md). Make changes on a branch and submit
a pull request. Keep examples fictional and never include credentials or private
deployment evidence. Do not generate or author Django migrations in this project.

Run these offline checks from the repository root:

```sh
python3 -B scripts/check_release.py
python3 -B scripts/run_tests.py
git diff --check
```

`check_release.py` checks JSON contracts, Python syntax, fixed action structure,
workflow pins, metadata and local documentation links. Its YAML checks are narrow
structural checks, not a general YAML parser or GitHub's hosted workflow validator.
`run_tests.py` discovers and counts the tests, fails if there are none, and runs
them with verbose unittest output. Direct `python3 -B -m unittest discover -s tests
-v` remains useful for diagnosis, but CI uses the wrapper to prevent empty success.
The tests inject fictional GitHub/Railway responses, including failures around
submission and persistence. They never contact providers or execute migrations.
Policy-binding tests create isolated temporary Git objects to test real committed,
staged, modified and symlinked paths. They never change this repository's refs.

Add meaningful regression cases for changed behavior, especially format upgrades,
ordering, run/attempt binding, history continuity, uncertainty, and wrong-target
responses. Keep the versioned schemas aligned with the controller's small supported
JSON Schema subset. The schemas are strict owned payload contracts; normal
third-party API envelope metadata is outside those contracts.

Update the affected public documentation with implementation changes. Independent
review is required for authority, persistent record, recovery, and secret-handling
changes. Hosted CI, provider qualification, database tests and serving-readiness
evidence are separate from these offline checks. Repository policy files describe
the desired review/protection settings; their presence does not establish that
GitHub has applied them.

The code and associated documentation are licensed under the [MIT License](LICENSE).
By submitting a contribution, you agree to license it under the same MIT License.
