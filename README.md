<p align="center">
  <img src="https://raw.githubusercontent.com/javamercy/warmpass/main/assets/hero.png" alt="Warmpass" width="640" />
</p>

<p align="center">
  <strong>Run and schedule coding agent warmups so your usage windows start early.</strong>
</p>

<p align="center">
  <a href="https://github.com/javamercy/warmpass/actions/workflows/ci.yml"><img src="https://github.com/javamercy/warmpass/actions/workflows/ci.yml/badge.svg" alt="CI" /></a>
  <a href="https://pypi.org/project/warmpass/"><img src="https://img.shields.io/pypi/v/warmpass" alt="PyPI" /></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.14%2B-blue" alt="Python 3.14+" /></a>
  <a href="https://github.com/javamercy/warmpass/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="License: MIT" /></a>
</p>

---

Warmpass sends a minimal, non-interactive prompt to supported coding agents (Claude Code, Codex, Antigravity) on demand, or registers native OS jobs (`launchd` on macOS, Task Scheduler on Windows) to trigger warmups automatically on a daily or weekly schedule.

> **Early development:** Warmpass is in early development (`0.1.x`). Commands, output formats, and schedule records may change between releases.

## Requirements & Supported Agents

- **Python:** 3.14 or newer (or install with `uv`, which provisions Python 3.14 automatically).
- **Operating system:**
  - `warmup`: macOS, Windows, and Linux.
  - `schedule`: macOS (`launchd`) and Windows (`Task Scheduler`).
- **Coding agent CLI:** At least one supported agent installed on `PATH` and already signed in:

| Agent | `--agent` value | Required CLI | Prerequisite |
|---|---|---|---|
| Claude Code | `claude` | `claude` | Installed on `PATH` and signed in |
| Codex | `codex` | `codex` | Installed on `PATH` and signed in |
| Antigravity | `antigravity` | `agy` | Installed on `PATH` and signed in |

## Installation

