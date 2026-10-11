import json
import os
import sqlite3
import sys
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts import forge


# Every test in this module runs against throwaway Forge state and a throwaway local CLI directory. The real
# .cendavo-run and .cendavo-tools are unreadable inside Forge's test sandbox, and tests must never depend on
# or modify live queue state.
_REAL_STATE = forge.STATE
_REAL_LOCAL_BIN = forge.LOCAL_BIN
_STATE_PATCH = None
_STATE_TMP = None


def setUpModule():
    global _STATE_PATCH, _STATE_TMP
    _STATE_TMP = tempfile.TemporaryDirectory()
    state = Path(_STATE_TMP.name) / 'forge-state'
    _STATE_PATCH = patch.multiple(forge, STATE=state, DB=state / 'queue.sqlite3', REPORTS=state / 'reports', LOGS=state / 'logs',
                                  STOP=state / 'STOP', ACTIVE=state / 'active-child.json', AGENTS_FILE=state / 'agents.json',
                                  LOCAL_BIN=Path(_STATE_TMP.name) / 'tools-bin')
    _STATE_PATCH.start()


def tearDownModule():
    _STATE_PATCH.stop()
    _STATE_TMP.cleanup()


def git(root, *args):
    return subprocess.run(['git', *args], cwd=root, text=True, capture_output=True, check=True).stdout


def write_config(root, data):
    (Path(root) / forge.CONFIG_NAME).write_text(json.dumps(data))


