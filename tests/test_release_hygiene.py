"""A published version must identify one content.

Derived from spec AC OPP-06 (a version is declared and incremented per release),
which was declared and never enforced. Three pull requests merged in sequence
under 0.4.4; a machine that had resolved the first reported itself up to date
while missing the other two, because an installation records the version it
resolved and nothing made that version move.

The decision under test is deliberately git-free: the workflow supplies the
changed paths and the base manifest, and this module only judges them.
"""

import importlib.util
import os
import unittest

import paths

SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(paths.__file__))),
    ".github", "scripts", "check_version_bump.py",
)


def load_module():
    spec = importlib.util.spec_from_file_location("check_version_bump", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class VersionBumpCheck(unittest.TestCase):
    def setUp(self):
        self.check = load_module()

    def test_the_script_ships_where_the_workflow_looks_for_it(self):
        self.assertTrue(os.path.isfile(SCRIPT), SCRIPT)

    def test_shipped_change_without_a_bump_is_refused(self):
        ok, message = self.check.verdict(
            ["plugins/orchestrate-project/skills/orchestrate-project/SKILL.md"],
            "0.4.4", "0.4.4",
        )
        self.assertFalse(ok)
        self.assertIn("0.4.4", message)

    def test_shipped_change_with_a_bump_passes(self):
        ok, _ = self.check.verdict(
            ["plugins/orchestrate-project/skills/orchestrate-project/SKILL.md"],
            "0.4.4", "0.4.5",
        )
        self.assertTrue(ok)

    def test_unshipped_change_needs_no_bump(self):
        """Tests, CI and repository docs are not what an installation resolves."""
        ok, _ = self.check.verdict(
            ["tests/test_references.py", "README.md", ".github/workflows/ci.yml"],
            "0.4.4", "0.4.4",
        )
        self.assertTrue(ok)

    def test_a_brand_new_plugin_needs_no_bump(self):
        """Nothing has published this version, so nothing can disagree with it."""
        ok, _ = self.check.verdict(
            ["plugins/orchestrate-project/skills/orchestrate-project/SKILL.md"],
            None, "0.1.0",
        )
        self.assertTrue(ok)

    def test_the_refusal_names_the_offending_files(self):
        """A message that says only "bump the version" makes the author hunt for
        which change triggered it."""
        _, message = self.check.verdict(
            ["plugins/orchestrate-project/skills/orchestrate-project/references/runner.md",
             "tests/test_references.py"],
            "0.4.4", "0.4.4",
        )
        self.assertIn("references/runner.md", message)
        self.assertNotIn("test_references.py", message)

    def test_the_refusal_says_what_to_edit(self):
        _, message = self.check.verdict(
            ["plugins/orchestrate-project/skills/orchestrate-project/SKILL.md"],
            "0.4.4", "0.4.4",
        )
        for place in ("plugin.json", "marketplace.json", "package.json"):
            self.assertIn(place, message, "the message must name every file that carries a version")
