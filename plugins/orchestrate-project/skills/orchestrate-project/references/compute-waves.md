# Phase 1 — Compute wave order

The one piece of genuine algorithmic reasoning in this skill. It runs over whatever
[Phase 0](read.md) just fetched, and it **recomputes from scratch every time** — kickoff and every
re-entry from [Phase 5](advance.md) alike. No wave table is persisted anywhere.

It consumes only what [the contract](contract.md) defines: items, their blocking relations, and a
completion boolean. No tracker status name, category or column identifier reaches this page.

## 0. Refuse when the graph cannot be read

If the selected tracker declares `read_blockers` **unavailable**, refuse to compute any wave at
all and report that the tracker cannot supply blocking relations. Do not fall back to treating
every item as unblocked: absence of data is never evidence of absence of blockers, and an empty
graph dispatches the whole work-group in one wave — the single most expensive mistake this skill
can make.

## 0.1 Cycle check — before any wave number is assigned

Run a DFS over the **in-group** blocking relations, tracking the recursion stack. A back-edge — an
edge into a node already on the current stack — means a cycle. External blockers cannot
participate; they are outside the set.

**If a cycle exists, refuse to compute any wave at all.** Not "skip the cyclic items and schedule
the rest" — the whole computation is refused, for every item in the run, until a human breaks the
cycle on the tracker. Report **every** item in the cycle by its human-facing reference, not just
the two where the back-edge was found.

A partial dispatch under a cycle would look like progress while the dependent half can never
start, which is worse than refusing outright.

## 1. The wave formula

Once the cycle check clears:

- **`wave = max(wave of each blocker) + 1`**
- An item with **no unsatisfied blockers** is **Wave 1** — whether it has no blocking relations at
  all, or every relation already resolved.
- A blocker that `read_completion` reports **complete** counts as satisfied: it contributes wave 0,
  so it does not push its dependent's number up. There is no special case between "no blockers" and
  "all blockers complete" — both resolve to Wave 1.

## 2. Fan-in

An item with **two or more** in-group blockers is a **fan-in** item and is flagged as such — it is
never silently grouped with single-blocker items.

Its wave is still `max(...) + 1`. Under AD-021 the linearization in section 2.5 is what satisfies
it: the item is cut from a chain that already contains every one of its parents, so there is no
partial-satisfaction case at dispatch time. **The flag still matters** — it is what tells section
2.5 which items constrain the chain, and a fan-in item whose chain does not cover all its parents
is a bug in the linearization, not a scheduling decision.

## 2.5 Linearize the waves into a chain

`gh stack` models a **linear** stack: `add` puts a branch on top, and navigation is
`up`/`down`/`top`/`bottom`/`trunk`. There is no two-parent concept. A dependency graph that
branches and re-joins therefore has to be reduced to a chain before it can be dispatched.

Take a **topological order** of the in-group graph, and make each item's base the branch of the
item immediately before it. Two properties make this correct rather than merely convenient:

- A topological order places every blocker before its dependent, so each item's base transitively
  contains **all** its parents — which is exactly what a fan-in needs.
- Independent items can be ordered either way. Order them by what the later work *reads*: when one
  item's artifact narrows the other's job, it goes first. That is a judgment call, and it is stated
  in the rendered table rather than left implicit.

**Siblings do not have to be serialized.** Items that share a base and do not depend on each other
are cut from that same base and dispatched together — the chain only has to be linear where the
graph has a real edge. This is what preserves parallelism: the chain sets the depth, and the
siblings at each level set the width.

Report the chain's **depth** and its **widest level**. Depth is the number of review-to-merge hops
the stack will have; width is how many implementers run at once. A linearization that turns a
3-wide level into three extra depth is a mistake worth catching before dispatch, not after.

## 3. Blocked externally

An **external blocker** is an item the orchestrator does not own. Three shapes, one rule:

- an item outside the resolved work-group's own item set;
- an item in another repository;
- an item in a work-group whose description marks it **owned outside this team**.

An item blocked by a still-incomplete external or read-only item ([Phase 0](read.md)) receives
**no wave number**. It appears in the table as "blocked externally by `<reference>`" — never
silently omitted, and never assigned a number it has not earned. External blockers are read for
their completion and reported by reference; they are never dispatched
([Phase 3](spawn.md)).

This is the normal shape for cross-repo and cross-team work: an item owned by another repository
or another team is in-scope for that owner's run, not this one.

## 3.1 When no item earns Wave 1 — the work-group is not ready

Count the items that earned Wave 1. If the count is **zero**, the work-group is **not ready**:
report that verdict, name every blocking reference and who owns it, and stop before
[Phase 3](spawn.md). Nothing is dispatched.

This is not the unscopeable case ([Phase 0](read.md)). There, no item is in scope at all and there
is nothing to schedule. Here the work-group has items, they are in scope, and every one of them is
waiting on something — an in-group blocker that is not yet complete, an item in a work-group owned
outside this team, or an item in another repository.

Report it as:

> **`<work-group>` is not ready.** No item is unblocked. Blocked by: `<reference>` (owner),
> `<reference>` (owner), …

Every blocker gets named. "Not ready" without the blocker list tells the reader nothing they can
act on, and the whole point of the verdict is to hand them the shortest path to making it ready.

Do not dispatch the item with the fewest blockers, and do not start "the closest one anyway". An
item whose blockers have not merged is an item whose base does not exist yet.

## 4. Render the stack table

| Level | Items | Base branch | Releases when |
| --- | --- | --- | --- |
| 1 | REF-1 | `main` | (no blockers) |
| 2 | REF-2 | `<prefix>/REF-1` | REF-1's PR **ready** (out of draft) |
| 3 | REF-3, REF-4 (siblings) | `<prefix>/REF-2` | REF-2's PR ready **and approved** (gated) |
| — | REF-5 — blocked externally by EXT-9 | — | EXT-9 (external) **complete**, i.e. merged |

Four things the table has to state explicitly, because each is a decision someone can disagree
with:

- **The base branch per item** — this is what Phase 3 passes to the runner's `create_worktree`, and
  getting it wrong is unrecoverable without a rebase.
- **Which items are gated** ([Phase 5](advance.md) step 3), so their dependents wait for an
  approving review rather than the ready flip alone.
- **Any ordering choice between independent items**, with the reason, per section 2.5.
- **External blockers, which never join the stack** and still require a real merge.

## 5. Record the graph as tasks

Create one task per dispatchable item, then add an edge per in-group blocker
([runner](runner.md)):

```
runner: task_create(item)                        → task id
runner: task_depends_on(task, blocker_task)      → one call per blocker
```

This gives the run a tracked DAG the whole team can read, and a place for completion to land.

**The task list is a tracking view, not the release gate.** A task is marked complete on what an
implementer *reports*, and a report is a claim. Under AD-021 the release signal is the pull request
leaving draft — often the same moment — but the two are still not the same fact: the release gate is
the pull request **and its pushed head branch, read back from the forge**. Dispatching a dependent
against a base branch that was never pushed produces a worktree cut from nothing.

`--auto-enqueue-on-ready` will enqueue a run once blocking dependencies complete. That is a
scheduling convenience inside the runtime; it never substitutes for the gate above, and a wave is
never released because the runtime thought a task was ready.

| Question | Answered by |
| --- | --- |
| Who depends on whom? | The runner's task DAG |
| What is dispatched / running / reported done? | The runner's task list |
| **Does the blocker's branch actually exist on the remote?** | This skill — [Phase 5](advance.md) |
| **May the next wave start?** | This skill — never the task list alone |
