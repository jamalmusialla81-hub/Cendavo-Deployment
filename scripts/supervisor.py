#!/usr/bin/env python3
"""Forge Supervisor: bounded, autonomous recovery around the Claude-only Forge pipeline.

Product failures (site build, frontend tests, unresolved audit findings) are repaired by
the Claude Builder with bounded retries. Infrastructure failures (Forge runner, its tests,
agent output handling, sandbox wiring) go to a separate Claude maintenance agent in an
isolated Git worktree. A maintenance patch is integrated only after a deterministic policy
check, sandboxed tests and an independent Claude security review; anything that touches a
security boundary waits for the owner's approval.

Claude Code runs on the owner's subscription only. There is no API key, paid fallback or
dollar limit; provider usage limits stop the run. Nothing is pushed or deployed.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import math
import os
import re
import secrets
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

# Import Forge as `scripts.forge` in every context so exception classes and state paths are shared with tests.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import forge  # noqa: E402

# Per task, per supervisor run. Set from forge.config.json `limits` (or --max-repairs/--max-maintenance) by supervise().
MAX_PRODUCT_REPAIRS = forge.DEFAULT_CONFIG['limits']['product_repairs']
MAX_MAINTENANCE = forge.DEFAULT_CONFIG['limits']['maintenance_attempts']
MAX_EVIDENCE_CHARS = 12_000
FORGE_TEST_MODULES = {'test_forge', 'test_supervisor'}

# Failure kinds
PRODUCT, INFRA, LIMIT, SECURITY, ENVIRONMENT, HUMAN = 'product', 'infrastructure', 'provider_limit', 'security', 'environment', 'needs_human'

SANDBOX_DENIAL = re.compile(r'operation not permitted|sandbox|deny\(\d\)|permissionerror: \[errno (1|13)\]', re.I)
PROTECTED_STATE = re.compile(r'\.cendavo-run|\.cendavo-tools|\.git/|/\.git\b|\.env')
FAILED_TEST = re.compile(r'^(?:ERROR|FAIL): \S+ \(([\w.]+)\)', re.M)
IMPORT_FAIL = re.compile(r'Failed to import test module: ([\w.]+)')

# Maintenance patch policy -------------------------------------------------------------
# Paths a maintenance patch may change without the owner's approval.
SAFE_PREFIXES = ('scripts/', 'tests/', 'docs/')
# Always need approval: the supervisor itself, agent definitions, CI, project instructions, ignore rules, dependencies.
APPROVAL_PATHS = ('scripts/supervisor.py', 'scripts/overnight.sh', 'scripts/supervise.sh', 'scripts/forge_sandbox.py', 'scripts/forge_platform.py', 'scripts/verify_wsl.sh', 'scripts/verify_agent_sandbox.py',
                  'forge.config.json', '.mcp.json', '.claude/', '.github/', 'AGENTS.md', 'CLAUDE.md', '.gitignore', 'requirements.txt')
# Changed lines in non-test code that touch security boundaries, credentials, sandbox or permission policy,
# product-repair containment, or the checkpoint proof that lets validated stages be reused.
BOUNDARY = re.compile(
    r'sandbox|profile|file-read|file-write|allow |deny|DENY|BILLING_ENV|subscription_env|subscription_flags|FORBIDDEN_CLAUDE_FLAGS|'
    r'restricted|forceLoginMethod|plugin|SKILL_AGENTS|REPAIR_MODE|repair_guard|product_repair_only|maintenance_isolation|'
    r'maintenance_root|SecurityFailure|MaintenanceRequired|fingerprint|stage_done|mark_stage|checkpoint|verdict|'
    r'CONTROL_|SECRET_|CONSEQUENTIAL_BASH|PROFILES|Profile\(|writable|agent_guard|guard_snapshot|write_denials|workspace|'
    r'mcp|allowedDomains|registr|max_turns|limits|deliver|ff-only|bwrap|unshare|ro-bind|forge_platform|doctor|'
    r'allowed_changes|protected|PROTECTED|APPROVAL_PATHS|SAFE_PREFIXES|BOUNDARY|'
    r'api[_-]?key|token|secret|credential|password|\bauth|oauth|'
    r'permission|allowedTools|disallowedTools|--tools|dontAsk|bypass|WRITABLE_AGENTS|REQUIRED_AGENTS|'
    r'\.cendavo-run|\.env|\.git\b|environ|subprocess|Popen|os\.system|shell=True|urllib|requests|socket|http',
    re.I)
TEST_DISABLE = re.compile(r'\bskip(If|Unless|Test)?\(|@unittest\.skip|expectedFailure|SkipTest|pytest\.mark\.(skip|xfail)')
# Test code also runs outside the sandbox when the owner runs the suite by hand.
TEST_DANGER = re.compile(r'subprocess|Popen|os\.system|shell=True|urllib|requests|socket|http|expanduser|~/|/Users/|\.ssh|environ\[|getenv', re.I)


@dataclass
class Failure:
    kind: str
    task_id: int
    stage: str
    summary: str
    evidence: str = ''
    log: str = ''
    failing_modules: list = field(default_factory=list)


@dataclass
class Assessment:
    violations: list = field(default_factory=list)   # hard rejections
    approvals: list = field(default_factory=list)    # need the owner's approval
    files: list = field(default_factory=list)

    @property
    def safe(self):  # noqa: D401
        return not self.violations and not self.approvals


# Paths and state ------------------------------------------------------------------------
def sup_dir():
    path = forge.STATE / 'supervisor'
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path


def maint_root():
    # Outside the project: the live test sandbox may write anywhere under ROOT, and the maintainer
    # is denied the whole live checkout (see forge.claude_argv).
    path = forge.maintenance_root()
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.chmod(0o700)
    return path


def write_private(path, text):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(0o600)


def load_state():
    try:
        return json.loads((sup_dir() / 'state.json').read_text())
    except (OSError, ValueError):
        return {'repairs': {}, 'maintenance': {}, 'deadline_epoch': None}


def save_state(state):
    write_private(sup_dir() / 'state.json', json.dumps(state, indent=2))


def bump(state, key, task_id):
    counts = state.setdefault(key, {})
    counts[str(task_id)] = counts.get(str(task_id), 0) + 1
    save_state(state)
    return counts[str(task_id)]


# Diagnosis ------------------------------------------------------------------------------
def read_log(path, limit=MAX_EVIDENCE_CHARS):
    try:
        text = Path(path).read_text(errors='replace')
    except OSError:
        return ''
    return text[-limit:]


def failing_modules(text):
    mods = {m.split('.')[0] for m in FAILED_TEST.findall(text)}
    mods.update(m.split('.')[0] for m in IMPORT_FAIL.findall(text))
    return sorted(mods)


def classify(exc, task_id):
    """Map an exception from run_task to a failure kind using its type, stage and log evidence."""
    msg = str(exc)
    if isinstance(exc, forge.RateLimited):
        return Failure(LIMIT, task_id, 'provider', msg)
    if isinstance(exc, forge.SecurityFailure):
        return Failure(SECURITY, task_id, 'security', msg)
    if isinstance(exc, forge.MaintenanceRequired):
        # Forge's own debugger-gated unit-test repair stopped. Only infrastructure findings go to the maintainer;
        # exhausted product repairs, TEST/UNKNOWN diagnoses and unvalidated trees need the owner.
        if exc.failure is not None and exc.classification == 'INFRASTRUCTURE':
            base = classify(exc.failure, task_id)
            base.kind = INFRA
            if not base.summary.startswith(base.stage + ':'):
                base.summary = f'{base.stage}: {msg}'
            return base
        evidence = read_log(exc.failure.log) if exc.failure is not None else ''
        return Failure(HUMAN, task_id, 'maintenance-required', msg, evidence)
    if isinstance(exc, forge.CommandFailure):
        log = read_log(exc.log) or exc.output
        stage = exc.stage
        mods = failing_modules(log)
        base = Failure(PRODUCT, task_id, stage, msg, log, str(exc.log), mods)
        if stage not in forge.test_stages():
            base.kind = INFRA  # an agent CLI call itself exited non-zero
        elif SANDBOX_DENIAL.search(log) and PROTECTED_STATE.search(log):
            base.kind = INFRA
            base.summary = f'{stage}: sandbox denied access to protected state; Forge tests or runner must not depend on it'
        elif stage == 'unit-tests' and mods and set(mods) <= FORGE_TEST_MODULES:
            base.kind = INFRA
            base.summary = f'{stage}: only Forge runner tests failed ({", ".join(mods)})'
        elif stage == 'unit-tests' and not mods and 'Traceback' in log and 'scripts/forge.py' in log:
            base.kind = INFRA
        return base
    lower = msg.lower()
    if 'touched protected files' in lower:
        return Failure(SECURITY, task_id, 'builder', msg)
    if 'not validated' in lower or 'uncommitted changes' in lower:
        return Failure(HUMAN, task_id, 'checkpoint', msg)
    if any(t in lower for t in ('requires macos', 'isolated test execution requires', 'not compatible with forge', 'missing required cli', 'not authenticated', 'manual stop',
                                'maximum runtime', 'timed out', 'left a child process', 'too large for an independent review',
                                'requires a logged-in', 'could not verify cli authentication', 'stopped before checkpoint')):
        return Failure(ENVIRONMENT, task_id, 'environment', msg)
    if 'review cycle limit' in lower or 'made no source changes' in lower:
        evidence = latest_report_text(task_id, ('audit-', 'security-'))
        return Failure(PRODUCT, task_id, 'review', msg, evidence)
    if any(t in lower for t in ('verdict missing', 'returned no report', 'reported an error', 'agent definition',
                                'missing agent', 'agent file', 'unknown agent')):
        return Failure(INFRA, task_id, 'agent-io', msg, latest_report_text(task_id, ('',)))
    return Failure(HUMAN, task_id, 'unknown', f'Unclassified failure: {type(exc).__name__}: {msg}')


def latest_report_text(task_id, prefixes):
    reports = sorted(forge.REPORTS.glob(f'{task_id:04d}-*.json'), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in reports:
        if any(path.name[5:].startswith(p) for p in prefixes):
            try:
                return str(json.loads(path.read_text()).get('result', ''))[-MAX_EVIDENCE_CHARS:]
            except (OSError, ValueError):
                continue
    return ''


def report_failure(conn, failure, action, detail=''):
    stamp = time.strftime('%Y%m%dT%H%M%S')
    body = {**asdict(failure), 'action': action, 'detail': detail, 'at': forge.now()}
    body['evidence'] = body['evidence'][-4000:]
    write_private(sup_dir() / 'reports' / f'{stamp}-task{failure.task_id:04d}-{failure.kind}.json', json.dumps(body, indent=2))
    forge.event(conn, failure.task_id, f'supervisor_{failure.kind}', f'{action}: {failure.summary} {detail}'.strip())


# Product repair -------------------------------------------------------------------------
# Shared with Forge, which enforces it after every writable agent call.
test_integrity_violations = forge.test_integrity_violations


def repair_product(conn, row, failure, deadline):
    task_id, _, title, _ = row
    with forge.task_context(conn, task_id) as profile:
        baseline = forge.git('rev-parse', 'HEAD').stdout.strip()
        cp = forge.load_checkpoint(task_id, baseline)
        if not forge.stage_done(cp, 'strategy'):
            raise RuntimeError('No validated strategy to repair against')
        names = forge.allowed_changes()
        frontend = forge.is_frontend_task(title, names)
        existing = set(test_integrity_violations(forge.git('diff', baseline, '--').stdout))
        prompt = forge.builder_prompt(title, cp['stages']['strategy']['text'], frontend,
                                      'Automated checks failed after your implementation. Diagnose the root cause from the evidence '
                                      'and repair it within your permission profile. Never skip, delete or weaken tests to make them pass.\n\n'
                                      f'Failed stage: {failure.stage}\nSummary: {failure.summary}\n\n'
                                      f'{forge.fenced("Failure evidence", failure.evidence[-MAX_EVIDENCE_CHARS:])}\n\n', profile)
        # builder_call runs under forge.agent_guard: profile scope, control plane, live checkout and test integrity.
        forge.builder_call(task_id, cp, f'repair-{failure.stage}', prompt, deadline, frontend)
        problems = [p for p in test_integrity_violations(forge.git('diff', baseline, '--').stdout) if p not in existing]
        if problems:
            raise forge.SecurityFailure('Repair weakened tests: ' + '; '.join(problems))
        diff, fp = forge.change_snapshot(baseline)
        if not diff.strip():
            raise RuntimeError('Repair left no changes')
        # The repaired change is a new Builder output: security review, tests and audit all run again on it.
        forge.mark_stage(task_id, cp, 'build', fp)


# Maintenance ----------------------------------------------------------------------------
def worktree_diff(path):
    forge.git('add', '-A', cwd=path)
    return forge.git('diff', '--cached', 'HEAD', cwd=path).stdout


def assess_patch(diff):
    """Deterministic policy: hard violations, approval-required changes, or safe."""
    result = Assessment()
    current = None
    for line in diff.splitlines():
        if line.startswith('diff --git '):
            parts = line.split(' b/', 1)
            current = parts[1] if len(parts) > 1 else None
            if current and current not in result.files:
                result.files.append(current)
            continue
        if line.startswith(('+++', '---', 'index ', 'new file', 'deleted file', 'similarity', 'rename', 'old mode', 'new mode')):
            if line.startswith(('old mode', 'new mode')) and current:
                result.approvals.append(f'{current}: file mode change')
            continue
        if not current or not line[:1] in '+-':
            continue
        if current.startswith('tests/'):
            if line.startswith('+') and TEST_DANGER.search(line[1:]):
                result.approvals.append(f'{current}: test code gains process, network or home-directory access: {line[1:].strip()[:100]}')
            continue  # otherwise judged by test_integrity_violations
        if BOUNDARY.search(line[1:]):
            result.approvals.append(f'{current}: touches a security boundary: {line[1:].strip()[:100]}')
    for name in result.files:
        parts = Path(name).parts
        if name.startswith('.env') or '..' in parts or name.startswith(('.git/', '.cendavo-run/', '.cendavo-tools/')):
            result.violations.append(f'{name}: forbidden path')
        elif name.startswith(APPROVAL_PATHS):
            result.approvals.append(f'{name}: protected control file')
        elif not name.startswith(SAFE_PREFIXES):
            result.violations.append(f'{name}: outside Forge infrastructure (product files are not maintenance scope)')
    result.violations += test_integrity_violations(diff)
    if not re.search(r'^\+\s*def test_', diff, re.M) or not any(f.startswith('tests/') for f in result.files):
        result.violations.append('no regression test added')
    # De-duplicate while keeping order.
    result.approvals = list(dict.fromkeys(result.approvals))
    return result


def create_worktree(task_id):
    name = f'{task_id:04d}-{time.strftime("%Y%m%dT%H%M%S")}-{secrets.token_hex(3)}'
    path = maint_root() / name
    branch = f'forge-maint/{name}'
    forge.git('worktree', 'add', '-q', '-b', branch, str(path), 'HEAD', cwd=forge.ROOT)
    return name, path, branch


def remove_worktree(path):
    forge.git('worktree', 'remove', '--force', str(path), check=False, cwd=forge.ROOT)


def maintenance(conn, row, failure, deadline, previous=''):
    """Returns (outcome, record). outcome: integrated | needs_approval | rejected."""
    task_id = row[0]
    name, path, branch = create_worktree(task_id)
    record = {'id': name, 'task_id': task_id, 'branch': branch, 'worktree': str(path), 'failure': asdict(failure), 'created_at': forge.now()}
    record['failure']['evidence'] = record['failure']['evidence'][-4000:]
    forge.event(conn, task_id, 'maintenance_started', f'{name} on {branch}')
    prompt = ('Forge infrastructure failure. Diagnose and fix it in this isolated worktree; add a regression test.\n'
              f'Stage: {failure.stage}\nSummary: {failure.summary}\nFailing test modules: {", ".join(failure.failing_modules) or "n/a"}\n'
              + (f'A previous maintenance attempt was rejected: {previous}\n' if previous else '')
              + forge.fenced('Failure evidence', failure.evidence[-MAX_EVIDENCE_CHARS:]))
    try:
        record['proposal'] = forge.claude_report(task_id, f'maintenance-{name}', 'cendavo-maintainer', prompt, deadline, True, cwd=path)
        diff = worktree_diff(path)
        if not diff.strip():
            return finish(conn, record, 'rejected', 'maintainer made no changes', path)
        record['patch_sha256'] = hashlib.sha256(diff.encode()).hexdigest()
        write_private(sup_dir() / 'patches' / f'{name}.diff', diff)
        assessment = assess_patch(diff)
        record['assessment'] = asdict(assessment)
        if assessment.violations:
            return finish(conn, record, 'rejected', '; '.join(assessment.violations), path)
        # Independent validation: sandboxed tests in the worktree, then a separate read-only security review.
        forge.tests(task_id, deadline, root=path)
        verdict, review = forge.review(task_id, f'maintenance-security-{name}', 'cendavo-security-reviewer',
                                       forge.review_prompt('SECURITY REVIEW of a proposed Forge infrastructure patch (it changes the '
                                                           'automation that runs agent-written code; scrutinise sandbox, permission and '
                                                           'secret handling)', failure.summary, diff), deadline)
        record['security_verdict'] = verdict
        if verdict != 'PASS':
            return finish(conn, record, 'rejected', f'security review {verdict}: {review[:300]}', path)
        if worktree_diff(path) != diff:
            return finish(conn, record, 'rejected', 'patch changed during validation', path)
        forge.git('-c', 'user.name=Cendavo Forge', '-c', 'user.email=forge@localhost', 'commit', '-q', '-m',
                  f'Forge maintenance: {failure.summary[:60]}', cwd=path)
        record['commit'] = forge.git('rev-parse', 'HEAD', cwd=path).stdout.strip()
        if assessment.approvals:
            record['status'] = 'pending'
            save_maintenance(record)
            forge.event(conn, task_id, 'maintenance_needs_approval', f'{name}: ' + '; '.join(assessment.approvals)[:500])
            return 'needs_approval', record
        return integrate(conn, record)
    except forge.RateLimited:
        record['status'] = 'interrupted'
        save_maintenance(record)
        remove_worktree(path)
        raise
    except forge.SecurityFailure as exc:
        # e.g. the maintainer touched the live checkout: record, discard the proposal and stop for the owner.
        finish(conn, record, 'rejected', f'security failure: {exc}', path)
        raise
    except forge.StageFailure as exc:
        return finish(conn, record, 'rejected', f'validation failed in {exc.stage}: see {exc.log}', path)
    except RuntimeError as exc:
        return finish(conn, record, 'rejected', str(exc), path)


def finish(conn, record, outcome, reason, path=None):
    record['status'] = outcome
    record['reason'] = reason
    save_maintenance(record)
    if path is not None:
        remove_worktree(path)
        # The temporary branch is Forge's own; drop it so rejected proposals cannot be integrated later.
        forge.git('branch', '-D', record['branch'], check=False, cwd=forge.ROOT)
    forge.event(conn, record['task_id'], f'maintenance_{outcome}', f'{record["id"]}: {reason}'[:500])
    return outcome, record


def save_maintenance(record):
    write_private(sup_dir() / 'maintenance' / f'{record["id"]}.json', json.dumps(record, indent=2))


def load_maintenance(name):
    if not re.fullmatch(r'[\w-]+', name):
        raise SystemExit('invalid maintenance id')
    return json.loads((sup_dir() / 'maintenance' / f'{name}.json').read_text())


def integrate(conn, record):
    """Cherry-pick a validated maintenance commit onto the live branch, re-test it, then fast-forward the task's
    workspace and keep its checkpoint valid when the task change is byte-identical."""
    live = forge.ROOT
    commit = record['commit']
    expected = forge.git('diff', f'{commit}^', commit, cwd=live).stdout
    if hashlib.sha256(expected.encode()).hexdigest() != record['patch_sha256']:
        return finish(conn, record, 'rejected', 'commit does not match the validated patch', Path(record['worktree']))
    files = forge.git('diff', '--name-only', f'{commit}^', commit, cwd=live).stdout.split()
    if forge.git('status', '--porcelain', '--', *files, cwd=live).stdout.strip():
        return finish(conn, record, 'rejected', 'files touched by the patch have uncommitted changes in the live checkout', Path(record['worktree']))
    task_id = record['task_id']
    ws = forge.task_workspace(task_id)
    task_changes = forge.changed_names(cwd=ws) if ws.exists() else set()
    if task_changes & set(files):
        return finish(conn, record, 'rejected', 'patch overlaps the task change', Path(record['worktree']))
    old = forge.git('rev-parse', 'HEAD', cwd=live).stdout.strip()
    before = task_change(conn, task_id, old)
    picked = forge.git('cherry-pick', commit, check=False, cwd=live)
    if picked.returncode:
        forge.git('cherry-pick', '--abort', check=False, cwd=live)
        return finish(conn, record, 'rejected', 'cherry-pick failed: ' + picked.stderr[:200], Path(record['worktree']))
    new = forge.git('rev-parse', 'HEAD', cwd=live).stdout.strip()
    record['integrated_commit'] = new
    try:
        forge.tests(task_id, time.monotonic() + 1800, root=live)
    except Exception as exc:  # revert keeps history intact and only touches the patch's own files
        forge.git('-c', 'user.name=Cendavo Forge', '-c', 'user.email=forge@localhost', 'revert', '--no-edit', new, check=False, cwd=live)
        sync_workspace(conn, task_id, old, before)
        return finish(conn, record, 'rejected', f'post-integration tests failed and the patch was reverted: {exc}', Path(record['worktree']))
    sync_workspace(conn, task_id, old, before)
    return finish(conn, record, 'integrated', f'{commit[:12]} -> {new[:12]}', Path(record['worktree']))


def task_change(conn, task_id, baseline):
    """The task's change text in its workspace (None when it has no workspace)."""
    if not forge.task_workspace(task_id).exists():
        return None
    with forge.task_context(conn, task_id):
        return forge.change_snapshot(baseline)[0]


