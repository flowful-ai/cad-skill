"""Gridfinity bin generator for CadQuery.

Vendored module: copy this file next to your model script and use

    from gridfinity import GridfinityBin

    bin = GridfinityBin(grid_x=3, grid_y=2, height_units=3,
                        stacking_lip=True, magnets=True)
    bin.add_pocket(length=88.6, width=72.6, corner_r=(12.0, 1.0))
    result = bin.build()
    cq.exporters.export(result, "my_bin.stl", tolerance=0.01,
                        angularTolerance=0.1)

Spec sources: gridfinity.xyz/specification and
github.com/gridfinity-unofficial/specification (42x42x7 grid, 41.5mm
bin footprint, 6x2mm magnets, M3 screws, holes on a 26mm square).
Base profile heights (0.8 / 1.8 / 2.15) match the bins shipped from
this repo and print-verified on standard baseplates.

Geometry conventions:
- Bottom of the bin at Z=0, ready for `.faces("<Z")` as the print bed.
- The stacking lip mirrors the base profile (adds 4.75mm on top of the
  nominal height) with square lofted corners; mating bases have rounded
  corners, so stacking clearance is preserved.
- Interior content (pockets, dividers, labels) tops out at the nominal
  height; the lip cut opens everything above it.
"""

import cadquery as cq

# ============================================================
# SPEC CONSTANTS (mm) - do not edit, these define compatibility
# ============================================================
GRID_PITCH = 42.0        # cell pitch
CLEARANCE = 0.25         # per side -> 41.5mm footprint per cell
HEIGHT_UNIT = 7.0        # one height unit
TAPER_1 = 0.8            # base profile: bottom 45-degree taper
RISER = 1.8              # base profile: vertical riser
TAPER_2 = 2.15           # base profile: top 45-degree taper
BASE_H = TAPER_1 + RISER + TAPER_2   # 4.75
CORNER_R = 3.75          # body corner radius (spec 4.0 minus clearance)
MAGNET_D = 6.5           # bore for 6x2mm magnets
MAGNET_DEPTH = 2.4
SCREW_D = 3.0            # M3 thread-forming
SCREW_DEPTH = 6.0
HOLE_SPACING = 26.0      # magnet/screw centers, square per cell
MIN_WALL = 1.2           # FDM minimum wall
DEFAULT_FLOOR = 2.0      # solid floor above the base profile
TOP_CHAMFER = 0.6        # rim edge chamfer

_INSET_BOT = TAPER_1 + TAPER_2   # 2.95 - footprint inset at the very bottom
_INSET_MID = TAPER_2             # 2.15 - inset at the riser
_EPS = 0.01


class GridfinityError(ValueError):
    """Raised when a bin configuration cannot produce valid geometry."""


def _corner_radii(corner_r):
    """Normalize scalar / 2-tuple / 4-tuple corner radii.

    Order: (+X+Y, -X+Y, -X-Y, +X-Y). A 2-tuple is (-X end, +X end),
    applied to both corners of that end.
    """
    if isinstance(corner_r, (int, float)):
        return (corner_r,) * 4
    if len(corner_r) == 2:
        r_minus, r_plus = corner_r
        return (r_plus, r_minus, r_minus, r_plus)
    if len(corner_r) == 4:
        return tuple(corner_r)
    raise GridfinityError("corner_r must be a number, 2-tuple, or 4-tuple")


def _rounded_rect(workplane, length, width, radii, center=(0.0, 0.0)):
    """Draw a closed rounded-rect wire with per-corner radii on `workplane`.

    `radii` order: (+X+Y, -X+Y, -X-Y, +X-Y). A radius of 0 gives a
    sharp corner.
    """
    ra, rb, rc, rd = radii
    hl, hw = length / 2, width / 2
    cx, cy = center

    wp = workplane.moveTo(cx - hl + rb, cy + hw)
    wp = wp.lineTo(cx + hl - ra, cy + hw)
    if ra > 0:
        wp = wp.radiusArc((cx + hl, cy + hw - ra), ra)
    wp = wp.lineTo(cx + hl, cy - hw + rd)
    if rd > 0:
        wp = wp.radiusArc((cx + hl - rd, cy - hw), rd)
    wp = wp.lineTo(cx - hl + rc, cy - hw)
    if rc > 0:
        wp = wp.radiusArc((cx - hl, cy - hw + rc), rc)
    wp = wp.lineTo(cx - hl, cy + hw - rb)
    if rb > 0:
        wp = wp.radiusArc((cx - hl + rb, cy + hw), rb)
    return wp.close()


