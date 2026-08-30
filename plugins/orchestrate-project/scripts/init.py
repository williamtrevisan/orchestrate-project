#!/usr/bin/env python3
"""
init.py - deterministic discovery and configuration for orchestrate-project.

Answers what is true about a repository so the /orchestrate-init command can ask
the operator only what the environment has not already settled, then writes the
answer down. Pure standard library, zero dependencies.

NON-INTERACTIVE BY CONTRACT. Every input is an argument. This script never reads
stdin, never prompts and never waits: it runs through an agent's shell, which is
not a terminal the operator can type into, so a prompt here would hang a session
with its own text invisible. The questions belong to the command; the facts
belong here.

Usage:
  init.py probe    [--root DIR] [-o json|human]
  init.py write    --tracker NAME [--root DIR] [--force] [-o json|human]
  init.py status   [--root DIR]
  init.py selftest

Exit codes:
  0  success
  1  a probe failed - nothing was written
  2  usage error
  3  configuration exists and --force was not given
  4  write was asked for without a resolved tracker or gate command
"""

import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys

CONFIG_NAME = ".orchestrate-project.json"
RUNNER = "compozy"
INSTALL_COMMAND = "curl -fsSL https://compozy.com/install.sh | sh"

#: Read from `compozy --help` on v0.3.0-beta.21, not assumed. `--version` is not
#: a flag this CLI has; `version` is a subcommand. Guessing the conventional
#: form produced a probe that reported the runner present with no version.
VERSION_COMMAND = [RUNNER, "version"]

#: Read from `compozy daemon --help`: its subcommands are bootstrap, start and
#: stop - there is no `daemon status`. Consolidated runtime state comes from the
#: top-level `compozy status`, whose daemon block carries the running flag.
DAEMON_STATUS_COMMAND = [RUNNER, "status", "-o", "json"]

#: The plugin root - this script lives in <plugin>/scripts/.
PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Where the shipped tracker documents live.
TRACKERS_DIR = os.path.join(
    PLUGIN_ROOT, "skills", "orchestrate-project", "references", "trackers"
)

#: How each tracker is reached, and what it needs, is declared by the tracker's
#: OWN document in a ```tracker-config fenced block - not here.
#:
#: It lived here once, and drifted: Jira's document quoted a project key in every
#: JQL query while this file never asked for one, so init wrote a configuration
#: the tracker could not use. Two sources for one fact diverge on the first
#: change to either.
#:
#: Keeping it in the document also restores the rule the contract claims: adding
#: a tracker is one new file and no change to any phase - including this script.
#:
#:   cli    a local executable this script runs and reads an exit code from
#:   mcp    an MCP server the *session* holds. A script cannot see the session's
#:          tool list, so it checks the server is configured and hands the
#:          command the tool to call.
TRACKER_CONFIG_BLOCK = re.compile(
    r"^```tracker-config\s*\n(.*?)\n```", re.MULTILINE | re.DOTALL
)


def read_tracker_declaration(name):
    """The transport a tracker document declares for itself.

    Returns None when the document ships no block - which is a defect in that
    document, reported as such rather than silently defaulted.
    """
    path = os.path.join(TRACKERS_DIR, f"{name}.md")
    try:
        with open(path, encoding="utf-8") as handle:
            found = TRACKER_CONFIG_BLOCK.search(handle.read())
    except OSError:
        return None
    if not found:
        return None
    try:
        block = json.loads(found.group(1))
    except ValueError:
        return None
    block.setdefault("requires", {})
    block["needs_config"] = sorted(block["requires"])
    block["kind"] = block.get("transport")
    return block


def tracker_transports():
    """Every shipped tracker's declaration, keyed by name."""
    declared = {}
    for name in shipped_trackers():
        block = read_tracker_declaration(name)
        if block:
            declared[name] = block
    return declared


#: Manifests that can name a project's gate, in the order they are looked for.
#: The value is the key or target a candidate command is read from.
GATE_MANIFESTS = [
    ("composer.json", "scripts"),
    ("package.json", "scripts"),
    ("pyproject.toml", None),
    ("Cargo.toml", None),
    ("go.mod", None),
    ("Makefile", None),
]

