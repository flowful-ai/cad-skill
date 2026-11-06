"""Cover plate for the hole left by a removed Cat Mate 4-way cat flap.

Sticks on with VHB tape. A hollow locating plug drops into the door
cut-out so the plate centres itself and the tape is not the only thing
resisting a sideways knock. Print two to close both faces of the door.

Print: front face down on the bed (smooth/textured plate finish shows),
plug pointing up, no supports. PLA or PETG, 0.2mm layers, brim against
corner lift. Check the fit with:
    python3 run_cadquery_model.py examples/cat_flap_cover.py --preview --strict --bed a1
"""

import cadquery as cq

# ============================================================
# PARAMETERS
# ============================================================
# Cat Mate 4-way flap (models 309 / 235). Frame measured on the door:
# 192 x 200 mm. Cut-out from the Cat Mate spec sheet: 165 x 174 mm.
frame_w = 192.0        # mm - old frame width, plate must hide its footprint
frame_h = 200.0        # mm - old frame height
cutout_w = 165.0       # mm - hole in the door, measure after removing the flap
cutout_h = 174.0       # mm

# Plate
tape_band_min = 20.0   # mm - flat land left around the plug for VHB tape
margin = 8.0           # mm - overlap past the old frame footprint, per side
plate_t = 3.0          # mm - plate thickness
corner_r = 10.0        # mm - outer corner radius
front_chamfer = 1.2    # mm - chamfer on the visible front edge (bed side)

# Locating plug (set plug_depth = 0 to drop it)
plug_clearance = 1.5   # mm - per side, hand-cut holes are never exact
plug_depth = 12.0      # mm - keep < half the door thickness if printing two
plug_wall = 2.4        # mm - 6 perimeters at 0.4 nozzle
plug_corner_r = 12.0   # mm - generous so it clears drilled hole corners

# Stiffening ribs inside the plug (stop the plate flexing when pushed)
rib_t = 2.0            # mm
rib_h = 8.0            # mm - above the plate back
ribs_x = 2             # ribs running along Y, spaced across X
ribs_y = 2             # ribs running along X, spaced across Y

# ============================================================
# DERIVED + CHECKS
# ============================================================
plate_w = frame_w + 2 * margin
plate_h = frame_h + 2 * margin
plug_w = cutout_w - 2 * plug_clearance
plug_h = cutout_h - 2 * plug_clearance
inner_w = plug_w - 2 * plug_wall
inner_h = plug_h - 2 * plug_wall

tape_band = min(plate_w - plug_w, plate_h - plug_h) / 2
assert cutout_w < frame_w and cutout_h < frame_h, "cut-out larger than frame"
assert plug_depth == 0 or tape_band >= tape_band_min, (
    f"only {tape_band:.1f} mm left for tape around the plug, raise margin")
assert rib_h <= plug_depth or plug_depth == 0, "ribs taller than plug"

# ============================================================
# MODEL  (Z=0 is the front face, on the bed)
# ============================================================
plate = (
    cq.Workplane("XY")
    .box(plate_w, plate_h, plate_t, centered=(True, True, False))
    .edges("|Z").fillet(corner_r)
    .faces("<Z").edges().chamfer(front_chamfer)
)

if plug_depth > 0:
    outer = (
        cq.Workplane("XY", origin=(0, 0, plate_t))
        .rect(plug_w, plug_h).extrude(plug_depth)
        .edges("|Z").fillet(plug_corner_r)
    )
    inner = (
        cq.Workplane("XY", origin=(0, 0, plate_t))
        .rect(inner_w, inner_h).extrude(plug_depth)
        .edges("|Z").fillet(plug_corner_r - plug_wall)
    )
    plate = plate.union(outer.cut(inner))

    for i in range(1, ribs_x + 1):
        x = -inner_w / 2 + i * inner_w / (ribs_x + 1)
        plate = plate.union(
            cq.Workplane("XY", origin=(x, 0, plate_t))
            .box(rib_t, inner_h + plug_wall, rib_h, centered=(True, True, False))
        )
    for j in range(1, ribs_y + 1):
        y = -inner_h / 2 + j * inner_h / (ribs_y + 1)
        plate = plate.union(
            cq.Workplane("XY", origin=(0, y, plate_t))
            .box(inner_w + plug_wall, rib_t, rib_h, centered=(True, True, False))
        )

result = plate

# ============================================================
# EXPORT
# ============================================================
bb = result.val().BoundingBox()
cq.exporters.export(result, "cat_flap_cover.stl",
                    tolerance=0.01, angularTolerance=0.1)
cq.exporters.export(result, "cat_flap_cover.step")
print(f"Plate {plate_w:.0f} x {plate_h:.0f} x {plate_t} mm, "
      f"plug {plug_w:.0f} x {plug_h:.0f} x {plug_depth} mm, "
      f"tape band {tape_band:.1f} mm, "
      f"bbox {bb.xlen:.1f} x {bb.ylen:.1f} x {bb.zlen:.1f}")
