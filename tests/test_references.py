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

    Two observed shapes: killed before finishing, and exited 0 after the tool it
    wrapped refused an unknown CLI flag. Both were reported as green before the
    output was read.

    The first shape has two killers with opposite remedies -- the kernel's OOM
    killer, and an agent harness reaping backgrounded commands while memory is
    still free. Six gate runs died to the second while a day was spent lowering
    worker counts against the first.
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


class DispatchFailureIsReportedNotWorkedAround(unittest.TestCase):
    """`POST /api/agent/spawn` hung for a whole run while every other daemon
    endpoint answered instantly. Eleven attempts across four parent-session
    states produced no dispatch and no child -- every one issued from a shell
    rather than from inside an agent turn, which is what the first reading of it
    missed.

    Three things went wrong around it, and each is asserted here: the wedge was
    not documented, so it was mapped by brute force; the only fix is a daemon
    restart, which kills other runs' implementers and is therefore a human's
    call; and with dispatch impossible, the orchestrator finished an item's last
    two assertions by hand — the one thing this skill says it never does.
    """

    def setUp(self):
        base = os.path.join(paths.PLUGIN_DIR, "skills", "orchestrate-project")
        self.skill = read(os.path.join(base, "SKILL.md"))
        self.runner = read(os.path.join(base, "references", "runner.md"))
        self.spawn = read(os.path.join(base, "references", "spawn.md"))

    def test_the_spawn_wedge_is_named_with_its_endpoint(self):
        self.assertIn("POST /api/agent/spawn", self.runner)

    def test_a_daemon_restart_is_a_human_decision(self):
        """It clears the wedge and kills every in-flight implementer on the box,
        including runs this skill cannot see."""
        for text in (self.runner, self.spawn):
            self.assertIn("Never restart the daemon", text)
        surface = self.skill[self.skill.index("## Surface, don't auto-do"):]
        self.assertIn("cannot dispatch", surface[:surface.index("\n## ")])

    def test_retries_are_bounded(self):
        self.assertIn("stop at two", self.spawn)

    def test_the_code_boundary_is_restated_for_a_dead_runner(self):
        section = self.skill[self.skill.index("## The orchestrator does not write code"):]
        section = section[:section.index("\n## Two boundaries")]
        self.assertIn("runner is down", section)
        self.assertIn("must not do is write the missing change", section)

    def test_orchestrator_landed_branches_still_follow_the_tracker(self):
        """Pushing the runner's local worktree name is how a PR ends up
        unlinkable from its item."""
        self.assertIn("run_branch_namespace", self.skill)


class ConcurrentRunsShareOneMachine(unittest.TestCase):
    """Two orchestrations ran against one clone. Each committed the other's
    uncommitted edits, one force-updated the other's branch and rewrote its pull
    request, both authored the same decision number into different features, and
    the contention killed six gate runs before they could finish.
    """

    def setUp(self):
        base = os.path.join(paths.PLUGIN_DIR, "skills", "orchestrate-project")
        self.skill = read(os.path.join(base, "SKILL.md"))
        self.spawn = read(os.path.join(base, "references", "spawn.md"))

    def test_the_repository_level_collision_is_named(self):
        self.assertIn("One orchestration per repository at a time", self.skill)

    def test_another_agents_uncommitted_work_is_never_committed(self):
        self.assertIn("Never commit another agent's uncommitted work", self.skill)

    def test_a_shared_clone_is_edited_with_plumbing(self):
        """checkout, reset --hard and stash all destroy work that was never yours."""
        self.assertIn("read-tree", self.skill)

    def test_machine_headroom_is_part_of_the_dispatch_preflight(self):
        self.assertIn("enough free memory", self.spawn)
        self.assertIn("All seven must hold", self.spawn)

    def test_shared_identifiers_are_read_from_the_trunk(self):
        """Two decisions shipped as the same number, each read before the other
        run appended to the log."""
        self.assertIn("before writing an identifier into it", self.skill)

    def test_the_two_killers_are_told_apart(self):
        """Their remedies are opposite: a narrower wave for the kernel, the
        foreground for a harness that reaps background jobs."""
        workflow = read(os.path.join(
            paths.PLUGIN_DIR, "skills", "orchestrate-project",
            "references", "standing-implementer-workflow.md",
        ))
        self.assertIn("Identify the killer", workflow)
        self.assertIn("not to background it", workflow)