def sync_workspace(conn, task_id, old, before):
    """Fast-forward the task workspace to the live HEAD (its uncommitted task files are disjoint from the patch)."""
    ws = forge.task_workspace(task_id)
    new = forge.git('rev-parse', 'HEAD', cwd=forge.ROOT).stdout.strip()
    if ws.exists() and new != old:
        merged = forge.git('merge', '--ff-only', '-q', new, cwd=ws, check=False)
        if merged.returncode:
            raise forge.MaintenanceRequired(f'Task workspace could not follow the live branch to {new[:12]}: {merged.stderr[:200]}')
    rebase_checkpoints(old, new, before, conn, task_id)


def rebase_checkpoints(old, new, before, conn=None, task_id=None):
    """Move checkpoints from `old` to `new` HEAD only if the task's change is byte-identical relative to `new`.

    Fingerprints hash that change, so identical text keeps every validated stage valid; otherwise only the
    Strategist report survives and the task is fully revalidated.
    """
    if conn is not None and task_id is not None:
        after = task_change(conn, task_id, new)
    else:
        after = forge.change_snapshot(new)[0]
    for path in (forge.STATE / 'checkpoints').glob('*.json'):
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if data.get('baseline') != old:
            continue
        if before is None or before != after:
            data['stages'] = {k: v for k, v in data['stages'].items() if k == 'strategy'}
        data['baseline'] = new
        write_private(path, json.dumps(data))


