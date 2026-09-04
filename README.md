# orchestrate-project

A Claude Code plugin that turns a tracker's dependency graph into parallel, stacked work.

It reads a work-group's items and their real blocking relations **live, every time** — never from a
cached file — linearizes them into a stack, dispatches one autonomous implementer per item into its
own [Compozy](https://www.compozy.com/) worktree cut from its parent's branch, and babysits every
pull request through CI and review until a human can merge the stack.

It never merges anything, and it never pushes to your default branch.

## Install

Once per machine, register the marketplace:

```
/plugin marketplace add williamtrevisan/orchestrate-project
```

Then **per repository**, from inside it:

```
/plugin install orchestrate-project --scope project
/orchestrate-init
```

Project scope is deliberate. Repositories differ — a different tracker, a different gate, or no
orchestration at all — so enabling this is a per-repository decision rather than a machine-wide one.
It is recorded in that repository's `.claude/settings.json`, which you commit, so the team shares it
and a repository that does not use the plugin pays nothing for it.

`/orchestrate-init` asks only what your environment has not already answered. It probes each
tracker's authentication before offering it, detects your gate command from whatever manifest you
actually have, walks the runtime readiness chain, and writes `.orchestrate-project.json` — which you
commit, because a tracker choice is a team fact.

### Skip the manual marketplace step

A repository can declare where the plugin comes from, so a teammate who clones it needs neither
command above. Commit this in `.claude/settings.json`:

```json
{
  "extraKnownMarketplaces": {
    "orchestrate-project": {
      "source": { "source": "github", "repo": "williamtrevisan/orchestrate-project" }
    }
  },
  "enabledPlugins": { "orchestrate-project@orchestrate-project": true }
}
```

Trusting the project folder then registers the marketplace and enables the plugin in one step, and
`/orchestrate-init` is all that is left. The plugin's files are still fetched into the machine-local
plugin cache — this declares provenance, the way `package.json` does rather than `node_modules`.

### Or vendor it into the repository

Some repositories want the skill in their own tree rather than in a per-machine cache — so a clone
carries it, a diff shows it changing, and no one has to install anything first. For those:

```
npx github:williamtrevisan/orchestrate-project install
```

That copies the skill, its references, its scripts and `/orchestrate-init` into `.claude/`, and
records a content hash in `skills-lock.json`. Commit all of it. `/orchestrate-init` then works
exactly as it does under the plugin — the command resolves `init.py` beside the skill when
`CLAUDE_PLUGIN_ROOT` is unset, so one artifact serves both shapes.

Re-run `install` to update; it is idempotent and reports when there is nothing to do. **It refuses
to overwrite a copy that has local edits** and exits 3, because a vendored copy that quietly drifts
from upstream is the failure this whole repository exists to remove — pass `--force` when
overwriting is what you actually want. `npx github:... remove` takes it all back out.

Pick one shape, not both. The plugin cache and a vendored copy would give one repository two
versions of the same skill, which is the problem, not a fallback.

Then run it:

```
/orchestrate-project <work-group>
```

## What it assumes about your project

**Nothing.** That is the point.

Your gate command, its working directory, your bootstrap marker, your conventions document and every
tracker connection detail live in your repository's `.orchestrate-project.json`. The plugin ships
none of them. A missing key stops the phase that needs it and names the key — it never substitutes a
value from somewhere else, because a guessed build command produces a confidently green worktree
that fails in CI, and the implementer who guessed is the last person able to notice.

```json
{
  "tracker": "github",
  "runner": "compozy",
  "compozy_pin": "v0.3.0-beta.21",
  "project": {
    "gate_command": "npm test",
    "gate_working_dir": null,
    "bootstrap_marker": null,
    "constitution_path": "CONVENTIONS.md"
  },
  "tracker_config": {
    "jira": { "site": "acme.atlassian.net", "cloud_id": "<uuid>" }
  }
}
```

## Trackers

One document per tracker under `skills/orchestrate-project/references/trackers/`, each implementing
the same four reads and one optional write. **No phase ever names a tracker.**

| Tracker | State |
| --- | --- |
| `github` | Milestones, issues, native `blocked_by` dependencies. Verified against a live repository |
| `jira` | Epics via the Atlassian MCP. Site and cloud id are discovered by tool call, not typed |
| `linear` | Linear's official hosted MCP. No credential in configuration — OAuth lives in the client. **Ships unvalidated** — no workspace existed to test against, so its tool names are not yet captured |

Adding a tracker is one new document and **no change to any phase**. The shipped set is the offered
set: drop a file in, and `/orchestrate-init` offers it. If a new tracker requires editing a phase,
the contract is wrong — fix the contract, not the phase.

## Requirements

- [Compozy](https://www.compozy.com/) — the dispatch runtime
- An MCP server or CLI for whichever tracker you choose

**You install none of it by hand.** `/orchestrate-init` walks the readiness chain and, with your
confirmation at each step, installs Compozy, bootstraps it, starts its daemon, adds the tracker's
MCP server at project scope, and offers to put the runtime on your `PATH`. It confirms before each
one and stops at a refusal — installing a runtime and editing a shell profile are changes to your
machine, and one blanket yes is not consent for the rest.
- Python 3 for the shipped scripts (standard library only, no dependencies)

## Two boundaries, both zero-exception

**It never merges a pull request** — no auto-merge, no self-approval. Once a pull request is
mergeable, CI-green and review-clean, the skill reports it review-ready and stops.

**It never pushes to your default branch.** A separate rule, not a subset of the first. Every write
happens through a human-merged pull request.

Both apply identically inside every dispatched worktree. There is no orchestration carve-out.

## Why it behaves the way it does

[`references/decisions.md`](plugins/orchestrate-project/skills/orchestrate-project/references/decisions.md)
records the decisions and what each one cost to learn — including the ones with trade-offs that went
the wrong way. Worth reading before overturning a rule that looks arbitrary.

## Development

```
python3 -m unittest discover -s tests -p "test_*.py"
python3 plugins/orchestrate-project/scripts/init.py selftest
```

`tests/test_publishable.py` is the gate that keeps this repository publishable: it fails if a tenant
identifier — an Atlassian site, a cloud id, an organisation, a token — reaches a shipped file.
Project-specific values belong in a consumer's `.orchestrate-project.json`, never here.

## License

[CC BY 4.0](LICENSE)
