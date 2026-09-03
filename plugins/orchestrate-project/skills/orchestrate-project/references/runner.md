# The runner — Compozy

The only file in this plugin where a Compozy command or flag appears. Every phase calls an
operation by name and never writes a flag of its own. When Compozy changes, this file changes and
nothing else does.

## Capture provenance

```
compozy version   →   compozy 0.3.0-beta.21
captured          →   2026-08-28, linux/x86_64
pinned            →   v0.3.0-beta.21
```

**Every flag below was read from `compozy <command> --help` on that build.** None was taken from
the documentation site, which returns 404 on every subcommand page, and none was written from
convention. That rule is not ceremony — three separate bugs in this migration came from assuming a
conventional form:

| Assumed | Actual | How it failed |
| --- | --- | --- |
| `compozy --version` | `compozy version` | Reported the runtime present with no version at all |
| version string carries `v` | `compozy 0.3.0-beta.21` | Reported drift between a build and itself |
| `compozy daemon status` | `compozy status` | Printed help, exited 0, read as a stopped daemon while it ran |

**A version bump invalidates this table.** `/orchestrate-init` warns when the installed build differs
from the pin; re-capture before dispatching rather than assuming a flag survived. Compozy has
shipped only prereleases — 21 in under two months — so this is a live risk, not a formality.

## Global conventions

- `-o json` on every call. `--json` is an accepted alias; prefer `-o json` for one spelling.
- `--workspace <ID|name|path>` overrides workspace context on every operation that touches one.
- Errors carry a `diagnostic` block with `code` and often `suggested_command`. **Read the suggested
  command rather than inventing a recovery** — it comes from the runtime that knows what it needs.

## Preflight

| Operation | Command |
| --- | --- |
| `daemon_state()` | `compozy status -o json` → `.daemon.status == "running"` |
| `diagnostics()` | `compozy doctor -o json` |

There is **no `compozy daemon status`**. `compozy daemon` has exactly three subcommands — `bootstrap`,
`start`, `stop` — and an invalid subcommand prints help and exits 0, so a check written against one
reports success for a stopped daemon.

`doctor` reports on the whole installation, including providers and extensions this skill never
uses. **Treat only `daemon`, `provider:claude` and worktree categories as blocking**; an
`extension_runtime_unavailable` for an unrelated extension is noise here.

## Worktrees

| Operation | Command |
| --- | --- |
| `create_worktree(name, branch, base)` | `compozy worktree create <name> --branch <branch> --base <base-ref> -o json` |
| `list_worktrees()` | `compozy worktree list --refresh -o json` |
| `inspect_worktree(ref)` | `compozy worktree inspect <ref> -o json` |
| `worktree_status(ref)` | `compozy worktree status <ref> -o json` |
| `cleanup_evidence(ref)` | `compozy worktree exit <ref> -o json` → the exit plan, including `cleanup.safe` |
| `remove_worktree(ref)` | `compozy worktree remove <ref> --force -o json` |

**`create` accepts no setup flag.** Bootstrap comes from `[worktrees] setup_command` in
`~/.compozy/config.toml`, not from the dispatch call. Its siblings there:

```toml
[worktrees]
root = "/absolute/path"          # must be absolute; TOML does not expand $HOME
run_branch_namespace = "run/"    # lowercase, slash-terminated
copy_list = [".env"]             # paths inside the repo, never absolute
setup_command = "..."            # the project's bootstrap
setup_timeout = "10m"
discovery_cache_ttl = "30s"
```

`root` defaults to `~/worktrees` — not `~/.compozy/worktrees`. A literal `$HOME/...` string fails
validation, because it is not an absolute path and TOML performs no expansion.

**A failed `setup_command` is not a failed worktree.** The checkout stays `ready` while
`setup_state` becomes `"failed"` with `setup_error` set. Poll the project's own bootstrap marker
(`project.bootstrap_marker` in `.orchestrate-project.json`) rather than trusting creation alone.

### `setup_command` is user-global, and that shapes what may be written there

There is **no per-project setup**. Verified against 0.3.0-beta.21: `config list` shows
`worktrees.setup_command` as the only key of its kind, `compozy config path` reports
`"scope": "user"` with a single target, `workspace edit` offers `--default-agent`, `--sandbox` and
`--add-dir` but nothing for setup, `worktree create` takes no setup flag, and profiles carry
identity (name, colour, icon) rather than configuration.

