import math

import cadquery as cq
import pytest

import mesh_io
from gridfinity import (
    BASE_H,
    CLEARANCE,
    GRID_PITCH,
    GridfinityBin,
    GridfinityError,
    HEIGHT_UNIT,
)


def _mesh(workplane, tmp_path, name="part.stl"):
    stl = tmp_path / name
    cq.exporters.export(workplane, str(stl),
                        tolerance=0.01, angularTolerance=0.1)
    return mesh_io.load_mesh(str(stl))


def _volume(bin):
    """B-rep volume, no tessellation round-trip."""
    return bin.build().val().Volume()


def _assert_footprint(mesh, grid_x, grid_y):
    assert mesh.extents[0] == pytest.approx(
        grid_x * GRID_PITCH - 2 * CLEARANCE, abs=0.01)
    assert mesh.extents[1] == pytest.approx(
        grid_y * GRID_PITCH - 2 * CLEARANCE, abs=0.01)


# ------------------------------------------------------------
# Configuration matrix
# ------------------------------------------------------------

def test_minimal_bin_no_lip(tmp_path):
    """1x1, 2U, no lip: exact box height, flat top."""
    m = _mesh(GridfinityBin(1, 1, 2, stacking_lip=False).build(), tmp_path)
    assert m.is_watertight
    _assert_footprint(m, 1, 1)
    assert m.extents[2] == pytest.approx(2 * HEIGHT_UNIT, abs=0.01)


def test_bin_with_lip_magnets_screws(tmp_path):
    """2x1, 3U with lip and base holes."""
    bin = GridfinityBin(2, 1, 3, stacking_lip=True, magnets=True, screws=True)
    built = bin.build()
    m = _mesh(built, tmp_path)
    assert m.is_watertight
    _assert_footprint(m, 2, 1)
    # The lip rim tapers to an edge slightly below the theoretical total.
    assert 3 * HEIGHT_UNIT + 4.0 < m.extents[2] <= bin.total_h + 0.01
    # Holes remove material vs the same bin without them.
    assert built.val().Volume() < _volume(GridfinityBin(2, 1, 3,
                                                        stacking_lip=True))


def test_compartments_scoop_label(tmp_path):
    bin = GridfinityBin(2, 2, 4).add_compartments(
        cols=3, rows=2, scoop_r=6.0, label_tab=True)
    built = bin.build()
    m = _mesh(built, tmp_path)
    assert m.is_watertight
    _assert_footprint(m, 2, 2)
    # Scoop and label add material vs plain compartments.
    assert built.val().Volume() > _volume(
        GridfinityBin(2, 2, 4).add_compartments(cols=3, rows=2))


def test_polygon_pocket_with_clearance_and_cylinder_well(tmp_path):
    hexagon = [(25 * math.cos(a), 25 * math.sin(a))
               for a in [i * math.pi / 3 for i in range(6)]]
    bin = GridfinityBin(2, 2, 4).add_polygon_pocket(
        hexagon, depth=15.0, clearance=0.3)
    # Overlapping tilted scoop merges with the polygon cavity.
    bin.add_cylinder_pocket(diameter=14.0, center=(25.0, 0.0),
                            tilt=35.0, tilt_dir=(-1.0, 0.0),
                            round_bottom=True)
    m = _mesh(bin.build(), tmp_path)
    assert m.is_watertight
    _assert_footprint(m, 2, 2)


def test_oversized_cylinder_pocket_raises():
    bin = GridfinityBin(1, 1, 3).add_cylinder_pocket(diameter=41.0)
    with pytest.raises(GridfinityError, match="cylinder"):
        bin.build()


def test_cylinder_pocket_tilt_limits():
    bin = GridfinityBin(2, 2, 4).add_cylinder_pocket(
        diameter=14.0, tilt=60.0, tilt_dir=(1.0, 0.0))
    with pytest.raises(GridfinityError, match="tilt"):
        bin.build()
    with pytest.raises(GridfinityError, match="tilt_dir"):
        GridfinityBin(2, 2, 4).add_cylinder_pocket(diameter=14.0, tilt=30.0)


