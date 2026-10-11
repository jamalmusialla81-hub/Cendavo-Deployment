# Forge on Windows (WSL2)

**Status: implemented, verified on macOS only. Windows/WSL2 support is not complete until the steps below pass on a real Windows 11 PC.**

Forge never runs natively on Windows: there is no supported sandbox for agent-written code there, so `forge.py` refuses to start (as it does on WSL1). On Windows, Forge runs inside a dedicated **WSL2** Linux distribution; JARVIS can run natively on Windows and talk to Forge through `wsl.exe`.

| Host | Forge's checks stage (build/tests of agent-written code) | Agents' Bash (Claude Code) |
| --- | --- | --- |
| macOS | Seatbelt via `sandbox-exec` (unchanged) | Claude Code sandbox (Seatbelt) |
| Linux / WSL2 | bubblewrap: own mount, network, PID and user namespaces | Claude Code sandbox (bubblewrap + socat) |
| Native Windows, WSL1 | refused | refused |

Forge never falls back to running agent-written code unsandboxed: the checks stage raises, preflight (`check_tools`) refuses to start a run, and agent sessions set `failIfUnavailable`.

## The Linux sandbox

`scripts/forge_platform.py` builds the bubblewrap profile with the same boundaries as the macOS profile:

- Visible: system runtime directories (read-only), a minimal `/etc` (linker cache, time zone, users/groups, CA certificates), the install roots of `python3`/`node`/`git` if they live outside the system directories (never a whole home directory), the project (read-write) and one private temporary directory. Nothing else exists inside the sandbox: not the home directory, other projects, `~/.ssh`, or Forge's queue.
- Hidden at any depth: `.git`, `.cendavo-run`, `.cendavo-tools`, `.env*`, `secret*`, `credential*`, key files, `auth.json`, `token.json`, `.npmrc` … (directories become empty read-only tmpfs; files read as empty and cannot be written).
- Read-only: Forge's scripts and tests, `.claude/`, `.github/`, `forge.config.json`, `.gitignore`, `CLAUDE.md`, `AGENTS.md`.
- `--unshare-all` (no network), `--cap-drop ALL`, `--new-session`, `--die-with-parent`; Forge's process-group termination, per-command timeouts and the open-file cap apply as on macOS.

Difference from macOS: bubblewrap hides protected names that exist when the stage starts; a file a test creates later under a protected name is visible to that test (it contains nothing secret). Paths outside the project are not merely denied but absent.

`python3 scripts/forge.py doctor` checks: WSL2 (not WSL1 or native Windows), that the project is on the Linux filesystem (not `/mnt/c`), POSIX permissions and case-sensitive names, `flock`, process-group termination, resource limits, a live bubblewrap self-test (project writable; outside, secrets, Forge state, tests, network and home denied), and Claude Code's Linux sandbox prerequisites (`bwrap`, `socat`). Preflight refuses to run while any required check fails.

## 1. Prepare WSL2 (Windows 11, PowerShell)

```powershell
wsl --install -d Ubuntu-24.04
wsl -l -v          # VERSION must be 2 for Ubuntu-24.04
```

## 2. Install tools (inside Ubuntu)

```bash
sudo apt update && sudo apt install -y git python3 nodejs bubblewrap socat
```

Install Claude Code inside WSL2 following [Anthropic's setup instructions](https://code.claude.com/docs/en/setup), then sign in with your Claude Max subscription: `claude auth login`, and check `claude auth status`. Forge only accepts a claude.ai Max login; API keys are stripped and refused.

If `forge.py doctor` reports that bubblewrap cannot create namespaces, your distribution restricts unprivileged user namespaces (Ubuntu 24.04 does this through AppArmor on some kernels). Do not disable the restriction globally without deciding that deliberately; Ubuntu's `bubblewrap` package ships an AppArmor profile that permits bwrap specifically. Send the doctor output if it still fails.

## 3. Get this branch into WSL2 (no push needed)

Copy `Cendavo-linux-wsl-backend.bundle` (from `~/Documents/Cendavo-backups/` on the Mac) to Windows, then inside Ubuntu:

```bash
git clone -b forge/linux-wsl-backend /mnt/c/Users/<you>/Downloads/Cendavo-linux-wsl-backend.bundle ~/Cendavo
cd ~/Cendavo
```

Keep the checkout in the Linux filesystem (`~/...`), never under `/mnt/c`: Windows drives ignore `chmod`, are case-insensitive and lock unreliably, and the doctor refuses them.

## 4. Verify without any agent

```bash
./scripts/verify_wsl.sh
```

It must end with `ALL NON-AGENT WSL2 CHECKS PASSED`. It runs the doctor, the platform tests (including the real bubblewrap boundary tests, which must not be skipped), the full test suite, Forge's checks stage through bubblewrap with throwaway state, the read-only `inspect` interface and the Claude login check (no model call).

## 5. Verify Claude Code's Linux agent sandbox (optional, one short Max session)

```bash
python3 scripts/verify_agent_sandbox.py --i-understand-this-uses-claude-max
```

It runs one Claude session with Forge's exact Builder permissions (without the Builder persona) in a disposable clone beside the checkout, and checks from disk that `.env`, the home directory, network, writes outside the workspace, control files and commits are blocked while ordinary work succeeds. Exit status 0 means every check held.

## 6. Report back

Send the full output of steps 4 and 5. Windows support should be called complete only when both pass on your PC; until then treat it as unverified. JARVIS-on-Windows integration is verified separately.
