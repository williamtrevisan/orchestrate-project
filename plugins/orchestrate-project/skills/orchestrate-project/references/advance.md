# Phase 5 — Advance the stack

A PR marked **ready for review** does not end the run — it releases the next item onto the stack.
This is the loop that keeps the cycle turning, and it holds the invariant the design rests on.

Amended by **[D-3](decisions.md)**. Before it, this phase released on a merge to `main`; the rule now is a PR
leaving draft, and the base branch moves with the chain instead of staying `main`.

## The invariant

**A draft PR releases nothing.**

Implementers open their PR as a **draft on the first commit** and push every atomic commit into it
([standing workflow](standing-implementer-workflow.md)), so progress is visible from the moment
work starts. That visibility is the draft's whole purpose. It is **not** a release signal.

The distinction is the one the whole stack rests on. The next item's worktree is **cut from the
parent's branch**, and a branch with one commit on it is a stub. Releasing a dependent against a
draft means an implementer starts consuming an artifact its parent has not written yet — and it
will not notice, because a stub and an empty result look identical.

`gh pr ready` is the moment the parent asserts *this branch is a base someone can stand on*. That,
and nothing earlier, releases the next item.

**A completed task is not that signal either.** The runner completes a task when the implementer
reports it; that is the implementer's own claim. The release gate is the pull request's state read
back from the forge. So **the task list is still never the release gate.** The runner answers *who
depends on whom*. This phase answers *has that pull request actually left draft, on a branch that
actually exists*.

## Draft events are progress, not release

Emit them, report them, and act on a red check against one ([Phase 4](monitor.md)). Do not
recompute the graph and do not dispatch anything. A draft opening changes nothing about what is
eligible.

## On a PR READY FOR REVIEW event

In this order:

**1. Mark the item reported** in the run's task list. Reported, not complete — nothing in this run
is complete until a human merges the stack.

**2. Confirm the PR and its branch, from the forge.**

```
gh pr view <pr> --json state,headRefName,baseRefName,isDraft
git fetch origin <headRefName>
git rev-parse --verify origin/<headRefName>
```

All four must hold, and **`isDraft: false` is the one this phase exists to check** — it is the
difference between a branch someone can build on and a branch with one commit on it. The PR is
`OPEN`, `isDraft` is `false`, its `baseRefName` is the base this item was dispatched against, and
its head branch resolves on the remote.

**A mismatch on `baseRefName` means the implementer opened against the wrong base** — most often
`main`, the old default. Stop, report it, and release nothing: everything cut from that branch
would inherit the wrong ancestry.

**Never flip a draft to ready on an implementer's behalf.** If an item looks finished but its PR
is still a draft, that is a question for its implementer or a human — re-engage
([Phase 4](monitor.md)) rather than undrafting it. `gh pr ready` is the implementer's assertion
that the branch is complete, and asserting it for them is how a dependent ends up on a stub.

**3. Check the review gate, where the run declares one.**

A **gated item** releases its dependents only after a human has approved its PR, not merely opened
it. The run names its gated items at kickoff; everything else releases on step 2 alone.

```
gh pr view <pr> --json reviewDecision --jq '.reviewDecision'
```

Release only on `APPROVED`. `CHANGES_REQUESTED` or an empty decision holds the dependents and is
reported by item reference — never waited on silently.

Gate the items whose output later items *consume* rather than extend. An analysis artifact that
four downstream items read is the case this exists for: a wrong classification there is not a
merge conflict, it is rework in every descendant, and it is cheap to catch while one PR is open
and expensive to catch when six are.

**4. Recompute from scratch.** Re-enter [Phase 0](read.md) and [Phase 1](compute-waves.md) in
full: `resolve_group` again, `list_items` again, `read_blockers` on every item again, and
recompute the chain over the **current live graph**. The same tracker selected at kickoff is
reused; a run never switches trackers part-way.

This is never a partial in-place update of a previously computed table. The graph is not persisted
anywhere, precisely so it cannot drift — recomputing is cheaper than reasoning about staleness,
and a stale graph fails silently.

**5. Dispatch what is now eligible.** Loop back to [Phase 3](spawn.md) for every item whose
blockers all have a confirmed open PR — and a passed review gate, where declared — and that has
not already been dispatched in this run. An item dispatched earlier is never re-spawned.

Newly eligible items enter [Phase 1.5](plan-production.md) first, for their spec and Definition
of Done, then Phase 3.

## On a PR returning to DRAFT — hold everything above it ([D-4](decisions.md))

Leaving draft releases the next item. **Returning to draft retracts that**, and the retraction has
to reach the items already cut from that branch.

When a PR goes `ready` → `draft`, or force-pushes over the commit its descendants were cut from:

**1. Hold every descendant, transitively.** Not just the items whose base is that branch — the
items cut from *those*, all the way up. A change at the bottom of a five-deep stack invalidates
everything above it.

**2. Tell each held implementer to stop where it is.** Do not let it keep working. Its base is
mid-change, so every edit it makes is against a state that will not exist, and every test it runs
proves something about a tree nobody will merge.

Send it a hold, not a kill: the work already done stays, uncommitted or committed, and resumes
after the rebase.

**3. Dispatch nothing new into the held subtree**, even for an item whose blockers technically
still show a ready PR. The ready flag is stale the moment its branch reopens.

