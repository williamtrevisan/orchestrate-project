"""Structural gates for the shipped skill references.

Derived from spec ACs OPP-02 (every reference ships), OPP-32 (a case-insensitive
search for `orca` returns zero matches) and OPP-22 (runner.md records the Compozy
version its command table was captured at).
"""

import os
import re
import unittest

import paths

LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


#: Files that still live only in the source tree. The link checker treats a link
#: to one of these as pending rather than broken.
#:
#: **This set is now empty: the migration is complete.** The link check is fully
#: strict, which is what it was written to become. An entry added back here must
#: be removed again before the migration can be called done.
PENDING_MIGRATION = set()


class OrcaFreedom(unittest.TestCase):
    """The whole point of the migration, asserted mechanically.

    This is a ratchet, not a milestone. It passes today because no Orca-carrying
    file has been copied in yet, and it fails the moment one arrives uncleaned.
    That is the useful direction: it prevents the regression rather than
    recording it.
    """

    def test_no_shipped_file_mentions_orca(self):
        offenders = {}
        for path in paths.shipped_markdown():
            hits = len(re.findall(r"orca", read(path), re.IGNORECASE))
            if hits:
                offenders[os.path.relpath(path, paths.REPO_ROOT)] = hits
        self.assertEqual(offenders, {})


class ShippedReferences(unittest.TestCase):
    def test_the_runtime_independent_references_are_present(self):
        for name in (
            "clarify.md",
            "compute-waves.md",
            "contract.md",
            "monitor.md",
            "plan-production.md",
            "read.md",
            "runner.md",
            "spawn.md",
            "standing-implementer-workflow.md",
        ):
            self.assertTrue(
                os.path.isfile(os.path.join(paths.REFERENCES_DIR, name)), name
            )

    def test_at_least_one_tracker_ships(self):
        trackers = [n for n in os.listdir(paths.TRACKERS_DIR) if n.endswith(".md")]
        self.assertTrue(trackers)

    def test_no_shipped_markdown_is_empty(self):
        for path in paths.shipped_markdown():
            self.assertTrue(read(path).strip(), path)


class RelativeLinks(unittest.TestCase):
    def test_every_relative_markdown_link_resolves_or_is_pending(self):
        broken = []
        for path in paths.shipped_markdown():
            base = os.path.dirname(path)
            for target in LINK.findall(read(path)):
                target = target.split("#", 1)[0].strip()
                if not target or "://" in target or target.startswith("mailto:"):
                    continue
                if os.path.exists(os.path.join(base, target)):
                    continue
                if os.path.normpath(target).lstrip("./") in PENDING_MIGRATION:
                    continue
                broken.append(f"{os.path.relpath(path, paths.REPO_ROOT)} -> {target}")
        self.assertEqual(broken, [])

    def test_pending_set_shrinks_as_files_arrive(self):
        """A file listed as pending must not already be shipped - a stale entry
        would silently exempt a real broken link."""
        shipped = {
            os.path.relpath(p, paths.REFERENCES_DIR) for p in paths.shipped_markdown()
        }
        self.assertEqual(sorted(PENDING_MIGRATION & shipped), [])


class RunnerVersionStamp(unittest.TestCase):
    """runner.md is the only file naming a Compozy command, so it must record
    the version those commands were captured at. Skipped until it exists."""

    def setUp(self):
        self.runner = os.path.join(paths.REFERENCES_DIR, "runner.md")
        if not os.path.isfile(self.runner):
            self.skipTest("runner.md is written in T5/T6, once Compozy is installed")

    def test_records_an_exact_compozy_version(self):
        self.assertRegex(read(self.runner), r"v\d+\.\d+\.\d+(-[0-9A-Za-z.]+)?")

    def test_records_the_capture_date(self):
        self.assertRegex(read(self.runner), r"\d{4}-\d{2}-\d{2}")


if __name__ == "__main__":
    unittest.main()