#: Filenames that commonly hold a project's conventions, most specific first.
#:
#: CLAUDE.md and AGENTS.md are here because that is where a project's rules
#: actually live in practice, not because they are conventions documents by
#: design. Probing a real repository found its whole rule set - gate command,
#: dependency semantics, tier labels - in CLAUDE.md while this list looked only
#: for tidier names and reported "none".
CONSTITUTION_CANDIDATES = [
    "docs/constitution.md",
    "docs/conventions.md",
    "CONVENTIONS.md",
    "CLAUDE.md",
    "AGENTS.md",
    "CONTRIBUTING.md",
]


def shipped_trackers():
    """The trackers this plugin ships, derived from the documents themselves.

    The shipped set IS the offered set: dropping a document under trackers/
    adds a choice with no change to this file.
    """
    if not os.path.isdir(TRACKERS_DIR):
        return []
    return sorted(
        name[:-3] for name in os.listdir(TRACKERS_DIR) if name.endswith(".md")
    )


def _run(argv):
    """Run a probe, returning (exit_code, stderr). Never raises."""
    if not shutil.which(argv[0]):
        return 127, f"{argv[0]}: not found on PATH"
    try:
        done = subprocess.run(
            argv, capture_output=True, text=True, timeout=30, check=False
        )
        return done.returncode, (done.stderr or done.stdout).strip()
    except subprocess.TimeoutExpired:
        return 124, f"{' '.join(argv)}: timed out"
    except OSError as err:
        return 126, str(err)


def configured_mcp_servers(root):
    """MCP server ids reachable from this repository, from every place they live.

    Claude Code keeps per-project servers inside ~/.claude.json under
    projects.<path>.mcpServers, which is *not* a file in the repository. Looking
    only at .mcp.json and .claude/settings*.json reports "not configured" for a
    server that is configured - a confident negative, which is worse than no
    answer.
    """
    found = set()
    home = os.path.expanduser("~/.claude.json")
    try:
        with open(home, encoding="utf-8") as handle:
            data = json.load(handle)
        found.update(data.get("mcpServers") or {})
        project = (data.get("projects") or {}).get(os.path.abspath(root)) or {}
        found.update(project.get("mcpServers") or {})
    except (ValueError, OSError):
        pass
    for relative in (".mcp.json", os.path.join(".claude", "settings.json")):
        try:
            with open(os.path.join(root, relative), encoding="utf-8") as handle:
                found.update(json.load(handle).get("mcpServers") or {})
        except (ValueError, OSError):
            continue
    return sorted(found)


def mcp_add_command(transport, scope="project"):
    """The exact command that adds this tracker's server."""
    return (
        f"claude mcp add --transport http {transport['server']} "
        f"{transport['endpoint']} --scope {scope}"
    )


def _missing_tracker_config(name, tracker_config):
    needed = (read_tracker_declaration(name) or {}).get("needs_config", [])
    present = (tracker_config or {}).get(name) or {}
    return [key for key in needed if not present.get(key)]