class RateLimitIsNeitherDeathNorFinish(unittest.TestCase):
    """The most common stop on a long run reads as completion.

    Observed three times in one run: the provider refuses, the turn ends, and
    the session goes idle — identical to having finished. A wave released on
    that silence releases dependents against half-done work; a re-dispatch on
    it pays for the same item twice.
    """

    def setUp(self):
        base = os.path.join(paths.PLUGIN_DIR, "skills", "orchestrate-project")
        self.runner = read(os.path.join(base, "references", "runner.md"))
        self.monitor = read(os.path.join(base, "references", "monitor.md"))

    def test_the_runner_names_the_machine_readable_signature(self):
        self.assertIn("errorKind", self.runner)
        self.assertIn("rate_limited", self.runner)

    def test_the_runner_says_to_wait_rather_than_re_dispatch(self):
        self.assertIn("Do not re-dispatch", self.runner)

    def test_the_runner_warns_nothing_reopens_the_turn(self):
        self.assertIn("Nothing reopens the turn on its own", self.runner)

    def test_the_monitor_classifies_before_acting(self):
        self.assertIn("three causes", self.monitor)

    def test_the_monitor_forbids_inferring_the_cause_from_silence(self):
        self.assertIn("Never infer the cause from elapsed silence", self.monitor)


class UsageIsCapturedBeforeItDisappears(unittest.TestCase):
    """A run totalled at the end can only measure what still exists.

    `session usage` dies with the session; six of twelve were unmeasurable by
    review time.
    """

    def setUp(self):
        self.text = read(os.path.join(
            paths.PLUGIN_DIR, "skills", "orchestrate-project",
            "references", "monitor.md",
        ))

    def test_it_says_usage_dies_with_the_session(self):
        self.assertIn("dies with the session", self.text)

    def test_it_says_where_to_write_usage_down(self):
        self.assertIn("meta.json", self.text)


class CoordinationIsTheBiggestLineItem(unittest.TestCase):
    """The orchestrator outspent every implementer combined.

    Handing the next orchestrator the run's own state, rather than making it
    re-derive history, cost 4.7% of deriving it.
    """

    def setUp(self):
        self.text = read(os.path.join(
            paths.PLUGIN_DIR, "skills", "orchestrate-project", "SKILL.md",
        ))

    def test_it_carries_the_measured_comparison(self):
        self.assertIn("Coordination outspends the work", self.text)

    def test_it_tells_a_resume_to_state_what_is_already_true(self):
        self.assertIn("On a resume, state what is already true", self.text)

    def test_it_names_the_read_write_ratio_as_the_tell(self):
        self.assertIn("200:1", self.text)


class WorktreeNamesAreDeterministic(unittest.TestCase):
    """A generated worktree name is invisible until recovery needs it.

    One item of ten came up as `calm-badger` beside `jur-129`…`jur-137`. The
    recovery check reported "worktree absent" for a worktree that existed and
    held uncommitted work.
    """

    def setUp(self):
        self.text = read(os.path.join(
            paths.PLUGIN_DIR, "skills", "orchestrate-project",
            "references", "runner.md",
        ))

    def test_it_forbids_letting_the_runner_name_the_worktree(self):
        self.assertIn("never let the runner name it", self.text)

    def test_it_requires_recording_the_resolved_path(self):
        self.assertIn("record the resolved path", self.text)


