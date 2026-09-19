from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import awo_terminals as tt

NONCE = 'n42'


def row(state, handle='t1', title='카톡 작업'):
    return dict(handle=handle, title=title, state=state, agent='claude' if state not in ('IDLE_SHELL', 'BUSY_SHELL') else None,
                path='/r', idle_hours=1.0, closable=False, reason='')


class Fake:
    def __init__(self, idle=(True, True), screen='', dirty_before=(), dirty_after=()):
        self.idle = list(idle)
        self.screen = screen
        self.dirty = [list(dirty_before), list(dirty_after)]
        self.sent, self.closed = [], []

    def deps(self):
        return dict(send=lambda h, t: self.sent.append(t),
                    wait_idle=lambda h, ms: self.idle.pop(0) if self.idle else True,
                    read=lambda h: self.screen,
                    own_dirty=lambda h: self.dirty.pop(0) if len(self.dirty) > 1 else self.dirty[0],
                    close=lambda h: self.closed.append(h), nonce=lambda: NONCE)


class SelectTests(unittest.TestCase):
    def test_title_or_handle_prefix_must_match_exactly_one(self):
        rows = [row('WORKING', 't_abc', '카톡 작업'), row('WORKING', 't_xyz', '유튜브')]
        self.assertEqual(tt.select(rows, '유튜브')['handle'], 't_xyz')
        self.assertEqual(tt.select(rows, 't_ab')['handle'], 't_abc')
        with self.assertRaises(RuntimeError):
            tt.select(rows, 't_')
        with self.assertRaises(RuntimeError):
            tt.select(rows, '없음')


class ParseTests(unittest.TestCase):
    def test_echoed_prompt_is_not_a_report(self):
        echo = f'[AWO 창 정리 요청 {NONCE}] ... 마지막 줄: AWO-RETIRE {NONCE} 뒤에 DONE 또는 BLOCKED'
        self.assertIsNone(tt.parse_retire(echo, NONCE))

    def test_done_and_blocked_lines(self):
        self.assertEqual(tt.parse_retire(f'x\nAWO-RETIRE {NONCE} DONE 커밋 2개\n', NONCE)[0], 'DONE')
        self.assertEqual(tt.parse_retire(f'AWO-RETIRE {NONCE} BLOCKED 다른 창 파일과 겹침', NONCE),
                         ('BLOCKED', '다른 창 파일과 겹침'))

    def test_other_nonce_is_ignored(self):
        self.assertIsNone(tt.parse_retire('AWO-RETIRE old DONE', NONCE))


class RetireTests(unittest.TestCase):
    def run_retire(self, r, fake, apply=True):
        return tt.retire(r, apply=apply, timeout_ms=1000, **fake.deps())

    def test_live_agent_done_and_clean_is_closed(self):
        f = Fake(screen=f'AWO-RETIRE {NONCE} DONE 커밋 1개', dirty_before=['/r:a.py'], dirty_after=[])
        out = self.run_retire(row('WORKING'), f)
        self.assertEqual(out['result'], 'closed')
        self.assertEqual(f.closed, ['t1'])
        self.assertIn(NONCE, f.sent[0])
        self.assertNotIn('\n', f.sent[0])

    def test_done_but_files_still_dirty_keeps_window(self):
        f = Fake(screen=f'AWO-RETIRE {NONCE} DONE', dirty_before=['/r:a.py'], dirty_after=['/r:a.py'])
        out = self.run_retire(row('IDLE_AGENT'), f)
        self.assertEqual((out['result'], f.closed), ('kept_uncommitted', []))
        self.assertEqual(out['files'], ['/r:a.py'])

    def test_blocked_report_keeps_window(self):
        f = Fake(screen=f'AWO-RETIRE {NONCE} BLOCKED 겹침')
        out = self.run_retire(row('WORKING'), f)
        self.assertEqual((out['result'], f.closed), ('kept_blocked', []))

    def test_busy_agent_is_not_interrupted(self):
        f = Fake(idle=(False,))
        out = self.run_retire(row('WORKING'), f)
        self.assertEqual((out['result'], f.sent, f.closed), ('kept_busy', [], []))

    def test_no_report_before_timeout_keeps_window(self):
        f = Fake(idle=(True, False), screen='still thinking')
        out = self.run_retire(row('WORKING'), f)
        self.assertEqual((out['result'], f.closed), ('kept_no_report', []))

    def test_dead_window_closes_only_when_its_files_are_clean(self):
        clean, dirty = Fake(), Fake(dirty_before=['/r:b.py'], dirty_after=['/r:b.py'])
        self.assertEqual(self.run_retire(row('EXITED'), clean)['result'], 'closed')
        out = self.run_retire(row('EXITED'), dirty)
        self.assertEqual((out['result'], dirty.closed, dirty.sent), ('kept_needs_human', [], []))

    def test_self_and_busy_shell_are_refused(self):
        for state in ('SELF', 'BUSY_SHELL', 'UNKNOWN'):
            f = Fake()
            self.assertEqual(self.run_retire(row(state), f)['result'], 'refused')
            self.assertEqual((f.sent, f.closed), ([], []))

    def test_preview_without_apply_changes_nothing(self):
        f = Fake(dirty_before=['/r:a.py'])
        out = self.run_retire(row('WORKING'), f, apply=False)
        self.assertEqual((out['result'], f.sent, f.closed), ('preview', [], []))


if __name__ == '__main__':
    unittest.main()