# Supervisor loop ------------------------------------------------------------------------
def default_reexec():
    """Reload Forge code after an integration by replacing this process; state lives on disk."""
    # The owner approved provider network access for this run; the approval covers the continuation only.
    os.execv(sys.executable, [sys.executable, str(Path(__file__).resolve()), 'run', '--continue', '--approve-provider-network'])


def attempt(conn, row, deadline, state, reexec):
    """Run one task with bounded recovery. Returns 'completed', 'next' or 'stop'."""
    task_id = row[0]
    previous_rejection = ''
    while True:
        if forge.STOP.exists() or time.monotonic() >= deadline:
            return 'stop'
        try:
            forge.run_task(conn, row, deadline)
            return 'completed'
        except KeyboardInterrupt:
            forge.set_state(conn, task_id, 'interrupted', 'Interrupted by operator')
            return 'stop'
        except Exception as exc:  # classified below; nothing is swallowed silently
            failure = classify(exc, task_id)
        # Recovery attempts are bounded by the supervisor, not by the queue's retry budget.
        conn.execute('UPDATE tasks SET attempts=MAX(attempts-1,0) WHERE id=?', (task_id,))
        conn.commit()
        if failure.kind == LIMIT:
            forge.set_state(conn, task_id, 'interrupted', failure.summary)
            report_failure(conn, failure, 'stopped', 'provider usage limit; resume after it resets (no paid fallback)')
            return 'stop'
        if failure.kind == SECURITY:
            forge.set_state(conn, task_id, 'blocked', failure.summary)
            report_failure(conn, failure, 'stopped', 'security failures always need the owner')
            return 'stop'
        if failure.kind in (ENVIRONMENT, HUMAN):
            forge.set_state(conn, task_id, 'interrupted', failure.summary)
            report_failure(conn, failure, 'stopped', 'cannot be fixed by an agent; see report')
            return 'stop'
        if failure.kind == PRODUCT:
            n = bump(state, 'repairs', task_id)
            if n > MAX_PRODUCT_REPAIRS:
                forge.set_state(conn, task_id, 'failed', failure.summary)
                report_failure(conn, failure, 'stopped', f'product repair limit ({MAX_PRODUCT_REPAIRS}) reached')
                return 'stop'
            report_failure(conn, failure, f'product repair {n}/{MAX_PRODUCT_REPAIRS}')
            try:
                repair_product(conn, row, failure, deadline)
            except forge.RateLimited as exc:
                report_failure(conn, Failure(LIMIT, task_id, 'repair', str(exc)), 'stopped')
                forge.set_state(conn, task_id, 'interrupted', str(exc))
                return 'stop'
            except Exception as exc:
                kind = SECURITY if isinstance(exc, forge.SecurityFailure) else HUMAN
                forge.set_state(conn, task_id, 'blocked' if kind == SECURITY else 'failed', str(exc))
                report_failure(conn, Failure(kind, task_id, 'repair', str(exc)), 'stopped')
                return 'stop'
            continue
        # Infrastructure
        n = bump(state, 'maintenance', task_id)
        if n > MAX_MAINTENANCE:
            forge.set_state(conn, task_id, 'interrupted', failure.summary)
            report_failure(conn, failure, 'stopped', f'maintenance limit ({MAX_MAINTENANCE}) reached')
            return 'stop'
        report_failure(conn, failure, f'maintenance {n}/{MAX_MAINTENANCE}')
        try:
            outcome, record = maintenance(conn, row, failure, deadline, previous_rejection)
        except forge.RateLimited as exc:
            forge.set_state(conn, task_id, 'interrupted', str(exc))
            report_failure(conn, Failure(LIMIT, task_id, 'maintenance', str(exc)), 'stopped')
            return 'stop'
        except Exception as exc:  # security failures and unexpected maintenance errors always need the owner
            kind = SECURITY if isinstance(exc, forge.SecurityFailure) else HUMAN
            forge.set_state(conn, task_id, 'blocked' if kind == SECURITY else 'interrupted', str(exc))
            report_failure(conn, Failure(kind, task_id, 'maintenance', str(exc)), 'stopped')
            return 'stop'
        if outcome == 'integrated':
            forge.set_state(conn, task_id, 'queued', 'Resuming after validated maintenance')
            reexec()  # real runs never return; resumes via `run --continue`
            continue
        if outcome == 'needs_approval':
            forge.set_state(conn, task_id, 'interrupted', f'Maintenance {record["id"]} awaits approval')
            report_failure(conn, failure, 'awaiting approval',
                           f'review .cendavo-run/supervisor/patches/{record["id"]}.diff then '
                           f'`python3 scripts/supervisor.py approve {record["id"]}` or `reject`')
            return 'stop'
        previous_rejection = record.get('reason', '')


