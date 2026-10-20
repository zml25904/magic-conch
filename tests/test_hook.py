"""離線測試：用假的 curl，檢查真實 hook stdin/stdout 與 session 上限。"""
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
                        MAGIC_CONCH_CACHE_DIR=str(self.root / 'cache'),
                        TEST_CURL_ARGS=str(self.root / 'curl-args.json'))

    def run_hook(self, message='ASK: a private question?', session='session-a', raw=None):
        event = {'hook_event_name': 'Stop', 'session_id': session,
                 'last_assistant_message': message, 'stop_hook_active': False}
        result = subprocess.run([sys.executable, str(SCRIPT)], input=raw if raw is not None else json.dumps(event),
                                text=True, capture_output=True, env=self.env, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '')
        return json.loads(result.stdout)

    def test_ask_returns_answer_without_sending_question(self):
        result = self.run_hook()
        self.assertEqual(result['decision'], 'block')
        self.assertIn('放手吧', result['reason'])
        self.assertIn('授權', result['reason'])
        argv = json.loads((self.root / 'curl-args.json').read_text())
        self.assertEqual(argv[-1], 'https://answerbook.david888.com/answersOriginal?lang=zh-TW')
        self.assertIn('--max-time', argv)
        self.assertEqual(argv[argv.index('--max-time') + 1], '5')
        self.assertNotIn('private', ' '.join(argv))

    def test_done_nonask_empty_ask_and_bad_input_pass_without_network(self):
        for message in ['DONE: finished', 'A normal answer.', 'ASK:']:
            with self.subTest(message=message): self.assertEqual(self.run_hook(message), {})
        for raw in ['not json', '[]', 'null', '{"last_assistant_message":3}',
                    '{"session_id":"a","last_assistant_message":"ASK: hi"}']:
            with self.subTest(raw=raw): self.assertEqual(self.run_hook(raw=raw), {})
        self.assertFalse((self.root / 'curl-args.json').exists())

    def test_limit_persists_across_processes_and_is_per_session(self):
        for _ in range(3): self.assertEqual(self.run_hook()['decision'], 'block')
        self.assertEqual(self.run_hook(), {})
        self.assertEqual(self.run_hook(session='session-b')['decision'], 'block')

    def test_concurrent_calls_cannot_exceed_session_limit(self):
        with ThreadPoolExecutor(max_workers=5) as pool:
            results = list(pool.map(lambda _: self.run_hook(), range(5)))
        self.assertEqual(sum(x.get('decision') == 'block' for x in results), 3)

    def test_api_error_and_bad_responses_pass_without_continuing(self):
        self.env['TEST_CURL_FAIL'] = '1'
        self.assertEqual(self.run_hook(), {})
        del self.env['TEST_CURL_FAIL']
        for response in ['not json', '{}', '{"answer":null}', '{"answer":""}', '[]']:
            self.env['TEST_CURL_RESPONSE'] = response
            with self.subTest(response=response):
                self.assertEqual(self.run_hook(session=response), {})

    def test_missing_session_or_unwritable_cache_pass(self):
        self.assertEqual(self.run_hook(session=''), {})
        obstruction = self.root / 'not-a-directory'
        obstruction.write_text('x')
        self.env['MAGIC_CONCH_CACHE_DIR'] = str(obstruction)
        self.assertEqual(self.run_hook(), {})
        self.assertFalse((self.root / 'curl-args.json').exists())


if __name__ == '__main__':
    unittest.main()
