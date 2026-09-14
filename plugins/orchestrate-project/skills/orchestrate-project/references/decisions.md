# Decisions

Why this skill behaves the way it does. Each entry is a decision that cost something to learn, kept
here so a reader can check a rule's reasoning instead of taking it on faith — and so a future change
knows what it would be overturning.

These are the skill's own decisions. They were originally numbered inside one project's decision log;
that log is not shipped, and a reference to it would resolve to nothing for anyone else. The
numbering here is this plugin's.

---

## D-1 · The tracker is behind a contract of four reads

**Decision.** Every tracker read goes through exactly four operations — resolve a work-group, list
its items, read blocking relations, read completion — plus one optional write. One document per
tracker implements them, and no phase ever names a tracker.

**Why.** A second tracker arrived. Rewriting the wave logic for it would have meant maintaining the
same graph computation twice, diverging quietly.

**Cost, stated honestly.** Two trackers' models genuinely differ — an epic is not a milestone, a
workflow status is not a merged pull request — so the abstraction can leak, and every change costs
one implementation per tracker. The mitigation is scope: the contract covers only what the
orchestrator *reads*, never a general tracker abstraction.

## D-2 · The optional write is optional, and never emulated

**Decision.** `mark_in_progress` is the one write, and a tracker may declare it absent. When absent,
nothing else changes: no wave number, no dispatch decision, no release gate may depend on it.

**Why.** A label applied at dispatch looks like a workflow transition until the day it does not.
Faking a capability makes two unlike things look alike, and the difference surfaces during a live
run rather than during review.

## D-3 · A wave releases on ready-for-review, not on merge

**Decision.** An item starts once every blocker has a pull request **marked ready for review**. Its
worktree is cut from its blocker's branch, its pull request targets that branch, and the stack
merges to the default branch as a unit, after review, by a human. Implementers open their pull
request as a **draft on the first commit**, so progress is visible from the start; a draft releases
nothing.

**Why.** Under a merge gate, a four-item chain costs four sequential review-to-merge round-trips
before the last item can start. The work is not what makes that slow.

**Cost.** Larger than it first looks. Nothing is validated against the default branch until the end,
so a defect at the bottom is found after everything above it is written. Draft-first costs a CI run
per pushed commit. Implementers work on bases containing unreviewed code and must be told not to fix
what belongs to the pull request below them.

## D-4 · A pull request returning to draft holds everything above it

**Decision.** A parent going back to draft — or force-pushing over the commit its descendants were
cut from — **holds every item stacked above it, transitively**. Held implementers stop where they
are. The hold lifts when the parent is ready again *and* each descendant's rebase is confirmed with
`git merge-base --is-ancestor`, not asked about.

**Why.** D-3 gave the stack a release signal and no retraction. On the run that produced this rule, a
parent was revised seven times while three descendants built against it; none was told to stop, and
two later reported green local gates against states that were never pushed.

**Escape.** One `git diff <old> <new> --name-only`. When the change touches nothing a descendant
consumes, skip the hold — but run the check rather than assuming.

## D-5 · The tier follows what the item produces

**Decision.** An item that writes code against a written spec runs on the execution tier. An item
whose deliverable is *analysis, classification, a survey or a decision input* runs on a high tier —
as does **any verification of another item's output**.

**Why.** For an implementation item, complexity is absorbed once in planning; the answer to a hard
one is a better plan, not a bigger worker. **That reasoning does not transfer to an analysis item**,
because there is no upstream plan to absorb the judgment into — the judgment is the deliverable. An
analysis item run on the execution tier produces an artifact that later items consume as fact.

**Cost.** High-tier items cost materially more, and the routing is a judgment call made from a
Definition of Done rather than a tracker field, so it can be got wrong in both directions.

## D-6 · Verification depth follows blast radius, and cheap checks run first

**Decision.** A leaf item nothing depends on gets mechanical checks and **no verification agent**. An
item consumed as fact by two or more dependents gets one deep pass. A **re-verification is scoped to
the diff**, never a re-run of the original pass. Cumulative spend is reported; when it exceeds what
the run was willing to spend, drop to cheap checks **and say so**.