class InitCommand(unittest.TestCase):
    """T16's criteria, asserted rather than trusted to prose review."""

    def setUp(self):
        self.path = os.path.join(
            paths.PLUGIN_DIR, "commands", "orchestrate-init.md"
        )
        if not os.path.isfile(self.path):
            self.skipTest("orchestrate-init.md is written in T16")
        self.text = read(self.path)

    def test_resolves_the_script_through_the_plugin_root_variable(self):
        """A hardcoded path breaks the moment the plugin is installed anywhere
        other than where it was written. The `:-` default extends that to the
        second shape this ships in, where a repository vendored the skill into
        .claude/ and the variable is not set at all; test_installer asserts the
        bare form is gone."""
        self.assertIn("${CLAUDE_PLUGIN_ROOT:-", self.text)

    def test_probes_before_it_writes(self):
        self.assertLess(self.text.index("probe"), self.text.index("write \\"))

    def test_documents_every_exit_code_the_script_can_return(self):
        for code in ("| 0 |", "| 1 |", "| 2 |", "| 3 |", "| 4 |"):
            self.assertIn(code, self.text)

    def test_states_that_a_failing_option_is_shown_not_hidden(self):
        self.assertIn("never hide it", self.text.lower())

    def test_carries_frontmatter_with_a_description(self):
        self.assertTrue(self.text.startswith("---"))
        self.assertIn("description:", self.text.split("---")[1])


class InitPerformsRunnerSetup(unittest.TestCase):
    """A setup command that prints a list of commands to type has not set
    anything up. The two exceptions are changes outside the repository."""

    def setUp(self):
        self.path = os.path.join(paths.PLUGIN_DIR, "commands", "orchestrate-init.md")
        if not os.path.isfile(self.path):
            self.skipTest("orchestrate-init.md is written in T16")
        self.text = read(self.path)

    def test_it_runs_the_command_rather_than_printing_it(self):
        self.assertIn("run it", self.text.lower())
        self.assertIn("do not print the", self.text.lower())

    def test_it_names_the_two_things_it_cannot_do_for_the_operator(self):
        for cannot in ("PATH", "claude mcp add"):
            self.assertIn(cannot, self.text)

    def test_it_confirms_before_each_step_rather_than_once(self):
        self.assertIn("never chain past a refusal", self.text.lower())


class StandingWorkflowIsProjectAgnostic(unittest.TestCase):
    """Baked-in default 0: "Nothing about a project is hardcoded."

    The standing workflow is embedded verbatim in every dispatch prompt, for
    every repository. It shipped naming one project's skills and one project's
    CI job as though they were universal, so an implementer in any other
    repository was told to run tooling that does not exist there and warned
    about a check that would never run. Every project-specific fact reaches an
    implementer through its assignment, which is derived from that project's own
    configuration.
    """

    def setUp(self):
        self.path = os.path.join(
            paths.PLUGIN_DIR, "skills", "orchestrate-project",
            "references", "standing-implementer-workflow.md",
        )
        self.text = read(self.path)

    def test_it_names_no_project_specific_skill_or_workflow_file(self):
        for borrowed in ("live-docs-sync", "live-docs-pr-create",
                         "live-docs-pr-description", "docs-check.yml"):
            self.assertNotIn(
                borrowed, self.text,
                f"{borrowed} belongs to one project, not to every dispatch prompt",
            )

    def test_it_defers_project_facts_to_the_assignment(self):
        lowered = self.text.lower()
        self.assertIn("your assignment", lowered)

    def test_the_gate_still_comes_from_configuration(self):
        """The one project fact it may name is where to read project facts."""
        self.assertIn("project.gate_command", self.text)


