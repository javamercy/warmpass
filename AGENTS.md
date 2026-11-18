# AGENTS.md

## Project

Warmpass is a Python 3.14+ CLI for running and scheduling agent warmups. Source code lives in `src/warmpass/`. The Typer entry point is `warmpass.cli.main:app`, and tests live under `tests/`.

- `warmup` sends a minimal prompt to a coding agent (Claude Code, Codex, Antigravity) to start its 5-hour usage window.
- `schedule` stores a schedule record and registers one OS job per schedule. The job's triggers are computed from the record, and the job runs `warmpass warmup`.
- `handoff` has the target agent summarize the source agent's session, then creates a new target-agent session that starts with the summary.
- `warmup` and `schedule add` accept optional `--model`. Model IDs are opaque strings validated by the agent; omission uses the agent's configured default. Schedules store and forward explicit model selections.

## Development

- Set up the environment with `uv sync --locked --dev`.
- Run lint, type checks (pyrefly), and formatting with `uv run --locked python scripts/check.py`. This command can reformat files, so review the diff after running it.
- Run tests with `uv run --locked python -m pytest`. Run an affected test file or directory first when narrowing down a failure.
- Check command help with `uv run --locked warmpass --help`.

## Rules for every task

- The project is unreleased. Explicitly requested breaking changes do not require migrations or compatibility machinery.
- Preserve documented command syntax, exit codes, and existing schedule records unless the task changes them. When a task changes them, update the docs and state what happens to existing records and installed jobs. Do not add compatibility shims.
- Do not run a real agent or register or remove a real OS job without asking. `warmup` and `handoff` spend agent quota, and `schedule` changes the user's OS.
- Tests never touch real agents, real OS jobs, the real home directory, or real Warmpass state and log locations.
- Verify in this order: the check script, the affected tests, then the full suite. Report what you could not run, such as other platforms or real agents.

## Skills

Load only the skills for the work you are doing. For a review, use the skills the request names.

- [python-architecture](.agents/skills/python-architecture/SKILL.md): which module owns a decision, which way imports point, and whether the structure is proportionate.
- [python-code-quality](.agents/skills/python-code-quality/SKILL.md): how functions, types, exceptions, and docstrings are written.
- [python-cli-design](.agents/skills/python-cli-design/SKILL.md): what users and installed jobs see, including option names, help, stdout and stderr, messages, and exit codes.
- [python-integration-reliability](.agents/skills/python-integration-reliability/SKILL.md): what happens when an agent call, OS job registration, or file write fails, times out, or partly succeeds.
- [python-testing](.agents/skills/python-testing/SKILL.md): which behavior gets a test, how to fake agents and schedulers, and what tests may touch.

If you notice an issue that belongs to a skill you are not using, write one line naming that skill and the issue, then move on.

## Review conventions

Apply these whenever a skill is used for a review, critique, or feedback request. Each skill adds its own finding fields.

### Stance

- Review as a senior engineer giving feedback to a maintainer who wants to learn. Warmpass has no target design. Judge the code by what it does and by the skill's principles, not against a layout you would have chosen.
- Lead with the verdict, then the reasoning. Name a principle or smell once and explain it in one sentence.
- Be blunt on substance. State problems plainly, with no cushioning and no hedges such as "you might want to consider". Never insult. Always give the principle behind a finding.
- Praise only when it is specific, as information about what to repeat.
- Check for too much structure before too little. The maintainer leans toward over-engineering. If the code is fine, say so and stop. Do not manufacture findings.
- Label each claim as fact, likely, or opinion (defined under Format). For opinions, offer options with tradeoffs. Commit to one answer for contract, correctness, and data-loss problems.
- Where a .NET equivalent makes a Python point clearer, name it in one clause. For example, `raise ... from exc` corresponds to `InnerException`, and `with` corresponds to `using`.

### Format

A review has two sections: a summary and the findings. Do not add other sections. Write so the reader can scan it: short paragraphs, bold labels, tables, and code instead of long prose.

#### 1. Summary

One or two sentences giving the verdict (sound, mixed, or needs work) and the single most important point. Then a table with one row per finding:

| # | Finding | Where | Impact | Type |
|---|---------|-------|--------|------|
| 1 | Short title naming the problem | `module.py` › `symbol` | High | Fact |

Impact is high, medium, or low. Type is one of:

- **Fact:** the problem is visible in the code, and you can point to the line.
- **Likely:** a reasoned guess, such as how code behaves at runtime or on another platform, that was not confirmed.
- **Opinion:** a style or design preference where other choices are also reasonable.

If there are no significant findings, say so in the summary and stop. Leave out the table and the findings section.

#### 2. Findings

List findings in impact order, at most five. If there are more, add one line after the last finding that names them in rank order. Write each finding with this template:

````markdown
### 1. <Short title naming the problem>

**Where:** `src/warmpass/<module>.py` › `<symbol>` · **Impact:** high · **Type:** fact

**Problem.** What is wrong, in one or two sentences.
**Principle.** The rule or smell behind it, in one sentence.
**Why it matters.** The concrete consequence, such as a bug, a lost failure, a broken job, or a change that becomes painful.

**Fix.** What to change and why that solves the problem, in one or two sentences.

```python
# Before: the current code, trimmed to the relevant lines
```

```python
# After: the proposed code
```

**Tradeoff.** What the fix costs or gives up.

<Fields the skill adds for its findings, as a short bullet list>
````

Rules for findings:

- Every finding shows code. Use real code from the repository and trim it with `# ...`. Keep each block short, about 15 lines at most, and show only what changes.
- When before-and-after code does not fit, such as a module dependency or a whole-suite gap, use a small table or a trace such as `cli.main → schedule.service → os_jobs.launchd`.
- For opinion findings, compare the options in a table with columns for the option, what it gains, and what it costs. Then give a recommendation.
- If you notice an issue that belongs to a skill you are not using, add a single line after the findings that names the skill and the issue, as described under Skills.

### Implementation tasks

Before coding, state the skill-specific plan in two or three lines. Keep to the requested scope. Afterward, summarize what changed and what you could not verify.
