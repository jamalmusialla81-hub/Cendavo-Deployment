import json
import os
import sqlite3
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts import forge


class IsolatedAgentTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        state = Path(temporary.name)
        isolated = patch.multiple(forge, ROOT=state, STATE=state, AGENTS_FILE=state/'agents.json',
                                  LOCAL_BIN=state/'bin')
        isolated.start()
        self.addCleanup(isolated.stop)
        auth_mock = patch.object(forge, 'check_subscription_auth', return_value=None)
        auth_mock.start()
        self.addCleanup(auth_mock.stop)
        git_mock = patch.object(forge, 'git', return_value=subprocess.CompletedProcess([], 0, '', ''))
        git_mock.start()
        self.addCleanup(git_mock.stop)


class ForgeQueueTests(IsolatedAgentTests):
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
            return subprocess.CompletedProcess(argv, 0, '{"loggedIn":true,"authMethod":"claude.ai","apiProvider":"firstParty","subscriptionType":"max"}', '')
        with tempfile.TemporaryDirectory() as tmp, patch.object(forge, 'STATE', Path(tmp)), patch.object(forge, 'AGENTS_FILE', Path(tmp)/'agents.json'), \
                patch.object(forge.shutil, 'which', return_value='/usr/bin/tool'), patch.object(forge.subprocess, 'run', side_effect=fake_run), \
                patch.object(forge, 'LOCAL_BIN', Path('/nonexistent-cendavo-bin')):
            self.assertIsNone(forge.check_tools())

    def test_builder_command_denies_sensitive_file_tools(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(forge, 'REPORTS', Path(tmp)), patch.object(forge, 'discover_design_plugin', return_value=forge.DesignPlugin(False, 'not installed')), patch.object(forge, 'run_command', return_value='{"result":"ok"}') as command:
            self.assertEqual(forge.claude_report(1, 'builder', 'cendavo-builder', 'Build', time.monotonic() + 60, True), 'ok')
            argv = command.call_args.args[0]
            self.assertIn('--restricted', argv)
            self.assertIn('--strict-mcp-config', argv)
            denied = argv[argv.index('--disallowedTools') + 1]
            for rule in ('mcp__*', 'Read(.git/**)', 'Read(.cendavo-run/**)',
                         'Read(.env.*)', 'Read(secrets/**)',
                         'Edit(scripts/forge_sandbox.py)'):
                self.assertIn(rule, denied)

    def test_frontend_agents_discover_and_can_use_local_design_skills(self):
        with tempfile.TemporaryDirectory() as tmp:
            plugin_dir = Path(tmp) / 'insane-web-design'
            (plugin_dir / '.claude-plugin').mkdir(parents=True)
            (plugin_dir / '.claude-plugin' / 'plugin.json').write_text('{"name":"insane-web-design"}')
            for name in ('design', 'animation', '3d'):
                skill = plugin_dir / 'skills' / name / 'SKILL.md'
                skill.parent.mkdir(parents=True)
                skill.write_text(f'---\nname: {name}\ndescription: {name} guidance\n---\n# {name}\n')
            installed = [{'id':'insane-web-design@synced', 'enabled':True,
                          'installPath':str(plugin_dir)}]
            listed = subprocess.CompletedProcess(['claude','plugin','list','--json'], 0,
                                                 json.dumps(installed), '')
            with patch.dict(os.environ, {forge.DESIGN_PLUGIN_DIR_ENV:''}), patch.object(forge, 'LOCAL_BIN', Path(tmp) / 'none'), patch.object(forge.subprocess, 'run', return_value=listed):
                plugin = forge.discover_design_plugin()
            self.assertTrue(plugin.available, plugin.detail)
            self.assertEqual(plugin.skills, ('3d', 'animation', 'design'))
            with patch.object(forge, 'REPORTS', Path(tmp)), patch.object(forge, 'run_command', return_value='{"result":"ok"}') as command:
                for writable, name, agent in ((False, 'strategy', 'cendavo-strategist'), (True, 'builder', 'cendavo-builder')):
                    forge.claude_report(7, name, agent, 'Improve the frontend', time.monotonic() + 60,
                                        writable, True, plugin)
                    argv, prompt = command.call_args.args[:2]
                    self.assertIn('Skill', argv[argv.index('--tools') + 1])
                    self.assertIn('insane-web-design:design', prompt)
                    self.assertIn('before implementation', prompt)
            with patch.dict(os.environ, {forge.DESIGN_PLUGIN_DIR_ENV:str(plugin_dir)}):
                override = forge.discover_design_plugin()
            self.assertTrue(override.explicit_load)
            with patch.object(forge, 'REPORTS', Path(tmp)), patch.object(forge, 'run_command', return_value='{"result":"ok"}') as command:
                forge.claude_report(7, 'builder-explicit', 'cendavo-builder', 'Improve the frontend',
                                    time.monotonic() + 60, True, True, override)
                self.assertEqual(command.call_args.args[0][command.call_args.args[0].index('--plugin-dir'):][:2], ['--plugin-dir', str(plugin_dir.resolve())])

    def test_design_plugin_hooks_are_not_loaded(self):
        with tempfile.TemporaryDirectory() as tmp:
            plugin_dir = Path(tmp)
            (plugin_dir / '.claude-plugin').mkdir()
            (plugin_dir / '.claude-plugin' / 'plugin.json').write_text('{"name":"insane-web-design","hooks":{}}')
            (plugin_dir / 'hooks').mkdir()
            skill = plugin_dir / 'skills' / 'design' / 'SKILL.md'
            skill.parent.mkdir(parents=True)
            skill.write_text('# design\n')
            plugin = forge._validate_design_plugin(plugin_dir, True)
            self.assertFalse(plugin.available)

    def test_missing_design_plugin_does_not_claim_skill_use(self):
        missing = forge.DesignPlugin(False, 'not installed')
        with tempfile.TemporaryDirectory() as tmp, patch.object(forge, 'REPORTS', Path(tmp)), patch.object(forge, 'run_command', return_value='{"result":"ok"}') as command:
            forge.claude_report(8, 'strategy', 'cendavo-strategist', 'Improve the frontend', time.monotonic() + 60,
                                False, True, missing)
            argv, prompt = command.call_args.args[:2]
            self.assertNotIn('Skill', argv[argv.index('--tools') + 1])
            self.assertIn('unavailable', prompt)

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


class AgentDefinitionTests(IsolatedAgentTests):
    def test_all_required_agents_load_inline_with_expected_tools(self):
        agents = forge.load_agents()
        for name in forge.REQUIRED_AGENTS:
            self.assertIn(name, agents)
        self.assertEqual(agents['cendavo-strategist']['tools'], ['Read', 'Glob', 'Grep', 'Skill'])
        for name in ('cendavo-security-reviewer', 'cendavo-auditor'):
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
        avail = forge.DesignPlugin(True, 'ok', ('design',))
        no_plugin = forge.claude_argv('cendavo-builder', writable=True, frontend=True)
        self.assertNotIn('Skill', no_plugin[no_plugin.index('--tools') + 1])
        reviewer = forge.claude_argv('cendavo-auditor', writable=False, plugin=avail, frontend=True)
        self.assertNotIn('Skill', reviewer[reviewer.index('--tools') + 1])
        front = forge.claude_argv('cendavo-builder', writable=True, plugin=avail, frontend=True)
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
                                       AGENTS_FILE=self.state/'agents.json'),
                        patch.object(forge, 'discover_design_plugin', return_value=forge.DesignPlugin(False, 'test: not installed'))]
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

    def fake_report(self, task_id, name, agent, prompt, deadline, writable=False, frontend=False, design_plugin=None):
        self.calls.append((name, agent, prompt))
        if agent == 'cendavo-strategist':
            return 'DECISION: APPROVE\nBUILDER BRIEF: add feature.txt'
        if agent == 'cendavo-debugger':
            return 'CLASSIFICATION: PRODUCT\nFix assets/feature.txt'
        if agent == 'cendavo-builder':
            (self.root / 'assets').mkdir(exist_ok=True)
            (self.root / 'assets' / 'feature.txt').write_text(f'v{len(self.calls)}\n')
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

    def test_dirty_infrastructure_blocks_before_attempt_or_agent(self):
        (self.root / 'scripts').mkdir()
        (self.root / 'scripts/forge.py').write_text('maintenance')
        with self.assertRaisesRegex(forge.MaintenanceRequired, 'infrastructure'):
            self.run_pipeline()
        self.assertEqual(self.calls, [])
        self.assertEqual(self.conn.execute('SELECT attempts,state FROM tasks WHERE id=1').fetchone(), (0, 'queued'))
        with self.assertRaises(forge.MaintenanceRequired):
            forge.change_snapshot(forge.git('rev-parse', 'HEAD').stdout.strip())

    def test_staged_infrastructure_cannot_enter_product_commit(self):
        (self.root / 'README.md').write_text('maintenance')
        forge.git('add', 'README.md')
        head = forge.git('rev-parse', 'HEAD').stdout
        with self.assertRaisesRegex(forge.MaintenanceRequired, 'Staged'):
            self.run_pipeline()
        self.assertEqual(forge.git('rev-parse', 'HEAD').stdout, head)
        self.assertEqual(self.calls, [])

    def test_manual_resume_runs_fresh_gates_without_rebuilding(self):
        (self.root / 'assets').mkdir()
        (self.root / 'assets/feature.txt').write_text('preserved accessibility')
        baseline = forge.git('rev-parse', 'HEAD').stdout.strip()
        cp = {'baseline':baseline, 'stages':{
            'strategy':{'text':'DECISION: APPROVE', 'fingerprint':None},
            'manual_resume':{'fingerprint':forge.change_snapshot(baseline)[1]}}, 'test_fix_attempts':1}
        forge.save_checkpoint(1, cp)
        self.run_pipeline()
        self.assertEqual(self.agents_called(), ['cendavo-security-reviewer', 'cendavo-auditor'])
        self.assertEqual(self.test_runs, 1)
        self.assertEqual((self.root / 'assets/feature.txt').read_text(), 'preserved accessibility')

    def test_read_only_preflight_does_not_accept_changed_product(self):
        (self.root / 'assets').mkdir()
        product = self.root / 'assets/feature.txt'
        product.write_text('reviewed')
        baseline = forge.git('rev-parse', 'HEAD').stdout.strip()
        forge.save_checkpoint(1, {'baseline':baseline, 'stages':{'manual_resume':{'fingerprint':forge.change_snapshot(baseline)[1]}}})
        self.assertTrue(forge.task_preflight(1)[2])
        product.write_text('unreviewed')
        with self.assertRaisesRegex(forge.MaintenanceRequired, 'not validated'):
            forge.task_preflight(1)
        self.assertEqual(self.conn.execute('SELECT attempts FROM tasks WHERE id=1').fetchone()[0], 0)

    def test_infrastructure_added_during_audit_blocks_commit(self):
        head = forge.git('rev-parse', 'HEAD').stdout
        def report(*args, **kwargs):
            result = self.fake_report(*args, **kwargs)
            if args[2] == 'cendavo-auditor':
                (self.root / 'scripts').mkdir()
                (self.root / 'scripts/forge.py').write_text('unrelated maintenance')
            return result
        with patch.object(forge, 'claude_report', side_effect=report), patch.object(forge, 'tests', side_effect=self.fake_tests):
            with self.assertRaises(forge.MaintenanceRequired):
                forge.run_task(self.conn, self.row, self.deadline)
        self.assertEqual(forge.git('rev-parse', 'HEAD').stdout, head)

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
        def limited(task_id, name, agent, prompt, deadline, writable=False, frontend=False, design_plugin=None):
            if agent == 'cendavo-auditor':
                raise forge.RateLimited('limit')
            return self.fake_report(task_id, name, agent, prompt, deadline, writable, frontend, design_plugin)
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
        def limited(task_id, name, agent, prompt, deadline, writable=False, frontend=False, design_plugin=None):
            if agent == 'cendavo-auditor':
                raise forge.RateLimited('limit')
            return self.fake_report(task_id, name, agent, prompt, deadline, writable, frontend, design_plugin)
        with patch.object(forge, 'claude_report', side_effect=limited), patch.object(forge, 'tests', side_effect=self.fake_tests):
            with self.assertRaises(forge.RateLimited):
                forge.run_task(self.conn, self.row, self.deadline)
        (self.root / 'feature.txt').write_text('tampered\n')
        with self.assertRaisesRegex(RuntimeError, 'not validated'):
            self.run_pipeline()

    def test_protected_file_change_is_rejected(self):
        def tamper(task_id, name, agent, prompt, deadline, writable=False, frontend=False, design_plugin=None):
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

    def test_unit_failure_repairs_then_fresh_security_tests_and_audit(self):
        def failing_once(task_id, deadline):
            self.test_runs += 1
            if self.test_runs == 1:
                raise forge.CommandFailure('unit-tests', 1, 'mock.log', 'AssertionError: product defect')
        with patch.object(forge, 'claude_report', side_effect=self.fake_report), patch.object(forge, 'tests', side_effect=failing_once):
            forge.run_task(self.conn, self.row, self.deadline)
        self.assertEqual(self.test_runs, 2)
        self.assertEqual(self.agents_called(), ['cendavo-strategist', 'cendavo-builder',
            'cendavo-security-reviewer', 'cendavo-debugger', 'cendavo-builder',
            'cendavo-security-reviewer', 'cendavo-auditor'])

    def test_infrastructure_failure_never_calls_debugger_or_fixer(self):
        with patch.object(forge, 'claude_report', side_effect=self.fake_report), patch.object(forge, 'tests',
                side_effect=forge.CommandFailure('unit-tests', 1, 'mock.log', 'PermissionError: Operation not permitted')):
            with self.assertRaises(forge.MaintenanceRequired):
                forge.run_task(self.conn, self.row, self.deadline)
        self.assertNotIn('cendavo-debugger', self.agents_called())
        self.assertEqual(self.agents_called().count('cendavo-builder'), 1)

    def test_unit_repair_attempts_persist_and_stop_at_limit(self):
        with patch.object(forge, 'claude_report', side_effect=self.fake_report), patch.object(forge, 'tests',
                side_effect=forge.CommandFailure('unit-tests', 1, 'mock.log', 'AssertionError: defect')):
            with self.assertRaises(forge.MaintenanceRequired):
                forge.run_task(self.conn, self.row, self.deadline)
            count = len(self.calls)
            with self.assertRaises(forge.MaintenanceRequired):
                forge.run_task(self.conn, self.row, self.deadline)
        self.assertEqual(len(self.calls), count)
        self.assertEqual(self.agents_called().count('cendavo-debugger'), forge.MAX_TEST_FIXES)

    def test_repair_cannot_change_test_expectations(self):
        original = self.fake_report
        def tamper(task_id, name, agent, *args, **kwargs):
            if name.startswith('test-fix-'):
                (self.root / 'tests').mkdir()
                (self.root / 'tests' / 'test_product.py').write_text('assert True')
            return original(task_id, name, agent, *args, **kwargs)
        with patch.object(forge, 'claude_report', side_effect=tamper), patch.object(forge, 'tests',
                side_effect=forge.CommandFailure('unit-tests', 1, 'mock.log', 'AssertionError: defect')):
            with self.assertRaises(forge.SecurityFailure):
                forge.run_task(self.conn, self.row, self.deadline)
        self.assertNotIn('cendavo-auditor', self.agents_called())

    def test_unknown_diagnosis_stops_without_fix(self):
        original = self.fake_report
        def unknown(task_id, name, agent, *args, **kwargs):
            if agent == 'cendavo-debugger':
                return 'CLASSIFICATION: UNKNOWN'
            return original(task_id, name, agent, *args, **kwargs)
        with patch.object(forge, 'claude_report', side_effect=unknown), patch.object(forge, 'tests',
                side_effect=forge.CommandFailure('unit-tests', 1, 'mock.log', 'AssertionError: defect')):
            with self.assertRaises(forge.MaintenanceRequired):
                forge.run_task(self.conn, self.row, self.deadline)
        self.assertEqual(self.agents_called().count('cendavo-builder'), 1)

    def test_security_blocks_repaired_code_before_retest(self):
        self.verdicts['cendavo-security-reviewer'] = ['VERDICT: PASS', 'VERDICT: BLOCK']
        def fail(task_id, deadline):
            self.test_runs += 1
            raise forge.CommandFailure('unit-tests', 1, 'mock.log', 'AssertionError: defect')
        with patch.object(forge, 'claude_report', side_effect=self.fake_report), patch.object(forge, 'tests', side_effect=fail):
            with self.assertRaises(forge.SecurityFailure):
                forge.run_task(self.conn, self.row, self.deadline)
        self.assertEqual(self.test_runs, 1)
        self.assertNotIn('cendavo-auditor', self.agents_called())

    def test_repair_cannot_modify_checkpoint(self):
        original = self.fake_report
        def tamper(task_id, name, agent, *args, **kwargs):
            if name.startswith('test-fix-'):
                forge.checkpoint_path(task_id).write_text('{}')
            return original(task_id, name, agent, *args, **kwargs)
        with patch.object(forge, 'claude_report', side_effect=tamper), patch.object(forge, 'tests',
                side_effect=forge.CommandFailure('unit-tests', 1, 'mock.log', 'AssertionError: defect')):
            with self.assertRaises(forge.SecurityFailure):
                forge.run_task(self.conn, self.row, self.deadline)
        self.assertNotIn('cendavo-auditor', self.agents_called())

    def test_build_failure_does_not_trigger_unit_repair(self):
        with patch.object(forge, 'claude_report', side_effect=self.fake_report), patch.object(forge, 'tests',
                side_effect=forge.CommandFailure('build', 1, 'mock.log', 'build failed')):
            with self.assertRaises(forge.CommandFailure):
                forge.run_task(self.conn, self.row, self.deadline)
        self.assertNotIn('cendavo-debugger', self.agents_called())


