"""Unit tests for init.py's discovery pass.

Derived from spec ACs, not from the implementation:
  OPP-10  the shipped set is the offered set
  OPP-11  each tracker's probe runs and its result is reported
  OPP-15  an unshipped tracker name is rejected by name
  OPP-18  every input is an argument; stdin is never read
  OPP-50  Compozy's presence and version are reported
  OPP-51  absence yields the install command, and installs nothing
  OPP-71  gate and conventions candidates are detected from the project
  OPP-74  detection reports evidence, never a substituted default
"""

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

import paths

sys.path.insert(0, os.path.join(paths.PLUGIN_DIR, "scripts"))
import init  # noqa: E402


@contextlib.contextmanager
def stubbed_runtime(
    version="compozy 0.3.0-beta.21", tracker_ok=True, daemon=True, binary=True
):
    """Replace every external call with a scripted answer.

    Without this the suite shells out to `gh auth status` and a live Compozy
    daemon on roughly a dozen tests, which took 151 seconds and made the result
    depend on network reachability and on whether a daemon happened to be
    running. A structural assertion should not need either. One integration
    test below still exercises the real binary.
    """

    def fake_run(argv):
        if argv[:2] == [init.RUNNER, "version"]:
            return (0, version) if version else (1, "")
        if argv[:2] == [init.RUNNER, "status"]:
            return (0, '{"daemon": {"status": "running"}}') if daemon else (1, "{}")
        if argv[:2] == [init.RUNNER, "doctor"]:
            return 0, "{}"
        return (0, "") if tracker_ok else (1, "not authenticated")

    original_run, original_which = init._run, shutil.which
    original_home = os.path.expanduser
    try:
        init._run = fake_run
        shutil.which = lambda name: f"/usr/bin/{name}" if binary else None
        os.path.expanduser = lambda path: (
            __file__ if path == "~/.compozy/config.toml" else original_home(path)
        )
        yield
    finally:
        init._run, shutil.which = original_run, original_which
        os.path.expanduser = original_home


