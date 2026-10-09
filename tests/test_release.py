"""Offline fictional consumers; real controller/client paths with injected I/O."""

import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import controller as c


SHA = "a" * 40
OTHER = "b" * 40
IDS = {"schema": "55555555-5555-4555-8555-555555555555",
       "application": "66666666-6666-4666-8666-666666666666"}
EXTERNAL = "77777777-7777-4777-8777-777777777777"


def policy(name="bookshop"):
    return c.load_policy(c.ROOT / "tests/fixtures" / (name + ".json"))


class Ledger:
    """REST fixture exercising the real GitHub record/continuity implementation."""
    def __init__(self, p, events):
        self.policy, self.events = p, events
        self.rows, self.statuses, self.calls = [], {}, []
        self.current, self.runs = SHA, {}
        self.run_reads, self.forbid_runs = 0, False
        self.mutate_created = None
        self.fail_create, self.fail_status = False, None

    def add(self, payload):
        row = {"id": len(self.rows) + 1, "sha": payload["source_sha"],
               "payload": copy.deepcopy(payload), "creator": {"login": c.BOT},
               "environment": self.policy["consumer"] + "-release-" + payload["phase"]}
        self.rows.append(row)
        self.runs[(payload["run_id"], payload["run_attempt"])] = self.run(
            payload["source_sha"], payload["run_id"], payload["run_attempt"])
        return row

    def run(self, sha, number, attempt):
        return {"id": number, "run_attempt": attempt, "head_sha": sha, "event": "push",
                "head_branch": self.policy["branch"], "path": self.policy["workflow"],
                "repository": {"full_name": self.policy["repository"]},
                "head_repository": {"full_name": self.policy["repository"]}}

    def api(self, path, data=None):
        self.calls.append((path, data))
        parsed = urlsplit(path)
        parts = parsed.path.strip("/").split("/")
        if parts[:2] == ["git", "ref"]:
            return {"object": {"sha": self.current}}
        if parts[:2] == ["actions", "runs"]:
            self.run_reads += 1
            if self.forbid_runs:
                raise c.Blocked("remote-response-unknown")
            number, attempt = int(parts[2]), int(parts[4])
            return copy.deepcopy(self.runs.get((number, attempt), self.run(SHA, number, attempt)))
        if parts == ["deployments"] and data is None:
            q = parse_qs(parsed.query)
            rows = [r for r in reversed(self.rows) if r["environment"] == q["environment"][0]
                    and ("sha" not in q or r["sha"] == q["sha"][0])]
            return copy.deepcopy(rows[:int(q["per_page"][0])])
        if parts == ["deployments"]:
            assert data["ref"] == data["payload"]["source_sha"]
            assert data["auto_merge"] is False and data["required_contexts"] == []
            row = self.add(data["payload"])
            self.events.append("intent:" + row["payload"]["phase"])
            if self.mutate_created:
                self.mutate_created(row)
            if self.fail_create:
                raise c.Blocked("remote-response-unknown")
            return copy.deepcopy(row)
        if len(parts) == 2 and parts[0] == "deployments":
            return copy.deepcopy(next(r for r in self.rows if r["id"] == int(parts[1])))
        if len(parts) == 3 and parts[2] == "statuses":
            number = int(parts[1])
            if data is None:
                return copy.deepcopy(list(reversed(self.statuses.get(number, [])))[:20])
            assert data["auto_inactive"] is False
            if self.fail_status and self.fail_status in data["description"]:
                raise c.Blocked("remote-response-unknown")
            row = {**data, "creator": {"login": c.BOT}}
            self.statuses.setdefault(number, []).append(row)
            phase = next(r["payload"]["phase"] for r in self.rows if r["id"] == number)
            self.events.append(data["description"].split(":")[1] + ":" + phase)
            return copy.deepcopy(row)
        raise AssertionError("Unexpected fixture REST path: " + path)


