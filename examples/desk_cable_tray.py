"""Under-desk cable tray, built from identical segments.

A 400 mm tray does not fit a 256 mm bed, so the run is split into
segments that print one at a time and slide together: each segment
ends in a socket (two outboard cheek plates) that the plain end of the
next segment drops into. Every segment screws to the desk underside on
its own, so the joint only has to align, not carry load.

Print: upright (open side up), no supports. Screw tabs sit on 45 degree
gussets. PETG or PLA, 0.2mm layers, 3 walls.
    python3 run_cadquery_model.py examples/desk_cable_tray.py --preview --strict --bed a1
"""

import math

import cadquery as cq

# ============================================================
# PARAMETERS
# ============================================================
run_length = 400.0     # mm - total tray length wanted under the desk
max_segment = 220.0    # mm - longest segment body (A1 usable ~246 incl. socket)

inner_w = 90.0         # mm - channel width (power strip ~55 + cables)
inner_h = 60.0         # mm - channel depth
wall = 2.4             # mm - side walls (6 perimeters at 0.4)
floor_t = 2.4          # mm - channel floor

# Joint
socket_len = 18.0      # mm - how far the cheeks overlap the next segment
joint_clearance = 0.3  # mm - per side, between cheek and next wall
cheek_t = 2.4          # mm

# Desk mounting tabs (screws go up into the desk)
tab_w = 16.0           # mm - along the tray
tab_reach = 14.0       # mm - out from the wall
tab_t = 4.0            # mm
screw_d = 4.5          # mm - clearance for a 4 mm wood screw
head_d = 9.0           # mm - screw head + driver, bored up through the gusset
tabs_per_side = 2

# ============================================================
# DERIVED + CHECKS
# ============================================================
n_segments = math.ceil(run_length / max_segment)
seg_len = run_length / n_segments
outer_w = inner_w + 2 * wall
outer_h = inner_h + floor_t
cheek_gap = outer_w + 2 * joint_clearance   # inside of the socket

assert tab_reach <= outer_h - tab_t, "gusset would hit the bed"
assert seg_len > 2 * tab_w * tabs_per_side, "segment too short for its tabs"

# ============================================================
# MODEL  (Z=0 is the tray floor on the bed, X runs along the tray)
# ============================================================
body = (
    cq.Workplane("XY")
    .box(seg_len, outer_w, outer_h, centered=(False, True, False))
    .cut(
        cq.Workplane("XY", origin=(0, 0, floor_t))
        .box(seg_len, inner_w, outer_h, centered=(False, True, False))
    )
)

# Socket at +X: two cheek plates outside the walls. Over the overlap a
# full-height filler strip joins each cheek to its wall. The socket only
# locates sideways; the screws hold each segment up against the desk.
for side in (-1, 1):
    y = side * (cheek_gap / 2 + cheek_t / 2)
    cheek = cq.Workplane("XY", origin=(seg_len, y, 0)).box(
        socket_len * 2, cheek_t, outer_h, centered=(True, True, False))
    body = body.union(cheek)
# Bridge between body wall and cheek at the body end (fills the gap)
for side in (-1, 1):
    y = side * (outer_w / 2 + joint_clearance / 2)
    body = body.union(
        cq.Workplane("XY", origin=(seg_len - socket_len / 2, y, 0)).box(
            socket_len, joint_clearance + 0.01, outer_h, centered=(True, True, False)))

# Mounting tabs on gussets at the top of both walls
tab_xs = [seg_len * (i + 0.5) / tabs_per_side for i in range(tabs_per_side)]
for side in (-1, 1):
    for x in tab_xs:
        y_wall = side * outer_w / 2
        tab = cq.Workplane("XY", origin=(x, y_wall + side * tab_reach / 2, outer_h - tab_t)).box(
            tab_w, tab_reach, tab_t, centered=(True, True, False))
        # 45 degree gusset: triangle in the YZ plane, extruded along X
        gusset = (
            cq.Workplane("YZ", origin=(x - tab_w / 2, 0, 0))
            .polyline([
                (y_wall, outer_h - tab_t),
                (y_wall + side * tab_reach, outer_h - tab_t),
                (y_wall, outer_h - tab_t - tab_reach),
            ]).close()
            .extrude(tab_w)
        )
        hole_xy = (x, y_wall + side * tab_reach / 2)
        hole = cq.Workplane("XY", origin=(*hole_xy, 0)).circle(
            screw_d / 2).extrude(outer_h + 1)
        head_bore = cq.Workplane("XY", origin=(*hole_xy, -1)).circle(
            head_d / 2).extrude(outer_h - tab_t + 1)
        body = body.union(tab).union(gusset).cut(hole).cut(head_bore)

result = body

# ============================================================
# FIT CHECK  (two segments in assembled position, not exported)
# ============================================================
def overlap(a, b):
    return a.intersect(b).val().Volume()

next_seg = body.translate((seg_len, 0, 0))
nominal = overlap(body, next_seg)
assert nominal < 1e-3, f"segments collide when assembled ({nominal:.2f} mm3)"
# The socket must actually capture the next segment: a sideways shift
# just past the clearance has to hit a cheek.
shifted = overlap(body, next_seg.translate((0, joint_clearance + 0.1, 0)))
assert shifted > 1.0, "socket does not capture the next segment"

# ============================================================
# EXPORT
# ============================================================
bb = result.val().BoundingBox()
cq.exporters.export(result, "desk_cable_tray_segment.stl",
                    tolerance=0.01, angularTolerance=0.1)
print(f"{n_segments} segments of {seg_len:.0f} mm, "
      f"bbox {bb.xlen:.1f} x {bb.ylen:.1f} x {bb.zlen:.1f}")
