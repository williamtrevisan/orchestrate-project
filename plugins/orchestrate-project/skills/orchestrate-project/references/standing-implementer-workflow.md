# Standing Implementer Workflow

Embedded verbatim in every dispatch prompt ([Phase 3](spawn.md)), unchanged from item to item,
so an implementer never needs to re-fetch this skill or invent its own process.

Follow it in order.

---

## Read this before step 0: never background a command and then wait for it

Run the gate, the build and the test suite **in the foreground**, and read their output.

A turn that ends while a background job is still running is not woken by it. The notification has
nowhere to land, the result is never read, and the session goes idle holding uncommitted work.
From outside it looks finished — the session reports `idle`, the tracker shows the item
dispatched, and the branch never moved.

This is not hypothetical. An implementer wrote its view, its route file, its menu entry, its tests
and a regenerated route tree, then backgrounded the gate and ended its turn saying it would wait
for the notification. The work sat uncommitted in the worktree at its base commit until a human
looked. Nothing reported an error, because nothing had failed — the turn had simply closed.

**A slow gate is fine.** Waiting in the foreground for ten minutes is the correct behaviour.
Backgrounding it to stay responsive is what loses the work. The same applies to sleeping in a
polling loop: if you find yourself waiting rather than doing, you have already ended the turn.

---

**0. Never delete or move your assignment file, and never copy it into the worktree.** It lives
outside the git tree precisely so it survives a crash, a stall, or a relaunch, and so it can never
be committed. An implementer that destroys its own spec cannot be resumed.

**1. Tell the tracker you have started — only where the selected tracker declares that write.**
It is the contract's one optional operation. Follow that tracker's own rules, resolved at runtime
and never from a hardcoded identifier. If the tracker declares it absent, or the expected
transition is not offered, skip it and carry on; the work matters more than the label.

**2. Read the relevant files before editing anything.** The item names its affected modules;
read them first. Editing before reading is how an agent reimplements something that already exists.

**3. Implement and test as two workstreams within this one item.** Both, always — never code
without its tests, never tests deferred to a follow-up item. Run `tlc-spec-driven`'s Execute
cycle: implement → gate → atomic commit.

**Stay inside this item's scope.** Anything you notice outside it — a bug, a refactor, a
tempting cleanup — gets reported, not done.

**Where your assignment names another branch or pull request as the owner of some files, a defect
you find there is reported to that owner, never fixed here** — even when it is real and the fix is
obvious. Someone else is changing those files right now; a second fix on your branch collides with
theirs on rebase and puts one change in two reviews.

**4. Run the gate.** Your assignment names the exact command and the directory to run it from —
they come from `project.gate_command` and `project.gate_working_dir` in the repository's
`.orchestrate-project.json`, written when the project was configured.

```
cd <project.gate_working_dir>   # when the key is absent: YOUR WORKTREE's root
<project.gate_command>
```

**When the key is absent the fallback is your own worktree, never the orchestrating clone.** The
phrase "repository root" is ambiguous in a worktree and resolves the wrong way by default: a
dispatch prompt that substitutes the orchestrator's checkout path gates a tree that does not
contain your change, then reports a pass that says nothing about your work. Observed on a real
run: **13 dispatch prompts** across several waves carried the orchestrating clone's absolute path,
and every "gate clean" claim they produced was unfounded. Whoever writes the prompt
([Phase 3](spawn.md)) resolves this path to the worktree it is dispatching.

**Run the whole command, never a subset.** A gate that chains lint, types and tests fails a pull
request on any of them, so a green test run alone is not evidence the gate passes.

**In the foreground**, however long it takes — see the warning above this list.

**If your assignment names no gate command, stop and report it.** Do not infer one from the files
you see. A guessed build command produces a confidently green worktree that fails in CI, and the
implementer who guessed is the last person able to notice.

Environment quirks — an interpreter version, a required variable, a missing local driver — belong
to the project, and the project's own setup is what handles them. Where one bites you anyway,
**report it rather than working around it silently**: a workaround that lives only in your session
is invisible to the next implementer.

