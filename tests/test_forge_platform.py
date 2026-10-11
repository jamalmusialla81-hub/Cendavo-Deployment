"""Platform abstraction: detection, sandbox backends, compatibility checks and the read-only inspect interface.

Policy tests run everywhere. Behavioural sandbox tests run only where that sandbox exists (macOS sandbox-exec,
Linux/WSL2 bubblewrap) and never inside an existing Forge sandbox.
"""
import fcntl
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from scripts import forge, forge_platform as fp

NESTED = bool(os.environ.get('CENDAVO_SANDBOXED'))
_STATE_PATCH = None
_STATE_TMP = None


def setUpModule():
    # Never touch the real .cendavo-run: every test here gets throwaway Forge state.
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


class DetectionTests(unittest.TestCase):
    def test_platform_kinds(self):
        self.assertEqual(fp.detect('Darwin', ''), 'macos')
        self.assertEqual(fp.detect('Windows', ''), 'windows')
        self.assertEqual(fp.detect('Linux', '6.8.0-45-generic'), 'linux')
        self.assertEqual(fp.detect('Linux', '5.15.153.1-microsoft-standard-WSL2'), 'wsl2')
        self.assertEqual(fp.detect('Linux', '6.6.36.3-microsoft-standard-WSL2+'), 'wsl2')
        self.assertEqual(fp.detect('Linux', '4.4.0-19041-Microsoft'), 'wsl1')

    def test_only_sandboxable_platforms_get_a_backend(self):
        self.assertIsInstance(fp.checks_sandbox('macos'), fp.MacSeatbelt)
        self.assertIsInstance(fp.checks_sandbox('linux'), fp.LinuxBubblewrap)
        self.assertIsInstance(fp.checks_sandbox('wsl2'), fp.LinuxBubblewrap)
        for kind in ('windows', 'wsl1', 'freebsd'):
            self.assertIsNone(fp.checks_sandbox(kind), kind)
            self.assertFalse(fp.check_platform(kind)['ok'])
        self.assertIn('WSL2', fp.unsupported_reason('windows'))
        self.assertIn('wsl --set-version', fp.unsupported_reason('wsl1'))

    def test_doctor_stops_at_unsupported_platform(self):
        results = fp.doctor(Path('.'), Path('.'), 'windows')
        self.assertEqual([r['check'] for r in results], ['platform'])
        self.assertTrue(fp.failures(results))


class NoUnsandboxedFallbackTests(unittest.TestCase):
    def test_checks_stage_refuses_without_a_backend(self):
        for backend in (None, type('Broken', (), {'available': lambda self: (False, 'bwrap missing'), 'name': 'bwrap'})()):
            with self.subTest(backend=backend), patch.object(fp, 'checks_sandbox', return_value=backend), \
                    patch.object(fp, 'detect', return_value='windows'), patch.object(forge, 'run_command') as run:
                with self.assertRaisesRegex(RuntimeError, 'requires a verified OS sandbox'):
                    forge.tests(1, time.monotonic() + 60, root=Path('.'))
                run.assert_not_called()

    def test_checks_stage_runs_every_check_through_the_backend(self):
        class Fake:
            name = 'bwrap'
            def available(self):
                return True, 'fake'
            def command(self, argv, root, tmp):
                return ['bwrap', '--fake', str(root), str(tmp), '--', *argv]
        with tempfile.TemporaryDirectory() as tmp, patch.object(fp, 'checks_sandbox', return_value=Fake()), \
                patch.object(forge, 'run_command') as run, patch.object(forge, 'ROOT', Path(tmp)):
            forge.tests(1, time.monotonic() + 60, root=Path(tmp))
        calls = run.call_args_list
        self.assertEqual([c.args[3] for c in calls], [n for n, _ in forge.DEFAULT_CONFIG['checks']])
        for call in calls:
            self.assertEqual(call.args[0][:2], ['bwrap', '--fake'])
            self.assertIsNotNone(call.kwargs['sandbox_tmp'])

    def test_bwrap_gets_the_same_process_handling_as_sandbox_exec(self):
        seen = {}

        class Stop(Exception):
            pass

        def fake_popen(argv, **kwargs):
            seen.update(argv=argv, **kwargs)
            raise Stop
        forge.LOGS.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as tmp, patch.object(forge.subprocess, 'Popen', side_effect=fake_popen):
            with self.assertRaises(Stop):
                forge.run_command(['bwrap', '--', 'python3', '-V'], '', 1, 'unit-tests', time.monotonic() + 600, sandbox_tmp=Path(tmp))
            with self.assertRaisesRegex(ValueError, 'private temporary'):
                forge.run_command(['bwrap', '--', 'true'], '', 1, 'x', time.monotonic() + 600)
        self.assertIs(seen['preexec_fn'], forge.cap_open_files)
        self.assertTrue(seen['start_new_session'])
        self.assertEqual((seen['env']['HOME'], seen['env']['TMPDIR'], seen['env']['CENDAVO_SANDBOXED']), (tmp, tmp, '1'))
        self.assertNotIn('PYTHONPATH', seen['env'])

    def test_preflight_refuses_an_incompatible_host(self):
        failed = [{'check': 'checks sandbox', 'ok': False, 'required': True, 'detail': 'bwrap missing'}]
        with patch.object(forge, 'write_agents_file'), patch.object(forge, 'load_config'), patch.object(forge.shutil, 'which', return_value='/x'), \
                patch.object(fp, 'doctor', return_value=failed), patch.object(forge, 'check_subscription_auth') as auth:
            issue = forge.check_tools()
        self.assertIn('not compatible', issue)
        self.assertIn('bwrap missing', issue)
        auth.assert_not_called()

    def test_main_refuses_native_windows_and_wsl1(self):
        for kind in ('windows', 'wsl1'):
            with self.subTest(kind=kind), patch.object(fp, 'detect', return_value=kind), patch('sys.argv', ['forge.py', 'status']), \
                    patch.object(forge, 'ensure_state') as state, patch('sys.stderr'):
                self.assertEqual(forge.main(), 2)
                state.assert_not_called()


