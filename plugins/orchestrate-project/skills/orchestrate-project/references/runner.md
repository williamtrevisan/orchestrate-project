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

**Always name the worktree after the item, and never let the runner name it.** A worktree created
without an explicit name gets a generated one — `calm-badger` on 2026-09-06, for an item whose nine
siblings were `jur-129` … `jur-137`. Nothing breaks at dispatch, which is what makes it dangerous:
it breaks later, in recovery. Every procedure in this skill for a stopped implementer begins by
reading its worktree ([Phase 4](monitor.md)), and a worktree whose path is unguessable cannot be
read. On that run the recovery check reported "worktree absent" for a worktree that existed and
held work.

Derive the name from the item reference, deterministically, so that any later session can find it
from the tracker alone — and record the resolved path in `.orch/<REF>/meta.json` at creation, so a
name that was generated anyway is still recoverable:

```
compozy worktree create <item-ref-slug> --branch <branch> --base <base-ref> -o json
```

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
| `spawn(agent, workspace, prompt, provider, model, effort)` | `compozy spawn --agent <agent> --ttl-seconds <n> --workspace <ws-id> --provider claude --model <model> --reasoning-effort <effort> --auto-stop-on-parent=false --mcp-server <tracker-server> --prompt-overlay "<prompt>" --name <ITEM-REF> -o json` |

**`spawn` requires the caller to be a runner-managed session.** It is an agent command, and outside
one it refuses before doing anything:

```
identity_required — COMPOZY_SESSION_ID is required for agent commands
action: run this command from a CompozyOS-managed agent session
```

**The identity is a pair, and the second half is only reported once the first is satisfied.**
Setting `COMPOZY_SESSION_ID` alone yields the same `identity_required` code, now naming
`COMPOZY_AGENT` — so a run "fixed" by reading the first message fails again at the same point.
Check both, or the check is worth nothing.

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

### A session must be *attached* before it can be prompted

`unbound` is not the only state that swallows a prompt. A session that was bound and has since
gone idle reads as **`detached`**, and every `session prompt` to it fails — not with a state
error, but with whatever unrelated error the resolution path happens to raise. Retrying the
prompt never fixes it; only re-attaching does.

```
compozy session health <session-id>      # State: detached / Attachable: false
compozy session resume <session-id>      # -> State: active, and prints "Attach Expires:"
```

**`resume` opens a fixed attach window** (~15 minutes, printed as `Attach Expires`). Send the
prompt inside it; after it lapses the session detaches again and the next prompt fails the same
way. Check `session health` *before* concluding a prompt failure is a daemon or network problem —
`State` and `Ineligibility Reason` name it directly.

### The tier is named in the session's own vocabulary, not as a model id

`session prompt --model` is validated against the ACP config options of that session, which are
short names — `opus`, `sonnet`, `haiku`, `claude-fable-5-1`, `default`. A full model id such as
`claude-opus-5` is **rejected**, and the error lists the choices that session will accept:

```
acp: model "claude-opus-5" is unavailable in config option "model";
     valid choices: claude-fable-5-1, default, haiku, opus, sonnet
```

This matters for the tier assertion in [Phase 3](spawn.md): assert the tier against the name the
session accepts. `session list -o json` reports the *effective* model in a different vocabulary
again (`claude-sonnet-5`), so compare tiers, never raw strings.

### The orchestrating session has a tier too, and nothing asserts it

[Phase 3](spawn.md) asserts the tier of every *item*. Nothing asserts the tier of the session
doing the asserting. A session created by `session new` takes no provider, model or
reasoning-effort — it resolves to whatever the machine default happens to be that day — so
"Opus orchestrates" ([D-5](decisions.md)) holds only by luck.

Observed 2026-09-06: a cold-started orchestrator came up on `claude-sonnet-5` and began Phase 0.
Nothing reported it. It is the same class of bug the item-level assertion exists to catch, one
level up, and it is worse there: the orchestrator is what computes the graph, sizes the waves and
decides every item's tier.

**Assert it on the first prompt, and read the right field.**

```
compozy session runtime set <id> --provider claude --model opus --reasoning-effort high
compozy session prompt <id> "<the invocation>" --provider claude --model opus --reasoning-effort high
```