class IsolatedAgentTests(unittest.TestCase):
    """Agent-argv tests: no Git, no CLI, a throwaway workspace and the default (app) profile."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        state = Path(temporary.name)
        self.ws = state / 'workspace'
        self.ws.mkdir()
        isolated = patch.multiple(forge, ROOT=state, STATE=state, AGENTS_FILE=state/'agents.json', REPORTS=state, LOCAL_BIN=state/'bin')
        isolated.start()
        self.addCleanup(isolated.stop)
        for target, kwargs in ((forge, {'check_subscription_auth': None}),):
            for name, value in kwargs.items():
                p = patch.object(target, name, return_value=value)
                p.start()
                self.addCleanup(p.stop)
        git_mock = patch.object(forge, 'git', return_value=subprocess.CompletedProcess([], 0, '', ''))
        git_mock.start()
        self.addCleanup(git_mock.stop)
        tree = forge.use_tree(self.ws, forge.PROFILES['app'])
        tree.__enter__()
        self.addCleanup(tree.__exit__, None, None, None)


def denied(argv):
    return argv[argv.index('--disallowedTools') + 1].split(',')


def settings(argv):
    return json.loads(argv[argv.index('--settings') + 1])


class ForgeQueueTests(IsolatedAgentTests):
    def test_queue_persists_order_profiles_and_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            with patch.multiple(forge, STATE=state, DB=state/'queue.sqlite3', REPORTS=state/'reports', LOGS=state/'logs'):
                conn = forge.ensure_state()
                forge.add_task(conn, 5, 'Later')
                forge.add_task(conn, 1, 'First', 'site')
                with self.assertRaises(ValueError):
                    forge.add_task(conn, 1, 'Bad', 'everything')
                conn.close()
                again = forge.ensure_state()
                rows = again.execute('SELECT title, profile FROM tasks ORDER BY priority,id').fetchall()
                events = again.execute('SELECT COUNT(*) FROM events').fetchone()[0]
                self.assertEqual(rows, [('First', 'site'), ('Later', None)])
                self.assertEqual(events, 2)
                again.close()

    def test_existing_queue_gains_profile_column(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / 'queue.sqlite3'
            old = sqlite3.connect(db)
            old.execute('CREATE TABLE tasks (id INTEGER PRIMARY KEY, priority INTEGER NOT NULL, title TEXT NOT NULL, state TEXT NOT NULL DEFAULT "queued", attempts INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, error TEXT)')
            old.execute("INSERT INTO tasks(priority,title,created_at,updated_at) VALUES(1,'kept','x','x')")
            old.commit(); old.close()
            with patch.multiple(forge, STATE=Path(tmp), DB=db, REPORTS=Path(tmp)/'r', LOGS=Path(tmp)/'l'):
                conn = forge.ensure_state()
                self.assertEqual(conn.execute('SELECT title, profile FROM tasks').fetchall(), [('kept', None)])
                self.assertEqual(forge.task_profile(conn, 1).name, 'app')

    def test_auth_check_pauses_when_claude_missing(self):
        original = forge.shutil.which
        with patch.object(forge.shutil, 'which', side_effect=lambda name: None if name == 'claude' else original(name)), patch.object(forge, 'LOCAL_BIN', Path('/nonexistent-cendavo-bin')):
            self.assertIn('claude', forge.check_tools())

    def test_auth_check_does_not_require_codex(self):
        def fake_run(argv, **kwargs):
            self.assertNotIn('codex', argv[0])
            return subprocess.CompletedProcess(argv, 0, '{"loggedIn":true,"authMethod":"claude.ai","apiProvider":"firstParty","subscriptionType":"max"}', '')
        with patch.object(forge.shutil, 'which', return_value='/usr/bin/tool'), patch.object(forge.subprocess, 'run', side_effect=fake_run), \
                patch.object(forge, 'LOCAL_BIN', Path('/nonexistent-cendavo-bin')), patch.object(forge, 'AGENT_DIR', Path(forge.__file__).resolve().parents[1] / '.claude' / 'agents'), \
                patch.object(forge.forge_platform, 'doctor', return_value=[]):  # host compatibility has its own tests
            self.assertIsNone(forge.check_tools())

    def test_frontend_agents_discover_and_can_use_local_design_skills(self):
        with tempfile.TemporaryDirectory() as tmp:
            plugin_dir = Path(tmp) / 'insane-web-design'
            (plugin_dir / '.claude-plugin').mkdir(parents=True)
            (plugin_dir / '.claude-plugin' / 'plugin.json').write_text('{"name":"insane-web-design"}')
            for name in ('design', 'animation', '3d'):
                skill = plugin_dir / 'skills' / name / 'SKILL.md'
                skill.parent.mkdir(parents=True)
                skill.write_text(f'---\nname: {name}\ndescription: {name} guidance\n---\n# {name}\n')
            installed = [{'id':'insane-web-design@synced', 'enabled':True, 'installPath':str(plugin_dir)}]
            listed = subprocess.CompletedProcess(['claude','plugin','list','--json'], 0, json.dumps(installed), '')
            with patch.dict(os.environ, {forge.DESIGN_PLUGIN_DIR_ENV:''}), patch.object(forge, 'LOCAL_BIN', Path(tmp) / 'none'), patch.object(forge.subprocess, 'run', return_value=listed):
                plugin = forge.discover_design_plugin()
            self.assertTrue(plugin.available, plugin.detail)
            self.assertEqual(plugin.skills, ('3d', 'animation', 'design'))
            with patch.object(forge, 'run_command', return_value='{"result":"ok"}') as command:
                for writable, name, agent in ((False, 'strategy', 'cendavo-strategist'), (True, 'builder', 'cendavo-builder')):
                    forge.claude_report(7, name, agent, 'Improve the frontend', time.monotonic() + 60, writable, True, plugin)
                    argv, prompt = command.call_args.args[:2]
                    self.assertIn('Skill', argv[argv.index('--tools') + 1])
                    self.assertIn('insane-web-design:design', prompt)
                    # Agents run with --restricted, which ignores user-enabled plugins: the directory must be passed.
                    self.assertEqual(argv[argv.index('--plugin-dir'):][:2], ['--plugin-dir', str(plugin_dir.resolve())])
            with patch.dict(os.environ, {forge.DESIGN_PLUGIN_DIR_ENV:str(plugin_dir)}):
                override = forge.discover_design_plugin()
            self.assertTrue(override.explicit_load)
            with patch.object(forge, 'run_command', return_value='{"result":"ok"}') as command:
                forge.claude_report(7, 'builder-explicit', 'cendavo-builder', 'Improve the frontend', time.monotonic() + 60, True, True, override)
                argv = command.call_args.args[0]
                self.assertEqual(argv[argv.index('--plugin-dir'):][:2], ['--plugin-dir', str(plugin_dir.resolve())])

    def test_design_plugin_hooks_are_not_loaded(self):
        with tempfile.TemporaryDirectory() as tmp:
            plugin_dir = Path(tmp)
            (plugin_dir / '.claude-plugin').mkdir()
            (plugin_dir / '.claude-plugin' / 'plugin.json').write_text('{"name":"insane-web-design","hooks":{}}')
            (plugin_dir / 'hooks').mkdir()
            skill = plugin_dir / 'skills' / 'design' / 'SKILL.md'
            skill.parent.mkdir(parents=True)
            skill.write_text('# design\n')
            self.assertFalse(forge._validate_design_plugin(plugin_dir, True).available)

    def test_missing_design_plugin_does_not_claim_skill_use(self):
        missing = forge.DesignPlugin(False, 'not installed')
        with patch.object(forge, 'run_command', return_value='{"result":"ok"}') as command:
            forge.claude_report(8, 'strategy', 'cendavo-strategist', 'Improve the frontend', time.monotonic() + 60, False, True, missing)
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


class AgentPermissionTests(IsolatedAgentTests):
    def test_all_required_agents_load_inline_with_expected_tools(self):
        with patch.object(forge, 'AGENT_DIR', Path(forge.__file__).resolve().parents[1] / '.claude' / 'agents'):
            agents = forge.load_agents()
        for name in forge.REQUIRED_AGENTS:
            self.assertIn(name, agents)
        self.assertEqual(agents['cendavo-strategist']['tools'], ['Read', 'Glob', 'Grep', 'Skill'])
        for name in ('cendavo-security-reviewer', 'cendavo-auditor', 'cendavo-debugger'):
            self.assertEqual(agents[name]['tools'], ['Read', 'Glob', 'Grep'])
        self.assertIn('Bash', agents['cendavo-builder']['tools'])
        self.assertIn('Bash', agents['cendavo-maintainer']['tools'])

    def test_missing_agent_is_reported_not_silently_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, 'cendavo-strategist.md').write_text('---\nname: cendavo-strategist\ndescription: x\ntools: Read\n---\nbody')
            with patch.object(forge, 'AGENT_DIR', Path(tmp)):
                with self.assertRaisesRegex(RuntimeError, 'cendavo-builder'):
                    forge.load_agents()

    def test_reviewers_stay_read_only_independent_and_shell_free(self):
        for agent in ('cendavo-security-reviewer', 'cendavo-auditor', 'cendavo-strategist', 'cendavo-debugger'):
            argv = forge.claude_argv(agent, False)
            self.assertEqual(argv[argv.index('--tools') + 1], 'Read,Glob,Grep', agent)
            self.assertIn('--no-session-persistence', argv)
            for item in ('Bash', 'Edit', 'Write', 'mcp__*', 'Read(.env*)', 'Read(.cendavo-run/**)'):
                self.assertIn(item, denied(argv))
            self.assertNotIn('sandbox', settings(argv))
            self.assertNotIn('--resume', argv)
            self.assertFalse(any('codex' in a for a in argv))

    def test_app_builder_gets_sandboxed_shell_and_full_project_scope(self):
        argv = forge.claude_argv('cendavo-builder', True)
        tools = argv[argv.index('--tools') + 1].split(',')
        allowed = argv[argv.index('--allowedTools') + 1].split(',')
        self.assertTrue({'Read', 'Edit', 'Write', 'Bash'} <= set(tools))
        self.assertTrue({'Edit', 'Write', 'Bash'} <= set(allowed))
        deny = denied(argv)
        for rule in ('Edit(scripts/forge.py)', 'Write(forge.config.json)', 'Edit(.claude/**)', 'Edit(.github/**)',
                     'Edit(tests/test_forge.py)', 'Edit(.env*)', 'Read(.env*)', 'Bash(git push:*)', 'Bash(git commit:*)',
                     'Bash(npm publish:*)', 'Bash(wrangler:*)', 'Bash(ssh:*)', 'mcp__*'):
            self.assertIn(rule, deny)
        self.assertNotIn('Edit(tests/**)', deny)
        self.assertNotIn('Edit(scripts/**)', deny)
        box = settings(argv)['sandbox']
        self.assertTrue(box['enabled'] and box['failIfUnavailable'] and box['autoAllowBashIfSandboxed'])
        self.assertFalse(box['allowUnsandboxedCommands'])
        self.assertIn(str(Path.home()), box['filesystem']['denyRead'])
        self.assertIn(str(self.ws.resolve() / '.env'), box['filesystem']['denyRead'])
        self.assertEqual(box['filesystem']['allowWrite'], [str(self.ws.resolve())])
        self.assertEqual(box['network']['allowedDomains'], forge.DEFAULT_CONFIG['package_registries'])
        self.assertEqual(settings(argv)['forceLoginMethod'], 'claudeai')
        self.assertIn('--restricted', argv)
        self.assertEqual(argv[argv.index('--max-turns') + 1], '80')

    def test_existing_control_and_secret_files_are_write_denied_in_the_shell_sandbox(self):
        for name in ('scripts/forge.py', '.claude/agents/x.md', 'forge.config.json', 'tests/test_forge.py', '.env.local', 'src/app.py', 'tests/test_app.py'):
            path = self.ws / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('x')
        box = settings(forge.claude_argv('cendavo-builder', True))['sandbox']['filesystem']
        ws = self.ws.resolve()
        for name in ('scripts/forge.py', '.claude', 'forge.config.json', 'tests/test_forge.py', '.env.local', '.git'):
            self.assertIn(str(ws / name), box['denyWrite'], name)
        for name in ('src/app.py', 'tests/test_app.py', 'tests', 'src'):
            self.assertNotIn(str(ws / name), box['denyWrite'], name)
        self.assertIn(str(ws / '.env.local'), box['denyRead'])

    def test_site_profile_limits_files_and_network(self):
        for name in ('assets/site.js', 'tests/test_site.py', 'tests/test_other.py', 'docs/x.md', 'scripts/build_site.py', 'scripts/other.py'):
            path = self.ws / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('x')
        with forge.use_tree(self.ws, forge.PROFILES['site']):
            argv = forge.claude_argv('cendavo-builder', True)
        allowed = argv[argv.index('--allowedTools') + 1].split(',')
        self.assertIn('Edit(assets/**)', allowed)
        self.assertNotIn('Edit', allowed)
        box = settings(argv)['sandbox']
        self.assertEqual(box['network']['allowedDomains'], [])
        ws = self.ws.resolve()
        for name in ('docs', 'tests/test_other.py', 'scripts/other.py'):
            self.assertIn(str(ws / name), box['filesystem']['denyWrite'], name)
        for name in ('assets', 'tests', 'tests/test_site.py', 'scripts', 'scripts/build_site.py'):
            self.assertNotIn(str(ws / name), box['filesystem']['denyWrite'], name)

    def test_docs_profile_has_no_shell(self):
        with forge.use_tree(self.ws, forge.PROFILES['docs']):
            argv = forge.claude_argv('cendavo-builder', True)
        self.assertNotIn('Bash', argv[argv.index('--tools') + 1].split(','))
        self.assertNotIn('sandbox', settings(argv))

    def test_maintainer_shell_has_no_network_and_cannot_touch_the_live_checkout(self):
        wt = forge.maintenance_root() / 'm1'
        wt.mkdir(parents=True)
        argv = forge.claude_argv('cendavo-maintainer', True, cwd=wt)
        self.assertIn('Bash', argv[argv.index('--tools') + 1].split(','))
        for rule in (f'Read(/{forge.ROOT}/**)', f'Write(/{forge.ROOT}/**)', 'Edit(.git/**)', 'Bash(git push:*)'):
            self.assertIn(rule, denied(argv))
        box = settings(argv)['sandbox']
        self.assertEqual(box['network']['allowedDomains'], [])
        self.assertEqual(box['filesystem']['allowWrite'], [str(wt.resolve())])
        self.assertEqual(argv[argv.index('--max-turns') + 1], '60')

    def test_turn_limits_follow_configuration(self):
        write_config(forge.ROOT, {'max_turns': {'cendavo-builder': 150, 'cendavo-auditor': 12}})
        self.assertEqual(forge.claude_argv('cendavo-builder', True)[forge.claude_argv('cendavo-builder', True).index('--max-turns') + 1], '150')
        argv = forge.claude_argv('cendavo-auditor', False)
        self.assertEqual(argv[argv.index('--max-turns') + 1], '12')

    def test_builder_session_flags(self):
        first = forge.claude_argv('cendavo-builder', True, session={'id': 'abc', 'started': False})
        later = forge.claude_argv('cendavo-builder', True, session={'id': 'abc', 'started': True})
        self.assertEqual(first[first.index('--session-id') + 1], 'abc')
        self.assertEqual(later[later.index('--resume') + 1], 'abc')
        for argv in (first, later):
            self.assertNotIn('--no-session-persistence', argv)

    def test_skill_only_for_frontend_builder_and_strategist(self):
        avail = forge.DesignPlugin(True, 'ok', ('design',))
        plain = forge.claude_argv('cendavo-builder', True)
        self.assertNotIn('Skill', plain[plain.index('--tools') + 1])
        reviewer = forge.claude_argv('cendavo-auditor', False, plugin=avail, frontend=True)
        self.assertNotIn('Skill', reviewer[reviewer.index('--tools') + 1])
        front = forge.claude_argv('cendavo-builder', True, plugin=avail, frontend=True)
        self.assertIn('Skill(insane-web-design:*)', front[front.index('--allowedTools') + 1])
        self.assertNotIn('--plugin-dir', plain)
        self.assertNotIn('--plugin-dir', reviewer)
        located = forge.DesignPlugin(True, 'ok', ('design',), Path('/plugins/insane-web-design'))
        for agent, writable in (('cendavo-strategist', False), ('cendavo-builder', True)):
            argv = forge.claude_argv(agent, writable, plugin=located, frontend=True)
            self.assertEqual(argv[argv.index('--plugin-dir') + 1], '/plugins/insane-web-design')

    def test_explicit_mcp_tools_only_for_configured_agents(self):
        write_config(forge.ROOT, {'mcp_servers': {'docs': {'command': '/usr/bin/true', 'args': ['x'], 'tools': ['search', 'read_page'],
                                                           'agents': ['cendavo-builder'], 'profiles': ['app']}}})
        mcp = forge.ROOT / 'mcp.json'
        argv = forge.claude_argv('cendavo-builder', True, mcp_file=mcp)
        allowed = argv[argv.index('--allowedTools') + 1].split(',')
        self.assertIn('mcp__docs__search', allowed)
        self.assertNotIn('mcp__*', denied(argv))
        self.assertEqual(argv[argv.index('--mcp-config') + 1], str(mcp))
        self.assertIn('--strict-mcp-config', argv)
        reviewer = forge.claude_argv('cendavo-security-reviewer', False, mcp_file=mcp)
        self.assertIn('mcp__*', denied(reviewer))
        self.assertNotIn('--mcp-config', reviewer)
        with forge.use_tree(self.ws, forge.PROFILES['site']):
            site = forge.claude_argv('cendavo-builder', True, mcp_file=mcp)
        self.assertIn('mcp__*', denied(site))

    def test_configured_mcp_tools_are_added_to_the_agent_definition(self):
        """Regression (real CLI): an agent's tools list bounds its session, so configured MCP tools were unavailable."""
        write_config(forge.ROOT, {'mcp_servers': {'docs': {'command': '/usr/bin/true', 'tools': ['search'], 'agents': ['cendavo-builder']}}})
        with patch.object(forge, 'AGENT_DIR', Path(forge.__file__).resolve().parents[1] / '.claude' / 'agents'):
            agents = forge.write_agents_file()
        self.assertIn('mcp__docs__search', agents['cendavo-builder']['tools'])
        self.assertNotIn('mcp__docs__search', agents['cendavo-security-reviewer']['tools'])
        self.assertIn('mcp__docs__search', json.loads(forge.AGENTS_FILE.read_text())['cendavo-builder']['tools'])

    def test_claude_report_writes_private_mcp_config_with_only_configured_servers(self):
        write_config(forge.ROOT, {'mcp_servers': {'docs': {'command': '/usr/bin/true', 'tools': ['search']}}})
        with patch.object(forge, 'run_command', return_value='{"result":"ok"}') as command:
            forge.claude_report(3, 'builder', 'cendavo-builder', 'Build', time.monotonic() + 60, True)
        argv = command.call_args.args[0]
        path = Path(argv[argv.index('--mcp-config') + 1])
        self.assertEqual(json.loads(path.read_text()), {'mcpServers': {'docs': {'command': '/usr/bin/true', 'args': []}}})
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_agent_env_keeps_tools_inside_the_workspace(self):
        with patch.object(forge, 'run_command', return_value='{"result":"ok"}') as command:
            forge.claude_report(3, 'builder', 'cendavo-builder', 'Build', time.monotonic() + 60, True)
        env = command.call_args.kwargs['env_extra']
        self.assertEqual(env['GIT_CONFIG_GLOBAL'], '/dev/null')
        self.assertTrue(env['npm_config_cache'].startswith(str(self.ws)))
        self.assertEqual(command.call_args.kwargs['cwd'], self.ws)

    def test_writable_agents_never_run_in_the_live_checkout(self):
        with forge.use_tree(forge.ROOT, forge.PROFILES['app']), patch.object(forge, 'run_command') as command:
            with self.assertRaisesRegex(forge.SecurityFailure, 'workspace'):
                forge.claude_report(1, 'builder', 'cendavo-builder', 'Build', time.monotonic() + 60, True)
        command.assert_not_called()

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


