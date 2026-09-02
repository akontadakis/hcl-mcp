"""Tests for sensor_layout.py — pure geometry, no file I/O."""

import math

import pytest

from hcl_radiance.sensor_layout import (
    _centred_axis,
    work_plane_grid,
    eye_observer_points,
    dgp_views,
)


# ---------------------------------------------------------------------------
# _centred_axis
# ---------------------------------------------------------------------------

def test_centred_axis_single_cell_when_span_smaller_than_spacing():
    pts = _centred_axis(0.0, 1.0, 2.0)
    assert pts == [0.5]


def test_centred_axis_exact_2_cells():
    pts = _centred_axis(0.0, 4.0, 2.0)
    assert len(pts) == 2
    # symmetric about midpoint 2.0
    assert abs(pts[0] - 1.0) < 1e-9
    assert abs(pts[1] - 3.0) < 1e-9


def test_centred_axis_4m_spacing_2m():
    """4 m span at spacing=2.0 -> 2 points (int(4//2)=2)."""
    pts = _centred_axis(0.0, 4.0, 2.0)
    assert len(pts) == 2


# ---------------------------------------------------------------------------
# work_plane_grid
# ---------------------------------------------------------------------------

def test_grid_4x4_spacing2_produces_4_points():
    """4×4 m floor at spacing=2.0 → 4 points (2×2 grid)."""
    grid = work_plane_grid((0.0, 0.0), (4.0, 4.0), workplane_h=0.8, spacing=2.0)
    assert len(grid) == 4


def test_grid_all_rows_have_z_equal_workplane_h():
    grid = work_plane_grid((0.0, 0.0), (6.0, 5.0), workplane_h=0.8, spacing=1.0)
    for row in grid:
        assert row[2] == 0.8


def test_grid_all_rows_direction_is_up():
    grid = work_plane_grid((0.0, 0.0), (4.0, 3.0), workplane_h=0.8, spacing=0.5)
    for row in grid:
        assert row[3:] == [0, 0, 1]


def test_grid_points_inside_extent():
    # NB: this only pins the bbox lattice to its own extent -- tautological for a bbox grid, and it
    # says NOTHING about a concave plan. Real polygon containment is covered by
    # tests/test_geometry_import.py::test_derived_grid_is_clipped_to_a_concave_floor.
    fmin = (1.0, 2.0)
    fmax = (5.0, 6.0)
    grid = work_plane_grid(fmin, fmax, workplane_h=0.8, spacing=0.5)
    assert grid, "expected a non-empty lattice"
    for row in grid:
        x, y = row[0], row[1]
        assert fmin[0] <= x <= fmax[0], f"x={x} outside extent {fmin[0]}..{fmax[0]}"
        assert fmin[1] <= y <= fmax[1], f"y={y} outside extent {fmin[1]}..{fmax[1]}"


def test_grid_each_row_is_6_elements():
    grid = work_plane_grid((0.0, 0.0), (4.0, 3.0), workplane_h=0.8, spacing=1.0)
    for row in grid:
        assert len(row) == 6


# ---------------------------------------------------------------------------
# eye_observer_points
# ---------------------------------------------------------------------------

def test_observers_z_equals_eye_h():
    obs = eye_observer_points((0.0, 0.0), (4.0, 3.0), eye_h=1.2, spacing=2.0)
    for row in obs:
        assert row[2] == 1.2


def test_observers_dz_is_zero():
    obs = eye_observer_points((0.0, 0.0), (4.0, 3.0), eye_h=1.2, spacing=2.0)
    for row in obs:
        assert row[5] == 0


def test_observers_horizontal_direction_is_unit():
    obs = eye_observer_points((0.0, 0.0), (4.0, 3.0), eye_h=1.2,
                              toward=(1.0, 1.0), spacing=2.0)
    for row in obs:
        mag = math.hypot(row[3], row[4])
        assert abs(mag - 1.0) < 1e-6, f"dir magnitude {mag} != 1.0"


def test_observers_default_toward_is_negative_y():
    obs = eye_observer_points((0.0, 0.0), (4.0, 4.0), eye_h=1.2, spacing=4.0)
    # Single point, toward default (0, -1)
    assert len(obs) == 1
    assert abs(obs[0][3] - 0.0) < 1e-6
    assert abs(obs[0][4] - (-1.0)) < 1e-6


def test_observers_each_row_is_6_elements():
    obs = eye_observer_points((0.0, 0.0), (4.0, 3.0), eye_h=1.2, spacing=2.0)
    for row in obs:
        assert len(row) == 6


# ---------------------------------------------------------------------------
# dgp_views
# ---------------------------------------------------------------------------

def test_dgp_views_format():
    views = dgp_views([[2.0, 1.5, 1.2, 0, -1, 0]])
    assert len(views) == 1
    v = views[0]
    assert v.startswith("-vp 2.0 1.5 1.2 -vd 0 -1 0")
    assert "-vta -vh 180 -vv 180" in v


def test_dgp_views_count_matches_observers():
    obs = eye_observer_points((0.0, 0.0), (6.0, 4.0), eye_h=1.2, spacing=2.0)
    views = dgp_views(obs)
    assert len(views) == len(obs)


def test_dgp_views_each_has_fisheye_flags():
    obs = [[1.0, 2.0, 1.2, 0.0, -1.0, 0.0], [3.0, 2.0, 1.2, 0.0, -1.0, 0.0]]
    for v in dgp_views(obs):
        assert "-vta" in v
        assert "-vh 180" in v
        assert "-vv 180" in v
