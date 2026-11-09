import cadquery as cq
import pytest

from mating import MatingError, check_mating, overlap


def _socket(gap):
    """A 20 mm block sitting in a U socket whose opening is `gap` wide."""
    sock = cq.Workplane("XY").box(gap + 10, 30, 5, centered=(True, True, False))
    for side in (-1, 1):
        sock = sock.union(
            cq.Workplane("XY", origin=(side * (gap / 2 + 2.5), 0, 5))
            .box(5, 30, 10, centered=(True, True, False)))
    return sock


BLOCK = cq.Workplane("XY", origin=(0, 0, 5)).box(20, 30, 8, centered=(True, True, False))


def test_overlap_zero_when_apart():
    assert overlap(BLOCK, BLOCK.translate((100, 0, 0))) == 0.0


def test_good_fit_passes():
    check_mating(_socket(20.6), BLOCK, clearance=0.3, axes=("x",))


def test_collision_fails():
    with pytest.raises(MatingError, match="collide"):
        check_mating(_socket(19.6), BLOCK, clearance=0.3, axes=("x",))


def test_loose_fit_fails():
    with pytest.raises(MatingError, match="no capture along"):
        check_mating(_socket(26.0), BLOCK, clearance=0.3, axes=("x",))


def test_unheld_axis_reported():
    # Nothing stops the block sliding along Y: asking for Y must fail.
    with pytest.raises(MatingError, match="y"):
        check_mating(_socket(20.6), BLOCK, clearance=0.3, axes=("y",))
