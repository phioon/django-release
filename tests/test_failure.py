"""Exact failure attribution and bounded consumer result contracts."""
import json
import unittest
from unittest.mock import patch

import test_release as fixtures
import test_schema_only as schema_only
import controller as c
from test_release import OTHER, IDS, EXTERNAL


class FailureEngineTests(unittest.TestCase):
    setUp = fixtures.EngineTests.setUp
    execute = fixtures.EngineTests.execute
    blocked = fixtures.EngineTests.blocked
    upgrade = schema_only.SchemaOnlyTests.upgrade
    assert_schema_only = schema_only.SchemaOnlyTests.assert_schema_only

    def interference(self, row):
        self.provider.rows.append({**row, "id": EXTERNAL, "status": "SUCCESS"})

    def test_exact_provider_failure_wins_over_interference_for_both_policies(self):
        for version in (1, 2):
            for status in ("FAILED", "CRASHED", "SKIPPED"):
                with self.subTest(version=version, status=status):
                    self.setUp()
                    if version == 2:
                        self.upgrade()
                    self.provider.status["schema"] = status
                    self.provider.on_submit = self.interference
                    self.blocked("schema-forward-recovery-required")
                    self.blocked("schema-forward-recovery-required", attempt=2)
                    self.assertEqual(self.github.status(self.ledger.rows[0]), ("failed", IDS["schema"]))
                    self.assertEqual(self.events.count("submit:schema"), 1)
                    self.assertNotIn("submit:application", self.events)
                    if version == 2:
                        self.assert_schema_only()

    def test_application_exact_failure_with_interference_preserves_schema(self):
        self.provider.status["application"] = "FAILED"
        self.provider.on_submit = lambda row: self.interference(row) if row["id"] == IDS["application"] else None
        self.blocked("application-forward-recovery-required")
        self.assertEqual(self.github.status(self.ledger.rows[0]), ("verified", IDS["schema"]))
        self.assertEqual(self.github.status(self.ledger.rows[1]), ("failed", IDS["application"]))

    def test_exact_consumer_failure_records_failed_even_when_provider_reports_success(self):
        for version in (1, 2):
            for stage in ("migration", "consumer-verification"):
                with self.subTest(version=version, stage=stage):
                    self.setUp()
                    if version == 2:
                        self.upgrade()
                    client = c.Railway(self.p, "fixture-token")
                    def result(deployment, expected):
                        failure = {k: v for k, v in expected.items()
                                   if k not in ("migrations_verified", "acl_verified", "acl_policy")}
                        with patch.object(client, "query", return_value={"deploymentLogs": [
                                {"message": c.FAILURE_PREFIX + json.dumps({**failure, "stage": stage})}]}):
                            return client.receipt(deployment, expected)
                    self.provider.receipt = result
                    self.provider.on_submit = self.interference
                    self.blocked("schema-" + stage + "-failed-forward-recovery-required")
                    self.blocked("schema-forward-recovery-required", attempt=2)
                    self.assertEqual(self.github.status(self.ledger.rows[0]), ("failed", IDS["schema"]))
                    self.assertEqual(self.events.count("submit:schema"), 1)
                    self.assertNotIn("submit:application", self.events)
                    if version == 2:
                        self.assert_schema_only()

    def test_success_with_interference_stays_submitted_for_both_modes(self):
        for version in (1, 2):
            with self.subTest(version=version):
                self.setUp()
                if version == 2:
                    self.upgrade()
                self.provider.on_submit = self.interference
                self.blocked("ambiguous-provider-submission")
                self.blocked("ambiguous-provider-submission", attempt=2)
                self.assertEqual(self.github.status(self.ledger.rows[0]), ("submitted", IDS["schema"]))
                self.assertEqual(self.events.count("submit:schema"), 1)
                if version == 2:
                    self.assert_schema_only()

    def test_terminal_provider_failure_records_before_reading_stage_diagnostics(self):
        for stage in c.FAILURE_STAGES:
            for status in ("FAILED", "CRASHED", "SKIPPED"):
                with self.subTest(stage=stage, status=status):
                    self.setUp()
                    self.upgrade()
                    self.provider.status["schema"] = status
                    self.provider.on_submit = self.interference
                    client = c.Railway(self.p, "fixture-token")
                    def result(deployment, expected):
                        self.assertEqual(self.github.status(self.ledger.rows[0]), ("failed", IDS["schema"]))
                        failure = {k: v for k, v in expected.items()
                                   if k not in ("migrations_verified", "acl_verified", "acl_policy")}
                        with patch.object(client, "query", return_value={"deploymentLogs": [
                                {"message": c.FAILURE_PREFIX + json.dumps({**failure, "stage": stage})}]}):
                            return client.receipt(deployment, expected)
                    self.provider.receipt = result
                    self.blocked("^schema-" + stage + "-failed-forward-recovery-required$")
                    self.assert_schema_only()

    def test_bad_or_unavailable_failure_logs_never_undo_conclusive_provider_failure(self):
        for mode in ("unavailable", "malformed", "missing", "wrong-binding", "contradiction"):
            with self.subTest(mode=mode):
                self.setUp()
                self.upgrade()
                self.provider.status["schema"] = "FAILED"
                self.provider.on_submit = self.interference
                client = c.Railway(self.p, "fixture-token")
                def result(deployment, expected):
                    if mode == "unavailable":
                        raise c.Blocked("secret-sentinel")
                    failure = {k: v for k, v in expected.items()
                               if k not in ("migrations_verified", "acl_verified", "acl_policy")}
                    failure.update(stage="migration")
                    if mode == "wrong-binding":
                        failure["deployment_id"] = EXTERNAL
                    rows = [{"message": c.FAILURE_PREFIX + json.dumps(failure)}]
                    if mode == "malformed":
                        rows = [{"message": c.FAILURE_PREFIX + "secret-sentinel"}]
                    elif mode == "missing":
                        rows = []
                    elif mode == "contradiction":
                        rows.append({"message": c.RECEIPT_PREFIX + json.dumps(expected)})
                    with patch.object(client, "query", return_value={"deploymentLogs": rows}):
                        return client.receipt(deployment, expected)
                self.provider.receipt = result
                self.blocked("^schema-forward-recovery-required$")
                self.assertEqual(self.github.status(self.ledger.rows[0]), ("failed", IDS["schema"]))
                self.blocked("^schema-forward-recovery-required$", attempt=2)
                self.assertEqual(self.events.count("submit:schema"), 1)
                self.assert_schema_only()

    def test_invalid_failure_on_provider_success_leaves_exact_record_unresolved(self):
        self.upgrade()
        client = c.Railway(self.p, "fixture-token")
        def invalid_result(deployment, expected):
            with patch.object(client, "query", return_value={"deploymentLogs": [
                    {"message": c.FAILURE_PREFIX + "secret-sentinel"}]}):
                return client.receipt(deployment, expected)
        self.provider.receipt = invalid_result
        self.blocked("invalid-json")
        self.blocked("invalid-json", attempt=2)
        self.assertEqual(self.github.status(self.ledger.rows[0]), ("submitted", IDS["schema"]))
        self.assertEqual(self.events.count("submit:schema"), 1)
        self.assert_schema_only()

    def test_absent_or_inconclusive_exact_id_never_adopts_external_failure(self):
        for absent in (False, True):
            with self.subTest(absent=absent):
                self.setUp()
                self.upgrade()
                if absent:
                    self.provider.absent.add("schema")
                self.provider.status["schema"] = "BUILDING"
                self.provider.receipt_valid = False
                self.provider.on_submit = self.interference
                self.blocked("schema-observation-unresolved-no-resubmit")
                self.provider.rows[-1]["status"] = "FAILED"
                self.blocked("schema-observation-unresolved-no-resubmit", attempt=2)
                self.assertEqual(self.github.status(self.ledger.rows[0]), ("submitted", IDS["schema"]))
                self.ledger.current = OTHER
                self.blocked("prior-release-unresolved", sha=OTHER)
                self.assertEqual(self.events.count("submit:schema"), 1)
                self.assert_schema_only()

    def test_failed_exact_id_wrong_sha_cannot_resolve_record(self):
        self.provider.status["schema"] = "FAILED"
        self.provider.on_submit = lambda row: row.update(meta={"commitHash": OTHER})
        self.blocked("provider-deployment-binding-mismatch")
        self.assertEqual(self.github.status(self.ledger.rows[0]), ("submitted", IDS["schema"]))

    def test_terminal_failure_allows_only_new_reviewed_sha(self):
        self.upgrade()
        self.provider.status["schema"] = "FAILED"
        self.blocked("schema-forward-recovery-required")
        self.blocked("schema-forward-recovery-required", attempt=2)
        self.provider.rows.clear()  # Fixture reuses one ID; history remains intact.
        self.provider.status["schema"] = "SUCCESS"
        self.ledger.current = OTHER
        self.execute(sha=OTHER)
        self.assertEqual(self.events.count("submit:schema"), 2)
        self.assertEqual(self.ledger.rows[-1]["payload"]["previous_heads"]["schema"], 1)
        self.assert_schema_only()