def configure_limits(state, repairs=None, maintenance=None):
    """Recovery budgets from forge.config.json `limits`, optionally overridden for this run (capped)."""
    global MAX_PRODUCT_REPAIRS, MAX_MAINTENANCE
    limits = forge.load_config()['limits']
    cap = forge.CAPS['limits']
    MAX_PRODUCT_REPAIRS = state.setdefault('max_repairs', min(cap, repairs or limits['product_repairs']))
    MAX_MAINTENANCE = state.setdefault('max_maintenance', min(cap, maintenance or limits['maintenance_attempts']))


def supervise(conn, hours, max_tasks, cont=False, reexec=default_reexec, repairs=None, maintenance=None):
    state = load_state()
    if cont and state.get('deadline_epoch'):
        remaining = state['deadline_epoch'] - time.time()
    else:
        remaining = hours * 3600
        state = {'repairs': {}, 'maintenance': {}, 'deadline_epoch': time.time() + remaining, 'max_tasks': max_tasks, 'done': 0}
    configure_limits(state, repairs, maintenance)
    save_state(state)
    forge.progress(None, 'supervisor', f'limits: {MAX_PRODUCT_REPAIRS} product repair(s), {MAX_MAINTENANCE} maintenance attempt(s) per task')
    deadline = time.monotonic() + max(0, remaining)
    max_tasks = state.get('max_tasks', max_tasks)
    while time.monotonic() < deadline and state.get('done', 0) < max_tasks and not forge.STOP.exists():
        row = conn.execute('SELECT id,priority,title,attempts FROM tasks WHERE state="queued" AND attempts<? ORDER BY priority,id LIMIT 1',
                           (forge.MAX_RETRIES + 1,)).fetchone()
        if not row:
            break
        result = attempt(conn, row, deadline, state, reexec)
        state['done'] = state.get('done', 0) + 1
        save_state(state)
        if result == 'stop':
            break
    return forge.summary(conn)