**Why.** Routing all analysis and all verification to a high tier without a budget cost roughly
384k tokens across four passes on one run, and the single largest item was a 103.6k-token pass that
re-verified an entire artifact to check the two citations a revision had changed.

**Cost, in the direction of missing things.** The deep passes are what caught fabricated provenance
and citations pointing at never-executed code — things no CI check surfaces. Cheap checks target
exactly those observed failure modes and will let other classes through. A leaf item now ships on
mechanical checks alone.

## D-7 · Nothing about a project is hardcoded

**Decision.** The gate command, its working directory, the bootstrap marker, the conventions
document and every tracker connection detail come from the consuming repository's
`.orchestrate-project.json`. A missing key stops the phase that needs it and names the key.

**Why.** The skill previously carried one project's build command, another project's Definition-of-
Done rules, and a third project's Atlassian tenant. Pointed at a different repository it would have
instructed every implementer to run the wrong thing, and nobody downstream could tell an invented
rule from a real one.

**Consequence.** Absent is a legitimate answer and is recorded as `null`, so a phase reads a
decision rather than a gap. No value is ever carried over from another repository.

## D-8 · Never a guessed flag

**Decision.** Every runtime command in [the runner](runner.md) is captured from `--help` on a pinned
build, with the version recorded. A version bump invalidates the table and requires re-capture.

**Why.** Three bugs in one migration came from writing a command from convention: a `--version` flag
that did not exist, a version string compared with a prefix it does not carry, and a `daemon status`
subcommand whose invalid form printed help and exited 0 — reporting a running daemon as stopped.
Each looked correct in review and failed only against the real binary.

**This rule was discovered twice, independently.** A separate lineage of this skill reached the same
conclusion from a different failure set and wrote its own command table for the same reason: *five*
defects that its fixture traces did not catch — a wrong MCP tool prefix, a lookup parameter that
took a slug rather than a URL, a boolean default that ran the wrong way, wrong JSON field names, and
executable resolution landing on an unrelated program. **All five were tool-surface errors, not
logic errors.** A documented algorithm can be internally consistent and still name flags that do not
exist. Eight defects across two lineages, zero of them caught by review.

## D-9 · A tracker reached over MCP is granted to every dispatched session

**Decision.** Where the selected tracker uses an MCP server, [Phase 3](spawn.md) grants it to each
dispatched implementer (`--mcp-server <id>`). If the orchestrating session does not itself hold that
server, the grant cannot be made and the dispatch stops rather than proceeding.

**Why.** An MCP server belongs to the session that holds it, not to the machine. The
[standing workflow](standing-implementer-workflow.md) has implementers touch the tracker — the
optional started-write, the Definition of Done written back, a review-stage transition — and none of
those is reachable from a worktree that was never granted the server.

**Where this came from.** An earlier copy of this skill rejected reaching Linear over MCP outright,
for exactly this reason: *"it works identically inside a dispatched worktree, where the MCP may not
be reachable at all."* That objection was correct against a runtime with no way to grant a server to
a child, and it drove that copy onto a CLI instead. The current runtime can grant one, so the
objection is answered rather than dismissed — but the answer is a required flag, not an assumption.

**Failure shape, which is why this is a decision and not a footnote.** Without the grant the
implementer's tracker writes do not error. They are silently skipped, and the board simply never
updates. A missing write that looks like a working run is worse than a loud failure.

## D-10 · The stack is a registered object, not a chain of pull requests

**Decision.** Every time an implementer's pull request opens, re-form the stack with
`gh stack link <bottom-pr> … <top-pr>`, passing **pull request numbers, never branch names**.

**Why.** `gh stack rebase`, `sync` and `merge` act on a stack registered on GitHub. Pull requests
that merely target one another's branches look like a stack and are not one, so those commands act
on nothing — silently. This skill maintained bases by hand and called the maintenance commands
without ever forming the object they operate on.

**Why `link` rather than `init` / `add` / `submit`.** It keeps no local tracking state; its help
names the case exactly — *"designed for users who manage branches with external tools."* Branches
here are created inside worktrees the orchestrating session is never checked out into, so there is
no working copy for local stack state to live in.

