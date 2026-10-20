"""離線測試：真實 hook process，fake curl 不連網。"""
import json
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'magic_conch.py'


class HookTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'bin').mkdir()
        curl = self.root / 'bin/curl'
        curl.write_text('''#!/usr/bin/env python3
import json, os, pathlib, sys
pathlib.Path(os.environ['TEST_CURL_ARGS']).write_text(json.dumps(sys.argv[1:]))
if os.environ.get('TEST_CURL_FAIL'): sys.exit(28)
print(os.environ.get('TEST_CURL_RESPONSE', '{"answer":"放手吧"}'))
''')
        curl.chmod(0o755)
        self.env = dict(os.environ, PATH=str(self.root / 'bin') + os.pathsep + os.environ['PATH'],
                        MAGIC_CONCH_CACHE_DIR=str(self.root / 'obsolete-cache'),
                        TEST_CURL_ARGS=str(self.root / 'curl-args.json'))
        self.env.pop('MAGIC_CONCH_MAX_CONTINUATIONS', None)

    def run_hook(self, message='A private question without ASK?', raw=None, active=False, skill=False):
        event = {'hook_event_name': 'Stop', 'session_id': 'same-session',
                 'last_assistant_message': message, 'stop_hook_active': active}
        result = subprocess.run([sys.executable, str(SCRIPT)] + (['--claude-skill'] if skill else []), input=raw if raw is not None else json.dumps(event),
                                text=True, capture_output=True, env=self.env, timeout=10)
        if skill:
            return result
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '')
        return json.loads(result.stdout)

    def test_only_uppercase_done_token_at_start_passes_without_network(self):
        for message in ['DONE', '  DONE: finished', 'DONE：完成', '\nDONE verified', 'DONE.']:
            with self.subTest(message=message): self.assertEqual(self.run_hook(message), {})
        self.assertFalse((self.root / 'curl-args.json').exists())

    def test_all_other_messages_continue_including_questions_progress_and_empty(self):
        for message in ['A private question?', 'Still working.', '', 'ASK:', 'done', 'Done',
                        'UNDONE', '說到DONE', 'DONEish', 'DONE_soon', 'DONE完成']:
            with self.subTest(message=message):
                result = self.run_hook(message)
                self.assertEqual(result['decision'], 'block')
                self.assertIn('放手吧', result['reason'])
        argv = json.loads((self.root / 'curl-args.json').read_text())
        self.assertEqual(argv[-1], 'https://answerbook.david888.com/answersOriginal?lang=zh-TW')
        self.assertEqual(argv[argv.index('--max-time') + 1], '5')
        self.assertNotIn('private', ' '.join(argv))

    def test_more_than_three_active_continuations_have_no_state_or_limit(self):
        for _ in range(5): self.assertEqual(self.run_hook(active=True)['decision'], 'block')
        self.assertFalse((self.root / 'obsolete-cache').exists())

    def test_api_failures_and_empty_or_bad_responses_use_fixed_continuation(self):
        self.env['TEST_CURL_FAIL'] = '1'
        fallback = self.run_hook()
        self.assertEqual(fallback['decision'], 'block')
        self.assertIn('完成才回 DONE', fallback['reason'])
        del self.env['TEST_CURL_FAIL']
        for response in ['not json', '{}', '{"answer":null}', '{"answer":""}',
                         '{"answer":"  "}', '[]']:
            self.env['TEST_CURL_RESPONSE'] = response
            with self.subTest(response=response): self.assertEqual(self.run_hook(), fallback)

    def test_bad_input_or_missing_fields_also_blocks(self):
        for raw in ['not json', '[]', 'null', '{}', '{"hook_event_name":"Stop"}',
                    '{"last_assistant_message":3}']:
            with self.subTest(raw=raw): self.assertEqual(self.run_hook(raw=raw)['decision'], 'block')

    def test_configured_limit_is_atomic_and_per_session(self):
        self.env['MAGIC_CONCH_MAX_CONTINUATIONS'] = '3'
        with ThreadPoolExecutor(max_workers=5) as pool:
            results = list(pool.map(lambda _: self.run_hook(), range(5)))
        self.assertEqual(sum(x.get('decision') == 'block' for x in results), 3)
        self.assertEqual(sum(x.get('continue') is False for x in results), 2)
        other = '{"hook_event_name":"Stop","session_id":"other","last_assistant_message":"Working"}'
        self.assertEqual(self.run_hook(raw=other)['decision'], 'block')

    def test_api_failure_fallback_uses_continuation_budget(self):
        self.env['MAGIC_CONCH_MAX_CONTINUATIONS'] = '2'
        self.env['TEST_CURL_FAIL'] = '1'
        for _ in range(2): self.assertEqual(self.run_hook()['decision'], 'block')
        self.assertIs(self.run_hook()['continue'], False)

    def test_empty_limit_is_unlimited_and_invalid_limit_is_diagnostic_stop(self):
        self.env['MAGIC_CONCH_MAX_CONTINUATIONS'] = ''
        for _ in range(4): self.assertEqual(self.run_hook()['decision'], 'block')
        self.assertFalse((self.root / 'obsolete-cache').exists())
        for value in ['0', '-1', 'abc', '1.5']:
            self.env['MAGIC_CONCH_MAX_CONTINUATIONS'] = value
            with self.subTest(value=value):
                result = self.run_hook()
                self.assertIs(result['continue'], False)
                self.assertIn('MAGIC_CONCH_MAX_CONTINUATIONS', result['stopReason'])

    def test_finite_limit_without_session_or_writable_cache_is_diagnostic_stop(self):
        self.env['MAGIC_CONCH_MAX_CONTINUATIONS'] = '2'
        result = self.run_hook(raw='{"hook_event_name":"Stop","last_assistant_message":"Working"}')
        self.assertIs(result['continue'], False)
        obstruction = self.root / 'not-a-directory'
        obstruction.write_text('x')
        self.env['MAGIC_CONCH_CACHE_DIR'] = str(obstruction)
        result = self.run_hook()
        self.assertIs(result['continue'], False)
        self.assertTrue(result['stopReason'])

    def test_skill_uses_exit_two_with_stderr_until_done(self):
        for message in ['Working', '', 'done']:
            result = self.run_hook(message, skill=True)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, '')
            self.assertIn('放手吧', result.stderr)
        result = self.run_hook('DONE: finished', skill=True)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout + result.stderr, '')

    def test_skill_fallback_retains_hook_and_budget_stop_removes_it(self):
        self.env['TEST_CURL_FAIL'] = '1'
        self.env['MAGIC_CONCH_MAX_CONTINUATIONS'] = '1'
        result = self.run_hook(skill=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('完成才回 DONE', result.stderr)
        result = self.run_hook(skill=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn('續跑上限', json.loads(result.stdout)['systemMessage'])
        self.env['MAGIC_CONCH_MAX_CONTINUATIONS'] = 'bad'
        result = self.run_hook(skill=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn('MAGIC_CONCH_MAX_CONTINUATIONS', json.loads(result.stdout)['systemMessage'])

    def test_explicit_nonstop_event_passes_without_network(self):
        self.assertEqual(self.run_hook(raw='{"hook_event_name":"Interrupt"}'), {})
        self.assertFalse((self.root / 'curl-args.json').exists())


if __name__ == '__main__':
    unittest.main()