class FailureContractTests(unittest.TestCase):
    setUp = fixtures.ProviderTests.setUp
    expected = fixtures.ProviderTests.expected

    def failure(self, stage="migration"):
        return {**{k: v for k, v in self.expected().items()
                   if k not in ("migrations_verified", "acl_verified", "acl_policy")}, "stage": stage}

    def result(self, messages):
        with patch.object(self.provider, "query", return_value={"deploymentLogs": [
                {"message": message} for message in messages]}):
            return self.provider.receipt(IDS["schema"], self.expected())

    def test_two_stages_are_failure_not_success(self):
        for stage in ("migration", "consumer-verification"):
            self.assertEqual(self.result([c.FAILURE_PREFIX + json.dumps(self.failure(stage))]), stage)

    def test_every_identity_field_is_bound_and_schema_is_strict(self):
        values = {"format_version": 2, "repository": "other/repo", "consumer": "other",
                  "source_sha": OTHER, "project_id": EXTERNAL, "environment_id": EXTERNAL,
                  "service_id": EXTERNAL, "deployment_id": EXTERNAL, "stage": "preflight",
                  "message": "secret-sentinel", "acl_policy": "not-a-certification"}
        for field, value in values.items():
            with self.subTest(field=field), self.assertRaises(c.Blocked) as error:
                self.result([c.FAILURE_PREFIX + json.dumps({**self.failure(), field: value})])
            self.assertNotIn("secret-sentinel", str(error.exception))
        for field in self.failure():
            with self.subTest(missing=field), self.assertRaises(c.Blocked):
                self.result([c.FAILURE_PREFIX + json.dumps({k: v for k, v in self.failure().items() if k != field})])

    def test_malformed_duplicate_contradictory_oversized_or_truncated_results_refuse(self):
        good = c.FAILURE_PREFIX + json.dumps(self.failure())
        success = c.RECEIPT_PREFIX + json.dumps(self.expected())
        for messages in ([good, good], [good, success], [success, good],
                         [good, c.FAILURE_PREFIX + json.dumps(self.failure("consumer-verification"))],
                         [c.FAILURE_PREFIX + "secret-sentinel"],
                         [c.FAILURE_PREFIX + '{"stage":"migration","stage":"migration"}'],
                         [c.FAILURE_PREFIX + " " * 4096], ["log"] * 499 + [good]):
            with self.subTest(count=len(messages)), self.assertRaises(c.Blocked) as error:
                self.result(messages)
            self.assertNotIn("secret-sentinel", str(error.exception))
        self.assertIsNone(self.result(["ordinary log secret-sentinel"]))
