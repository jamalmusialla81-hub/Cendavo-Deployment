import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts import forge


class ForgeQueueTests(unittest.TestCase):
    def test_queue_persists_order_and_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            with patch.multiple(forge, STATE=state, DB=state/'queue.sqlite3', REPORTS=state/'reports', LOGS=state/'logs'):
                conn = forge.ensure_state()
                forge.add_task(conn, 5, 'Later')
                forge.add_task(conn, 1, 'First')
                conn.close()
                again = forge.ensure_state()
                titles = [row[0] for row in again.execute('SELECT title FROM tasks ORDER BY priority,id')]
                events = again.execute('SELECT COUNT(*) FROM events').fetchone()[0]
                self.assertEqual(titles, ['First','Later'])
                self.assertEqual(events, 2)
                again.close()

    def test_auth_check_pauses_when_claude_missing(self):
        original = forge.shutil.which
        with patch.object(forge.shutil, 'which', side_effect=lambda name: None if name == 'claude' else original(name)), patch.object(forge, 'LOCAL_BIN', Path('/nonexistent-cendavo-bin')):
            self.assertIn('claude', forge.check_tools())

    def test_codex_login_can_report_on_stderr(self):
        def fake_run(argv, **kwargs):
            if argv[0] == 'codex':
                return subprocess.CompletedProcess(argv, 0, '', 'Logged in using ChatGPT')
            return subprocess.CompletedProcess(argv, 0, '{"authMethod":"claude.ai"}', '')
        with patch.object(forge.shutil, 'which', return_value='/usr/bin/tool'), patch.object(forge.subprocess, 'run', side_effect=fake_run):
            self.assertIsNone(forge.check_tools())

    def test_resume_reconciles_stale_running_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            with patch.multiple(forge, STATE=state, DB=state/'queue.sqlite3', REPORTS=state/'reports', LOGS=state/'logs', STOP=state/'STOP', ACTIVE=state/'active-child.json'):
                conn = forge.ensure_state()
                forge.add_task(conn, 1, 'Interrupted work')
                forge.set_state(conn, 1, 'running')
                conn.close()
                with patch('sys.argv', ['forge.py','resume']):
                    self.assertEqual(forge.main(), 0)
                conn = sqlite3.connect(state/'queue.sqlite3')
                self.assertEqual(conn.execute('SELECT state FROM tasks WHERE id=1').fetchone()[0], 'queued')
                conn.close()


if __name__ == '__main__':
    unittest.main()