class Provider:
    def __init__(self, p, events):
        self.policy, self.events, self.rows = p, events, []
        self.status, self.lost, self.absent = {}, set(), set()
        self.receipt_valid, self.preflight_error = True, None
        self.on_submit, self.on_receipt = None, None

    def preflight(self, phase):
        if self.preflight_error:
            raise c.Blocked(self.preflight_error)

    def deployments(self, service):
        return copy.deepcopy([r for r in self.rows if r["serviceId"] == service])

    def submit(self, service, sha):
        phase = next(p for p in c.PHASES if self.policy[p]["service_id"] == service)
        self.events.append("submit:" + phase)
        row = {"id": IDS[phase], "serviceId": service, "projectId": self.policy["project_id"],
               "environmentId": self.policy["environment_id"], "status": self.status.get(phase, "SUCCESS"),
               "meta": {"commitHash": sha}}
        if phase not in self.absent:
            self.rows.append(row)
        if self.on_submit:
            self.on_submit(row)
        if phase in self.lost:
            raise c.Blocked("provider-response-unknown")
        return row["id"]

    def receipt(self, deployment, expected):
        self.events.append("receipt:schema")
        c.contract(expected, "receipt")
        if self.on_receipt:
            self.on_receipt()
        return "verified" if self.receipt_valid else None


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.p, self.events = policy(), []
        self.ledger = Ledger(self.p, self.events)
        self.github = c.GitHub(self.p, "fictional-token")
        self.github.api = self.ledger.api
        self.provider = Provider(self.p, self.events)

    def execute(self, sha=SHA, attempt=1):
        run_id = 999 if sha == SHA else 1000
        self.ledger.runs[(run_id, attempt)] = self.ledger.run(sha, run_id, attempt)
        c.Engine(self.p, self.github, self.provider, sha, run_id, attempt,
                 sleep=lambda _: None, polls=2).execute()

    def blocked(self, reason, **kwargs):
        with self.assertRaisesRegex(c.Blocked, reason):
            self.execute(**kwargs)

    def test_order_exact_sha_and_single_submission_across_attempts(self):
        self.execute()
        self.execute(attempt=2)
        for earlier, later in (("intent:schema", "submit:schema"),
                               ("submitted:schema", "receipt:schema"),
                               ("verified:schema", "intent:application"),
                               ("intent:application", "submit:application")):
            self.assertLess(self.events.index(earlier), self.events.index(later))
        self.assertEqual(self.events.count("submit:schema"), 1)
        self.assertEqual(self.events.count("submit:application"), 1)
        self.assertEqual({r["meta"]["commitHash"] for r in self.provider.rows}, {SHA})
        self.assertEqual(self.ledger.rows[0]["payload"]["run_attempt"], 1)

    def test_two_consumers_separate_targets_records_and_receipts(self):
        outcomes = []
        for name in ("bookshop", "observatory"):
            p, events = policy(name), []
            ledger = Ledger(p, events)
            github = c.GitHub(p, name + "-token")
            github.api = ledger.api
            provider = Provider(p, events)
            c.Engine(p, github, provider, SHA, 999, 1, sleep=lambda _: None).execute()
            self.assertEqual(events.count("submit:application"), 1)
            self.assertTrue(all(r["payload"]["repository"] == p["repository"] for r in ledger.rows))
            outcomes.append((ledger.rows, provider.rows))
        self.assertNotEqual(outcomes[0][0][0]["environment"], outcomes[1][0][0]["environment"])
        self.assertNotEqual(outcomes[0][1][0]["serviceId"], outcomes[1][1][0]["serviceId"])

    def test_schema_failure_zero_application_submits_and_no_retry(self):
        self.provider.status["schema"] = "CRASHED"
        self.blocked("schema-forward-recovery-required")
        self.blocked("schema-forward-recovery-required")
        self.assertNotIn("submit:application", self.events)
        self.assertEqual(self.events.count("submit:schema"), 1)

    def test_application_failure_preserves_schema_and_requires_forward_recovery(self):
        self.provider.status["application"] = "FAILED"
        self.blocked("application-forward-recovery-required")
        self.blocked("application-forward-recovery-required")
        self.assertEqual(self.github.status(self.ledger.rows[0]), ("verified", IDS["schema"]))
        self.assertEqual(self.events.count("submit:application"), 1)

    def test_lost_response_same_sha_listing_is_never_adopted(self):
        self.provider.lost.add("schema")
        self.blocked("provider-response-unknown")
        self.blocked("schema-submission-unattributed-no-resubmit")
        self.assertEqual(len(self.provider.rows), 1)
        self.assertNotIn("receipt:schema", self.events)
        self.assertNotIn("submit:application", self.events)
        self.assertEqual(self.events.count("submit:schema"), 1)

    def test_lost_response_without_listing_blocks_new_sha(self):
        self.provider.lost.add("schema")
        self.provider.absent.add("schema")
        self.blocked("provider-response-unknown")
        self.ledger.current = OTHER
        self.blocked("prior-release-unresolved", sha=OTHER)
        self.assertEqual(self.events.count("submit:schema"), 1)

    def test_durable_application_id_resumes_while_branch_advanced(self):
        self.provider.status["application"] = "BUILDING"
        self.blocked("application-observation-unresolved-no-resubmit")
        self.ledger.current = OTHER
        self.provider.rows[-1]["status"] = "SUCCESS"
        self.execute(attempt=2)
        self.assertEqual(self.events.count("submit:application"), 1)

    def test_returned_id_not_persisted_never_rediscovered(self):
        self.ledger.fail_status = "submitted"
        self.blocked("remote-response-unknown")
        self.ledger.fail_status = None
        self.blocked("schema-submission-unattributed-no-resubmit")
        self.assertEqual(self.events.count("submit:schema"), 1)

    def test_lost_intent_write_response_does_not_submit(self):
        self.ledger.fail_create = True
        self.blocked("remote-response-unknown")
        self.ledger.fail_create = False
        self.blocked("schema-submission-unattributed-no-resubmit")
        self.assertNotIn("submit:schema", self.events)

    def test_missing_or_false_receipt_never_submits_application(self):
        self.provider.receipt_valid = False
        self.blocked("schema-observation-unresolved-no-resubmit")
        self.assertNotIn("submit:application", self.events)

    def test_schema_removed_requires_receipt(self):
        self.provider.status["schema"] = "REMOVED"
        self.execute()
        self.assertEqual(self.events.count("submit:application"), 1)

    def test_stale_before_release_does_not_create_intent(self):
        self.ledger.current = OTHER
        self.blocked("stale-candidate")
        self.assertEqual(self.events, [])

    def test_branch_advances_after_schema_does_not_submit_application(self):
        self.provider.on_receipt = lambda: setattr(self.ledger, "current", OTHER)
        self.blocked("stale-candidate")
        self.assertNotIn("submit:application", self.events)

    def test_branch_advances_after_intent_records_no_submission(self):
        self.ledger.mutate_created = lambda _: setattr(self.ledger, "current", OTHER)
        self.blocked("stale-candidate")
        self.assertEqual(self.github.status(self.ledger.rows[0]), ("stale", None))
        self.assertNotIn("submit:schema", self.events)

    def test_concurrent_duplicate_intent_stops_before_provider_call(self):
        self.ledger.mutate_created = lambda row: self.ledger.add(row["payload"])
        self.blocked("broken-history-continuity|duplicate-release-intents")
        self.assertNotIn("submit:schema", self.events)

    def test_untracked_same_sha_cannot_be_adopted(self):
        self.provider.submit(self.p["schema"]["service_id"], SHA)
        self.blocked("untracked-same-sha-deployment")
        self.assertNotIn("intent:schema", self.events)

    def test_other_inflight_provider_deployment_blocks_submission(self):
        self.provider.submit(self.p["schema"]["service_id"], OTHER)
        self.provider.rows[0]["status"] = "BUILDING"
        self.blocked("provider-deployment-still-active")
        self.assertNotIn("intent:schema", self.events)

    def test_duplicate_provider_candidates_fail_closed(self):
        self.provider.on_submit = lambda row: self.provider.rows.append({**row, "id": EXTERNAL})
        self.blocked("ambiguous-provider-submission")
        self.assertNotIn("submit:application", self.events)

    def test_wrong_target_sha_or_returned_id_stops_application(self):
        for key, value in (("projectId", EXTERNAL), ("environmentId", EXTERNAL),
                           ("meta", {"commitHash": OTHER})):
            with self.subTest(key=key):
                self.setUp()
                self.provider.on_submit = lambda row: row.update({key: value})
                self.blocked("wrong-deployment-target|provider-deployment-binding-mismatch")
                self.assertNotIn("submit:application", self.events)

    def test_policy_change_at_existing_sha_is_rejected(self):
        self.execute()
        self.p["acl_policy"] = "changed-policy"
        self.blocked("release-policy-changed")
        self.assertEqual(self.events.count("submit:application"), 1)

    def test_autodeploy_drift_stops_before_any_intent(self):
        self.provider.preflight_error = "native-autodeploy-must-be-disabled"
        self.blocked("native-autodeploy-must-be-disabled")
        self.assertEqual(self.events, [])

    def test_status_write_response_loss_after_persistence_resumes(self):
        original = self.github.record
        def lose(item, state, deployment):
            original(item, state, deployment)
            if state == "submitted":
                raise c.Blocked("remote-response-unknown")
        self.github.record = lose
        self.blocked("remote-response-unknown")
        self.github.record = original
        self.execute()
        self.assertEqual(self.events.count("submit:schema"), 1)