So a project-specific command written there **runs for every repository on the machine**. Write a
delegator that carries no project knowledge, and let each repository own its own bootstrap:

```toml
[worktrees]
setup_command = "sh -c '[ -x ./scripts/worktree-setup.sh ] && exec ./scripts/worktree-setup.sh; true'"
```

The guard makes it a no-op wherever that script is absent, so one line serves every project, and the
bootstrap itself is versioned and reviewable in the repository it belongs to. `/orchestrate-init`
checks this key and offers exactly this command.

**Whatever the hook invokes must exist on the base branch.** A worktree is cut from
`origin/<base>` and contains only what is committed there, so a bootstrap script that is staged,
stashed, or living on another branch is simply absent — and the guard above then makes its absence
*silent*. Land the script before the first dispatch, not alongside it.

### A restart-required setting may not be applicable from the CLI

`compozy config set` reports `"lifecycle": "restart-required"` and `"applied": false` for some keys;
`config reload` answers `"next_action": "restart-daemon"`. **`compozy daemon stop` refuses with
`daemon is not running` when the daemon was started by the Compozy app rather than the CLI**, while
`compozy status` reports it running with a pid — the two disagree because they mean different
things, and `daemon start` then fails with `detached daemon exited before readiness` because one is
already up.

The setting stays pending in that case. Read back what is *live* rather than what the file says:
`config get` reports the file's effective value, not the daemon's active generation.

**Lifecycle states**: `pending` → `ready`, then `failed`, `missing`, `removing`, `removed`,
`dismissed`. Only `ready` accepts a session.

**`--force` on `remove` confirms a destructive removal.** Read `cleanup_evidence` first and continue
only when `cleanup.safe` is true. Removal deletes the linked checkout, never the branch or history.

## Dispatch

| Operation | Command |
| --- | --- |
| `spawn(agent, worktree, prompt, provider, model, effort)` | `compozy spawn --agent <agent> --ttl-seconds <n> --workspace <worktree-path> --provider claude --model <model> --reasoning-effort <effort> --prompt-overlay "<prompt>" --name <ITEM-REF> -o json` |

**`spawn` requires the caller to be a runner-managed session.** It is an agent command, and outside
one it refuses before doing anything:

```
identity_required — COMPOZY_SESSION_ID is required for agent commands
action: run this command from a CompozyOS-managed agent session
```

So the orchestrating session must itself be a Compozy session — [Phase 3](spawn.md) checks this
first, because every other preflight can pass while this one makes dispatch impossible.

**Creating the orchestrating session is itself done from outside** — see "Before anything: can
this session dispatch at all?" in `SKILL.md`. `compozy session new --cwd "<repo path>"`
auto-registers the workspace and creates the session; the first `session prompt` binds it. A
session that is created and never prompted stays `unbound` and never runs.

| Operation | Command |
| --- | --- |
| `session_new(cwd, agent, name)` | `compozy session new --cwd "<path>" --agent <agent> --name <label> -o json` |
| `session_new(worktree, agent, name)` | `compozy session new --worktree <worktree-name> --agent <agent> --name <ITEM-REF> -o json` |
| `session_prompt(id, text, provider, model, effort)` | `compozy session prompt <session-id> "<text>" --provider claude --model <model> --reasoning-effort <effort> -o json` |

**`session prompt` prints nothing on success.** No id, no acknowledgement, no JSON — an empty
stdout and exit 0. It looks identical to a call that did nothing, and reading it as a failure is
the trap: re-sending produces a second turn on a session that is already working.

**Never judge delivery by the CLI's output.** The prompt landed when the session starts producing
events; that is the only reliable signal:

```
compozy session inspect <session-id> -o json     # state
# or read the daemon's event stream for that session id
```

An empty `session_input_queue` is also not evidence of failure — it drains as the prompt is
consumed, so "queue empty" and "queue never filled" look the same after the fact.

**`session prompt` resolves its workspace from the current directory**, and takes no `--workspace`
override. Run it from inside the worktree, or it fails resolving a workspace that has nothing to do
with the session being prompted.

