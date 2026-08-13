"""Shared test setup: redirect /data before main.py is imported.

WHY THIS IS HERE AND NOT IN EACH TEST FILE
main.py creates its CSVs under /data at import time, which cannot exist on
macOS, so every suite has to redirect open/exists/makedirs first. Doing that
per-file worked one file at a time and broke the moment two ran together:
each module picked its OWN temp directory, but `main` is imported once, so
the app wrote into whichever directory was patched last while a suite's
helpers still read from its own. Six tests failed for that reason alone and
none of it was a real defect.

pytest imports conftest.py before any test module, so patching here happens
once, before main is imported, and every suite shares one directory.

The patches are deliberately NOT restored: main.py reads these paths again on
every request, not only at import.
"""
import builtins
import os
import sys
import tempfile

DATA = tempfile.mkdtemp(prefix="music-school-test-")

_open, _exists, _makedirs = builtins.open, os.path.exists, os.makedirs


def redir(p):
    """Map /data/... into the throwaway directory."""
    return DATA + str(p)[5:] if isinstance(p, (str, bytes)) and str(p).startswith("/data") else p


builtins.open = lambda f, *a, **k: _open(redir(f), *a, **k)
os.path.exists = lambda p: _exists(redir(p))
os.makedirs = lambda p, *a, **k: _makedirs(redir(p), *a, **k)

# Real open/exists, for suites that need to read a CSV back without going
# through the patched builtins.
raw_open = _open
raw_exists = _exists

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("SECRET_KEY", "test-secret-for-music-school-suite")

import main  # noqa: E402,F401  imported here so the patches are already live
