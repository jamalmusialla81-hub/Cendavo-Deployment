"""Platform backends for Forge: which OS sandbox contains agent-written code, and host compatibility checks.

* macOS: Seatbelt via `sandbox-exec` (scripts/forge_sandbox.py, unchanged).
* Linux, including WSL2: bubblewrap. The checks stage gets its own mount, network, PID and user namespaces;
  agents' Bash uses Claude Code's built-in Linux sandbox, which also relies on bubblewrap (plus socat).
* Native Windows and WSL1 are refused: they have no supported sandbox. Forge never falls back to running
  agent-written code unsandboxed.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time

try:  # POSIX only: native Windows imports this module just to explain why Forge must run in WSL2.
    import fcntl
    import resource
except ImportError:  # pragma: no cover - exercised on native Windows
    fcntl = resource = None

if __package__:
    from .forge_sandbox import build_profile
else:
    from forge_sandbox import build_profile

# Same names the macOS profile hides at any project depth (forge_sandbox.build_profile).
PROTECTED_NAME = re.compile(
    r'^(\.git|\.cendavo-run|\.cendavo-tools|\.env([.][^/]*)?'
    r'|[Ss]ecrets?([.][^/]*)?|[Cc]redentials?([.][^/]*)?'
    r'|\.secrets?([.][^/]*)?|\.credentials?([.][^/]*)?'
    r'|auth[.]json|token[.]json|service-account[.]json'
    r'|id_rsa|id_ed25519|\.npmrc|\.pypirc'
    r'|[^/]+[.](pem|key|p12|pfx|kdbx))$')
# Same read-only paths as the macOS profile, plus the platform module itself.
READ_ONLY = ('.claude', '.github', 'tests', 'scripts/forge.py', 'scripts/forge_sandbox.py', 'scripts/forge_platform.py',
             'scripts/overnight.sh', 'scripts/verify_wsl.sh', 'scripts/verify_agent_sandbox.py', 'scripts/supervisor.py', 'scripts/supervise.sh', 'forge.config.json', '.gitignore',
             'AGENTS.md', 'CLAUDE.md')
SYSTEM_DIRS = ('/usr', '/bin', '/sbin', '/lib', '/lib32', '/lib64', '/libx32')
# Only what dynamic linking, Python, Node and Git need; no resolver, credentials or user configuration.
SYSTEM_FILES = ('/etc/ld.so.cache', '/etc/ld.so.conf', '/etc/ld.so.conf.d', '/etc/localtime', '/etc/alternatives',
                '/etc/passwd', '/etc/group', '/etc/nsswitch.conf', '/etc/ssl/certs', '/etc/ca-certificates')
TOOLS = ('python3', 'node', 'git')
SKIP_WALK = ('node_modules', '__pycache__', '.venv', 'dist', '.forge-cache')


def detect(system=None, release=None):
    """'macos', 'linux', 'wsl2', 'wsl1' or 'windows' (or the raw system name for anything else)."""
    system = system or platform.system()
    if system == 'Darwin':
        return 'macos'
    if system == 'Windows':
        return 'windows'
    if system == 'Linux':
        release = (release if release is not None else platform.release()).lower()
        if 'microsoft' in release:
            # WSL2 kernels: '5.15.x-microsoft-standard-WSL2'; WSL1 reports the Windows build: '4.4.0-19041-Microsoft'.
            return 'wsl2' if ('wsl2' in release or 'microsoft-standard' in release) else 'wsl1'
        return 'linux'
    return system.lower()


def unsupported_reason(kind):
    return {
        'windows': 'Native Windows has no supported sandbox for Forge. Run Forge inside WSL2 (see docs/WINDOWS.md).',
        'wsl1': 'WSL1 has no Linux kernel namespaces, so bubblewrap cannot sandbox Forge. Convert the distribution to WSL2: '
                'wsl --set-version <distro> 2.',
    }.get(kind, f'Unsupported platform {kind!r}: Forge needs macOS or Linux/WSL2.')


# --- checks-stage sandbox ------------------------------------------------------------------------------------
class MacSeatbelt:
    name = 'sandbox-exec'

    def available(self):
        return (True, 'macOS sandbox-exec') if shutil.which('sandbox-exec') else (False, 'sandbox-exec not found')

    def command(self, argv, root, tmp):
        return ['sandbox-exec', '-p', build_profile(Path(root), Path(tmp)), *argv]


class LinuxBubblewrap:
    name = 'bwrap'

    def available(self):
        path = shutil.which('bwrap')
        if not path:
            return False, 'bubblewrap (bwrap) is not installed: sudo apt install bubblewrap'
        probe = subprocess.run([path, '--unshare-all', '--die-with-parent', '--ro-bind', '/', '/', 'true'],
                               capture_output=True, text=True, timeout=20)
        if probe.returncode:
            return False, ('bubblewrap cannot create unprivileged namespaces here: '
                           + (probe.stderr.strip() or f'exit {probe.returncode}')[:300])
        return True, f'bubblewrap at {path}'

    def command(self, argv, root, tmp):
        return bwrap_argv(Path(root), Path(tmp)) + ['--', *argv]


def checks_sandbox(kind=None):
    """The backend for the current host, or None when Forge must refuse to run agent-written code."""
    kind = kind or detect()
    if kind == 'macos':
        return MacSeatbelt()
    if kind in ('linux', 'wsl2'):
        return LinuxBubblewrap()
    return None


def _protected_paths(root):
    """Existing protected names anywhere in the project (bubblewrap hides paths that exist; see bwrap_argv)."""
    found = []
    for base, dirs, files in os.walk(root):
        for name in list(dirs) + files:
            if PROTECTED_NAME.match(name):
                found.append(Path(base) / name)
        dirs[:] = [d for d in dirs if not PROTECTED_NAME.match(d) and d not in SKIP_WALK]
    return found


def _tool_roots(home=None):
    """Install roots of python3/node/git outside the system directories (e.g. pyenv, nvm, Homebrew on Linux)."""
    home = Path(home or Path.home()).resolve()
    roots = set()
    for found in [shutil.which(name) for name in TOOLS] + [sys.executable]:
        if not found:
            continue
        real = Path(found).resolve()
        if str(real).startswith(SYSTEM_DIRS):
            continue
        prefix = real.parents[1]  # <prefix>/bin/<tool>
        if prefix in (home, Path('/')) or prefix == home.parent:
            continue  # never expose a whole home directory
        roots.add(prefix)
    return sorted(roots)


def bwrap_argv(root, tmp, home=None):
    """bubblewrap arguments matching the macOS checks profile.

    Visible: system runtime directories (read-only), a minimal /etc, install roots of python3/node/git (read-only),
    the project (read-write) and one private temporary directory. Everything else, including the home directory,
    other projects and Forge's state, does not exist inside the sandbox. Protected names are hidden (directories
    become empty read-only tmpfs, files read as empty and cannot be written), runner and test definitions are
    read-only, and every namespace is unshared, so there is no network.
    """
    root, tmp = Path(root).resolve(strict=True), Path(tmp).resolve(strict=True)
    if root == tmp or root in tmp.parents:
        raise ValueError('Sandbox temporary directory must be outside the project')
    args = ['bwrap', '--unshare-all', '--die-with-parent', '--new-session', '--cap-drop', 'ALL',
            '--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp']
    # os.path checks return False instead of raising when a path cannot be inspected (e.g. inside another sandbox).
    for path in SYSTEM_DIRS:
        if os.path.islink(path):
            args += ['--symlink', os.readlink(path), path]
        elif os.path.isdir(path):
            args += ['--ro-bind', path, path]
    for path in SYSTEM_FILES:
        if os.path.exists(path):
            args += ['--ro-bind', path, path]
    for prefix in _tool_roots(home):
        args += ['--ro-bind', str(prefix), str(prefix)]
    args += ['--bind', str(root), str(root), '--bind', str(tmp), str(tmp)]
    for path in _protected_paths(root):
        if path.is_dir() and not path.is_symlink():
            args += ['--tmpfs', str(path), '--remount-ro', str(path)]
        else:
            args += ['--ro-bind', '/dev/null', str(path)]
    for name in READ_ONLY:
        path = root / name
        if os.path.exists(path) and not os.path.islink(path):
            args += ['--ro-bind', str(path), str(path)]
    args += ['--chdir', str(root)]
    return args


# --- compatibility checks -------------------------------------------------------------------------------------
def _check(name, ok, detail, required=True):
    return {'check': name, 'ok': bool(ok), 'required': required, 'detail': detail}


def check_platform(kind):
    if kind in ('macos', 'linux', 'wsl2'):
        return _check('platform', True, {'macos': 'macOS', 'linux': 'Linux', 'wsl2': 'WSL2 (Linux kernel)'}[kind])
    return _check('platform', False, unsupported_reason(kind))


def check_filesystem(root, kind):
    """Forge's state relies on POSIX permissions, case-sensitive names and local locking."""
    root = Path(root).resolve()
    if kind == 'wsl2' and str(root).startswith('/mnt/'):
        return _check('filesystem', False, f'{root} is on a Windows drive (/mnt/...). Clone Forge into the WSL2 Linux filesystem, '
                                           'e.g. ~/Cendavo: Windows drives ignore chmod, are case-insensitive and lock unreliably.')
    try:
        with tempfile.TemporaryDirectory(dir=root, prefix='.forge-fscheck-') as scratch:
            probe = Path(scratch) / 'probe'
            probe.write_text('x')
            probe.chmod(0o600)
            mode_ok = (probe.stat().st_mode & 0o777) == 0o600
            (Path(scratch) / 'Case').write_text('a')
            case_ok = not (Path(scratch) / 'case').exists()
    except OSError as exc:
        return _check('filesystem', False, f'cannot create private files under {root}: {exc}')
    # macOS's default APFS is case-insensitive and safe for Forge (its guard compares bytes of control files, not names);
    # on Linux/WSL2 a case-insensitive project means a Windows drive, where permissions and locking are unreliable.
    case_required = kind != 'macos'
    problems = ([] if mode_ok else ['chmod 0600 is not honoured']) + ([] if case_ok or not case_required else ['file names are case-insensitive'])
    note = '' if case_ok else ' (case-insensitive, accepted on macOS)'
    return _check('filesystem', not problems, '; '.join(problems) or 'POSIX permissions honoured' + note)


