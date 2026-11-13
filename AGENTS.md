# AGENTS.md

## Project

Warmpass is a Python 3.14+ CLI for running and scheduling agent warmups. Source code lives in `src/warmpass/`. The Typer entry point is `warmpass.cli.main:app`, and tests live under `tests/`.

- `warmup` sends a minimal prompt to a coding agent (Claude Code, Codex, Antigravity) to start its 5-hour usage window.
- `schedule` stores a schedule record and registers one OS job per schedule. The job's triggers are computed from the record, and the job runs `warmpass warmup`.
- `handoff` has the target agent summarize the source agent's session, then creates a new target-agent session that starts with the summary.

## Development

- Set up the environment with `uv sync --locked --dev`.
- Run lint, type checks (pyrefly), and formatting with `uv run --locked python scripts/check.py`. This command can reformat files, so review the diff after running it.
- Run tests with `uv run --locked python -m pytest`. Run an affected test file or directory first when narrowing down a failure.
- Check command help with `uv run --locked warmpass --help`.

## Rules for every task

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
- Label each claim as observed (in code), inferred, or taste. For taste, offer options with tradeoffs. Commit to one answer for contract, correctness, and data-loss problems.
- Where a .NET equivalent makes a Python point clearer, name it in one clause. For example, `raise ... from exc` corresponds to `InnerException`, and `with` corresponds to `using`.

### Format

1. **Verdict.** Two or three sentences: sound, mixed, or needs work, and the single most important point.
2. **What works.** One to three items, each tied to a file or symbol.
3. **Findings, in impact order.** At most five. For each, give where (file and symbol), what is wrong and the principle behind it, why it matters, the fix and its tradeoff, and the kind (observed, inferred, or taste). Rank any remaining findings in one sentence.
4. **Leave alone.** Things that look improvable but are not worth the cost now.
5. **Outside this review.** One line per issue that belongs to another skill, naming the skill. No analysis.
6. **Worth learning.** Optional, one line: a concept tied to a finding.

If there are no significant findings, the verdict says so and sections 3 to 6 may be short or empty.

### Implementation tasks

Before coding, state the skill-specific plan in two or three lines. Keep to the requested scope. Afterward, summarize what changed and what you could not verify.