Recommended (with [uv](https://docs.astral.sh/uv/)):

```sh
uv tool install warmpass
```

With `pip` (requires Python 3.14+):

```sh
pip install warmpass
```

Verify the installation:

```sh
warmpass --help
```

## Quick Start

Run an immediate warmup:

```sh
warmpass warmup --agent codex
```

Schedule recurring warmups every 2 hours between 09:00 and 17:00 local time (09:00, 11:00, 13:00, 15:00):

```sh
warmpass schedule add --agent codex --trigger daily --from 09:00 --until 17:00 --every 2h
```

Inspect your active schedules:

```sh
warmpass schedule list
```

## Usage

### `warmpass warmup`

Send an immediate warmup prompt to an agent.

```sh
warmpass warmup --agent <claude|codex|antigravity> [--model <model-id>]
```

| Option | Required | Description |
|---|---|---|
| `--agent` | Yes | Target agent: `claude`, `codex`, or `antigravity`. |
| `--model` | No | Model ID forwarded directly to the agent CLI. Omit to use the agent's configured default. |

**Examples:**

```sh
# Warm up Claude Code with its default model
warmpass warmup --agent claude

# Warm up Codex with an explicit model
warmpass warmup --agent codex --model gpt-6-luna
```

**Output & exit codes:**
- Attempt status, interactive spinner (when attached to a TTY), and errors are written to `stderr`; completion logs are written to `stdout`.
- Exits `0` on success, `1` on warmup failure (agent CLI not found, timeout, or non-zero agent exit), and `2` on invalid arguments.

---

### `warmpass schedule`

Manage recurring OS-scheduled warmups (macOS and Windows).

#### Add a schedule

```sh
warmpass schedule add \
  --agent <claude|codex|antigravity> \
  --trigger <daily|weekly> \
  --every <1h|2h|3h|4h|5h> \
  [--from HH:MM] \
  [--until HH:MM] \
  [--day <weekday>]... \
  [--model <model-id>]
```

| Option | Required | Description |
|---|---|---|
| `--agent` | Yes | Target agent: `claude`, `codex`, or `antigravity`. |
| `--trigger` | Yes | Recurrence kind: `daily` or `weekly`. |
| `--every` | Yes | Interval between runs: `1h`, `2h`, `3h`, `4h`, or `5h`. |
| `--from` | No | Window start in 24-hour local time (`HH:MM`, inclusive). Defaults to `00:00`. |
| `--until` | No | Window end in 24-hour local time (`HH:MM`, exclusive). Defaults to end of day (`24:00`). |
| `--day` | Weekly only | Weekday (`monday`–`sunday`, case-insensitive). Repeat for multiple days; cannot be combined with `--trigger daily`. |
| `--model` | No | Model ID saved with the schedule and forwarded to `warmpass warmup`. |

**Window rules:**
- Windows are half-open `[from, until)`: `--from 09:00 --until 17:00 --every 2h` runs at `09:00`, `11:00`, `13:00`, and `15:00` (not `17:00`).
- `daily` schedules may cross midnight (e.g., `--from 22:00 --until 04:00 --every 2h` runs at `22:00`, `00:00`, `02:00`).
- `weekly` schedules cannot cross midnight and require at least one `--day` without duplicates.

**Examples:**

```sh
# Daily: every 5 hours starting at 08:00 until end of day (08:00, 13:00, 18:00, 23:00)
warmpass schedule add --agent claude --trigger daily --from 08:00 --every 5h

# Weekly: weekdays from 07:30 to 17:30 every 5 hours (07:30, 12:30) with an explicit model
warmpass schedule add \
  --agent codex \
  --trigger weekly \
  --day monday --day tuesday --day wednesday --day thursday --day friday \
  --from 07:30 --until 17:30 --every 5h \
  --model gpt-6-luna
```

#### Inspect and remove schedules

```sh
# List all schedules (reconciled against the OS scheduler)
warmpass schedule list

# Show one schedule by UUID
warmpass schedule get <schedule-id>

# Remove one schedule and its OS job
warmpass schedule remove <schedule-id>

# Remove all Warmpass schedules and OS jobs (pass -y/--yes to skip confirmation)
warmpass schedule clear
warmpass schedule clear --yes
```

## How It Works & Behavior

### Warmup execution
- Sends a minimal prompt (`"ONLY reply with OK. Do not use tools or inspect files."`) to the selected agent CLI with `stdin` closed, a 60-second timeout, and a temporary working directory.
- Runs agents non-interactively with minimal side effects where supported (e.g., ephemeral/no-session-persistence, read-only/no tools, slash commands disabled).
- Each warmup spends a minimal amount of agent usage quota—that is what starts the usage window.

### OS scheduling & drift detection
- `warmpass schedule add` saves a JSON record locally and registers one native OS job prefixed with `dev.warmpass.schedule.<uuid>` that runs `warmpass warmup --agent <agent> [--model <model>]`:
  - **macOS:** User LaunchAgent at `~/Library/LaunchAgents/dev.warmpass.schedule.<uuid>.plist`, managed via `launchctl`. Captures your `PATH` at registration time so unattended runs can locate agent CLIs.
  - **Windows:** Scheduled Task named `dev.warmpass.schedule.<uuid>`, managed via `schtasks.exe`.
- `warmpass schedule list` and `get` reconcile saved records against the OS scheduler and report an error if an OS job is missing, orphaned, or modified outside Warmpass.
- Warmpass only touches OS jobs with the `dev.warmpass.schedule.` prefix.

### Missed runs & sleep
- **macOS:** `launchd` (`StartCalendarInterval`) may run a missed trigger after waking from sleep.
- **Windows:** Missed triggers while asleep or powered off are skipped rather than run late.

### Local files & logs
- **macOS:**
  - Schedule records: `~/Library/Application Support/Warmpass/`
  - Scheduled job logs (`stdout`/`stderr`): `~/Library/Logs/Warmpass/`
- **Windows:**
  - Schedule records: `%LOCALAPPDATA%\Warmpass\`

### Before uninstalling or reinstalling
Run `warmpass schedule clear` before uninstalling Warmpass (or changing where the `warmpass` binary is installed) so orphaned OS jobs are not left behind.

## Development

Requires Python 3.14+ and [uv](https://docs.astral.sh/uv/):

```sh
git clone https://github.com/javamercy/warmpass.git
cd warmpass
uv sync --locked --dev
```

Run lint, type checks (`pyrefly`), and formatting:

```sh
uv run --locked python scripts/check.py
```

Run the test suite (never invokes real agents or modifies real OS jobs):

```sh
uv run --locked python -m pytest
```

Bug reports and pull requests are welcome at [GitHub Issues](https://github.com/javamercy/warmpass/issues).

## License

MIT License. See [LICENSE](https://github.com/javamercy/warmpass/blob/main/LICENSE).