class ReleaseHappensInTheTurnThatFlips(unittest.TestCase):
    """Flipping a PR and dispatching what it releases are one turn.

    Split three times in one run: the orchestrator flipped, reported, and ended
    the turn with the released item never dispatched. Nothing reopens the turn.
    """

    def setUp(self):
        self.text = read(os.path.join(
            paths.PLUGIN_DIR, "skills", "orchestrate-project",
            "references", "advance.md",
        ))

    def test_it_puts_the_dispatch_before_the_report(self):
        self.assertIn("Report before dispatching and the dispatch will not happen", self.text)

    def test_it_states_that_nothing_reopens_the_turn(self):
        self.assertIn("Nothing reopens the turn", self.text)

    def test_idle_with_items_left_is_not_an_ending(self):
        self.assertIn("is not an ending, it is a stall", self.text)

    def test_the_falsified_inference_is_recorded_as_false(self):
        """A turn was spent testing "call it from inside a turn" and it hung the
        same way. Leaving the theory standing would buy that turn again."""
        runner = read(os.path.join(
            paths.PLUGIN_DIR, "skills", "orchestrate-project",
            "references", "runner.md",
        ))
        self.assertIn("tested and is false", runner)
        self.assertIn("the discriminator", runner)

    def test_the_restart_decision_comes_with_its_blast_radius(self):
        """A human asked to restart with no list has to go and look."""
        runner = read(os.path.join(
            paths.PLUGIN_DIR, "skills", "orchestrate-project",
            "references", "runner.md",
        ))
        self.assertIn("enumerating what would die", runner)
        self.assertIn("stale flag", runner)

    def test_the_hang_is_placed_after_the_identity_check(self):
        """A stale session id fails in under a second; a fresh unbound one passes
        the check and then hangs. Reading it as a wedged endpoint produced the
        wrong remedy -- waiting it out instead of dispatching from a turn."""
        runner = read(os.path.join(
            paths.PLUGIN_DIR, "skills", "orchestrate-project",
            "references", "runner.md",
        ))
        self.assertIn("identity_stale", runner)
        self.assertIn("inside an agent's own turn", runner)


class DaemonLifecycleIsDocumentedWhereItLies(unittest.TestCase):
    """Twelve spawn failures over two days were a degraded daemon process, and a
    restart fixed it in seconds. Every command the restart needs misreported
    something, so "ask a human to restart" was not actionable on its own.
    """

    def setUp(self):
        base = os.path.join(paths.PLUGIN_DIR, "skills", "orchestrate-project")
        self.runner = read(os.path.join(base, "references", "runner.md"))
        self.spawn = read(os.path.join(base, "references", "spawn.md"))

    def test_the_age_claim_is_withdrawn_with_its_counter_evidence(self):
        """A restart fixed twelve failures and the same daemon failed again an
        hour later, so age was falsified faster than it was published."""
        self.assertIn("daemon.lock", self.runner)
        self.assertIn("age is not the discriminator", self.runner)
        self.assertIn("was wrong within the hour", self.runner)

    def test_the_restart_is_framed_as_a_window(self):
        """A restart buys a working dispatch window, not a fix; the wave goes out
        inside it."""
        self.assertIn("rather than a fix", self.runner)
        self.assertIn("inside that window", self.runner)

    def test_the_lying_stop_command_is_recorded(self):
        """`daemon stop` reported "not running" while the process held the socket."""
        self.assertIn("daemon is not running", self.runner)
        self.assertIn("/proc/<pid>", self.runner)

    def test_the_self_killing_start_is_recorded(self):
        """`daemon start` terminates the daemon it just booted when session repair
        outlives its readiness wait."""
        self.assertIn("received shutdown signal", self.runner)
        self.assertIn("setsid nohup", self.runner)

    def test_a_forced_kill_costs_recovery_time(self):
        self.assertIn("unapplied WAL", self.runner)

    def test_an_unprompted_child_is_named_as_the_trap(self):
        """A spawned child sits idle with zero events until it is prompted, which
        looks exactly like one that died."""
        self.assertIn("does not start it", self.spawn)
        self.assertIn("active_prompt: false", self.spawn)