`runtime set` is per session, which is what makes it usable — the machine-wide default is never
the lever, because it reaches every agent starting in that window, including other repositories'.

**`session list`'s `runtime.effective` is a stale snapshot and will lie to you here.** After a
`runtime set` it reports `selected` correctly while `effective` still names the model of the
previous — possibly cancelled — turn. The authoritative value is `prompt_runtime`, carried on the
active turn's own event:

```
compozy session events <session-id> -o json     # -> "prompt_runtime": {"model": "opus", …}
```

A cold start that resolved wrong is cheap to fix in the first minute and expensive after: cancel
the turn (`session prompt-cancel`), set the runtime, re-send. Do it before Phase 0 reads anything.

### Retry a prompt with an explicit identity, never a bare re-send

`--message-id` and `--idempotency-key` must be **provided together** -- either alone is an error --
and together they make a retry safe: a duplicate delivery is refused rather than producing a
second turn.

```
compozy session prompt <id> "<text>" --provider claude --model opus \
  --reasoning-effort high --queue --message-id msg-<item>-1 --idempotency-key idem-<item>-1
```

**A key is single-use, including by the attempt that failed.** A call rejected for any reason
(an invalid model, a timeout) still binds its key, and reusing it returns
`idempotency conflict: ... already bound to another request`. A genuine retry therefore needs a
**fresh** pair -- so verify the prompt did not land (below) before issuing one.

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

**The cheapest positive signal is the turn count.** `session history` groups by turn, so a prompt
that landed added exactly one; a prompt that did not left the count where it was. It is one call,
it needs no event parsing, and it answers the only question a retry loop actually has:

```
compozy session history <session-id> -o json | jq length     # before, then after
```

Guard every re-send on it. A retry loop that re-sends on a non-zero exit — or on any signal other
than the count failing to move — will eventually deliver the same instruction twice, and an
orchestrator that reads its own marching orders twice is worse than one that never got them.

**Nor is a timeout.** `session prompt` routinely holds the connection open past a two-minute
client timeout while the prompt is already delivered and the session is working. Killing the
client changes nothing on the daemon's side. Count events before and after: a session that went
from 2 events to 134 received the prompt, whatever the shell reported.

**Errors arrive on stdout with exit 0.** Every failure above — the model rejection, the
idempotency conflict — printed to stdout and exited 0. Never filter runner output, and never read
an exit status as the result.

### A daemon serves a handful of children per boot, then blocks forever

This is the operative limit, and it is measured rather than inferred. Across three daemon boots:

| Boot | Children created | Everything after |
| --- | --- | --- |
| 1 | 2 | 11 attempts, all blocked |
| 2 | 2 | 3 attempts, all blocked |
| 3 | 3 | 6 attempts, all blocked |

**`spawn` blocks rather than refusing.** At the limit it holds the connection until the client's
deadline, so the failure arrives as `context deadline exceeded` — indistinguishable from a wedged
endpoint, which is what three earlier readings of this page called it.

**Once blocked, it stays blocked.** All of the following were tried on a blocked daemon and none
restored it: waiting hours, letting every child reach TTL and report `stopped`, running nothing
else on the machine, and **killing the children's leftover processes outright**. Only a restart
works.

Two observations that go with it, and do not explain it:

- A session reports `stopped` while its `npm exec @agentclientprotocol/claude-agent-acp` tree keeps
  running. Six such trees were found alive on one daemon, aged three to eight hours, every one a
  child of the daemon with its session long stopped.
- Reaping those trees changes nothing about the block, so whatever the daemon is counting is not
  the OS process.

**No mechanism is claimed here.** Four have been published and falsified — a wedged endpoint, the
caller's call site, the daemon's age, and machine load. What follows is the operating rule that
survives all four:

> A daemon boot buys roughly **two dispatches**. Plan the wave around that, dispatch what the
> window allows, and report the rest as needing a restart — which is a human's call
> ([`SKILL.md`](../SKILL.md), "Surface, don't auto-do").

### `spawn` hangs after the identity check, wherever it is called from

