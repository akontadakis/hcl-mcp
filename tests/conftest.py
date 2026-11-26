"""Shared test set-up."""
import os

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(autouse=True)
def _atmosphere_cache_in_the_repo(monkeypatch):
    """Keep gensdaymtx's scattering tables out of the developer's home folder.

    `run_gensdaymtx` starts the program in a cache folder, by default under ~/hcl_work. A test
    must not write there. The repo root is where the suite has always left `atmos_data/`
    (git-ignored), so the live tests go on reusing the tables already computed there instead of
    spending minutes on a fresh set every session.
    """
    if "HCL_ATMOS_CACHE" not in os.environ:
        monkeypatch.setenv("HCL_ATMOS_CACHE", _REPO_ROOT)