def probe_tracker(name, tracker_config=None, root="."):
    """Whether this tracker is reachable, answered the way its transport allows.

    `ok` is never optimistic. An MCP tracker returns ok=False with
    `verify_in_session` set, because this script cannot see the session's tool
    list and must not report a guess as a pass.
    """
    transport = read_tracker_declaration(name)
    if transport is None:
        return {
            "tracker": name,
            "transport": None,
            "command": None,
            "exit_code": None,
            "stderr": "no transport declared for this tracker",
            "ok": False,
            "verify_in_session": False,
            "verify_tool": None,
            "discover_tool": None,
            "server_configured": None,
            "asks": {},
        }

    kind = transport["kind"]
    missing = _missing_tracker_config(name, tracker_config)
    base = {
        "tracker": name,
        "transport": kind,
        "missing_config": missing,
        "verify_in_session": False,
        "verify_tool": transport.get("verify_tool"),
        "verify_tool_prefix": transport.get("verify_tool_prefix"),
        "discover_tool": transport.get("discover_tool"),
        "server_configured": None,
        "asks": {},
    }

    server_present = None
    if kind == "mcp":
        server_present = transport["server"] in configured_mcp_servers(root)
        base["server_configured"] = server_present
        if not server_present:
            return {
                **base,
                "command": mcp_add_command(transport),
                "exit_code": None,
                "stderr": (
                    f"MCP server {transport['server']!r} is not configured for "
                    "this repository"
                ),
                "ok": False,
            }

    if missing:
        keys = ", ".join(f"tracker_config.{name}.{k}" for k in missing)
        prefix = "server present; " if server_present else ""
        return {
            **base,
            "command": None,
            "exit_code": None,
            "stderr": f"{prefix}not configured: {keys}",
            "ok": False,
            "asks": {key: transport["requires"][key] for key in missing},
        }

    if kind == "cli":
        argv = transport["command"]
        code, err = _run(argv)
        return {
            **base,
            "command": " ".join(argv),
            "exit_code": code,
            "stderr": "" if code == 0 else err,
            "ok": code == 0,
        }

    if kind == "mcp":
        named = transport.get("verify_tool")
        target = named or f"any {transport['verify_tool_prefix']}* read-only tool"
        return {
            **base,
            "command": target,
            "exit_code": None,
            "stderr": (
                f"configured; call {target} to verify - a shell cannot reach an "
                "MCP server the session holds"
                + ("" if named else " (exact tool not yet captured)")
            ),
            "ok": False,
            "verify_in_session": True,
        }

    raise ValueError(f"unknown transport kind {kind!r} for tracker {name!r}")


def is_prerelease(version):
    """True when a version string carries a prerelease identifier.

    Compozy has shipped only prereleases - 21 of them in under two months - so
    a pin is a moving target rather than a stable contract. Saying so is the
    honest default until a stable release exists.
    """
    token = normalize_version(version)
    return bool(token) and "-" in token


VERSION_TOKEN = re.compile(r"v?(\d+\.\d+\.\d+(?:-[0-9A-Za-z.]+)?)")


def normalize_version(text):
    """The bare version token from a string, without a leading v.

    `compozy version` prints "compozy 0.3.0-beta.21" while a release tag reads
    "v0.3.0-beta.21". Comparing those as substrings reports drift between a
    build and itself, and a false drift warning trains the operator to ignore
    a real one.
    """
    if not text:
        return None
    found = VERSION_TOKEN.search(text)
    return found.group(1) if found else None


def compare_pin(version, pin):
    """How an installed version relates to the pin the flags were captured at.

    Returns one of: 'unknown' (either side unreadable), 'match', or 'drift'.
    Drift is never resolved silently - it is a re-verification trigger, because
    the documented flags were read from one specific build.
    """
    installed = normalize_version(version)
    pinned = normalize_version(pin)
    if not installed or not pinned:
        return "unknown"
    return "match" if installed == pinned else "drift"


def _suggested_command(output):
    """The recovery command Compozy itself names, when it names one.

    Its JSON errors carry diagnostic.suggested_command. Reading that beats
    hardcoding a fix here, which would drift from the runtime it repairs.
    """
    try:
        payload = json.loads(output)
    except (ValueError, TypeError):
        return None
    diagnostic = payload.get("diagnostic") or {}
    return diagnostic.get("suggested_command") or payload.get("suggested_command")


def _stage(name, ok, detail, command=None):
    return {"stage": name, "ok": ok, "detail": detail, "suggested_command": command}


