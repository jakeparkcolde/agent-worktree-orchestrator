"""Mock Path.home to a temporary fixture; never read the user's key file."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from awo_advice import AdviceError, load_key


class JevKeyTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name)
        self.file = self.home / '.config/awo/jev.env'
        self.file.parent.mkdir(parents=True)
        env = {k: v for k, v in os.environ.items() if k != 'TYPESAFE_API_KEY'}
        patcher = patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        home_patch = patch('awo_advice.Path.home', return_value=self.home)
        home_patch.start()
        self.addCleanup(home_patch.stop)

    def write(self, body='TYPESAFE_API_KEY=fixture-key\n', mode=0o600):
        if self.file.exists():
            self.file.chmod(0o600)
        self.file.write_text(body)
        self.file.chmod(mode)

    def failure(self, reason):
        with self.assertRaises(AdviceError) as caught:
            load_key()
        self.assertEqual(str(caught.exception), reason)
        self.assertNotIn('fixture-key', str(caught.exception))
        self.assertNotIn(str(self.file), str(caught.exception))

    def test_missing_and_empty_key(self):
        self.failure('missing_key')
        for content in ('', 'TYPESAFE_API_KEY=', 'TYPESAFE_API_KEY=\n'):
            self.write(content)
            self.failure('missing_key')

    def test_valid_file_unchanged(self):
        for ending in ('', '\n', '\r\n'):
            self.write('TYPESAFE_API_KEY=fixture-key' + ending)
            before = self.file.read_bytes()
            self.assertEqual(load_key(), 'fixture-key')
            self.assertEqual(self.file.read_bytes(), before)
            self.assertEqual(self.file.stat().st_mode & 0o7777, 0o600)

    def test_utf8_template_comments_and_blank_lines(self):
        self.write('# TypeSafe(Jev) API 키를 아래 등호 뒤에 붙여 넣고 저장하세요.\n'
                   '\nTYPESAFE_API_KEY=fake-test-key\n\n  # 메모\n')
        before = self.file.read_bytes()
        self.assertEqual(load_key(), 'fake-test-key')
        self.assertEqual(self.file.read_bytes(), before)

    def test_environment_precedence_including_explicit_empty(self):
        self.write('malformed file', 0o644)
        with patch.dict(os.environ, {'TYPESAFE_API_KEY': 'environment-key'}), patch('awo_advice.os.open') as opened:
            self.assertEqual(load_key(), 'environment-key')
            opened.assert_not_called()
        with patch.dict(os.environ, {'TYPESAFE_API_KEY': ''}), patch('awo_advice.os.open') as opened:
            self.failure('missing_key')
            opened.assert_not_called()

    def test_symlink_permissions_owner_and_nonregular_rejected(self):
        self.file.symlink_to(self.home / 'nonexistent')
        self.failure('key_file_unreadable')
        self.file.unlink()
        for mode in (0o644, 0o400, 0o660, 0o1600):
            self.write(mode=mode)
            self.failure('key_file_permissions')
        self.write()
        with patch('awo_advice.os.getuid', return_value=os.getuid() + 1):
            self.failure('key_file_owner')
        self.file.unlink()
        os.mkfifo(self.file, 0o600)
        self.failure('key_file_type')
        self.file.unlink()
        self.file.mkdir()
        self.failure('key_file_unreadable')

    def test_strict_format_and_no_shell_evaluation(self):
        for content in ('export TYPESAFE_API_KEY=fixture-key', '# 주석만 있음\n',
                        'TYPESAFE_API_KEY=fixture-key\nOTHER=value\n',
                        'TYPESAFE_API_KEY=fixture-key\nTYPESAFE_API_KEY=second-key\n',
                        'OTHER=fixture-key', 'x' * 4097):
            self.write(content)
            self.failure('key_file_format')
        for value in ('"fixture-key"', "'fixture-key'", ' fixture-key', 'fixture-key ',
                      '$(touch sentinel)', '`touch sentinel`', 'fixture-key; echo private',
                      '키', 'fixture-key # inline comment'):
            self.write('TYPESAFE_API_KEY=' + value)
            self.failure('invalid_key_format')
        self.assertFalse((self.home / 'sentinel').exists())
        with patch.dict(os.environ, {'TYPESAFE_API_KEY': 'fixture-key\nINJECTED=value'}):
            self.failure('invalid_key_format')


if __name__ == '__main__':
    unittest.main()
