"""Gridfinity 3x3 diagonal cradle bin for the Logitech MX Master 3.

Showcases the scan-to-pocket pipeline: the pocket is the mouse's real
outline (max cross-section of its bottom 19mm, extracted from a 3D
scan with outline_from_scan.py), rotated 43.9 degrees, the angle
minimizing its bounding square (120.6mm incl. clearance), so it fits
a 3x3 grid (123.1mm usable) instead of 4x3. A thumb scoop with a
hemispherical bottom leans 35 degrees toward the mouse so the thumb
slides down a smooth ramp under the thumb-rest wing.

Walls thin to ~1.2mm at the four diagonal contact points; fine for a
drawer bin. The rotation is computed below from the base outline, so
a regenerated outline only needs pasting once.

Fit note (print-verified): the outline is the MX Master 3 scan scaled
up a few percent (to 128.2x88.4mm), so an MX Master 3 / 3S sits in it
with ~3mm of easy slack per side.

Outline provenance: "Logitech Mx Master 3 3D Scan" by robomo
(printables.com/model/1149616), processed with:
    python3 outline_from_scan.py mxmaster3_scan.stl \
        --dims 128.2x88.4x50.8 --zmax 19
(For a snug MX Master 3 fit, use --dims 124.9x84.3x51 instead. The
angle comes from outline_from_scan.py --rotate-min-square.)

Print: upright, bottom on bed, no supports. PLA, 0.2mm layers.
"""

import math
import sys
from pathlib import Path

import cadquery as cq

# In your own project, copy gridfinity.py next to your script instead
# of this path shim (it only resolves the module inside this repo).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from gridfinity import GridfinityBin

# ============================================================
# PARAMETERS
# ============================================================
fit_clearance = 0.3     # mm - per-side fit clearance
easy_grab = 1.0         # mm - extra per-side room to drop in/out easily

angle_deg = 43.9        # rotation minimizing the outline's bounding square

well_d = 22.0           # mm - thumb scoop diameter
well_center_base = (42.0, 27.0)  # mm - over the wing, in base coords
well_pull = 5.0         # mm - pulled toward the bin center off the wall
well_tilt = 35.0        # deg from vertical, leaning toward the mouse

# Max cross-section of the mouse's bottom 19mm, mm, centered on the
# footprint bbox. Nose at +X, thumb wing at +Y. 52 points.
mouse_outline_base = [
    (-61.56, -23.06), (-64.02, -12.41), (-64.07, -7.76), (-63.61, -3.2),
    (-61.1, 4.55), (-52.59, 22.81), (-45.12, 34.43), (-40.35, 39.89),
    (-37.67, 41.82), (-34.96, 42.98), (-30.06, 43.96), (-22.86, 44.06),
    (-7.54, 43.03), (3.18, 41.39), (6.89, 39.76), (10.06, 36.88),
    (13.97, 29.4), (15.89, 27.05), (18.67, 25.38), (22.04, 24.8),
    (24.67, 20.91), (26.91, 19.01), (29.58, 18.02), (34.37, 17.92),
    (50.66, 21.07), (53.69, 20.55), (54.27, 21.6), (56.75, 21.62),
    (60.61, 19.31), (62.17, 17.4), (63.42, 14.54), (63.9, 8.65),
    (62.94, -3.02), (61.32, -12.48), (58.62, -23.66), (56.9, -28.39),
    (55.83, -30.05), (54.55, -30.87), (54.23, -31.97), (50.48, -34.12),
    (48.88, -34.62), (38.66, -36.49), (15.69, -38.27), (-0.95, -41.56),
    (-16.35, -43.73), (-26.5, -44.19), (-34.62, -43.59), (-40.31, -42.31),
    (-44.22, -40.9), (-51.19, -36.53), (-54.94, -33.12), (-58.56, -28.66),
]

# ============================================================
# DERIVED: rotate outline and well, re-center on the rotated bbox
# ============================================================
_a = math.radians(angle_deg)


def _rot(p):
    return (p[0] * math.cos(_a) - p[1] * math.sin(_a),
            p[0] * math.sin(_a) + p[1] * math.cos(_a))


_rotated = [_rot(p) for p in mouse_outline_base]
_xs = [p[0] for p in _rotated]
_ys = [p[1] for p in _rotated]
_shift = (-(min(_xs) + max(_xs)) / 2, -(min(_ys) + max(_ys)) / 2)
mouse_outline = [(x + _shift[0], y + _shift[1]) for x, y in _rotated]

_wx, _wy = _rot(well_center_base)
_wx, _wy = _wx + _shift[0], _wy + _shift[1]
_scale = 1 - well_pull / math.hypot(_wx, _wy)
well_center = (_wx * _scale, _wy * _scale)

# ============================================================
# MODEL
# ============================================================
bin = GridfinityBin(grid_x=3, grid_y=3, height_units=3,
                    stacking_lip=True)
bin.add_polygon_pocket(mouse_outline,
                       clearance=fit_clearance + easy_grab)
bin.add_cylinder_pocket(diameter=well_d, center=well_center,
                        tilt=well_tilt,
                        tilt_dir=(-well_center[0], -well_center[1]),
                        round_bottom=True)
result = bin.build()

# ============================================================
# EXPORT
# ============================================================
cq.exporters.export(result, "mx_master3_bin_3x3.stl",
                    tolerance=0.01, angularTolerance=0.1)
print(bin.summary())
print(f"Mouse rotated {angle_deg} deg; thumb scoop at "
      f"({well_center[0]:.1f}, {well_center[1]:.1f})")