def preflight(conn):
    if forge.STOP.exists():
        return 'STOP file exists. Use `python3 scripts/forge.py resume` after review.'
    if forge.ACTIVE.exists():
        return f'An earlier child process may still be running. Inspect {forge.ACTIVE}.'
    issue = forge.check_tools()
    if issue:
        return issue
    if forge.git('rev-parse', '--verify', 'HEAD', check=False).returncode:
        return 'Commit initial repository state before running Forge.'
    note = forge.frontend_plugin_note()
    if note:
        forge.event(conn, None, 'warning', note)
    return None


def diagnose(conn, task_id=None):
    """Classify the most recent failure from the queue and logs without invoking any agent."""
    q = 'SELECT id,state,error FROM tasks WHERE error IS NOT NULL' + (' AND id=?' if task_id else '') + ' ORDER BY updated_at DESC LIMIT 1'
    row = conn.execute(q, (task_id,) if task_id else ()).fetchone()
    if not row:
        return {'diagnosis': 'no recorded task failure'}
    tid, state, error = row
    match = re.search(r'^(\S+) exited \d+; see (\S+)$', error or '')
    exc = forge.StageFailure(error, match.group(1), match.group(2)) if match else RuntimeError(error)
    if 'provider limit' in (error or ''):
        exc = forge.RateLimited(error)
    elif (error or '').startswith(('Unit-test failure involves runner/sandbox infrastructure', 'Debugger classified failure')):
        # Forge stopped its own unit-test repair; rebuild the evidence from the task's latest unit-test log.
        logs = sorted(forge.LOGS.glob(f'{tid:04d}-unit-tests-*.log'), key=lambda p: p.stat().st_mtime)
        cause = forge.StageFailure(f'unit-tests failed; see {logs[-1]}', 'unit-tests', logs[-1]) if logs else None
        kind = 'INFRASTRUCTURE'
        if error.startswith('Debugger'):
            first = (latest_report_text(tid, ('debug-',)).strip().splitlines() or [''])[0]
            kind = first.split(':', 1)[-1].strip() if first.startswith('CLASSIFICATION:') else 'UNKNOWN'
        exc = forge.MaintenanceRequired(error, cause, kind)
    failure = classify(exc, tid)
    return {'task': tid, 'state': state, 'kind': failure.kind, 'stage': failure.stage, 'summary': failure.summary,
            'failing_test_modules': failure.failing_modules, 'log': failure.log,
            'evidence_tail': failure.evidence[-2500:]}


