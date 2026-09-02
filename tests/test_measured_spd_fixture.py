"""Regression guard for a LOCAL measured-SPD fixture, when one is present.

This test is **development-only**. The fixture it reads is deliberately **not tracked**:
the measured spectra it holds are not distributed with this toolkit. When the directory
is absent — which is the case in any published checkout — the whole module skips.

The always-on counterpart is `test_alpha_opic_public_illuminants.py`, which pins the same
α-opic / spectral-metric code against public CIE illuminants and runs everywhere.

Where the fixture lives: `$HCL_MEASURED_SPD_DIR`, else `tests/fixtures/measured-spd-local/`.
It must contain `measured-spd/wavelengths.txt`, `measured-spd/<ORIENT>_MAY_<day>_<hour>.txt`
and `derived/measured_spd_alpha_opic.csv`.

Only **scale-invariant** metrics are checked, because the SPD files in this export are
peak-normalised (max == 1.0). That is a property of the export, not of the source readings.
"""
import csv
import os

import pytest

from hcl_core.alpha_opic import alpha_opic_from_spd as ao_exact
from hcl_core.spectral_metrics import mel_der, mel_photopic_ratio

HERE = os.path.dirname(__file__)
CASE = os.environ.get("HCL_MEASURED_SPD_DIR",
                      os.path.join(HERE, "fixtures", "measured-spd-local"))
SPD_DIR = os.path.join(CASE, "measured-spd")
GOLDEN = os.path.join(CASE, "derived", "measured_spd_alpha_opic.csv")

_PRESENT = os.path.isfile(os.path.join(SPD_DIR, "wavelengths.txt")) and os.path.isfile(GOLDEN)

pytestmark = pytest.mark.skipif(
    not _PRESENT,
    reason="local measured-SPD fixture not present (set HCL_MEASURED_SPD_DIR to enable)")

_WLS = ([int(float(x)) for x in open(os.path.join(SPD_DIR, "wavelengths.txt")) if x.strip()]
        if _PRESENT else [])


def _pairs(orientation, day, hour):
    fname = f"{orientation}_MAY_{day}_{hour}.txt"
    vals = [float(x) for x in open(os.path.join(SPD_DIR, fname)) if x.strip()]
    return list(zip(_WLS, vals))


def _rows():
    if not _PRESENT:
        return []
    with open(GOLDEN) as fh:
        return list(csv.DictReader(fh))


def test_grid_is_cie_s026_aligned():
    assert _WLS[0] == 380 and _WLS[-1] == 780 and len(_WLS) == 401


def test_fixture_row_count():
    assert len(_rows()) == 188


@pytest.mark.parametrize("row", _rows(), ids=lambda r: f"{r['orientation']}{r['day']}_{r['hour']}")
def test_alpha_opic_matches_golden(row):
    pairs = _pairs(row["orientation"], row["day"], row["hour"])
    assert len(pairs) == 401
    assert mel_der(pairs) == pytest.approx(float(row["mel_der"]), abs=1e-4)
    assert mel_photopic_ratio(pairs) == pytest.approx(float(row["mel_photopic_ratio"]), abs=1e-4)
    ao = ao_exact(pairs)
    for name in ("melanopic", "s_cone", "m_cone", "l_cone", "rhodopic"):
        assert ao[name]["ELR"] == pytest.approx(float(row[f"{name}_ELR"]), abs=1e-3)
