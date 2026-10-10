#!/usr/bin/env python3
"""Local, bounded Claude Builder / Strategist / Codex Auditor runner.

No API keys, push, deploy, email, or billing actions are performed.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import shutil
import signal
import sqlite3
import subprocess
import sys
import time
import platform
import tempfile
from datetime import datetime, timezone

if __package__:
    from .forge_sandbox import build_profile
else:
    from forge_sandbox import build_profile

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / '.cendavo-run'
DB = STATE / 'queue.sqlite3'
STOP = STATE / 'STOP'
REPORTS = STATE / 'reports'
LOGS = STATE / 'logs'
ACTIVE = STATE / 'active-child.json'
MAX_RETRIES = 2
MAX_REVIEW_CYCLES = 2
LOCAL_BIN = ROOT / '.cendavo-tools' / 'node_modules' / '.bin'


class RateLimited(RuntimeError):
    pass
SEED = [
    (1, 'Improve the demo request workflow for a real local service task. Preserve browser-local synthetic data and clear status controls.'),
    (2, 'Improve keyboard and screen-reader access in the site and demo. Keep changes focused and testable.'),
    (3, 'Add a safe way to export synthetic demo requests from the browser without sending them to a server.'),
]


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def git(*args, check=True):
    return subprocess.run(['git', *args], cwd=ROOT, text=True, capture_output=True, check=check)


def ensure_state():
    for path in (STATE, REPORTS, LOGS):
        path.mkdir(mode=0o700, exist_ok=True)
        path.chmod(0o700)
    conn = sqlite3.connect(DB)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY, priority INTEGER NOT NULL, title TEXT NOT NULL, state TEXT NOT NULL DEFAULT "queued", attempts INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, error TEXT)')
    conn.execute('CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, task_id INTEGER, at TEXT NOT NULL, kind TEXT NOT NULL, detail TEXT NOT NULL)')
    conn.commit()
    DB.chmod(0o600)
    return conn


def event(conn, task_id, kind, detail):
    conn.execute('INSERT INTO events(task_id, at, kind, detail) VALUES(?,?,?,?)', (task_id, now(), kind, str(detail)[:2000]))
    conn.commit()
    print(f'[{now()}] task={task_id or "-"} {kind}: {detail}', flush=True)


def add_task(conn, priority, title):
    conn.execute('INSERT INTO tasks(priority,title,created_at,updated_at) VALUES(?,?,?,?)', (priority,title,now(),now()))
    conn.commit()
    event(conn, conn.execute('SELECT last_insert_rowid()').fetchone()[0], 'queued', title)


def set_state(conn, task_id, state, error=None):
    conn.execute('UPDATE tasks SET state=?,updated_at=?,error=? WHERE id=?', (state,now(),error,task_id))
    conn.commit()
    event(conn, task_id, state, error or '')


def clean_tree():
    # Local agent reports and build output are ignored; source must be clean.
    return not git('status','--porcelain').stdout.strip()


def check_tools():
    missing = [name for name in ('claude','codex','git','python3','node') if not (shutil.which(name) or (LOCAL_BIN / name).exists())]
    if missing:
        return f'Missing required CLI(s): {", ".join(missing)}'
    try:
        env = dict(os.environ)
        env.pop('ANTHROPIC_API_KEY', None)
        auth = subprocess.run([str(LOCAL_BIN / 'claude') if (LOCAL_BIN / 'claude').exists() else 'claude','auth','status'], cwd=ROOT, text=True, capture_output=True, timeout=20, env=env)
        data = json.loads(auth.stdout) if auth.returncode == 0 else {}
        method = data.get('authMethod')
        if method not in ('claude.ai','oauth_token'):
            return f'Claude Code is not authenticated with a supported subscription method (reported: {method or "none"}).'
        codex = subprocess.run(['codex','login','status'], cwd=ROOT, text=True, capture_output=True, timeout=20)
        if codex.returncode != 0 or 'ChatGPT' not in (codex.stdout + codex.stderr):
            return 'Codex CLI is not logged in with ChatGPT.'
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        return f'Could not verify CLI authentication: {type(exc).__name__}'
    return None


def terminate_group(pgid):
    """Reap every process in a command group, including surviving descendants."""
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return True
    for _ in range(20):
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.1)
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        return True
    for _ in range(20):
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.1)
    return False


def run_command(argv, stdin, task_id, name, deadline, timeout=1800, sandbox_tmp=None):
    if STOP.exists():
        raise RuntimeError('Manual STOP file found')
    remaining = int(deadline - time.monotonic())
    if remaining < 30:
        raise RuntimeError('Maximum runtime reached')
    env = dict(os.environ)
    env['PATH'] = str(LOCAL_BIN) + os.pathsep + env.get('PATH', '')
    if argv[0] == 'sandbox-exec':
        if sandbox_tmp is None:
            raise ValueError('Sandboxed commands require a private temporary directory')
        for key in ('TMPDIR', 'TMP', 'TEMP', 'XDG_CACHE_HOME'):
            env[key] = str(sandbox_tmp)
        env['HOME'] = str(sandbox_tmp)
        env['GIT_CONFIG_NOSYSTEM'] = '1'
        env['GIT_CONFIG_GLOBAL'] = '/dev/null'
        env['PATH'] = '/Library/Developer/CommandLineTools/usr/bin' + os.pathsep + env['PATH']
        env['PYTHONDONTWRITEBYTECODE'] = '1'
        env['CENDAVO_SANDBOXED'] = '1'
        env.pop('PYTHONPATH', None)
        env.pop('NODE_OPTIONS', None)
    for key in ('ANTHROPIC_API_KEY','OPENAI_API_KEY','CLOUDFLARE_API_TOKEN','CLOUDFLARE_API'):
        env.pop(key, None)
    path = LOGS / f'{task_id:04d}-{name}-{int(time.time())}.log'
    with path.open('w+') as log:
        os.chmod(path, 0o600)
        log.write('command: ' + ' '.join(argv[:4]) + '\nstarted: ' + now() + '\n\n')
        log.flush()
        proc = subprocess.Popen(argv, cwd=ROOT, stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT, text=True, env=env, start_new_session=True)
        ACTIVE.write_text(json.dumps({'pid':proc.pid,'name':name,'task_id':task_id,'started_at':now()}))
        ACTIVE.chmod(0o600)
        started = time.monotonic()
        group_cleaned = False
        try:
            if stdin:
                proc.stdin.write(stdin)
            proc.stdin.close()
            while proc.poll() is None:
                if STOP.exists() or time.monotonic() >= deadline or time.monotonic() - started >= timeout:
                    raise RuntimeError(f'{name} stopped or timed out; see {path}')
                time.sleep(1)
        except KeyboardInterrupt:
            raise
        finally:
            group_cleaned = terminate_group(proc.pid)
            proc.wait()
            if not group_cleaned:
                try:
                    os.killpg(proc.pid, 0)
                except ProcessLookupError:
                    group_cleaned = True
            if group_cleaned:
                ACTIVE.unlink(missing_ok=True)
        if not group_cleaned:
            raise RuntimeError(f'{name} left a child process running; inspect {ACTIVE}')
        log.flush()
        log.seek(0)
        output = log.read().split('\n\n',1)[-1]
        log.seek(0,os.SEEK_END)
        log.write(f'\nexit: {proc.returncode}\n')
    if proc.returncode:
        lower = output.lower()
        if any(term in lower for term in ('rate limit', 'usage limit', 'quota exceeded', 'overloaded')):
            raise RateLimited(f'{name} reached a provider limit; see {path}')
        raise RuntimeError(f'{name} exited {proc.returncode}; see {path}')
    return output


def claude_report(task_id, name, prompt, deadline, writable=False):
    tools = 'Read,Glob,Grep,Edit,Write' if writable else 'Read,Glob,Grep'
    agent = 'cendavo-builder' if writable else 'cendavo-strategist'
    argv = ['claude','-p','--restricted','--strict-mcp-config','--agent',agent,'--permission-mode','dontAsk','--tools',tools,'--allowedTools',tools,'--disallowedTools','mcp__*','--output-format','json','--max-turns','16' if writable else '6']
    raw = run_command(argv, prompt, task_id, name, deadline)
    try:
        payload = json.loads(raw)
        result = payload.get('result', '')
    except ValueError:
        result = raw
        payload = {}
    report = {'at':now(),'agent':agent,'result':result,'usage':{k:payload.get(k) for k in ('total_cost_usd','usage') if k in payload}}
    path = REPORTS / f'{task_id:04d}-{name}.json'
    path.write_text(json.dumps(report,indent=2))
    path.chmod(0o600)
    return result


def codex_review(task_id, prompt, deadline, cycle):
    out = REPORTS / f'{task_id:04d}-audit-{cycle}.txt'
    argv = ['codex','exec','--ephemeral','-s','read-only','-C',str(ROOT),'-o',str(out),'-']
    run_command(argv, prompt, task_id, f'audit-{cycle}', deadline)
    text = out.read_text() if out.exists() else ''
    if not text.strip():
        raise RuntimeError('Codex audit returned no report')
    return text


def tests(task_id, deadline):
    if platform.system() != 'Darwin' or not shutil.which('sandbox-exec'):
        raise RuntimeError('Isolated test execution requires macOS sandbox-exec on this host')
    with tempfile.TemporaryDirectory(prefix='cendavo-sandbox-') as temporary:
        tmp = Path(temporary).resolve()
        profile = build_profile(ROOT, tmp)
        for name, argv in [
            ('build', ['python3','scripts/build_site.py']),
            ('unit-tests', ['python3','-m','unittest','discover','-s','tests','-v']),
            ('site-js', ['node','--check','assets/site.js']),
            ('demo-js', ['node','--check','assets/demo.js']),
        ]:
            run_command(['sandbox-exec','-p',profile,*argv], '', task_id, name, deadline, timeout=300, sandbox_tmp=tmp)


def allowed_changes():
    names = set(git('diff','--name-only').stdout.splitlines())
    names.update(git('ls-files','--others','--exclude-standard').stdout.splitlines())
    protected = ('.github/','.claude/','.git/','.cendavo-run/','.cendavo-tools/',
                 'scripts/forge.py','scripts/forge_sandbox.py','scripts/overnight.sh',
                 'AGENTS.md','CLAUDE.md')
    forbidden = [n for n in names if n.startswith(protected) or n.startswith('.env') or '..' in Path(n).parts]
    if forbidden:
        raise RuntimeError('Builder touched protected files: ' + ', '.join(forbidden))
    return names


def run_task(conn, row, deadline):
    task_id, priority, title, attempts = row
    conn.execute('UPDATE tasks SET attempts=attempts+1 WHERE id=?', (task_id,))
    set_state(conn,task_id,'running')
    if not clean_tree():
        raise RuntimeError('Source tree has uncommitted changes. Commit or stash before running Forge.')
    baseline = git('rev-parse','HEAD').stdout.strip()
    strategy = claude_report(task_id,'strategy',f'Read Cendavo and assess this queued task: {title}. Challenge value, feasibility, cost and risk. Propose the smallest useful implementation. State evidence versus assumptions. Respond in concise sections: PROPOSAL, EVIDENCE, RISKS, BUILDER BRIEF. Do not modify files.',deadline)
    event(conn,task_id,'strategy_complete',f'report {task_id:04d}-strategy.json')
    claude_report(task_id,'builder',f'Implement this approved task in Cendavo: {title}\n\nStrategist report:\n{strategy}\n\nWork only in product and tests. No shell, deployment or secrets. Explain the final changes and remaining risks.',deadline,True)
    names = allowed_changes()
    if not names:
        raise RuntimeError('Builder made no source changes')
    for cycle in range(1,MAX_REVIEW_CYCLES+1):
        review = codex_review(task_id,f'SECURITY PREFLIGHT before executing Claude-edited code for task: {title}. Inspect git diff since {baseline}. Do not execute or edit files. Check for exfiltration, unsafe build/test scripts, unwanted dependencies, protected file changes and scope violations. Start with VERDICT: PASS or VERDICT: FIX and give actionable findings.',deadline,f'preflight-{cycle}')
        event(conn,task_id,'preflight',f'cycle {cycle}')
        if review.lstrip().startswith('VERDICT: PASS'):
            break
        if not review.lstrip().startswith('VERDICT: FIX') or cycle == MAX_REVIEW_CYCLES:
            raise RuntimeError('Security preflight failed or review cycle limit reached')
        claude_report(task_id,f'preflight-fix-{cycle}',f'Fix the security preflight findings for task {title}:\n{review}',deadline,True)
        allowed_changes()
    tests(task_id,deadline)
    for cycle in range(1,MAX_REVIEW_CYCLES+1):
        review = codex_review(task_id,f'Independently audit Claude Builder changes since {baseline} for task: {title}. Inspect git diff and relevant code. Focus on security, correctness, reliability, regressions, honest product claims and meaningful test gaps. Do not edit files. Start your final report with exactly VERDICT: PASS or VERDICT: FIX. Then list evidence and actionable findings.',deadline,cycle)
        event(conn,task_id,'audited',f'cycle {cycle}; report {task_id:04d}-audit-{cycle}.txt')
        if review.lstrip().startswith('VERDICT: PASS'):
            break
        if not review.lstrip().startswith('VERDICT: FIX'):
            raise RuntimeError('Audit verdict missing or malformed')
        if cycle == MAX_REVIEW_CYCLES:
            raise RuntimeError('Review cycle limit reached; manual resolution needed')
        claude_report(task_id,f'fix-{cycle}',f'Fix the actionable findings for task {title}. Codex report:\n{review}\nKeep the approved scope and do not modify protected files. Report each fix.',deadline,True)
        allowed_changes()
        safety = codex_review(task_id,f'SECURITY PREFLIGHT after Claude fixes for task: {title}. Inspect all current changes since {baseline}. Do not execute or edit files. Check for exfiltration, unsafe build/test scripts, unwanted dependencies and scope violations. Start with VERDICT: PASS or VERDICT: FIX.',deadline,f'postfix-preflight-{cycle}')
        if not safety.lstrip().startswith('VERDICT: PASS'):
            raise RuntimeError('Post-fix security preflight did not pass')
        tests(task_id,deadline)
    if STOP.exists() or time.monotonic() >= deadline:
        raise RuntimeError('Stopped before checkpoint')
    git('add','--',*sorted(names.union(allowed_changes())))
    staged = git('diff','--cached','--name-only').stdout.splitlines()
    if not staged:
        raise RuntimeError('No changes to checkpoint')
    git('commit','-m',f'Forge: {title[:65]}')
    sha = git('rev-parse','HEAD').stdout.strip()
    set_state(conn,task_id,'completed')
    event(conn,task_id,'checkpoint',sha)


def summary(conn):
    tasks = conn.execute('SELECT id,state,attempts,title,error FROM tasks ORDER BY id').fetchall()
    estimates = []
    for path in REPORTS.glob('*.json'):
        try:
            cost = json.loads(path.read_text()).get('usage',{}).get('total_cost_usd')
            if isinstance(cost, (int,float)):
                estimates.append(cost)
        except (OSError,ValueError):
            continue
    report = {'generated_at':now(),'branch':git('branch','--show-current').stdout.strip(),'head':git('rev-parse','HEAD',check=False).stdout.strip(),'usage_estimate_usd':round(sum(estimates),4) if estimates else None,'tasks':[{'id':id,'state':state,'attempts':attempts,'title':title,'error':error} for id,state,attempts,title,error in tasks]}
    target = STATE / 'summary.json'
    target.write_text(json.dumps(report,indent=2))
    target.chmod(0o600)
    return report


def main():
    signal.signal(signal.SIGTERM, lambda _signum, _frame: (_ for _ in ()).throw(KeyboardInterrupt()))
    parser = argparse.ArgumentParser(description='Cendavo Forge local overnight runner')
    sub = parser.add_subparsers(dest='command',required=True)
    sub.add_parser('init')
    sub.add_parser('status')
    sub.add_parser('stop')
    sub.add_parser('resume')
    add = sub.add_parser('add');add.add_argument('title');add.add_argument('--priority',type=int,default=5)
    run = sub.add_parser('run');run.add_argument('--hours',type=float,default=8);run.add_argument('--max-tasks',type=int,default=10)
    run.add_argument('--approve-provider-network', action='store_true', help='explicitly approve Claude and Codex model connections for this run')
    args = parser.parse_args()
    conn = ensure_state()
    if args.command == 'init':
        if not conn.execute('SELECT 1 FROM tasks LIMIT 1').fetchone():
            for priority,title in SEED: add_task(conn,priority,title)
    elif args.command == 'add':
        add_task(conn,args.priority,args.title)
    elif args.command == 'status':
        print(json.dumps(summary(conn),indent=2))
    elif args.command == 'stop':
        STOP.write_text(f'Stopped manually at {now()}\n')
        print(f'Stop requested. Active command will finish or time out; runner will not start another task. {STOP}')
    elif args.command == 'resume':
        if ACTIVE.exists():
            print(f'Inspect possible orphan process before resume: {ACTIVE}',file=sys.stderr)
            return 2
        conn.execute('UPDATE tasks SET state="interrupted",updated_at=?,error="Runner exited during task; inspect working tree before resume" WHERE state="running"', (now(),))
        if STOP.exists(): STOP.unlink()
        conn.execute('UPDATE tasks SET state="queued",updated_at=? WHERE state="interrupted"', (now(),))
        conn.commit();print('STOP removed; interrupted tasks returned to queue. Inspect source changes before run.')
    elif args.command == 'run':
        if args.hours <= 0 or args.hours > 8 or args.max_tasks <= 0:
            parser.error('hours must be >0 and <=8; max-tasks must be >0')
        if not args.approve_provider_network:
            print('Model network access requires --approve-provider-network for this run.',file=sys.stderr);return 2
        if STOP.exists():
            print('STOP file exists. Use resume after review.',file=sys.stderr);return 2
        lock = (STATE / 'run.lock').open('w')
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('Another Forge runner is active.',file=sys.stderr);return 2
        if ACTIVE.exists():
            print(f'An earlier child process may still be running. Inspect {ACTIVE} before resume.',file=sys.stderr);return 2
        issue = check_tools()
        if issue:
            event(conn,None,'paused',issue);summary(conn);print(issue,file=sys.stderr);return 2
        if not git('rev-parse','--verify','HEAD',check=False).returncode == 0:
            print('Commit initial repository state before running Forge.',file=sys.stderr);return 2
        deadline = time.monotonic()+args.hours*3600
        conn.execute('UPDATE tasks SET state="interrupted",updated_at=?,error="Runner exited during task; inspect working tree before resume" WHERE state="running"', (now(),))
        conn.commit()
        count=0
        while time.monotonic()<deadline and count<args.max_tasks and not STOP.exists():
            row=conn.execute('SELECT id,priority,title,attempts FROM tasks WHERE state="queued" AND attempts<? ORDER BY priority,id LIMIT 1',(MAX_RETRIES+1,)).fetchone()
            if not row:break
            try:
                run_task(conn,row,deadline)
            except KeyboardInterrupt:
                set_state(conn,row[0],'interrupted','Interrupted by operator');break
            except RateLimited as exc:
                conn.execute('UPDATE tasks SET attempts=attempts-1 WHERE id=?',(row[0],));conn.commit()
                set_state(conn,row[0],'interrupted',str(exc))
                event(conn,row[0],'paused','Provider limit reached; resume after reset')
                break
            except Exception as exc:
                detail=str(exc)
                state='failed' if row[3]+1 >= MAX_RETRIES+1 else 'interrupted'
                set_state(conn,row[0],state,detail)
                # Never retry source-changing work automatically without inspection.
                if not clean_tree():
                    event(conn,row[0],'paused','Uncommitted changes require inspection before resume')
                    break
                if state=='interrupted':
                    conn.execute('UPDATE tasks SET state="queued" WHERE id=?',(row[0],));conn.commit()
                    time.sleep(min(30,5*(row[3]+1)))
            count+=1
        print(json.dumps(summary(conn),indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