**Why numbers and not branches.** Its help states that branch arguments are *pushed to the remote*
before being resolved. The orchestrator never pushes. Implementers open their pull requests
draft-first ([D-3](decisions.md)), so a number always exists by the time this runs, and passing one
keeps the never-push boundary intact.

**Found by comparing lineages, not by review.** Four copies of this skill had diverged across four
repositories; one had solved this and the others had not. That divergence is the reason this plugin
exists.

## D-11 · A production action is authorized per instance, and leaves a revert behind

**Decision.** Any destructive or outward action on production — purging a queue, changing a
production environment variable, repointing live data, triggering a deploy that changes
configuration — needs the user's explicit authorization **for that instance**. Authorization for one
does not carry to the next, however similar. Each gets a written log entry: what changed, the state
before, and how to revert it — or an explicit **"not reversible"** where it is not.

**Why.** These actions sit outside every safety this skill has. No pull request carries them, no
review sees them, no CI gates them, and the stack's merge boundary does not apply. A run that is
fixing a production incident is also the run under the most pressure to "just do" one, and the
consequence lands on real users rather than on a branch.

**Verification follows the same standard.** A production change is verified by driving the real
surface — fetch the actual resource and read its status — never by a UI that opens. **Measure from
the machine that matters**: the same resource can succeed from the server and fail from a consumer's
network, or the reverse, and a result obtained on the wrong machine is not evidence about the other
one.

**Cost.** Round trips to the user in the middle of an incident. Paid deliberately: the alternative is
an action nobody can reconstruct or undo.

## D-12 · A wrong claim is retracted everywhere it travelled

**Decision.** When a claim the orchestrator made proves wrong, it is **retracted explicitly** in every
place it propagated: the briefings and steers that carried it, any persistent notes the orchestrator
keeps across sessions, the run-state file, and pull-request bodies. Where an implementer's pull
request still carries the claim and a steer cannot reach the implementer in time, the orchestrator
**edits the body itself and says in the pull request that it did**.

**Why.** An orchestrator's claim does not stay in the chat. It is copied into prompts, and from there
into commits, pull-request bodies and notes that later sessions read as fact. Observed: a measurement
produced by an instrument that ignored its own parameter was briefed to an implementer, and retracted
mid-run while the implementer was already working from it ([Phase 4](monitor.md) §7.6). Correcting
the chat alone would have left the wrong number in every place a reviewer actually looks.

**Cost.** Editing a pull-request body the implementer wrote is a write to something the orchestrator
does not own. It is limited to removing the orchestrator's own retracted claim, and it is disclosed
in the pull request every time.

## D-13 · Cost follows context × turns, so the orchestrator delegates, filters, and steps down a tier

**Decision.** The orchestrator spends at most ~5 tool calls on any one question before delegating
it. Its monitors emit only actionable events. It compacts on a schedule and resumes from RUN-STATE.
It retries a measurement nothing waits on at most twice, runs one verification job per PR head, and
keeps chat updates short. Its mechanical turns run on the execution tier, and its judgement turns on a
high tier.

**Why.** Summed from every session transcript of a real multi-week run: 19.4 B tokens, **98% of
them cache reads and 0.3% output**. Each turn re-reads the whole context, so cost ≈ context size ×
turns. Orchestrator sessions took ~52% of the run, against ~120 implementer worktrees sharing the
rest. One orchestrator session alone was 2.88 B tokens, 15% of the lifetime spend: a production
investigation run inline, monitors waking it for non-actionable state changes, retries at full
context, long status replies, and the top tier on every mechanical turn.

**What this overturns.** The model policy in `SKILL.md` said "Opus orchestrates", which put every
orchestrator turn on the top tier. It now says the top tier *judges*. D-5 is unchanged: items are still tiered by what they produce, and verification of another item's output
stays high. What moved is the tier of the orchestrator's own mechanical loop.

**Cost, in the direction of missing things.** A delegated question returns only a conclusion, so the
orchestrator no longer sees the evidence it would have noticed in passing. A filtered monitor will not
surface a state change nobody predicted was actionable. An execution-tier loop can misjudge what
needs escalation. The mitigations are an explicit escalation list and the rule that a verdict comes
with its evidence. But this decision trades some peripheral vision for roughly half a run's spend,
knowingly.
