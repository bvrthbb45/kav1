#!/usr/bin/env python3
"""Kav1 - cut a release: bump VERSION, roll the CHANGELOG, commit and tag.

  python tools/bump_version.py patch|minor|major [--dry-run]

Steps (all local - nothing is pushed):
  1. refuses to run with a dirty working tree or without entries under
     "## [Unreleased]" in CHANGELOG.md;
  2. computes the new semantic version from the VERSION file;
  3. turns "## [Unreleased]" into "## [X.Y.Z] - <today>" and opens a fresh,
     empty Unreleased section; refreshes the compare links at the bottom;
  4. updates AppVersion in kav1.iss;
  5. commits "Release vX.Y.Z" and creates the annotated tag vX.Y.Z.

Then publish with:  git push origin <branch> vX.Y.Z
See docs/VERSIONING.md for when to pick major / minor / patch.
"""

import argparse
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO_URL = "https://github.com/bvrthbb45/kav1"
SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def git(*args):
    return subprocess.run(
        ["git", "-C", str(ROOT)] + list(args),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def bump(version, part):
    m = SEMVER.match(version)
    if not m:
        sys.exit("VERSION must look like MAJOR.MINOR.PATCH, got %r" % version)
    major, minor, patch = (int(x) for x in m.groups())
    if part == "major":
        return "%d.0.0" % (major + 1)
    if part == "minor":
        return "%d.%d.0" % (major, minor + 1)
    return "%d.%d.%d" % (major, minor, patch + 1)


def main():
    ap = argparse.ArgumentParser(description="Bump version, roll changelog, tag.")
    ap.add_argument("part", choices=["major", "minor", "patch"])
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    old = (ROOT / "VERSION").read_text().strip()
    new = bump(old, args.part)
    tag = "v" + new

    if git("status", "--porcelain"):
        sys.exit("Working tree is not clean - commit or stash first.")
    if git("tag", "--list", tag):
        sys.exit("Tag %s already exists." % tag)

    cl_path = ROOT / "CHANGELOG.md"
    cl = cl_path.read_text(encoding="utf-8")
    m = re.search(
        r"^## \[Unreleased\]\s*\n(.*?)(?=^## \[|^\[Unreleased\]:)", cl, re.S | re.M
    )
    if not m or not re.search(r"^- ", m.group(1), re.M):
        sys.exit(
            "CHANGELOG.md has no entries under '## [Unreleased]' - nothing to release."
        )

    cl = cl.replace(
        "## [Unreleased]\n",
        "## [Unreleased]\n\n## [%s] - %s\n" % (new, date.today().isoformat()),
        1,
    )
    prev = "v" + old
    cl = re.sub(
        r"^\[Unreleased\]:.*$",
        "[Unreleased]: %s/compare/%s...HEAD\n[%s]: %s/compare/%s...%s"
        % (REPO_URL, tag, new, REPO_URL, prev, tag),
        cl,
        count=1,
        flags=re.M,
    )

    iss_path = ROOT / "kav1.iss"
    iss = iss_path.read_text(encoding="utf-8")
    iss_new = re.sub(r"^AppVersion=.*$", "AppVersion=" + new, iss, count=1, flags=re.M)

    print("%s -> %s (tag %s)" % (old, new, tag))
    if args.dry_run:
        print("dry run: no files changed, no commit, no tag.")
        return
    (ROOT / "VERSION").write_text(new + "\n")
    cl_path.write_text(cl, encoding="utf-8")
    iss_path.write_text(iss_new, encoding="utf-8")
    git("add", "VERSION", "CHANGELOG.md", "kav1.iss")
    git("commit", "-m", "Release %s" % tag)
    git("tag", "-a", tag, "-m", "Kav1 %s" % new)
    print(
        "Committed and tagged %s locally. Publish with:\n  git push origin HEAD %s"
        % (tag, tag)
    )


if __name__ == "__main__":
    main()