**`POST /api/agent/spawn` hangs while every other endpoint answers instantly**, so a run reads as
healthy right up to the moment it dispatches, and then cannot. It looks exactly like the
`GET /api/workspaces/{id}` wedge below — and the first reading of it was that, which is why the
remedy came out wrong. It is not the same thing, and the difference decides what to do.

Measured 2026-09-06 across **eleven attempts and four configurations**, and once more on
2026-09-07 from inside an agent's own turn:

| Parent session state | Result |
| --- | --- |
| `unbound` — created, never prompted | `context deadline exceeded` |
| Re-attached with `session resume` | `context deadline exceeded` |
| With `--no-notify-creator` | `context deadline exceeded` |
| Mid-turn on a real prompt (75k tokens, `done: end_turn`) | `context deadline exceeded` |

Throughout, from the same shell and the same second: `session list`, `workspace info`,
`worktree status` and `session prompt` all answered — `session prompt` ran a complete billed turn.
**None of the twelve created a child**, so the failure is at least clean: check `session list` for a
child named after the item before concluding anything, but expect nothing there.

**The identity check is not what hangs.** A *stale* session id — one whose runtime is gone —
comes back in under a second:

```
identity_stale — agent session identity is not active
action: start or resume the CompozyOS session, then retry
```

A *freshly created, never-prompted* session id passes that check and then hangs. So the block is
after identity resolution, and the plausible reading is that the daemon waits for the parent's
runtime to acknowledge the child — a runtime a session only has while it is running a turn.

Two facts fit that and nothing else does: **every one of the eleven hangs was issued from an
outside shell against a session that was not mid-turn**, and **the only spawns ever observed to
succeed came from inside an agent's own turn** — the first orchestrator of the run dispatched two
implementers that way, in the same session, minutes before it ended.

**That inference was tested and is false.** On 2026-09-07 a session was prompted to run nothing
but the `spawn` command, so the call was issued from inside a live agent turn by the agent that
owned the session. It hung identically — `context deadline exceeded`, no child, `end_turn`, $0.33
spent to learn it. Where the call is made from is **not** the discriminator.

What survives as measured fact, and nothing more:

- The identity check is fast and correct — `identity_stale` comes back in under a second.
- Everything after it hangs, from a shell and from inside a turn alike.
- Every other endpoint answers throughout, including `session prompt`, which runs complete billed
  turns.
- The only spawns ever observed to succeed happened on 2026-09-05, within hours of the daemon
  starting. Nothing has succeeded since, across two days and twelve attempts.

**Stop trying to characterise it from the caller's side.** Four call shapes and two call sites were
tried; each cost time and none moved it. Treat a hanging `spawn` as a daemon-level fault, make
**two** attempts, and report.

**Restarting the daemon does clear it — and it comes back.** A restart resolved twelve failures
instantly: a probe spawn returned a child in seconds. **One hour later the same daemon was failing
again**, so age is not the discriminator, and an earlier revision of this page that named it the
leading suspect was wrong within the hour.

What the timeline actually shows:

| Machine state | `spawn` |
| --- | --- |
| Freshly restarted, nothing running | works |
| ~1h in, one implementer running | times out, and `session list` times out with it |

`workspace list` kept answering throughout, both times. Two days earlier the only successful spawns
were likewise the first ones, before the implementers they created were doing anything.

**The correlate is an active agent session, not elapsed time — and that is an observation, not a
mechanism.** The test that would settle it is cheap and has not been run: probe `spawn` once the
running implementer finishes, on the same daemon. Until someone does that, report what is
measurable —

```
P=$(cat ~/.compozy/daemon.lock); ps -o etime= -p "$P"    # age
compozy session list                                     # what is running (may itself time out)
```

— and say plainly that a restart buys a working dispatch window rather than a fix. **Dispatch the
whole wave inside that window**, because the second item may not get one.

**Never restart the daemon yourself.** It is the only thing likely to clear this, and it kills
every in-flight implementer on the machine — including waves belonging to other runs. That makes
it a human decision, and it belongs in `SKILL.md`'s "Surface, don't auto-do" list rather than in a
recovery routine here.

**Make that decision cheap by enumerating what would die.** A human asked "should I restart?" with
no list has to go and look; a human handed the list can answer in a second. Report both, because
a worktree's flag can be stale while its session is long gone:

