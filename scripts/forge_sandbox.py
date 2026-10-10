"""macOS Seatbelt profile for running untrusted Cendavo build and test code.

The model clients run outside this profile because they need their own private
authentication and an approved connection to their model providers. Their
tool permissions are set separately in forge.py.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import shutil


def _quoted(path: Path | str) -> str:
    return json.dumps(str(path))


def _ancestors(path: Path) -> set[Path]:
    return set(path.parents)


def _tool_paths() -> set[Path]:
    """Allow executable files, symlink entry points and their real paths only."""
    paths: set[Path] = set()
    for name in ('python3', 'node', 'git', 'claude'):
        found = shutil.which(name)
        if found:
            entry = Path(found).absolute()
            paths.update((entry, entry.resolve()))
    return paths


def build_profile(root: Path, temporary: Path) -> str:
    """Return a project-scoped, offline macOS sandbox profile.

    The temporary directory must be a private directory created by the caller.
    Only known development runtime trees are readable outside the project.
    Deny rules override the project-wide allow rules.
    """
    root = root.resolve(strict=True)
    temporary = temporary.resolve(strict=True)
    if root == temporary or root in temporary.parents:
        raise ValueError('Sandbox temporary directory must be outside the project')

    runtime = (
        '/usr', '/bin', '/sbin', '/System/Library',
        '/Library/Frameworks', '/Library/Developer/CommandLineTools',
        '/opt/homebrew', '/usr/local', '/private/var/db/dyld',
        str(Path.home() / '.local/share/claude/versions'),
    )
    readable_subpaths = {root, temporary, *(Path(p) for p in runtime)}
    tool_files = _tool_paths()
    literals = {Path('/dev/null'), Path('/dev/random'), Path('/dev/urandom'),
                Path('/private/etc/localtime'),
                Path('/private/var/select/developer_dir'),
                Path('/var/select/developer_dir'), *tool_files}
    for path in readable_subpaths | literals:
        literals.update(_ancestors(path))
    read_rules = ' '.join(f'(subpath {_quoted(p)})' for p in sorted(readable_subpaths))
    read_rules += ' ' + ' '.join(f'(literal {_quoted(p)})' for p in sorted(literals))

    escaped = re.escape(str(root))
    # Match at any depth. These names are never readable or writable, even
    # when a tool attempts access through an in-project symlink.
    protected = (
        rf'^{escaped}/([^/]+/)*'
        r'(\.git|\.cendavo-run|\.cendavo-tools|\.env([.][^/]*)?'
        r'|[Ss]ecrets?([.][^/]*)?|[Cc]redentials?([.][^/]*)?'
        r'|\.secrets?([.][^/]*)?|\.credentials?([.][^/]*)?'
        r'|auth[.]json|token[.]json|service-account[.]json'
        r'|id_rsa|id_ed25519|\.npmrc|\.pypirc'
        r'|[^/]+[.](pem|key|p12|pfx|kdbx))(/|$)'
    )
    return ''.join((
        '(version 1)',
        '(deny default)',
        '(allow process*)',
        '(allow sysctl-read)',
        '(allow mach-lookup)',
        f'(allow file-read* {read_rules})',
        f'(allow file-write* (subpath {_quoted(root)}) (subpath {_quoted(temporary)}))',
        '(allow file-write* (literal "/dev/null"))',
        f'(deny file-read* file-write* (regex {json.dumps(protected)}))',
        '(deny network*)',
    ))
