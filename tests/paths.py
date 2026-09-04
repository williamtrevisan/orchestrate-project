"""Shared path resolution for the structural test suite.

Every test resolves paths from this module rather than from its own location,
so moving a test file cannot silently change what it inspects.
"""

import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MARKETPLACE_MANIFEST = os.path.join(REPO_ROOT, ".claude-plugin", "marketplace.json")
PLUGIN_DIR = os.path.join(REPO_ROOT, "plugins", "orchestrate-project")
PLUGIN_MANIFEST = os.path.join(PLUGIN_DIR, ".claude-plugin", "plugin.json")
SKILL_DIR = os.path.join(PLUGIN_DIR, "skills", "orchestrate-project")
REFERENCES_DIR = os.path.join(SKILL_DIR, "references")
TRACKERS_DIR = os.path.join(REFERENCES_DIR, "trackers")
COMMANDS_DIR = os.path.join(PLUGIN_DIR, "commands")
INSTALLER = os.path.join(REPO_ROOT, "bin", "install.mjs")
PACKAGE_MANIFEST = os.path.join(REPO_ROOT, "package.json")


def shipped_markdown():
    """Every Markdown file that ships inside the plugin, as absolute paths."""
    found = []
    for dirpath, _dirnames, filenames in os.walk(PLUGIN_DIR):
        for name in sorted(filenames):
            if name.endswith(".md"):
                found.append(os.path.join(dirpath, name))
    return sorted(found)