class PolicyTests(unittest.TestCase):
    def test_profiles_scope_writes_and_never_allow_the_control_plane(self):
        app, site, docs = (forge.PROFILES[n] for n in ('app', 'site', 'docs'))
        for name in ('src/api/server.py', 'backend/db.py', 'tests/test_api.py', 'docs/API.md', 'package.json', 'README.md', 'pages/x.html'):
            self.assertTrue(forge.writable(name, app), name)
        for name in ('scripts/forge.py', 'scripts/supervisor.py', 'scripts/forge_sandbox.py', 'forge.config.json', '.claude/agents/a.md',
                     '.github/workflows/x.yml', 'CLAUDE.md', 'AGENTS.md', '.gitignore', '.env', '.env.production', 'config/secrets.json',
                     'keys/server.pem', '.git/config', '../escape.py', 'tests/test_forge.py', 'tests/test_supervisor.py', '.mcp.json'):
            for profile in (app, site, docs):
                self.assertFalse(forge.writable(name, profile), (name, profile.name))
        self.assertTrue(forge.writable('assets/site.js', site))
        self.assertTrue(forge.writable('tests/test_site.py', site))
        self.assertFalse(forge.writable('src/api.py', site))
        self.assertFalse(forge.writable('tests/test_api.py', site))
        self.assertTrue(forge.writable('docs/guide.md', docs))
        self.assertFalse(forge.writable('assets/site.js', docs))

    def test_parse_structured_findings(self):
        text = ('VERDICT: FIX\n- [code] assets/site.js:42: focus lost after render\n- [code] `src/api.py`: missing validation\n'
                '- [manual] VoiceOver pass on /demo/\n- [out-of-scope] .github/workflows/ci.yml: add a CI step\n')
        found = forge.parse_findings(text)
        self.assertEqual([f['path'] for f in found['code']], ['assets/site.js', 'src/api.py'])
        self.assertEqual(len(found['manual']), 1)
        self.assertEqual(found['out-of-scope'][0]['path'], '.github/workflows/ci.yml')

    def test_test_weakening_is_detected_for_python_and_javascript(self):
        self.assertTrue(forge.test_integrity_violations('+++ b/tests/test_a.py\n+    @unittest.skip("x")\n'))
        self.assertTrue(forge.test_integrity_violations('+++ b/src/app.test.js\n+it.skip("works", () => {})\n'))
        self.assertTrue(forge.test_integrity_violations('+++ b/tests/test_a.py\n-    def test_x(self):\n-        assert x\n'))
        self.assertFalse(forge.test_integrity_violations('+++ b/tests/test_a.py\n+    def test_y(self):\n+        assert y\n'))

    def test_sensitive_files_are_flagged_for_the_security_reviewer(self):
        prompt = forge.review_prompt('SECURITY REVIEW', 't', '+++ b/package.json\n+  "dep": "1"\n+++ b/src/a.js\n+x\n')
        self.assertIn('Sensitive files changed', prompt)
        self.assertIn('package.json', prompt)
        self.assertNotIn('Sensitive', forge.review_prompt('SECURITY REVIEW', 't', '+++ b/src/a.js\n+x\n'))


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = patch.object(forge, 'ROOT', Path(self.tmp.name))
        p.start()
        self.addCleanup(p.stop)

    def bad(self, data):
        write_config(forge.ROOT, data)
        with self.assertRaises(ValueError):
            forge.load_config()

    def test_defaults_without_a_file(self):
        cfg = forge.load_config()
        self.assertEqual(cfg['default_profile'], 'app')
        self.assertEqual(cfg['mcp_servers'], {})

    def test_limits_are_capped_and_validated(self):
        self.bad({'max_turns': {'cendavo-builder': 500}})
        self.bad({'max_turns': {'cendavo-builder': 0}})
        self.bad({'limits': {'product_repairs': 11}})
        self.bad({'limits': {'unknown': 1}})
        self.bad({'surprise': True})
        self.bad({'default_profile': 'root'})
        write_config(forge.ROOT, {'limits': {'product_repairs': 5}, 'max_turns': {'cendavo-builder': 120}})
        cfg = forge.load_config()
        self.assertEqual((cfg['limits']['product_repairs'], cfg['max_turns']['cendavo-builder']), (5, 120))

    def test_mcp_servers_must_be_local_explicit_and_credential_free(self):
        ok = {'command': 'node', 'args': ['server.js'], 'tools': ['search']}
        self.bad({'mcp_servers': {'x': dict(ok, env={'TOKEN': 'secret'})}})
        self.bad({'mcp_servers': {'x': dict(ok, url='https://example.com/mcp')}})
        self.bad({'mcp_servers': {'x': dict(ok, tools=['*'])}})
        self.bad({'mcp_servers': {'x': dict(ok, tools=[])}})
        self.bad({'mcp_servers': {'x': dict(ok, agents=['someone-else'])}})
        self.bad({'mcp_servers': {'Bad Name': ok}})
        write_config(forge.ROOT, {'mcp_servers': {'x': ok}})
        self.assertIn('x', forge.load_config()['mcp_servers'])

    def test_network_and_read_paths_cannot_open_secrets(self):
        self.bad({'package_registries': ['not a domain']})
        self.bad({'extra_read_paths': ['~/.ssh']})
        self.bad({'extra_read_paths': [str(Path.home())]})
        self.bad({'extra_read_paths': ['relative/path']})
        self.bad({'checks': [['build', 'python3 build.py']]})