class HistoryTests(unittest.TestCase):
    setUp = EngineTests.setUp
    execute = EngineTests.execute
    blocked = EngineTests.blocked

    def seed(self, count=250):
        heads = dict.fromkeys(c.PHASES)
        for number in range(1, count + 1):
            for phase in c.PHASES:
                payload = {"format_version": 1, "repository": self.p["repository"],
                           "consumer": self.p["consumer"], "phase": phase,
                           "source_sha": f"{number:040x}", "workflow": self.p["workflow"],
                           "run_id": number, "run_attempt": 1,
                           "project_id": self.p["project_id"], "environment_id": self.p["environment_id"],
                           "service_id": self.p[phase]["service_id"], "policy_sha256": "0" * 64,
                           "before": [], "previous_heads": heads.copy()}
                row = self.ledger.add(payload)
                self.github.record(row, "submitted", IDS[phase])
                self.github.record(row, "verified", IDS[phase])
                heads[phase] = row["id"]
        self.ledger.calls.clear()
        self.events.clear()

    def test_250_completed_releases_bounded_reads_preserve_records(self):
        self.seed()
        self.execute()
        self.assertEqual(len(self.ledger.rows), 502)
        self.assertLess(len(self.ledger.calls), 75)
        self.assertLess(self.ledger.run_reads, 8)
        self.assertEqual(self.events.count("submit:application"), 1)

    def test_terminal_checkpoint_does_not_need_old_actions_runs(self):
        self.seed()
        self.ledger.forbid_runs = True
        self.github.snapshot(SHA)
        self.assertEqual(self.ledger.run_reads, 0)

    def test_checkpoint_cannot_hide_unresolved_predecessor(self):
        self.seed(3)
        self.ledger.statuses[4] = self.ledger.statuses[4][:1]
        with self.assertRaisesRegex(c.Blocked, "prior-release-unresolved"):
            self.github.snapshot(SHA)

    def test_broken_predecessor_link_stops(self):
        self.seed(3)
        self.ledger.rows[-1]["payload"]["previous_heads"]["application"] = 2
        with self.assertRaisesRegex(c.Blocked, "broken-history-continuity"):
            self.github.snapshot(SHA)

    def test_application_checkpoint_must_bind_verified_same_sha_schema(self):
        self.seed(3)
        self.ledger.rows[-1]["payload"]["previous_heads"]["schema"] = 3
        with self.assertRaisesRegex(c.Blocked, "schema-predecessor-binding-mismatch"):
            self.github.snapshot(SHA)

    def test_application_record_without_schema_predecessor_is_invalid(self):
        self.seed(1)
        self.ledger.rows[-1]["payload"]["previous_heads"]["schema"] = None
        with self.assertRaisesRegex(c.Blocked, "schema-predecessor-not-verified"):
            self.github.snapshot(SHA)

    def test_unknown_record_fields_versions_and_creators_stop(self):
        self.seed(1)
        row = self.ledger.rows[-1]
        for field, value in (("format_version", 2), ("unknown", True), ("run_attempt", True),
                             ("environment_id", EXTERNAL)):
            altered = copy.deepcopy(row)
            altered["payload"][field] = value
            with self.subTest(field=field), self.assertRaises(c.Blocked):
                self.github.validate_record(altered)
        row["creator"]["login"] = "untrusted-bot"
        with self.assertRaisesRegex(c.Blocked, "untrusted-record-creator"):
            self.github.snapshot(SHA)

    def test_active_run_sha_branch_attempt_repository_and_workflow_binding(self):
        for key, value in (("head_sha", OTHER), ("head_branch", "other"), ("run_attempt", 2),
                           ("event", "workflow_dispatch"), ("path", ".github/workflows/other.yml"),
                           ("repository", {"full_name": "example-other/other"}),
                           ("head_repository", {"full_name": "example-other/other"})):
            run = self.ledger.run(SHA, 999, 1)
            run[key] = value
            self.ledger.runs[(999, 1)] = run
            with self.subTest(key=key), self.assertRaisesRegex(c.Blocked, "unbound-workflow-run"):
                self.github.validate_run(SHA, 999, 1)

    def test_active_actions_unavailable_fails_closed(self):
        self.provider.status["schema"] = "BUILDING"
        self.blocked("schema-observation-unresolved")
        self.ledger.forbid_runs = True
        with self.assertRaisesRegex(c.Blocked, "remote-response-unknown"):
            self.github.snapshot(SHA)

    def test_duplicate_historical_sha_records_are_rejected(self):
        self.seed(3)
        self.ledger.rows[0]["sha"] = self.ledger.rows[2]["sha"]
        self.ledger.rows[0]["payload"]["source_sha"] = self.ledger.rows[2]["sha"]
        with self.assertRaisesRegex(c.Blocked, "duplicate-release-intents"):
            self.github.snapshot(self.ledger.rows[2]["sha"])

    def test_status_unknown_format_contradiction_and_history_bounds(self):
        self.seed(1)
        item = self.ledger.rows[0]
        original = copy.deepcopy(self.ledger.statuses[1])
        variants = []
        for description in ("v2:verified:" + IDS["schema"], "v1:verified:" + EXTERNAL):
            variant = copy.deepcopy(original)
            variant[-1]["description"] = description
            variants.append(variant)
        variant = copy.deepcopy(original)
        variant[-1]["creator"]["login"] = "other"
        variants.extend([variant, original[1:], original * 10])
        for variant in variants:
            self.ledger.statuses[1] = variant
            with self.assertRaises(c.Blocked):
                self.github.status(item)