```
compozy session list      # any session in `running` or `prompting` is live work
compozy worktree list     # a `running` worktree whose session is `done` is a stale flag
```

Say plainly whether the restart would interrupt anything, and let the human decide.

**When the human says yes, the documented commands are not enough.** Every step of this was
observed on 2026-09-07:

| Step | What happens | What works |
| --- | --- | --- |
| `compozy daemon stop` | prints `daemon is not running` while the process is alive | read `~/.compozy/daemon.lock` for the pid |
| `ps \| grep compozy` | lists nothing, also while it is alive | `ls -d /proc/<pid>`, and `fuser ~/.compozy/daemon.sock` for who holds it |
| `kill -TERM` | ignored, twice | escalate to `kill -KILL` after a bounded wait |
| `compozy daemon start` | boots the daemon, then kills it — the log reads `received shutdown signal: terminated` about 40s in, because session repair over a large `compozy.db` outlives the CLI's readiness wait | `setsid nohup compozy daemon start --foreground >…/logs/manual-start.log 2>&1 </dev/null &`, then wait for `daemon.sock` to appear |

**A forced kill is not free.** `compozy.db` was 91 MB with a 4.5 MB unapplied WAL, and the next boot
spent minutes on recovery and session repair before the socket appeared. Wait for the socket rather
than concluding the start failed — `daemon start` will have already reported a readiness timeout it
caused itself.

### When dispatch stalls but the daemon answers

A single wedged handler is indistinguishable from a dead daemon unless the two are told apart
deliberately. Observed: every single-resource `GET /api/workspaces/{id}` timed out for hours
(`context deadline exceeded`) while the *list* endpoints answered instantly. Because every
`session new` route — `--cwd`, `--workspace`, `--worktree` — resolves through that one GET, no
new dispatch was possible while `session list` and `workspace list` made the daemon look healthy.

```
compozy workspace list      # answers  -> daemon is alive
compozy workspace info <id> # times out -> the single-resource handler is the wedge
```

**That classification is a snapshot, not a diagnosis — re-probe before acting on it.** Observed
2026-09-06: the same wedge began exactly as described, with the list endpoints answering, and
roughly an hour later `workspace list`, `session list` and `session status` were timing out too.
Anything built on "the list routes are fine" — a monitor, a retry loop, a report — was by then
reading a daemon that answered nothing, and said so only if it had been written to notice.

**It also clears on its own.** That same wedge recovered without intervention, and a guarded retry
loop dispatched the waiting item the moment it did. Waiting cost one leaf item a delay; a restart
would have cost every in-flight implementer on the machine, across every repository sharing the
daemon. **Prefer waiting.** Restarting is a human's call, and the honest way to put it to them is
with the count of sessions currently `active` — theirs and other runs' alike.

`session resume` does not go through workspace resolution, which is why an already-created session
can still be re-attached and prompted while new ones cannot be created. Recovering an existing
session is therefore the first thing to try when dispatch stalls — not a daemon restart, which
kills every in-flight implementer and is a human's call.

**`session prompt` resolves its workspace from the current directory**, and takes no `--workspace`
override. Run it from inside the worktree, or it fails resolving a workspace that has nothing to do
with the session being prompted.

`compozy session new --worktree <name>` creates a session from outside one, and
`compozy session prompt <id> "<text>" --provider … --model … --reasoning-effort …` carries the tier,
so the pair looks like a substitute. **It is not a complete one:** `session new` has no
`--mcp-server`, so a tracker reached over MCP is unreachable from the child, and the tracker writes
the [standing workflow](standing-implementer-workflow.md) expects then fail as silently skipped
steps. Reach for it only knowing that, and say so in the run report.

### A provider session limit is not a failure, and not a finish

The most common way a session stops on a long run is neither. The provider refuses, the turn ends,
and the session goes idle — which from the outside is byte-for-byte what "finished its work" looks
like. Observed three times in one run on 2026-09-06, twice on an orchestrator and once on an
implementer:

```
{"code":-32603,
 "message":"Internal error: You've hit your session limit · resets 7:50pm (America/Sao_Paulo)",
 "data":{"errorKind":"rate_limit"}}; provider_failure_kind=rate_limited; next_action=retry
```