class StreamTests(unittest.TestCase):
    def test_progress_lines_from_stream_json(self):
        lines = [json.dumps({'type': 'assistant', 'message': {'content': [
                    {'type': 'tool_use', 'name': 'Bash', 'input': {'command': 'npm   test'}},
                    {'type': 'tool_use', 'name': 'Edit', 'input': {'file_path': '/ws/src/app.py'}}]}}),
                 json.dumps({'type': 'result', 'result': 'done'})]
        with patch.object(forge, 'progress') as progress:
            rest = forge.stream_progress('\n'.join(lines) + '\n{"type":"assi', 5, 'builder', '/ws')
        self.assertEqual([c.args[2] for c in progress.call_args_list], ['Bash npm test', 'Edit src/app.py'])
        self.assertEqual(rest, '{"type":"assi')

    def test_result_and_rate_limit_parsing(self):
        stream = '\n'.join([json.dumps({'type': 'system'}), json.dumps({'type': 'rate_limit_event', 'rate_limit_info': {'status': 'allowed'}}),
                            json.dumps({'type': 'result', 'result': 'ok', 'session_id': 's'})])
        payload, limited = forge.parse_claude_output(stream)
        self.assertEqual((payload['result'], limited), ('ok', False))
        rejected = json.dumps({'type': 'rate_limit_event', 'rate_limit_info': {'status': 'rejected'}})
        self.assertTrue(forge.parse_claude_output(rejected + '\n' + stream)[1])

    def test_progress_is_written_privately(self):
        forge.STATE.mkdir(parents=True, exist_ok=True)
        with patch('builtins.print'):
            forge.progress(9, 'builder', 'Bash npm test')
        path = forge.STATE / 'progress.jsonl'
        self.assertEqual(json.loads(path.read_text().splitlines()[-1])['detail'], 'Bash npm test')
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)


