"""Local-only trial tests: temporary directory, mock clock/key/API, no user files."""
from contextlib import redirect_stdout
from copy import deepcopy
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import awo_advice as advice
import awo_jev_trial as trial
import awo_request as request
from test_advice import replay

NOW = datetime(2026, 9, 26, 0, 0, tzinfo=timezone.utc)
START = '2026-09-25T09:00:00Z'
END = '2026-10-02T09:00:00Z'


class JevTrialTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.directory = Path(temp.name) / 'jev-trial'
        self.directory.mkdir()
        self.file = self.directory / 'events.jsonl'
        self.config = self.directory / 'config.json'
        self.args = SimpleNamespace(advise='jev', advice_cohort='production', apply=False,
            project=None, worktree=None, new_goal=False, goal='Private goal title', text='Private request text')
        self.base = {'action': 'needs_project', 'candidates': [], 'registered_projects': ['private-project']}
        self.projects = {'private-project': {'path': '/private/local/path'}}
        self.snapshot = ({'project:private-project': {'key': 'private-project',
                          'aliases': 'Private aliases', 'description': 'Private candidate description'}}, {}, {})
        self.enable()
        for patcher in (patch.object(trial, 'trial_directory', return_value=self.directory),
                        patch.object(trial, 'utcnow', return_value=NOW),
                        patch.object(advice, 'catalog', return_value=self.snapshot),
                        patch.object(advice, 'load_key', return_value='fixture-api-key')):
            patcher.start()
            self.addCleanup(patcher.stop)

    def enable(self, start=START, end=END):
        self.config.write_text(json.dumps({'starts_at': start, 'ends_at': end}))

    def advise(self, failure=None):
        original = deepcopy(self.base)
        def success(payload, key):
            return replay(payload, {'project': 'project:private-project', 'request_type': 'implementation'})
        with patch.object(advice, 'call_jev', side_effect=failure or success) as api, \
                patch.object(advice.time, 'perf_counter', side_effect=[100.0, 100.25]) as clock:
            result = advice.advise(self.args, self.projects, self.base)
        self.assertEqual(self.base, original)
        return result, api, clock

    def rows(self):
        return [json.loads(line) for line in self.file.read_text().splitlines()]

    def test_default_and_no_config_preserve_existing_behavior(self):
        self.args.advise = 'none'
        with patch.object(trial, 'trial_state') as state:
            result, api, _ = self.advise()
        state.assert_not_called()
        api.assert_not_called()
        self.assertNotIn('trial', result)
        self.assertFalse(self.file.exists())
        self.args.advise = 'jev'
        self.config.unlink()
        result, api, _ = self.advise()
        api.assert_called_once()
        self.assertEqual(result['status'], 'suggested')
        self.assertNotIn('trial', result)
        self.assertFalse(self.file.exists())

    def test_allowlisted_event_and_api_only_latency(self):
        result, api, clock = self.advise()
        event = self.rows()[0]
        self.assertEqual(set(event), {'type', 'event_id', 'timestamp', 'cohort', 'status', 'reason',
            'model', 'api_called', 'api_latency_ms', 'input_tokens', 'selection_ids'})
        self.assertEqual(str(uuid.UUID(event['event_id'])), result['trial']['event_id'])
        self.assertEqual(event['api_latency_ms'], 250)
        self.assertTrue(event['api_called'])
        self.assertEqual(event['input_tokens'], 42)
        self.assertEqual(event['selection_ids'], result['trial']['selection_ids'])
        self.assertEqual(clock.call_count, 2)  # Only wraps the provider, not catalog inspection.
        self.assertEqual(api.call_count, 1)
        raw = self.file.read_text()
        for forbidden in ('Private request', 'Private goal', '/private/local/path', 'fixture-api-key',
                          'private-project', 'Private aliases', 'Private candidate', 'implementation'):
            self.assertNotIn(forbidden, raw)
        self.assertEqual(self.file.stat().st_mode & 0o777, 0o600)

    def test_skipped_api_and_failure_are_distinct(self):
        self.args.apply = True
        result, api, clock = self.advise()
        api.assert_not_called(); clock.assert_not_called()
        self.assertEqual(result['reason'], 'apply_boundary')
        self.args.apply = False
        result, api, clock = self.advise(advice.AdviceError('timeout'))
        self.assertEqual(result['status'], 'unavailable')
        self.assertTrue(self.rows()[1]['api_called'])
        self.assertEqual(self.rows()[1]['api_latency_ms'], 250)
        data = trial.report()['cohorts']['production']
        self.assertEqual((data['events'], data['skipped_calls'], data['live_failures']), (2, 1, 1))
        self.assertEqual(data['reviewed'], 0)
        self.assertEqual(data['input_tokens']['unknown_calls'], 1)

    def test_period_boundaries_and_invalid_configuration_block_api(self):
        for now, reason in [(datetime(2026, 9, 25, 8, 59, tzinfo=timezone.utc), 'trial_not_started'),
                            (datetime(2026, 10, 2, 9, 0, tzinfo=timezone.utc), 'trial_expired')]:
            with self.subTest(reason=reason), patch.object(trial, 'utcnow', return_value=now):
                result, api, _ = self.advise()
                api.assert_not_called()
                self.assertEqual(result['reason'], reason)
                self.assertFalse(self.file.exists())
        with patch.object(trial, 'utcnow', return_value=trial.parse_time(START)):
            self.assertEqual(self.advise()[0]['trial']['status'], 'recorded')
        for body in ('not JSON private', '{}', '{"starts_at":"2026-09-25","ends_at":"2026-10-02"}'):
            self.config.write_text(body)
            result, api, _ = self.advise()
            api.assert_not_called()
            self.assertEqual(result['reason'], 'trial_config_invalid')
            self.assertNotIn('private', json.dumps(result))
        self.enable('2026-09-25T18:00:00+09:00', '2026-10-02T18:00:00+09:00')
        self.assertEqual(trial.trial_state()['starts_at'], START)

    def test_expiry_during_git_inspection_prevents_call(self):
        def inspect(*args):
            self.enable(end='2026-09-25T23:59:59Z')
            return self.snapshot
        with patch.object(advice, 'catalog', side_effect=inspect):
            result, api, _ = self.advise()
        api.assert_not_called()
        self.assertEqual(result['reason'], 'trial_window_changed')
        self.assertEqual(result['trial']['status'], 'not_recorded')
        self.assertFalse(self.file.exists())

    def test_record_failure_is_visible_and_cli_action_is_preserved(self):
        stream = io.StringIO()
        with patch.object(trial, 'append_row', side_effect=OSError('private disk detail')):
            result, _, _ = self.advise()
            self.assertEqual(result['status'], 'suggested')
            self.assertEqual(result['trial'], {'status': 'unavailable', 'reason': 'record_failed'})
            with patch.object(sys, 'argv', ['awo request', 'ambiguous text', '--advise', 'jev']), \
                    patch.object(request, 'registry', return_value={}), \
                    patch.object(advice, 'call_jev', side_effect=lambda p, k: replay(p)), redirect_stdout(stream):
                code = request.main()
        parsed = json.loads(stream.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(parsed['action'], 'needs_project')
        self.assertEqual(parsed['advisory']['trial']['reason'], 'record_failed')
        self.assertNotIn('private disk', stream.getvalue())

    def test_latest_feedback_counts_once_and_cohorts_never_mix(self):
        first = self.advise()[0]['trial']['event_id']
        second = self.advise()[0]['trial']['event_id']
        third = self.advise()[0]['trial']['event_id']
        before = self.file.read_bytes()
        trial.feedback(first, 'accepted', False)
        trial.feedback(first, 'corrected', True)
        trial.feedback(second, 'uncertain', False)
        self.assertTrue(self.file.read_bytes().startswith(before))
        self.args.advice_cohort = 'smoke'
        smoke = self.advise()[0]['trial']['event_id']
        trial.feedback(smoke, 'accepted', False)
        report = trial.report()['cohorts']
        production = report['production']
        self.assertEqual((production['live_calls'], production['reviewed'], production['unreviewed']), (3, 2, 1))
        self.assertEqual((production['accepted'], production['corrected'], production['uncertain'],
                          production['critical_misroutes']), (0, 1, 1, 1))
        self.assertEqual(report['smoke']['accepted'], 1)
        self.assertEqual(production['sufficiency'], 'unknown')
        self.assertEqual(len([r for r in self.rows() if r['event_id'] == first]), 3)
        # A later explicit correction also supersedes the critical flag.
        trial.feedback(first, 'accepted', False)
        self.assertEqual(trial.report()['cohorts']['production']['critical_misroutes'], 0)
        self.assertNotIn(third, json.dumps(report))

    def test_empty_report_and_percentiles_are_observations_not_accuracy(self):
        report = trial.report()['cohorts']['production']
        self.assertEqual(report['sufficiency'], 'unknown')
        self.assertEqual(report['evidence'], 'insufficient_data')
        self.assertIsNone(report['latency_ms']['p50'])
        self.assertNotIn('accuracy', report)
        result = advice.status('suggested', 'candidate_recommendation')
        for latency in (100, 200, 300, 400, 500):
            trial.record(result, {'api_called': True, 'api_latency_ms': latency, 'input_tokens': 2},
                         trial.trial_state(), 'production')
        report = trial.report()['cohorts']['production']
        self.assertEqual(report['latency_ms']['p50'], 300)
        self.assertEqual(report['latency_ms']['p95'], 500)
        self.assertEqual(report['unreviewed'], 5)
        self.assertEqual(report['quality'], 'unknown')
        self.assertEqual(report['input_tokens']['known_total'], 10)

    def test_feedback_validation_and_expired_trial_report(self):
        event_id = self.advise()[0]['trial']['event_id']
        self.enable(end='2026-09-26T00:00:01Z')
        with patch.object(trial, 'utcnow', return_value=datetime(2026, 10, 2, tzinfo=timezone.utc)):
            trial.feedback(event_id, 'accepted', False)  # Explicit feedback can arrive after expiry.
            self.assertEqual(trial.report()['cohorts']['production']['accepted'], 1)
        for value, reason in [('not-a-uuid', 'invalid_event_id'), (str(uuid.uuid4()), 'unknown_event_id')]:
            with self.assertRaisesRegex(trial.TrialError, reason):
                trial.feedback(value, 'accepted', False)
        self.args.apply = True
        skipped = self.advise()[0]['trial']['event_id']
        with self.assertRaisesRegex(trial.TrialError, 'event_not_reviewable'):
            trial.feedback(skipped, 'accepted', False)
        self.enable(start='2026-09-27T00:00:00Z')
        self.assertEqual(trial.report()['cohorts']['production']['events'], 0)

    def test_corruption_and_symlink_are_not_silently_ignored(self):
        self.advise()
        with self.file.open('a') as stream:
            stream.write('{partial')
        with self.assertRaisesRegex(trial.TrialError, 'journal_invalid'):
            trial.report()
        self.file.unlink()
        target = self.directory / 'preserved'
        target.write_text('do not change')
        self.file.symlink_to(target)
        result, _, _ = self.advise()
        self.assertEqual(result['trial']['reason'], 'record_failed')
        self.assertEqual(target.read_text(), 'do not change')

    def test_cli_commands_emit_json_and_feedback_requires_explicit_result(self):
        event_id = self.advise()[0]['trial']['event_id']
        for args in (['status', '--json'], ['report', '--json'],
                     ['feedback', event_id, '--result', 'corrected', '--critical-misroute', '--json']):
            stream = io.StringIO()
            with patch.object(sys, 'argv', ['awo jev-trial', *args]), redirect_stdout(stream):
                self.assertEqual(trial.main(), 0)
            self.assertIsInstance(json.loads(stream.getvalue()), dict)
        self.assertEqual(trial.report()['cohorts']['production']['critical_misroutes'], 1)


if __name__ == '__main__':
    unittest.main()
