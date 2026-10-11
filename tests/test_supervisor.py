"""Simulated-failure tests for the Forge Supervisor. No real Claude agent, sandbox or network is used."""
import json
import os
import re
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import forge, supervisor


# Every test in this module runs against a throwaway Forge state directory. The real .cendavo-run is
# unreadable inside Forge's test sandbox, and tests must never depend on or modify live queue state.
_REAL_STATE = forge.STATE
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


class ClassifyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.patch = patch.multiple(forge, STATE=self.dir, REPORTS=self.dir / 'reports')
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def stage(self, stage, log):
        path = self.dir / f'{stage}.log'
        path.write_text(log)
        return forge.StageFailure(f'{stage} exited 1; see {path}', stage, path)

    def test_sandbox_denial_on_forge_state_is_infrastructure(self):
        log = ("ERROR: test_queue (test_forge.ForgeQueueTests.test_queue)\nPermissionError: [Errno 1] Operation not permitted: "
               "'/Users/x/Documents/Cendavo/.cendavo-run/queue.sqlite3'\n")
        f = supervisor.classify(self.stage('unit-tests', log), 2)
        self.assertEqual(f.kind, supervisor.INFRA)
        self.assertIn('protected state', f.summary)

    def test_only_forge_tests_failing_is_infrastructure(self):
        f = supervisor.classify(self.stage('unit-tests', 'FAIL: test_x (test_forge.A.test_x)\n'), 2)
        self.assertEqual((f.kind, f.failing_modules), (supervisor.INFRA, ['test_forge']))

    def test_site_test_failure_is_product(self):
        log = 'FAIL: test_nav (test_site.S.test_nav)\nFAIL: test_x (test_forge.A.test_x)\n'
        self.assertEqual(supervisor.classify(self.stage('unit-tests', log), 2).kind, supervisor.PRODUCT)
        self.assertEqual(supervisor.classify(self.stage('demo-js', 'SyntaxError: Unexpected token'), 2).kind, supervisor.PRODUCT)
        self.assertEqual(supervisor.classify(self.stage('build', 'Traceback\nKeyError'), 2).kind, supervisor.PRODUCT)

    def test_other_kinds(self):
        c = lambda exc: supervisor.classify(exc, 1).kind
        self.assertEqual(c(forge.RateLimited('limit')), supervisor.LIMIT)
        self.assertEqual(c(forge.SecurityFailure('block')), supervisor.SECURITY)
        self.assertEqual(c(RuntimeError('Builder touched protected files: .claude/x')), supervisor.SECURITY)
        self.assertEqual(c(RuntimeError('Source tree has uncommitted changes that Forge has not validated.')), supervisor.HUMAN)
        self.assertEqual(c(RuntimeError('Isolated test execution requires macOS sandbox-exec on this host')), supervisor.ENVIRONMENT)
        self.assertEqual(c(RuntimeError('audit review cycle limit reached; manual resolution needed')), supervisor.PRODUCT)
        self.assertEqual(c(RuntimeError('security-1: verdict missing or malformed')), supervisor.INFRA)
        self.assertEqual(c(ValueError('???')), supervisor.HUMAN)

    def test_forge_maintenance_required_is_routed_by_its_evidence(self):
        cause = self.stage('unit-tests', 'FAIL: test_x (test_forge.A.test_x)\n')
        c = lambda *a: supervisor.classify(forge.MaintenanceRequired('stopped', *a), 2)
        self.assertEqual(c(cause, 'INFRASTRUCTURE').kind, supervisor.INFRA)
        self.assertEqual(c(cause, 'INFRASTRUCTURE').failing_modules, ['test_forge'])
        # Exhausted product repair, TEST/UNKNOWN diagnoses and unvalidated trees always go to the owner.
        for args in ((cause, 'TEST'), (cause, 'UNKNOWN'), (cause, None), ()):
            self.assertEqual(c(*args).kind, supervisor.HUMAN, args)

    def test_agent_cli_exit_is_infrastructure_not_product(self):
        for stage in ('strategy', 'builder', 'debug-1', 'test-fix-1', 'security-fix-1', 'repair-build'):
            self.assertEqual(supervisor.classify(self.stage(stage, 'error: unexpected exit'), 2).kind, supervisor.INFRA, stage)

    def test_sandbox_denied_local_cli_is_infrastructure(self):
        log = ("FAIL: test_auth (test_forge.SubscriptionAuthTests.test_auth)\nPermissionError: [Errno 1] Operation not permitted: "
               "'/Users/x/Documents/Cendavo/.cendavo-tools/node_modules/.bin/claude'\n")
        self.assertEqual(supervisor.classify(self.stage('unit-tests', log), 2).kind, supervisor.INFRA)