class SubscriptionCallTests(IsolatedAgentTests):
    def test_estimates_do_not_enforce_dollar_caps(self):
        with patch.object(forge, 'REPORTS', forge.STATE), patch.object(forge, 'run_command',
                return_value='{"result":"ok","total_cost_usd":99}') as command:
            for _ in range(12):
                self.assertEqual(forge.claude_report(1, 'debug', 'cendavo-debugger', 'diagnose', time.monotonic()+60), 'ok')
            self.assertEqual(command.call_count, 12)
            self.assertNotIn('--max-budget-usd', command.call_args.args[0])
            reports = list(forge.STATE.glob('0001-debug-*.json'))
            self.assertEqual(json.loads(reports[0].read_text())['usage']['total_cost_usd'], 99)

    def test_limit_stops_even_successful_response(self):
        for result in ('Usage limit reached', "You've hit your limit", 'Quota exceeded'):
            with self.subTest(result=result), patch.object(forge, 'run_command', return_value=json.dumps({'result':result})):
                with self.assertRaises(forge.RateLimited):
                    forge.claude_report(1, 'debug', 'cendavo-debugger', 'diagnose', time.monotonic()+60)

    def test_auth_failure_prevents_call(self):
        with patch.object(forge, 'check_subscription_auth', return_value='Subscription required'), patch.object(forge, 'run_command') as command:
            with self.assertRaisesRegex(RuntimeError, 'Subscription required'):
                forge.claude_report(1, 'debug', 'cendavo-debugger', 'diagnose', time.monotonic()+60)
            command.assert_not_called()

    def test_repair_tool_scope(self):
        with patch.object(forge, 'REPAIR_MODE', True):
            argv = forge.claude_argv('cendavo-builder', True)
        allowed = argv[argv.index('--allowedTools')+1]
        self.assertIn('Edit(assets/**)', allowed)
        self.assertNotIn(',Edit,', allowed)
        self.assertIn('Edit(tests/**)', argv[argv.index('--disallowedTools')+1])