PROBE_STARTED = 'forge-probe-started'


def _run_probe(backend, root, tmp, code):
    """Run `code` with the same `python3` and PATH as Forge's checks stage (not whichever interpreter runs Forge)."""
    path = '/Library/Developer/CommandLineTools/usr/bin' + os.pathsep + os.environ.get('PATH', '')
    env = dict(os.environ, TMPDIR=str(tmp), HOME=str(tmp), PYTHONDONTWRITEBYTECODE='1', PATH=path)
    env.pop('PYTHONPATH', None)
    started = f"import sys; sys.stdout.write({PROBE_STARTED!r} + chr(10)); sys.stdout.flush()\n"
    argv = backend.command(['python3', '-c', started + code], root, tmp)
    return subprocess.run(argv, cwd=root, env=env, capture_output=True, text=True, timeout=60, preexec_fn=cap_open_files)


def check_checks_sandbox(kind):
    """Run Forge's real checks-stage backend against a scratch project and prove its boundaries."""
    backend = checks_sandbox(kind)
    if backend is None:
        return _check('checks sandbox', False, unsupported_reason(kind))
    ok, detail = backend.available()
    if not ok:
        return _check('checks sandbox', False, detail)
    with tempfile.TemporaryDirectory(prefix='forge-sandbox-selftest-') as scratch:
        base = Path(scratch).resolve()
        root, tmp, outside = base / 'project', base / 'tmp', base / 'outside.txt'
        for d in (root / 'src', root / 'tests', root / '.cendavo-run', tmp):
            d.mkdir(parents=True)
        (root / '.env').write_text('SECRET=selftest\n')
        (root / '.cendavo-run' / 'queue.sqlite3').write_text('state')
        (root / 'tests' / 'test_x.py').write_text('x')
        expectations = {
            'project writable': ("open('src/ok.txt','w').write('ok')", True),
            'outside not writable': (f"open({str(outside)!r},'w').write('x')", False),
            'secret unreadable': ("assert 'SECRET' in open('.env').read()", False),
            'Forge state unreadable': ("open('.cendavo-run/queue.sqlite3').read()", False),
            'tests read-only': ("open('tests/test_x.py','a').write('y')", False),
            'no network': ("import socket; socket.create_connection(('1.1.1.1', 53), timeout=3)", False),
        }
        home_file = next((f for f in (Path.home() / n for n in ('.gitconfig', '.profile', '.zshrc', '.bashrc', '.bash_profile'))
                          if f.is_file()), None)
        if home_file:  # contents of files in the home directory must not be readable
            expectations['home files unreadable'] = (f"open({str(home_file)!r}).read(1)", False)
        failures = []
        for label, (code, allowed) in expectations.items():
            result = _run_probe(backend, root, tmp, code)
            if PROBE_STARTED not in result.stdout:
                failures.append(f'{label} (python3 could not start in the sandbox: {result.stderr.strip()[-160:]})')
            elif (result.returncode == 0) != allowed:
                failures.append(label)
        failures += ['outside file created'] if outside.exists() else []
    return _check('checks sandbox', not failures,
                  f'{backend.name}: ' + (('FAILED: ' + ', '.join(failures)) if failures else 'project writable; outside, secrets, '
                                         'Forge state, tests, network and home all denied'))