**A gate that did not finish is not a gate that passed, and not one that failed either.** Two
shapes of this, both of which read as a result if you only look at the exit status:

- **Killed, not failed.** A gate stopped before it finished reports no failures because it never
  got far enough to find any. Say "the gate did not complete", never "the gate passed", and name
  why.

  **Identify the killer, because the remedies are opposite.** The OS out-of-memory killer takes
  the largest process when the machine is genuinely out of memory; the fix there is a narrower
  wave or a quieter box. But an agent harness may *also* reap **backgrounded** commands under
  memory pressure — proactively, while several gigabytes are still free — and that fix is simply
  not to background it. Observed 2026-09-06: six consecutive backgrounded gate runs were reaped,
  including one pinned to a single worker that died before printing a line; the same gate then ran
  to completion in the foreground, on the same machine, minutes later, and its three checks were
  green. A whole day was spent lowering worker counts against the wrong cause.

  This is the second, independent reason for the foreground rule at the top of this page. The
  first is that a turn ending on a background job never sees its result. The second is that the
  job may not survive to produce one.
- **Exited 0 having done nothing.** A wrapper that shells out can exit 0 while the tool it invoked
  refused its arguments — an unknown flag, a bad config path — so a run that never executed a
  single test looks identical to a clean one. Read the output, not the status. Observed
  2026-09-05: a full suite invoked with an unsupported CLI flag aborted on the parse error and
  still exited 0, and was reported as green until the log was actually read.

**When the full gate genuinely cannot run, verify the blast radius instead — and say that is what
you did.** Find every consumer of what you changed and run their tests; combine that with a
project-wide typecheck and a lint of the changed files. That is a real, bounded argument, and it
is honest in a way "gate green" would not be. It is a fallback for a broken machine, never a
substitute chosen for speed.

**A locally green gate is not always a green CI.** Where the project measures something locally
unmeasurable — coverage without a driver installed, a check that only runs on CI hardware — write
the change as if it were enforced, because in CI it is.

Your worktree is a separate checkout, so anything the project's setup creates inside it — a local
database, a cache, generated files — is yours alone and runs in parallel with other implementers
without collision.

Fix every failure your own change surfaces. CI must be green before you mark the PR ready — a red
check on a draft is expected mid-flight and is fixed as it appears, not swept up at the end.

**Two exceptions, and the second is specific to working on a stack:**

- Failures originating *inside* a dependency directory are reported, not chased — a dependency defect is not
  this item's work.
- **A failure that belongs to the parent PR your branch is stacked on is reported, not fixed.**
  Your base contains unreviewed work from the item below you. Fixing its defect here puts the same
  fix in two open PRs, which conflicts on rebase and hides the defect from the review that should
  have caught it. Report it by item reference and carry on.

**5. Update the docs, where this project asks for it.** Your assignment's Definition of Done is
derived from the project's own conventions document, so it — not this page — names whether
documentation is expected, where it lives, and whether CI enforces it.

**Do what your assignment says, and nothing this page invents.** If it names a documentation skill
or a docs check, follow it. If it is silent, this project has no such requirement and you write no
docs to satisfy a rule that does not exist. A step performed for another project's convention is
wasted work at best, and a confusing diff at worst.

**6. Open a draft PR on your first commit, then keep pushing into it.**

Commit with a Conventional Commits message and the `Co-Authored-By` trailer; never `--no-verify`.
Push to the **remote branch name this repo uses**, which is not your local worktree branch:

```
git push -u origin HEAD:refs/heads/<prefix>/<ITEM-REF>
```

`<ITEM-REF>` is the item's human-facing reference, in whatever shape the selected tracker gives
it — never a shape assumed from the look of a reference string. `<prefix>` is derived from the
item's `kind` by that same tracker's branch-prefix rule, and `kind` is structured data or it is
absent. Your local branch follows the runner's own `run_branch_namespace` and stays as-is — it is a
runtime implementation detail, and renaming it desyncs the runner from the worktree it created.

