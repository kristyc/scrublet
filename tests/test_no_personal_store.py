"""A personal word store must never enter this repository: its files are ignored and untracked,
and every word in the docs and examples is invented."""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GIT = shutil.which("git")


def git(*args):
    return subprocess.run([GIT, *args], cwd=ROOT, capture_output=True, text=True, check=False)


@pytest.mark.skipif(GIT is None or not (ROOT / ".git").exists(), reason="needs a git checkout")
@pytest.mark.parametrize(
    "path",
    [
        "terms.json",
        "scrublet/terms.json",
        "tacitkit/terms.json",
        "terms.json.lock",
        ".terms-abc.tmp",
        "migrated-from-tacitkit.json",
        "MOVED-TO-SCRUBLET.txt",
    ],
)
def test_store_files_are_ignored_by_git(path):
    assert git("check-ignore", "-q", path).returncode == 0, f"{path} is not ignored"


@pytest.mark.skipif(GIT is None or not (ROOT / ".git").exists(), reason="needs a git checkout")
def test_no_store_file_is_tracked():
    tracked = git("ls-files").stdout.splitlines()
    names = {Path(p).name for p in tracked}
    assert not names & {"terms.json", "terms.json.lock", "migrated-from-tacitkit.json"}
    assert not [p for p in tracked if re.match(r"(scrublet|tacitkit)/", p)]


def test_the_source_never_reads_a_store_outside_the_guarded_resolution():
    # one rule, one home: only terms.py names the store's file
    offenders = [
        p.name
        for p in (ROOT / "src").rglob("*.py")
        if "terms.json" in p.read_text(encoding="utf-8") and p.name != "terms.py"
    ]
    assert offenders == []
