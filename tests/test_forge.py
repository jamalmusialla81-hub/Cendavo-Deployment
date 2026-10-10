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
        with patch.object(forge.shutil, 'which', return_value='/usr/bin/tool'), patch.object(forge.subprocess, 'run', side_effect=fake_run), patch.object(forge, 'LOCAL_BIN', Path('/nonexistent-cendavo-bin')):
            self.assertIsNone(forge.check_tools())

    def test_builder_command_denies_sensitive_file_tools(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(forge, 'REPORTS', Path(tmp)), patch.object(forge, 'discover_design_plugin', return_value=forge.DesignPlugin(False, 'not installed')), patch.object(forge, 'run_command', return_value='{"result":"ok"}') as command:
            self.assertEqual(forge.claude_report(1, 'builder', 'Build', time.monotonic() + 60, True), 'ok')
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
                for writable, name in ((False, 'strategy'), (True, 'builder')):
                    forge.claude_report(7, name, 'Improve the frontend', time.monotonic() + 60,
                                        writable, plugin)
                    argv, prompt = command.call_args.args[:2]
                    self.assertIn('Skill', argv[argv.index('--tools') + 1])
                    self.assertIn('insane-web-design:design', prompt)
                    self.assertIn('before implementation', prompt)
            with patch.dict(os.environ, {forge.DESIGN_PLUGIN_DIR_ENV:str(plugin_dir)}):
                override = forge.discover_design_plugin()
            self.assertTrue(override.explicit_load)
            with patch.object(forge, 'REPORTS', Path(tmp)), patch.object(forge, 'run_command', return_value='{"result":"ok"}') as command:
                forge.claude_report(7, 'builder-explicit', 'Improve the frontend',
                                    time.monotonic() + 60, True, override)
                self.assertEqual(command.call_args.args[0][-2:], ['--plugin-dir', str(plugin_dir.resolve())])

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
            forge.claude_report(8, 'strategy', 'Improve the frontend', time.monotonic() + 60,
                                False, missing)
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


if __name__ == '__main__':
    unittest.main()