class SpawnBudgetIsTheOperatingLimit(unittest.TestCase):
    """Measured across three daemon boots: two, two and three children, then
    every further spawn blocked. It blocks rather than refusing, and once
    blocked nothing short of a restart clears it -- not TTL expiry, not an idle
    machine, not killing the children's leftover processes.

    Four mechanisms have been published and falsified. These pin the measurement
    and the operating rule, which is what survived all four.
    """

    def setUp(self):
        base = os.path.join(paths.PLUGIN_DIR, "skills", "orchestrate-project")
        self.skill = read(os.path.join(base, "SKILL.md"))
        self.runner = read(os.path.join(base, "references", "runner.md"))

    def test_the_cap_matches_what_the_runner_measured(self):
        """A documented cap of 4 sent waves past a ceiling of about 2, where the
        extra dispatches did not error -- they hung."""
        self.assertIn("concurrency cap is **2**", self.skill)
        self.assertNotIn("concurrency cap is 4", self.skill)

    def test_blocking_is_distinguished_from_refusing(self):
        self.assertIn("blocks rather than refusing", self.runner)

    def test_the_failed_recoveries_are_listed(self):
        """Each was tried; listing them stops the next run retrying them."""
        self.assertIn("Once blocked, it stays blocked", self.runner)
        self.assertIn("killing the children's leftover processes", self.runner)

    def test_no_fifth_mechanism_is_claimed(self):
        self.assertIn("No mechanism is claimed here", self.runner)


class EveryRunCreatesItsOwnSession(unittest.TestCase):
    """The cold start said to reuse an `attachable` session named for the work
    group. A session is attachable only while a runtime is live, and that ends
    with the turn, so the branch was unreachable -- every reuse attempt failed.
    The thing worth guarding is two orchestrations of one group running at once,
    which is a question about a running session, not a reason to inherit a dead
    one.
    """

    def setUp(self):
        self.skill = read(os.path.join(
            paths.PLUGIN_DIR, "skills", "orchestrate-project", "SKILL.md",
        ))

    def test_the_run_creates_its_own_session(self):
        self.assertIn("Every run creates its own session", self.skill)

    def test_the_guard_is_a_live_run_not_an_inherited_one(self):
        self.assertIn("Check for a live run", self.skill)
        self.assertNotIn("Reuse before creating", self.skill)

    def test_the_withdrawn_rule_keeps_its_evidence(self):
        """Naming the errors stops someone restoring the rule."""
        for symptom in ("dead runtime", "not attachable", "identity_stale"):
            self.assertIn(symptom, self.skill)


class DispatchIsTheWholeLineAndThePrompt(unittest.TestCase):
    """Four refusals, one flag at a time, before a single dispatch; then two
    implementers sat idle because a spawn that returned a child was read as a
    dispatch; then a worktree removed before its session wedged the CLI.
    """

    def setUp(self):
        base = os.path.join(paths.PLUGIN_DIR, "skills", "orchestrate-project")
        self.skill = read(os.path.join(base, "SKILL.md"))
        self.runner = read(os.path.join(base, "references", "runner.md"))
        self.spawn = read(os.path.join(base, "references", "spawn.md"))

    def test_the_identity_is_checked_as_a_pair_before_phase_0(self):
        section = self.skill[self.skill.index("## Before anything"):]
        self.assertIn("`COMPOZY_AGENT`", section[:section.index("\n### ")])

    def test_the_runner_carries_the_inline_identity_line(self):
        self.assertIn("COMPOZY_SESSION_ID=<parent-session-id> COMPOZY_AGENT=", self.runner)

    def test_every_refusal_on_the_way_is_named(self):
        for refusal in ('"agent", "ttl-seconds" not set',
                        "provider is required when model is set"):
            self.assertIn(refusal, self.runner)

    def test_a_workspace_is_registered_with_a_name(self):
        self.assertIn('workspace add "<path>" --name', self.runner)

    def test_the_prompt_is_part_of_the_dispatch(self):
        self.assertIn("Dispatch is three commands, never one", self.spawn)
        self.assertIn("no `--message` flag", self.spawn)

    def test_teardown_has_an_order(self):
        self.assertIn("stop → archive → remove", self.runner)
        self.assertIn("workspace has active sessions", self.runner)

    def test_teardown_looks_for_unlanded_work_first(self):
        self.assertIn("look for work that never landed", self.runner)