def test_finger_notch_removes_material(tmp_path):
    notched_bin = GridfinityBin(1, 1, 4).add_finger_notch(
        "+Y", width=15.0, offset=8.0)
    built = notched_bin.build()
    m = _mesh(built, tmp_path, "notched.stl")
    assert m.is_watertight
    assert built.val().Volume() < _volume(GridfinityBin(1, 1, 4))


def test_notch_offset_past_wall_raises():
    bin = GridfinityBin(1, 1, 4).add_finger_notch("+Y", width=15.0,
                                                  offset=15.0)
    with pytest.raises(GridfinityError, match="offset"):
        bin.build()


# ------------------------------------------------------------
# D110 cradle regression (known-good published bin)
# ------------------------------------------------------------

def test_d110_regression(tmp_path):
    """Rebuild the published D110 cradle; dimensions must match."""
    bin = GridfinityBin(3, 2, 3, stacking_lip=True)
    bin.add_pocket(88.6, 72.6, corner_r=(12.0, 1.0))
    assert bin.outer_w == pytest.approx(125.5)
    assert bin.outer_d == pytest.approx(83.5)
    assert bin.total_h == pytest.approx(25.75)
    assert bin.floor_z == pytest.approx(6.75)
    assert bin.max_depth == pytest.approx(19.0)

    m = _mesh(bin.build(), tmp_path)
    assert m.is_watertight
    assert m.extents[0] == pytest.approx(125.5, abs=0.01)
    assert m.extents[1] == pytest.approx(83.5, abs=0.01)
    # Rim tapers to an edge just below total_h (chamfer meets lip cut).
    assert m.extents[2] == pytest.approx(25.45, abs=0.05)
    # Volume within 2% of the reference geometry.
    assert m.volume == pytest.approx(123785, rel=0.02)


# ------------------------------------------------------------
# Validation errors
# ------------------------------------------------------------

def test_oversized_pocket_raises():
    bin = GridfinityBin(1, 1, 3).add_pocket(45.0, 20.0)
    with pytest.raises(GridfinityError, match="outer wall"):
        bin.build()


def test_too_deep_pocket_raises():
    bin = GridfinityBin(3, 2, 3).add_pocket(50.0, 40.0, depth=50.0)
    with pytest.raises(GridfinityError, match="depth"):
        bin.build()


def test_thin_divider_raises():
    bin = GridfinityBin(2, 2, 3).add_compartments(cols=2, rows=2, wall_t=0.8)
    with pytest.raises(GridfinityError, match="wall_t"):
        bin.build()


def test_too_many_compartments_raises():
    bin = GridfinityBin(1, 1, 3).add_compartments(cols=8, rows=1)
    with pytest.raises(GridfinityError, match="compartments"):
        bin.build()


def test_compartments_only_once():
    bin = GridfinityBin(2, 2, 3).add_compartments(cols=2, rows=2)
    with pytest.raises(GridfinityError, match="once"):
        bin.add_compartments(cols=3, rows=1)


def test_screws_need_thick_floor():
    bin = GridfinityBin(1, 1, 3, screws=True, floor_t=0.8)
    with pytest.raises(GridfinityError, match="screw"):
        bin.build()


def test_bad_notch_side_raises():
    bin = GridfinityBin(1, 1, 3).add_finger_notch("up", width=10.0)
    with pytest.raises(GridfinityError, match="side"):
        bin.build()


def test_pocket_radii_exceed_size_raises():
    bin = GridfinityBin(3, 2, 3).add_pocket(30.0, 30.0, corner_r=20.0)
    with pytest.raises(GridfinityError, match="radii"):
        bin.build()


def test_polygon_needs_three_points():
    bin = GridfinityBin(1, 1, 3).add_polygon_pocket([(0, 0), (10, 0)])
    with pytest.raises(GridfinityError, match="points"):
        bin.build()


def test_zero_grid_raises():
    with pytest.raises(GridfinityError, match="grid"):
        GridfinityBin(0, 1, 3).build()
