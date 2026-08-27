# GitHub tracker

One implementation of [the tracker contract](../contract.md), against GitHub milestones, issues and
**native issue dependencies**. This is the only place GitHub nouns are allowed to appear.

Everything here goes through the `gh` CLI. No MCP server, no GitHub SDK, no new dependency — `gh` is
already installed and authenticated for the repository this skill runs in.

**Connection.** The repository is `<owner>/<repo>`, taken from the run's own checkout
(`gh repo view --json owner,name`). The default branch comes from the same call and is not assumed
to be `main`.

## Capability table

| Operation | Required? | Declared |
| --- | --- | --- |
| `resolve_group` | required | implemented — a milestone |
| `list_items` | required | implemented — the milestone's issues, pull requests excluded |
| `read_blockers` | required | implemented — `dependencies/blocked_by` |
| `read_completion` | required | implemented — closed **and** its closing pull request merged into the default branch |
| `mark_in_progress` | optional | **absent** — see [why](#mark_in_progress-is-absent) |

## Contract mapping

| Contract operation | GitHub implementation |
| --- | --- |
| `resolve_group(identifier)` | A milestone, resolved from its number, its exact title, or its URL |
| `list_items(group)` | `GET repos/{owner}/{repo}/issues?milestone=N&state=all`, filtered to `.pull_request == null` |
| `read_blockers(item)` | `GET repos/{owner}/{repo}/issues/{n}/dependencies/blocked_by` |
| `read_completion(item)` | issue `state == "closed"` **AND** a pull request closing it merged into the default branch |
| `mark_in_progress(item)` | not implemented, declared absent |

---

## 1. `resolve_group` — the milestone

Three identifier forms, all landing on the same milestone.

| Form | Example | How |
| --- | --- | --- |
| Number | `3` | `gh api repos/{owner}/{repo}/milestones/3` |
| URL | `https://github.com/melhorenvio/shopify-envios/milestone/3` | Take the trailing path segment as the number, then resolve as above |
| Title | `Schema adoption` | List and match exactly |

```bash
# by number, or the number extracted from a URL
gh api "repos/$OWNER/$REPO/milestones/$NUMBER"

# by exact title — state=all, so a closed milestone still resolves
gh api "repos/$OWNER/$REPO/milestones?state=all&per_page=100" --paginate \
  --jq '.[] | select(.title == "Schema adoption") | .number'
```

**`state=all` is not optional.** The default is `state=open`, and a milestone closed after its front
finished must still resolve — its issues are blockers for other fronts.

Failures, per the contract's failure rule — stop, never fall back to a search:

- **Number or URL that does not exist** → `404 Not Found`. Report the number and stop.
- **Title that matches nothing** → an empty result from the filter above. Report the title and stop.
- **Title that matches more than one milestone** → ambiguous. Report every candidate number and
  title, and stop. Never pick the first.

The milestone's `description` is returned **verbatim** to the contract, untouched and untrusted.
Programme-level facts — the front's objective, its person-week estimate, the decision identifiers
that constrain it, whether it is owned outside this team — are read from that text by the phase that
needs them, not parsed into structure here.

## 2. `list_items` — the milestone's issues

```bash
gh api "repos/$OWNER/$REPO/issues?milestone=$NUMBER&state=all&per_page=100" --paginate \
  --jq '.[] | select(.pull_request == null) | {number, title, state, kind: .type.name}'
```

Three things this command gets right, each of which fails silently if dropped:

- **`select(.pull_request == null)` is mandatory.** GitHub's issues endpoint returns pull requests
  as issues — they share one number space. Verified on this repository: `repos/{o}/{r}/issues/1`
  returns pull request #1, complete with a `pull_request` object and a `merged_at`. Without the
  filter, every pull request in the milestone becomes an item and gets an implementer dispatched
  against it.
- **`state=all`.** Closed issues must be listed. A closed-and-merged blocker is what releases the
  next wave; filtered out, it looks like it never existed and its dependent never unblocks.
- **`--paginate`.** The contract requires the item set complete or nothing. `per_page=100` is the
  ceiling; a milestone with more than 100 issues silently truncates without it.

**`kind` comes from `.type.name`** — GitHub's org-level issue types (`Task`, `Bug`, `Feature` on
this organisation). It is structured data or it is nothing: when no type is set, `.type` is `null`
and `kind` is absent. Never infer it from a label, a title prefix or the body.

