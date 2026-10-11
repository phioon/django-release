"""Fresh migration attempts with real clients and isolated committed inputs."""

import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import controller as c
import test_release as fixtures
from test_release import SHA, OTHER, EXTERNAL


def policy():
    return fixtures.policy('bookshop-migrations')


def receipt(p, deployment, sha=SHA):
    return {'format_version': 2, 'repository': p['repository'], 'consumer': p['consumer'],
            'source_sha': sha, 'project_id': p['project_id'], 'environment_id': p['environment_id'],
            'service_id': p['schema']['service_id'], 'deployment_id': deployment,
            'migrations_verified': True}


class RailwayAPI:
    """Only the fixed schema target operations exist in this fictional API."""
    preflight = fixtures.ProviderTests.preflight

    def __init__(self, p):
        self.p = p
        self.rows, self.logs, self.submissions, self.observed, self.log_reads = {}, {}, [], [], []
        self.calls, self.status, self.lost = [], 'SUCCESS', False
        self.messages, self.alter_row, self.preflight_change = None, None, None
        self.active_reads, self.on_active = 0, None
        self.observe_error = None
        self.returned_id, self.missing_deployment = None, False

    def row(self, deployment, sha=SHA, status='SUCCESS'):
        return {'id': deployment, 'projectId': self.p['project_id'],
                'environmentId': self.p['environment_id'], 'serviceId': self.p['schema']['service_id'],
                'status': status, 'meta': {'commitHash': sha}}

    def request(self, url, token, *, data=None, railway=False):
        assert railway and url == 'https://backboard.railway.com/graphql/v2', 'GitHub access forbidden'
        query, variables = data['query'], data['variables']
        self.calls.append((query, copy.deepcopy(variables)))
        if 'serviceInstanceAutoDeployStatus' in query:
            assert variables == {'projectId': self.p['project_id'], 'environmentId': self.p['environment_id'],
                                 'serviceId': self.p['schema']['service_id']}
            result = self.preflight('schema')
            if self.preflight_change:
                self.preflight_change(result)
            return {'data': result}
        if 'deployments(' in query:
            assert 'first:1)' in query and 'after' not in variables, 'Lifetime history forbidden'
            target = variables['input']
            assert {k: v for k, v in target.items() if k != 'status'} == {
                'projectId': self.p['project_id'], 'environmentId': self.p['environment_id'],
                'serviceId': self.p['schema']['service_id']}
            self.active_reads += 1
            if self.on_active:
                self.on_active(self)
            rows = [r for r in reversed(list(self.rows.values()))
                    if r['status'] not in target['status']['notIn']]
            return {'data': {'deployments': {'edges': [{'node': copy.deepcopy(r)} for r in rows[:1]],
                                             'pageInfo': {'hasNextPage': len(rows) > 1}}}}
        if 'serviceInstanceDeployV2(' in query:
            assert variables['serviceId'] == self.p['schema']['service_id']
            assert variables['environmentId'] == self.p['environment_id']
            deployment = '55555555-5555-4555-8555-' + str(len(self.submissions) + 1).zfill(12)
            self.submissions.append((deployment, variables['commitSha']))
            row = self.row(deployment, variables['commitSha'], self.status)
            if self.alter_row:
                self.alter_row(row)
            self.rows[deployment] = row
            messages = [c.RECEIPT_PREFIX + json.dumps(receipt(self.p, deployment, variables['commitSha']))]
            self.logs[deployment] = self.messages(messages, deployment) if self.messages else messages
            if self.lost:
                raise c.Blocked('remote-response-unknown')
            return {'data': {'serviceInstanceDeployV2': self.returned_id or deployment}}
        if 'deployment(id:' in query:
            self.observed.append(variables['id'])
            if self.observe_error:
                raise self.observe_error
            return {'data': {'deployment': None if self.missing_deployment
                             else copy.deepcopy(self.rows[variables['id']])}}
        if 'deploymentLogs(' in query:
            assert 'limit:500' in query
            self.log_reads.append(variables['deploymentId'])
            return {'data': {'deploymentLogs': [{'message': m} for m in self.logs[variables['deploymentId']]]}}
        raise AssertionError('Unexpected provider operation')