def watch(follow=True, lines=40):
    """Print progress lines as Forge and the Supervisor emit them (agent tool calls, stages, heartbeats)."""
    path = forge.STATE / 'progress.jsonl'
    def show(raw):
        try:
            item = json.loads(raw)
        except ValueError:
            return
        print(f"{item['at'][11:19]} task={item.get('task') or '-'} {item['kind']}: {item['detail']}", flush=True)
    while not path.exists():
        if not follow:
            return 0
        time.sleep(1)
    with path.open() as f:
        for raw in f.readlines()[-lines:]:
            show(raw)
        while follow:
            raw = f.readline()
            if raw:
                show(raw)
            else:
                time.sleep(0.5)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description='Forge Supervisor: bounded autonomous recovery')
    sub = parser.add_subparsers(dest='command', required=True)
    run = sub.add_parser('run')
    run.add_argument('--hours', type=float, default=8)
    run.add_argument('--max-tasks', type=int, default=10)
    run.add_argument('--continue', dest='cont', action='store_true', help='internal: resume after integration re-exec')
    run.add_argument('--approve-provider-network', action='store_true', help='explicitly approve Claude model connections for this run')
    run.add_argument('--max-repairs', type=int, help='product repairs per task (default from forge.config.json, capped)')
    run.add_argument('--max-maintenance', type=int, help='maintenance attempts per task (default from forge.config.json, capped)')
    w = sub.add_parser('watch', help='stream Forge progress (.cendavo-run/progress.jsonl)')
    w.add_argument('--no-follow', action='store_true')
    w.add_argument('--lines', type=int, default=40)
    d = sub.add_parser('diagnose')
    d.add_argument('--task', type=int)
    sub.add_parser('approvals')
    for name in ('approve', 'reject'):
        p = sub.add_parser(name)
        p.add_argument('id')
    args = parser.parse_args(argv)
    if args.command == 'watch':
        return watch(not args.no_follow, args.lines)
    if args.command == 'run':  # validate before touching any state
        if not math.isfinite(args.hours) or args.hours <= 0 or args.hours > 8 or args.max_tasks <= 0:
            parser.error('hours must be >0 and <=8; max-tasks must be >0')
        for value in (args.max_repairs, args.max_maintenance):
            if value is not None and not 1 <= value <= forge.CAPS['limits']:
                parser.error(f"repair limits must be 1..{forge.CAPS['limits']}")
    conn = forge.ensure_state()
    if args.command == 'diagnose':
        print(json.dumps(diagnose(conn, args.task), indent=2))
        return 0
    if args.command == 'approvals':
        for path in sorted((sup_dir() / 'maintenance').glob('*.json')):
            rec = json.loads(path.read_text())
            if rec.get('status') == 'pending':
                print(json.dumps({k: rec.get(k) for k in ('id', 'task_id', 'branch', 'commit', 'assessment')}, indent=2))
        return 0
    if args.command in ('approve', 'reject'):
        lock = (forge.STATE / 'run.lock').open('w')  # never integrate under an active runner
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('Another Forge runner is active.', file=sys.stderr)
            return 2
        rec = load_maintenance(args.id)
        if rec.get('status') != 'pending':
            print(f'{args.id} is {rec.get("status")}, not pending', file=sys.stderr)
            return 2
        if args.command == 'reject':
            finish(conn, rec, 'rejected', 'rejected by owner', Path(rec['worktree']))
            return 0
        forge.event(conn, rec['task_id'], 'maintenance_approved', f'{args.id} approved by owner')
        outcome, rec = integrate(conn, rec)
        print(f'{args.id}: {outcome} ({rec.get("reason", "")})')
        if outcome == 'integrated':
            forge.set_state(conn, rec['task_id'], 'queued', 'Resuming after approved maintenance')
            print('Run `./scripts/supervise.sh` to resume.')
        return 0 if outcome == 'integrated' else 2
    if not args.approve_provider_network:
        print('Model network access requires --approve-provider-network for this run.', file=sys.stderr)
        return 2
    lock = (forge.STATE / 'run.lock').open('w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print('Another Forge runner is active.', file=sys.stderr)
        return 2
    issue = preflight(conn)
    if issue:
        forge.event(conn, None, 'paused', issue)
        print(issue, file=sys.stderr)
        return 2
    # Like `forge.py run`: never auto-requeue stopped work; the owner uses `forge.py resume` after review.
    conn.execute('UPDATE tasks SET state="interrupted",updated_at=?,error="Runner exited during task; inspect working tree before resume" WHERE state="running"', (forge.now(),))
    conn.commit()
    print(json.dumps(supervise(conn, args.hours, args.max_tasks, args.cont, repairs=args.max_repairs,
                               maintenance=args.max_maintenance), indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
