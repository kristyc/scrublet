"""The package must build from its own source: v0.7.0 declared the licence twice (an SPDX
expression and a classifier), which current setuptools rejects, so `pip install git+...` failed."""

import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

import scrublet_pii

ROOT = Path(__file__).resolve().parents[1]
PROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]


def test_the_licence_is_declared_once_as_an_spdx_expression():
    assert isinstance(PROJECT["license"], str)
    assert not [c for c in PROJECT.get("classifiers", []) if c.startswith("License ::")]
    assert set(PROJECT["license-files"]) <= {p.name for p in ROOT.iterdir()}


def test_the_version_in_the_package_is_the_version_in_the_metadata():
    assert scrublet_pii.__version__ == PROJECT["version"]


def metadata_build(tmp_path, pyproject=None):
    """Run setuptools' own metadata step on a copy of the project; (return code, error text)."""
    copy = tmp_path / "project"
    shutil.copytree(
        ROOT,
        copy,
        ignore=shutil.ignore_patterns(".git", "__pycache__", ".*", "bench", "tests", "docs"),
    )
    if pyproject is not None:
        (copy / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    snippet = (
        "import os; os.makedirs('out'); "
        "from setuptools.build_meta import prepare_metadata_for_build_wheel as p; p('out')"
    )
    done = subprocess.run(
        [sys.executable, "-c", snippet], cwd=copy, capture_output=True, text=True, check=False
    )
    return done.returncode, done.stderr


def test_setuptools_accepts_the_metadata_so_pip_can_build_it(tmp_path):
    pytest.importorskip("setuptools")
    code, error = metadata_build(tmp_path)
    assert code == 0, error[-600:]


def test_the_check_itself_catches_the_v0_7_0_mistake(tmp_path):
    pytest.importorskip("setuptools")
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    classifier = '    "License :: OSI Approved :: Apache Software License",\n'
    broken = text.replace('    "Topic :: Security",\n', '    "Topic :: Security",\n' + classifier)
    assert broken != text
    code, error = metadata_build(tmp_path, broken)
    assert code != 0 and "License ::" in error