class MigrationAttemptTests(unittest.TestCase):
    def setUp(self):
        self.p = policy()
        self.api = RailwayAPI(self.p)
        self.provider = c.Railway(self.p, 'fictional-token')
        self.sleeps = []

    def execute(self, sha=SHA):
        with patch.object(c, 'request', side_effect=self.api.request), \
                patch.object(c, 'GitHub', side_effect=AssertionError('GitHub client forbidden')):
            c.MigrationsEngine(self.p, self.provider, sha, polls=2, sleep=self.sleeps.append).execute()

    def test_every_same_sha_invocation_submits_new_id_after_retained_success(self):
        self.execute()
        self.execute()
        self.assertEqual([sha for _, sha in self.api.submissions], [SHA, SHA])
        self.assertEqual(len(set(self.api.observed)), 2)
        self.assertEqual(self.api.log_reads, self.api.observed)
        self.assertEqual(self.sleeps, [])
        self.assertEqual({row['status'] for row in self.api.rows.values()}, {'SUCCESS'})

    def test_retry_after_failure_unknown_or_timeout_is_fresh(self):
        for outcome in ('failed', 'lost-submit', 'lost-observation', 'missing-receipt'):
            with self.subTest(outcome=outcome):
                self.setUp()
                self.api.status = 'FAILED' if outcome == 'failed' else 'SUCCESS'
                self.api.lost = outcome == 'lost-submit'
                self.api.observe_error = c.Blocked('remote-response-unknown') if outcome == 'lost-observation' else None
                self.api.messages = (lambda *_: []) if outcome == 'missing-receipt' else None
                with self.assertRaises(c.Blocked):
                    self.execute()
                self.assertEqual(len(self.api.submissions), 1)
                self.api.status, self.api.lost, self.api.observe_error, self.api.messages = 'SUCCESS', False, None, None
                self.execute()
                self.assertEqual(len(self.api.submissions), 2)
                self.assertEqual(self.api.observed[-1], self.api.submissions[-1][0])

    def test_old_success_receipt_cannot_verify_current_attempt(self):
        self.execute()
        old_id = self.api.submissions[0][0]
        self.api.messages = lambda *_: self.api.logs[old_id]
        with self.assertRaisesRegex(c.Blocked, 'wrong-maintenance-receipt'):
            self.execute()
        self.assertEqual(len(self.api.submissions), 2)
        self.assertEqual(self.api.log_reads, [old_id, self.api.submissions[-1][0]])

    def test_exact_uuid_sha_and_target_are_required(self):
        for key, value in (('id', EXTERNAL), ('projectId', EXTERNAL), ('environmentId', EXTERNAL),
                           ('serviceId', EXTERNAL), ('meta', {'commitHash': OTHER}), ('meta', None)):
            with self.subTest(key=key):
                self.setUp()
                self.api.alter_row = lambda row: row.update({key: value})
                with self.assertRaises(c.Blocked):
                    self.execute()
                self.assertEqual(len(self.api.submissions), 1)
                self.assertEqual(self.api.log_reads, [])

    def test_failure_status_wins_over_success_looking_receipt(self):
        for status in ('FAILED', 'CRASHED', 'SKIPPED', 'CANCELLED', 'CANCELED', 'unknown'):
            with self.subTest(status=status):
                self.setUp()
                self.api.status = status
                with self.assertRaises(c.Blocked):
                    self.execute()
                self.assertEqual(self.api.log_reads, [])
                self.assertEqual(len(self.api.submissions), 1)

    def test_in_progress_receipt_does_not_finish_or_repeat_submission(self):
        self.api.status = 'DEPLOYING'
        with self.assertRaisesRegex(c.Blocked, 'migration-observation-timeout'):
            self.execute()
        self.assertEqual(len(self.api.submissions), 1)
        self.assertEqual(len(self.api.observed), 2)
        self.assertEqual(self.api.log_reads, [])

    def test_malformed_submission_id_and_absent_observation_fail_without_retry(self):
        for mode in ('malformed-id', 'absent-observation'):
            with self.subTest(mode=mode):
                self.setUp()
                self.api.returned_id = 'invalid-id' if mode == 'malformed-id' else None
                self.api.missing_deployment = mode == 'absent-observation'
                with self.assertRaises(c.Blocked):
                    self.execute()
                self.assertEqual(len(self.api.submissions), 1)
                self.assertEqual(self.api.log_reads, [])

    def test_removed_one_shot_needs_current_receipt(self):
        self.api.status = 'REMOVED'
        self.execute()
        self.api.messages = lambda *_: []
        with self.assertRaisesRegex(c.Blocked, 'migration-observation-timeout'):
            self.execute()

    def test_active_wait_can_finish_without_adopting_previous_attempt(self):
        self.api.rows[EXTERNAL] = self.api.row(EXTERNAL, status='BUILDING')
        def complete_previous(api):
            if api.active_reads == 2:
                api.rows[EXTERNAL]['status'] = 'SUCCESS'
        self.api.on_active = complete_previous
        self.execute()
        self.assertEqual(self.sleeps, [5])
        self.assertEqual(len(self.api.submissions), 1)
        self.assertNotIn(EXTERNAL, self.api.observed + self.api.log_reads)

    def test_active_timeout_prevents_submission_without_scanning_old_history(self):
        for index in range(1200):
            deployment = f'66666666-6666-4666-8666-{index:012d}'
            self.api.rows[deployment] = self.api.row(deployment, status='SUCCESS')
        self.api.rows[EXTERNAL] = self.api.row(EXTERNAL, status='BUILDING')
        with self.assertRaisesRegex(c.Blocked, 'maintenance-still-active'):
            self.execute()
        self.assertEqual(self.api.submissions, [])
        self.assertEqual(self.api.active_reads, 2)
        self.api.rows[EXTERNAL]['status'] = 'FAILED'
        self.execute()
        self.assertEqual(len(self.api.submissions), 1)

    def test_active_wrong_target_is_rejected(self):
        self.api.rows[EXTERNAL] = {**self.api.row(EXTERNAL, status='BUILDING'), 'serviceId': EXTERNAL}
        with self.assertRaisesRegex(c.Blocked, 'wrong-deployment-target'):
            self.execute()
        self.assertEqual(self.api.submissions, [])

    def test_cancellation_during_observation_never_resubmits(self):
        self.api.observe_error = KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            self.execute()
        self.assertEqual(len(self.api.submissions), 1)
        self.assertEqual(self.api.log_reads, [])

    def test_provider_config_refuses_before_mutation(self):
        for mutate in (lambda r: r['service'].update(projectId=EXTERNAL),
                       lambda r: r['serviceInstanceAutoDeployStatus'].update(enabled=True),
                       lambda r: r['serviceInstance']['source'].update(repo='other/repository')):
            with self.subTest(mutate=mutate):
                self.setUp()
                self.api.preflight_change = mutate
                with self.assertRaises(c.Blocked):
                    self.execute()
                self.assertEqual(self.api.submissions, [])

    def test_incomplete_or_malformed_activity_page_refuses(self):
        for page in ({'edges': [], 'pageInfo': {'hasNextPage': True}},
                     {'edges': [{'node': {}}, {'node': {}}], 'pageInfo': {'hasNextPage': False}},
                     {'edges': [], 'pageInfo': {'hasNextPage': 0}}):
            with self.subTest(page=page), patch.object(self.provider, 'query', return_value={'deployments': page}), \
                    self.assertRaisesRegex(c.Blocked, 'invalid-provider-page'):
                self.provider.active_deployment(self.p['schema']['service_id'])


