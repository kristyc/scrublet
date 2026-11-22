"""Deprecated name. This package is now scrublet_pii; for one version `import tacitkit` and
`from tacitkit import terms` keep working, and they give the very same module objects (so state,
caches and test patches are shared). Switch to `scrublet_pii`; this alias goes in v0.8.0."""

import importlib
import sys
import warnings

import scrublet_pii

warnings.warn(
    "tacitkit is now scrublet_pii; import scrublet_pii instead (this alias goes in v0.8.0)",
    DeprecationWarning,
    stacklevel=2,
)
for _name in ("terms", "printed", "patterns", "fold", "corpus", "bench", "models"):
    sys.modules[f"tacitkit.{_name}"] = importlib.import_module(f"scrublet_pii.{_name}")
sys.modules["tacitkit"] = scrublet_pii
