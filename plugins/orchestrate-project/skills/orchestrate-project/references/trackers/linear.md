# Linear tracker — a contract note, not an implementation

**This tracker does not exist.** Nothing in this skill selects it, no code here has been run against
Linear, and every mapping below is an obligation a future implementation must satisfy, not a
description of behaviour anyone has observed.

The file exists so the contract's claim is falsifiable. [The tracker contract](../contract.md) says
a third tracker is a tracker document rather than a rewrite of the skill. This is that document,
written to the point where the remaining work is verification against a real workspace — and stopped
there deliberately, because shipping an untested tracker path is worse than shipping none.

## Capability table

Every row is a declaration of intent. None is implemented.

| Operation | Required? | Declared |
| --- | --- | --- |
| `resolve_group` | required | **not implemented** |
| `list_items` | required | **not implemented** |
| `read_blockers` | required | **not implemented** |
| `read_completion` | required | **not implemented** |
| `mark_in_progress` | optional | **not implemented** — and it is optional, so an implementation may leave it that way |

A tracker whose required reads are unimplemented is not selectable. That is the correct state for
this file, not a defect in it.

## What each read must map to

### `resolve_group(identifier) -> group`

A Linear **Project** — or a **Cycle**, if the workspace organises delivery that way; the choice must
be made once and recorded here, not left per-run. It must accept the group's identifier, its name,
and its URL, with all three landing on the same group, and return the group's description text
verbatim so programme-level facts stay readable to the phases that need them.

The tracker contract's failure rule applies unchanged: an identifier that resolves to nothing stops
the run, and one that resolves to several reports the candidates and stops.

### `list_items(group) -> item[]`

Every issue belonging to that group, paged to the end. Linear's API is cursor-paginated, so
"complete or nothing" means following the cursor until it is exhausted, never taking the first page.

Each item must carry a stable id, the human reference an implementer would type (Linear's
`TEAM-123` form), the title, the body verbatim, and a `kind` taken from a structured field. If the
workspace expresses issue type through labels rather than a typed field, `kind` is **absent** —
absent is a valid answer, and inferring it from a label would break the contract's rule that `kind`
is structured data or nothing.

### `read_blockers(item) -> item[] | UNAVAILABLE`

Linear records issue relations, and a blocking relation is among them. The expectation is that this
read is **implemented rather than declared `UNAVAILABLE`** — that expectation is unverified, and
confirming it is the first thing to check against a real workspace.

Only the relation counts. A "blocks" written in a description, a sub-issue link, a parent-child
relationship, or a label convention is not a dependency, exactly as on every other tracker.

If it turns out a workspace cannot expose these relations to the token in use, the honest outcome is
`read_blockers: UNAVAILABLE` in the table above, and the contract's consequence follows: wave
computation refuses. Not an empty list.

### `read_completion(item) -> bool`

A boolean derived from the workflow state's **type** — Linear groups states into types such as
started, completed and cancelled — and never from the state's name. State names are workspace-
authored and frequently translated, so name matching silently misclassifies exactly the way it does
on the Jira path.

Then the second half. The contract requires that completion cannot be set ahead of the work wherever
a tracker's own state is something a human can set by hand, and a Linear state is. So a completed
state must be conjoined with a fact nobody types: the merged pull request attached to the issue.
Linear's PR/MR attachments are the obvious carrier, and how reliably they record the merge — and
against which branch — is unverified.

### `mark_in_progress(item)` — optional

Linear can move an issue into a started state, so an implementation may declare this one implemented.
It may equally leave it absent. Under [D-2](../decisions.md) the orchestrator behaves identically either way, and
nothing downstream may depend on it having happened.

**Connection.** Linear's own hosted MCP server, `https://mcp.linear.app/mcp`. Nothing to install,
OAuth 2.1, free on every plan. Configuration is one key, and **no credential at all** — the OAuth
grant lives in the MCP client, not in a file this repository commits:

```json
{ "tracker_config": { "linear": { "workspace": "acme" } } }
```

The `/sse` endpoint is retired; `/mcp` over Streamable HTTP is the current one.

## Transport

**Linear's GraphQL API directly.** The alternative was a runtime-provided Linear CLI; that runtime
is gone, and depending on any dispatch tool for a read path that has nothing to do with worktrees
would re-couple the tracker layer to the runner — exactly the boundary [D-1](../decisions.md) exists to hold.

The transport is recorded here, in this file, and nowhere else. A phase never learns it.

**A dispatched implementer needs this server granted to it.** [Phase 3](../spawn.md) passes
`--mcp-server linear` on the spawn; an MCP server is held by a session, not by the machine, so a
child does not inherit the orchestrator's. This was a real objection to reaching a tracker over MCP
at all under the previous runtime, which had no way to grant one — see [D-9](../decisions.md).

**This backend ships unvalidated.** No Linear workspace exists to test it against, so
`/orchestrate-init` probes it like any other tracker and a failure is loud, but nothing here has
been proven end to end. Treat the four contract reads below as a specification to verify, not as
behaviour already observed.

## What shipping this requires

Not more writing. Verification.

1. **A Linear workspace to test against.** Every mapping above is derived from the contract and from
   how Linear is generally understood to work, not from a live read. Two of them — that blocking
   relations are exposed as relations, and that a merged pull request is reliably attached — are the
   ones most likely to be wrong.
2. **Each of the four reads executed once against that workspace, with its real output recorded in
   this file**, the way the GitHub tracker records its own. A tracker that has never been run is a
   guess with a table around it.
3. **A group holding two issues where one blocks the other**, to confirm the wave computation
   produces the same shape it produces on the other two trackers. That is the contract's real test.
4. **The transport decision above, taken and written down.**

Until all four are done, this file stays a contract note.

## Nothing selects this tracker

- It is absent from the tracker selection list the entrypoint offers.
- No repository configuration value names it.
- Asking for it explicitly must stop and say it is not implemented, and must never fall back to
  another tracker.

Adding the entry that makes it selectable is the **last** step of building it, never the first.