class ContractTests(unittest.TestCase):
    def test_policy_unknown_keys_versions_wrong_types_and_isolation(self):
        original = policy()
        for key, value in (("unknown", "secret-sentinel"), ("format_version", 2),
                           ("format_version", True), ("project_id", "not-a-uuid")):
            altered = {**original, key: value}
            with self.subTest(key=key), self.assertRaises(c.Blocked):
                c.contract(altered, "policy")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "policy.json"
            original["application"]["service_id"] = original["schema"]["service_id"]
            path.write_text(json.dumps(original))
            with self.assertRaisesRegex(c.Blocked, "must-be-isolated"):
                c.load_policy(path)

    def test_duplicate_keys_and_non_json_constants_rejected(self):
        for value in ('{"a":1,"a":2}', '{"x":NaN}', '{"x":Infinity}', "broken"):
            with self.assertRaises(c.Blocked):
                c.decode(value)

    def test_config_files_are_not_supported_in_v1(self):
        for phase in c.PHASES:
            p = policy()
            p[phase]["config"] = "railway.toml"
            with self.subTest(phase=phase), self.assertRaises(c.Blocked):
                c.contract(p, "policy")

    def test_context_exact_checkout_event_and_attempt(self):
        p = policy()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "event.json"
            path.write_text(json.dumps({"after": SHA, "deleted": False, "ref": "refs/heads/main",
                                       "repository": {"full_name": p["repository"]}}))
            env = {"GITHUB_EVENT_NAME": "push", "GITHUB_REPOSITORY": p["repository"],
                   "GITHUB_REF": "refs/heads/main", "GITHUB_WORKFLOW_REF": p["repository"] + "/"
                   + p["workflow"] + "@refs/heads/main", "GITHUB_SHA": SHA, "GITHUB_RUN_ID": "999",
                   "GITHUB_RUN_ATTEMPT": "1", "GITHUB_EVENT_PATH": str(path), "GITHUB_WORKSPACE": directory}
            with patch.object(c.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout=SHA)):
                c.context(p, env)
                for key, value in (("GITHUB_RUN_ATTEMPT", "0"), ("GITHUB_SHA", OTHER),
                                   ("GITHUB_EVENT_NAME", "pull_request"), ("GITHUB_REF", "refs/heads/other")):
                    with self.subTest(key=key), self.assertRaises(c.Blocked):
                        c.context(p, {**env, key: value})
            with patch.object(c.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout=OTHER)):
                with self.assertRaisesRegex(c.Blocked, "checkout-must-match"):
                    c.context(p, env)

    def test_sanitized_main_does_not_print_exception_details(self):
        output = io.StringIO()
        with patch.object(sys, "argv", ["controller.py", "--policy", "x"]), \
                patch.dict(c.os.environ, {}, clear=True), contextlib.redirect_stdout(output):
            self.assertEqual(c.main(), 1)
        self.assertNotIn("Traceback", output.getvalue())
        self.assertIn("Details suppressed", output.getvalue())


