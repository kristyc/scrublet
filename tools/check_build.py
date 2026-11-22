"""A local release check, no CI needed: build the sdist and the wheel, install each into a fresh
virtual environment, and use what was installed.

    python tools/check_build.py

Needs `uv` on PATH (or the `build` package) and network access for the build backend, as `pip
install` itself does. It exits 0 only when everything was built, installed and imported. A missing
builder is reported as an incomplete check (exit 2), never as a pass. Everything it makes lives in
one temp folder that is removed when it ends, however it ends.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
VERSION = PROJECT["version"]
# What a user's first import must show: the package, its alias, and that they are one module.
PROBE = (
    "import warnings; warnings.simplefilter('ignore'); import scrublet_pii, tacitkit; "
    "from scrublet_pii import terms, patterns, printed; from tacitkit import terms as old; "
    f"assert scrublet_pii.__version__ == {VERSION!r}, scrublet_pii.__version__; "
    "assert old is terms; "
    "assert 'pattern.card' in patterns.kinds('Card 4111 1111 1111 1111'); print('imports ok')"
)


def run(argv: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(argv, capture_output=True, text=True, check=False, **kwargs)


def builder(out: Path) -> list[str] | None:
    if shutil.which("uv"):
        return ["uv", "build", "--out-dir", str(out), str(ROOT)]
    if run([sys.executable, "-c", "import build"]).returncode == 0:
        return [sys.executable, "-m", "build", "--outdir", str(out), str(ROOT)]
    return None


def check_artifacts(sdist: Path, wheel: Path) -> None:
    with tarfile.open(sdist) as archive:
        names = {Path(n).name for n in archive.getnames()}
    missing = {"LICENSE", "NOTICE", "pyproject.toml"} - names
    assert not missing, f"sdist lacks {sorted(missing)}"
    with zipfile.ZipFile(wheel) as archive:
        meta = next(n for n in archive.namelist() if n.endswith("METADATA"))
        text = archive.read(meta).decode("utf-8")
        files = {Path(n).name for n in archive.namelist()}
    assert "License-Expression: Apache-2.0" in text, "wheel metadata lacks the licence expression"
    assert "Classifier: License ::" not in text, "licence declared twice"
    assert {"LICENSE", "NOTICE"} <= files, "wheel lacks the licence files"


def fresh_env(base: Path, name: str) -> Path:
    folder = base / name
    done = run([sys.executable, "-m", "venv", str(folder)])
    assert done.returncode == 0, f"venv failed: {done.stderr[-300:]}"
    return (
        folder
        / ("Scripts" if os.name == "nt" else "bin")
        / ("python.exe" if os.name == "nt" else "python")
    )


def install_and_use(python: Path, artifact: Path, label: str) -> None:
    done = run(
        [str(python), "-m", "pip", "install", "--no-deps", "--force-reinstall", str(artifact)]
    )
    assert done.returncode == 0, f"pip could not install the {label}:\n{done.stderr[-800:]}"
    used = run([str(python), "-I", "-c", PROBE])
    assert used.returncode == 0 and "imports ok" in used.stdout, f"{label}: {used.stderr[-600:]}"
    print(f"  {label}: built, installed in a fresh venv, imports ok")


def main() -> int:
    work = Path(tempfile.mkdtemp(prefix="scrublet-build-")).resolve()
    try:
        out = work / "dist"
        command = builder(out)
        if command is None:
            print(
                "INCOMPLETE: neither `uv` nor the `build` package is available; nothing checked."
            )
            return 2
        done = run(command)
        if done.returncode != 0:
            print("FAIL: the build failed:\n" + (done.stderr or done.stdout)[-1500:])
            return 1
        sdist, wheel = next(out.glob("*.tar.gz")), next(out.glob("*.whl"))
        assert VERSION in sdist.name and VERSION in wheel.name, (
            "artifact version differs from pyproject"
        )
        check_artifacts(sdist, wheel)
        print(f"built {sdist.name} and {wheel.name}; licence files and metadata are right")
        python = fresh_env(work, "env")
        install_and_use(python, wheel, "wheel")
        install_and_use(python, sdist, "sdist (builds from source)")
        print("OK")
        return 0
    except AssertionError as error:
        print(f"FAIL: {error}")
        return 1
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