class SubscriptionAuthTests(unittest.TestCase):
    def test_requires_verified_max_subscription(self):
        valid = dict(loggedIn=True, authMethod='claude.ai', apiProvider='firstParty', subscriptionType='max')
        cases = [({}, True), ({'loggedIn':False}, False), ({'authMethod':'oauth_token'}, False),
                 ({'authMethod':'api_key'}, False), ({'apiProvider':'bedrock'}, False),
                 ({'subscriptionType':None}, False)]
        for changes, accepted in cases:
            with self.subTest(changes=changes), patch.object(forge.subprocess, 'run',
                    return_value=subprocess.CompletedProcess([], 0, json.dumps(valid | changes), '')) as run:
                self.assertEqual(forge.check_subscription_auth() is None, accepted)
                self.assertIn('--restricted', run.call_args.args[0])

    def test_removes_billing_and_routing_overrides(self):
        keys = ('ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN', 'ANTHROPIC_BASE_URL',
                'CLAUDE_CODE_USE_BEDROCK', 'CLAUDE_CODE_USE_VERTEX', 'CLAUDE_CODE_OAUTH_TOKEN',
                'CLAUDE_CONFIG_DIR', 'CLAUDE_AGENT_SDK_OAUTH_TOKEN', 'FALLBACK_FOR_ALL_PRIMARY_MODELS')
        with patch.dict(os.environ, dict.fromkeys(keys, 'mock-value')):
            env = forge.subscription_env()
        for key in keys:
            self.assertNotIn(key, env)
        self.assertEqual(json.loads(forge.subscription_flags()[-1])['forceLoginMethod'], 'claudeai')


