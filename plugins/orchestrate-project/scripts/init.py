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
import shutil
import subprocess
import sys

CONFIG_NAME = ".orchestrate-project.json"
RUNNER = "compozy"

#: The plugin root - this script lives in <plugin>/scripts/.
PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Where the shipped tracker documents live.
TRACKERS_DIR = os.path.join(
    PLUGIN_ROOT, "skills", "orchestrate-project", "references", "trackers"
)

#: The authentication probe each tracker declares. Read-only, every one of them.
TRACKER_PROBES = {
    "github": ["gh", "auth", "status"],
    "jira": ["acli", "jira", "auth", "status"],
    "linear": ["linear", "whoami"],
}

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
CONSTITUTION_CANDIDATES = [
    "docs/constitution.md",
    "docs/conventions.md",
    "CONVENTIONS.md",
    "CONTRIBUTING.md",
    "AGENTS.md",
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


def probe_tracker(name):
    argv = TRACKER_PROBES.get(name)
    if argv is None:
        return {
            "tracker": name,
            "command": None,
            "exit_code": None,
            "stderr": "no probe declared for this tracker",
            "ok": False,
        }
    code, err = _run(argv)
    return {
        "tracker": name,
        "command": " ".join(argv),
        "exit_code": code,
        "stderr": "" if code == 0 else err,
        "ok": code == 0,
    }


def probe_runner(pin=None):
    """Report Compozy's presence and version. Absence is a fact, not an error."""
    if not shutil.which(RUNNER):
        return {
            "present": False,
            "version": None,
            "pin": pin,
            "matches_pin": None,
            "install_command": "curl -fsSL https://compozy.com/install.sh | sh",
        }
    code, out = _run([RUNNER, "--version"])
    version = out.splitlines()[0].strip() if code == 0 and out else None
    return {
        "present": True,
        "version": version,
        "pin": pin,
        "matches_pin": None if (pin is None or version is None) else (pin in version),
        "install_command": None,
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


def build_config(tracker, project, pin=None, today=None):
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
    report = {
        "shipped_trackers": trackers,
        "tracker_probes": [probe_tracker(name) for name in trackers],
        "runner": probe_runner(args.pin),
        "gate_candidates": detect_gate_commands(args.root),
        "constitution_candidates": detect_constitutions(args.root),
        "config_exists": config is not None,
        "config": config,
        "config_error": config_error,
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
        mark = "ok  " if probe["ok"] else "FAIL"
        detail = "" if probe["ok"] else f" - {probe['stderr']}"
        print(f"  {mark}  {probe['tracker']:<8} {probe['command']}{detail}")
    runner = report["runner"]
    if runner["present"]:
        print(f"  ok    {RUNNER}   {runner['version']}")
    else:
        print(f"  WARN  {RUNNER}   not installed - {runner['install_command']}")
    gates = report["gate_candidates"]
    print(f"  info  gate     {len(gates)} manifest(s) found")
    docs = report["constitution_candidates"]
    print(f"  info  conventions {len(docs) or 'none'} candidate(s)")
    passing = sum(1 for p in report["tracker_probes"] if p["ok"])
    print(f"\ninit: {passing}/{len(report['tracker_probes'])} tracker probe(s) passing")


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

    probe = probe_tracker(args.tracker)
    if not probe["ok"]:
        print(
            f"  FAIL  {probe['tracker']:<8} {probe['command']} - {probe['stderr']}",
            file=sys.stderr,
        )
        print("init: probe failed; nothing written", file=sys.stderr)
        return 1

    config = build_config(args.tracker, project, pin=args.pin, today=args.today)
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
        assert name in TRACKER_PROBES, f"no probe declared for shipped tracker {name}"
    absent = probe_runner("v0.0.0-none")
    assert absent["present"] in (True, False)
    assert detect_gate_commands("/nonexistent-path-for-selftest") == []
    assert detect_constitutions("/nonexistent-path-for-selftest") == []
    assert missing_required({}) == ["gate_command"]
    assert missing_required({"gate_command": "make test"}) == []
    sample = build_config("github", {"gate_command": "x"}, today="2026-01-01")
    assert set(sample["project"]) == set(PROJECT_KEYS)
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
    p.set_defaults(fn=cmd_probe)

    p = sub.add_parser("write", help="Write the repository configuration")
    p.add_argument("--tracker", required=True, choices=shipped_trackers() or None)
    p.add_argument("--gate-command", default=None, help="Required: the project's gate")
    p.add_argument("--gate-working-dir", default=None)
    p.add_argument("--bootstrap-marker", default=None)
    p.add_argument("--constitution-path", default=None)
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
