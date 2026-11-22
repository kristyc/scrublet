"""Every test gets its own scratch store. The library also refuses the real store under pytest
(tests/test_guard.py), so this is a convenience, not the protection."""

import pytest

from scrublet_pii import terms


@pytest.fixture(autouse=True)
def scratch_store(tmp_path, monkeypatch):
    monkeypatch.setenv("SCRUBLET_HOME", str(tmp_path / "scratch-store"))
    monkeypatch.setattr(terms, "_production", False)
    terms._cache.clear()