class GridfinityBin:
    """Builder for a spec-compatible Gridfinity bin.

    Create the bin, add features, then call `build()` to get a
    `cq.Workplane` with the bottom at Z=0.
    """

    def __init__(self, grid_x, grid_y, height_units,
                 stacking_lip=True, magnets=False, screws=False,
                 floor_t=DEFAULT_FLOOR, corner_r=CORNER_R,
                 top_chamfer=TOP_CHAMFER):
        self.grid_x = grid_x
        self.grid_y = grid_y
        self.height_units = height_units
        self.stacking_lip = stacking_lip
        self.magnets = magnets
        self.screws = screws
        self.floor_t = floor_t
        self.corner_r = corner_r
        self.top_chamfer = top_chamfer
        self._pockets = []
        self._polygon_pockets = []
        self._compartments = None
        self._notches = []

    # ------------------------------------------------------------
    # Derived dimensions
    # ------------------------------------------------------------
    @property
    def outer_w(self):
        return self.grid_x * GRID_PITCH - 2 * CLEARANCE

    @property
    def outer_d(self):
        return self.grid_y * GRID_PITCH - 2 * CLEARANCE

    @property
    def nominal_h(self):
        return self.height_units * HEIGHT_UNIT

    @property
    def total_h(self):
        return self.nominal_h + (BASE_H if self.stacking_lip else 0)

    @property
    def floor_z(self):
        """Z of the interior floor: base profile plus solid floor."""
        return BASE_H + self.floor_t

    @property
    def max_depth(self):
        """Deepest cavity possible from the top of the bin."""
        return self.total_h - self.floor_z

    # ------------------------------------------------------------
    # Features
    # ------------------------------------------------------------
    def add_pocket(self, length, width, depth=None, corner_r=2.0,
                   center=(0.0, 0.0)):
        """Rounded-rect cavity cut from the top rim down `depth` mm.

        `corner_r`: scalar, (-X end, +X end) 2-tuple, or 4-tuple
        (+X+Y, -X+Y, -X-Y, +X-Y). `depth=None` reaches the floor.
        """
        self._pockets.append({
            "length": length, "width": width, "depth": depth,
            "radii": _corner_radii(corner_r), "center": center,
        })
        return self

    def add_polygon_pocket(self, points, depth=None, clearance=0.0):
        """Cavity with an arbitrary closed outline (list of (x, y) mm).

        `clearance` offsets the outline outward, e.g. to add fit
        clearance around a traced object. `depth=None` reaches the floor.
        """
        self._polygon_pockets.append({
            "points": list(points), "depth": depth, "clearance": clearance,
        })
        return self

    def add_compartments(self, cols=1, rows=1, wall_t=MIN_WALL,
                         scoop_r=0.0, label_tab=False, label_d=12.0):
        """Classic divided storage interior: cols x rows compartments.

        Optional `scoop_r` rounds the front (-Y) floor edge of every
        compartment; `label_tab` adds a 45-degree label shelf along the
        back (+Y) of every row, `label_d` mm deep.
        """
        self._compartments = {
            "cols": cols, "rows": rows, "wall_t": wall_t,
            "scoop_r": scoop_r, "label_tab": label_tab, "label_d": label_d,
        }
        return self

    def add_finger_notch(self, side="+X", width=20.0, depth=None):
        """U-shaped scallop cut into one side wall from the top rim.

        `side` is one of "+X", "-X", "+Y", "-Y". `depth` defaults to
        half the bin height, measured from the top rim.
        """
        self._notches.append({"side": side, "width": width, "depth": depth})
        return self

    # ------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------
    def _validate(self):
        if self.grid_x < 1 or self.grid_y < 1:
            raise GridfinityError("grid_x and grid_y must be >= 1")
        if self.height_units < 1:
            raise GridfinityError("height_units must be >= 1")
        if self.floor_t < 0.6:
            raise GridfinityError("floor_t must be >= 0.6mm")
        if self.nominal_h <= self.floor_z:
            raise GridfinityError(
                f"bin too short: nominal height {self.nominal_h}mm does not "
                f"clear the floor at {self.floor_z}mm; increase height_units")
        base_sketch_r = self.corner_r - _INSET_BOT
        if base_sketch_r < 0.4:
            raise GridfinityError(
                f"corner_r {self.corner_r}mm too small; must be >= "
                f"{_INSET_BOT + 0.4}mm so the base corners stay printable")
        if self.screws and self.floor_z < SCREW_DEPTH + 0.6:
            raise GridfinityError(
                f"screw holes are {SCREW_DEPTH}mm deep; floor_t must be >= "
                f"{SCREW_DEPTH + 0.6 - BASE_H:.2f}mm to keep a printable "
                f"membrane above them")

        for p in self._pockets:
            self._check_depth(p["depth"], "pocket")
            cx, cy = p["center"]
            if (abs(cx) + p["length"] / 2 > self.outer_w / 2 - MIN_WALL or
                    abs(cy) + p["width"] / 2 > self.outer_d / 2 - MIN_WALL):
                raise GridfinityError(
                    f"pocket {p['length']}x{p['width']}mm at {p['center']} "
                    f"leaves less than {MIN_WALL}mm of outer wall "
                    f"(interior is {self.outer_w - 2 * MIN_WALL:.1f}x"
                    f"{self.outer_d - 2 * MIN_WALL:.1f}mm)")
            ra, rb, rc, rd = p["radii"]
            if (ra + rb > p["length"] or rc + rd > p["length"] or
                    rb + rc > p["width"] or ra + rd > p["width"]):
                raise GridfinityError("pocket corner radii exceed pocket size")

        for p in self._polygon_pockets:
            if len(p["points"]) < 3:
                raise GridfinityError("polygon pocket needs >= 3 points")
            self._check_depth(p["depth"], "polygon pocket")
            xs = [pt[0] for pt in p["points"]]
            ys = [pt[1] for pt in p["points"]]
            grow = p["clearance"]
            if (max(map(abs, xs)) + grow > self.outer_w / 2 - MIN_WALL or
                    max(map(abs, ys)) + grow > self.outer_d / 2 - MIN_WALL):
                raise GridfinityError(
                    "polygon pocket (plus clearance) leaves less than "
                    f"{MIN_WALL}mm of outer wall")

        c = self._compartments
        if c:
            if c["wall_t"] < MIN_WALL:
                raise GridfinityError(f"divider wall_t must be >= {MIN_WALL}mm")
            comp_w, comp_d = self._compartment_size()
            if comp_w < 5 or comp_d < 5:
                raise GridfinityError(
                    f"compartments are {comp_w:.1f}x{comp_d:.1f}mm; "
                    "reduce cols/rows or wall_t (5mm minimum)")
            if c["scoop_r"] > min(comp_d, self.nominal_h - self.floor_z):
                raise GridfinityError("scoop_r too large for the compartment")
            if c["label_tab"] and c["label_d"] > min(
                    comp_d, self.nominal_h - self.floor_z):
                raise GridfinityError("label_d too large for the compartment")

        for n in self._notches:
            if n["side"] not in ("+X", "-X", "+Y", "-Y"):
                raise GridfinityError('notch side must be "+X", "-X", "+Y" or "-Y"')
            if n["width"] < 2:
                raise GridfinityError("notch width must be >= 2mm")
            depth = n["depth"] if n["depth"] is not None else self.total_h / 2
            if depth < n["width"] / 2:
                raise GridfinityError("notch depth must be >= width/2")
            self._check_depth(depth, "finger notch")

    def _check_depth(self, depth, what):
        if depth is not None and depth > self.max_depth + _EPS:
            raise GridfinityError(
                f"{what} depth {depth}mm exceeds max {self.max_depth:.2f}mm "
                f"({self.floor_t}mm floor above the {BASE_H}mm base)")

    def _compartment_size(self):
        c = self._compartments
        interior_w = self.outer_w - 2 * c["wall_t"]
        interior_d = self.outer_d - 2 * c["wall_t"]
        comp_w = (interior_w - (c["cols"] - 1) * c["wall_t"]) / c["cols"]
        comp_d = (interior_d - (c["rows"] - 1) * c["wall_t"]) / c["rows"]
        return comp_w, comp_d

    # ------------------------------------------------------------
    # Geometry
    # ------------------------------------------------------------
    def build(self):
        """Validate and build; returns a cq.Workplane, bottom at Z=0."""
        self._validate()

        solid = self._base_cells().union(self._body())
        if self.stacking_lip:
            solid = solid.cut(self._lip_cut())

        for p in self._pockets:
            solid = solid.cut(self._pocket_cut(p))
        for p in self._polygon_pockets:
            solid = solid.cut(self._polygon_cut(p))
        if self._compartments:
            solid = self._apply_compartments(solid)
        for n in self._notches:
            solid = solid.cut(self._notch_cut(n))
        if self.magnets or self.screws:
            solid = self._cut_base_holes(solid)

        return solid.clean()

    def _cell_centers(self):
        return [((ix - (self.grid_x - 1) / 2) * GRID_PITCH,
                 (iy - (self.grid_y - 1) / 2) * GRID_PITCH)
                for ix in range(self.grid_x) for iy in range(self.grid_y)]

    def _base_cells(self):
        """Per-cell base profile: taper, riser, taper (45 degrees).

        The sketch fillet starts at corner_r - 2.95 so the corner radius
        grows through the tapers to exactly corner_r at the top, flowing
        into the body fillet with no step (spec radii 0.8 / 1.6 / 3.75).
        """
        cell_size = GRID_PITCH - 2 * CLEARANCE
        cell_bot = cell_size - 2 * _INSET_BOT
        sketch_r = self.corner_r - _INSET_BOT

        base = None
        for cx, cy in self._cell_centers():
            cell = (
                cq.Workplane("XY")
                .transformed(offset=(cx, cy, 0))
                .sketch().rect(cell_bot, cell_bot)
                .vertices().fillet(sketch_r).finalize()
                .extrude(TAPER_1, taper=-45)
            )
            cell = cell.faces(">Z").wires().toPending().extrude(RISER)
            cell = (cell.faces(">Z").wires().toPending()
                    .extrude(TAPER_2, taper=-45))
            base = cell if base is None else base.union(cell)
        return base

    def _body(self):
        return (
            cq.Workplane("XY")
            .transformed(offset=(0, 0, BASE_H))
            .box(self.outer_w, self.outer_d, self.total_h - BASE_H,
                 centered=(True, True, False))
            .edges("|Z").fillet(self.corner_r)
            .edges(">Z").chamfer(self.top_chamfer)
        )

    def _lip_cut(self):
        """Stacking lip: the mirrored base profile lofted around the rim."""
        w, d = self.outer_w, self.outer_d
        return (
            cq.Workplane("XY")
            .transformed(offset=(0, 0, self.nominal_h))
            .rect(w - 2 * _INSET_BOT, d - 2 * _INSET_BOT)
            .workplane(offset=TAPER_1)
            .rect(w - 2 * _INSET_MID, d - 2 * _INSET_MID)
            .workplane(offset=RISER)
            .rect(w - 2 * _INSET_MID, d - 2 * _INSET_MID)
            .workplane(offset=TAPER_2)
            .rect(w, d)
            .loft(ruled=True)
        )

    def _pocket_cut(self, p):
        depth = p["depth"] if p["depth"] is not None else self.max_depth
        z0 = self.total_h - depth
        wp = cq.Workplane("XY").workplane(offset=z0)
        wire = _rounded_rect(wp, p["length"], p["width"], p["radii"],
                             p["center"])
        return wire.extrude(self.total_h - z0 + 1)

    def _polygon_cut(self, p):
        depth = p["depth"] if p["depth"] is not None else self.max_depth
        z0 = self.total_h - depth
        wp = (cq.Workplane("XY").workplane(offset=z0)
              .polyline(p["points"]).close())
        if p["clearance"] > 0:
            wp = wp.offset2D(p["clearance"])
        return wp.extrude(self.total_h - z0 + 1)

    def _apply_compartments(self, solid):
        c = self._compartments
        comp_w, comp_d = self._compartment_size()
        interior_w = self.outer_w - 2 * c["wall_t"]
        interior_d = self.outer_d - 2 * c["wall_t"]
        pocket_r = max(0.5, self.corner_r - c["wall_t"])

        for col in range(c["cols"]):
            for row in range(c["rows"]):
                cx = -interior_w / 2 + col * (comp_w + c["wall_t"]) + comp_w / 2
                cy = -interior_d / 2 + row * (comp_d + c["wall_t"]) + comp_d / 2
                wp = cq.Workplane("XY").workplane(offset=self.floor_z)
                cut = _rounded_rect(wp, comp_w, comp_d, (pocket_r,) * 4,
                                    (cx, cy)).extrude(
                    self.total_h - self.floor_z + 1)
                solid = solid.cut(cut)
                if c["scoop_r"] > 0:
                    solid = solid.union(
                        self._scoop(cx, cy - comp_d / 2, comp_w, c["scoop_r"]))

        if c["label_tab"]:
            for row in range(c["rows"]):
                y_back = (-interior_d / 2 + row * (comp_d + c["wall_t"])
                          + comp_d)
                solid = solid.union(
                    self._label_shelf(y_back, interior_w, c["label_d"]))
        return solid

    def _scoop(self, cx, y_front, span, r):
        """Concave quarter-round ramp along a compartment's front floor edge."""
        block = (
            cq.Workplane("XY")
            .box(span, r, r, centered=(True, False, False))
            .translate((cx, y_front, self.floor_z))
        )
        cyl = cq.Solid.makeCylinder(
            r, span,
            cq.Vector(cx - span / 2, y_front + r, self.floor_z + r),
            cq.Vector(1, 0, 0))
        return block.cut(cyl)

    def _label_shelf(self, y_back, span, label_d):
        """45-degree triangular label shelf hanging from a back wall."""
        z_top = self.nominal_h
        pts = [(y_back, z_top), (y_back - label_d, z_top),
               (y_back, z_top - label_d)]
        return (
            cq.Workplane("YZ", origin=(-span / 2, 0, 0))
            .polyline(pts).close()
            .extrude(span)
        )

    def _notch_cut(self, n):
        depth = n["depth"] if n["depth"] is not None else self.total_h / 2
        w = n["width"]
        z_bot = self.total_h - depth
        length = (self.outer_w if n["side"] in ("+X", "-X")
                  else self.outer_d) / 2 + 1
        cutter = (
            cq.Workplane("YZ")
            .moveTo(-w / 2, self.total_h + 1)
            .lineTo(-w / 2, z_bot + w / 2)
            .threePointArc((0, z_bot), (w / 2, z_bot + w / 2))
            .lineTo(w / 2, self.total_h + 1)
            .close()
            .extrude(length)
        )
        angle = {"+X": 0, "+Y": 90, "-X": 180, "-Y": 270}[n["side"]]
        if angle:
            cutter = cutter.rotate((0, 0, 0), (0, 0, 1), angle)
        return cutter

    def _cut_base_holes(self, solid):
        """Magnet bores and/or screw holes, 4 per cell on a 26mm square."""
        half = HOLE_SPACING / 2
        positions = [(cx + dx, cy + dy)
                     for cx, cy in self._cell_centers()
                     for dx in (-half, half) for dy in (-half, half)]
        if self.magnets:
            cutter = (cq.Workplane("XY").pushPoints(positions)
                      .circle(MAGNET_D / 2).extrude(MAGNET_DEPTH))
            solid = solid.cut(cutter)
        if self.screws:
            cutter = (cq.Workplane("XY").pushPoints(positions)
                      .circle(SCREW_D / 2).extrude(SCREW_DEPTH))
            solid = solid.cut(cutter)
        return solid

    def summary(self):
        """One-paragraph description of the built dimensions."""
        lip = f" + {BASE_H}mm lip" if self.stacking_lip else ""
        return (f"Gridfinity {self.grid_x}x{self.grid_y} bin, "
                f"{self.height_units}U ({self.nominal_h:.0f}mm{lip}): "
                f"{self.outer_w:.1f} x {self.outer_d:.1f} x "
                f"{self.total_h:.2f}mm, interior floor at Z="
                f"{self.floor_z:.2f}mm, max cavity depth "
                f"{self.max_depth:.2f}mm")