class ShippedTrackers(unittest.TestCase):
    def test_derives_the_offered_set_from_the_shipped_documents(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("alpha.md", "beta.md"):
                open(os.path.join(tmp, name), "w", encoding="utf-8").close()
            original = init.TRACKERS_DIR
            try:
                init.TRACKERS_DIR = tmp
                self.assertEqual(init.shipped_trackers(), ["alpha", "beta"])
            finally:
                init.TRACKERS_DIR = original

    def test_a_new_document_adds_a_choice_with_no_code_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            open(os.path.join(tmp, "github.md"), "w", encoding="utf-8").close()
            original = init.TRACKERS_DIR
            try:
                init.TRACKERS_DIR = tmp
                self.assertEqual(init.shipped_trackers(), ["github"])
                open(os.path.join(tmp, "asana.md"), "w", encoding="utf-8").close()
                self.assertEqual(init.shipped_trackers(), ["asana", "github"])
            finally:
                init.TRACKERS_DIR = original

    def test_ignores_non_markdown_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            open(os.path.join(tmp, "github.md"), "w", encoding="utf-8").close()
            open(os.path.join(tmp, "notes.txt"), "w", encoding="utf-8").close()
            original = init.TRACKERS_DIR
            try:
                init.TRACKERS_DIR = tmp
                self.assertEqual(init.shipped_trackers(), ["github"])
            finally:
                init.TRACKERS_DIR = original

    def test_trackers_dir_resolves_against_the_real_plugin_layout(self):
        """Regression: TRACKERS_DIR was built from the script's own directory
        rather than the plugin root, so it pointed at scripts/skills/... and
        silently resolved to no trackers at all. Unit tests missed it because
        they all patched TRACKERS_DIR; only a real run surfaced it."""
        self.assertTrue(
            os.path.isdir(init.TRACKERS_DIR),
            f"TRACKERS_DIR does not exist: {init.TRACKERS_DIR}",
        )
        self.assertTrue(init.shipped_trackers(), "no trackers resolved from disk")

    def test_every_shipped_tracker_declares_a_probe(self):
        for name in init.shipped_trackers():
            self.assertIn(name, init.TRACKER_PROBES)


class TrackerProbe(unittest.TestCase):
    def test_reports_the_command_it_ran(self):
        with stubbed_runtime():
            result = init.probe_tracker("github")
        self.assertEqual(result["command"], "gh auth status")

    def test_a_missing_executable_is_a_failure_not_a_crash(self):
        original = dict(init.TRACKER_PROBES)
        try:
            init.TRACKER_PROBES["ghost"] = ["definitely-not-a-real-binary-xyz"]
            result = init.probe_tracker("ghost")
            self.assertFalse(result["ok"])
            self.assertIn("not found", result["stderr"])
        finally:
            init.TRACKER_PROBES.clear()
            init.TRACKER_PROBES.update(original)

    def test_an_undeclared_tracker_reports_the_gap_rather_than_passing(self):
        result = init.probe_tracker("nonexistent")
        self.assertFalse(result["ok"])
        self.assertIsNone(result["command"])


class RunnerProbe(unittest.TestCase):
    def test_absence_yields_an_install_command_and_installs_nothing(self):
        original = shutil.which
        try:
            shutil.which = lambda _name: None
            result = init.probe_runner()
            self.assertFalse(result["present"])
            self.assertIn("compozy.com/install.sh", result["install_command"])
            self.assertIsNone(result["version"])
        finally:
            shutil.which = original

    def test_absence_reports_no_pin_match_rather_than_a_false_one(self):
        original = shutil.which
        try:
            shutil.which = lambda _name: None
            self.assertEqual(
                init.probe_runner("v0.3.0-beta.21")["pin_state"], "unknown"
            )
        finally:
            shutil.which = original


class GateDetection(unittest.TestCase):
    def test_an_empty_repository_yields_no_candidates(self):
        """OPP-74: absence is reported as absence, never resolved to a guess."""
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(init.detect_gate_commands(tmp), [])

    def test_a_node_project_is_detected_from_its_own_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "package.json"), "w", encoding="utf-8") as fh:
                json.dump({"scripts": {"test": "vitest", "build": "tsc"}}, fh)
            found = init.detect_gate_commands(tmp)
            self.assertEqual(len(found), 1)
            self.assertEqual(found[0]["source"], "package.json")
            self.assertIn("test", found[0]["candidates"])
            self.assertNotIn("build", found[0]["candidates"])

    def test_a_go_project_is_detected_without_inventing_a_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            open(os.path.join(tmp, "go.mod"), "w", encoding="utf-8").close()
            found = init.detect_gate_commands(tmp)
            self.assertEqual([f["source"] for f in found], ["go.mod"])
            self.assertEqual(found[0]["candidates"], [])

    def test_a_malformed_manifest_yields_no_candidates_rather_than_raising(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "package.json"), "w", encoding="utf-8") as fh:
                fh.write("{not json")
            self.assertEqual(init.detect_gate_commands(tmp)[0]["candidates"], [])

    def test_a_manifest_one_level_down_is_found(self):
        """Regression: a root-only search reported "no gate found" for this
        very repository, whose gate lives in backend/."""
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "backend"))
            with open(
                os.path.join(tmp, "backend", "composer.json"), "w", encoding="utf-8"
            ) as fh:
                json.dump({"scripts": {"test": "pest"}}, fh)
            found = init.detect_gate_commands(tmp)
            self.assertEqual(len(found), 1)
            self.assertEqual(found[0]["working_dir"], "backend")
            self.assertEqual(found[0]["source"], os.path.join("backend", "composer.json"))
            self.assertIn("test", found[0]["candidates"])

    def test_a_root_manifest_reports_an_empty_working_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            open(os.path.join(tmp, "go.mod"), "w", encoding="utf-8").close()
            self.assertEqual(init.detect_gate_commands(tmp)[0]["working_dir"], "")

    def test_dependency_directories_are_not_searched(self):
        with tempfile.TemporaryDirectory() as tmp:
            for noise in ("node_modules", "vendor", ".git"):
                os.makedirs(os.path.join(tmp, noise))
                open(
                    os.path.join(tmp, noise, "package.json"), "w", encoding="utf-8"
                ).close()
            self.assertEqual(init.detect_gate_commands(tmp), [])

    def test_multiple_manifests_are_all_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            open(os.path.join(tmp, "Makefile"), "w", encoding="utf-8").close()
            open(os.path.join(tmp, "go.mod"), "w", encoding="utf-8").close()
            self.assertEqual(
                sorted(f["source"] for f in init.detect_gate_commands(tmp)),
                ["Makefile", "go.mod"],
            )


