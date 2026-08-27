# Phase 2 — Clarify only what is genuinely ambiguous

One batched question, or none at all. This phase exists to prevent a kickoff questionnaire, not to
create one.

## Single batched call

**At most one clarification call per run.** Every genuine ambiguity found across every item is
batched into that one call — never one question per item, and never a follow-up round for
something that was already knowable when the first call was made.

If nothing is genuinely ambiguous, ask nothing and proceed.

## Legitimate categories

Only these five. Each is real, project-specific ambiguity that Phases 0, 1 and 1.5 could not
resolve on their own:

1. **Scope** — should this run include independent or lower-priority items, or only the core
   dependency chain?
2. **An in-flight item** — an item somebody has already started outside this run: fold it in, or
   leave it alone?
3. **A spec gap [Phase 1.5](plan-production.md) could not close** — `tlc-spec-driven` hit an
   ambiguity it could not auto-size past.
4. **An in-scope item naming another service** — a tracker's scope rule denotes discipline, not
   repository, so an item like "Criar rota … no serviço de webhooks" needs a human to say whether
   it belongs to this run.
5. **Ambiguous repo target** — when the work-group's items could plausibly map to more than one
   repo.

## Never ask about the baked-in defaults

The four defaults in `SKILL.md` — stacked waves released when a PR leaves draft; one implementer per item
per worktree; the CI-and-review gate; never merging — are **never** the subject of a question here,
under any framing:

- Never ask whether waves should be stacked, or what a PR should target — the linearized chain
  ([Phase 1](compute-waves.md)) settles every base branch.
- Never ask whether each item needs its own worktree, or whether two could share state.
- Never ask whether the CI/review gate can be skipped for a particular item.
- Never ask whether to merge a ready PR, or offer to merge one "just this once".

These are settled structural facts. Asking about any of them is exactly the redundant,
already-answered question this phase exists to avoid.

Likewise, do not ask about anything already decided in the work-group's own description
([Phase 0](read.md)) — those constraints are honored verbatim, not re-litigated.
