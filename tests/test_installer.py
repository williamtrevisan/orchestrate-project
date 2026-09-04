"""Structural gates for the vendoring installer.

The skill ships in two shapes: installed as a Claude Code plugin, and vendored
into a repository's .claude/ by bin/install.mjs. These assert the second shape
is real - that what lands is complete, that it is inert to re-runs, that it
refuses to overwrite a copy someone edited, and that the shipped script still
finds its own references once the layout around it has changed.
"""

import json
import os
import shutil
import subprocess
import tempfile
import unittest

import paths


def load(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def node_missing():
    return shutil.which("node") is None


class PackageManifest(unittest.TestCase):
    """package.json is a third place a version is written down. The first two
    disagreeing is what shipped 0.4.1 against a 0.4.3 plugin, so this one is
    pinned to them by a test rather than by discipline."""

    def test_version_matches_the_plugin_manifest(self):
        self.assertEqual(
            load(paths.PACKAGE_MANIFEST)["version"],
            load(paths.PLUGIN_MANIFEST)["version"],
        )

    def test_bin_entry_points_at_the_installer(self):
        manifest = load(paths.PACKAGE_MANIFEST)
        self.assertEqual(manifest["bin"]["orchestrate-project"], "bin/install.mjs")
        self.assertTrue(os.path.isfile(paths.INSTALLER))

    def test_published_files_carry_the_payload(self):
        """npx fetches only what `files` lists; omitting plugins/ would ship an
        installer with nothing to install."""
        self.assertEqual(sorted(load(paths.PACKAGE_MANIFEST)["files"]), ["bin", "plugins"])


class CommandPathResolution(unittest.TestCase):
    def setUp(self):
        with open(
            os.path.join(paths.COMMANDS_DIR, "orchestrate-init.md"), encoding="utf-8"
        ) as handle:
            self.body = handle.read()

    def test_every_invocation_carries_the_vendored_default(self):
        """A bare ${CLAUDE_PLUGIN_ROOT} expands to the empty string outside the
        plugin runtime, which calls python3 /scripts/init.py."""
        self.assertNotIn("${CLAUDE_PLUGIN_ROOT}", self.body)

    def test_the_default_resolves_to_the_vendored_skill(self):
        self.assertIn(
            "${CLAUDE_PLUGIN_ROOT:-.claude/skills/orchestrate-project}/scripts/init.py",
            self.body,
        )


@unittest.skipIf(node_missing(), "node is not installed on this machine")
class Installer(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.skill = os.path.join(self.root, ".claude", "skills", "orchestrate-project")

    def run_installer(self, *args):
        return subprocess.run(
            ["node", paths.INSTALLER, *args, "--root", self.root],
            capture_output=True,
            text=True,
        )

    def install(self, *args):
        result = self.run_installer("install", *args)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def test_install_lands_the_skill_its_references_and_its_scripts(self):
        self.install()
        for relative in (
            "SKILL.md",
            os.path.join("references", "trackers", "github.md"),
            os.path.join("scripts", "init.py"),
        ):
            self.assertTrue(os.path.isfile(os.path.join(self.skill, relative)), relative)

    def test_install_lands_the_init_command(self):
        self.install()
        self.assertTrue(
            os.path.isfile(
                os.path.join(self.root, ".claude", "commands", "orchestrate-init.md")
            )
        )

    def test_install_records_the_hash_in_the_lockfile(self):
        self.install()
        entry = load(os.path.join(self.root, "skills-lock.json"))["skills"][
            "orchestrate-project"
        ]
        self.assertEqual(entry["source"], "williamtrevisan/orchestrate-project")
        self.assertEqual(entry["sourceType"], "github")
        self.assertRegex(entry["computedHash"], r"^[0-9a-f]{64}$")

    def test_the_recorded_hash_matches_the_skill_meta(self):
        self.install()
        lock = load(os.path.join(self.root, "skills-lock.json"))
        meta = load(os.path.join(self.skill, ".skill-meta.json"))
        self.assertEqual(lock["skills"]["orchestrate-project"]["computedHash"], meta["contentHash"])

    def test_no_build_artefact_is_vendored(self):
        """A __pycache__ would make the hash differ per machine for identical
        content, so an install would never report itself current."""
        self.install()
        for dirpath, dirnames, filenames in os.walk(self.skill):
            self.assertNotIn("__pycache__", dirnames, dirpath)
            for name in filenames:
                self.assertFalse(name.endswith(".pyc"), name)

    def test_a_second_install_is_inert(self):
        self.install()
        self.assertIn("nothing to do", self.install().stdout)

    def test_install_refuses_to_overwrite_a_local_edit(self):
        self.install()
        with open(os.path.join(self.skill, "SKILL.md"), "a", encoding="utf-8") as handle:
            handle.write("\nlocal edit\n")
        result = self.run_installer("install")
        self.assertEqual(result.returncode, 3)
        self.assertIn("local edits", result.stderr)

    def test_force_overwrites_a_local_edit(self):
        self.install()
        target = os.path.join(self.skill, "SKILL.md")
        with open(target, "a", encoding="utf-8") as handle:
            handle.write("\nlocal edit\n")
        self.install("--force")
        with open(target, encoding="utf-8") as handle:
            self.assertNotIn("local edit", handle.read())

    def test_remove_takes_back_the_files_and_the_lock_entry(self):
        self.install()
        result = self.run_installer("remove")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(os.path.exists(self.skill))
        self.assertNotIn(
            "orchestrate-project",
            load(os.path.join(self.root, "skills-lock.json"))["skills"],
        )

    def test_remove_preserves_other_skills_in_the_lockfile(self):
        lock = os.path.join(self.root, "skills-lock.json")
        with open(lock, "w", encoding="utf-8") as handle:
            json.dump({"version": 1, "skills": {"vue": {"source": "antfu/skills"}}}, handle)
        self.install()
        self.run_installer("remove")
        self.assertIn("vue", load(lock)["skills"])

    def test_the_vendored_script_still_finds_its_trackers(self):
        """The layout around init.py changes when it is vendored: references/
        moves from three levels away to one. This is the whole reason the
        vendored shape is usable rather than merely present."""
        self.install()
        environment = {k: v for k, v in os.environ.items() if k != "CLAUDE_PLUGIN_ROOT"}
        result = subprocess.run(
            [
                "python3",
                os.path.join(self.skill, "scripts", "init.py"),
                "--root", self.root, "probe", "-o", "json",
            ],
            capture_output=True, text=True, env=environment,
        )
        # The exit code is deliberately not asserted: probe returns 1 when no
        # tracker authenticates, which is the state of any runner without gh
        # credentials. It prints the report either way, and the report is what
        # carries the answer this test is after.
        self.assertTrue(result.stdout, result.stderr)
        self.assertEqual(
            json.loads(result.stdout)["shipped_trackers"], ["github", "jira", "linear"]
        )


if __name__ == "__main__":
    unittest.main()