class ConstitutionDetection(unittest.TestCase):
    def test_an_empty_repository_yields_no_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(init.detect_constitutions(tmp), [])

    def test_an_existing_document_is_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            open(os.path.join(tmp, "AGENTS.md"), "w", encoding="utf-8").close()
            self.assertEqual(init.detect_constitutions(tmp), ["AGENTS.md"])

    def test_the_most_specific_candidate_is_listed_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "docs"))
            open(
                os.path.join(tmp, "docs", "constitution.md"), "w", encoding="utf-8"
            ).close()
            open(os.path.join(tmp, "AGENTS.md"), "w", encoding="utf-8").close()
            self.assertEqual(
                init.detect_constitutions(tmp), ["docs/constitution.md", "AGENTS.md"]
            )


class ConfigReading(unittest.TestCase):
    def test_a_missing_configuration_is_not_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            config, error = init.read_config(tmp)
            self.assertIsNone(config)
            self.assertIsNone(error)

    def test_malformed_json_reports_the_parse_error(self):
        """Edge case: never fall back to a default tracker."""
        with tempfile.TemporaryDirectory() as tmp:
            with open(
                os.path.join(tmp, init.CONFIG_NAME), "w", encoding="utf-8"
            ) as fh:
                fh.write("{oops")
            config, error = init.read_config(tmp)
            self.assertIsNone(config)
            self.assertIn("not valid JSON", error)