def check_agent_sandbox(kind):
    """Claude Code's own Bash sandbox: built in on macOS; on Linux it needs bubblewrap and socat."""
    if kind == 'macos':
        return _check('agent sandbox', True, 'Claude Code uses macOS Seatbelt')
    if kind not in ('linux', 'wsl2'):
        return _check('agent sandbox', False, unsupported_reason(kind))
    missing = [t for t in ('bwrap', 'socat') if not shutil.which(t)]
    if missing:
        return _check('agent sandbox', False, f'Claude Code\'s Linux sandbox needs {" and ".join(missing)}: '
                                              f'sudo apt install {" ".join("bubblewrap" if t == "bwrap" else t for t in missing)}')
    return _check('agent sandbox', True, 'bubblewrap and socat present (Forge sets failIfUnavailable, so Claude Code refuses '
                                         'rather than running Bash unsandboxed)')


def check_process_termination():
    """Forge stops agents by killing their whole process group, including descendants."""
    proc = subprocess.Popen([sys.executable, '-c', 'import subprocess,sys,time;'
                             'subprocess.Popen([sys.executable,"-c","import time; time.sleep(60)"]);time.sleep(60)'],
                            start_new_session=True)
    time.sleep(0.5)
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    except PermissionError as exc:
        proc.kill()
        proc.wait(timeout=10)
        return _check('process termination', False, f'cannot signal a process group: {exc}')
    proc.wait(timeout=10)
    for _ in range(50):
        try:
            os.killpg(proc.pid, 0)
        except ProcessLookupError:
            return _check('process termination', True, 'process groups and their descendants terminate')
        time.sleep(0.1)
    os.killpg(proc.pid, signal.SIGKILL)
    return _check('process termination', False, 'a descendant survived SIGTERM of its process group')


