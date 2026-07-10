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

import math
from typing import NamedTuple

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

# ============================================================
# PRINTABILITY DEFAULTS (mm) - 0.4mm-nozzle FDM, tunable
# ============================================================
MIN_WALL = 1.2           # minimum wall/divider thickness
DEFAULT_FLOOR = 2.0      # solid floor above the base profile
TOP_CHAMFER = 0.6        # rim edge chamfer

_INSET_BOT = TAPER_1 + TAPER_2   # 2.95 - footprint inset at the very bottom
_INSET_MID = TAPER_2             # 2.15 - inset at the riser
_EPS = 0.01


class GridfinityError(ValueError):
    """Raised when a bin configuration cannot produce valid geometry."""


class _Pocket(NamedTuple):
    length: float
    width: float
    depth: float
    radii: tuple
    center: tuple


class _PolygonPocket(NamedTuple):
    points: list
    depth: float
    clearance: float


class _Compartments(NamedTuple):
    cols: int
    rows: int
    wall_t: float
    scoop_r: float
    label_tab: bool
    label_d: float


class _CylinderPocket(NamedTuple):
    diameter: float
    depth: float
    center: tuple
    tilt: float
    tilt_dir: tuple
    round_bottom: bool


class _Notch(NamedTuple):
    side: str
    width: float
    depth: float
    offset: float


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


def _compound(parts):
    """Collect the solids of several workplanes/solids into one Compound.

    Booleans against a single compound are much cheaper than one OCC
    operation per feature. ONLY safe when the solids are disjoint or
    the boolean is a fuse; CUTTING with a compound of overlapping tools
    leaves internal faces. Use _fused for cutters that may overlap.
    """
    solids = []
    for p in parts:
        solids.extend(p.vals() if isinstance(p, cq.Workplane) else [p])
    return cq.Compound.makeCompound(solids)


def _fused(parts):
    """Combine cutter workplanes into one safe boolean tool.

    Disjoint cutters ride in a cheap Compound; if any two bounding
    boxes intersect, everything is fused instead so the cut cannot
    leave internal faces. clean=False: the tool is discarded after
    the cut, the built solid gets its own clean().
    """
    if len(parts) == 1:
        return parts[0]
    solids = []
    for p in parts:
        solids.extend(p.vals() if isinstance(p, cq.Workplane) else [p])
    boxes = [s.BoundingBox() for s in solids]
    overlapping = any(
        a.xmin <= b.xmax and b.xmin <= a.xmax and
        a.ymin <= b.ymax and b.ymin <= a.ymax and
        a.zmin <= b.zmax and b.zmin <= a.zmax
        for i, a in enumerate(boxes) for b in boxes[i + 1:])
    if not overlapping:
        return cq.Compound.makeCompound(solids)
    return parts[0].union(_compound(parts[1:]), clean=False)