class SubscriptionCallTests(IsolatedAgentTests):
    def test_estimates_do_not_enforce_dollar_caps(self):
        with patch.object(forge, 'run_command', return_value='{"result":"ok","total_cost_usd":99}') as command:
            for _ in range(12):
                self.assertEqual(forge.claude_report(1, 'debug', 'cendavo-debugger', 'diagnose', time.monotonic()+60), 'ok')
            self.assertEqual(command.call_count, 12)
            self.assertNotIn('--max-budget-usd', command.call_args.args[0])
            reports = list(forge.STATE.glob('0001-debug-*.json'))
            self.assertEqual(json.loads(reports[0].read_text())['usage']['total_cost_usd'], 99)

    def test_limit_stops_short_limit_responses(self):
        for result in ('Usage limit reached', "You've hit your limit", 'Quota exceeded'):
            with self.subTest(result=result), patch.object(forge, 'run_command', return_value=json.dumps({'result':result})):
                with self.assertRaises(forge.RateLimited):
                    forge.claude_report(1, 'debug', 'cendavo-debugger', 'diagnose', time.monotonic()+60)

    def test_long_report_mentioning_rate_limits_is_not_a_provider_limit(self):
        report = 'Implemented API rate limiting middleware. ' + 'Details. ' * 60
        with patch.object(forge, 'run_command', return_value=json.dumps({'type': 'result', 'result': report})):
            self.assertEqual(forge.claude_report(1, 'debug', 'cendavo-debugger', 'diagnose', time.monotonic()+60), report)

    def test_auth_failure_prevents_call(self):
        with patch.object(forge, 'check_subscription_auth', return_value='Subscription required'), patch.object(forge, 'run_command') as command:
            with self.assertRaisesRegex(RuntimeError, 'Subscription required'):
                forge.claude_report(1, 'debug', 'cendavo-debugger', 'diagnose', time.monotonic()+60)
            command.assert_not_called()


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