class RunnerStopTests(unittest.TestCase):
    def run_main(self, exc, extra_args=()):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            with patch.multiple(forge, STATE=state, DB=state/'queue.sqlite3', REPORTS=state/'reports', LOGS=state/'logs', STOP=state/'STOP',
                                ACTIVE=state/'active.json'):
                conn = forge.ensure_state()
                forge.add_task(conn, 1, 'A')
                forge.add_task(conn, 2, 'B')
                conn.close()
                with patch.object(forge, 'check_tools', return_value=None), patch.object(forge, 'frontend_plugin_note', return_value=None), \
                        patch.object(forge, 'git', return_value=subprocess.CompletedProcess([], 0, 'test-head', '')), patch.object(forge, 'run_task', side_effect=exc) as run, patch.object(forge.time, 'sleep'), patch('sys.argv', ['forge.py', 'run', '--approve-provider-network', *extra_args]):
                    forge.main()
                conn = sqlite3.connect(state/'queue.sqlite3')
                states = dict(conn.execute('SELECT id,state FROM tasks'))
                conn.close()
                return run.call_count, states

    def test_max_tasks_stops_after_one_mock_task(self):
        calls, _ = self.run_main(None, ('--max-tasks', '1'))
        self.assertEqual(calls, 1)

    def test_nonfinite_runtime_rejected(self):
        for hours in ('nan', 'inf', '-inf'):
            with self.subTest(hours=hours), self.assertRaises(SystemExit):
                self.run_main(None, ('--hours=' + hours,))

    def test_expired_deadline_never_starts_process(self):
        with patch.object(forge, 'STOP', Path('/nonexistent-forge-stop')), patch.object(forge.subprocess, 'Popen') as process:
            with self.assertRaisesRegex(RuntimeError, 'Maximum runtime'):
                forge.run_command(['mock'], '', 1, 'mock', time.monotonic()-1)
            process.assert_not_called()

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
