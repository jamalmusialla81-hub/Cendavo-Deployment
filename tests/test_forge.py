import json
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

    def test_auth_check_does_not_require_codex(self):
        def fake_run(argv, **kwargs):
            self.assertNotIn('codex', argv[0])
            return subprocess.CompletedProcess(argv, 0, '{"authMethod":"claude.ai"}', '')
        with tempfile.TemporaryDirectory() as tmp, patch.object(forge, 'STATE', Path(tmp)), patch.object(forge, 'AGENTS_FILE', Path(tmp)/'agents.json'), \
                patch.object(forge.shutil, 'which', return_value='/usr/bin/tool'), patch.object(forge.subprocess, 'run', side_effect=fake_run):
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


class AgentDefinitionTests(unittest.TestCase):
    def test_all_required_agents_load_inline_with_expected_tools(self):
        agents = forge.load_agents()
        for name in forge.REQUIRED_AGENTS:
            self.assertIn(name, agents)
        for name in ('cendavo-strategist', 'cendavo-security-reviewer', 'cendavo-auditor'):
            self.assertEqual(agents[name]['tools'], ['Read', 'Glob', 'Grep'])
        self.assertNotIn('Bash', agents['cendavo-builder']['tools'])

    def test_missing_agent_is_reported_not_silently_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, 'cendavo-strategist.md').write_text('---\nname: cendavo-strategist\ndescription: x\ntools: Read\n---\nbody')
            with patch.object(forge, 'AGENT_DIR', Path(tmp)):
                with self.assertRaisesRegex(RuntimeError, 'cendavo-builder'):
                    forge.load_agents()

    def test_claude_argv_loads_agents_inline_and_restricts_reviewers(self):
        argv = forge.claude_argv('cendavo-security-reviewer', writable=False)
        self.assertIn('--agents', argv)
        self.assertEqual(argv[argv.index('--agent') + 1], 'cendavo-security-reviewer')
        self.assertEqual(argv[argv.index('--tools') + 1], 'Read,Glob,Grep')
        self.assertIn('--no-session-persistence', argv)
        deny = argv[argv.index('--disallowedTools') + 1]
        for item in ('Bash', 'Edit', 'Write', 'mcp__*', 'Read(.env*)'):
            self.assertIn(item, deny)
        self.assertNotIn('--resume', argv)
        self.assertNotIn('--continue', argv)
        self.assertFalse(any('codex' in a for a in argv))

    def test_builder_gets_skill_only_for_frontend_plugin(self):
        plain = forge.claude_argv('cendavo-builder', writable=True)
        self.assertNotIn('Skill', plain[plain.index('--tools') + 1])
        front = forge.claude_argv('cendavo-builder', writable=True, frontend=True)
        self.assertIn('Skill(insane-web-design:*)', front[front.index('--allowedTools') + 1])
        self.assertIn('Edit(.claude/**)', front[front.index('--disallowedTools') + 1])

    def test_frontend_detection(self):
        self.assertTrue(forge.is_frontend_task('Improve keyboard access in the demo'))
        self.assertTrue(forge.is_frontend_task('Refactor', ['assets/demo.js']))
        self.assertFalse(forge.is_frontend_task('Tidy the queue schema'))

    def test_verdict_parsing_is_strict(self):
        self.assertEqual(forge.verdict_of('VERDICT: PASS\nok'), 'PASS')
        self.assertEqual(forge.verdict_of('\n\nVERDICT: BLOCK - bad'), 'BLOCK')
        self.assertIsNone(forge.verdict_of('Looks fine. VERDICT: PASS'))
        self.assertIsNone(forge.verdict_of(''))

    def test_pipeline_has_no_codex_invocation(self):
        source = Path(forge.__file__).read_text()
        self.assertNotIn("'codex'", source)
        self.assertFalse(hasattr(forge, 'codex_review'))


