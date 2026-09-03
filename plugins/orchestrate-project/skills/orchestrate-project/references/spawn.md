# Phase 3 — Dispatch a wave

Cuts one worktree per wave-eligible item and starts that item's implementer in it. Every command
here is an operation named in [the runner](runner.md) — this page never writes a flag of its own.

Every tracker read on this page is one of [the contract](contract.md)'s four operations. Item
fields — the body, the human-facing reference, the `kind` a branch prefix derives from — come from
`list_items`, never from a tracker-specific field name.

**Never dispatch into a work-group owned outside this team.** Where the work-group's description
marks it as owned elsewhere, its items still count as blockers and are still read for their
completion, but no implementer is ever created against one. Deleting them from the graph would
break the dependency chain; dispatching into them would put our implementers on someone else's
work.

## 1. Preflight — refuse rather than dispatch into a broken setup

All six must hold. Any miss: report **which** one failed, and dispatch nothing.

```
session: COMPOZY_SESSION_ID is set in this session's environment
runner:  daemon_state()        → .daemon.status == "running"
runner:  the repository is a registered workspace
config:  .orchestrate-project.json parses, and carries project.gate_command
config:  worktrees.setup_command is set in Compozy's own config
git:     the base branch resolves on the remote
```

**The first one was already established before Phase 0** — see "Before anything: can this session
dispatch at all?" in `SKILL.md`. A run that reaches this page has it. It is restated here because
this is the list a reader checks when a dispatch fails, and a precondition absent from that list
reads as one that does not exist:

```
identity_required — COMPOZY_SESSION_ID is required for agent commands
```

Re-reading it here costs nothing and cannot fail on its own, since the variable belongs to the
session and no phase between there and here can change it. If it *is* somehow unset by this point,
refuse exactly as Phase 0 would have: orchestration runs from inside a Compozy session, or it does
not dispatch.

`/orchestrate-init` reports this as `runner.dispatch_identity` rather than as a readiness stage,
because configuring a repository from one session and orchestrating it from another is normal.

**The workspace registration is the second thing built infrastructure depends on.**
`worktree create` resolves its workspace from the cwd and fails outright on an unregistered
directory:

```
compozy workspace add "<repository path>"
```

The middle two are the difference between a usable worktree and a bare one:

- Compozy's `setup_command` is what populates dependencies and env files for a fresh checkout.
  Those are gitignored, so a worktree without it cannot run the gate at all.
- **A failed setup is not a failed worktree.** The checkout stays `ready` while `setup_state`
  becomes `"failed"`. Nothing surfaces unless you look, so the readiness test is the project's own
  marker, not the worktree's state.
- **Whatever `setup_command` invokes must already be on the base branch.** The key being set is not
  the same fact as the bootstrap being reachable: `setup_command` is user-global and is normally a
  delegator to a script inside the repository ([runner](runner.md)), and a worktree cut from
  `origin/<base>` contains only what is committed there. A script that is uncommitted, or committed
  only on the branch about to be built, is absent at the moment it is needed — and because the
  delegator is guarded, its absence is silent: the tree comes up bare and the first symptom is an
  implementer that cannot run the gate. Confirm the script exists on the base
  (`git cat-file -e origin/<base>:<path>`) before dispatching the first item of a run.

**Never read a project fact from this file.** The gate command, its working directory and the
bootstrap marker come from `project.*` in `.orchestrate-project.json`, written by
`/orchestrate-init`. A literal here would send every implementer in every repository to run one
project's build.

**If a required project key is absent, stop and name it.** Never substitute a value — a guessed
build command is worse than no dispatch, because it fails inside a worktree hours later.

## 2. Resolve and fetch the base branch

The bottom of the stack is cut from `origin/main`. Every other item is cut from **the remote branch
of its parent in the linearized chain** ([Phase 1](compute-waves.md)) — never from `main`, and never
from a local branch.

```
git fetch origin <base-branch>
git rev-parse --verify origin/<base-branch>
```

