#!/usr/bin/env python3
"""Print the CHANGELOG.md section of a version, for a GitHub release.
/ GitHub のリリース用に、CHANGELOG.md のあるバージョンの節を出力する。

    scripts/release_notes.py 1.1.0 > notes.md

Fails (exit 1) when / 次の場合は失敗する (exit 1):
  - the version differs from __version__ in gpu_monitor.py
    / バージョンが gpu_monitor.py の __version__ と違う
  - CHANGELOG.md has no "## [<version>] - <date>" section, or its date is
    still "Unreleased" / CHANGELOG.md に "## [<version>] - <日付>" が無い、
    または日付がまだ "Unreleased"
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def module_version():
    """__version__ from gpu_monitor.py, read without importing it
    (tkinter may be missing). / gpu_monitor.py の __version__ を import
    せずに読む（tkinter が無い環境もあるため）。"""
    m = re.search(r'^__version__ = "([^"]+)"',
                  (ROOT / "gpu_monitor.py").read_text(), re.M)
    return m.group(1) if m else None


def release_notes(version, changelog):
    """Return the body of the "## [version] - date" section.
    / "## [version] - 日付" の節の本文を返す。"""
    m = re.search(rf"^## \[{re.escape(version)}\] - (.+)$", changelog, re.M)
    if not m:
        raise ValueError(f"CHANGELOG.md has no section for {version}")
    if m.group(1).strip().lower() == "unreleased":
        raise ValueError(f"{version} is still marked Unreleased in "
                         "CHANGELOG.md; set the release date first")
    rest = changelog[m.end():]
    end = re.search(r"^## \[", rest, re.M)
    return (rest[:end.start()] if end else rest).strip() + "\n"


def main(argv):
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    version = argv[1].lstrip("v")
    if module_version() != version:
        print(f"error: tag {version} != __version__ {module_version()} "
              "in gpu_monitor.py", file=sys.stderr)
        return 1
    try:
        sys.stdout.write(release_notes(
            version, (ROOT / "CHANGELOG.md").read_text()))
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