class PipelineTests(unittest.TestCase):
    """Drive run_task in a throwaway git repo with Claude and the test sandbox mocked."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.root = base / 'repo'
        self.root.mkdir()
        self.state = base / 'state'
        for cmd in (['init', '-q'], ['config', 'user.email', 't@example.com'], ['config', 'user.name', 'T']):
            subprocess.run(['git', *cmd], cwd=self.root, check=True)
        (self.root / 'README.md').write_text('hi\n')
        subprocess.run(['git', 'add', '.'], cwd=self.root, check=True)
        subprocess.run(['git', 'commit', '-qm', 'init'], cwd=self.root, check=True)
        self.patches = [patch.multiple(forge, ROOT=self.root, STATE=self.state, DB=self.state/'queue.sqlite3', REPORTS=self.state/'reports',
                                       LOGS=self.state/'logs', STOP=self.state/'STOP', ACTIVE=self.state/'active.json',
                                       AGENTS_FILE=self.state/'agents.json')]
        for p in self.patches:
            p.start()
        self.conn = forge.ensure_state()
        forge.add_task(self.conn, 1, 'Add a feature')
        self.row = (1, 1, 'Add a feature', 0)
        self.calls = []
        self.verdicts = {'cendavo-security-reviewer': ['VERDICT: PASS'], 'cendavo-auditor': ['VERDICT: PASS']}
        self.test_runs = 0
        self.deadline = forge.time.monotonic() + 3600

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.conn.close()
        self.tmp.cleanup()

    def fake_report(self, task_id, name, agent, prompt, deadline, writable=False, frontend=False):
        self.calls.append((name, agent, prompt))
        if agent == 'cendavo-strategist':
            return 'DECISION: APPROVE\nBUILDER BRIEF: add feature.txt'
        if agent == 'cendavo-builder':
            (self.root / 'feature.txt').write_text(f'v{len(self.calls)}\n')
            return 'done'
        queue = self.verdicts[agent]
        return queue.pop(0) if len(queue) > 1 else queue[0]

    def fake_tests(self, task_id, deadline):
        self.test_runs += 1

    def run_pipeline(self):
        with patch.object(forge, 'claude_report', side_effect=self.fake_report), patch.object(forge, 'tests', side_effect=self.fake_tests):
            return forge.run_task(self.conn, self.row, self.deadline)

    def agents_called(self):
        return [a for _, a, _ in self.calls]

    def test_full_pipeline_order_and_checkpoint(self):
        self.run_pipeline()
        self.assertEqual(self.agents_called(), ['cendavo-strategist', 'cendavo-builder', 'cendavo-security-reviewer', 'cendavo-auditor'])
        self.assertEqual(self.test_runs, 1)
        log = subprocess.run(['git', 'log', '--oneline'], cwd=self.root, text=True, capture_output=True).stdout
        self.assertIn('Forge: Add a feature', log)
        self.assertEqual(self.conn.execute('SELECT state FROM tasks WHERE id=1').fetchone()[0], 'completed')
        self.assertFalse(forge.checkpoint_path(1).exists())

    def test_reviewers_never_see_builder_report_and_get_the_diff(self):
        self.run_pipeline()
        for name, agent, prompt in self.calls:
            if agent in ('cendavo-security-reviewer', 'cendavo-auditor'):
                self.assertIn('feature.txt', prompt)
                self.assertNotIn('Builder report', prompt)
                self.assertNotEqual(prompt, '')

    def test_security_block_stops_before_tests_and_commit(self):
        self.verdicts['cendavo-security-reviewer'] = ['VERDICT: BLOCK exfiltration']
        with self.assertRaises(forge.SecurityFailure):
            self.run_pipeline()
        self.assertEqual(self.test_runs, 0)
        self.assertNotIn('cendavo-auditor', self.agents_called())
        log = subprocess.run(['git', 'log', '--oneline'], cwd=self.root, text=True, capture_output=True).stdout
        self.assertNotIn('Forge:', log)

    def test_security_fix_then_retest_and_audit_on_fixed_change(self):
        self.verdicts['cendavo-security-reviewer'] = ['VERDICT: FIX bad', 'VERDICT: PASS']
        self.run_pipeline()
        self.assertEqual(self.agents_called().count('cendavo-builder'), 2)
        self.assertEqual(self.agents_called().count('cendavo-security-reviewer'), 2)
        self.assertEqual(self.test_runs, 1)

    def test_audit_fix_reruns_security_and_tests(self):
        self.verdicts['cendavo-auditor'] = ['VERDICT: FIX bug', 'VERDICT: PASS']
        self.run_pipeline()
        self.assertEqual(self.agents_called().count('cendavo-security-reviewer'), 2)
        self.assertEqual(self.test_runs, 2)

    def test_fix_retries_are_bounded(self):
        self.verdicts['cendavo-auditor'] = ['VERDICT: FIX still broken']
        with self.assertRaisesRegex(RuntimeError, 'cycle limit'):
            self.run_pipeline()
        self.assertLessEqual(self.agents_called().count('cendavo-builder'), 1 + forge.MAX_REVIEW_CYCLES)

    def test_malformed_verdict_fails_closed(self):
        self.verdicts['cendavo-security-reviewer'] = ['Looks good to me']
        with self.assertRaisesRegex(RuntimeError, 'verdict missing'):
            self.run_pipeline()
        self.assertEqual(self.test_runs, 0)

    def test_strategist_rejection_skips_build(self):
        def reject(task_id, name, agent, *a, **k):
            self.calls.append((name, agent, ''))
            return 'DECISION: REJECT\nNo customer evidence'
        with patch.object(forge, 'claude_report', side_effect=reject):
            forge.run_task(self.conn, self.row, self.deadline)
        self.assertEqual(self.agents_called(), ['cendavo-strategist'])
        self.assertEqual(self.conn.execute('SELECT state FROM tasks WHERE id=1').fetchone()[0], 'rejected')

    def test_interruption_reuses_validated_stages(self):
        calls_before = None
        # First run: stop after tests by failing the auditor with a provider limit.
        def limited(task_id, name, agent, prompt, deadline, writable=False, frontend=False):
            if agent == 'cendavo-auditor':
                raise forge.RateLimited('limit')
            return self.fake_report(task_id, name, agent, prompt, deadline, writable, frontend)
        with patch.object(forge, 'claude_report', side_effect=limited), patch.object(forge, 'tests', side_effect=self.fake_tests):
            with self.assertRaises(forge.RateLimited):
                forge.run_task(self.conn, self.row, self.deadline)
        first = list(self.agents_called())
        self.assertEqual(first, ['cendavo-strategist', 'cendavo-builder', 'cendavo-security-reviewer'])
        self.assertEqual(self.test_runs, 1)
        # Second run resumes: dirty tree matches validated fingerprint, so only the audit runs.
        self.run_pipeline()
        second = self.agents_called()[len(first):]
        self.assertEqual(second, ['cendavo-auditor'])
        self.assertEqual(self.test_runs, 1)
        self.assertEqual(self.conn.execute('SELECT state FROM tasks WHERE id=1').fetchone()[0], 'completed')

    def test_unvalidated_dirty_tree_is_refused(self):
        (self.root / 'stray.txt').write_text('manual edit\n')
        with self.assertRaisesRegex(RuntimeError, 'not validated'):
            self.run_pipeline()
        self.assertEqual(self.calls, [])

    def test_edit_after_validation_invalidates_checkpoint(self):
        def limited(task_id, name, agent, prompt, deadline, writable=False, frontend=False):
            if agent == 'cendavo-auditor':
                raise forge.RateLimited('limit')
            return self.fake_report(task_id, name, agent, prompt, deadline, writable, frontend)
        with patch.object(forge, 'claude_report', side_effect=limited), patch.object(forge, 'tests', side_effect=self.fake_tests):
            with self.assertRaises(forge.RateLimited):
                forge.run_task(self.conn, self.row, self.deadline)
        (self.root / 'feature.txt').write_text('tampered\n')
        with self.assertRaisesRegex(RuntimeError, 'not validated'):
            self.run_pipeline()

    def test_protected_file_change_is_rejected(self):
        def tamper(task_id, name, agent, prompt, deadline, writable=False, frontend=False):
            self.calls.append((name, agent, prompt))
            if agent == 'cendavo-strategist':
                return 'DECISION: APPROVE'
            (self.root / 'scripts').mkdir(exist_ok=True)
            (self.root / 'scripts' / 'forge.py').write_text('evil')
            return 'done'
        with patch.object(forge, 'claude_report', side_effect=tamper), patch.object(forge, 'tests', side_effect=self.fake_tests):
            with self.assertRaisesRegex(RuntimeError, 'protected'):
                forge.run_task(self.conn, self.row, self.deadline)
        self.assertEqual(self.test_runs, 0)


class RunnerStopTests(unittest.TestCase):
    def run_main(self, exc):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            with patch.multiple(forge, STATE=state, DB=state/'queue.sqlite3', REPORTS=state/'reports', LOGS=state/'logs', STOP=state/'STOP',
                                ACTIVE=state/'active.json'):
                conn = forge.ensure_state()
                forge.add_task(conn, 1, 'A')
                forge.add_task(conn, 2, 'B')
                conn.close()
                with patch.object(forge, 'check_tools', return_value=None), patch.object(forge, 'frontend_plugin_note', return_value=None), \
                        patch.object(forge, 'run_task', side_effect=exc) as run, patch.object(forge.time, 'sleep'), patch('sys.argv', ['forge.py', 'run']):
                    forge.main()
                conn = sqlite3.connect(state/'queue.sqlite3')
                states = dict(conn.execute('SELECT id,state FROM tasks'))
                conn.close()
                return run.call_count, states

    def test_provider_limit_stops_and_does_not_burn_an_attempt(self):
        calls, states = self.run_main(forge.RateLimited('limit'))
        self.assertEqual((calls, states[1], states[2]), (1, 'interrupted', 'queued'))

    def test_security_failure_stops_run_and_blocks_task(self):
        calls, states = self.run_main(forge.SecurityFailure('bad'))
        self.assertEqual((calls, states[1], states[2]), (1, 'blocked', 'queued'))

    def test_unexpected_error_stops_run(self):
        calls, states = self.run_main(ValueError('boom'))
        self.assertEqual(calls, 1)
        self.assertEqual(states[2], 'queued')


if __name__ == '__main__':
    unittest.main()