`<base-branch>` is `main` for the bottom item, otherwise the remote name the parent's implementer
pushed ([standing workflow](standing-implementer-workflow.md)), read back from the parent's pull
request rather than assumed — the pull request is out of draft by the time this runs, which is what
released this item.

**A base branch that does not resolve on the remote aborts that item's dispatch.** The runner cuts
a worktree from whatever it is given; pointed at a branch that was never pushed it produces a tree
with none of the parent's work, and the implementer then rebuilds it or contradicts it. Report the
missing branch and leave the item unscheduled — never fall back to `main`, which is precisely the
base the parent's work is not on.

Compozy refuses the same way at its own layer: a `ref` removed before start fails the run with
`worktree_ref_invalid` and **never falls back to the workspace root**.

## 3. Write the dispatch prompt to a file outside the worktree

Each item's prompt contains:

- The full spec — the item's body read verbatim, or [Phase 1.5](plan-production.md)'s produced spec.
- Its **Definition of Done**.
- The [standing implementer workflow](standing-implementer-workflow.md), embedded in full, with
  `project.gate_command` and `project.gate_working_dir` resolved into it.
- **The stack position**, stated explicitly: which item this one is built on, that the parent's
  work is **already present and unreviewed** in the base, and that it must be reused rather than
  re-derived or corrected. An implementer that does not know it is standing on unmerged work will
  read a parent's artifact as pre-existing fact and never question it.

It is written to `.orch/<REF>/prompt.md` — **outside the worktree, never inside it.** An implementer
that can commit or delete its own assignment can destroy it, and then no restart can recover what it
was doing. A scratch file outside the tree cannot be committed by accident, so no deletion
instruction is ever needed.

## 4. Create the worktree

```
runner: create_worktree(name=<ITEM-REF>, branch=<prefix>/<ITEM-REF>, base=origin/<base-branch>)
```

**Never construct the worktree path — read it back** from the response. Placement follows
`worktrees.root` and `run_branch_namespace` from Compozy's own configuration, which is per-operator,
so the same item yields a different path for a different machine.

## 5. Reconcile the result — never retry on an error

**A transport-level error is not a failed create.** The operation usually continues and succeeds. A
bare retry on the error produces two worktrees for one item, and then two implementers.

```
until <worktree appears> or <timeout>:
    runner: list_worktrees()        # match on the name given to create
    git worktree list               # independent second opinion
```

**Always corroborate with `git worktree list` before declaring a failure.** It reads git directly
rather than the runner's model, so the two disagreeing means the bug is in the poll, not in the
create. A false negative here is expensive in exactly one direction: it licenses a retry, and
retries are what produce duplicates.

Only after the poll expires — confirmed on **both** surfaces — may the create be considered failed.
**Never retry on the error itself.**

## 6. Start the implementer

**A worktree is dispatched with two calls, not one.** `spawn` is an *agent* command: outside a
runner-managed session it refuses with `identity_required`, and even from inside one it cannot
target a worktree — the path is not a registered workspace, so it fails with `workspace not found`.
[The runner](runner.md) documents both refusals. The pair that works:

```
runner: session_new(worktree, agent, name)      → session id
runner: session_prompt(id, prompt, provider, model, effort)
```

`session new --worktree <name>` starts the session inside an already-`ready` worktree. **The
session it creates is idle**: a session that is created and never prompted never runs. The prompt
is what binds it and starts the work.

**The tier is asserted on the prompt, not on the session.** `session new` takes no provider, model
or reasoning-effort — it resolves to the machine default. `session prompt` takes all three, so that
is where an item's tier travels ([D-5](decisions.md)). Two rules follow, unchanged:

- **Never read the machine default, and never change it.** The tier travels with the dispatch.
- **Verify what resolved and abort the wave on a mismatch, in either direction.** An implementation
  item that silently came up on a high tier is a cost bug; an analysis item that came up on the
  execution tier is a correctness one.