class PipelineTests(unittest.TestCase):
    """Drive run_task in a throwaway repo: real Git workspaces, delivery and guards; Claude and the test sandbox mocked."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name).resolve()
        self.root = base / 'repo'
        self.root.mkdir()
        self.state = base / 'state'
        for cmd in (['init', '-q', '-b', 'main'], ['config', 'user.email', 't@example.com'], ['config', 'user.name', 'T']):
            git(self.root, *cmd)
        (self.root / 'README.md').write_text('hi\n')
        (self.root / 'scripts').mkdir()
        (self.root / 'scripts' / 'forge.py').write_text('# control plane\n')
        (self.root / 'tests').mkdir()
        (self.root / 'tests' / 'test_existing.py').write_text('def test_a():\n    assert True\n')
        git(self.root, 'add', '.')
        git(self.root, 'commit', '-qm', 'init')
        self.patches = [patch.multiple(forge, ROOT=self.root, STATE=self.state, DB=self.state/'queue.sqlite3', REPORTS=self.state/'reports',
                                       LOGS=self.state/'logs', STOP=self.state/'STOP', ACTIVE=self.state/'active.json',
                                       AGENTS_FILE=self.state/'agents.json'),
                        patch.object(forge, 'discover_design_plugin', return_value=forge.DesignPlugin(False, 'test: not installed')),
                        patch('builtins.print')]
        for p in self.patches:
            p.start()
        self.conn = forge.ensure_state()
        forge.add_task(self.conn, 1, 'Add a feature')
        self.row = (1, 1, 'Add a feature', 0)
        self.calls = []
        self.sessions = []
        self.verdicts = {'cendavo-security-reviewer': ['VERDICT: PASS'], 'cendavo-auditor': ['VERDICT: PASS']}
        self.test_runs = 0
        self.deadline = forge.time.monotonic() + 3600
        self.build = self.write_feature

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.conn.close()
        self.tmp.cleanup()

    def ws(self):
        return forge.task_workspace(1)

    def write_feature(self, ws):
        (ws / 'src').mkdir(exist_ok=True)
        (ws / 'src' / 'feature.py').write_text(f'VALUE = {len(self.calls)}\n')

    def fake_report(self, task_id, name, agent, prompt, deadline, writable=False, frontend=False, design_plugin=None, cwd=None, session=None):
        self.calls.append((name, agent, prompt))
        if agent == 'cendavo-strategist':
            return 'DECISION: APPROVE\nBUILDER BRIEF: add src/feature.py'
        if agent == 'cendavo-debugger':
            return getattr(self, 'diagnosis', 'CLASSIFICATION: PRODUCT\nFix src/feature.py')
        if agent == 'cendavo-builder':
            self.sessions.append(dict(session or {}))
            with forge.agent_guard():
                self.build(forge.tree())
            return 'done'
        queue = self.verdicts[agent]
        return queue.pop(0) if len(queue) > 1 else queue[0]

    def fake_tests(self, task_id, deadline, root=None):
        self.test_runs += 1

    def run_pipeline(self):
        with patch.object(forge, 'claude_report', side_effect=self.fake_report), patch.object(forge, 'tests', side_effect=self.fake_tests):
            return forge.run_task(self.conn, self.row, self.deadline)

    def agents_called(self):
        return [a for _, a, _ in self.calls]

    def live_log(self):
        return git(self.root, 'log', '--format=%s')

    def state_of(self):
        return self.conn.execute('SELECT state FROM tasks WHERE id=1').fetchone()[0]

    # --- happy path and delivery ---------------------------------------------------------------
    def test_full_pipeline_builds_in_workspace_and_fast_forwards_live_branch(self):
        head = git(self.root, 'rev-parse', 'HEAD').strip()
        self.run_pipeline()
        self.assertEqual(self.agents_called(), ['cendavo-strategist', 'cendavo-builder', 'cendavo-security-reviewer', 'cendavo-auditor'])
        self.assertEqual(self.test_runs, 1)
        self.assertIn('Forge: Add a feature', self.live_log())
        self.assertEqual(git(self.root, 'rev-parse', 'HEAD~1').strip(), head)  # fast-forward: no merge commit
        self.assertTrue((self.root / 'src' / 'feature.py').exists())
        self.assertEqual(git(self.root, 'status', '--porcelain'), '')
        self.assertFalse(self.ws().exists())
        self.assertNotIn('forge-task/0001', git(self.root, 'branch'))
        self.assertEqual(self.state_of(), 'completed')
        self.assertFalse(forge.checkpoint_path(1).exists())

    def test_app_profile_builds_backend_tests_and_docs_without_approval(self):
        def full_stack(ws):
            for name, body in (('backend/api.py', 'def handler():\n    return 200\n'), ('tests/test_api.py', 'def test_h():\n    assert True\n'),
                               ('docs/API.md', '# API\n'), ('package.json', '{"name":"app"}\n'), ('README.md', 'hi\nusage\n')):
                (ws / name).parent.mkdir(parents=True, exist_ok=True)
                (ws / name).write_text(body)
        self.build = full_stack
        self.run_pipeline()
        self.assertEqual(self.state_of(), 'completed')
        for name in ('backend/api.py', 'tests/test_api.py', 'docs/API.md', 'package.json'):
            self.assertTrue((self.root / name).exists(), name)
        security_prompt = next(p for n, a, p in self.calls if a == 'cendavo-security-reviewer')
        self.assertIn('Sensitive files changed', security_prompt)

    def test_reviewers_never_see_builder_report_and_get_the_diff(self):
        self.run_pipeline()
        for name, agent, prompt in self.calls:
            if agent in ('cendavo-security-reviewer', 'cendavo-auditor'):
                self.assertIn('feature.py', prompt)
                self.assertNotIn('Builder report', prompt)
                self.assertIn('[manual]', prompt)  # structured findings format with the Builder's scope

    def test_builder_calls_share_one_resumable_session(self):
        self.verdicts['cendavo-auditor'] = ['VERDICT: FIX\n- [code] src/feature.py: wrong value', 'VERDICT: PASS']
        self.run_pipeline()
        self.assertEqual(len(self.sessions), 2)
        self.assertEqual(self.sessions[0]['id'], self.sessions[1]['id'])
        self.assertEqual([s['started'] for s in self.sessions], [False, True])

    def test_live_branch_moved_keeps_validated_commit_on_task_branch(self):
        def advance(ws):
            self.write_feature(ws)
            (self.root / 'NOTES.md').write_text('owner work\n')
            git(self.root, 'add', 'NOTES.md')
            git(self.root, '-c', 'user.name=O', '-c', 'user.email=o@x', 'commit', '-qm', 'owner commit')
        self.build = advance
        with self.assertRaises(forge.SecurityFailure):  # the agent guard sees the live checkout change
            self.run_pipeline()
        self.assertNotIn('Forge: Add a feature', self.live_log())

    def test_delivery_refuses_when_live_moved_and_resumes_later(self):
        original = forge.deliver
        def moved(conn, task_id, baseline, commit):
            (self.root / 'NOTES.md').write_text('owner work\n')
            git(self.root, 'add', 'NOTES.md')
            git(self.root, 'commit', '-qm', 'owner commit')
            return original(conn, task_id, baseline, commit)
        with patch.object(forge, 'deliver', side_effect=moved):
            with self.assertRaisesRegex(forge.MaintenanceRequired, 'kept on forge-task/0001'):
                self.run_pipeline()
        self.assertNotIn('Forge: Add a feature', self.live_log())
        self.assertIn('Forge: Add a feature', git(self.root, 'log', '--format=%s', 'forge-task/0001'))
        git(self.root, 'reset', '-q', '--hard', 'HEAD~1')  # owner undoes their commit
        calls = len(self.calls)
        self.run_pipeline()  # resumes straight into delivery, no agents
        self.assertEqual(len(self.calls), calls)
        self.assertIn('Forge: Add a feature', self.live_log())
        self.assertEqual(self.state_of(), 'completed')

    def test_dirty_live_checkout_blocks_before_any_agent(self):
        (self.root / 'stray.txt').write_text('owner edit\n')
        with self.assertRaisesRegex(forge.MaintenanceRequired, 'uncommitted'):
            self.run_pipeline()
        self.assertEqual(self.calls, [])
        self.assertEqual(self.conn.execute('SELECT attempts FROM tasks WHERE id=1').fetchone()[0], 0)

    def test_strategist_rejection_discards_workspace(self):
        def reject(task_id, name, agent, *a, **k):
            self.calls.append((name, agent, ''))
            return 'DECISION: REJECT\nNo customer evidence'
        with patch.object(forge, 'claude_report', side_effect=reject):
            forge.run_task(self.conn, self.row, self.deadline)
        self.assertEqual(self.agents_called(), ['cendavo-strategist'])
        self.assertEqual(self.state_of(), 'rejected')
        self.assertFalse(self.ws().exists())

    def test_discard_rolls_back_workspace_only(self):
        with patch.object(forge, 'claude_report', side_effect=forge.RateLimited('limit')), patch.object(forge, 'tests', side_effect=self.fake_tests):
            with self.assertRaises(forge.RateLimited):
                forge.run_task(self.conn, self.row, self.deadline)
        self.assertTrue(self.ws().exists())
        head = git(self.root, 'rev-parse', 'HEAD')
        forge.discard_workspace(1)
        self.assertFalse(self.ws().exists())
        self.assertNotIn('forge-task/0001', git(self.root, 'branch'))
        self.assertEqual(git(self.root, 'rev-parse', 'HEAD'), head)

    # --- permission enforcement ------------------------------------------------------------------
    def assert_blocked(self, build, pattern):
        self.build = build
        head = git(self.root, 'rev-parse', 'HEAD')
        with self.assertRaisesRegex(forge.SecurityFailure, pattern):
            self.run_pipeline()
        self.assertEqual(self.test_runs, 0)
        self.assertEqual(git(self.root, 'rev-parse', 'HEAD'), head)
        self.assertEqual(git(self.root, 'status', '--porcelain'), '')

    def test_control_plane_changes_are_security_failures(self):
        for name in ('scripts/forge.py', '.claude/agents/x.md', 'forge.config.json', '.github/workflows/ci.yml', '.gitignore', '.env', 'CLAUDE.md'):
            with self.subTest(name=name):
                self.tearDown(); self.setUp()
                def tamper(ws, name=name):
                    (ws / name).parent.mkdir(parents=True, exist_ok=True)
                    (ws / name).write_text('evil')
                self.assert_blocked(tamper, 'protected|permission profile|control files')

    def test_site_profile_rejects_backend_changes(self):
        self.conn.execute('UPDATE tasks SET profile="site" WHERE id=1'); self.conn.commit()
        self.assert_blocked(lambda ws: ((ws / 'src').mkdir(), (ws / 'src' / 'api.py').write_text('x')), "'site' permission profile")

    def test_writes_to_the_live_checkout_are_security_failures(self):
        self.build = lambda ws: (self.root / 'README.md').write_text('escaped')
        with self.assertRaisesRegex(forge.SecurityFailure, 'live checkout'):
            self.run_pipeline()

    def test_checkpoint_tampering_is_a_security_failure(self):
        self.build = lambda ws: (self.write_feature(ws), forge.checkpoint_path(1).write_text('{}'))
        with self.assertRaisesRegex(forge.SecurityFailure, 'checkpoints'):
            self.run_pipeline()

    def test_test_weakening_is_a_security_failure(self):
        self.assert_blocked(lambda ws: (ws / 'tests' / 'test_existing.py').write_text('import unittest\n@unittest.skip("x")\ndef test_a():\n    pass\n'),
                            'weakens tests')

    def test_symlinks_are_refused(self):
        self.assert_blocked(lambda ws: (ws / 'link').symlink_to('/etc/hosts'), 'Symlinks')

    def test_unvalidated_workspace_changes_are_refused(self):
        ws = forge.ensure_workspace(1)
        (ws / 'stray.py').write_text('manual edit\n')
        with self.assertRaisesRegex(forge.MaintenanceRequired, 'not validated'):
            self.run_pipeline()
        self.assertEqual(self.calls, [])

    # --- review gates ----------------------------------------------------------------------------
    def test_security_block_stops_before_tests_and_commit(self):
        self.verdicts['cendavo-security-reviewer'] = ['VERDICT: BLOCK exfiltration']
        with self.assertRaises(forge.SecurityFailure):
            self.run_pipeline()
        self.assertEqual(self.test_runs, 0)
        self.assertNotIn('cendavo-auditor', self.agents_called())
        self.assertNotIn('Forge:', self.live_log())

    def test_security_fix_then_retest_and_audit_on_fixed_change(self):
        self.verdicts['cendavo-security-reviewer'] = ['VERDICT: FIX\n- [code] src/feature.py: unsafe', 'VERDICT: PASS']
        self.run_pipeline()
        self.assertEqual(self.agents_called().count('cendavo-builder'), 2)
        self.assertEqual(self.agents_called().count('cendavo-security-reviewer'), 2)
        self.assertEqual(self.test_runs, 1)

    def test_security_fix_outside_builder_scope_stops_for_owner(self):
        self.verdicts['cendavo-security-reviewer'] = ['VERDICT: FIX\n- [code] .github/workflows/ci.yml: pin actions']
        with self.assertRaisesRegex(forge.SecurityFailure, 'outside the Builder'):
            self.run_pipeline()
        self.assertEqual(self.agents_called().count('cendavo-builder'), 1)

    def test_audit_fix_reruns_security_and_tests_with_only_code_findings(self):
        self.verdicts['cendavo-auditor'] = ['VERDICT: FIX\n- [code] src/feature.py: off by one\n- [manual] VoiceOver pass', 'VERDICT: PASS']
        self.run_pipeline()
        self.assertEqual(self.agents_called().count('cendavo-security-reviewer'), 2)
        self.assertEqual(self.test_runs, 2)
        fix_prompt = next(p for n, a, p in self.calls if n == 'audit-fix-1')
        self.assertIn('off by one', fix_prompt)
        self.assertNotIn('VoiceOver', fix_prompt)

    def test_audit_never_demands_out_of_scope_or_manual_work(self):
        """Regression for Task 2: repeated FIX verdicts that only the owner could satisfy."""
        self.verdicts['cendavo-auditor'] = ['VERDICT: FIX\n- [out-of-scope] .github/workflows/ci.yml: add accessibility CI\n'
                                            '- [code] CLAUDE.md: document the change\n- [manual] Keyboard-only pass of /demo/']
        self.run_pipeline()
        self.assertEqual(self.state_of(), 'completed')
        self.assertEqual(self.agents_called().count('cendavo-builder'), 1)
        followups = (self.state / 'followups' / 'task-0001.md').read_text()
        for text in ('Keyboard-only pass', 'accessibility CI', 'CLAUDE.md'):
            self.assertIn(text, followups)
        kinds = [k for (k,) in self.conn.execute('SELECT kind FROM events WHERE task_id=1')]
        self.assertIn('audit_followups', kinds)

    def test_fix_retries_are_bounded_by_configuration(self):
        write_config(self.root, {'limits': {'review_cycles': 2}})
        git(self.root, 'add', forge.CONFIG_NAME); git(self.root, 'commit', '-qm', 'config')
        self.verdicts['cendavo-auditor'] = ['VERDICT: FIX\n- [code] src/feature.py: still broken']
        with self.assertRaisesRegex(RuntimeError, 'cycle limit'):
            self.run_pipeline()
        self.assertLessEqual(self.agents_called().count('cendavo-builder'), 1 + 2)

    def test_malformed_verdict_fails_closed(self):
        self.verdicts['cendavo-security-reviewer'] = ['Looks good to me']
        with self.assertRaisesRegex(RuntimeError, 'verdict missing'):
            self.run_pipeline()
        self.assertEqual(self.test_runs, 0)

    # --- interruption and checkpoints --------------------------------------------------------------
    def limited_at(self, agent_name):
        def limited(task_id, name, agent, *args, **kwargs):
            if agent == agent_name:
                raise forge.RateLimited('limit')
            return self.fake_report(task_id, name, agent, *args, **kwargs)
        return limited

    def test_interruption_reuses_validated_stages(self):
        with patch.object(forge, 'claude_report', side_effect=self.limited_at('cendavo-auditor')), patch.object(forge, 'tests', side_effect=self.fake_tests):
            with self.assertRaises(forge.RateLimited):
                forge.run_task(self.conn, self.row, self.deadline)
        first = list(self.agents_called())
        self.assertEqual(first, ['cendavo-strategist', 'cendavo-builder', 'cendavo-security-reviewer'])
        self.run_pipeline()
        self.assertEqual(self.agents_called()[len(first):], ['cendavo-auditor'])
        self.assertEqual(self.test_runs, 1)
        self.assertEqual(self.state_of(), 'completed')

    def test_edit_after_validation_invalidates_checkpoint(self):
        with patch.object(forge, 'claude_report', side_effect=self.limited_at('cendavo-auditor')), patch.object(forge, 'tests', side_effect=self.fake_tests):
            with self.assertRaises(forge.RateLimited):
                forge.run_task(self.conn, self.row, self.deadline)
        (self.ws() / 'src' / 'feature.py').write_text('tampered\n')
        with self.assertRaisesRegex(RuntimeError, 'not validated'):
            self.run_pipeline()

    # --- unit-test recovery ------------------------------------------------------------------------
    def failing(self, output='AssertionError: product defect', times=1, stage='unit-tests'):
        def fail(task_id, deadline, root=None):
            self.test_runs += 1
            if self.test_runs <= times:
                raise forge.CommandFailure(stage, 1, 'mock.log', output)
        return fail

    def test_unit_failure_repairs_then_fresh_security_tests_and_audit(self):
        with patch.object(forge, 'claude_report', side_effect=self.fake_report), patch.object(forge, 'tests', side_effect=self.failing()):
            forge.run_task(self.conn, self.row, self.deadline)
        self.assertEqual(self.test_runs, 2)
        self.assertEqual(self.agents_called(), ['cendavo-strategist', 'cendavo-builder', 'cendavo-security-reviewer', 'cendavo-debugger',
                                                'cendavo-builder', 'cendavo-security-reviewer', 'cendavo-auditor'])

    def test_wrong_project_test_may_be_fixed_in_app_but_not_site_profile(self):
        self.diagnosis = 'CLASSIFICATION: TEST\nThe expectation in tests/test_existing.py is wrong'
        with patch.object(forge, 'claude_report', side_effect=self.fake_report), patch.object(forge, 'tests', side_effect=self.failing()):
            forge.run_task(self.conn, self.row, self.deadline)
        self.assertEqual(self.state_of(), 'completed')
        self.tearDown(); self.setUp()
        self.conn.execute('UPDATE tasks SET profile="site" WHERE id=1'); self.conn.commit()
        self.build = lambda ws: ((ws / 'assets').mkdir(exist_ok=True), (ws / 'assets' / 'a.js').write_text(f'{len(self.calls)}'))
        self.diagnosis = 'CLASSIFICATION: TEST\nwrong expectation'
        with patch.object(forge, 'claude_report', side_effect=self.fake_report), patch.object(forge, 'tests', side_effect=self.failing()):
            with self.assertRaises(forge.MaintenanceRequired):
                forge.run_task(self.conn, self.row, self.deadline)

    def test_infrastructure_failure_never_calls_debugger_or_fixer(self):
        with patch.object(forge, 'claude_report', side_effect=self.fake_report), patch.object(forge, 'tests',
                side_effect=self.failing('PermissionError: Operation not permitted', times=99)):
            with self.assertRaises(forge.MaintenanceRequired):
                forge.run_task(self.conn, self.row, self.deadline)
        self.assertNotIn('cendavo-debugger', self.agents_called())
        self.assertEqual(self.agents_called().count('cendavo-builder'), 1)

    def test_unit_repair_attempts_persist_and_stop_at_configured_limit(self):
        with patch.object(forge, 'claude_report', side_effect=self.fake_report), patch.object(forge, 'tests', side_effect=self.failing(times=99)):
            with self.assertRaises(forge.MaintenanceRequired):
                forge.run_task(self.conn, self.row, self.deadline)
            count = len(self.calls)
            with self.assertRaises(forge.MaintenanceRequired):
                forge.run_task(self.conn, self.row, self.deadline)
        self.assertEqual(len(self.calls), count)
        self.assertEqual(self.agents_called().count('cendavo-debugger'), forge.load_config()['limits']['test_fixes'])

    def test_unknown_diagnosis_stops_without_fix(self):
        self.diagnosis = 'CLASSIFICATION: UNKNOWN'
        with patch.object(forge, 'claude_report', side_effect=self.fake_report), patch.object(forge, 'tests', side_effect=self.failing(times=99)):
            with self.assertRaises(forge.MaintenanceRequired):
                forge.run_task(self.conn, self.row, self.deadline)
        self.assertEqual(self.agents_called().count('cendavo-builder'), 1)

    def test_security_blocks_repaired_code_before_retest(self):
        self.verdicts['cendavo-security-reviewer'] = ['VERDICT: PASS', 'VERDICT: BLOCK']
        with patch.object(forge, 'claude_report', side_effect=self.fake_report), patch.object(forge, 'tests', side_effect=self.failing(times=99)):
            with self.assertRaises(forge.SecurityFailure):
                forge.run_task(self.conn, self.row, self.deadline)
        self.assertEqual(self.test_runs, 1)
        self.assertNotIn('cendavo-auditor', self.agents_called())

    def test_build_failure_does_not_trigger_unit_repair(self):
        with patch.object(forge, 'claude_report', side_effect=self.fake_report), patch.object(forge, 'tests', side_effect=self.failing('build failed', 99, 'build')):
            with self.assertRaises(forge.CommandFailure):
                forge.run_task(self.conn, self.row, self.deadline)
        self.assertNotIn('cendavo-debugger', self.agents_called())


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
                        patch.object(forge, 'git', return_value=subprocess.CompletedProcess([], 0, 'test-head', '')), patch.object(forge, 'run_task', side_effect=exc) as run, patch.object(forge.time, 'sleep'), patch('sys.argv', ['forge.py', 'run', '--approve-provider-network', *extra_args]), patch('builtins.print'):
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


class SandboxSpawnTests(unittest.TestCase):
    def test_sandboxed_children_get_a_bounded_open_file_limit(self):
        """Regression: an inherited ~1M descriptor limit made each spawn inside the sandbox ~0.14s and timed out the test stage."""
        code = 'import resource; print(resource.getrlimit(resource.RLIMIT_NOFILE)[0])'
        out = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, preexec_fn=forge.cap_open_files)
        self.assertLessEqual(int(out.stdout), forge.SANDBOX_OPEN_FILES)
        self.assertGreater(int(out.stdout), 0)

    def test_run_command_applies_the_cap_only_to_sandboxed_commands(self):
        seen = {}

        class Stop(Exception):
            pass

        def fake_popen(argv, **kwargs):
            seen[argv[0]] = kwargs.get('preexec_fn')
            raise Stop
        forge.LOGS.mkdir(parents=True, exist_ok=True)
        with patch.object(forge.subprocess, 'Popen', side_effect=fake_popen):
            for argv, tmp in ((['sandbox-exec', '-p', 'x', 'true'], forge.STATE), (['git', 'status'], None)):
                with self.assertRaises(Stop):
                    forge.run_command(argv, '', 1, 'probe', time.monotonic() + 600, sandbox_tmp=tmp)
        self.assertIs(seen['sandbox-exec'], forge.cap_open_files)
        self.assertIsNone(seen['git'])

    def test_stop_during_a_running_command_cleans_up_on_macos_and_linux(self):
        """Regression (found by JARVIS integration): on macOS a zombie-only process group answers EPERM, which escaped
        terminate_group and left the orphan marker behind, so `resume` refused."""
        forge.STATE.mkdir(parents=True, exist_ok=True)
        forge.LOGS.mkdir(parents=True, exist_ok=True)
        def stop_soon():
            time.sleep(1.5)
            forge.STOP.write_text('stop')
        threading.Thread(target=stop_soon, daemon=True).start()
        try:
            with self.assertRaisesRegex(RuntimeError, 'stopped or timed out'):
                forge.run_command([sys.executable, '-c', 'import time; time.sleep(60)'], '', 1, 'builder', time.monotonic() + 600)
        finally:
            forge.STOP.unlink(missing_ok=True)
        self.assertFalse(forge.ACTIVE.exists())

    @unittest.skipIf(os.environ.get('CENDAVO_SANDBOXED'), 'signals to process groups are restricted inside the checks sandbox')
    def test_terminate_group_treats_a_zombie_only_group_as_gone(self):
        proc = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], start_new_session=True)
        time.sleep(0.3)
        os.killpg(proc.pid, forge.signal.SIGTERM)
        time.sleep(0.3)  # exited, not yet reaped
        self.assertTrue(forge.terminate_group(proc.pid, proc))
        self.assertIsNotNone(proc.returncode)

    def test_paid_fallback_and_budget_flags_are_refused(self):
        for flag in forge.FORBIDDEN_CLAUDE_FLAGS:
            with self.assertRaisesRegex(RuntimeError, 'paid-fallback'):
                forge.run_command(['claude', '-p', flag, 'x'], '', 1, 'x', time.monotonic() + 600)


class TestStateIsolationTests(unittest.TestCase):
    def test_module_never_uses_real_forge_state_or_local_cli(self):
        self.assertNotEqual(forge.STATE, _REAL_STATE)
        for name in ('STATE', 'DB', 'REPORTS', 'LOGS', 'STOP', 'ACTIVE', 'AGENTS_FILE', 'LOCAL_BIN'):
            path = str(getattr(forge, name))
            self.assertNotIn(str(_REAL_STATE), path, name)
            self.assertNotIn(str(_REAL_LOCAL_BIN.parents[1]), path, name)

    def test_suite_passes_when_real_state_is_unreadable(self):
        """Regression for the sandboxed unit-test stage: run this module with the real state path made inaccessible."""
        if os.environ.get('CENDAVO_ISOLATION_CHILD'):
            self.skipTest('inner run')
        with tempfile.TemporaryDirectory() as tmp:
            blocked = Path(tmp) / 'blocked'
            blocked.mkdir(mode=0)
            env = dict(os.environ, CENDAVO_ISOLATION_CHILD='1', PYTHONDONTWRITEBYTECODE='1')
            code = ('import sys,unittest;from pathlib import Path;from scripts import forge;'
                    f'forge.STATE=Path({str(blocked / ".cendavo-run")!r});'
                    f'forge.LOCAL_BIN=Path({str(blocked / ".cendavo-tools" / "bin")!r});'
                    'r=unittest.main(module="tests.test_forge",argv=["x"],exit=False).result;'
                    'sys.exit(0 if r.wasSuccessful() else 1)')
            try:
                run = subprocess.run([sys.executable, '-c', code], cwd=Path(forge.__file__).resolve().parents[1],
                                     env=env, capture_output=True, text=True, timeout=240, preexec_fn=forge.cap_open_files)
            finally:
                blocked.chmod(0o700)
            self.assertEqual(run.returncode, 0, run.stderr[-2000:])


if __name__ == '__main__':
    unittest.main()