class BubblewrapPolicyTests(unittest.TestCase):
    """The Linux checks profile, built on any host (no bwrap needed)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name).resolve()
        self.root, self.temp, self.home = base / 'home' / 'u' / 'Cendavo', base / 'sandbox-tmp', base / 'home' / 'u'
        for d in ('src', 'tests', 'scripts', '.claude/agents', '.cendavo-run', '.git', 'node_modules/pkg', 'deep/secrets', 'a/b'):
            (self.root / d).mkdir(parents=True, exist_ok=True)
        self.temp.mkdir()
        for f in ('.env', '.env.local', 'a/b/server.pem', 'scripts/forge.py', 'forge.config.json', 'CLAUDE.md', 'src/app.py',
                  'tests/test_app.py', 'deep/secrets/key.txt', 'node_modules/pkg/.env'):
            (self.root / f).write_text('x')
        self.argv = fp.bwrap_argv(self.root, self.temp, home=self.home)

    def pairs(self, flag):
        return [(self.argv[i + 1], self.argv[i + 2] if i + 2 < len(self.argv) else None) for i, a in enumerate(self.argv) if a == flag]

    def test_isolation_flags(self):
        for flag in ('--unshare-all', '--die-with-parent', '--new-session'):
            self.assertIn(flag, self.argv)
        self.assertEqual(self.argv[self.argv.index('--cap-drop') + 1], 'ALL')
        self.assertNotIn('--share-net', self.argv)
        self.assertEqual(self.argv[self.argv.index('--chdir') + 1], str(self.root))

    def test_only_project_and_private_tmp_are_writable(self):
        writable = [src for src, _ in self.pairs('--bind')]
        self.assertEqual(writable, [str(self.root), str(self.temp)])
        self.assertNotIn(str(self.home), [s for s, _ in self.pairs('--ro-bind')])
        self.assertFalse(any(s == str(self.home) for s, _ in self.pairs('--bind')))

    def test_protected_names_are_hidden_at_any_depth(self):
        hidden_files = [dst for src, dst in self.pairs('--ro-bind') if src == '/dev/null']
        for f in ('.env', '.env.local', 'a/b/server.pem'):
            self.assertIn(str(self.root / f), hidden_files, f)
        tmpfs = [p for p, _ in self.pairs('--tmpfs')]
        for d in ('.git', '.cendavo-run', 'deep/secrets'):
            self.assertIn(str(self.root / d), tmpfs, d)
            self.assertIn(str(self.root / d), [p for p, _ in self.pairs('--remount-ro')])
        self.assertNotIn(str(self.root / 'src/app.py'), hidden_files)

    def test_control_files_are_read_only_after_the_project_bind(self):
        project_bind = self.argv.index(str(self.root))
        for name in ('tests', 'scripts/forge.py', 'forge.config.json', 'CLAUDE.md', '.claude'):
            path = str(self.root / name)
            self.assertIn((path, path), self.pairs('--ro-bind'), name)
            self.assertGreater(self.argv.index(path), project_bind, name)
        self.assertNotIn((str(self.root / 'src'), str(self.root / 'src')), self.pairs('--ro-bind'))

    def test_temporary_directory_must_be_outside_the_project(self):
        inside = self.root / 'tmp'
        inside.mkdir()
        with self.assertRaises(ValueError):
            fp.bwrap_argv(self.root, inside, home=self.home)

    def test_tool_install_roots_never_expose_the_home_directory(self):
        nvm = self.home / '.nvm' / 'versions' / 'node' / 'v22' / 'bin'
        nvm.mkdir(parents=True)
        (nvm / 'node').write_text('#!/bin/sh\n')
        (self.home / 'bin').mkdir()
        (self.home / 'bin' / 'git').write_text('#!/bin/sh\n')
        found = {'node': str(nvm / 'node'), 'git': str(self.home / 'bin' / 'git'), 'python3': '/usr/bin/python3'}
        with patch.object(fp.shutil, 'which', side_effect=lambda n: found.get(n)), patch.object(fp.sys, 'executable', '/usr/bin/python3'):
            roots = fp._tool_roots(self.home)
        self.assertEqual(roots, [self.home.resolve() / '.nvm' / 'versions' / 'node' / 'v22'])

    def test_system_symlinks_are_recreated_not_followed(self):
        with patch.object(fp, 'SYSTEM_DIRS', ('/usr', str(self.root / 'linkbin'))):
            (self.root / 'linkbin').symlink_to('usr/bin')
            argv = fp.bwrap_argv(self.root, self.temp, home=self.home)
        i = argv.index('--symlink')
        self.assertEqual(argv[i + 1:i + 3], ['usr/bin', str(self.root / 'linkbin')])


class CompatibilityCheckTests(unittest.TestCase):
    def test_wsl_projects_on_windows_drives_are_refused(self):
        result = fp.check_filesystem(Path('/mnt/c/Users/me/Cendavo'), 'wsl2')
        self.assertFalse(result['ok'])
        self.assertIn('WSL2 Linux filesystem', result['detail'])

    def test_case_insensitive_names_are_refused_on_linux_but_accepted_on_macos(self):
        with tempfile.TemporaryDirectory() as tmp:
            sensitive = fp.check_filesystem(Path(tmp), 'macos')
            self.assertTrue(sensitive['ok'], sensitive)
            with patch.object(Path, 'exists', lambda self: self.name == 'case' or os.path.exists(self)):
                linux = fp.check_filesystem(Path(tmp), 'linux')
                mac = fp.check_filesystem(Path(tmp), 'macos')
        self.assertFalse(linux['ok'])
        self.assertIn('case-insensitive', linux['detail'])
        self.assertTrue(mac['ok'])

    def test_ignored_permissions_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(Path, 'chmod', lambda self, mode: None), \
                patch.object(Path, 'write_text', lambda self, t: os.close(os.open(self, os.O_CREAT | os.O_WRONLY, 0o644)) or len(t)):
            result = fp.check_filesystem(Path(tmp), 'linux')
        self.assertFalse(result['ok'])
        self.assertIn('chmod', result['detail'])

    def test_linux_agent_sandbox_needs_bubblewrap_and_socat(self):
        with patch.object(fp.shutil, 'which', side_effect=lambda n: None if n == 'socat' else '/usr/bin/' + n):
            result = fp.check_agent_sandbox('wsl2')
        self.assertFalse(result['ok'])
        self.assertIn('apt install socat', result['detail'])
        with patch.object(fp.shutil, 'which', return_value='/usr/bin/x'):
            self.assertTrue(fp.check_agent_sandbox('linux')['ok'])

    def test_bubblewrap_without_user_namespaces_is_unavailable(self):
        denied = subprocess.CompletedProcess([], 1, '', 'bwrap: No permissions to creating new namespace')
        with patch.object(fp.shutil, 'which', return_value='/usr/bin/bwrap'), patch.object(fp.subprocess, 'run', return_value=denied):
            ok, detail = fp.LinuxBubblewrap().available()
        self.assertFalse(ok)
        self.assertIn('namespace', detail)
        with patch.object(fp.shutil, 'which', return_value=None):
            self.assertIn('apt install bubblewrap', fp.LinuxBubblewrap().available()[1])

    @unittest.skipIf(NESTED, 'signals and locks are restricted inside an existing sandbox')
    def test_host_checks_pass_here(self):
        with tempfile.TemporaryDirectory() as tmp:
            for check in (fp.check_process_termination(), fp.check_resource_limits(), fp.check_locking(Path(tmp))):
                self.assertTrue(check['ok'], check)

    def test_agent_settings_never_allow_unsandboxed_fallback(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(forge, 'git', return_value=subprocess.CompletedProcess([], 1, '', '')):
            box = forge.sandbox_settings(Path(tmp), forge.PROFILES['app'], forge.DEFAULT_CONFIG)
        self.assertTrue(box['failIfUnavailable'])
        self.assertFalse(box['allowUnsandboxedCommands'])


class InspectTests(unittest.TestCase):
    """The read-only interface JARVIS uses, including across the Windows/WSL2 boundary."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        st = Path(self.tmp.name) / 'state'
        self.patch = patch.multiple(forge, STATE=st, DB=st / 'queue.sqlite3', REPORTS=st / 'reports', LOGS=st / 'logs',
                                    STOP=st / 'STOP', ACTIVE=st / 'active-child.json')
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.st = st
        conn = forge.ensure_state()
        with patch('builtins.print'):
            forge.add_task(conn, 1, 'Export', 'site')
            forge.event(conn, 1, 'checkpoint', 'abc123')
            forge.event(conn, 1, 'delivered', 'live branch fast-forwarded to abc123')
            forge.set_state(conn, 1, 'completed')
        conn.close()
        (st / 'reports' / '0001-builder-1791679690093003000.json').write_text(json.dumps({'agent': 'cendavo-builder', 'at': 'x', 'result': 'done'}))
        (st / 'reports' / '0001-security-1-1791679690093003001.json').write_text(json.dumps({'agent': 'cendavo-security-reviewer', 'result': 'VERDICT: PASS'}))
        (st / 'followups').mkdir()
        (st / 'followups' / 'task-0001.md').write_text('- [manual] check\n')

    def snapshot(self, **kw):
        before = sorted(p.name for p in self.st.rglob('*'))
        snap = forge.inspect_state(**kw)
        self.assertEqual(sorted(p.name for p in self.st.rglob('*')), before)  # strictly read-only
        return json.loads(json.dumps(snap, default=str))

    def test_snapshot_reports_tasks_events_reports_and_results(self):
        snap = self.snapshot(task_id=1)
        self.assertEqual(snap['interface'], 1)
        self.assertEqual([(t['id'], t['state'], t['profile']) for t in snap['tasks']], [(1, 'completed', 'site')])
        task = snap['task']
        self.assertEqual([(r['stage'], r['agent']) for r in task['reports']],
                         [('builder', 'cendavo-builder'), ('security-1', 'cendavo-security-reviewer')])
        self.assertEqual((task['commit'], task['followups']), ('abc123', '- [manual] check\n'))
        self.assertIn('abc123', task['delivered'])

    def test_runner_lock_and_orphan_detection(self):
        self.assertFalse(self.snapshot()['runner_active'])
        with (self.st / 'run.lock').open('w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertTrue(self.snapshot()['runner_active'])
        forge.ACTIVE.write_text(json.dumps({'pid': 999999, 'name': 'builder', 'task_id': 1}))
        child = self.snapshot()['active_child']
        self.assertEqual((child['name'], child['alive']), ('builder', False))

    def test_pre_v2_queue_without_profile_column(self):
        db = self.st / 'queue.sqlite3'
        for suffix in ('-wal', '-shm'):
            Path(str(db) + suffix).unlink(missing_ok=True)
        db.unlink()
        conn = sqlite3.connect(db)
        conn.execute('CREATE TABLE tasks (id INTEGER PRIMARY KEY, priority INTEGER NOT NULL, title TEXT NOT NULL, state TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, error TEXT)')
        conn.execute('CREATE TABLE events (id INTEGER PRIMARY KEY, task_id INTEGER, at TEXT NOT NULL, kind TEXT NOT NULL, detail TEXT NOT NULL)')
        conn.execute("INSERT INTO tasks VALUES (1, 1, 'old', 'queued', 0, 'x', 'x', NULL)")
        conn.commit(); conn.close()
        self.assertEqual(self.snapshot()['tasks'][0]['profile'], None)

    def test_module_uses_throwaway_state(self):
        real = Path(forge.__file__).resolve().parents[1] / '.cendavo-run'
        for name in ('STATE', 'LOGS', 'REPORTS', 'DB'):
            self.assertNotIn(str(real), str(getattr(forge, name)))

    def test_cli_inspect_is_json(self):
        with patch('sys.argv', ['forge.py', 'inspect', '--task', '1']), patch('builtins.print') as out:
            self.assertEqual(forge.main(), 0)
        self.assertEqual(json.loads(out.call_args.args[0])['task']['row']['state'], 'completed')


@unittest.skipUnless(fp.detect() in ('linux', 'wsl2') and shutil.which('bwrap') and not NESTED,
                     'requires Linux/WSL2 with bubblewrap, outside an existing sandbox')
class LinuxBubblewrapBehaviourTests(unittest.TestCase):
    """Real bubblewrap boundaries (run these on Linux/WSL2; see docs/WINDOWS.md)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='forge-bwrap-test-')
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name).resolve()
        self.root, self.temp, self.outside = base / 'Cendavo', base / 'tmp', base / 'outside.txt'
        for d in ('src', 'tests', '.cendavo-run', 'nested/secrets', '.git'):
            (self.root / d).mkdir(parents=True)
        self.temp.mkdir()
        (self.root / '.env').write_text('SECRET=1\n')
        (self.root / 'nested' / 'secrets' / 'token.txt').write_text('t')
        (self.root / '.cendavo-run' / 'queue.sqlite3').write_text('state')
        (self.root / 'tests' / 'test_x.py').write_text('x')
        (self.root / 'escape').symlink_to(Path.home())

    def py(self, code):
        argv = fp.LinuxBubblewrap().command([sys.executable, '-c', code], self.root, self.temp)
        env = dict(os.environ, HOME=str(self.temp), TMPDIR=str(self.temp))
        return subprocess.run(argv, cwd=self.root, env=env, capture_output=True, text=True, timeout=60, preexec_fn=forge.cap_open_files)

    def test_project_is_writable(self):
        result = self.py("open('src/new.py','w').write('ok'); print(open('src/new.py').read())")
        self.assertEqual((result.returncode, result.stdout.strip()), (0, 'ok'), result.stderr)

    def test_boundaries(self):
        cases = {
            'secret file': "print(open('.env').read())",
            'nested secret dir': "print(open('nested/secrets/token.txt').read())",
            'forge state': "print(open('.cendavo-run/queue.sqlite3').read())",
            'git metadata': "import os; print(os.listdir('.git') or exit(1))",
            'tests read-only': "open('tests/test_x.py','a').write('y')",
            'outside write': f"open({str(self.outside)!r},'w').write('x')",
            'home via symlink': "import os; print(os.listdir('escape') or exit(1))",
            'home directly': f"import os; print(os.listdir({str(Path.home())!r}) or exit(1))",
            'network': "import socket; socket.create_connection(('1.1.1.1', 53), timeout=3)",
        }
        for label, code in cases.items():
            with self.subTest(label=label):
                result = self.py(code)
                self.assertTrue(result.returncode != 0 or not result.stdout.strip(), (label, result.stdout))
        self.assertFalse(self.outside.exists())
        self.assertEqual((self.root / '.env').read_text(), 'SECRET=1\n')

    def test_sandbox_dies_with_forge_process_group(self):
        argv = fp.LinuxBubblewrap().command([sys.executable, '-c', 'import time; time.sleep(60)'], self.root, self.temp)
        proc = subprocess.Popen(argv, start_new_session=True)
        time.sleep(1)
        self.assertTrue(forge.terminate_group(proc.pid))
        proc.wait(timeout=10)

    def test_doctor_passes_on_this_host(self):
        results = fp.doctor(Path(forge.__file__).resolve().parents[1], Path(self.tmp.name) / 'state')
        self.assertEqual(fp.failures(results), [], json.dumps(results, indent=2))


@unittest.skipUnless(fp.detect() == 'macos' and shutil.which('sandbox-exec') and not NESTED,
                     'requires macOS sandbox-exec outside an existing sandbox')
class MacSandboxSelfTest(unittest.TestCase):
    def test_doctor_sandbox_probe_passes(self):
        result = fp.check_checks_sandbox('macos')
        self.assertTrue(result['ok'], result)


if __name__ == '__main__':
    unittest.main()