SAFE_PATCH = '''diff --git a/tests/test_forge.py b/tests/test_forge.py
--- a/tests/test_forge.py
+++ b/tests/test_forge.py
@@ -1,2 +1,6 @@
+def setUpModule():
+    isolate_state()
+    def test_state_is_temporary(self):
+        self.assertNotIn('.cendavo-run', str(forge.STATE))
'''


class PatchPolicyTests(unittest.TestCase):
    def test_tests_only_fix_with_regression_test_is_safe(self):
        a = supervisor.assess_patch(SAFE_PATCH)
        self.assertTrue(a.safe, a)

    def test_sandbox_or_permission_change_needs_approval(self):
        diff = SAFE_PATCH + '''diff --git a/scripts/forge.py b/scripts/forge.py
--- a/scripts/forge.py
+++ b/scripts/forge.py
@@ -1 +1 @@
-    readable.append(x)
+    profile += '(allow file-read* (subpath "/Users"))'
'''
        a = supervisor.assess_patch(diff)
        self.assertFalse(a.violations)
        self.assertTrue(any('security boundary' in r for r in a.approvals))

    def test_control_files_need_approval(self):
        for name in ('scripts/supervisor.py', '.claude/agents/cendavo-builder.md', 'CLAUDE.md', '.gitignore'):
            diff = SAFE_PATCH + f'diff --git a/{name} b/{name}\n--- a/{name}\n+++ b/{name}\n@@ -1 +1 @@\n+harmless\n'
            self.assertTrue(any(name in r for r in supervisor.assess_patch(diff).approvals), name)

    def test_test_code_gaining_process_access_needs_approval(self):
        diff = SAFE_PATCH.replace("+def setUpModule():", "+import subprocess\n+def setUpModule():")
        self.assertTrue(supervisor.assess_patch(diff).approvals)

    def test_hard_violations(self):
        cases = {
            '.env': 'diff --git a/.env b/.env\n+++ b/.env\n+KEY=1\n',
            'product': 'diff --git a/assets/demo.js b/assets/demo.js\n+++ b/assets/demo.js\n+x\n',
            'removes': SAFE_PATCH + ''.join(f'-    def test_old{i}(self):\n-        self.assertTrue(x)\n' for i in range(2)),
            'skip': SAFE_PATCH + "+    @unittest.skip('flaky')\n",
            'no regression': 'diff --git a/scripts/forge.py b/scripts/forge.py\n+++ b/scripts/forge.py\n+x = 1\n',
        }
        for label, diff in cases.items():
            self.assertTrue(supervisor.assess_patch(diff).violations, label)