**Immediately after that first push, open the PR as a draft** — against your parent's branch, not
against `main`. Your assignment names the base branch you were dispatched from; use that exact
value.

```
gh pr create --draft --head <prefix>/<ITEM-REF> --base <BASE-BRANCH>   # see below — prefer the project skill
```

`<BASE-BRANCH>` is `main` only if you are the bottom of the stack. **Opening against `main` from
anywhere else silently unstacks your PR** and shows your diff on top of work that is not in your
base — the orchestrator checks `baseRefName` for exactly this and will refuse to release anything
built on you.

**Where the repository ships a pull-request skill, use it instead of raw `gh pr create`.** A
hand-written body drifts from whatever convention the project settled on, and such a skill exists
precisely so it does not. Look for one before opening your first PR — your assignment names it if
the project has one. If it exists but cannot express something you need — a draft, or a base branch
that is not the default — use it for the body and fall back to `gh pr create` for the mechanics
rather than abandoning it entirely.

**The title follows the project's own commit convention, not a shape invented here.** Where the
project uses Conventional Commits — check `git log` on the default branch before writing it — the
pull request title is a Conventional Commits subject like any commit: `feat(scope): …`. Reach for
your own first commit's subject; it is usually already the right title.

Do not open with the item's reference unless the project's convention document asks for it. A
tracker that links pull requests by branch name already has the link, so a reference in the title
adds nothing and displaces the type and scope a reader scans for.

Follow the project's own pull-request template and labelling rules where it has them, and add
neither where it does not — again, from your assignment rather than from this page.

**The draft exists so progress is visible while you work, not because the work is done.** From
here on, every atomic commit of the implement → gate → commit cycle is pushed to the same branch.
The draft updates itself; you never open a second PR for the same item.

**7. Keep the draft honest.** Each push re-runs whatever checks the project gates pull requests
on, so a red check on a draft is real feedback about the commit you just pushed, not noise to be
tidied up at the end. Fix it when it appears.

**A check that fails on work you did not touch is reported, not chased.** A repository whose trunk
is not green will hand you inherited failures; confirm against the project's own baseline before
treating one as yours, and name it in the pull request instead of fixing it out of scope.

Update the PR body as the shape of the work settles, so someone watching the draft can tell what
is done and what is still open. A draft whose description still describes the first commit is
worse than no description.

**8. Mark it ready for review — this is the moment that matters.**

Only when the work is complete, the full gate passes, and the docs are updated:

```
gh pr ready <PR-NUMBER>
```

**This is the signal the orchestrator releases the next item on.** A draft releases nothing —
anything cut from your branch while you are still working would build on a stub. Flipping to ready
means: this branch is a base someone else can stand on.

Never flip a PR to ready to unblock a teammate, to show progress, or because the item is
"basically done". If it is not finished, it stays a draft.

**9. Write the Definition of Done back to the item**, where the selected tracker defines a place
for it. One report: each DoD entry with what you actually delivered against it, plus the PR URL.
**Any entry you could not satisfy is stated explicitly** — never quietly omitted. Then make the
review-stage transition, where that tracker defines one.

**If the tracker refuses the write** — a plan limit, a missing permission, a server that is not
reachable — do not improvise a substitute on the tracker. Put the same Definition of Done report in
the pull-request body, state in your completion report that the tracker write was refused and with
what error, and carry on. The orchestrator tells the user.

**10. Report `worker_done`** to the orchestrator. Completion is reported, not inferred from a PR
appearing — and least of all from a draft appearing.

**11. Stop.** Once the PR is marked ready and its checks are green or pending, your job for this
item is done.

**Never merge, and never push directly to `main`.** These are two separate zero-exception rules,
and they apply identically inside every dispatched worktree — there is no orchestration carve-out.
A human reviews and merges every PR.