**Three things make it identifiable, and all three are in the last turn, not in the session state:**

| Field | Value |
| --- | --- |
| `data.errorKind` | `rate_limit` |
| `provider_failure_kind` | `rate_limited` |
| `message` | carries the **reset time**, in the user's timezone |

`session status` reports `idle`/`done`, and `session health` may report `healthy` — neither says
why. **Read the last turn before concluding anything about a session that went quiet:**

```
compozy session history <session-id> -o json     # last turn's last block carries the refusal
```

**What to do.** The message names when the quota returns, so this is a wait, not a recovery:

1. **Do not re-dispatch, and do not cut a new worktree.** The item is mid-flight; its worktree
   holds the work. Re-dispatching pays for it twice and throws the first attempt away.
2. **Do not treat it as done.** A wave released on a rate-limited session's silence releases
   dependents against work that stopped halfway.
3. **Wait for the stated reset, then re-prompt the same session** with what remains. If the session
   died in the meantime, re-prompt a fresh one **into the same worktree** — the recovery in
   [Phase 4](monitor.md).
4. **Report the wait to the user with the reset time.** An orchestration that appears frozen for
   six hours with no explanation reads as broken.

**Nothing reopens the turn on its own.** Every one of those three interruptions needed a human or a
driver session to re-prompt; the internal monitor did not, and neither did the daemon. Plan a long
run knowing that a limit costs the wall-clock to the reset **plus** the round trip to notice it.

### A child is stopped with its parent unless you say otherwise

`--auto-stop-on-parent` **defaults to `true`**, and the parent is the orchestrating session, not a
supervisor process. Ending a turn is a normal stop, so the default cascades it: every implementer
the wave dispatched is killed mid-work, with uncommitted changes in its worktree, no commit, no
branch pushed and no pull request.

Observed 2026-09-05. An orchestrator dispatched a two-item wave, reported both implementers live
and both tiers asserted, then filled its context window — `used: 200111, size: 200000` — and ended
its turn. Both children died two and twelve minutes later, `health: dead` and not reattachable.
Each had a nearly complete implementation sitting uncommitted. From the outside the run looked
finished: the tracker showed both items in progress, the sessions were gone from `session list`,
and nothing had errored.

**Always pass `--auto-stop-on-parent=false`.** An implementer must outlive the turn that started
it — that is the whole point of dispatching it. This is not a preference to set deliberately in
some cases; there is no case in this skill where the default is correct.

**Recovery, when it has already happened:** the work is not lost. A killed child leaves its
worktree exactly as it was, so run the cheap checks ([the cost discipline](../SKILL.md)) against
that tree — typecheck, the item's own tests, the gate — and either land what is there or
re-dispatch a fresh implementer into the *same* worktree with a prompt that names what remains.
Do not start a new worktree; you would throw away work that is sitting on disk.

### A worktree is not a workspace

`compozy worktree list` and `compozy workspace list` are separate registries, and
`spawn --workspace` resolves only the second. A worktree the runner just created is **not** a
workspace: its name, its `wt_*` id and its absolute path all fail with `workspace not found`.

```
compozy workspace add "<worktree path>"     # -> ws_…
compozy spawn --workspace ws_… …
```

`session new --cwd` auto-registers, which is why the orchestrating session never hits this — and
why it is invisible until the first `spawn` into a fresh worktree.

- **`--ttl-seconds` is mandatory.** There is no default; omitting it is an error. Size it to the
  item, and remember an expired TTL stops a child mid-work.
- **`--provider`, `--model` and `--reasoning-effort` are the tier assertion.** This is what
  [D-5](decisions.md) lacked under the previous runtime, which accepted no model flag and forced either a
  machine-default mutation or a corruption-prone terminal path. Set the tier here and compare it
  against what resolved; never read the machine default and never change it.
- **`--provider claude` only.** Compozy's release notes claim end-to-end delivery for Claude Code
  and Hermes; no other provider is dispatched to.
- **`--auto-stop-on-parent=false` is mandatory in practice**, though the flag defaults true. See
  "A child is stopped with its parent unless you say otherwise" above — the default has already
  cost one wave.
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