`compozy session new --worktree <name>` creates a session from outside one, and
`compozy session prompt <id> "<text>" --provider … --model … --reasoning-effort …` carries the tier,
so the pair looks like a substitute. **It is not a complete one:** `session new` has no
`--mcp-server`, so a tracker reached over MCP is unreachable from the child, and the tracker writes
the [standing workflow](standing-implementer-workflow.md) expects then fail as silently skipped
steps. Reach for it only knowing that, and say so in the run report.

- **`--ttl-seconds` is mandatory.** There is no default; omitting it is an error. Size it to the
  item, and remember an expired TTL stops a child mid-work.
- **`--provider`, `--model` and `--reasoning-effort` are the tier assertion.** This is what
  [D-5](decisions.md) lacked under the previous runtime, which accepted no model flag and forced either a
  machine-default mutation or a corruption-prone terminal path. Set the tier here and compare it
  against what resolved; never read the machine default and never change it.
- **`--provider claude` only.** Compozy's release notes claim end-to-end delivery for Claude Code
  and Hermes; no other provider is dispatched to.
- `--auto-stop-on-parent` defaults true. For an implementer that must outlive the orchestrating
  session, set it false deliberately.
- **Grant the selected tracker's MCP server to the child**, when that tracker uses one:
  `--mcp-server <id>`. An MCP server belongs to the session that holds it, not to the machine, so a
  dispatched implementer does not inherit the orchestrator's. Without the grant, every implementer
  write the tracker declares — telling it work has started, writing the Definition of Done back — is
  unreachable inside the worktree, and the failure appears as a silently skipped step rather than an
  error.
- Other grants are explicit and repeatable the same way: `--tool`, `--skill`, `--sandbox-profile`,
  `--workspace-path`, `--channel`.

## Monitoring

| Operation | Command |
| --- | --- |
| `sessions_for(worktree_id)` | `compozy session list --worktree <worktree-id> --include-health -o json` |
| `session_state(id)` | `compozy session inspect <id> -o json` |
| `session_health(id)` | `compozy session health <id> -o json` |
| `read_logs(session)` | `compozy logs --session <id> --last <n> -o json` |
| `session_prompt(id, text)` | `compozy session prompt <id> "<message>" -o json` |

**Liveness is a reported state, never an inference.** `--state` takes `starting`, `active`,
`stopping`, `stopped`; `--attention` filters to sessions needing an operator. Do not count
terminals, do not grep a transcript, and do not treat process existence as progress — the previous
runtime forced all three, and misreading them cost the reference run about eight hours.

`--worktree <id>` is the binding between a dispatched item and its session. Filter on it rather
than matching display names.

`session prompt` takes `--queue` to hold input while the session is busy, and `--steer` /
`--interrupt` with `--expected-turn-id` to replace or cut the active turn. **Prefer plain send or
`--queue`.** Steering and interrupting act on a turn id that may have moved by the time the call
lands; use them only when a session is demonstrably going the wrong way, never as a routine nudge.

`compozy logs --follow` streams over SSE. Prefer `--last` for a bounded read; a follow that is never
closed holds the session open.

## The wave graph

| Operation | Command |
| --- | --- |
| `task_create(item)` | `compozy task create --title "<title>" --identifier <ITEM-REF> --auto-enqueue-on-ready -o json` |
| `task_depends_on(task, blocker)` | `compozy task dependency add <task-id> --depends-on <blocker-task-id> -o json` |
| `task_list()` | `compozy task list -o json` |
| `task_inspect(id)` | `compozy task inspect <id> -o json` |

**This is a tracking view, not the release gate.** A task marked complete records what an
implementer *claimed*; a claim is not a pushed branch. Wave release is decided by this skill's own
confirmation that the pull request has left draft and its head branch exists on the remote — never
by a task's state here.

`--auto-enqueue-on-ready` enqueues a run once blocking dependencies complete. That is a scheduling
convenience inside Compozy; it never substitutes for the release gate above.

## What this file deliberately does not use

`compozy worktree pr`, `worktree push` and `worktree commit` exist. **The orchestrator calls none of
them.** Implementers push their own branches from inside their own worktrees, and the two
zero-exception boundaries stand unchanged: never merge a pull request, never push to `main`. A
convenience command that crosses either boundary is still a crossing.