class AHungDaemonAndAFilteredPipeBothLookFine(unittest.TestCase):
    """A daemon with a live process and a live socket timed out on writes, then
    reads, and a timed-out `session list` printed nothing -- the same bytes as
    a machine with no sessions. Separately, piped and silenced commands kept
    reporting the status of the wrong process.
    """

    def setUp(self):
        base = os.path.join(paths.PLUGIN_DIR, "skills", "orchestrate-project")
        self.runner = read(os.path.join(base, "references", "runner.md"))
        self.monitor = read(os.path.join(base, "references", "monitor.md"))

    def test_hung_is_told_apart_from_crashed(self):
        self.assertIn("hung rather than crashed", self.runner)

    def test_an_empty_listing_after_a_timeout_is_unknown(self):
        self.assertIn("A timed-out listing is not an empty one", self.runner)
        self.assertIn("unknown, not zero", self.runner)

    def test_the_restart_stays_with_the_human(self):
        self.assertIn("still the human's, even when it blocks this run's dispatch", self.runner)

    def test_the_pipe_status_trap_is_named(self):
        self.assertIn("A filter hides the error you need", self.monitor)
        self.assertIn("`head`'s", self.monitor)


class SteersLandLateAndFencesNameAnOwner(unittest.TestCase):
    """A corrective steer sat third in a queue while the implementer authored the
    two out-of-scope commits it was meant to prevent, into files a second
    implementer owned. The fence had named paths, not the owner.
    """

    def setUp(self):
        base = os.path.join(paths.PLUGIN_DIR, "skills", "orchestrate-project")
        self.runner = read(os.path.join(base, "references", "runner.md"))
        self.monitor = read(os.path.join(base, "references", "monitor.md"))
        self.spawn = read(os.path.join(base, "references", "spawn.md"))
        self.workflow = read(os.path.join(
            base, "references", "standing-implementer-workflow.md"))

    def test_queue_delivery_is_after_the_turn(self):
        self.assertIn("delivers after the current turn, and only then", self.runner)
        self.assertIn("session input list", self.runner)

    def test_the_missing_turn_id_is_recorded(self):
        self.assertIn("no turn id", self.runner)

    def test_the_queue_is_pruned_before_adding(self):
        self.assertIn("Prune before you add", self.monitor)
        self.assertIn("session input cancel", self.monitor)

    def test_every_steer_restates_the_finish_line(self):
        self.assertIn("Restate the whole finish line in every steer", self.monitor)

    def test_fences_name_an_owner_and_overlap_is_sequenced(self):
        self.assertIn("Fence by owner, not by path", self.monitor)
        self.assertIn("sequence them instead of fencing", self.monitor)
        self.assertIn("Ownership fences, by owner", self.spawn)
        self.assertIn("reported to that owner, never fixed here", self.workflow)