class MigrationReceiptTests(unittest.TestCase):
    def setUp(self):
        self.p, self.deployment = policy(), EXTERNAL
        self.provider = c.Railway(self.p, 'fictional-token')
        self.expected = receipt(self.p, self.deployment)

    def read(self, messages):
        with patch.object(self.provider, 'query', return_value={'deploymentLogs': [
                {'message': message} for message in messages]}):
            return self.provider.migration_receipt(self.deployment, self.expected)

    def test_minimal_strict_receipt_binds_every_field(self):
        self.assertTrue(self.read([c.RECEIPT_PREFIX + json.dumps(self.expected)]))
        values = {'format_version': 1, 'repository': 'other/repo', 'consumer': 'other',
                  'source_sha': OTHER, 'project_id': fixtures.IDS['schema'],
                  'environment_id': fixtures.IDS['schema'], 'service_id': fixtures.IDS['schema'],
                  'deployment_id': fixtures.IDS['schema'], 'migrations_verified': False,
                  'acl_verified': True, 'acl_policy': 'old-policy', 'unexpected': 'sentinel'}
        for key, value in values.items():
            with self.subTest(key=key), self.assertRaises(c.Blocked):
                self.read([c.RECEIPT_PREFIX + json.dumps({**self.expected, key: value})])
        for key in self.expected:
            with self.subTest(missing=key), self.assertRaises(c.Blocked):
                self.read([c.RECEIPT_PREFIX + json.dumps({k: v for k, v in self.expected.items() if k != key})])

    def test_missing_malformed_duplicate_contradictory_or_truncated(self):
        good = c.RECEIPT_PREFIX + json.dumps(self.expected)
        self.assertFalse(self.read(['ordinary output']))
        for messages in ([good, good], [c.RECEIPT_PREFIX + 'not-json'],
                         [c.RECEIPT_PREFIX + '{"format_version":2,"format_version":2}'],
                         [good, c.FAILURE_PREFIX + '{}'], [c.FAILURE_PREFIX + 'not-json'],
                         [c.RECEIPT_PREFIX + ' ' * 4096], ['ordinary output'] * 499 + [good]):
            with self.subTest(messages=len(messages)), self.assertRaises(c.Blocked):
                self.read(messages)

    def test_v1_receipt_shape_and_legacy_engine_remain_separate(self):
        with self.assertRaises(c.Blocked):
            c.contract({**self.expected, 'format_version': 1}, 'receipt')
        with patch.object(self.provider, 'query', return_value={'deploymentLogs': [
                {'message': c.RECEIPT_PREFIX + json.dumps(self.expected)}]}), self.assertRaises(c.Blocked):
            legacy = {**self.expected, 'format_version': 1, 'acl_verified': True, 'acl_policy': 'bookshop-acl-v1'}
            self.provider.receipt(self.deployment, legacy)
        with self.assertRaisesRegex(c.Blocked, 'legacy-policy-required'):
            c.Engine(self.p, None, None, SHA, 1, 1).execute()