class SubscriptionOnlyTests(unittest.TestCase):
    def test_billing_env_is_stripped(self):
        env = forge.subscription_env({'ANTHROPIC_API_KEY': 'k', 'ANTHROPIC_BASE_URL': 'u', 'CLAUDE_CODE_USE_BEDROCK': '1',
                                      'CLAUDE_CODE_OAUTH_TOKEN': 'sub', 'AWS_BEARER_TOKEN_BEDROCK': 'b', 'OPENAI_API_KEY': 'o',
                                      'PATH': '/bin'})
        # Local Forge is stricter than token pass-through: only the claude.ai login (checked by check_subscription_auth) is used.
        self.assertEqual(set(env), {'PATH', 'CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC'})

    def test_paid_fallback_and_budget_flags_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp, patch.multiple(forge, STOP=Path(tmp) / 'STOP'):
            for flag in forge.FORBIDDEN_CLAUDE_FLAGS:
                with self.assertRaisesRegex(RuntimeError, 'paid-fallback'):
                    forge.run_command(['claude', '-p', flag, 'x'], '', 1, 'x', forge.time.monotonic() + 600)

    def test_agent_argv_has_no_budget_flags_and_maintainer_is_contained(self):
        for agent in forge.REQUIRED_AGENTS:
            argv = forge.claude_argv(agent, agent in forge.WRITABLE_AGENTS)
            self.assertFalse(set(argv) & set(forge.FORBIDDEN_CLAUDE_FLAGS))
        m = forge.claude_argv('cendavo-maintainer', True)
        deny = m[m.index('--disallowedTools') + 1]
        for rule in ('Bash', 'Read(.env*)', 'Edit(.env*)', 'Write(.git/**)', 'Edit(.cendavo-run/**)',
                     f'Read(/{forge.ROOT}/**)', f'Edit(/{forge.ROOT}/**)', f'Write(/{forge.ROOT}/**)'):
            self.assertIn(rule, deny)
        self.assertIn('--restricted', m)
        self.assertNotIn('Skill', m[m.index('--tools') + 1])

    def test_read_only_agents_cannot_be_run_writable(self):
        with self.assertRaisesRegex(RuntimeError, 'read-only'):
            forge.claude_report(1, 'x', 'cendavo-security-reviewer', 'p', 0, writable=True)

    def test_maintainer_only_runs_in_a_maintenance_worktree(self):
        with self.assertRaisesRegex(RuntimeError, 'maintenance worktree'):
            forge.claude_report(1, 'x', 'cendavo-maintainer', 'p', 0, writable=True)
        with self.assertRaisesRegex(RuntimeError, 'maintenance worktree'):
            forge.claude_report(1, 'x', 'cendavo-builder', 'p', 0, writable=True, cwd=forge.ROOT)
        with patch.object(forge, '_claude_report', return_value='ok') as inner, self.assertRaises(forge.SecurityFailure):
            forge.claude_report(1, 'x', 'cendavo-maintainer', 'p', 0, writable=True, cwd=forge.ROOT / 'scripts')
        inner.assert_not_called()

    def test_supervisor_never_invokes_codex(self):
        source = Path(supervisor.__file__).read_text()
        self.assertNotIn("'codex'", source)