def probe_runner_stages(pin=None, deep=False):
    """Every prerequisite between a bare machine and a dispatchable runtime.

    Reported as an ordered chain because each stage gates the next: a daemon
    cannot start before bootstrap, and doctor cannot run before the daemon. The
    first failure is the only one worth acting on.

    `doctor` runs only under deep=True. It takes seconds and reports on the
    whole installation, most of which this skill never touches, so paying for it
    on every probe would make the common path slow for information the operator
    did not ask for.
    """
    stages = []

    binary = shutil.which(RUNNER)
    stages.append(
        _stage(
            "binary",
            bool(binary),
            binary or f"{RUNNER} not on PATH",
            None if binary else INSTALL_COMMAND,
        )
    )
    if not binary:
        fallback = os.path.expanduser(f"~/.local/bin/{RUNNER}")
        if os.path.isfile(fallback):
            stages[-1]["detail"] = (
                f"{fallback} exists but is not on PATH"
            )
            stages[-1]["suggested_command"] = 'export PATH="$HOME/.local/bin:$PATH"'
        return stages

    code, out = _run(VERSION_COMMAND)
    version = out.splitlines()[0].strip() if code == 0 and out else None
    stages.append(
        _stage("version", version is not None, version or "version unreadable")
    )

    config = os.path.expanduser("~/.compozy/config.toml")
    bootstrapped = os.path.isfile(config)
    stages.append(
        _stage(
            "bootstrap",
            bootstrapped,
            config if bootstrapped else "~/.compozy/config.toml absent",
            None if bootstrapped else f"{RUNNER} install --provider claude -o json",
        )
    )
    if not bootstrapped:
        return stages

    code, out = _run(DAEMON_STATUS_COMMAND)
    running = code == 0 and '"status": "running"' in out
    stages.append(
        _stage(
            "daemon",
            running,
            "running" if running else "not reachable",
            None if running else (_suggested_command(out) or f"{RUNNER} daemon start"),
        )
    )
    if not running or not deep:
        return stages

    code, out = _run([RUNNER, "doctor", "-o", "json"])
    stages.append(
        _stage("doctor", code == 0, "ran" if code == 0 else "unavailable",
               _suggested_command(out))
    )
    return stages


def probe_runner(pin=None, deep=False):
    """Report Compozy's presence and version. Absence is a fact, not an error."""
    stages = probe_runner_stages(pin, deep=deep)
    blocking = next((st for st in stages if not st["ok"]), None)
    if not shutil.which(RUNNER):
        return {
            "present": False,
            "version": None,
            "pin": pin,
            "pin_state": "unknown",
            "prerelease": is_prerelease(pin),
            "install_command": INSTALL_COMMAND,
            "stages": stages,
            "ready": False,
            "blocking_stage": blocking["stage"] if blocking else None,
            "advice": (
                f"{RUNNER} is not installed. Dispatch cannot run until it is; "
                "install it yourself rather than having this write a config that "
                "claims a working runner."
            ),
        }
    code, out = _run(VERSION_COMMAND)
    version = out.splitlines()[0].strip() if code == 0 and out else None
    state = compare_pin(version, pin)
    advice = None
    if version is None:
        advice = (
            f"{RUNNER} is on PATH but `{' '.join(VERSION_COMMAND)}` returned nothing "
            "readable. Treat the runtime as unverified rather than usable."
        )
    elif state == "drift":
        advice = (
            f"installed {version} but references/runner.md was captured at {pin}. "
            "Re-capture the command table from --help before dispatching; a flag "
            "may have moved."
        )
    elif is_prerelease(version):
        advice = (
            f"{version} is a prerelease. The runtime is unstable: a version bump "
            "is a re-verification trigger, not an automatic upgrade."
        )
    return {
        "present": True,
        "version": version,
        "pin": pin,
        "pin_state": state,
        "prerelease": is_prerelease(version),
        "install_command": None,
        "stages": stages,
        "ready": blocking is None,
        "blocking_stage": blocking["stage"] if blocking else None,
        "advice": advice,
    }


def _read_manifest(path, key):
    if not key:
        return []
    try:
        with open(path, encoding="utf-8") as handle:
            scripts = json.load(handle).get(key) or {}
    except (ValueError, OSError):
        return []
    return [name for name in scripts if "test" in name or "check" in name]


