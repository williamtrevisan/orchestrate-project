---
description: Configure orchestrate-project for this repository — pick a tracker, confirm the gate, and write .orchestrate-project.json after verifying every prerequisite is actually reachable.
argument-hint: "[--tracker <name>] [--force]"
---

# Configure orchestrate-project for this repository

Discover what is true, ask only what the environment has not already settled, then write the answer down.

## The contract you are working inside

`${CLAUDE_PLUGIN_ROOT}/scripts/init.py` is **non-interactive by design**. It never prompts and never reads stdin, because it runs through a shell the operator cannot type into — a prompt there would hang the session with its own text invisible.

**You own every question. The script owns every fact and every write.** Do not ask the operator something the script already answered, and do not write the configuration file yourself.

## 1. Discover, before asking anything

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/init.py" --root . probe -o json
```

Read the report. It carries the shipped tracker set, each tracker's probe verdict with the exact command and stderr, the **runner readiness chain**, candidate gate commands with the manifest each came from, candidate conventions documents, and whether a configuration already exists.

### The runner readiness chain

`runner.stages` is an ordered chain, because each stage gates the next. `runner.ready` is true only when all of them pass; `runner.blocking_stage` names the first that does not.

| Stage | Passes when | Recovery |
| --- | --- | --- |
| `binary` | `compozy` resolves on PATH | The install command, or the `export PATH` line when the binary exists but is unreachable |
| `version` | `compozy version` returns a readable token | Present-but-unreadable is unverified, not usable |
| `bootstrap` | `~/.compozy/config.toml` exists | `compozy install --provider claude -o json` |
| `daemon` | `compozy status` reports the daemon running | `compozy daemon start` |
| `doctor` | `compozy doctor` runs | Whatever Compozy itself suggests |

**Act on `blocking_stage` only.** The stages after it are consequences, not separate problems, and the chain stops there rather than reporting a cascade.

**Prefer the `suggested_command` in the report over anything you know.** Compozy names its own recovery command in its JSON errors; a command written here would drift from the runtime it repairs.

**A tracker the operator names on the command line still gets probed.** An unverified choice is the failure this whole step exists to prevent.

## 2. Ask only what is left

Each question below is skipped when the report or an argument already settles it. Ask them in one batch where they are independent; never ask more than you need.

| Question | Offer | Skip when |
| --- | --- | --- |
| Which tracker? | Every shipped tracker, each labelled with its probe verdict **and its transport** | `--tracker` was given, or exactly one tracker probes clean and the rest are absent |
| The tracker's connection settings | The keys named in `missing_config`, with placeholder shapes | `tracker_config` already carries them, or the tracker needs none |
| Which gate command, and from where? | Each detected candidate with the manifest it came from and its working directory, plus "let me type it" | Exactly one candidate exists and the operator confirms it |
| Which conventions document? | Each detected candidate, plus **"none — derive the Definition of Done from the item alone"** | No candidate exists, and the operator is told so |
| The runner is not ready — run the next step? | The command from `runner.blocking_stage`, and "not now" | `runner.ready` is true |

### Transports differ, and so does what "reachable" means

| Transport | Reachability | Configured by |
| --- | --- | --- |
| `cli` | The script runs the command and reads its exit code | Nothing — `github`'s connection is implied by the checkout |
| `mcp` | **You verify it, by calling the tool.** The script cannot — a shell has no access to the session's MCP servers — so it hands you the tool name in `verify_tool` | `tracker_config.<tracker>.*`, discoverable via `discover_tool` |

**No tracker takes a credential.** `.orchestrate-project.json` is committed, so a transport that
needed an API key would put a secret's location in version control. GitHub reads ambient CLI auth;
both MCP servers authenticate in the client.

### Verifying and discovering an MCP tracker

An `mcp` probe returns `ok: false` with `verify_in_session: true`. **That is not a failure — it is
the script declining to guess.** Finish the job yourself:

1. **Call the probe's `verify_tool`.** For Jira that is
   `mcp__atlassian__atlassianUserInfo`, a read-only identity call. It returning an active account
   *is* the reachability check. If the tool is not available in this session, the MCP server is not
   connected — say so and stop, rather than writing a configuration that claims a working tracker.
2. **Call the probe's `discover_tool` to fill the configuration.** For Jira,
   `mcp__atlassian__getAccessibleAtlassianResources` returns the accessible sites with their cloud
   ids. Offer those as the options rather than asking the operator to paste a UUID — they have the
   answer in front of them and typing it is where the typo goes.
   **Dedupe by cloud id and select on scope**: that call returns one entry per scope set, so a site
   appears twice and the first entry may be a grant that cannot read the tracker at all.
3. Pass what you found to `write --tracker-config`.

**Never mark an MCP tracker verified without calling its tool.** The whole reason the script defers
is that a guess and a check are indistinguishable in the output.

**Never put a credential in `tracker_config`.** It names *where* a secret lives — an environment
variable — and the configuration file is committed.

**Show a failing option; never hide it.** A tracker whose credential is broken must appear with its failure attached. Hiding it makes a broken credential look like an unsupported tracker, and the operator then debugs the wrong thing.

**Never install anything and never write anything without an explicit answer.** If the operator declines, report what would have been written and stop.

## 3. Write

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/init.py" --root . write \
  --tracker <chosen> \
  --gate-command "<chosen>" \
  [--gate-working-dir <dir>] \
  [--bootstrap-marker <path>] \
  [--constitution-path <path>] \
  [--pin <compozy-version>] \
  [--force]
```

`--gate-command` is required. The rest are optional and are recorded as `null` when absent, so a phase reads a decision rather than a gap.

## 4. Report what happened

| Exit | Meaning | What to say |
| --- | --- | --- |
| 0 | Written | Print the configuration and the plugin version |
| 1 | A probe failed | Name the failing command and its stderr. Nothing was written |
| 2 | Usage error | The argument that was wrong |
| 3 | Configuration exists | Show the current value and offer `--force` |
| 4 | No resolved tracker or gate command | Name the missing key |

**A non-zero exit is never worked around.** Do not write the file by hand, and do not retry with a value the operator did not choose.

## Boundaries

- **Never invent a gate command.** If detection found nothing, ask. A guessed build tool sends every dispatched implementer to run the wrong thing.
- **Never carry a value from another repository.** Absent is a legitimate answer and is recorded as `null`.
- **Never write a credential** into the configuration. Trackers are reached through ambient CLI auth.
- **Never claim a working runner.** If Compozy is absent, say so and let the operator decide.
