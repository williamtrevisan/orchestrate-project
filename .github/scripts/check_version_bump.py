#!/usr/bin/env python3
"""Refuse a change to shipped plugin content that reuses the published version.

The marketplace serves a plugin by version, and an installation records the
version it resolved. When shipped files change under a version that has already
been published, that number stops identifying a single content: two machines can
both hold "0.4.4" and disagree about what it contains, and the mismatch is
invisible until someone reads a file that should be there and is not.

Observed 2026-09-07 in this repository: three pull requests merged in sequence
under 0.4.4, and a machine that had resolved the first of them reported itself
up to date while missing the other two.

The git plumbing lives in the workflow. This module is the decision, so it can
be tested without a repository.
"""

import json
import sys

#: Only content the marketplace actually ships. Tests, CI and docs outside the
#: plugin directory can change freely under the same version -- they are not
#: what an installation resolves.
SHIPPED_PREFIX = "plugins/"


def ships(path):
    return path.startswith(SHIPPED_PREFIX)


def verdict(changed_paths, base_version, head_version):
    """Return (ok, message).

    `base_version` is None when the plugin manifest does not exist on the base
    ref -- a plugin being added for the first time, which nothing has published
    yet and which therefore needs no bump.
    """
    shipped = sorted(p for p in changed_paths if ships(p))
    if not shipped:
        return True, "No shipped file changed; version may stay at %s." % head_version
    if base_version is None:
        return True, "Plugin is new at %s; nothing has published this version yet." % head_version
    if head_version != base_version:
        return True, "Shipped files changed and the version moved %s -> %s." % (base_version, head_version)

    listed = "\n".join("  %s" % p for p in shipped[:20])
    more = "\n  ... and %d more" % (len(shipped) - 20) if len(shipped) > 20 else ""
    return False, (
        "Shipped files changed while the version stayed at %s:\n%s%s\n\n"
        "Bump `version` in all three places that carry it -- "
        "plugins/orchestrate-project/.claude-plugin/plugin.json, the marketplace entry in "
        ".claude-plugin/marketplace.json, and package.json. Reusing a published version "
        "leaves two installations holding the same number and different content."
        % (base_version, listed, more)
    )


def read_version(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)["version"]
    except (FileNotFoundError, KeyError, ValueError):
        return None


def main(argv):
    if len(argv) != 3:
        print("usage: check_version_bump.py <changed-paths-file> <base-manifest-or-'-'>")
        return 2
    with open(argv[1], encoding="utf-8") as handle:
        changed = [line.strip() for line in handle if line.strip()]
    base_version = read_version(argv[2]) if argv[2] != "-" else None
    head_version = read_version("plugins/orchestrate-project/.claude-plugin/plugin.json")
    ok, message = verdict(changed, base_version, head_version)
    print(message)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