def _search_dirs(root):
    """The repository root, then each immediate subdirectory.

    A monorepo keeps its manifest one level down - this repository's own gate
    lives in backend/, not at the root - so a root-only search reports "no gate
    found" for exactly the project the plugin was written in. The directory a
    manifest is found in becomes that candidate's working directory.
    """
    yield "", root
    try:
        entries = sorted(os.listdir(root))
    except OSError:
        return
    for name in entries:
        if name.startswith(".") or name in ("node_modules", "vendor"):
            continue
        path = os.path.join(root, name)
        if os.path.isdir(path):
            yield name, path


def detect_gate_commands(root):
    """Candidate gate commands, each carrying the file it was read from.

    Evidence, never a default. An empty result is reported as empty so the
    command asks rather than guessing a build tool the project does not use.
    """
    found = []
    for working_dir, directory in _search_dirs(root):
        for filename, key in GATE_MANIFESTS:
            path = os.path.join(directory, filename)
            if not os.path.isfile(path):
                continue
            found.append(
                {
                    "source": os.path.join(working_dir, filename)
                    if working_dir
                    else filename,
                    "working_dir": working_dir,
                    "candidates": _read_manifest(path, key),
                }
            )
    return found


def detect_constitutions(root):
    """Conventions documents that actually exist in this repository."""
    return [c for c in CONSTITUTION_CANDIDATES if os.path.isfile(os.path.join(root, c))]


#: Keys of the project block, and whether a phase can proceed without them.
PROJECT_KEYS = {
    "gate_command": "required",
    "gate_working_dir": "optional",
    "bootstrap_marker": "optional",
    "constitution_path": "optional",
}


def plugin_version():
    """The version this plugin reports, read from its own manifest."""
    manifest = os.path.join(PLUGIN_ROOT, ".claude-plugin", "plugin.json")
    try:
        with open(manifest, encoding="utf-8") as handle:
            return json.load(handle).get("version")
    except (ValueError, OSError):
        return None


def build_config(tracker, project, pin=None, today=None, tracker_config=None):
    """The configuration document, with every project key stated explicitly.

    An optional key the operator did not supply is written as null rather than
    omitted. Absence is then a recorded decision a phase can read, instead of a
    gap another project's value could quietly fill (OPP-74).
    """
    stamp = today or datetime.date.today().isoformat()
    return {
        "tracker": tracker,
        "runner": RUNNER,
        "compozy_pin": pin,
        "plugin_version": plugin_version(),
        "initialized_at": stamp,
        "project": {key: project.get(key) for key in sorted(PROJECT_KEYS)},
        "tracker_config": tracker_config or {},
    }


def missing_required(project):
    """Required project keys the caller did not supply, by name."""
    return sorted(
        key
        for key, need in PROJECT_KEYS.items()
        if need == "required" and not project.get(key)
    )


def read_config(root):
    path = os.path.join(root, CONFIG_NAME)
    if not os.path.isfile(path):
        return None, None
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle), None
    except ValueError as err:
        return None, f"{CONFIG_NAME} is not valid JSON: {err}"


def cmd_probe(args):
    trackers = shipped_trackers()
    config, config_error = read_config(args.root)
    existing_tracker_config = (config or {}).get("tracker_config") or {}
    report = {
        "shipped_trackers": trackers,
        "tracker_probes": [
            probe_tracker(name, existing_tracker_config, args.root)
            for name in trackers
        ],
        "runner": probe_runner(args.pin, deep=args.deep),
        "gate_candidates": detect_gate_commands(args.root),
        "constitution_candidates": detect_constitutions(args.root),
        "config_exists": config is not None,
        "config": config,
        "config_error": config_error,
        "plugin_version": plugin_version(),
    }
    if args.output == "json":
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        _print_human(report)
    return 0 if any(p["ok"] for p in report["tracker_probes"]) else 1


