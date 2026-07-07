"""Gridfinity 3x2 cradle bin for the Orico D110 label printer.

The hand-rolled original lives at the repo root; this version rebuilds
it on the vendored gridfinity module in ~25 lines. The printer lies on
its 34mm side so the bin fits an IKEA Alex top drawer; it protrudes
above the rim for easy grabbing.

Print: upright, bottom on bed, no supports. PLA, 0.2mm layers.
"""

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
# Orico D110 label printer: 88 x 72 x 34 mm lying on its side
printer_l = 88.0        # mm - printer length (X)
printer_w = 72.0        # mm - printer width (Y)
printer_clearance = 0.3 # mm - per-side fit clearance
easy_grab = 1.0         # mm - extra per-side room for insertion/removal

# The D110 has very rounded corners on the grip/USB end (-X, ~12mm)
# and near-square corners on the label-exit end (+X, ~1mm).
pocket_r = (12.0, 1.0)  # mm - (-X end, +X end)

# ============================================================
# MODEL
# ============================================================
bin = GridfinityBin(grid_x=3, grid_y=2, height_units=3,
                    stacking_lip=True)
bin.add_pocket(
    length=printer_l + 2 * (printer_clearance + easy_grab),
    width=printer_w + 2 * (printer_clearance + easy_grab),
    corner_r=pocket_r,
)
result = bin.build()

# ============================================================
# EXPORT
# ============================================================
cq.exporters.export(result, "gridfinity_d110_bin.stl",
                    tolerance=0.01, angularTolerance=0.1)
print(bin.summary())