class GridfinityBin:
    """Builder for a spec-compatible Gridfinity bin.

    Create the bin, add features, then call `build()` to get a
    `cq.Workplane` with the bottom at Z=0.
    """

    def __init__(self, grid_x, grid_y, height_units,
                 stacking_lip=True, magnets=False, screws=False,
                 floor_t=DEFAULT_FLOOR):
        self.grid_x = grid_x
        self.grid_y = grid_y
        self.height_units = height_units
        self.stacking_lip = stacking_lip
        self.magnets = magnets
        self.screws = screws
        self.floor_t = floor_t
        self._pockets = []
        self._polygon_pockets = []
        self._cylinder_pockets = []
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
        self._pockets.append(_Pocket(
            length, width, self.max_depth if depth is None else depth,
            _corner_radii(corner_r), center))
        return self

    def add_polygon_pocket(self, points, depth=None, clearance=0.0):
        """Cavity with an arbitrary closed outline (list of (x, y) mm).

        `clearance` offsets the outline outward, e.g. to add fit
        clearance around a traced object. `depth=None` reaches the floor.
        """
        self._polygon_pockets.append(_PolygonPocket(
            list(points), self.max_depth if depth is None else depth,
            clearance))
        return self

    def add_cylinder_pocket(self, diameter, depth=None, center=(0.0, 0.0),
                            tilt=0.0, tilt_dir=None, round_bottom=False):
        """Round cavity cut from the top rim down `depth` mm.

        Useful for finger wells next to an object pocket, batteries,
        coins, dowels. Overlapping another pocket merges the cavities.
        `depth=None` reaches the floor. `center` is the opening center
        at the rim.

        For a smooth thumb scoop instead of a straight hole: set
        `round_bottom=True` (hemispherical bottom) and lean the bore
        with `tilt` (degrees from vertical, max 45 so it prints without
        supports) toward `tilt_dir`, an (dx, dy) direction the bottom
        tip shifts along, e.g. toward the object pocket.
        """
        if tilt and tilt_dir is None:
            raise GridfinityError("tilt_dir is required when tilt is set")
        if tilt_dir is not None:
            norm = math.hypot(*tilt_dir)
            if norm == 0:
                raise GridfinityError("tilt_dir must be a non-zero (dx, dy)")
            tilt_dir = (tilt_dir[0] / norm, tilt_dir[1] / norm)
        self._cylinder_pockets.append(_CylinderPocket(
            diameter, self.max_depth if depth is None else depth, center,
            tilt, tilt_dir, round_bottom))
        return self

    def add_compartments(self, cols=1, rows=1, wall_t=MIN_WALL,
                         scoop_r=0.0, label_tab=False, label_d=12.0):
        """Classic divided storage interior: cols x rows compartments.

        Optional `scoop_r` rounds the front (-Y) floor edge of every
        compartment; `label_tab` adds a 45-degree label shelf along the
        back (+Y) of every row, `label_d` mm deep.
        """
        if self._compartments is not None:
            raise GridfinityError("add_compartments can only be called once")
        self._compartments = _Compartments(
            cols, rows, wall_t, scoop_r, label_tab, label_d)
        return self

    def add_finger_notch(self, side="+X", width=20.0, depth=None,
                         offset=0.0):
        """U-shaped scallop cut into one side wall from the top rim.

        `side` is one of "+X", "-X", "+Y", "-Y". `depth` defaults to
        half the bin height, measured from the top rim. `offset` slides
        the notch along the wall from its center (mm, signed).
        """
        self._notches.append(_Notch(
            side, width, self.total_h / 2 if depth is None else depth,
            offset))
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
        if self.screws and self.floor_z < SCREW_DEPTH + 0.6:
            raise GridfinityError(
                f"screw holes are {SCREW_DEPTH}mm deep; floor_t must be >= "
                f"{SCREW_DEPTH + 0.6 - BASE_H:.2f}mm to keep a printable "
                f"membrane above them")

        for p in self._pockets:
            self._check_depth(p.depth, "pocket")
            self._check_wall_clearance(
                p.length / 2, p.width / 2, p.center,
                f"pocket {p.length}x{p.width}mm at {p.center}")
            ra, rb, rc, rd = p.radii
            if (ra + rb > p.length or rc + rd > p.length or
                    rb + rc > p.width or ra + rd > p.width):
                raise GridfinityError("pocket corner radii exceed pocket size")

        for p in self._polygon_pockets:
            if len(p.points) < 3:
                raise GridfinityError("polygon pocket needs >= 3 points")
            self._check_depth(p.depth, "polygon pocket")
            xs = [pt[0] for pt in p.points]
            ys = [pt[1] for pt in p.points]
            self._check_wall_clearance(
                max(map(abs, xs)) + p.clearance,
                max(map(abs, ys)) + p.clearance, (0, 0),
                "polygon pocket (plus clearance)")

        for p in self._cylinder_pockets:
            self._check_depth(p.depth, "cylinder pocket")
            self._check_wall_clearance(
                p.diameter / 2, p.diameter / 2, p.center,
                f"cylinder pocket d={p.diameter}mm at {p.center}")
            if not 0 <= p.tilt <= 45:
                raise GridfinityError(
                    "cylinder pocket tilt must be 0..45 degrees "
                    "(above 45 the bore ceiling needs supports)")
            if p.round_bottom and p.depth < p.diameter / 2:
                raise GridfinityError(
                    "round_bottom needs depth >= diameter/2")
            if p.tilt:
                shift = self._cylinder_drop(p) * math.tan(
                    math.radians(p.tilt))
                bottom = (p.center[0] + shift * p.tilt_dir[0],
                          p.center[1] + shift * p.tilt_dir[1])
                self._check_wall_clearance(
                    p.diameter / 2, p.diameter / 2, bottom,
                    f"tilted cylinder pocket bottom at "
                    f"({bottom[0]:.1f}, {bottom[1]:.1f})")

        c = self._compartments
        if c:
            if c.wall_t < MIN_WALL:
                raise GridfinityError(f"divider wall_t must be >= {MIN_WALL}mm")
            comp_w, comp_d, _, _ = self._compartment_size()
            if comp_w < 5 or comp_d < 5:
                raise GridfinityError(
                    f"compartments are {comp_w:.1f}x{comp_d:.1f}mm; "
                    "reduce cols/rows or wall_t (5mm minimum)")
            if c.scoop_r > min(comp_d, self.nominal_h - self.floor_z):
                raise GridfinityError("scoop_r too large for the compartment")
            if c.label_tab and c.label_d > min(
                    comp_d, self.nominal_h - self.floor_z):
                raise GridfinityError("label_d too large for the compartment")

        for n in self._notches:
            if n.side not in ("+X", "-X", "+Y", "-Y"):
                raise GridfinityError('notch side must be "+X", "-X", "+Y" or "-Y"')
            if n.width < 2:
                raise GridfinityError("notch width must be >= 2mm")
            if n.depth < n.width / 2:
                raise GridfinityError("notch depth must be >= width/2")
            self._check_depth(n.depth, "finger notch")
            wall_half = (self.outer_d if n.side in ("+X", "-X")
                         else self.outer_w) / 2
            if abs(n.offset) + n.width / 2 > wall_half - CORNER_R:
                raise GridfinityError(
                    f"notch offset {n.offset}mm pushes it past the wall "
                    f"(usable half-span {wall_half - CORNER_R:.1f}mm)")

    def _check_wall_clearance(self, half_x, half_y, center, what):
        """Feature footprint must leave MIN_WALL of outer wall."""
        cx, cy = center
        if (abs(cx) + half_x > self.outer_w / 2 - MIN_WALL or
                abs(cy) + half_y > self.outer_d / 2 - MIN_WALL):
            raise GridfinityError(
                f"{what} leaves less than {MIN_WALL}mm of outer wall "
                f"(interior is {self.outer_w - 2 * MIN_WALL:.1f}x"
                f"{self.outer_d - 2 * MIN_WALL:.1f}mm)")

    def _check_depth(self, depth, what):
        if depth > self.max_depth + _EPS:
            raise GridfinityError(
                f"{what} depth {depth}mm exceeds max {self.max_depth:.2f}mm "
                f"({self.floor_t}mm floor above the {BASE_H}mm base)")

    def _compartment_size(self):
        c = self._compartments
        interior_w = self.outer_w - 2 * c.wall_t
        interior_d = self.outer_d - 2 * c.wall_t
        comp_w = (interior_w - (c.cols - 1) * c.wall_t) / c.cols
        comp_d = (interior_d - (c.rows - 1) * c.wall_t) / c.rows
        return comp_w, comp_d, interior_w, interior_d

    # ------------------------------------------------------------
    # Geometry
    # ------------------------------------------------------------
    def build(self):
        """Validate and build; returns a cq.Workplane, bottom at Z=0."""
        self._validate()

        solid = self._body().union(self._base_cells())
        if self.stacking_lip:
            solid = solid.cut(self._lip_cut())

        # Batch all interior cutters into one boolean, then all added
        # material (scoops, label shelves) into one union. Notches come
        # after the unions so a notch can pass through a scoop.
        cutters = [self._pocket_cut(p) for p in self._pockets]
        cutters += [self._polygon_cut(p) for p in self._polygon_pockets]
        cutters += [self._cylinder_cut(p) for p in self._cylinder_pockets]
        adds = []
        if self._compartments:
            comp_cutters, comp_adds = self._compartment_solids()
            cutters += comp_cutters
            adds += comp_adds
        if cutters:
            solid = solid.cut(_fused(cutters))
        if adds:
            solid = solid.union(_compound(adds))
        if self._notches:
            solid = solid.cut(
                _fused([self._notch_cut(n) for n in self._notches]))
        if self.magnets or self.screws:
            solid = solid.cut(self._base_hole_cutter())

        return solid.clean()

    def _cell_centers(self):
        return [((ix - (self.grid_x - 1) / 2) * GRID_PITCH,
                 (iy - (self.grid_y - 1) / 2) * GRID_PITCH)
                for ix in range(self.grid_x) for iy in range(self.grid_y)]

    def _base_cells(self):
        """Per-cell base profile: taper, riser, taper (45 degrees).

        The sketch fillet starts at CORNER_R - 2.95 so the corner radius
        grows through the tapers to exactly CORNER_R at the top, flowing
        into the body fillet with no step (spec radii 0.8 / 1.6 / 3.75).
        All cells are identical: build one at the origin and translate
        copies to each grid position.
        """
        cell_size = GRID_PITCH - 2 * CLEARANCE
        cell_bot = cell_size - 2 * _INSET_BOT

        cell = (
            cq.Workplane("XY")
            .sketch().rect(cell_bot, cell_bot)
            .vertices().fillet(CORNER_R - _INSET_BOT).finalize()
            .extrude(TAPER_1, taper=-45)
        )
        cell = cell.faces(">Z").wires().toPending().extrude(RISER)
        cell = (cell.faces(">Z").wires().toPending()
                .extrude(TAPER_2, taper=-45))
        solid = cell.val()
        return _compound([solid.translate(cq.Vector(cx, cy, 0))
                          for cx, cy in self._cell_centers()])

    def _body(self):
        return (
            cq.Workplane("XY")
            .transformed(offset=(0, 0, BASE_H))
            .box(self.outer_w, self.outer_d, self.total_h - BASE_H,
                 centered=(True, True, False))
            .edges("|Z").fillet(CORNER_R)
            .edges(">Z").chamfer(TOP_CHAMFER)
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
        wp = cq.Workplane("XY").workplane(offset=self.total_h - p.depth)
        return _rounded_rect(wp, p.length, p.width, p.radii,
                             p.center).extrude(p.depth + 1)

    def _polygon_cut(self, p):
        wp = (cq.Workplane("XY").workplane(offset=self.total_h - p.depth)
              .polyline(p.points).close())
        if p.clearance > 0:
            wp = wp.offset2D(p.clearance)
        return wp.extrude(p.depth + 1)

    def _cylinder_drop(self, p):
        """Vertical span of the bore's cylindrical part."""
        return p.depth - (p.diameter / 2 if p.round_bottom else 0)

    def _cylinder_cut(self, p):
        r = p.diameter / 2
        t = math.radians(p.tilt)
        axis_len = self._cylinder_drop(p) / math.cos(t)
        top_extra = 5.0  # reach above the rim so the cut clears the chamfer
        if p.round_bottom:
            # Single revolved capsule: a cylinder unioned with a tangent
            # sphere leaves a degenerate seam that breaks watertightness.
            k = r * math.sin(math.radians(45))
            cutter = (
                cq.Workplane("XZ")
                .moveTo(0, top_extra)
                .lineTo(r, top_extra)
                .lineTo(r, -axis_len)
                .threePointArc((k, -axis_len - k), (0, -axis_len - r))
                .close()
                .revolve(360, (0, 0), (0, 1))
            )
        else:
            cutter = (cq.Workplane("XY", origin=(0, 0, top_extra))
                      .circle(r).extrude(-(axis_len + top_extra)))
        if p.tilt:
            # Rotate about the opening center; axis (dy, -dx) swings the
            # bottom tip toward tilt_dir.
            dx, dy = p.tilt_dir
            cutter = cutter.rotate((0, 0, 0), (dy, -dx, 0), p.tilt)
        return cutter.translate((p.center[0], p.center[1], self.total_h))

    def _compartment_solids(self):
        """Cutters (cavities) and additions (scoops, label shelves)."""
        c = self._compartments
        comp_w, comp_d, interior_w, interior_d = self._compartment_size()
        # Interior corner radius floors at 0.5mm: with dividers thicker
        # than the body fillet the interior corners just get near-sharp,
        # which is valid geometry (this is a choice, not a repair).
        pocket_r = max(0.5, CORNER_R - c.wall_t)

        cutters, adds = [], []
        for col in range(c.cols):
            for row in range(c.rows):
                cx = -interior_w / 2 + col * (comp_w + c.wall_t) + comp_w / 2
                cy = -interior_d / 2 + row * (comp_d + c.wall_t) + comp_d / 2
                wp = cq.Workplane("XY").workplane(offset=self.floor_z)
                cutters.append(
                    _rounded_rect(wp, comp_w, comp_d, (pocket_r,) * 4,
                                  (cx, cy)).extrude(self.max_depth + 1))
                if c.scoop_r > 0:
                    adds.append(self._scoop(cx, cy - comp_d / 2, comp_w,
                                            c.scoop_r))
        if c.label_tab:
            for row in range(c.rows):
                y_back = -interior_d / 2 + row * (comp_d + c.wall_t) + comp_d
                adds.append(self._label_shelf(y_back, interior_w, c.label_d))
        return cutters, adds

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
        w = n.width
        z_bot = self.total_h - n.depth
        length = (self.outer_w if n.side in ("+X", "-X")
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
        angle = {"+X": 0, "+Y": 90, "-X": 180, "-Y": 270}[n.side]
        if angle:
            cutter = cutter.rotate((0, 0, 0), (0, 0, 1), angle)
        if n.offset:
            # Slide along the wall: the +-X walls span Y, +-Y walls span X.
            shift = ((0, n.offset, 0) if n.side in ("+X", "-X")
                     else (n.offset, 0, 0))
            cutter = cutter.translate(shift)
        return cutter

    def _base_hole_cutter(self):
        """Magnet bores and/or screw holes, 4 per cell on a 26mm square."""
        half = HOLE_SPACING / 2
        positions = [(cx + dx, cy + dy)
                     for cx, cy in self._cell_centers()
                     for dx in (-half, half) for dy in (-half, half)]
        cutters = []
        for enabled, dia, depth in ((self.magnets, MAGNET_D, MAGNET_DEPTH),
                                    (self.screws, SCREW_D, SCREW_DEPTH)):
            if enabled:
                cutters.append(cq.Workplane("XY").pushPoints(positions)
                               .circle(dia / 2).extrude(depth))
        # Magnet bores and screw holes are concentric counterbores;
        # _fused detects the overlap and fuses them into one tool.
        return _fused(cutters)

    def summary(self):
        """One-paragraph description of the built dimensions."""
        lip = f" + {BASE_H}mm lip" if self.stacking_lip else ""
        return (f"Gridfinity {self.grid_x}x{self.grid_y} bin, "
                f"{self.height_units}U ({self.nominal_h:.0f}mm{lip}): "
                f"{self.outer_w:.1f} x {self.outer_d:.1f} x "
                f"{self.total_h:.2f}mm, interior floor at Z="
                f"{self.floor_z:.2f}mm, max cavity depth "
                f"{self.max_depth:.2f}mm")
