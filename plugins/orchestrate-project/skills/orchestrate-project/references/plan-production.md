# Phase 1.5 — Plan production and Definition of Done

Runs once per item, the moment it becomes wave-eligible and before [Phase 3](spawn.md) writes
its dispatch prompt.

**This is where complexity is absorbed.** Implementers run on the execution tier and are never
escalated (see the model policy in `SKILL.md`), so a hard item is answered with a *better plan*,
not a bigger worker. The plan is written once; the work is executed in parallel across every
implementer, so this is the cheapest place to put the thinking.

## 1. Decide whether an item is too thin

An item is **thin** when its body is missing any of:

- **Acceptance criteria** — no testable statement of done.
- **Area of change** — nothing indicating which modules or files it touches.
- **Test scenarios** — nothing describing what a passing implementation is verified against.

Items on this board are generally well scoped, so this is expected to be the exception. An item
with all three is dispatched from its own body and skips straight to section 3.

## 2. Produce the missing plan

For a thin item, invoke `tlc-spec-driven`'s Specify phase — auto-sizing into Design and Tasks
when its own complexity rules call for it — using the item's title, body and comments as input.
Output lands at:

```
.specs/features/<reference-slug>-<kebab-title-fragment>/
```

`<reference-slug>` is the item's human-facing reference lowercased and reduced to filename-safe
characters, whatever shape the selected tracker gives that reference.

The dispatch prompt is then built from that spec, **not** from the thin body.

**A dependency discovered while planning that the tracker does not record as a blocking relation
is surfaced to a human as a discrepancy** — never silently resolved by creating the relation. A
plan-time discovery correcting an authoring-time gap is exactly the kind of thing a person should
see.

## 3. Derive the Definition of Done

Every item gets a DoD, thin or not. It is **generated** from the item plus the project's own
conventions document, not demanded of the item's author — the gap here is not specification, it is
that "done" is implicit.

**Read the conventions document named by `project.constitution_path`** in the repository's
`.orchestrate-project.json`. That path is per-repository and was recorded when the project was
configured; this file names no path of its own, because a fixed one points at whichever repository
the skill happened to be written in.

**Where no conventions document is configured, derive the DoD from the item alone and say so.**
State plainly that no project rules were applied. Inventing rules the project never adopted is
worse than a thin DoD: implementers cannot tell an invented constraint from a real one, and they
will satisfy both.

Where a document *is* configured, include only the rules that actually apply to this change. The
shape to aim for:

| Include when the change… | DoD item |
| --- | --- |
| touches a rule the conventions document states | That rule, quoted closely enough to be checkable |
| can fail in a new way | The project's own failure-handling convention |
| adds a unit the project tests | The project's own testing expectation for that unit |
| — always — | The gate named in `project.gate_command` passes; the change stays within the item's scope |

Omit rows that do not apply. A DoD padded with irrelevant items trains implementers to skim it, and
a DoD quoting another project's rules trains them to distrust it.

**Never copy a rule from memory of another repository.** Every DoD line traces to a line in this
project's configured document, or to the item itself.

## 3.5 Decide the item's tier

The Definition of Done you just derived is what settles it (AD-023, and the table in `SKILL.md`).

Ask what the item's deliverable **is**, not how hard it sounds:

- A DoD dominated by "cite the evidence for each X", "classify every Y", "state what could not be
  determined" → the deliverable is judgment. **High tier.**
- A DoD dominated by "implement X", "the test asserts Y", "the gate passes" → the deliverable is
  code against a plan. **Execution tier.**

A tracker's own wording does not decide this. An item titled like a build task whose acceptance
criteria are all evidentiary is an analysis item.

**The execution tier is the default and needs no justification. A high tier is a spend decision
and must carry one** — a `tierReason` that names what judgment the item requires and what would go
wrong on the execution tier. "It looks hard" is not a reason; "the deliverable is the evidence" is.

Only **one** high-tier implementer runs at a time (AD-024). If a wave contains two, the second
waits — they are the items most likely to exhaust a quota, and one did on the first real run.

Record the decision and its reason in `meta.json` alongside the base branch. [Phase 3](spawn.md)
verifies the tier that actually resolved against it, and a mismatch aborts the wave — so an
unrecorded decision reads as "execution tier" and will abort a high-tier item on arrival.

## 4. Where the DoD goes

**Into the dispatch prompt, and nowhere else yet.** Nothing is written to the tracker before
dispatch beyond the contract's optional `mark_in_progress`, and an item's body is never modified —
it stays human-authored.

The implementer writes the completed DoD back when it finishes, where the selected tracker defines
a place for it ([standing workflow](standing-implementer-workflow.md)). That report is what a
reviewer reads next to the PR: the checklist the agent was held to, and the honest result against
each entry — including any it could not satisfy.
