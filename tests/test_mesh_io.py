import pytest
import mesh_io


def test_load_mesh_valid(tmp_stl):
    tm = mesh_io.load_mesh(str(tmp_stl))
    assert len(tm.vertices) > 0
    assert len(tm.faces) > 0
    assert tm.is_watertight


def test_load_mesh_missing_file(tmp_path):
    with pytest.raises(ValueError, match="Failed to load STL"):
        mesh_io.load_mesh(str(tmp_path / "nope.stl"))


def test_load_mesh_empty_file(tmp_path):
    empty = tmp_path / "empty.stl"
    empty.write_bytes(b"")
    with pytest.raises(ValueError):
        mesh_io.load_mesh(str(empty))


def test_load_mesh_no_pyrender_import():
    """mesh_io must not pull in pyrender (it's the whole point of the split)."""
    import sys
    assert "pyrender" not in dir(mesh_io), "mesh_io should not reference pyrender"


def test_parse_bed_forms():
    assert mesh_io.parse_bed("A1") == (256, 256, 256)
    assert mesh_io.parse_bed("a1-mini") == (180, 180, 180)
    assert mesh_io.parse_bed("250x210x220") == (250.0, 210.0, 220.0)
    assert mesh_io.parse_bed("200") == (200.0, 200.0, 200.0)
    for bad in ("10x10", "250x-210x220", "inf", "nan", "0"):
        with pytest.raises(ValueError, match="printer name"):
            mesh_io.parse_bed(bad)


def test_bed_fit_allows_rotation_and_reports_overflow():
    bed = (250, 210, 220)
    # Usable area is 240 x 200 with the 5 mm margin.
    assert mesh_io.bed_fit((230, 190, 10), bed)[0]
    # 190 x 230 needs the 90 degree turn.
    assert mesh_io.bed_fit((190, 230, 10), bed)[0]
    fits, msg = mesh_io.bed_fit((245, 100, 10), bed)
    assert not fits and "245.0x100.0" in msg
    fits, msg = mesh_io.bed_fit((100, 100, 300), bed)
    assert not fits and "height 300.0" in msg


def test_estimate_mass_hollow_less_than_solid(tmp_stl):
    tm = mesh_io.load_mesh(str(tmp_stl))
    solid = abs(tm.volume) / 1000 * 1.24
    est = mesh_io.estimate_mass(tm)
    # A 10 mm cube is mostly skin: estimate sits between 15% and 100% solid.
    assert solid * 0.15 < est < solid
    assert mesh_io.estimate_mass(tm, infill=1.0) == pytest.approx(solid)