**Putting the tier on `session new` is the mistake this section exists to prevent.** It is silently
accepted and silently ignored, so a high-tier item comes up on the execution default and nothing
reports it.

### The MCP grant cannot be made on this path

`session new` has no `--mcp-server`. A tracker reached over MCP is therefore **unreachable from
the child**, and every tracker write the [standing workflow](standing-implementer-workflow.md)
expects — the optional started-write, the Definition of Done written back, the review-stage
transition — fails as a silently skipped step. That is the worst shape a failure can take.

Do not dispatch and hope. **Convert the silence into a stated handoff**, in the dispatch prompt:

- Tell the implementer plainly that it has no tracker access and must not attempt those writes.
- Name a file, outside the worktree, where it writes its Definition of Done instead.
- State that the orchestrator copies that report to the item and makes the transition.

A handoff someone can read beats a step that vanishes. Say so in the run report too, so the gap is
visible rather than inferred from a missing comment on the item.

`--ttl-seconds` is mandatory on `spawn`. `session new` has no TTL of its own, so an implementer
started this way runs until it stops or the daemon does — size the work accordingly and rely on
[Phase 4](monitor.md)'s stall detection rather than on a timeout.

## 7. Confirm the implementer is actually running

Not from an exit code:

```
runner: sessions_for(worktree_id)   → state, health
```

- **Liveness is a reported state.** `starting`, `active`, `stopping`, `stopped` come from the
  runtime. Do not count terminals, do not grep a transcript, and do not treat process existence as
  progress.
- **The worktree is bootstrapped** — poll for `project.bootstrap_marker` from configuration. Where
  no marker is configured, treat the worktree as ready on creation and say so, rather than
  inventing a filename to wait for. Bootstrap is asynchronous: the worktree appears before
  `setup_command` finishes.
- **Exactly one session per worktree.** Two sessions on one item is the failure to look for, and it
  comes from retrying a create, not from normal operation.
- **Stall detection**: a session `active` with no new events for 15 minutes is stalled — report it
  by item reference. Read `read_logs(session)` before attributing a cause; an update-check loop and
  a quota exhaustion look identical from the outside, and misdiagnosing that cost the reference run
  about eight hours.

## 8. Tell the tracker the work has started — only if the tracker declares it

`mark_in_progress(item)` is the contract's one **optional** write. Call it only when the selected
tracker's capability table declares it implemented. When the tracker declares it absent, call
nothing and change nothing else: no wave number, no dispatch decision, no completion read and no
release gate may depend on it having happened ([D-2](decisions.md)).

Never emulate it. A label, a comment, a body edit or a naming convention standing in for a real
transition is forbidden — it makes two unlike things look alike, and the difference then surfaces
only during a live run. If a declared implementation fails, log it and continue; a board-side
annotation is not worth stopping real work over.

## 9. Record, and handle failure per item

Write `.orch/<REF>/meta.json`: item reference, worktree path, worktree id, session id, local branch,
**remote branch**, **base branch**, **parent item reference**, whether the item is **gated**,
**requested tier**, **resolved tier**, stack level, database name.

The base branch and parent reference are what make the rebase cascade in [Phase 5](advance.md)
tractable: when a parent takes review changes, this is the record that says which worktrees are now
standing on a branch that moved. The tier pair is what makes step 6's mismatch check a comparison
rather than a recollection.

Concurrency is capped at **4**, and at **1** for items on a high tier — they run for hours and are
the item most likely to exhaust a quota. An item already dispatched in this run is never
re-dispatched.

When one item's dispatch genuinely fails: report the exact error, leave it unscheduled, and
**continue dispatching the wave's other items**. One failure never blocks the rest — but it is
never silently retried either.

**A failed run is surfaced, never auto-repaired.** There is no diagnose-and-retry cycle: the
recovery agent that would have driven one does not exist in this runtime, and an orchestrator that
silently restarts work hides the reason it failed.