class DispatchSurvivesTheOrchestratorsTurn(unittest.TestCase):
    """A wave was lost to a default nobody read.

    `compozy spawn --auto-stop-on-parent` defaults to true, and the parent is
    the orchestrating session rather than a supervisor process. Ending a turn is
    a normal stop, so the default cascaded it and killed both implementers of a
    live wave mid-work, with the code uncommitted in their worktrees.

    The guidance existed as one bullet in a flag list while the canonical
    `spawn` row a reader copies carried neither that flag nor the MCP grant.
    These assert the fix where it is actually read: in the command itself.
    """

    def setUp(self):
        base = os.path.join(paths.PLUGIN_DIR, "skills", "orchestrate-project")
        self.runner = read(os.path.join(base, "references", "runner.md"))
        self.spawn = read(os.path.join(base, "references", "spawn.md"))
        self.monitor = read(os.path.join(base, "references", "monitor.md"))

    def test_the_canonical_spawn_command_disables_auto_stop(self):
        """The row a reader copies is the row that has to be right."""
        row = next(
            line for line in self.runner.splitlines()
            if line.startswith("| `spawn(")
        )
        self.assertIn("--auto-stop-on-parent=false", row)

    def test_the_canonical_spawn_command_grants_the_tracker(self):
        row = next(
            line for line in self.runner.splitlines()
            if line.startswith("| `spawn(")
        )
        self.assertIn("--mcp-server", row)

    def test_the_default_is_recorded_with_what_it_cost(self):
        self.assertIn("defaults to `true`", self.runner)
        self.assertIn("--auto-stop-on-parent=false", self.spawn)

    def test_a_worktree_is_not_a_workspace(self):
        """`spawn --workspace` resolves the workspace registry, not the worktree
        one, and `workspace add` is the one command that closes the gap. Phase 3
        routed around this for a whole release, paying the MCP grant and the TTL
        for a limitation that was a missing registration."""
        self.assertIn("workspace add", self.runner)
        self.assertIn("workspace add", self.spawn)
        self.assertIn("workspace not found", self.spawn)

    def test_a_dead_implementer_is_read_before_it_is_replaced(self):
        """A killed session looks exactly like one that never started; the
        difference is on disk, in the worktree."""
        self.assertIn("git -C <worktree> status --short", self.monitor)


class IncompleteChecksAreNotResults(unittest.TestCase):
    """A gate that never finished reports no failures, which reads as a pass.

    Two observed shapes: killed by the OS out-of-memory killer on a contended
    machine, and exited 0 after the tool it wrapped refused an unknown CLI flag.
    Both were reported as green before the output was read.
    """

    def setUp(self):
        self.text = read(os.path.join(
            paths.PLUGIN_DIR, "skills", "orchestrate-project",
            "references", "standing-implementer-workflow.md",
        ))

    def test_it_separates_did_not_finish_from_passed(self):
        self.assertIn("is not a gate that passed", self.text)

    def test_it_names_the_exit_zero_trap(self):
        self.assertIn("Exited 0 having done nothing", self.text)

    def test_it_offers_blast_radius_as_the_honest_fallback(self):
        lowered = self.text.lower()
        self.assertIn("blast radius", lowered)


class TheOrchestratorAssertsItsOwnTier(unittest.TestCase):
    """Every item's tier is asserted; the asserting session's never was.

    A cold-started orchestrator resolved to `claude-sonnet-5` and began Phase 0
    with nothing reporting it, while "Opus orchestrates" held only by luck. The
    trap that hides it is `session list`'s `runtime.effective`, which keeps
    reporting the previous turn's model after a `runtime set`.
    """

    def setUp(self):
        self.text = read(os.path.join(
            paths.PLUGIN_DIR, "skills", "orchestrate-project",
            "references", "runner.md",
        ))

    def test_it_names_the_per_session_lever(self):
        self.assertIn("session runtime set", self.text)

    def test_it_warns_that_effective_is_stale(self):
        self.assertIn("stale snapshot", self.text)

    def test_it_names_the_authoritative_field(self):
        self.assertIn("prompt_runtime", self.text)


