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


#: Files that still live only in the source tree. Each is copied and retargeted
#: in a later task; the link checker treats a link to one of these as pending
#: rather than broken. The set shrinks to empty as the migration completes, at
#: which point the check becomes fully strict on its own.
PENDING_MIGRATION = {
    "SKILL.md",
    "advance.md",
    "compute-waves.md",
    "monitor.md",
    "plan-production.md",
    "spawn.md",
    "standing-implementer-workflow.md",
    "trackers/jira.md",
    "trackers/linear.md",
}


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
        for name in ("clarify.md", "contract.md", "read.md"):
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
        other than where it was written."""
        self.assertIn("${CLAUDE_PLUGIN_ROOT}", self.text)

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