class CommandLine(unittest.TestCase):
    def test_an_unshipped_tracker_is_rejected_by_argparse(self):
        """OPP-15: rejection is a library guarantee, not hand-written."""
        parser_err = io.StringIO()
        with contextlib.redirect_stderr(parser_err):
            with self.assertRaises(SystemExit) as raised:
                init.main(["probe", "--output", "nonsense"])
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("invalid choice", parser_err.getvalue())

    def test_probe_emits_parseable_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = io.StringIO()
            with stubbed_runtime(), contextlib.redirect_stdout(out):
                init.main(["--root", tmp, "probe", "-o", "json"])
            report = json.loads(out.getvalue())
            for key in (
                "shipped_trackers",
                "tracker_probes",
                "runner",
                "gate_candidates",
                "constitution_candidates",
                "config_exists",
            ):
                self.assertIn(key, report)

    def test_probe_writes_no_file(self):
        """OPP-12: the discovery pass is read-only."""
        with tempfile.TemporaryDirectory() as tmp:
            with stubbed_runtime(), contextlib.redirect_stdout(io.StringIO()):
                init.main(["--root", tmp, "probe", "-o", "json"])
            self.assertEqual(os.listdir(tmp), [])

    def test_a_subcommand_is_required(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                init.main([])
        self.assertEqual(raised.exception.code, 2)

    def test_selftest_passes(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(init.main(["selftest"]), 0)


class NonInteractive(unittest.TestCase):
    def test_the_script_never_reads_stdin(self):
        """OPP-18: a prompt here would hang an agent session invisibly."""
        script = os.path.join(paths.PLUGIN_DIR, "scripts", "init.py")
        with open(script, encoding="utf-8") as handle:
            source = handle.read()
        for forbidden in ("input(", "sys.stdin.read", "getpass"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()


class ConfigBuilding(unittest.TestCase):
    def test_carries_every_documented_top_level_key(self):
        config = init.build_config("github", {"gate_command": "x"}, today="2026-01-01")
        for key in (
            "tracker",
            "runner",
            "compozy_pin",
            "plugin_version",
            "initialized_at",
            "project",
        ):
            self.assertIn(key, config)

    def test_runner_has_one_legal_value(self):
        """runner is recorded, not selected."""
        config = init.build_config("github", {"gate_command": "x"}, today="2026-01-01")
        self.assertEqual(config["runner"], "compozy")

    def test_plugin_version_is_read_from_the_manifest(self):
        with open(
            os.path.join(paths.PLUGIN_MANIFEST), encoding="utf-8"
        ) as handle:
            expected = json.load(handle)["version"]
        self.assertEqual(init.plugin_version(), expected)

    def test_an_absent_optional_key_is_written_as_null_not_omitted(self):
        """OPP-74: absence is a recorded decision, not a gap another project's
        value can quietly fill."""
        config = init.build_config("github", {"gate_command": "x"}, today="2026-01-01")
        self.assertEqual(sorted(config["project"]), sorted(init.PROJECT_KEYS))
        self.assertIsNone(config["project"]["constitution_path"])

    def test_missing_required_names_the_key(self):
        self.assertEqual(init.missing_required({}), ["gate_command"])

    def test_optional_keys_are_never_required(self):
        self.assertEqual(init.missing_required({"gate_command": "make test"}), [])


class WriteSubcommand(unittest.TestCase):
    def _write(self, root, extra=None):
        argv = [
            "--root",
            root,
            "write",
            "--tracker",
            "github",
            "--gate-command",
            "composer test",
            "--today",
            "2026-01-01",
        ]
        return init.main(argv + (extra or []))

    def test_writes_the_config_at_the_repository_root(self):
        """OPP-16: the same key, at the same path, the skill already reads."""
        with tempfile.TemporaryDirectory() as tmp:
            with contextlib.redirect_stdout(io.StringIO()):
                code = self._write(tmp)
            self.assertEqual(code, 0)
            path = os.path.join(tmp, init.CONFIG_NAME)
            self.assertTrue(os.path.isfile(path))
            with open(path, encoding="utf-8") as handle:
                self.assertEqual(json.load(handle)["tracker"], "github")

    def test_refuses_to_overwrite_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            with contextlib.redirect_stdout(io.StringIO()):
                self._write(tmp)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = self._write(tmp)
            self.assertEqual(code, 3)
            self.assertIn("already exists", out.getvalue())

    def test_force_replaces_an_existing_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            with contextlib.redirect_stdout(io.StringIO()):
                self._write(tmp)
                code = self._write(tmp, ["--force"])
            self.assertEqual(code, 0)

    def test_without_a_gate_command_it_exits_4_naming_the_key(self):
        """OPP-70/74: no value is carried over from another project."""
        with tempfile.TemporaryDirectory() as tmp:
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                code = init.main(
                    ["--root", tmp, "write", "--tracker", "github", "--today", "x"]
                )
            self.assertEqual(code, 4)
            self.assertIn("gate_command", err.getvalue())
            self.assertEqual(os.listdir(tmp), [])

    def test_a_malformed_existing_config_stops_the_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(
                os.path.join(tmp, init.CONFIG_NAME), "w", encoding="utf-8"
            ) as fh:
                fh.write("{oops")
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                code = self._write(tmp)
            self.assertEqual(code, 1)
            self.assertIn("not valid JSON", err.getvalue())

    def test_an_unshipped_tracker_is_rejected_before_any_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    init.main(
                        ["--root", tmp, "write", "--tracker", "asana", "--today", "x"]
                    )
            self.assertEqual(os.listdir(tmp), [])

    def test_the_written_file_ends_with_a_newline(self):
        with tempfile.TemporaryDirectory() as tmp:
            with contextlib.redirect_stdout(io.StringIO()):
                self._write(tmp)
            with open(
                os.path.join(tmp, init.CONFIG_NAME), encoding="utf-8"
            ) as handle:
                self.assertTrue(handle.read().endswith("\n"))

    def test_status_round_trips_what_write_produced(self):
        with tempfile.TemporaryDirectory() as tmp:
            with contextlib.redirect_stdout(io.StringIO()):
                self._write(tmp)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = init.main(["--root", tmp, "status"])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out.getvalue())["tracker"], "github")


class PinComparison(unittest.TestCase):
    def test_either_side_missing_is_unknown_not_a_match(self):
        self.assertEqual(init.compare_pin(None, "v0.3.0-beta.21"), "unknown")
        self.assertEqual(init.compare_pin("v0.3.0-beta.21", None), "unknown")

    def test_an_exact_pin_inside_the_version_string_matches(self):
        self.assertEqual(
            init.compare_pin("compozy version v0.3.0-beta.21", "v0.3.0-beta.21"),
            "match",
        )

    def test_a_different_build_is_drift(self):
        self.assertEqual(
            init.compare_pin("compozy version v0.3.0-beta.24", "v0.3.0-beta.21"),
            "drift",
        )

    def test_drift_is_not_resolved_silently(self):
        """A bump is a re-verification trigger: the flags were read from one
        specific build, so drift must surface rather than be tolerated."""
        self.assertNotEqual(
            init.compare_pin("v0.3.0-beta.24", "v0.3.0-beta.21"), "match"
        )


class PrereleaseDetection(unittest.TestCase):
    def test_a_beta_is_a_prerelease(self):
        self.assertTrue(init.is_prerelease("v0.3.0-beta.21"))

    def test_a_stable_release_is_not(self):
        self.assertFalse(init.is_prerelease("v1.0.0"))

    def test_build_metadata_alone_is_not_a_prerelease(self):
        self.assertFalse(init.is_prerelease("v1.0.0+build.5"))

    def test_an_absent_version_is_not_a_prerelease(self):
        self.assertFalse(init.is_prerelease(None))


class RunnerAdvice(unittest.TestCase):
    def test_absence_advises_installing_rather_than_writing_a_false_config(self):
        original = shutil.which
        try:
            shutil.which = lambda _name: None
            result = init.probe_runner("v0.3.0-beta.21")
            self.assertIn("not installed", result["advice"])
            self.assertIn("claims a working runner", result["advice"])
        finally:
            shutil.which = original

    def test_absence_still_names_the_install_command(self):
        original = shutil.which
        try:
            shutil.which = lambda _name: None
            self.assertEqual(
                init.probe_runner()["install_command"], init.INSTALL_COMMAND
            )
        finally:
            shutil.which = original


class PluginVersionReporting(unittest.TestCase):
    def test_probe_reports_the_plugin_version(self):
        """OPP-60: reported alongside the resolved tracker."""
        with tempfile.TemporaryDirectory() as tmp:
            out = io.StringIO()
            with stubbed_runtime(), contextlib.redirect_stdout(out):
                init.main(["--root", tmp, "probe", "-o", "json"])
            self.assertEqual(
                json.loads(out.getvalue())["plugin_version"], init.plugin_version()
            )

    def test_human_output_names_the_plugin_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = io.StringIO()
            with stubbed_runtime(), contextlib.redirect_stdout(out):
                init.main(["--root", tmp, "probe"])
            self.assertIn(f"plugin {init.plugin_version()}", out.getvalue())


class Selftest(unittest.TestCase):
    """T15's criteria, pinned. The selftest grew across T12-T14 rather than
    arriving whole; these assert what it must keep doing."""

    def test_prints_an_ok_line_and_exits_zero(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = init.main(["selftest"])
        self.assertEqual(code, 0)
        self.assertIn("ok", out.getvalue())

    def test_runs_from_any_working_directory(self):
        """It is an in-field diagnostic: it must not depend on being run from
        a project root, because it is run when something is already wrong."""
        original = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            try:
                os.chdir(tmp)
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(init.main(["selftest"]), 0)
            finally:
                os.chdir(original)

    def test_writes_no_file(self):
        original = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            try:
                os.chdir(tmp)
                with contextlib.redirect_stdout(io.StringIO()):
                    init.main(["selftest"])
                self.assertEqual(os.listdir(tmp), [])
            finally:
                os.chdir(original)

    def test_the_script_makes_no_network_calls(self):
        script = os.path.join(paths.PLUGIN_DIR, "scripts", "init.py")
        with open(script, encoding="utf-8") as handle:
            source = handle.read()
        for forbidden in ("urllib", "requests", "socket", "http.client"):
            self.assertNotIn(forbidden, source)


class VersionCommandRegression(unittest.TestCase):
    """Both bugs here were found by installing Compozy and running probe against
    it - neither was reachable from fixtures alone."""

    def test_version_is_read_from_a_subcommand_not_a_flag(self):
        """`compozy --version` does not exist; `compozy version` does. The
        conventional form was assumed rather than read from --help, and the
        probe reported the runner present with no version."""
        self.assertEqual(init.VERSION_COMMAND, ["compozy", "version"])
        self.assertNotIn("--version", init.VERSION_COMMAND)

    def test_a_missing_v_prefix_is_not_drift(self):
        """`compozy version` prints "compozy 0.3.0-beta.21" while the release
        tag reads "v0.3.0-beta.21". Substring comparison reported drift between
        a build and itself."""
        self.assertEqual(
            init.compare_pin("compozy 0.3.0-beta.21", "v0.3.0-beta.21"), "match"
        )

    def test_a_present_v_prefix_still_matches(self):
        self.assertEqual(
            init.compare_pin("compozy v0.3.0-beta.21", "0.3.0-beta.21"), "match"
        )

    def test_a_genuinely_different_build_is_still_drift(self):
        """The normalization must not soften a real mismatch."""
        self.assertEqual(
            init.compare_pin("compozy 0.3.0-beta.24", "v0.3.0-beta.21"), "drift"
        )

    def test_unreadable_output_is_unknown_not_a_match(self):
        self.assertEqual(init.compare_pin("garbage output", "v0.3.0-beta.21"), "unknown")

    def test_a_present_runner_with_no_readable_version_is_flagged(self):
        with stubbed_runtime(version=None):
            result = init.probe_runner("v0.3.0-beta.21")
        self.assertIsNone(result["version"])
        self.assertIn("unverified", result["advice"])


class VersionNormalization(unittest.TestCase):
    def test_extracts_the_bare_token(self):
        self.assertEqual(init.normalize_version("compozy 0.3.0-beta.21"), "0.3.0-beta.21")

    def test_strips_a_leading_v(self):
        self.assertEqual(init.normalize_version("v1.2.3"), "1.2.3")

    def test_a_string_with_no_version_yields_none(self):
        self.assertIsNone(init.normalize_version("no version here"))

    def test_none_yields_none(self):
        self.assertIsNone(init.normalize_version(None))

    def test_prerelease_detection_survives_normalization(self):
        self.assertTrue(init.is_prerelease("compozy 0.3.0-beta.21"))
        self.assertFalse(init.is_prerelease("compozy 1.0.0"))


class RunnerReadinessChain(unittest.TestCase):
    """Every prerequisite between a bare machine and a dispatchable runtime,
    reported as an ordered chain because each stage gates the next."""

    def test_stages_are_reported_in_dependency_order(self):
        with stubbed_runtime():
            names = [st["stage"] for st in init.probe_runner_stages(deep=True)]
        expected = ["binary", "version", "bootstrap", "daemon", "doctor"]
        self.assertEqual(names, expected[: len(names)])

    def test_the_chain_stops_at_the_first_failure(self):
        """Only the first failure is worth acting on; the rest are consequences."""
        original = shutil.which
        try:
            shutil.which = lambda _name: None
            stages = init.probe_runner_stages()
            self.assertEqual(len(stages), 1)
            self.assertFalse(stages[0]["ok"])
        finally:
            shutil.which = original

    def test_a_missing_binary_offers_the_install_command(self):
        original = shutil.which
        try:
            shutil.which = lambda _name: None
            stages = init.probe_runner_stages()
            self.assertIsNotNone(stages[0]["suggested_command"])
        finally:
            shutil.which = original

    def test_blocking_stage_is_named_rather_than_left_to_inference(self):
        with stubbed_runtime():
            result = init.probe_runner("v0.3.0-beta.21")
        self.assertIn("blocking_stage", result)
        self.assertIn("ready", result)
        if result["ready"]:
            self.assertIsNone(result["blocking_stage"])
        else:
            self.assertIsNotNone(result["blocking_stage"])


class SuggestedCommandParsing(unittest.TestCase):
    """Compozy names its own recovery command in JSON errors. Reading that beats
    hardcoding a fix that would drift from the runtime it repairs."""

    def test_reads_the_command_from_a_diagnostic_block(self):
        payload = json.dumps(
            {"error": "x", "diagnostic": {"suggested_command": "compozy daemon start"}}
        )
        self.assertEqual(init._suggested_command(payload), "compozy daemon start")

    def test_reads_a_top_level_suggested_command(self):
        payload = json.dumps({"suggested_command": "compozy install"})
        self.assertEqual(init._suggested_command(payload), "compozy install")

    def test_non_json_output_yields_none_rather_than_raising(self):
        self.assertIsNone(init._suggested_command("Doctor\n======\nStatus: error"))

    def test_none_yields_none(self):
        self.assertIsNone(init._suggested_command(None))


class DaemonStatusCommand(unittest.TestCase):
    def test_daemon_state_is_read_from_the_top_level_status_command(self):
        """Regression: `compozy daemon status` does not exist - daemon's
        subcommands are bootstrap, start and stop. The invalid form printed help
        and exited 0, which the check read as a stopped daemon while it ran."""
        self.assertEqual(
            init.DAEMON_STATUS_COMMAND, ["compozy", "status", "-o", "json"]
        )
        self.assertNotIn("daemon", init.DAEMON_STATUS_COMMAND)


class HumanOutput(unittest.TestCase):
    """The operator-facing view. The readiness chain was computed but not
    printed, so the one surface a human reads showed none of it."""

    def _probe(self, root):
        out = io.StringIO()
        with stubbed_runtime(), contextlib.redirect_stdout(out):
            init.main(["--root", root, "probe"])
        return out.getvalue()

    def test_every_stage_is_printed(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = self._probe(tmp)
            for name in ("binary", "version", "bootstrap", "daemon"):
                self.assertIn(name, text)

    def test_the_summary_states_whether_the_runner_is_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = self._probe(tmp)
            self.assertTrue(
                "runner ready" in text or "blocked at" in text,
                "summary must state runner readiness",
            )

    def test_a_failing_stage_prints_its_next_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = io.StringIO()
            with stubbed_runtime(binary=False), contextlib.redirect_stdout(out):
                init.main(["--root", tmp, "probe"])
            self.assertIn("next:", out.getvalue())


class LiveRuntimeIntegration(unittest.TestCase):
    """The one test that touches the real binary. Everything else is stubbed, so
    this is where a genuine mismatch between our commands and the installed
    Compozy would surface."""

    def setUp(self):
        if not shutil.which(init.RUNNER):
            self.skipTest("compozy is not installed on this machine")

    def test_the_real_version_command_returns_a_parseable_token(self):
        code, out = init._run(init.VERSION_COMMAND)
        self.assertEqual(code, 0, f"{' '.join(init.VERSION_COMMAND)} failed: {out}")
        self.assertIsNotNone(
            init.normalize_version(out),
            f"no version token in {out!r}",
        )

    def test_the_real_daemon_status_command_is_valid(self):
        """An invalid subcommand prints help and exits 0, so assert on content."""
        code, out = init._run(init.DAEMON_STATUS_COMMAND)
        self.assertEqual(code, 0)
        self.assertIn("daemon", out)