class PromptDeliveryIsCountedNotInferred(unittest.TestCase):
    """A retry loop guarded on anything but the turn count double-delivers.

    `session prompt` prints errors on stdout and exits 0 without delivering, so
    a loop that retries on a non-zero status eventually sends an orchestrator
    its marching orders twice.
    """

    def setUp(self):
        self.text = read(os.path.join(
            paths.PLUGIN_DIR, "skills", "orchestrate-project",
            "references", "runner.md",
        ))

    def test_it_offers_the_turn_count_as_the_delivery_check(self):
        self.assertIn("session history", self.text)

    def test_it_forbids_guarding_a_resend_on_the_exit_status(self):
        self.assertIn("re-sends on a non-zero exit", self.text)


class AWedgeIsRecheckedAndOutwaited(unittest.TestCase):
    """The list-endpoints-answer classification expires, and restarts cost more.

    The same wedge spread to `workspace list`, `session list` and
    `session status` within the hour, then cleared on its own while a guarded
    retry dispatched the waiting item.
    """

    def setUp(self):
        self.text = read(os.path.join(
            paths.PLUGIN_DIR, "skills", "orchestrate-project",
            "references", "runner.md",
        ))

    def test_it_marks_the_classification_as_a_snapshot(self):
        self.assertIn("snapshot, not a diagnosis", self.text)

    def test_it_prefers_waiting_to_restarting(self):
        self.assertIn("Prefer waiting", self.text)


class MonitorsSurviveTheRunner(unittest.TestCase):
    """A monitor sourced only from the daemon goes blind, silently.

    Observed: a poll loop written as query-parse-echo swallowed a full outage
    and read as a healthy, unchanged run.
    """

    def setUp(self):
        self.text = read(os.path.join(
            paths.PLUGIN_DIR, "skills", "orchestrate-project",
            "references", "monitor.md",
        ))

    def test_it_requires_a_runner_independent_channel(self):
        self.assertIn("cannot take down with it", self.text)

    def test_it_requires_emitting_when_the_source_fails(self):
        self.assertIn("runner unreachable", self.text)


class UnstartedCIIsNotTheItemsFailure(unittest.TestCase):
    """Actions unavailable stalls the whole model, so it needs its own path.

    A billing block failed every job in seconds with no steps, which the CI-green
    ready-flip gate turns into a wave that can never release.
    """

    def setUp(self):
        self.text = read(os.path.join(
            paths.PLUGIN_DIR, "skills", "orchestrate-project",
            "references", "monitor.md",
        ))

    def test_it_separates_a_job_that_never_ran_from_a_red_check(self):
        self.assertIn("never started is not the item's failure", self.text)

    def test_it_confirms_against_the_default_branch_before_blaming_the_run(self):
        self.assertIn("Confirm it is environmental", self.text)

    def test_it_forbids_looping_for_a_green_that_cannot_arrive(self):
        self.assertIn("Do not loop waiting for green", self.text)

    def test_a_substituted_gate_is_re_run_not_trusted(self):
        self.assertIn("Re-run the gate yourself", self.text)


class CitedPathsMustExistInAWorktree(unittest.TestCase):
    """Paths resolve in the orchestrating session and vanish in the checkout.

    Ten items cited a spec directory the repository's `.gitignore` excluded, so
    every worktree would have been dispatched without the documents its prompt
    was built around.
    """

    def setUp(self):
        self.text = read(os.path.join(
            paths.PLUGIN_DIR, "skills", "orchestrate-project",
            "references", "spawn.md",
        ))

    def test_it_requires_checking_cited_paths_before_dispatch(self):
        self.assertIn("readable inside a fresh worktree", self.text)

    def test_it_names_the_check_that_finds_an_ignored_path(self):
        self.assertIn("git check-ignore", self.text)

    def test_the_configured_gate_is_a_default_not_the_items_gate(self):
        self.assertIn("not necessarily this item's gate", self.text)
