"""Policy upgrade keeps both histories while surrendering application authority."""
import copy
import json
import unittest
from unittest.mock import Mock

import controller as c
import test_release as fixtures
from test_release import SHA, OTHER


class SchemaOnlyTests(unittest.TestCase):
    setUp = fixtures.EngineTests.setUp
    execute = fixtures.EngineTests.execute
    blocked = fixtures.EngineTests.blocked
    def upgrade(self):
        p = copy.deepcopy(self.p)
        p["format_version"] = 2
        p["mode"] = "schema-only"
        p["historical_application_service_id"] = p.pop("application")["service_id"]
        self.p = c.policy_bytes(json.dumps(p).encode())
        self.github.policy = self.p
        self.provider.preflight = Mock()
        original = self.provider.deployments
        self.provider.deployments = Mock(side_effect=original)
        self.events.clear()

    def assert_schema_only(self):
        self.assertNotIn("submit:application", self.events)
        self.assertTrue(all(call.args == ("schema",) for call in self.provider.preflight.call_args_list))
        self.assertTrue(all(call.args == (self.p["schema"]["service_id"],)
                            for call in self.provider.deployments.call_args_list))

    def test_schema_only_fresh_and_rerun(self):
        self.upgrade()
        self.execute()
        self.execute(attempt=2)
        self.assertEqual(self.events.count("submit:schema"), 1)
        self.assertEqual(len(self.ledger.rows), 1)
        self.assert_schema_only()

    def test_terminal_legacy_histories_keep_identities_and_heads(self):
        self.execute()
        before = copy.deepcopy(self.ledger.rows)
        self.upgrade()
        self.ledger.current = OTHER
        self.provider.rows.clear()  # Provider fixture uses one fixed ID per phase.
        self.execute(sha=OTHER)
        self.assertEqual(self.ledger.rows[:2], before)
        self.assertEqual(self.ledger.rows[-1]["payload"]["previous_heads"], {"schema": 1, "application": 2})
        self.assert_schema_only()

    def test_unresolved_legacy_schema_and_application_block_upgrade(self):
        for phase in ("schema", "application"):
            with self.subTest(phase=phase):
                self.setUp()
                self.provider.lost.add(phase)
                self.blocked("provider-response-unknown")
                self.upgrade()
                self.ledger.current = OTHER
                self.blocked("prior-release-unresolved", sha=OTHER)
                self.assertEqual(self.events, [])
                self.assert_schema_only()

    def test_same_sha_unresolved_application_cannot_be_abandoned(self):
        self.provider.status["application"] = "BUILDING"
        self.blocked("application-observation-unresolved")
        self.upgrade()
        self.blocked("prior-release-unresolved")
        self.assert_schema_only()

    def test_schema_only_lost_response_is_never_replayed(self):
        self.upgrade()
        self.provider.lost.add("schema")
        self.blocked("provider-response-unknown")
        self.blocked("schema-submission-unattributed-no-resubmit")
        self.assertEqual(self.events.count("submit:schema"), 1)
        self.assert_schema_only()

    def test_returned_schema_id_without_durable_status_is_not_rediscovered(self):
        self.upgrade()
        self.ledger.fail_status = "submitted"
        self.blocked("remote-response-unknown")
        self.ledger.fail_status = None
        self.blocked("schema-submission-unattributed-no-resubmit")
        self.assertEqual(self.events.count("submit:schema"), 1)
        self.assert_schema_only()

    def test_failed_schema_stays_terminal_without_application_calls(self):
        self.upgrade()
        self.provider.status["schema"] = "FAILED"
        self.blocked("schema-forward-recovery-required")
        self.blocked("schema-forward-recovery-required")
        self.assertEqual(self.events.count("submit:schema"), 1)
        self.assert_schema_only()

    def test_historical_application_identity_cannot_be_erased_or_changed(self):
        self.execute()
        self.upgrade()
        self.ledger.current = OTHER
        for identity in (None, self.p["schema"]["service_id"]):
            self.p["historical_application_service_id"] = identity
            self.blocked("wrong-record-target", sha=OTHER)
        self.assert_schema_only()

    def test_explicit_v2_fields_and_mode_are_required(self):
        self.upgrade()
        for key in ("mode", "historical_application_service_id"):
            p = {k: v for k, v in self.p.items() if k != key}
            with self.assertRaises(c.Blocked):
                c.policy_bytes(json.dumps(p).encode())
        for version in (True, 3):
            with self.assertRaises(c.Blocked):
                c.policy_bytes(json.dumps({**self.p, "format_version": version}).encode())


if __name__ == "__main__":
    unittest.main()