def _print_human(report):
    if report["config_error"]:
        print(f"  FAIL  {report['config_error']}")
    for probe in report["tracker_probes"]:
        if probe["ok"]:
            mark = "ok  "
        elif probe["verify_in_session"]:
            mark = "?   "
        else:
            mark = "FAIL"
        detail = "" if probe["ok"] else f" - {probe['stderr']}"
        kind = probe["transport"] or "?"
        print(f"  {mark}  {probe['tracker']:<8} [{kind}] {probe['command']}{detail}")
    runner = report["runner"]
    for stage in runner.get("stages", []):
        mark = "ok  " if stage["ok"] else "FAIL"
        print(f"  {mark}  {stage['stage']:<10} {stage['detail']}")
        if not stage["ok"] and stage["suggested_command"]:
            print(f"        next: {stage['suggested_command']}")
    if runner["pin_state"] == "drift":
        print(f"  WARN  pin        {runner['version']} vs pinned {runner['pin']}")
    if runner["advice"]:
        print(f"        {runner['advice']}")
    gates = report["gate_candidates"]
    print(f"  info  gate     {len(gates)} manifest(s) found")
    docs = report["constitution_candidates"]
    print(f"  info  conventions {len(docs) or 'none'} candidate(s)")
    passing = sum(1 for p in report["tracker_probes"] if p["ok"])
    runner_state = (
        "runner ready" if runner["ready"] else f"blocked at {runner['blocking_stage']}"
    )
    print(
        f"\ninit: {passing}/{len(report['tracker_probes'])} tracker probe(s) passing, "
        f"{runner_state} (plugin {report['plugin_version']})"
    )


def cmd_write(args):
    trackers = shipped_trackers()
    if args.tracker not in trackers:
        print(
            f"init: unknown tracker {args.tracker!r}; shipped: {', '.join(trackers)}",
            file=sys.stderr,
        )
        return 4

    project = {
        "gate_command": args.gate_command,
        "gate_working_dir": args.gate_working_dir,
        "bootstrap_marker": args.bootstrap_marker,
        "constitution_path": args.constitution_path,
    }
    absent = missing_required(project)
    if absent:
        print(
            f"init: cannot write without {', '.join(absent)} - "
            "no value is carried over from another project",
            file=sys.stderr,
        )
        return 4

    existing, error = read_config(args.root)
    if error:
        print(f"  FAIL  {error}", file=sys.stderr)
        return 1
    if existing is not None and not args.force:
        print(f"init: {CONFIG_NAME} already exists; pass --force to replace it")
        print(json.dumps(existing, indent=2, ensure_ascii=False))
        return 3

    tracker_config = {}
    if args.tracker_config:
        try:
            tracker_config = json.loads(args.tracker_config)
        except ValueError as err:
            print(f"init: --tracker-config is not valid JSON: {err}", file=sys.stderr)
            return 2
        if not isinstance(tracker_config, dict):
            print("init: --tracker-config must be a JSON object", file=sys.stderr)
            return 2

    probe = probe_tracker(args.tracker, tracker_config, args.root)
    if not probe["ok"] and not probe["verify_in_session"]:
        print(
            f"  FAIL  {probe['tracker']:<8} {probe['command']} - {probe['stderr']}",
            file=sys.stderr,
        )
        print("init: probe failed; nothing written", file=sys.stderr)
        return 1
    if probe["verify_in_session"]:
        print(
            f"  ?     {probe['tracker']:<8} configured; verify with "
            f"{probe['verify_tool']}",
            file=sys.stderr,
        )

    config = build_config(
        args.tracker, project, pin=args.pin, today=args.today,
        tracker_config=tracker_config,
    )
    path = os.path.join(args.root, CONFIG_NAME)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(config, handle, indent=2, ensure_ascii=False)
        handle.write("\n")

    print(json.dumps(config, indent=2, ensure_ascii=False))
    if args.output != "json":
        print(f"\ninit: wrote {CONFIG_NAME} (plugin {config['plugin_version']})")
    return 0


def cmd_status(args):
    config, error = read_config(args.root)
    if error:
        print(f"  FAIL  {error}", file=sys.stderr)
        return 1
    if config is None:
        print(f"init: no {CONFIG_NAME} in {args.root}")
        return 0
    print(json.dumps(config, indent=2, ensure_ascii=False))
    return 0