class CommittedPolicyTests(unittest.TestCase):
    """Real local Git objects in isolated temporary repos; never shared refs."""
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.relative = ".github/release.json"
        self.path = self.directory / self.relative
        self.path.parent.mkdir()
        self.content = (c.ROOT / "tests/fixtures/bookshop.json").read_bytes()
        self.path.write_bytes(self.content)
        self.git("init", "--quiet")
        self.sha = self.record_tree()

    def git(self, *args, input=None):
        result = c.subprocess.run(["git", "-C", str(self.directory), *args], input=input,
                                  capture_output=True, check=True)
        return result.stdout

    def record_tree(self):
        self.git("add", "--all")
        tree = self.git("write-tree").strip().decode()
        # Unreferenced fixture commit objects; no branch, checkout or shared
        # repository is committed or moved by this test helper.
        return self.git("-c", "user.name=Fictional Fixture", "-c",
                        "user.email=fixtures@example.invalid", "commit-tree", tree,
                        input=b"Fictional offline policy fixture\n").strip().decode()

    def read(self, relative=None):
        return c.committed_policy(self.directory, relative or self.relative, self.sha)

    def test_regular_committed_policy_is_accepted(self):
        self.assertEqual(self.read(), policy())

    def test_git_replace_cannot_substitute_different_policy_for_event_commit(self):
        original_sha = self.sha
        altered = policy()
        altered["project_id"] = EXTERNAL
        self.path.write_text(json.dumps(altered))
        replacement_sha = self.record_tree()
        self.git("replace", original_sha, replacement_sha)
        self.sha = original_sha
        with self.assertRaisesRegex(c.Blocked, "policy-index-must-match-commit"):
            self.read()

    def test_modified_working_policy_is_rejected(self):
        altered = policy()
        altered["project_id"] = EXTERNAL
        self.path.write_text(json.dumps(altered))
        with self.assertRaisesRegex(c.Blocked, "policy-checkout-must-match-commit"):
            self.read()

    def test_staged_policy_is_rejected_even_if_worktree_restored(self):
        self.path.write_bytes(self.content + b"\n")
        self.git("add", self.relative)
        self.path.write_bytes(self.content)
        with self.assertRaisesRegex(c.Blocked, "policy-index-must-match-commit"):
            self.read()

    def test_untracked_policy_is_rejected(self):
        (self.directory / "untracked.json").write_bytes(self.content)
        with self.assertRaisesRegex(c.Blocked, "policy-must-be-committed-regular-blob"):
            self.read("untracked.json")

    def test_absolute_traversal_and_non_normalized_paths_are_rejected(self):
        for relative in (str(self.path), "../release.json", "./.github/release.json",
                         ".github//release.json", ".github/../.github/release.json", "."):
            with self.subTest(relative=relative), self.assertRaisesRegex(
                    c.Blocked, "policy-path-must-be-normalized-relative"):
                self.read(relative)

    def test_symlink_file_is_rejected_even_when_it_has_identical_bytes(self):
        target = self.directory / "target.json"
        target.write_bytes(self.content)
        self.path.unlink()
        self.path.symlink_to(target)
        with self.assertRaisesRegex(c.Blocked, "policy-path-missing-or-symlink"):
            self.read()

    def test_symlink_parent_is_rejected_even_when_file_has_identical_bytes(self):
        target = self.directory / "target-directory"
        self.path.parent.rename(target)
        self.path.parent.symlink_to(target, target_is_directory=True)
        with self.assertRaisesRegex(c.Blocked, "policy-path-missing-or-symlink"):
            self.read()

    def test_committed_symlink_is_rejected(self):
        target = self.directory / "target.json"
        target.write_bytes(self.content)
        self.path.unlink()
        self.path.symlink_to("../target.json")
        self.sha = self.record_tree()
        with self.assertRaisesRegex(c.Blocked, "policy-must-be-committed-regular-blob"):
            self.read()

    def test_committed_directory_is_rejected(self):
        with self.assertRaisesRegex(c.Blocked, "policy-must-be-committed-regular-blob"):
            self.read(".github")

    def test_size_bound_and_strict_json_are_preserved(self):
        for content, reason in ((b" " * 16385, "policy-size-limit"),
                                (b'{"format_version":1,"format_version":2}', "duplicate-json-key")):
            self.path.write_bytes(content)
            self.sha = self.record_tree()
            with self.subTest(reason=reason), self.assertRaisesRegex(c.Blocked, reason):
                self.read()

    def test_parse_uses_verified_blob_if_working_file_changes_after_comparison(self):
        original = c.policy_bytes
        # Load expected before patching the parser used by the fixture helper.
        expected = policy()
        def parse_after_change(content):
            self.path.write_text('{"unreviewed":true}')
            self.assertEqual(content, self.content)
            return original(content)
        with patch.object(c, "policy_bytes", side_effect=parse_after_change):
            self.assertEqual(self.read(), expected)

    def test_documented_download_probe_stops_before_any_network_request(self):
        output = io.StringIO()
        env = {"GITHUB_WORKSPACE": str(self.directory), "GITHUB_SHA": self.sha,
               "GITHUB_TOKEN": "download-probe-no-token", "RAILWAY_TOKEN": "download-probe-no-token"}
        with patch.object(sys, "argv", ["controller.py", "--policy",
                                      ".github/action-download-probe-does-not-exist.json"]), \
                patch.dict(c.os.environ, env, clear=True), patch.object(c, "request") as request, \
                contextlib.redirect_stdout(output):
            self.assertEqual(c.main(), 1)
        request.assert_not_called()
        self.assertIn("django-release blocked: policy-must-be-committed-regular-blob", output.getvalue())

    def test_root_and_nested_default_railway_configs_refuse_before_network(self):
        for relative in ("railway.toml", "railway.json", "services/schema/railway.toml",
                         "nested/application/railway.json"):
            path = self.directory / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("fictional config override\n")
            self.sha = self.record_tree()
            output = io.StringIO()
            env = {"GITHUB_WORKSPACE": str(self.directory), "GITHUB_SHA": self.sha}
            with self.subTest(relative=relative), \
                    patch.object(sys, "argv", ["controller.py", "--policy", self.relative]), \
                    patch.dict(c.os.environ, env, clear=True), patch.object(c, "request") as request, \
                    contextlib.redirect_stdout(output):
                self.assertEqual(c.main(), 1)
            request.assert_not_called()
            self.assertIn("django-release blocked: committed-railway-config-not-supported", output.getvalue())
            self.assertNotIn(relative, output.getvalue())
            path.unlink()
            self.sha = self.record_tree()

    def test_similar_config_names_are_allowed(self):
        for relative in ("railway.toml.example", "railway.json.bak", ".railway.toml",
                         "railway.TOML", "nested/myrailway.json", "railway-config.json"):
            path = self.directory / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("fictional example\n")
        self.sha = self.record_tree()
        c.verify_dashboard_only_tree(self.directory, self.sha)

    def test_tree_scan_uses_candidate_sha_not_index_or_working_files(self):
        clean_sha = self.sha
        path = self.directory / "railway.toml"
        path.write_text("fictional override\n")
        self.sha = self.record_tree()
        c.verify_dashboard_only_tree(self.directory, clean_sha)
        path.unlink()
        self.git("add", "--all")
        with self.assertRaisesRegex(c.Blocked, "committed-railway-config-not-supported"):
            c.verify_dashboard_only_tree(self.directory, self.sha)
        self.sha = self.record_tree()
        c.verify_dashboard_only_tree(self.directory, self.sha)

    def test_tree_scan_ignores_git_replacement_objects(self):
        clean_sha = self.sha
        (self.directory / "railway.json").write_text("fictional override\n")
        with_config_sha = self.record_tree()
        self.git("replace", with_config_sha, clean_sha)
        with self.assertRaisesRegex(c.Blocked, "committed-railway-config-not-supported"):
            c.verify_dashboard_only_tree(self.directory, with_config_sha)

    def test_tree_path_byte_and_time_bounds_stop_cleanly(self):
        for constant, limit, reason in (("MAX_TREE_PATHS", 1, "candidate-tree-path-limit"),
                                        ("MAX_TREE_BYTES", 8, "candidate-tree-size-limit"),
                                        ("TREE_READ_SECONDS", 0, "candidate-tree-time-limit")):
            with self.subTest(constant=constant), patch.object(c, constant, limit), \
                    self.assertRaisesRegex(c.Blocked, reason):
                c.verify_dashboard_only_tree(self.directory, self.sha)

    def test_unavailable_candidate_tree_stops_with_sanitized_reason(self):
        with self.assertRaisesRegex(c.Blocked, "candidate-tree-unavailable"):
            c.verify_dashboard_only_tree(self.directory, "f" * 40)


