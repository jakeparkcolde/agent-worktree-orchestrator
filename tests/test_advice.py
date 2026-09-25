"""Offline contract tests. All provider responses are synthetic, never live."""
from contextlib import redirect_stdout
from copy import deepcopy
import http.client
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch, MagicMock
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import awo_advice as advice
import awo_request as request
import test_request


def replay(payload, choices=None):
    """A schema fixture, not a model or measured Korean evaluation."""
    choices = choices or {}
    return {'model': advice.MODEL, 'usage': {'input_tokens': 42}, 'answers': {
        name: {'type': 'choice', 'choice': choices.get(name, 'none'), 'confidence': 0.9,
               'probabilities': {k: float(k == choices.get(name, 'none')) for k in q['criteria']}}
        for name, q in payload['questions'].items()}}


class AdviceTransportTests(unittest.TestCase):
    def setUp(self):
        self.payload = advice.build_payload('알림이 안 와요', '알림 수정',
            {'project:secretary': {'key': 'secretary', 'aliases': '비서', 'description': ''}}, {}, True, False)

    def test_closed_schema_rejects_malformed_and_nonfinite_responses(self):
        valid = replay(self.payload)
        invalid = [None, [], {}, {**valid, 'model': 'jev-latest'}, {**valid, 'answers': {}},
                   {**valid, 'usage': {}}, {**valid, 'usage': {'input_tokens': True}},
                   {**valid, 'usage': {'input_tokens': -1}}]
        for field, value in [('choice', 'project:invented'), ('choice', []), ('type', 'score'),
                             ('confidence', float('nan')), ('confidence', float('inf')),
                             ('confidence', True), ('confidence', 10 ** 500),
                             ('probabilities', {}), ('probabilities', {'none': 1})]:
            bad = deepcopy(valid)
            bad['answers']['project'][field] = value
            invalid.append(bad)
        for value in (float('nan'), float('inf'), -1, True, '1', 0.5):
            bad = deepcopy(valid)
            bad['answers']['project']['probabilities']['none'] = value
            invalid.append(bad)
        bad = deepcopy(valid)
        bad['answers']['project']['choice'] = 'ambiguous'
        invalid.append(bad)
        for bad in invalid:
            with self.subTest(bad=repr(bad)[:200]), self.assertRaises(advice.AdviceError):
                advice.validate_response(bad, self.payload)
        answers, usage = advice.validate_response(valid, self.payload)
        self.assertEqual(answers['project']['choice'], 'none')
        self.assertEqual(usage, {'input_tokens': 42})

    def test_request_and_catalog_limits_stop_before_transport(self):
        projects = {'project:' + str(i): {'key': str(i), 'description': '가' * 240,
                                        'aliases': '나' * 512} for i in range(64)}
        with self.assertRaisesRegex(advice.AdviceError, 'input_limit'):
            advice.build_payload('고쳐줘', '', projects, {}, True, False)
        with self.assertRaisesRegex(advice.AdviceError, 'candidate_limit'):
            advice.catalog({}, [str(i) for i in range(65)])
        with patch.object(advice.urllib.request, 'build_opener') as build:
            with self.assertRaisesRegex(advice.AdviceError, 'input_limit'):
                advice.call_jev({'state': 'x' * advice.MAX_REQUEST}, 'fixture-key')
            build.assert_not_called()

    def test_transport_is_fixed_bounded_and_does_not_retry(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = json.dumps(replay(self.payload)).encode()
        with patch.object(advice.urllib.request, 'build_opener') as build:
            build.return_value.open.return_value = response
            advice.call_jev(self.payload, 'test-key')
        args, kwargs = build.return_value.open.call_args
        self.assertEqual(args[0].full_url, advice.ENDPOINT)
        self.assertEqual(args[0].get_header('Authorization'), 'Bearer test-key')
        self.assertEqual(json.loads(args[0].data), self.payload)
        self.assertEqual(kwargs['timeout'], 5)
        response.read.assert_called_once_with(advice.MAX_RESPONSE + 1)
        build.return_value.open.assert_called_once()
        self.assertIsInstance(build.call_args.args[0], advice.NoRedirect)
        self.assertIsNone(advice.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://evil.invalid'))

    def test_transport_failures_are_codes_without_error_bodies(self):
        for error, reason in [
            (TimeoutError('secret'), 'timeout'),
            (urllib.error.URLError(TimeoutError('secret')), 'timeout'),
            (urllib.error.URLError('secret'), 'network_error'),
            (http.client.IncompleteRead(b'secret'), 'network_error'),
            (urllib.error.HTTPError(advice.ENDPOINT, 429, 'secret', {}, io.BytesIO(b'secret')), 'rate_limited'),
            (urllib.error.HTTPError(advice.ENDPOINT, 401, 'secret', {}, io.BytesIO(b'secret')), 'http_error'),
            (urllib.error.HTTPError(advice.ENDPOINT, 302, 'secret', {}, io.BytesIO(b'secret')), 'http_error'),
        ]:
            with self.subTest(reason=reason), patch.object(advice.urllib.request, 'build_opener') as build:
                build.return_value.open.side_effect = error
                with self.assertRaises(advice.AdviceError) as caught:
                    advice.call_jev(self.payload, 'test-key')
                self.assertEqual(str(caught.exception), reason)
                build.return_value.open.assert_called_once()
        for raw, reason in [(b'not JSON secret', 'malformed_response'),
                            (b'[' * 2000 + b']' * 2000, 'malformed_response'),
                            (b'x' * (advice.MAX_RESPONSE + 1), 'response_limit')]:
            with patch.object(advice.urllib.request, 'build_opener') as build:
                build.return_value.open.return_value.__enter__.return_value.read.return_value = raw
                with self.assertRaises(advice.AdviceError) as caught:
                    advice.call_jev(self.payload, 'test-key')
                self.assertEqual(str(caught.exception), reason)

    def test_sensitive_and_oversize_input_never_transmitted(self):
        for text in ['/Users/me/private', 'file /tmp/private', 'C:\\Users\\me',
                     'api_key=secret', 'Bearer secret', 'x' * 2049]:
            with self.subTest(text=text[:40]), self.assertRaises(advice.AdviceError):
                advice.build_payload(text, '', {}, {}, True, False)


class AdviceRoutingTests(unittest.TestCase):
    # Use the established real Git + isolated Orca fixture without inheriting
    # and rerunning its unrelated test methods.
    setUp = test_request.RequestTests.setUp
    run_cmd = test_request.RequestTests.run_cmd
    git = test_request.RequestTests.git
    request = test_request.RequestTests.request
    report = test_request.RequestTests.report

    def invoke(self, *args, text='AWO 어느 작업을 이어갈까', response=None, key='fixture-key'):
        stream = io.StringIO()
        env = {**self.env, 'TYPESAFE_API_KEY': key}
        if key is None:
            env.pop('TYPESAFE_API_KEY')
        with patch.dict(os.environ, env, clear=True), patch.object(sys, 'argv', ['awo request', text, *args]), \
                patch.object(advice, 'call_jev', side_effect=response or (lambda p, k: replay(p))) as call, redirect_stdout(stream):
            code = request.main()
        return json.loads(stream.getvalue()), call, code

    def existing(self, goal='알림 누락 수정'):
        return self.report('--goal', goal, '--apply')['path']

    def test_default_disabled_network_zero_and_no_mutation(self):
        with patch.object(advice, 'load_key') as key_loader:
            report, call, _ = self.invoke('--goal', '알림 수정')
        key_loader.assert_not_called()
        self.assertEqual(report['advisory']['status'], 'disabled')
        self.assertEqual(report['action'], 'needs_project')
        call.assert_not_called()
        self.assertFalse((self.repo / '.git/awo').exists())
        self.assertFalse(self.calls.exists())

    def test_rules_and_explicit_project_win_without_network(self):
        wt = self.existing()
        cases = [(['--goal', '알림 누락 수정'], 'AWO 카카오 비서'),
                 (['--project', 'secretary', '--goal', '알림 누락 수정'], '다른 프로젝트'),
                 (['--project', 'missing', '--goal', '수정'], 'AWO 카카오 비서'),
                 (['--goal', '다른 목표', '--worktree', wt], 'AWO 카카오 비서'),
                 ([], 'AWO 카카오 비서')]
        for args, text in cases:
            with self.subTest(args=args):
                baseline, _, _ = self.invoke(*args, text=text)
                result, call, _ = self.invoke(*args, '--advise', 'jev', text=text)
                call.assert_not_called()
                result.pop('advisory'); baseline.pop('advisory')
                self.assertEqual(result, baseline)

    def test_missing_key_is_normal_json_and_no_network(self):
        result, call, code = self.invoke('--advise', 'jev', key='')
        self.assertEqual(code, 0)
        self.assertEqual(result['advisory']['reason'], 'missing_key')
        self.assertEqual(result['advisory']['status'], 'unavailable')
        call.assert_not_called()

    def test_key_file_cli_success_and_failure_use_only_mock_home(self):
        file = self.root / '.config/awo/jev.env'
        file.parent.mkdir(parents=True)
        file.write_text('# 한국어 안내\n\nTYPESAFE_API_KEY=fixture-key\n')
        file.chmod(0o600)
        with patch.object(advice.Path, 'home', return_value=self.root):
            result, call, code = self.invoke('--advise', 'jev', key=None)
            self.assertEqual(code, 0)
            self.assertEqual(result['advisory']['status'], 'shadow_advisory')
            self.assertEqual(call.call_args.args[1], 'fixture-key')
            file.chmod(0o644)
            result, call, code = self.invoke('--advise', 'jev', key=None)
            self.assertEqual(code, 0)
            self.assertEqual(result['action'], 'needs_project')
            self.assertEqual(result['advisory']['reason'], 'key_file_permissions')
            call.assert_not_called()
            file.chmod(0o600)
            result, call, _ = self.invoke('--advise', 'jev', key=None, text='fixture-key 고쳐줘')
            self.assertEqual(result['advisory']['reason'], 'sensitive_input')
            call.assert_not_called()

    def test_advice_only_adds_supplement_and_exports_allowlisted_fields(self):
        wt = self.existing()
        (Path(wt) / 'code.txt').write_text('SECRET FILE CONTENT')
        (Path(wt) / 'untracked.txt').write_text('PRIVATE')
        with self.config.open('a') as f:
            f.write('    description: "메신저 알림 관리"\n')
        baseline, _, _ = self.invoke('--goal', '누락되는 메시지 고치기')
        def choose(payload, key):
            self.assertEqual(key, 'fixture-key')
            wire = json.dumps(payload, ensure_ascii=False)
            for forbidden in (str(self.repo), wt, 'code.txt', 'untracked.txt',
                              'SECRET FILE CONTENT', 'PRIVATE', 'fixture-key', 'refs/heads'):
                self.assertNotIn(forbidden, wire)
            self.assertEqual(set(payload['state']), {'request', 'goal', 'projects', 'existing_goals'})
            task_id = next(iter(payload['state']['existing_goals']))
            return replay(payload, {'project': 'project:secretary', 'existing_goal': task_id,
                                    'request_type': 'implementation'})
        result, call, _ = self.invoke('--goal', '누락되는 메시지 고치기', '--advise', 'jev', response=choose)
        supplement = result.pop('advisory'); baseline.pop('advisory')
        self.assertEqual(result, baseline)
        self.assertEqual(supplement['status'], 'suggested')
        self.assertEqual(supplement['source'], 'live')  # Mocked transport; no runtime fixture path.
        self.assertFalse(supplement['execution_authority'])
        self.assertEqual(next(iter(supplement['candidates']['existing_goals'].values()))['path'], wt)
        call.assert_called_once()

    def test_explicit_project_limits_questions_and_candidates(self):
        self.existing()
        # Leave capacity for a rule-level create decision; advice cannot change it.
        self.config.write_text(self.config.read_text().replace('max_worktrees: 2', 'max_worktrees: 3'))
        def choose(payload, key):
            self.assertNotIn('project', payload['questions'])
            self.assertEqual(list(payload['state']['projects']), ['project:secretary'])
            task_id = next(iter(payload['state']['existing_goals']))
            return replay(payload, {'existing_goal': task_id})
        result, _, _ = self.invoke('--project', 'secretary', '--goal', '메시지 누락 고치기',
                                   '--advise', 'jev', response=choose)
        self.assertEqual(result['action'], 'create')
        self.assertEqual(result['project'], 'secretary')
        self.assertNotIn('path', result)

    def test_apply_boundary_no_model_and_rule_action_preserved(self):
        with patch.object(advice, 'load_key') as key_loader:
            result, call, _ = self.invoke('--advise', 'jev', '--apply', '--goal', '수정')
        key_loader.assert_not_called()
        self.assertEqual(result['action'], 'needs_project')
        self.assertEqual(result['advisory']['reason'], 'apply_boundary')
        call.assert_not_called()
        self.assertFalse(self.calls.exists())
        result, call, _ = self.invoke('--project', 'secretary', '--goal', '수정', '--apply', '--advise', 'jev')
        self.assertEqual(result['action'], 'create')
        self.assertEqual(result['advisory']['reason'], 'apply_boundary')
        call.assert_not_called()
        self.assertTrue(Path(result['path']).exists())
        result, call, _ = self.invoke('--project', 'secretary', '--goal', '수정', '--apply', '--advise', 'jev')
        self.assertEqual(result['action'], 'reuse')
        call.assert_not_called()

    def test_special_choices_are_not_provider_errors(self):
        for special in ('none', 'ambiguous', 'multiple'):
            result, _, _ = self.invoke('--advise', 'jev', response=lambda p, k: replay(p, {'project': special}))
            self.assertEqual(result['advisory']['status'], 'shadow_advisory')
            self.assertEqual(result['advisory']['answers']['project']['choice'], special)
            self.assertEqual(result['action'], 'needs_project')

    def test_uncertain_or_multiple_intent_keeps_candidates_for_review(self):
        wt = self.existing()
        for kind in ('unclear', 'multiple', 'none'):
            def choose(payload, key):
                self.assertNotIn('ambiguous', payload['questions']['request_type']['criteria'])
                self.assertIn('ENTIRE request', payload['questions']['existing_goal']['instructions'])
                task_id = next(iter(payload['state']['existing_goals']))
                return replay(payload, {'project': 'project:secretary', 'existing_goal': task_id,
                                        'request_type': kind})
            with self.subTest(kind=kind):
                result, _, _ = self.invoke('--advise', 'jev', response=choose)
                supplement = result['advisory']
                self.assertEqual(supplement['status'], 'shadow_advisory')
                self.assertEqual(supplement['reason'], 'request_needs_review')
                self.assertEqual(supplement['answers']['project']['choice'], 'project:secretary')
                self.assertEqual(next(iter(supplement['candidates']['existing_goals'].values()))['path'], wt)
                self.assertEqual(result['action'], 'needs_project')
        # Old duplicate taxonomy must fail closed, not silently map a live answer.
        result, _, _ = self.invoke('--advise', 'jev',
            response=lambda p, k: replay(p, {'request_type': 'ambiguous'}))
        self.assertEqual(result['advisory']['reason'], 'unknown_id')

    def test_existing_goal_advice_at_limit_does_not_unblock_request(self):
        self.existing()
        def choose(payload, key):
            task_id = next(iter(payload['state']['existing_goals']))
            return replay(payload, {'existing_goal': task_id, 'request_type': 'implementation'})
        result, call, code = self.invoke('--project', 'secretary', '--goal', '누락된 메시지 수정',
                                         '--advise', 'jev', response=choose)
        self.assertEqual(result['action'], 'blocked')
        self.assertEqual(code, 1)
        self.assertEqual(result['advisory']['status'], 'suggested')
        call.assert_called_once()

    def test_bad_provider_never_changes_decision_or_logs_exception(self):
        for response in [lambda p, k: {}, lambda p, k: replay(p, {'project': 'invented'}),
                         advice.AdviceError('timeout'), advice.AdviceError('rate_limited')]:
            result, _, code = self.invoke('--advise', 'jev', response=response)
            self.assertEqual(code, 0)
            self.assertEqual(result['action'], 'needs_project')
            self.assertEqual(result['advisory']['status'], 'unavailable')
            self.assertNotIn('answers', result['advisory'])

    def test_incomplete_response_read_preserves_cli_action_and_json(self):
        baseline, _, code = self.invoke()
        with patch.object(advice.urllib.request, 'build_opener') as build:
            response = build.return_value.open.return_value.__enter__.return_value
            response.read.side_effect = http.client.IncompleteRead(b'private partial body', 40)
            result, _, result_code = self.invoke('--advise', 'jev', response=advice.call_jev)
        supplement = result.pop('advisory'); baseline.pop('advisory')
        self.assertEqual(result_code, code)
        self.assertEqual(result, baseline)
        self.assertEqual(supplement['status'], 'unavailable')
        self.assertEqual(supplement['reason'], 'network_error')
        self.assertNotIn('partial', json.dumps(supplement))
        response.read.assert_called_once_with(advice.MAX_RESPONSE + 1)

    def test_stale_replaced_locked_and_unregistered_goals_are_excluded(self):
        wt = self.existing()
        self.git('worktree', 'remove', wt)
        self.git('worktree', 'add', '-b', 'replacement', wt, 'main')
        def check(payload, key):
            self.assertEqual(payload['state']['existing_goals'], {})
            self.assertNotIn('existing_goal', payload['questions'])
            return replay(payload)
        self.invoke('--advise', 'jev', response=check)
        # A registered but locked goal must also disappear from suggestions.
        self.report('--goal', '다른 목표', '--worktree', wt, '--apply')
        self.git('worktree', 'lock', wt)
        self.invoke('--advise', 'jev', response=check)

    def test_candidate_change_during_call_discards_advice(self):
        wt = self.existing()
        def changed(payload, key):
            self.git('worktree', 'lock', wt)
            return replay(payload, {'project': 'project:secretary'})
        result, _, _ = self.invoke('--advise', 'jev', response=changed)
        self.assertEqual(result['advisory']['reason'], 'stale_candidates')
        self.assertNotIn('answers', result['advisory'])

    def test_ambiguous_alias_stays_ambiguous_and_corrupt_metadata_stops_advice(self):
        with self.config.open('a') as f:
            f.write(f'  other:\n    path: "{self.repo}"\n    aliases: "카카오 비서"\n')
        result, _, _ = self.invoke('--advise', 'jev', text='카카오 비서',
            response=lambda p, k: replay(p, {'project': 'project:secretary'}))
        self.assertEqual(set(result['candidates']), {'secretary', 'other'})
        self.assertEqual(result['action'], 'needs_project')
        folder = self.repo / '.git/awo'
        folder.mkdir(exist_ok=True)
        (folder / 'tasks.json').write_text('{}')
        result, call, _ = self.invoke('--advise', 'jev')
        call.assert_not_called()
        self.assertEqual(result['advisory']['reason'], 'candidate_state_unavailable')

    def test_sensitive_or_excessive_catalog_fails_without_network(self):
        with self.config.open('a') as f:
            f.write('    description: "password=private"\n')
        result, call, _ = self.invoke('--advise', 'jev')
        self.assertEqual(result['advisory']['reason'], 'sensitive_input')
        call.assert_not_called()
        with patch.object(advice, 'catalog', side_effect=advice.AdviceError('candidate_limit')):
            result, call, _ = self.invoke('--advise', 'jev')
        self.assertEqual(result['advisory']['reason'], 'candidate_limit')
        call.assert_not_called()


if __name__ == '__main__':
    unittest.main()
