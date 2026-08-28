# Standing Implementer Workflow

Embedded verbatim in every dispatch prompt ([Phase 3](spawn.md)), unchanged from item to item,
so an implementer never needs to re-fetch this skill or invent its own process.

Follow it in order.

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

**4. Run the gate.** Your assignment names the exact command and the directory to run it from —
they come from `project.gate_command` and `project.gate_working_dir` in the repository's
`.orchestrate-project.json`, written when the project was configured.

```
cd <project.gate_working_dir>   # repository root when the key is absent
<project.gate_command>
```

**Run the whole command, never a subset.** A gate that chains lint, types and tests fails a pull
request on any of them, so a green test run alone is not evidence the gate passes.

**If your assignment names no gate command, stop and report it.** Do not infer one from the files
you see. A guessed build command produces a confidently green worktree that fails in CI, and the
implementer who guessed is the last person able to notice.

Environment quirks — an interpreter version, a required variable, a missing local driver — belong
to the project, and the project's own setup is what handles them. Where one bites you anyway,
**report it rather than working around it silently**: a workaround that lives only in your session
is invisible to the next implementer.

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

**5. Update the docs.** Run `live-docs-sync` for changes to real mechanisms or business rules.

**`docs-check.yml` enforces this and will fail your PR.** Any PR carrying a `feat:` or `fix:`
commit that changes no file under `docs/` fails the check. A PR whose commits are all `chore:`,
`refactor:`, `test:` or `ci:` is exempt and exits before the check runs. A second, unconditional
job re-resolves every document `docs/context/01-agent-entrypoint.md` links to and fails naming any
that has gone missing — so moving or renaming a doc means fixing that entrypoint in the same PR.

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

**Where the repository ships a pull-request skill, use it instead of raw `gh pr create`.** In this
one that is **`live-docs-pr-create`**, which generates the body through `live-docs-pr-description`
(reading the diff and the project's context map) and then opens the PR. A hand-written body drifts
from whatever convention the project settled on, and the skill exists precisely so it does not.

Check for such a skill before opening your first PR. If one exists and cannot express something you
need — a draft, or a base branch that is not the default — use it for the body and fall back to
`gh pr create` for the mechanics rather than abandoning it entirely.

Title references the item. This repository has no
pull-request template and no review-triggering label, so add neither.

**The draft exists so progress is visible while you work, not because the work is done.** From
here on, every atomic commit of the implement → gate → commit cycle is pushed to the same branch.
The draft updates itself; you never open a second PR for the same item.

**7. Keep the draft honest.** Each push re-runs `ci` and `docs-check` against your branch, so a
red check on a draft is real feedback about the commit you just pushed, not noise to be tidied up
at the end. Fix it when it appears.

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

**10. Report `worker_done`** to the orchestrator. Completion is reported, not inferred from a PR
appearing — and least of all from a draft appearing.

**11. Stop.** Once the PR is marked ready and its checks are green or pending, your job for this
item is done.

**Never merge, and never push directly to `main`.** These are two separate zero-exception rules,
and they apply identically inside every dispatched worktree — there is no orchestration carve-out.
A human reviews and merges every PR.