**4. Release on the parent's next ready flip**, and only after each held descendant has rebased
onto the new head. Confirm the rebase — `git merge-base --is-ancestor <parent-head> <child-head>`
— rather than asking. A descendant that resumes without rebasing is working on the old base and
its green CI proves nothing about the merged result.

### When a hold is not needed

A parent can change without invalidating its children. **The test is whether the diff touches
anything a descendant consumes**, and it is a check, not an assumption:

```
git diff <old-parent-head> <new-parent-head> --name-only
```

Nothing the descendants read → release them immediately and say why. Otherwise hold.

**Default to holding.** Deciding a change is irrelevant costs one diff; getting it wrong costs
every item above rebuilding on a base that moved under them. Measured on the first real run: one
item was revised **seven times** while three descendants built on it, and each revision silently
invalidated their rebase. Nobody was told to stop, so all three kept working and re-rebased.

### Say it out loud

A hold is not silent. Report which items are held, which parent they are waiting on, and what
released them — the same way a wave release is reported. An implementer that stops without the
run saying why is indistinguishable from one that stalled.

## External blockers are not stackable

An external blocker — another repository, another team's work-group — has no branch in this
stack to build on. It reverts to the older rule: its dependent waits for `read_completion` to
report it **complete**, and that means merged. A stack never spans repositories.

## Form the stack — every time a pull request opens

`gh stack rebase`, `sync` and `merge` operate on a **stack object registered on GitHub**. A chain of
pull requests that merely target each other's branches is not one, and running those commands
against an unformed chain acts on nothing. Form it, then maintain it:

```
gh stack link <bottom-pr> <next-pr> … <top-pr>
```

Arguments go **bottom to top**, in the merge order [Phase 1](compute-waves.md) derived. Re-run it
each time a new pull request opens; it reuses the ones that exist and chains their bases correctly.

**Pass pull request numbers or URLs — never branch names.** Its own help states that *"branch
arguments are automatically pushed to the remote before creating or looking up PRs."* The
orchestrator never pushes, and it has nothing to push: implementers open their own pull requests
draft-first, so by the time this runs every item already has a number. A branch argument here would
make the orchestrator write to a branch it does not own, for no gain.

`link` is the right command rather than `init` / `add` / `submit` because **it keeps no local
tracking state** — its help names this case exactly: *"designed for users who manage branches with
external tools."* This skill's branches are created inside worktrees the orchestrating session is
never checked out into, so there is no working copy for local stack state to live in.

## When a parent changes after its children are cut

Review does not leave the base alone. When a gated parent takes review changes, or any parent
force-pushes, every descendant is now built on a branch that has moved.

```
gh stack rebase
gh stack sync
```

Run it from the orchestrating checkout, which shares its object store with every worktree, then
**verify each descendant's PR still targets the branch it was dispatched against** — a rebase that
retargets a PR to `main` has silently unstacked it.

**Report the cascade by item reference.** A rebase that lands cleanly is still work an implementer
may be sitting on top of mid-edit, and the descendants most likely to conflict are the ones whose
own work overlaps what review changed.

## Fan-in

Linearization ([Phase 1](compute-waves.md)) collapses fan-in: an item with two blockers is cut
from the chain that already contains both, so there is no partial-satisfaction case left to
mishandle. **This holds only while the chain is intact.** If a recompute in step 4 shows a
dependency the chain does not cover — a blocker added on the tracker mid-run — the chain is stale.
Re-linearize and report it; never dispatch the item against a base missing one of its parents.

## Release in the same turn that flips the PR

A ready flip and the dispatch it releases belong to one turn. Splitting them is the most reliable
way this skill stalls: the flip is satisfying, it reads like an ending, and the turn closes on it.

Observed 2026-09-06 — the pattern repeated three times in a ten-item run. The orchestrator flipped
a PR out of draft, wrote its report, and ended the turn with the newly released item never
dispatched. **Nothing reopens the turn.** Not the internal monitor, not the daemon, not the
released item's own eligibility. Each time it cost the wall-clock until a person noticed a run that
looked finished and was not.

So the order inside the turn matters, and it is the reverse of the order that feels natural:

1. Flip the PR out of draft.
2. **Immediately compute what that release unblocks, and dispatch it.**
3. *Then* report — the report names both the flip and the dispatch.

**Report before dispatching and the dispatch will not happen.** Where the window is too small to
do both, say so explicitly and name the item left undispatched, so the next prompt starts from a
stated gap rather than from a run that appears complete.

This is the same failure as ending a turn with work uncommitted ([the runner](runner.md)) seen from
the coordination side: the state is consistent, nothing errored, and the run is simply stopped.

## Ending

The run ends when every dispatchable item has a PR **out of draft** and reported review-ready —
never when anything is merged. An item whose PR is still a draft is still in progress, however
long it has been open.

**"Idle with items left" is not an ending, it is a stall.** Before reporting a run finished, check
that every item is either review-ready, deliberately held with a stated reason, or has a live
implementer. An item that is none of those was dropped between turns.

**The stack merges as a unit, and a human merges it.** `gh stack merge` is theirs to run, after
review, and so is deciding whether to run this skill again afterwards. Both zero-exception
boundaries in `SKILL.md` survive [D-3](decisions.md) untouched: this skill never merges a pull request, and
never pushes to `main`.