The branch prefix derives from `kind`:

```
branch_prefix(kind) → "fix"   when kind is Bug
                    → "feat"  otherwise, including when kind is absent
```

An absent `kind` takes `feat` by default. It is never guessed from the title.

**Failure.** A milestone number the repository does not know produces `422 Validation Failed` with
`{"field":"milestone","code":"invalid"}`, not an empty list. Treat it as a stop, not as an empty
milestone.

## 3. `read_blockers` — native dependencies only

```bash
gh api "repos/$OWNER/$REPO/issues/$NUMBER/dependencies/blocked_by"
gh api "repos/$OWNER/$REPO/issues/$NUMBER/dependencies/blocking"   # the inverse, for reporting
```

`blocked_by` is the read the wave computation consumes: every entry is an item that must be complete
before this one may start.

**Only these endpoints are a dependency.** Inferring a blocking relation from anything else is
forbidden, without exception:

- **Never from issue body text.** "Blocked by #42", "depends on the schema work", "do this after
  #17" — prose, not a dependency.
- **Never from a task list.** A `- [ ] #42` checkbox in a body renders as a tracked sub-item on
  GitHub. It is not a dependency and must not be read as one.
- **Never from a label.** No `blocked` label, no `wave-2` label, no naming convention.
- **Never from a cross-reference or a mention.** A timeline cross-reference records that someone
  linked two issues, nothing more.

Every one of those is a convention that a human eventually edits, and the graph then rots without
any error. The dependency endpoints are the only explicit record.

**An empty array is not proof of no blockers.** Verified on this repository: `dependencies/blocked_by`
on number `1` returns `[]` — and number 1 here is a pull request, not an issue at all. The endpoint
answers `[]` for things that are not issues and for issues that do not exist. Only trust an empty
result for an item that came out of `list_items`.

**Cross-repository blockers.** Each entry carries its own `repository_url`. When that is not this
repository, the entry is an **external blocker**: report it by `owner/repo#number`, read its
completion, and never dispatch it. The orchestrator only drives what it owns.

## 4. `read_completion` — closed **and** merged

```bash
# half one: the issue's own state
gh api "repos/$OWNER/$REPO/issues/$NUMBER" --jq '.state'

# half two: the pull requests that close it, and whether one merged into the default branch
gh api graphql -f query='
  query($o:String!,$r:String!,$n:Int!){
    repository(owner:$o, name:$r){
      issue(number:$n){
        state
        closedByPullRequestsReferences(first:20, includeClosedPrs:true){
          nodes{ number merged baseRefName }
        }
      }
    }
  }' -f o="$OWNER" -f r="$REPO" -F n="$NUMBER"
```

```
complete(item) = item.state == "closed"
              AND ∃ pr ∈ closedByPullRequestsReferences :
                    pr.merged == true AND pr.baseRefName == <default branch>
```

**Both halves are required.** A closed issue on its own is a state someone set by hand: closed as
not-planned, closed by mistake, closed because a comment said it was done. The contract requires
completion to be conjoined with a fact nobody sets by hand, and a merged pull request is that fact.
This is the same merge-gated rule the Jira path expresses through its own workflow (AD-006): an
issue closed with no merged pull request is **not complete**, and its dependents stay blocked.

`baseRefName` is compared against the repository's actual default branch, read once at preflight —
never hardcoded. A pull request merged into a long-lived feature branch has not landed.

**GraphQL and REST disagree about what an issue is, and GraphQL is the stricter one.** Verified
here: `repository.issue(number: 1)` returns `NOT_FOUND` for the same number 1 that REST happily
returns as a pull request. That strictness is useful — it is a second guard against a pull request
being treated as an item — but it means a `NOT_FOUND` from this query is only a real error for a
number that came out of `list_items`.

## `mark_in_progress` is absent

**Declared absent. Not implemented, not emulated.**

GitHub issues have two states, `open` and `closed`. There is no third state meaning "someone is
working on this". The nearest equivalent is a status field on a Projects v2 board, which this
tracker deliberately does not depend on: the board is a human view (a `project` scope concern), the
graph is not, and making wave computation depend on a Projects v2 field would put the whole
orchestration behind a scope that the contract's four reads do not need.

The rejected alternative was a label — `in-progress`, applied at dispatch and removed at merge.
Rejected under AD-015: it would make a label convention and a real workflow transition look like the
same capability, and the difference would surface only during a live run. Faking a capability is
worse than not having one.

