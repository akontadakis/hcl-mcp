import math
import pytest
from hcl_core.klems import (KLEMS_FULL_BINS, KLEMS_ANGLE_BASIS, KLEMS_BASIS_NAME,
                            klems_bin_count, klems_solid_angles)


def test_klems_full_is_145_bins():
    assert KLEMS_FULL_BINS == 145


def test_angle_basis_is_the_real_lbnl_full_basis():
    """NINE rings, taken from a genBSDF file -- not eight. A plausible-looking 8-ring
    reconstruction ending in one 28-patch 65-90 ring also sums to 145, while binning
    every grazing direction wrongly."""
    assert [n for *_r, n in KLEMS_ANGLE_BASIS] == [1, 8, 16, 20, 24, 24, 24, 16, 12]
    assert [lo for lo, *_r in KLEMS_ANGLE_BASIS] == [0, 5, 15, 25, 35, 45, 55, 65, 75]
    assert [up for _lo, up, *_r in KLEMS_ANGLE_BASIS] == [5, 15, 25, 35, 45, 55, 65, 75, 90]
    assert sum(n for *_r, n in KLEMS_ANGLE_BASIS) == 145


def test_basis_name_is_the_one_dctimestep_matches_on():
    """'Klems Full' alone is not recognised; dctimestep resolves by this exact name."""
    assert KLEMS_BASIS_NAME == "LBNL/Klems Full"


def test_bin_count_rejects_unknown_basis():
    assert klems_bin_count("Klems Full") == 145
    with pytest.raises(ValueError, match="Klems Quarter"):
        klems_bin_count("Klems Quarter")


def test_solid_angles_cover_the_hemisphere():
    omega = klems_solid_angles()
    assert len(omega) == 145
    assert math.isclose(sum(omega), 2 * math.pi, rel_tol=1e-9)
    assert all(w > 0 for w in omega)