class VerificationReadsWhatItMeasured(unittest.TestCase):
    """A scoped run stayed green after a follow-up commit widened the diff into
    shared code; a briefing cited numbers from an API that ignored its page
    parameter; background verification runs were reaped and reported nothing.
    """

    def setUp(self):
        base = os.path.join(paths.PLUGIN_DIR, "skills", "orchestrate-project")
        self.skill = read(os.path.join(base, "SKILL.md"))
        self.monitor = read(os.path.join(base, "references", "monitor.md"))
        self.advance = read(os.path.join(base, "references", "advance.md"))

    def test_scope_growth_is_a_cheap_check(self):
        self.assertIn("**Scope has not grown**", self.skill)

    def test_blast_radius_is_per_head(self):
        self.assertIn("Blast radius belongs to the verified head", self.skill)
        self.assertIn("per verified head, not per item", self.monitor)

    def test_the_instrument_is_validated(self):
        self.assertIn("Validate the instrument before citing a reading", self.monitor)

    def test_a_reaped_gate_is_not_green(self):
        self.assertIn("A killed or memory-reaped gate is not a green gate", self.monitor)
        self.assertIn("create → use → remove", self.monitor)

    def test_red_gates_are_controlled_against_main(self):
        self.assertIn("Compare the failing-test\nlists", self.monitor)

    def test_mutation_sensors_count_replacements(self):
        self.assertIn("abort on zero", self.monitor)

    def test_green_making_test_commits_are_read(self):
        self.assertIn("read for weakening", self.monitor)

    def test_visual_references_are_never_regenerated_to_pass(self):
        self.assertIn("Never regenerate a\nreference just to turn a gate green", self.monitor)

    def test_the_user_facing_path_is_checked(self):
        self.assertIn("Green tests can still ship the wrong behaviour", self.monitor)

    def test_the_draft_flag_is_the_brake(self):
        self.assertIn("gh pr ready <pr> --undo", self.advance)

    def test_ci_red_starts_with_the_annotation(self):
        self.assertIn("Read the check annotation", self.monitor)
        self.assertIn("multi-minute duration", self.monitor)


class TheRunKeepsItsOwnState(unittest.TestCase):
    """Facts the orchestrator had already found -- an API address, the working
    dispatch flags -- cost about six round trips each to rediscover, because
    nothing it could re-read held them.
    """

    def setUp(self):
        base = os.path.join(paths.PLUGIN_DIR, "skills", "orchestrate-project")
        self.skill = read(os.path.join(base, "SKILL.md"))
        self.monitor = read(os.path.join(base, "references", "monitor.md"))

    def test_the_run_state_file_is_named_in_both_places(self):
        self.assertIn(".orch/RUN-STATE.md", self.skill)
        self.assertIn(".orch/RUN-STATE.md", self.monitor)

    def test_it_is_read_first_and_never_replaces_the_graph(self):
        self.assertIn("read this file before anything else", self.monitor)
        self.assertIn("it\nnever replaces the graph", self.monitor)

    def test_compaction_happens_at_boundaries(self):
        self.assertIn("Compact at boundaries", self.skill)

    def test_it_never_holds_a_credential(self):
        self.assertIn("never a credential", self.monitor)

    def test_polls_and_secondary_measurements_are_bounded(self):
        self.assertIn("Prefer single-shot checks to long background polls", self.monitor)
        self.assertIn("Bound the attempts on a secondary measurement", self.monitor)


class ProductionAndRetractionsAreHonest(unittest.TestCase):
    """Production actions sit outside every review this skill has, and a claim
    the orchestrator retracted in chat kept living in a briefing and a pull
    request body.
    """

    def setUp(self):
        base = os.path.join(paths.PLUGIN_DIR, "skills", "orchestrate-project")
        self.skill = read(os.path.join(base, "SKILL.md"))
        self.monitor = read(os.path.join(base, "references", "monitor.md"))
        self.decisions = read(os.path.join(base, "references", "decisions.md"))
        self.workflow = read(os.path.join(
            base, "references", "standing-implementer-workflow.md"))

    def test_production_actions_are_surfaced_not_done(self):
        surface = self.skill[self.skill.index("## Surface, don't auto-do"):]
        surface = surface[:surface.index("\n## ")]
        self.assertIn("destructive or outward production action", surface)

    def test_each_action_is_authorized_and_logged_with_a_revert(self):
        self.assertIn("for that instance", self.decisions)
        self.assertIn('"not reversible"', self.decisions)

    def test_production_is_measured_from_the_machine_that_matters(self):
        self.assertIn("from the machine that matters", self.monitor)

    def test_retractions_reach_every_place_the_claim_went(self):
        self.assertIn("retracted everywhere it travelled", self.decisions)
        self.assertIn("edits the body itself", self.decisions)

    def test_a_refused_tracker_write_has_a_stated_fallback(self):
        self.assertIn("If the tracker refuses the write", self.workflow)