class SandboxProfileTests(unittest.TestCase):
    def test_forge_state_tools_git_env_and_supervisor_are_protected_in_test_sandbox(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, temporary = Path(tmp).resolve() / 'repo', Path(tmp).resolve() / 'sandbox-tmp'
            root.mkdir()
            temporary.mkdir()
            profile = forge.build_profile(root, temporary)
            protected = re.search(r'\(deny file-read\* file-write\* \(regex (".*?")\)\)', profile)
            pattern = re.compile(json.loads(protected.group(1)))
            for name in ('.cendavo-run/queue.sqlite3', '.cendavo-tools/node_modules/.bin/claude', '.git/config', '.env'):
                self.assertTrue(pattern.match(str(root / name)), name)
            write_denied = profile.split('(deny file-write* ')[-1]
            for name in ('scripts/supervisor.py', 'scripts/supervise.sh', 'scripts/forge.py', 'tests'):
                self.assertIn(f'"{root / name}"', write_denied, name)
            self.assertIn('(deny network*)', profile)

    def test_maintenance_worktrees_are_outside_the_sandboxed_project(self):
        self.assertNotIn(forge.ROOT, forge.maintenance_root().resolve().parents)
        self.assertEqual(forge.maintenance_root().parent, forge.ROOT.parent)


class SupervisorFlowTests(unittest.TestCase):
    """End-to-end recovery against a real temporary Git repository and real worktrees, with simulated agents."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.root = base / 'repo'
        self.root.mkdir()
        self.state = base / 'state'
        git(self.root, 'init', '-q')
        git(self.root, 'config', 'user.email', 't@example.com')
        git(self.root, 'config', 'user.name', 'T')
        (self.root / 'tests').mkdir()
        (self.root / 'tests' / 'test_existing.py').write_text('def test_a():\n    assert True\n')
        (self.root / 'README.md').write_text('hi\n')
        git(self.root, 'add', '.')
        git(self.root, 'commit', '-qm', 'init')
        self.patch = patch.multiple(forge, ROOT=self.root, STATE=self.state, DB=self.state / 'queue.sqlite3', REPORTS=self.state / 'reports',
                                    LOGS=self.state / 'logs', STOP=self.state / 'STOP', ACTIVE=self.state / 'active.json',
                                    AGENTS_FILE=self.state / 'agents.json', LOCAL_BIN=self.state / 'bin',
                                    discover_design_plugin=lambda: forge.DesignPlugin(False, 'test fixture'))
        self.patch.start()
        self.conn = forge.ensure_state()
        forge.add_task(self.conn, 1, 'Improve accessibility')
        self.calls = []
        self.main_test_failures = []   # StageFailure factories consumed by tests() on the live checkout
        self.worktree_tests_fail = False
        self.post_integration_fail = False
        self.maint_patch = self.safe_maintainer
        self.maint_verdict = 'VERDICT: PASS'
        self.reexecs = 0
        self.debugger_verdict = 'CLASSIFICATION: PRODUCT'

    def tearDown(self):
        self.patch.stop()
        self.conn.close()
        self.tmp.cleanup()

    # --- simulated agents and sandbox -------------------------------------------------
    def fake_report(self, task_id, name, agent, prompt, deadline, writable=False, frontend=False, design_plugin=None, cwd=None):
        self.calls.append((name, agent))
        if agent == 'cendavo-strategist':
            return 'DECISION: APPROVE\nBUILDER BRIEF: label the form'
        if agent == 'cendavo-builder':
            (self.root / 'pages').mkdir(exist_ok=True)
            (self.root / 'pages' / 'a11y.html').write_text(f'<label>v{len(self.calls)}</label>\n')
            return 'done'
        if agent == 'cendavo-debugger':
            return self.debugger_verdict + '\nEvidence: simulated'
        if agent == 'cendavo-maintainer':
            self.maint_patch(Path(cwd))
            return 'ROOT CAUSE: tests used real state'
        if name.startswith('maintenance-security'):
            return self.maint_verdict
        return 'VERDICT: PASS'

    def safe_maintainer(self, wt):
        (wt / 'tests' / 'test_isolation.py').write_text('def test_state_isolated():\n    assert True\n')

    def fake_tests(self, task_id, deadline, root=None):
        if root is not None:
            self.calls.append(('worktree-tests', str(root)))
            if self.worktree_tests_fail:
                raise self.failure('unit-tests', 'FAIL: test_state_isolated (test_isolation.T.test_state_isolated)')
            return
        self.calls.append(('tests', 'live'))
        if self.main_test_failures:
            raise self.main_test_failures.pop(0)()
        if self.post_integration_fail and any(n == 'worktree-tests' for n, _ in self.calls):
            self.post_integration_fail = False
            raise self.failure('unit-tests', 'FAIL: test_x (test_forge.A.test_x)')

    def failure(self, stage, log):
        path = self.state / 'logs' / f'0001-{stage}-{len(self.calls)}.log'
        path.write_text(log)
        return forge.StageFailure(f'{stage} exited 1; see {path}', stage, path, log)

    def infra(self):
        return self.failure('unit-tests', "ERROR: test_q (test_forge.Q.test_q)\nPermissionError: [Errno 1] Operation not permitted: '/x/.cendavo-run/queue.sqlite3'")

    def product(self):
        return self.failure('unit-tests', 'FAIL: test_label (test_site.S.test_label)\nAssertionError')

    def build_failure(self):
        return self.failure('build', 'Traceback (most recent call last):\nKeyError: missing page title')

    def supervise(self):
        def reexec():
            self.reexecs += 1
        with patch.object(forge, 'claude_report', side_effect=self.fake_report), patch.object(forge, 'tests', side_effect=self.fake_tests):
            return supervisor.supervise(self.conn, 1, 5, reexec=reexec)

    def agents(self):
        return [a for _, a in self.calls]

    def task_state(self):
        return self.conn.execute('SELECT state FROM tasks WHERE id=1').fetchone()[0]

    def log(self):
        return git(self.root, 'log', '--format=%s')

    # --- scenarios --------------------------------------------------------------------
    def test_clean_run_completes_without_recovery(self):
        self.supervise()
        self.assertEqual(self.task_state(), 'completed')
        self.assertNotIn('cendavo-maintainer', self.agents())

    def test_product_failure_is_repaired_and_fully_revalidated(self):
        self.main_test_failures = [self.build_failure]
        self.supervise()
        self.assertEqual(self.task_state(), 'completed')
        names = [n for n, _ in self.calls]
        self.assertIn('repair-build', names)
        # The repaired change is security-reviewed and tested again before audit and checkpoint.
        after = names[names.index('repair-build'):]
        self.assertEqual([n for n in after if n.startswith(('security-', 'tests', 'audit-'))][:3], ['security-1', 'tests', 'audit-1'])
        self.assertIn('Forge: Improve accessibility', self.log())

    def test_unit_test_product_failure_uses_forge_debugger_repair_first(self):
        """Forge's own debugger-gated repair stays the first layer; the Supervisor does not repair it a second time."""
        self.main_test_failures = [self.product]
        self.supervise()
        self.assertEqual(self.task_state(), 'completed')
        names = [n for n, _ in self.calls]
        self.assertEqual([n for n in names if n.startswith(('debug-', 'test-fix-'))], ['debug-1', 'test-fix-1'])
        self.assertFalse(any(n.startswith('repair-') for n in names))
        self.assertNotIn('cendavo-maintainer', self.agents())
        after = names[names.index('test-fix-1'):]
        self.assertEqual([n for n in after if n.startswith(('security-', 'tests', 'audit-'))][:3], ['security-1', 'tests', 'audit-1'])

    def test_debugger_non_product_diagnosis_stops_for_owner(self):
        self.main_test_failures = [self.product]
        self.debugger_verdict = 'CLASSIFICATION: TEST'
        head = git(self.root, 'rev-parse', 'HEAD')
        self.supervise()
        self.assertEqual(self.task_state(), 'interrupted')
        self.assertEqual(git(self.root, 'rev-parse', 'HEAD'), head)
        self.assertNotIn('cendavo-maintainer', self.agents())
        self.assertNotIn('test-fix-1', [n for n, _ in self.calls])

    def test_debugger_infrastructure_diagnosis_goes_to_maintenance(self):
        self.main_test_failures = [self.product]
        self.debugger_verdict = 'CLASSIFICATION: INFRASTRUCTURE'
        self.supervise()
        self.assertIn('cendavo-maintainer', self.agents())
        self.assertEqual(self.task_state(), 'completed')

    def test_product_repairs_are_bounded(self):
        self.main_test_failures = [self.build_failure] * 10
        self.supervise()
        self.assertEqual(self.task_state(), 'failed')
        self.assertEqual(sum(n.startswith('repair-') for n, _ in self.calls), supervisor.MAX_PRODUCT_REPAIRS)
        reports = list((self.state / 'supervisor' / 'reports').glob('*-product.json'))
        self.assertTrue(any('limit' in json.loads(p.read_text())['detail'] for p in reports))
        self.assertTrue((self.root / 'pages' / 'a11y.html').exists())  # work preserved for inspection

    def test_repair_that_weakens_tests_is_blocked(self):
        self.main_test_failures = [self.build_failure]
        original = self.fake_report

        def cheat(task_id, name, agent, prompt, deadline, writable=False, frontend=False, design_plugin=None, cwd=None):
            if name.startswith('repair-'):
                (self.root / 'tests' / 'test_existing.py').write_text('import unittest\n@unittest.skip("x")\ndef test_a():\n    pass\n')
                self.calls.append((name, agent))
                return 'done'
            return original(task_id, name, agent, prompt, deadline, writable, frontend, design_plugin, cwd)
        with patch.object(forge, 'claude_report', side_effect=cheat), patch.object(forge, 'tests', side_effect=self.fake_tests):
            supervisor.supervise(self.conn, 1, 5, reexec=lambda: None)
        self.assertEqual(self.task_state(), 'blocked')
        self.assertNotIn('Forge: Improve accessibility', self.log())

    def test_repair_outside_product_scope_is_a_security_stop(self):
        self.main_test_failures = [self.build_failure]
        original = self.fake_report

        def escape(task_id, name, agent, prompt, deadline, writable=False, frontend=False, design_plugin=None, cwd=None):
            if name.startswith('repair-'):
                (self.root / 'README.md').write_text('changed by repair\n')
                self.calls.append((name, agent))
                return 'done'
            return original(task_id, name, agent, prompt, deadline, writable, frontend, design_plugin, cwd)
        with patch.object(forge, 'claude_report', side_effect=escape), patch.object(forge, 'tests', side_effect=self.fake_tests):
            supervisor.supervise(self.conn, 1, 5, reexec=lambda: None)
        self.assertEqual(self.task_state(), 'blocked')

    def test_maintainer_touching_live_checkout_is_a_security_stop(self):
        self.main_test_failures = [self.infra]

        def guarded(task_id, name, agent, prompt, deadline, writable=False, frontend=False, design_plugin=None, cwd=None):
            if agent != 'cendavo-maintainer':
                return self.fake_report(task_id, name, agent, prompt, deadline, writable, frontend, design_plugin, cwd)
            self.calls.append((name, agent))
            # Exercise the real containment wrapper around a maintainer that escapes its worktree.
            with forge.maintenance_isolation(cwd):
                (self.root / 'README.md').write_text('escaped\n')
            return 'done'
        head = git(self.root, 'rev-parse', 'HEAD')
        with patch.object(forge, 'claude_report', side_effect=guarded), patch.object(forge, 'tests', side_effect=self.fake_tests):
            supervisor.supervise(self.conn, 1, 5, reexec=lambda: None)
        self.assertEqual(self.task_state(), 'blocked')
        self.assertEqual(git(self.root, 'rev-parse', 'HEAD'), head)
        rec = json.loads(next((self.state / 'supervisor' / 'maintenance').glob('*.json')).read_text())
        self.assertEqual(rec['status'], 'rejected')
        self.assertEqual(git(self.root, 'worktree', 'list').count('\n'), 1)

    def test_infrastructure_failure_safe_patch_integrates_and_resumes_from_checkpoint(self):
        self.main_test_failures = [self.infra]
        self.supervise()
        self.assertEqual(self.task_state(), 'completed')
        self.assertEqual(self.reexecs, 1)
        log = self.log()
        self.assertIn('Forge maintenance:', log)
        self.assertIn('Forge: Improve accessibility', log)
        self.assertTrue((self.root / 'tests' / 'test_isolation.py').exists())
        # Validated stages were reused: no second strategist, builder or security review after integration.
        agents = self.agents()
        i = agents.index('cendavo-maintainer')
        self.assertNotIn('cendavo-strategist', agents[i:])
        self.assertNotIn('cendavo-builder', agents[i:])
        self.assertEqual([n for n, _ in self.calls[i:] if n.startswith('security-')], [])
        self.assertEqual(agents.count('cendavo-security-reviewer'), 2)  # task review + independent patch review
        self.assertIn('worktree-tests', [n for n, _ in self.calls])
        self.assertEqual(git(self.root, 'worktree', 'list').count('\n'), 1)  # maintenance worktree cleaned up
        self.assertEqual(git(self.root, 'status', '--porcelain'), '')

    def test_security_boundary_patch_waits_for_owner_then_integrates_on_approval(self):
        self.main_test_failures = [self.infra]

        def boundary(wt):
            self.safe_maintainer(wt)
            (wt / 'scripts').mkdir(exist_ok=True)
            (wt / 'scripts' / 'fix.py').write_text("profile = '(allow file-read* (subpath \"/x\"))'\n")
        self.maint_patch = boundary
        head = git(self.root, 'rev-parse', 'HEAD')
        self.supervise()
        self.assertEqual(self.task_state(), 'interrupted')
        self.assertEqual(git(self.root, 'rev-parse', 'HEAD'), head)
        self.assertTrue((self.root / 'pages' / 'a11y.html').exists())
        pending = list((self.state / 'supervisor' / 'maintenance').glob('*.json'))
        rec = json.loads(pending[0].read_text())
        self.assertEqual(rec['status'], 'pending')
        self.assertTrue((self.state / 'supervisor' / 'patches' / f'{rec["id"]}.diff').exists())
        with patch.object(forge, 'tests', side_effect=self.fake_tests), patch('sys.stdout'):
            self.assertEqual(supervisor.main(['approve', rec['id']]), 0)
        self.assertIn('Forge maintenance:', self.log())
        self.assertEqual(self.task_state(), 'queued')

    def test_owner_rejection_leaves_checkout_untouched(self):
        self.main_test_failures = [self.infra]
        self.maint_patch = lambda wt: (self.safe_maintainer(wt), (wt / 'CLAUDE.md').write_text('x'))
        head = git(self.root, 'rev-parse', 'HEAD')
        self.supervise()
        rec = json.loads(next((self.state / 'supervisor' / 'maintenance').glob('*.json')).read_text())
        with patch('sys.stdout'):
            supervisor.main(['reject', rec['id']])
        self.assertEqual(git(self.root, 'rev-parse', 'HEAD'), head)
        self.assertEqual(json.loads(next((self.state / 'supervisor' / 'maintenance').glob('*.json')).read_text())['status'], 'rejected')

    def test_patch_that_deletes_tests_is_rejected_and_attempts_are_bounded(self):
        self.main_test_failures = [self.infra] * 5
        self.maint_patch = lambda wt: (wt / 'tests' / 'test_existing.py').unlink()
        head = git(self.root, 'rev-parse', 'HEAD')
        self.supervise()
        self.assertEqual(self.agents().count('cendavo-maintainer'), supervisor.MAX_MAINTENANCE)
        self.assertEqual(git(self.root, 'rev-parse', 'HEAD'), head)
        self.assertEqual(self.task_state(), 'interrupted')
        self.assertEqual(git(self.root, 'worktree', 'list').count('\n'), 1)

    def test_maintenance_security_block_and_failing_validation_are_rejected(self):
        for setup in ('block', 'tests'):
            with self.subTest(setup=setup):
                self.tearDown(); self.setUp()
                self.main_test_failures = [self.infra] * 5
                if setup == 'block':
                    self.maint_verdict = 'VERDICT: BLOCK reads ~/.ssh'
                else:
                    self.worktree_tests_fail = True
                head = git(self.root, 'rev-parse', 'HEAD')
                self.supervise()
                self.assertEqual(git(self.root, 'rev-parse', 'HEAD'), head)
                self.assertNotIn('Forge: Improve accessibility', self.log())

    def test_post_integration_failure_is_reverted_without_losing_task_work(self):
        self.main_test_failures = [self.infra]
        self.post_integration_fail = True
        self.supervise()
        log = self.log()
        self.assertIn('Revert "Forge maintenance:', log)
        self.assertTrue((self.root / 'pages' / 'a11y.html').exists())

    def test_provider_limit_stops_without_recovery(self):
        def limited(task_id, name, agent, *a, **k):
            raise forge.RateLimited('usage limit')
        with patch.object(forge, 'claude_report', side_effect=limited), patch.object(forge, 'tests', side_effect=self.fake_tests):
            supervisor.supervise(self.conn, 1, 5, reexec=lambda: None)
        self.assertEqual(self.task_state(), 'interrupted')
        self.assertEqual(self.conn.execute('SELECT attempts FROM tasks WHERE id=1').fetchone()[0], 0)

    def test_dirty_unvalidated_tree_stops_for_owner(self):
        (self.root / 'manual.txt').write_text('owner work\n')
        self.supervise()
        self.assertEqual(self.task_state(), 'interrupted')
        self.assertEqual(self.calls, [])
        self.assertTrue((self.root / 'manual.txt').exists())

    def test_task_history_is_preserved(self):
        self.main_test_failures = [self.infra]
        self.supervise()
        kinds = [k for (k,) in self.conn.execute('SELECT kind FROM events WHERE task_id=1 ORDER BY id')]
        for k in ('queued', 'supervisor_infrastructure', 'maintenance_started', 'maintenance_integrated', 'checkpoint'):
            self.assertIn(k, kinds)

    def test_diagnose_reads_logs_without_agents(self):
        exc = self.infra()
        forge.set_state(self.conn, 1, 'interrupted', str(exc))
        with patch.object(forge, 'claude_report', side_effect=AssertionError('no agents')):
            d = supervisor.diagnose(self.conn, 1)
        self.assertEqual(d['kind'], supervisor.INFRA)
        self.assertIn('.cendavo-run', d['evidence_tail'])


    def test_diagnose_forge_blocked_infrastructure_task_from_its_latest_log(self):
        """Mirrors a task blocked by `forge.py run`: the error text has no log path, so the latest unit-test log is used."""
        log = self.state / 'logs' / '0001-unit-tests-1791676073.log'
        log.write_text('FAIL: test_requires_verified_max_subscription (test_forge.SubscriptionAuthTests)\nAssertionError: False != True\n')
        forge.set_state(self.conn, 1, 'blocked', 'Unit-test failure involves runner/sandbox infrastructure; maintenance review required')
        with patch.object(forge, 'claude_report', side_effect=AssertionError('no agents')):
            d = supervisor.diagnose(self.conn, 1)
        self.assertEqual((d['kind'], d['stage'], d['failing_test_modules']), (supervisor.INFRA, 'unit-tests', ['test_forge']))
        self.assertEqual(d['log'], str(log))

    def test_integration_keeps_existing_checkpoint_fields_and_validated_stages(self):
        """Checkpoints written by the manual maintenance flow (extra keys, manual_resume) survive a validated integration."""
        self.main_test_failures = [self.infra]
        seen = {}
        original_integrate = supervisor.integrate

        def spy(conn, record):
            path = forge.checkpoint_path(1)
            data = json.loads(path.read_text())
            data['previous_checkpoint'] = {'baseline': 'older', 'stages': {}}
            data['stages']['manual_resume'] = {'at': 'x', 'fingerprint': data['stages']['security']['fingerprint'], 'reviewer': 'owner'}
            path.write_text(json.dumps(data))
            outcome = original_integrate(conn, record)
            seen.update(json.loads(path.read_text()))
            return outcome
        with patch.object(supervisor, 'integrate', side_effect=spy):
            self.supervise()
        self.assertEqual(self.task_state(), 'completed')
        self.assertEqual(seen['baseline'], git(self.root, 'rev-parse', 'HEAD~1').strip())  # the integrated maintenance commit
        self.assertEqual(seen['previous_checkpoint'], {'baseline': 'older', 'stages': {}})
        self.assertEqual(set(seen['stages']), {'strategy', 'build', 'security', 'manual_resume'})

if __name__ == '__main__':
    unittest.main()
