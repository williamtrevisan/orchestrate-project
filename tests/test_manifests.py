"""Structural gates for the marketplace and plugin manifests.

Derived from spec ACs OPP-01 (marketplace resolves without further arguments),
OPP-02 (the plugin carries the skill and its references) and OPP-06 (a version
is declared and incremented per release).
"""

import json
import os
import unittest

import paths


def load(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


class MarketplaceManifest(unittest.TestCase):
    def setUp(self):
        self.manifest = load(paths.MARKETPLACE_MANIFEST)

    def test_lives_at_the_documented_path(self):
        self.assertTrue(os.path.isfile(paths.MARKETPLACE_MANIFEST))

    def test_declares_identity_keys(self):
        for key in ("name", "description", "owner", "plugins"):
            self.assertIn(key, self.manifest)

    def test_declares_exactly_one_plugin(self):
        self.assertEqual(len(self.manifest["plugins"]), 1)

    def test_entry_carries_every_required_key(self):
        entry = self.manifest["plugins"][0]
        for key in ("name", "source", "description", "category", "version"):
            self.assertIn(key, entry)

    def test_source_resolves_on_disk(self):
        source = self.manifest["plugins"][0]["source"]
        self.assertTrue(os.path.isdir(os.path.join(paths.REPO_ROOT, source)))


class PluginManifest(unittest.TestCase):
    def setUp(self):
        self.manifest = load(paths.PLUGIN_MANIFEST)

    def test_lives_at_the_documented_path(self):
        self.assertTrue(os.path.isfile(paths.PLUGIN_MANIFEST))

    def test_name_matches_the_marketplace_entry(self):
        entry = load(paths.MARKETPLACE_MANIFEST)["plugins"][0]
        self.assertEqual(self.manifest["name"], entry["name"])

    def test_version_matches_the_marketplace_entry(self):
        entry = load(paths.MARKETPLACE_MANIFEST)["plugins"][0]
        self.assertEqual(self.manifest["version"], entry["version"])

    def test_declares_a_version(self):
        self.assertRegex(self.manifest["version"], r"^\d+\.\d+\.\d+$")

    def test_user_config_declares_only_machine_level_defaults(self):
        """Repository-scoped state belongs in .orchestrate-project.json, which
        is committed. A per-machine value must never stand in for it."""
        self.assertEqual(
            sorted(self.manifest["userConfig"]),
            ["compozy_pin", "default_tracker"],
        )

    def test_no_user_config_entry_is_marked_sensitive(self):
        """Credentials are never stored by the plugin; ambient CLI auth is read
        instead. A sensitive entry here would contradict that."""
        for entry in self.manifest["userConfig"].values():
            self.assertFalse(entry.get("sensitive", False))


class ComponentLayout(unittest.TestCase):
    def test_skill_directory_is_at_the_plugin_root(self):
        """Component directories live at the plugin root, never inside
        .claude-plugin/."""
        self.assertTrue(os.path.isdir(paths.SKILL_DIR))
        self.assertFalse(
            os.path.isdir(os.path.join(paths.PLUGIN_DIR, ".claude-plugin", "skills"))
        )

    def test_every_shipped_tracker_is_a_markdown_file(self):
        entries = sorted(os.listdir(paths.TRACKERS_DIR))
        self.assertTrue(entries)
        for name in entries:
            self.assertTrue(name.endswith(".md"), name)


if __name__ == "__main__":
    unittest.main()