**Consequence, and it is the whole point:** nothing changes. The orchestrator behaves identically on
this tracker as on one that implements the write. Progress is visible through the dispatched
worktree and the pull request that follows, not through the board.

## Permissions

| Read | Scope | Granted by |
| --- | --- | --- |
| Milestones, issues, issue dependencies | `repo` | `gh auth refresh -s repo` |
| Projects v2 board (not used by any contract read) | `project` | `gh auth refresh -s project` |

Check the token's real scopes from the response header rather than from memory:

```bash
gh api -i user 2>&1 | grep -i '^x-oauth-scopes'
```

**A missing scope stops the tracker.** GitHub answers an unscoped request with `403` or `404`, and
`404` is indistinguishable from "this does not exist" — which for `read_blockers` reads as "nothing
blocks this" and dispatches the entire milestone in one wave. So:

- Never return empty on a `403` or a `404` that could be a permission failure.
- Stop, name the missing scope, and print the exact `gh auth refresh -s <scope>` command that grants
  it.
- The `project` scope is never required. Every contract read works without it; only the board needs
  it.

## Statelessness

The graph is re-read on every wave computation and **never persisted between waves**. No cached
milestone list, no cached issue set, no cached dependency map, nothing written to disk and nothing
carried across a Phase 5 re-entry.

This is a contract-level rule and it matters more here than the cost of re-reading suggests: waves
release on merges, merges happen while the orchestrator is running, and a graph cached before a
merge reports a blocker as open forever.

## Verified against this repository

Every command above was executed once against `melhorenvio/shopify-envios` on 2026-08-20, read-only.
The repository held **0 milestones, 0 issues and one merged pull request** at the time, so the reads
that need a graph returned empty — recorded here as they actually came back, not as they would look
against a seeded repository.

| Command | Real output |
| --- | --- |
| `gh repo view melhorenvio/shopify-envios --json defaultBranchRef,name,owner` | `{"defaultBranchRef":{"name":"main"},"name":"shopify-envios","owner":{...,"login":"melhorenvio"}}` |
| `gh api "repos/.../milestones?state=all&per_page=100"` | `[]` |
| `gh api "repos/.../milestones?state=all&per_page=100" --jq '.[] \| select(.title == "Schema adoption") \| .number'` | empty, exit 0 — the shape a title that matches nothing produces |
| `gh api "repos/.../milestones/1"` | `{"message":"Not Found",...,"status":"404"}`, exit 1 |
| `gh api "repos/.../issues?milestone=1&state=all&per_page=100"` | `{"message":"Validation Failed","errors":[{"value":"1","resource":"Issue","field":"milestone","code":"invalid"}],"status":"422"}` — an unknown milestone is a 422, never an empty list |
| `gh api "repos/.../issues?state=all&per_page=100"` | one element: pull request #1, carrying a `pull_request` object |
| the same, `--jq '.[] \| select(.pull_request == null) \| {number,title,state,kind:.type.name}'` | empty — the filter removed the pull request, which is the whole reason it is there |
| `gh api "repos/.../issues/1"` | pull request #1: `{"number":1,"title":"feat: fundação da reescrita em Laravel...","state":"closed","type":null,"pull_request":{...,"merged_at":"2026-08-20T20:07:50Z"}}` |
| `gh api "repos/.../issues/1/dependencies/blocked_by"` | `[]` — for a number that is a pull request, not an issue |
| `gh api "repos/.../issues/1/dependencies/blocking"` | `[]` |
| `gh api "repos/.../pulls/1" --jq '{number,merged,merged_at,base:.base.ref}'` | `{"base":"main","merged":true,"merged_at":"2026-08-20T20:07:50Z","number":1}` — the second half of the completion check, against a real merge |
| `gh api graphql` … `repository.issue(number:1)` | `{"data":{"repository":{"issue":null}},"errors":[{"type":"NOT_FOUND",...,"message":"Could not resolve to an Issue with the number of 1."}]}` |
| `gh api -i user \| grep -i '^x-oauth-scopes'` | `X-Oauth-Scopes: gist, project, read:org, repo, workflow` |

Two of those results are the reason rules above exist rather than assertions of taste: an issues read
that hands back a pull request, and a `blocked_by` read that answers `[]` for something that is not
an issue.