class MigrationEntryTests(unittest.TestCase):
    git = fixtures.CommittedPolicyTests.git
    record_tree = fixtures.CommittedPolicyTests.record_tree

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.p, self.relative = policy(), '.github/release.json'
        self.path = self.directory / self.relative
        self.path.parent.mkdir()
        self.path.write_text(json.dumps(self.p))
        self.git('init', '--quiet')
        self.sha = self.record_tree()
        self.git('update-ref', 'HEAD', self.sha)
        self.event_path = self.directory / 'event.json'
        self.event = {'after': self.sha, 'deleted': False, 'ref': 'refs/heads/main',
                      'repository': {'full_name': self.p['repository']}}
        self.event_path.write_text(json.dumps(self.event))
        self.env = {'GITHUB_EVENT_NAME': 'push', 'GITHUB_REPOSITORY': self.p['repository'],
                    'GITHUB_REF': 'refs/heads/main', 'GITHUB_SHA': self.sha,
                    'GITHUB_WORKFLOW_REF': self.p['repository'] + '/' + self.p['workflow'] + '@refs/heads/main',
                    'GITHUB_RUN_ID': '999', 'GITHUB_RUN_ATTEMPT': '1', 'GITHUB_EVENT_PATH': str(self.event_path),
                    'GITHUB_WORKSPACE': str(self.directory), 'RAILWAY_TOKEN': 'fictional-token'}
        self.api = RailwayAPI(self.p)

    def run_main(self):
        output = io.StringIO()
        with patch.dict(c.os.environ, self.env, clear=True), \
                patch.object(sys, 'argv', ['controller.py', '--policy', self.relative]), \
                patch.object(c, 'request', side_effect=self.api.request), \
                patch.object(c, 'GitHub', side_effect=AssertionError('No GitHub client for v3')), \
                contextlib.redirect_stdout(output):
            result = c.main()
        return result, output.getvalue()

    def test_main_dispatch_without_github_credentials_api_or_ledger(self):
        self.assertEqual(self.run_main()[0], 0)
        self.env['GITHUB_RUN_ATTEMPT'] = '2'
        self.assertEqual(self.run_main()[0], 0)
        self.assertEqual([sha for _, sha in self.api.submissions], [self.sha, self.sha])

    def test_trusted_event_and_workflow_refused_before_provider_requests(self):
        for key, value in (('GITHUB_EVENT_NAME', 'pull_request'), ('GITHUB_REPOSITORY', 'other/repo'),
                           ('GITHUB_WORKFLOW_REF', 'other/ref'), ('GITHUB_REF', 'refs/heads/other'),
                           ('GITHUB_RUN_ATTEMPT', '0')):
            original = self.env[key]
            self.env[key] = value
            with self.subTest(key=key):
                self.assertEqual(self.run_main()[0], 1)
                self.assertEqual(self.api.calls, [])
            self.env[key] = original
        self.event['deleted'] = True
        self.event_path.write_text(json.dumps(self.event))
        self.assertEqual(self.run_main()[0], 1)
        self.assertEqual(self.api.calls, [])

    def test_checkout_mismatch_refused_before_mutation(self):
        self.git('update-ref', 'HEAD', self.record_tree())
        result, output = self.run_main()
        self.assertEqual(result, 1)
        self.assertIn('checkout-must-match-event-sha', output)
        self.assertEqual(self.api.calls, [])

    def test_modified_staged_and_symlink_policy_refused_before_requests(self):
        original = self.path.read_text()
        self.path.write_text(original + '\n')
        self.assertEqual(self.run_main()[0], 1)
        self.git('add', self.relative)
        self.path.write_text(original)
        self.assertEqual(self.run_main()[0], 1)
        self.git('add', self.relative)
        target = self.directory / 'target.json'
        target.write_text(original)
        self.path.unlink()
        self.path.symlink_to(target)
        self.assertEqual(self.run_main()[0], 1)
        self.assertEqual(self.api.calls, [])

    def test_policy_v3_rejects_legacy_fields_wrong_mode_or_missing_identity(self):
        for key, value in (('mode', 'schema-only'), ('format_version', True),
                           ('acl_policy', 'legacy'), ('application', {}),
                           ('historical_application_service_id', None)):
            with self.subTest(key=key), self.assertRaises(c.Blocked):
                c.policy_bytes(json.dumps({**self.p, key: value}).encode())
        for key in self.p:
            with self.subTest(missing=key), self.assertRaises(c.Blocked):
                c.policy_bytes(json.dumps({k: v for k, v in self.p.items() if k != key}).encode())

    def test_unknown_submission_fails_main_without_retry(self):
        self.api.lost = True
        result, output = self.run_main()
        self.assertEqual(result, 1)
        self.assertIn('fresh migration attempt', output)
        self.assertEqual(len(self.api.submissions), 1)
        self.assertEqual(self.api.observed, [])


if __name__ == '__main__':
    unittest.main()
