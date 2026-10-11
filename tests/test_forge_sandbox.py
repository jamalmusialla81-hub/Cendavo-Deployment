"""Behavioral checks of the macOS sandbox, not just its profile text."""
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import unittest

from scripts import forge
from scripts.forge_sandbox import build_profile


@unittest.skipUnless(platform.system() == 'Darwin' and shutil.which('sandbox-exec')
                     and not os.environ.get('CENDAVO_SANDBOXED'),
                     'requires macOS sandbox-exec outside an existing sandbox')
class ForgeSandboxTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix='cendavo-policy-test-')
        self.addCleanup(self.scratch.cleanup)
        base = Path(self.scratch.name).resolve()
        self.root = base / 'Cendavo'
        self.root.mkdir()
        self.temporary = base / 'runtime-tmp'
        self.temporary.mkdir()
        self.private = base / 'private-home'
        self.private.mkdir()
        self.profile = build_profile(self.root, self.temporary)
        self.env = dict(os.environ, TMPDIR=str(self.temporary), TMP=str(self.temporary),
                        TEMP=str(self.temporary), HOME=str(self.temporary),
                        GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='/dev/null',
                        PYTHONDONTWRITEBYTECODE='1')
        self.env['PATH'] = '/Library/Developer/CommandLineTools/usr/bin' + os.pathsep + self.env.get('PATH', '')

    def run_sandbox(self, *argv, timeout=20):
        return subprocess.run(['sandbox-exec', '-p', self.profile, *argv],
                              cwd=self.root, env=self.env, text=True,
                              capture_output=True, timeout=timeout)

    def python(self, code, path):
        return self.run_sandbox(sys.executable, '-c', code, str(path))

    def test_project_tree_allows_creation_read_and_write(self):
        target = self.root / 'new' / 'nested' / 'request.txt'
        code = 'from pathlib import Path; import sys; p=Path(sys.argv[1]); p.parent.mkdir(parents=True); p.write_text("ok"); print(p.read_text())'
        result = self.python(code, target)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'ok')

    def test_protected_project_paths_deny_read_write_and_creation(self):
        for name in ('.git/config', '.cendavo-run/queue.sqlite3', '.env',
                     'nested/.env.local', 'nested/secrets/token.txt',
                     'nested/credentials.json', 'nested/private.pem',
                     '.cendavo-tools/cli'):
            with self.subTest(name=name):
                target = self.root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text('sentinel')
                read = self.python('from pathlib import Path; import sys; print(Path(sys.argv[1]).read_text())', target)
                write = self.python('from pathlib import Path; import sys; Path(sys.argv[1]).write_text("changed")', target)
                self.assertNotEqual(read.returncode, 0, name)
                self.assertNotEqual(write.returncode, 0, name)
                self.assertEqual(target.read_text(), 'sentinel')
        new_secret = self.root / 'nested' / 'secrets' / 'new.txt'
        self.assertNotEqual(self.python('from pathlib import Path; import sys; Path(sys.argv[1]).write_text("bad")', new_secret).returncode, 0)
        (self.root / 'env-alias').symlink_to(self.root / '.env')
        self.assertNotEqual(self.python('from pathlib import Path; import sys; print(Path(sys.argv[1]).read_text())', self.root / 'env-alias').returncode, 0)

    def test_unrelated_home_system_and_symlink_escapes_are_denied(self):
        for name in ('.ssh/id_ed25519', 'Library/Application Support/Browser/profile',
                     'other-project/data.txt'):
            target = self.private / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('private')
            with self.subTest(name=name):
                self.assertNotEqual(self.python('from pathlib import Path; import sys; print(Path(sys.argv[1]).read_text())', target).returncode, 0)
                self.assertNotEqual(self.python('from pathlib import Path; import sys; Path(sys.argv[1]).write_text("bad")', target).returncode, 0)
                self.assertEqual(target.read_text(), 'private')
        (self.root / 'escape').symlink_to(self.private, target_is_directory=True)
        target = self.root / 'escape' / '.ssh' / 'id_ed25519'
        self.assertNotEqual(self.python('from pathlib import Path; import sys; print(Path(sys.argv[1]).read_text())', target).returncode, 0)
        self.assertNotEqual(self.python('from pathlib import Path; import sys; Path(sys.argv[1]).write_text("bad")', target).returncode, 0)
        self.assertNotEqual(self.python('from pathlib import Path; import sys; print(Path(sys.argv[1]).read_text())', '/etc/hosts').returncode, 0)

    def test_runner_and_test_definitions_are_read_only(self):
        for name in ('scripts/forge.py', 'scripts/forge_sandbox.py', 'tests/test_site.py',
                     '.claude/agents/reviewer.md', 'AGENTS.md'):
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('sentinel')
            with self.subTest(name=name):
                self.assertEqual(self.python('from pathlib import Path; import sys; print(Path(sys.argv[1]).read_text())', target).returncode, 0)
                self.assertNotEqual(self.python('from pathlib import Path; import sys; Path(sys.argv[1]).write_text("bad")', target).returncode, 0)
                self.assertEqual(target.read_text(), 'sentinel')

    def test_network_is_denied(self):
        code = 'import socket; s=socket.socket(); s.connect(("127.0.0.1", 9))'
        result = self.run_sandbox(sys.executable, '-c', code)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Operation not permitted', result.stderr)

    def test_installed_development_tools_can_start(self):
        for name in ('python3', 'node', 'git', 'claude'):
            tool = shutil.which(name, path=self.env['PATH'])
            if not tool:
                continue
            with self.subTest(name=name):
                result = self.run_sandbox(tool, '--version')
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_homebrew_python_can_resolve_its_cellar_path(self):
        homebrew_python = Path('/opt/homebrew/bin/python3')
        if not homebrew_python.exists():
            self.skipTest('Homebrew Python is not installed')
        result = self.run_sandbox(str(homebrew_python), '-c',
                                  'import os,sys; print(os.path.realpath(sys.executable))')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('/opt/homebrew/Cellar/', result.stdout)


    def test_forge_and_supervisor_tests_pass_inside_sandbox_without_protected_paths(self):
        """Regression: the automated unit-test stage must not need .cendavo-run, .cendavo-tools or the real .git."""
        source = Path(__file__).resolve().parents[1]
        shutil.copytree(source / 'scripts', self.root / 'scripts', ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copytree(source / '.claude' / 'agents', self.root / '.claude' / 'agents')
        (self.root / 'tests').mkdir()
        for name in ('__init__.py', 'test_forge.py', 'test_supervisor.py'):
            if (source / 'tests' / name).exists():
                shutil.copy(source / 'tests' / name, self.root / 'tests' / name)
        sentinels = {}
        for name in ('.cendavo-run/queue.sqlite3', '.cendavo-tools/node_modules/.bin/claude', '.git/config'):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('sentinel')
            sentinels[path] = path.stat().st_mtime_ns
        env = dict(self.env, CENDAVO_SANDBOXED='1', XDG_CACHE_HOME=str(self.temporary))
        env.pop('PYTHONPATH', None)
        python3 = shutil.which('python3', path=env['PATH'])
        result = subprocess.run(['sandbox-exec', '-p', self.profile, python3, '-m', 'unittest', 'discover', '-s', 'tests'],
                                cwd=self.root, env=env, text=True, capture_output=True, timeout=300,
                                preexec_fn=forge.cap_open_files)
        self.assertEqual(result.returncode, 0, result.stderr[-3000:])
        for path, mtime in sentinels.items():
            self.assertEqual((path.read_text(), path.stat().st_mtime_ns), ('sentinel', mtime), path)
        self.assertEqual(sorted(p.name for p in (self.root / '.cendavo-run').iterdir()), ['queue.sqlite3'])

if __name__ == '__main__':
    unittest.main()
