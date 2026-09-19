from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import awo_terminals as tt

HOUR = 3600 * 1000
NOW = 1_800_000_000_000
PROMPT = 'user@host agents % '
RESUME = 'Resume this session with:\nclaude --resume "old"\n' + PROMPT


def term(handle, path='/p/main', agent=None, idle_h=13, preview=PROMPT, **extra):
    row = dict(handle=handle, worktreePath=path, agentIdentity=agent, title=handle,
               lastOutputAt=NOW - int(idle_h * HOUR), preview=preview, connected=True)
    row.update(extra)
    return row


def state(row, self_handle='term_self'):
    return tt.classify(row, NOW, 12, self_handle)


class ClassifyTests(unittest.TestCase):
    def test_exited_agent_at_prompt_is_closable(self):
        r = state(term('a', agent='claude', preview='done\n' + RESUME))
        self.assertEqual((r['state'], r['closable']), ('EXITED', True))

    def test_exited_codex_is_closable(self):
        r = state(term('a', agent='codex', preview='To continue this session, run codex resume 01a\n' + PROMPT))
        self.assertEqual((r['state'], r['closable']), ('EXITED', True))

    def test_resume_hint_without_prompt_is_not_exited(self):
        r = state(term('a', agent='claude', preview=RESUME + '\n⏺ still working on it'))
        self.assertNotEqual(r['state'], 'EXITED')
        self.assertFalse(r['closable'])

    def test_duplicate_conversation_is_closable(self):
        r = state(term('a', agent='claude', preview='This conversation is open in another app  R to Retry'))
        self.assertEqual((r['state'], r['closable']), ('DUPLICATE', True))

    def test_idle_plain_shell_at_prompt_is_closable(self):
        r = state(term('a', preview='ls\nREADME.md\n' + PROMPT))
        self.assertEqual((r['state'], r['closable']), ('IDLE_SHELL', True))

    def test_shell_running_service_is_never_closable(self):
        r = state(term('a', idle_h=40, preview='[bridge] polling kakao...\n[bridge] 3 new'))
        self.assertEqual((r['state'], r['closable']), ('BUSY_SHELL', False))

    def test_idle_live_agent_is_reported_not_closed(self):
        r = state(term('a', agent='claude', idle_h=30, preview='› Ask anything'))
        self.assertEqual((r['state'], r['closable']), ('IDLE_AGENT', False))

    def test_recent_agent_is_working(self):
        r = state(term('a', agent='codex', idle_h=0.5, preview='› Ask Codex'))
        self.assertEqual((r['state'], r['closable']), ('WORKING', False))

    def test_recent_candidates_are_kept_until_threshold(self):
        for preview, agent in ((RESUME, 'claude'), (PROMPT, None)):
            r = state(term('a', agent=agent, idle_h=2, preview=preview))
            self.assertFalse(r['closable'], preview)

    def test_self_terminal_is_protected(self):
        r = state(term('term_self', agent='claude', preview=RESUME))
        self.assertEqual((r['state'], r['closable']), ('SELF', False))

    def test_missing_activity_time_is_unknown(self):
        row = term('a', preview=PROMPT)
        row['lastOutputAt'] = None
        r = state(row)
        self.assertEqual((r['state'], r['closable']), ('UNKNOWN', False))

    def test_future_timestamp_is_clamped_to_zero(self):
        r = state(term('a', agent='claude', idle_h=-0.01, preview='›'))
        self.assertEqual((r['idle_hours'], r['state']), (0.0, 'WORKING'))

    def test_ansi_codes_do_not_hide_prompt(self):
        r = state(term('a', preview='\x1b[32mREADME.md\x1b[0m\n\x1b[1m' + PROMPT + '\x1b[0m'))
        self.assertEqual(r['state'], 'IDLE_SHELL')


class InventoryTests(unittest.TestCase):
    def listing(self, *rows, truncated=False):
        return {'result': {'terminals': list(rows), 'truncated': truncated}}

    def test_filters_to_project_paths(self):
        inv = tt.inventory({'/p/main', '/p/wt'}, self.listing(term('a'), term('b', path='/other')), NOW, 12, None)
        self.assertEqual([r['handle'] for r in inv['rows']], ['a'])

    def test_warns_when_two_agents_work_in_same_checkout(self):
        inv = tt.inventory({'/p/main'}, self.listing(term('a', agent='claude', idle_h=0.1), term('b', agent='codex', idle_h=1)), NOW, 12, None)
        self.assertEqual(len(inv['warnings']), 1)
        self.assertIn('/p/main', inv['warnings'][0])

    def test_single_worker_has_no_warning(self):
        inv = tt.inventory({'/p/main'}, self.listing(term('a', agent='claude', idle_h=0.1), term('b', preview=PROMPT)), NOW, 12, None)
        self.assertEqual(inv['warnings'], [])

    def test_truncated_listing_is_flagged(self):
        inv = tt.inventory({'/p/main'}, self.listing(term('a'), truncated=True), NOW, 12, None)
        self.assertTrue(inv['truncated'])


class ApplyTests(unittest.TestCase):
    def setUp(self):
        self.closed = []

    def close(self, handle):
        self.closed.append(handle)

    def test_closes_only_closable_and_rechecks(self):
        rows = [state(term('dead', agent='claude', preview=RESUME)), state(term('live', agent='claude', idle_h=0.1, preview='›'))]
        show = lambda h: term(h, agent='claude', preview=RESUME)
        results = tt.close_safe(rows, show, self.close, NOW, 12, 'term_self')
        self.assertEqual(self.closed, ['dead'])
        self.assertEqual([r['result'] for r in results], ['closed'])

    def test_skips_when_state_changed_since_listing(self):
        rows = [state(term('dead', agent='claude', preview=RESUME))]
        show = lambda h: term(h, agent='claude', idle_h=0, preview='⏺ resumed and working')
        results = tt.close_safe(rows, show, self.close, NOW, 12, 'term_self')
        self.assertEqual(self.closed, [])
        self.assertEqual(results[0]['result'], 'skipped_changed')

    def test_close_failure_is_reported_not_raised(self):
        rows = [state(term('dead', agent='claude', preview=RESUME))]
        def boom(h):
            raise RuntimeError('orca down')
        results = tt.close_safe(rows, lambda h: term(h, agent='claude', preview=RESUME), boom, NOW, 12, 'term_self')
        self.assertEqual(results[0]['result'], 'close_failed')


if __name__ == '__main__':
    unittest.main()