class TestRunnerTests(unittest.TestCase):
    def test_empty_discovery_is_a_failure(self):
        spec = importlib.util.spec_from_file_location("release_tests", c.ROOT / "scripts/run_tests.py")
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
        output = io.StringIO()
        with patch.object(runner.unittest.defaultTestLoader, "discover", return_value=unittest.TestSuite()), \
                contextlib.redirect_stderr(output):
            self.assertEqual(runner.main(), 1)
        self.assertIn("No tests discovered", output.getvalue())


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.p = policy()
        self.provider = c.Railway(self.p, "secret-sentinel")

    def expected(self):
        return {"format_version": 1, "repository": self.p["repository"], "consumer": self.p["consumer"],
                "source_sha": SHA, "project_id": self.p["project_id"], "environment_id": self.p["environment_id"],
                "service_id": self.p["schema"]["service_id"], "deployment_id": IDS["schema"],
                "migrations_verified": True, "acl_verified": True, "acl_policy": self.p["acl_policy"]}

    def test_receipt_exact_version_full_acl_and_target(self):
        expected = self.expected()
        with patch.object(self.provider, "query", return_value={"deploymentLogs": [
                {"message": c.RECEIPT_PREFIX + json.dumps(expected)}]}):
            self.assertTrue(self.provider.receipt(IDS["schema"], expected))
        for key, value in (("format_version", 2), ("acl_verified", False), ("migrations_verified", False),
                           ("source_sha", OTHER), ("service_id", EXTERNAL), ("deployment_id", EXTERNAL),
                           ("extra", "secret-sentinel"), ("consumer", "observatory")):
            altered = {**expected, key: value}
            with self.subTest(key=key), patch.object(self.provider, "query", return_value={"deploymentLogs": [
                    {"message": c.RECEIPT_PREFIX + json.dumps(altered)}]}), self.assertRaises(c.Blocked):
                self.provider.receipt(IDS["schema"], expected)

    def test_receipt_duplicate_missing_malformed_and_window_bounds(self):
        expected = self.expected()
        good = {"message": c.RECEIPT_PREFIX + json.dumps(expected)}
        for rows in ([good, good], [{"message": c.RECEIPT_PREFIX + "bad"}],
                     [{"message": "ordinary log"}] * 499 + [good]):
            with patch.object(self.provider, "query", return_value={"deploymentLogs": rows}), \
                    self.assertRaises(c.Blocked):
                self.provider.receipt(IDS["schema"], expected)
        with patch.object(self.provider, "query", return_value={"deploymentLogs": []}):
            self.assertFalse(self.provider.receipt(IDS["schema"], expected))

    def test_only_mutation_has_configured_target_and_exact_sha(self):
        with patch.object(self.provider, "query", return_value={"serviceInstanceDeployV2": IDS["application"]}) as call:
            self.assertEqual(self.provider.submit(self.p["application"]["service_id"], SHA), IDS["application"])
        self.assertEqual(call.call_args.args[1], {"serviceId": self.p["application"]["service_id"],
                                                "environmentId": self.p["environment_id"], "commitSha": SHA})
        self.assertIn("serviceInstanceDeployV2", call.call_args.args[0])

    def test_graphql_and_http_errors_do_not_expose_diagnostics(self):
        with patch.object(c, "request", return_value={"errors": [{"message": "secret-sentinel"}]}):
            with self.assertRaisesRegex(c.Blocked, "^provider-response-unknown$"):
                self.provider.submit(self.p["schema"]["service_id"], SHA)
        with patch.object(c, "build_opener", side_effect=ValueError("secret-sentinel")):
            with self.assertRaisesRegex(c.Blocked, "^remote-response-unknown$"):
                c.request("https://example.invalid", "secret-sentinel", data={})

    def test_http_redirects_are_not_followed_with_tokens(self):
        with self.assertRaisesRegex(c.Blocked, "remote-redirect-refused"):
            c.NoRedirect().redirect_request(None, None, None, None, None, None)

    def page(self, more=False, cursor=None, edges=None):
        return {"deployments": {"edges": edges or [],
                                "pageInfo": {"hasNextPage": more, "endCursor": cursor}}}

    def test_complete_pagination_and_repeated_cursor_fail_closed(self):
        with patch.object(self.provider, "query", side_effect=[self.page(True, "one"), self.page()]) as call:
            self.assertEqual(self.provider.deployments(self.p["schema"]["service_id"]), [])
            self.assertEqual(call.call_args.args[1]["after"], "one")
        with patch.object(self.provider, "query", return_value=self.page(True, "one")):
            with self.assertRaisesRegex(c.Blocked, "broken-provider-pagination"):
                self.provider.deployments(self.p["schema"]["service_id"])

    def test_history_limit_and_duplicate_ids(self):
        with patch.object(self.provider, "query", side_effect=[self.page(True, str(i)) for i in range(10)]):
            with self.assertRaisesRegex(c.Blocked, "provider-history-limit"):
                self.provider.deployments(self.p["schema"]["service_id"])
        with patch.object(self.provider, "query", return_value=self.page(edges=[
                {"node": {"id": EXTERNAL}}, {"node": {"id": EXTERNAL}}])):
            with self.assertRaisesRegex(c.Blocked, "duplicate-provider-deployment"):
                self.provider.deployments(self.p["schema"]["service_id"])

    def preflight(self, phase):
        service = self.p[phase]
        return {"service": {"id": service["service_id"], "name": service["name"], "projectId": self.p["project_id"]},
                "tcpProxies": [], "serviceInstanceAutoDeployStatus": {"enabled": False},
                "serviceInstance": {"serviceId": service["service_id"], "environmentId": self.p["environment_id"],
                    "source": {"repo": self.p["repository"], "image": None}, "railwayConfigFile": service["config"],
                    "rootDirectory": "/", "preDeployCommand": None, "startCommand": service["start_command"],
                    "healthcheckPath": service["healthcheck_path"], "numReplicas": 1,
                    "restartPolicyType": service["restart_policy"],
                    "domains": {"serviceDomains": [], "customDomains": []}}}

    def test_preflight_rejects_autodeploy_process_source_domain_and_target_drift(self):
        good = self.preflight("schema")
        with patch.object(self.provider, "query", return_value=good):
            self.provider.preflight("schema")
        mutations = [lambda r: r["serviceInstanceAutoDeployStatus"].update(enabled=True),
                     lambda r: r["service"].update(projectId=EXTERNAL),
                     lambda r: r["serviceInstance"].update(startCommand="unexpected"),
                     lambda r: r["serviceInstance"].update(preDeployCommand=["unexpected"]),
                     lambda r: r["serviceInstance"]["source"].update(repo="example-other/other"),
                     lambda r: r["serviceInstance"]["domains"]["customDomains"].append({"id": "domain"})]
        for mutate in mutations:
            bad = copy.deepcopy(good)
            mutate(bad)
            with patch.object(self.provider, "query", return_value=bad), self.assertRaises(c.Blocked):
                self.provider.preflight("schema")

    def test_application_may_have_public_http_without_schema_public_access(self):
        result = self.preflight("application")
        result["serviceInstance"]["domains"]["serviceDomains"].append({"id": "domain"})
        with patch.object(self.provider, "query", return_value=result):
            self.provider.preflight("application")

    def test_null_and_literal_empty_provider_config_bindings_are_absent(self):
        for phase in c.PHASES:
            for binding in (None, ""):
                result = self.preflight(phase)
                result["serviceInstance"]["railwayConfigFile"] = binding
                with self.subTest(phase=phase, binding=binding), \
                        patch.object(self.provider, "query", return_value=result):
                    self.provider.preflight(phase)

    def test_matching_dashboard_settings_with_config_override_or_wrong_type_are_rejected(self):
        for phase in c.PHASES:
            for binding in ("railway.toml", ".railway/service.json", " ", "\t", "\n",
                            False, True, 0, 1, [], {}, [""], {"path": ""}):
                result = self.preflight(phase)
                result["serviceInstance"]["railwayConfigFile"] = binding
                with self.subTest(phase=phase, binding=binding), \
                        patch.object(self.provider, "query", return_value=result), \
                        self.assertRaisesRegex(c.Blocked, "provider-service-config-drift"):
                    self.provider.preflight(phase)

    def test_absent_provider_config_does_not_relax_null_consumer_policy(self):
        for phase in c.PHASES:
            for binding in (None, ""):
                result = self.preflight(phase)
                result["serviceInstance"]["railwayConfigFile"] = binding
                with self.subTest(phase=phase, binding=binding), \
                        patch.dict(self.p[phase], {"config": ""}), \
                        patch.object(self.provider, "query", return_value=result), \
                        self.assertRaisesRegex(c.Blocked, "provider-service-config-drift"):
                    self.provider.preflight(phase)


if __name__ == "__main__":
    unittest.main()