SANDBOX_OPEN_FILES = 4096


def cap_open_files():
    """Child-side: cap the open-file limit (see forge.cap_open_files)."""
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    limit = SANDBOX_OPEN_FILES if soft == resource.RLIM_INFINITY else min(soft, SANDBOX_OPEN_FILES)
    resource.setrlimit(resource.RLIMIT_NOFILE, (limit, hard))


def check_resource_limits():
    out = subprocess.run([sys.executable, '-c', 'import resource; print(resource.getrlimit(resource.RLIMIT_NOFILE)[0])'],
                         capture_output=True, text=True, preexec_fn=cap_open_files, timeout=20)
    try:
        ok = 0 < int(out.stdout) <= SANDBOX_OPEN_FILES
    except ValueError:
        ok = False
    return _check('resource limits', ok, f'child open-file limit {out.stdout.strip() or "unknown"} (cap {SANDBOX_OPEN_FILES}); '
                                         'per-command timeouts are enforced by Forge')


def check_locking(state):
    state = Path(state)
    try:
        state.mkdir(mode=0o700, parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=state, prefix='.lockcheck-') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(handle, fcntl.LOCK_UN)
    except OSError as exc:
        return _check('locking', False, f'flock does not work in {state}: {exc}')
    return _check('locking', True, 'flock works for the run lock')


def doctor(root, state, kind=None):
    """All compatibility checks; Forge refuses to run while any required check fails."""
    kind = kind or detect()
    results = [check_platform(kind)]
    if not results[0]['ok']:
        return results
    results += [check_filesystem(root, kind), check_locking(state), check_process_termination(), check_resource_limits(),
                check_checks_sandbox(kind), check_agent_sandbox(kind)]
    return results


def failures(results):
    return [r for r in results if r['required'] and not r['ok']]


if __name__ == '__main__':
    report = doctor(Path(__file__).resolve().parents[1], Path(__file__).resolve().parents[1] / '.cendavo-run')
    print(json.dumps(report, indent=2))
    sys.exit(1 if failures(report) else 0)
