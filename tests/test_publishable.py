"""Nothing tenant-identifying may ship inside the plugin.

This is the gate that makes the repository safe to open, and safe to *keep*
open. Publishing is a one-way door: a private detail that reaches a public repo
has been cloned and indexed before anyone notices. So the rule is enforced on
every run rather than audited once.

Anything specific to a project - an Atlassian site, a cloud id, an organisation,
a repository, a real issue key - belongs in that project's own
`.orchestrate-project.json`, never in the shipped skill.
"""

import os
import re
import unittest

import paths

#: Tenant identifiers that must never appear in shipped files.
FORBIDDEN = {
    "atlassian site": re.compile(r"[a-z0-9-]+\.atlassian\.net", re.I),
    "cloud id / uuid": re.compile(
        r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I
    ),
    "github org/repo path": re.compile(
        r"github\.com/(?!<|\{|owner|your-org|acme)[A-Za-z0-9._-]+/[A-Za-z0-9._-]+"
    ),
    "bearer or api token": re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{20,}|Bearer\s+[A-Za-z0-9._-]{20,})"),
}

#: Placeholder forms every example must use instead of a real value.
NEUTRAL_EXAMPLES = ("acme", "example", "your-org", "<", "{")

#: Files whose own purpose is to name this plugin's home.
ALLOWED_SELF_REFERENCE = {"plugin.json", "marketplace.json", "README.md", "LICENSE"}


def shipped_files():
    found = []
    for dirpath, dirnames, filenames in os.walk(paths.PLUGIN_DIR):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for name in sorted(filenames):
            if name.endswith(".pyc"):
                continue
            found.append(os.path.join(dirpath, name))
    return sorted(found)


def read(path):
    with open(path, encoding="utf-8", errors="replace") as handle:
        return handle.read()


class NoTenantIdentifiers(unittest.TestCase):
    def test_no_shipped_file_carries_a_forbidden_identifier(self):
        offenders = []
        for path in shipped_files():
            name = os.path.basename(path)
            text = read(path)
            for label, pattern in FORBIDDEN.items():
                if label == "github org/repo path" and name in ALLOWED_SELF_REFERENCE:
                    continue
                for hit in pattern.findall(text):
                    hit = hit if isinstance(hit, str) else hit[0]
                    offenders.append(
                        f"{os.path.relpath(path, paths.REPO_ROOT)}: {label} -> {hit}"
                    )
        self.assertEqual(offenders, [], "\n".join(offenders))

    def test_no_dangling_decision_reference(self):
        """AD-NNN points at a decision log in the repository the skill was
        written in. A consumer cloning this plugin has no such log, so the
        reference resolves to nothing and the reader cannot check the claim."""
        offenders = []
        decisions = os.path.join(paths.SKILL_DIR, "references", "decisions.md")
        for path in shipped_files():
            if os.path.abspath(path) == os.path.abspath(decisions):
                continue
            for hit in set(re.findall(r"\bAD-\d{3}\b", read(path))):
                offenders.append(f"{os.path.relpath(path, paths.REPO_ROOT)}: {hit}")
        self.assertEqual(offenders, [], "\n".join(sorted(offenders)))


class ExamplesAreNeutral(unittest.TestCase):
    def test_tracker_examples_use_placeholder_identifiers(self):
        trackers = [
            os.path.join(paths.TRACKERS_DIR, n)
            for n in sorted(os.listdir(paths.TRACKERS_DIR))
            if n.endswith(".md")
        ]
        self.assertTrue(trackers)
        for path in trackers:
            text = read(path).lower()
            self.assertTrue(
                any(marker in text for marker in NEUTRAL_EXAMPLES),
                f"{os.path.basename(path)} shows no placeholder-form example",
            )


class ProjectConfigIsTheOnlyHome(unittest.TestCase):
    def test_every_tracker_document_points_at_repository_configuration(self):
        """A tracker's connection details are per-project. The document must say
        where they come from rather than carrying one project's values."""
        for name in sorted(os.listdir(paths.TRACKERS_DIR)):
            if not name.endswith(".md"):
                continue
            text = read(os.path.join(paths.TRACKERS_DIR, name))
            self.assertTrue(
                "tracker_config" in text,
                f"{name} does not name where its connection settings come from",
            )


class LicensingIsExplicit(unittest.TestCase):
    """A repository nobody can legally reuse is not open in any useful sense."""

    def test_a_license_file_exists(self):
        self.assertTrue(
            os.path.isfile(os.path.join(paths.REPO_ROOT, "LICENSE")),
            "no LICENSE at the repository root",
        )

    def test_a_readme_exists(self):
        self.assertTrue(
            os.path.isfile(os.path.join(paths.REPO_ROOT, "README.md")),
            "no README.md at the repository root",
        )


if __name__ == "__main__":
    unittest.main()