def _selftest():
    assert shipped_trackers() == sorted(shipped_trackers())
    for name in shipped_trackers():
        block = read_tracker_declaration(name)
        assert block, f"{name}.md ships no tracker-config block"
        assert block["kind"] in ("cli", "mcp"), f"{name}: unknown transport"
        for key, why in block["requires"].items():
            assert why.strip(), f"{name}.{key} is declared with no explanation"
    assert "project_key" in _missing_tracker_config("jira", {})
    for name, block in tracker_transports().items():
        if block["kind"] == "mcp":
            assert block.get("verify_tool") or block.get(
                "verify_tool_prefix"
            ), f"{name} names neither a verify tool nor a prefix"
    assert _missing_tracker_config("github", {}) == []
    assert isinstance(configured_mcp_servers("/nonexistent-selftest"), list)
    assert "claude mcp add" in mcp_add_command(tracker_transports()["linear"])
    absent = probe_runner("v0.0.0-none")
    assert absent["present"] in (True, False)
    assert compare_pin(None, "v1") == "unknown"
    assert compare_pin("v1.0.0", None) == "unknown"
    assert compare_pin("compozy v0.3.0-beta.21", "v0.3.0-beta.21") == "match"
    assert compare_pin("compozy 0.3.0-beta.21", "v0.3.0-beta.21") == "match"
    assert compare_pin("compozy v0.3.0-beta.24", "v0.3.0-beta.21") == "drift"
    assert normalize_version("compozy 0.3.0-beta.21") == "0.3.0-beta.21"
    assert normalize_version("no version here") is None
    assert is_prerelease("v0.3.0-beta.21") is True
    assert is_prerelease("v1.0.0") is False
    assert detect_gate_commands("/nonexistent-path-for-selftest") == []
    assert detect_constitutions("/nonexistent-path-for-selftest") == []
    assert missing_required({}) == ["gate_command"]
    assert missing_required({"gate_command": "make test"}) == []
    sample = build_config("github", {"gate_command": "x"}, today="2026-01-01")
    assert set(sample["project"]) == set(PROJECT_KEYS)
    assert sample["tracker_config"] == {}
    assert json.loads(json.dumps(sample)) == sample
    print("selftest_init: ok")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="init.py",
        description="Discovery and configuration for orchestrate-project.",
    )
    parser.add_argument("--root", default=".", help="Repository root (default: .)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("probe", help="Report what is true; write nothing")
    p.add_argument("-o", "--output", default="human", choices=["human", "json"])
    p.add_argument("--pin", default=None, help="Compozy version to compare against")
    p.add_argument(
        "--deep",
        action="store_true",
        help="Also run compozy doctor (seconds, whole-installation scope)",
    )
    p.set_defaults(fn=cmd_probe)

    p = sub.add_parser("write", help="Write the repository configuration")
    p.add_argument("--tracker", required=True, choices=shipped_trackers() or None)
    p.add_argument("--gate-command", default=None, help="Required: the project's gate")
    p.add_argument("--gate-working-dir", default=None)
    p.add_argument("--bootstrap-marker", default=None)
    p.add_argument("--constitution-path", default=None)
    p.add_argument(
        "--tracker-config",
        default=None,
        help="JSON object of per-project tracker connection settings "
             "(site, cloud id, workspace). Never a credential - reference the "
             "environment variable that holds one instead.",
    )
    p.add_argument("--pin", default=None, help="Compozy version this repo targets")
    p.add_argument("--today", default=None, help="Override the stamp (tests)")
    p.add_argument("--force", action="store_true")
    p.add_argument("-o", "--output", default="human", choices=["human", "json"])
    p.set_defaults(fn=cmd_write)

    p = sub.add_parser("status", help="Print the current configuration")
    p.set_defaults(fn=cmd_status)

    p = sub.add_parser("selftest", help="Run stdlib regressions")
    p.set_defaults(fn=lambda args: _selftest())

    args = parser.parse_args(argv)
    args.root = os.path.abspath(args.root)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
